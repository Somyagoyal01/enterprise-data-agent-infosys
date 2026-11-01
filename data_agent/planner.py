"""Question -> SQL planning.

Two planners share one interface (plan(question, schema) -> Plan):
- RulePlanner: offline, deterministic, no API key. It maps words to metrics,
  dimensions and filters using the profiled schema (column names and the
  distinct values found by the profiler). It abstains when it cannot ground
  every part of the question.
- LLMPlanner: optional real-LLM path (OpenAI-compatible). It sends the schema
  context and asks for one SELECT statement. The guard checks its output the
  same way it checks the rule planner's.
"""
import os
import re
from dataclasses import dataclass, field

REVENUE = "SUM(oi.quantity * p.unit_price)"
BASE = ("FROM orders o JOIN order_items oi ON oi.order_id = o.order_id "
        "JOIN products p ON p.product_id = oi.product_id "
        "JOIN customers c ON c.customer_id = o.customer_id")

METRICS = {  # order matters: more specific phrases first
    "customers": (["how many customers", "number of customers", "customer count", "customers"], "COUNT(DISTINCT c.customer_id)"),
    "aov": (["average order value", "aov"], f"ROUND({REVENUE} * 1.0 / COUNT(DISTINCT o.order_id), 2)"),
    "revenue": (["revenue", "sales", "turnover", "billing", "how much did we sell"], f"ROUND({REVENUE}, 2)"),
    "units": (["units", "quantity sold", "how many units"], "SUM(oi.quantity)"),
    "orders": (["number of orders", "how many orders", "order count", "orders"], "COUNT(DISTINCT o.order_id)"),
}
METRIC_WORDS = {w for ws, _ in METRICS.values() for w in ws}
DIMENSIONS = {
    "region": (["region", "regions"], "c.region"),
    "segment": (["segment", "segments"], "c.segment"),
    "category": (["category", "categories"], "p.category"),
    "product": (["product", "products"], "p.product_name"),
    "month": (["month", "monthly", "per month"], "substr(o.order_date, 1, 7)"),
    "status": (["status"], "o.status"),
}
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
UNSUPPORTED = ["profit", "margin", "cost", "employee", "salary", "discount", "churn", "forecast", "delete", "drop", "update"]


@dataclass
class Plan:
    sql: str | None
    abstain_reason: str | None = None
    notes: list = field(default_factory=list)


def _find(q: str, words: list) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", q) for w in words)


class RulePlanner:
    name = "rule"

    def plan(self, question: str, schema: dict) -> Plan:
        q = question.lower().strip()
        bad = [w for w in UNSUPPORTED if re.search(rf"\b{w}", q)]
        if bad:
            return Plan(None, f"no column in the schema supports '{bad[0]}'")
        metric = next((k for k, (ws, _) in METRICS.items() if _find(q, ws)), None)
        if metric is None:
            return Plan(None, "could not map the question to a known metric")
        # 'customers' as a metric only when asked to count them
        if metric == "customers" and not re.search(r"how many|number of|count", q):
            metric = next((k for k, (ws, _) in METRICS.items() if k != "customers" and _find(q, ws)), None)
            if metric is None:
                return Plan(None, "could not map the question to a known metric")
        expr = METRICS[metric][1]
        notes, where = [], []
        # value filters grounded in profiled distinct values
        for col_key, col in [("region", "c.region"), ("segment", "c.segment"),
                             ("category", "p.category"), ("status", "o.status")]:
            table, cname = {"c": "customers", "p": "products", "o": "orders"}[col[0]], col.split(".")[1]
            for v in schema[table][cname].sample_values:
                if re.search(rf"\b{re.escape(str(v).lower())}\b", q):
                    where.append(f"{col} = '{v}'")
        if metric in ("revenue", "aov", "units") and not any(w.startswith("o.status") for w in where):
            where.append("o.status = 'completed'")
            notes.append("revenue counts completed orders only")
        m = re.search(r"\b(" + "|".join(MONTHS) + r")\s+(20\d\d)\b", q)
        if m:
            where.append(f"substr(o.order_date, 1, 7) = '{m.group(2)}-{MONTHS[m.group(1)]:02d}'")
        else:
            y = re.search(r"\b(?:in|for|during)\s+(20\d\d)\b", q)
            if y:
                where.append(f"substr(o.order_date, 1, 4) = '{y.group(1)}'")
        dim = None
        by = re.search(r"\b(?:by|per|for each|each|across)\s+(\w+)", q)
        if by:
            dim = next((k for k, (ws, _) in DIMENSIONS.items() if by.group(1) in ws), None)
            if dim is None and by.group(1) not in METRIC_WORDS and by.group(1) != "the":
                return Plan(None, f"unknown grouping '{by.group(1)}'")
        top = re.search(r"\btop\s+(\d+)\s+(\w+)", q)
        if top and dim is None:
            dim = next((k for k, (ws, _) in DIMENSIONS.items() if top.group(2) in ws), None)
        if _find(q, ["monthly", "per month", "month by month"]):
            dim = "month"
        w = (" WHERE " + " AND ".join(where)) if where else ""
        if dim:
            d = DIMENSIONS[dim][1]
            order = "ORDER BY value DESC" if top or dim != "month" else "ORDER BY label"
            lim = f" LIMIT {int(top.group(1))}" if top else ""
            sql = f"SELECT {d} AS label, {expr} AS value {BASE}{w} GROUP BY {d} {order}{lim}"
        else:
            sql = f"SELECT {expr} AS value {BASE}{w}"
        return Plan(sql, None, notes)


class LLMPlanner:  # pragma: no cover - needs an API key and network
    name = "llm"

    def __init__(self, model: str = "gpt-4o-mini"):
        from openai import OpenAI
        self.client, self.model = OpenAI(), model

    def plan(self, question: str, schema: dict, schema_text: str = "") -> Plan:
        prompt = (
            "You write one SQLite SELECT statement for the question, using only these tables "
            "and columns. Revenue = SUM(order_items.quantity * products.unit_price) over "
            "completed orders. If the schema cannot answer it, reply exactly ABSTAIN: <reason>.\n\n"
            f"{schema_text}\n\nQuestion: {question}\nSQL:"
        )
        out = self.client.chat.completions.create(
            model=self.model, temperature=0,
            messages=[{"role": "user", "content": prompt}]).choices[0].message.content.strip()
        if out.upper().startswith("ABSTAIN"):
            return Plan(None, out.split(":", 1)[-1].strip())
        return Plan(out.strip("`").removeprefix("sql").strip())


def get_planner():
    if os.getenv("OPENAI_API_KEY") and os.getenv("DATA_AGENT_USE_LLM") == "1":
        return LLMPlanner()
    return RulePlanner()
