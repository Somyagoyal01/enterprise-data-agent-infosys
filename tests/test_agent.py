import pytest

from data_agent import guard
from data_agent.agent import DataAgent
from data_agent.make_db import build
from data_agent.schema import discover, infer_joins, quality_report


@pytest.fixture(scope="module")
def con():
    return build()


def test_discovery_finds_tables_and_joins(con):
    schema = discover(con)
    assert set(schema) == {"customers", "orders", "order_items", "products"}
    joins = infer_joins(con, schema)
    assert ("orders", "customer_id", "customers", "customer_id") in joins
    assert ("order_items", "product_id", "products", "product_id") in joins


def test_quality_report_catches_injected_issues(con):
    issues = " | ".join(quality_report(con, discover(con)))
    assert "customers.email" in issues and "missing" in issues
    assert "negative" in issues
    assert "possible duplicates" in issues


@pytest.mark.parametrize("sql", [
    "DELETE FROM orders",
    "SELECT 1; DROP TABLE orders",
    "SELECT * FROM salaries",
    "SELECT not_a_column FROM orders",
])
def test_guard_blocks_unsafe_or_invalid(con, sql):
    with pytest.raises(guard.GuardError):
        guard.check(sql, con, discover(con))


def test_guard_adds_limit(con):
    assert guard.check("SELECT * FROM orders", con, discover(con)).endswith("LIMIT 200")


def test_agent_answers_and_abstains(con):
    agent = DataAgent(con)
    a = agent.ask("Revenue by region")
    assert not a.abstained and len(a.rows) == 4
    assert agent.ask("What is our profit margin?").abstained
    assert agent.ask("Delete all cancelled orders").abstained


def test_dev_eval_passes():
    from eval.run_eval import evaluate
    assert evaluate("eval/cases_dev.json")["accuracy"] == 1.0
