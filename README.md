# enterprise-data-agent-infosys

> Personal project by Somya Goyal, built while applying to Infosys (DAAI – AI/ML Engineer). Not affiliated with or endorsed by Infosys; uses a synthetic database only.

A small **structured-data agent**: it discovers and profiles a SQL database, flags data-quality issues, turns business questions into **guarded, read-only SQL**, and refuses questions the schema can't answer. An **execution-accuracy eval harness** (dev set plus a hand-written blind set written after the code freeze) shows where it is right, where it abstains, and where it is silently wrong.

## Why this matters for Infosys

- **The problem:** the DAAI role asks for "structured data agents that can connect to databases, inspect schemas, generate SQL" and for "AI evaluation routines covering answer quality … hallucination checks, regression tests". In a text-to-SQL agent, the expensive failure is a confident wrong number: a query that runs but answers a slightly different question.
- **Who feels it:** client analysts and business users who get numbers from an agent instead of a BI team, and the delivery teams who have to defend those numbers.
- **What this shows:** a schema-grounded agent with three safety layers (planner abstention, a SQL guard, a read-only connection) and an eval that counts silent wrong answers separately from refusals. That split tells a team which failures to fix first.
- **Context (public):** Infosys has launched 200+ enterprise AI agents as part of Infosys Topaz ([Infosys press release, 2025](https://www.infosys.com/newsroom/press-releases/2025/launches-enterprise-ai-agents.html)) and Topaz Fabric, a composable stack of data, models and agents ([Angel One, Nov 2025](https://www.angelone.in/news/market-updates/infosys-launches-topaz-fabric-to-transform-enterprise-ai-delivery)). This repo is a small, independent illustration of the data-agent pattern; it makes no claim about Infosys's internal systems.

## Demo

```bash
pip install -r requirements.txt
python run.py        # profile + quality report + sample Q&A + both evals
pytest -q            # 9 tests
```

Sample output:

```
Q: Revenue by region
   SQL: SELECT c.region AS label, ROUND(SUM(oi.quantity * p.unit_price), 2) AS value FROM orders o JOIN ... WHERE o.status = 'completed' GROUP BY c.region ORDER BY value DESC LIMIT 200
Q: What is our profit margin?
   -> ABSTAIN: no column in the schema supports 'profit'
```

## How it works

| Step | File | What it does |
|---|---|---|
| Synthetic data | `data_agent/make_db.py` | 121 customers, 9 products, 600 orders; injects missing emails, a duplicate customer, a negative quantity |
| Discovery & profiling | `data_agent/schema.py` | Tables/columns via PRAGMA, null rate, distinct counts, categorical values, **inferred joins** (name match + ≥95% value overlap), a data-quality report, and a compact schema prompt |
| Planning | `data_agent/planner.py` | Offline `RulePlanner` (no API key) maps metrics, groupings and filters to the profiled schema and abstains when it can't ground the question; optional `LLMPlanner` (OpenAI-compatible) uses the schema prompt |
| Guard | `data_agent/guard.py` | SELECT-only, single statement, no write/admin keywords, known tables only, `EXPLAIN` to validate columns, auto `LIMIT` |
| Agent | `data_agent/agent.py` | discover → plan → guard → execute; the connection runs with `PRAGMA query_only = ON` |
| Eval | `eval/run_eval.py` | Compares the agent's result set with hand-written gold SQL; reports answer accuracy, correct abstentions, **silent wrong answers** and false abstentions |

Real-LLM path: `OPENAI_API_KEY=... DATA_AGENT_USE_LLM=1 python run.py` (same guard and eval; not run for the numbers below).

## Results (offline rule planner, from `python run.py`)

| Set | Correct | Answerable correct | Correct abstain / block | Silent wrong answers | False abstains |
|---|---|---|---|---|---|
| Dev (12, used while building) | 12/12 | 10/10 | 2/2 | 0 | 0 |
| **Blind (15, hand-written after code freeze)** | **9/15 (60%)** | 6/12 | 3/3 | **3** | 3 |

Data-quality report found all three injected issues: 6.6% missing emails, a negative quantity, and one email shared by two customer IDs.

**Reading the blind result.** The unsafe cases were all handled (`drop table`, churn rate, salesperson). The three **silent wrong answers** matter most:
1. "Q1 2026" was ignored, so it returned all-time West revenue.
2. "product category" was grouped by product instead of category.
3. "including cancelled orders" was read as "only cancelled".

The three false abstains ("brought in the most money", listing customers with no email, a product-name filter) are vocabulary and coverage gaps. They are safer, but still misses.

## Limitations / next steps

- Abstain when a time, filter or negation word in the question is not grounded in the SQL (e.g. "Q1", "including", "excluding"). This would have turned all 3 silent errors into abstentions.
- Add product-name value matching and a "list rows" intent.
- Run the LLM planner through the same blind set and compare silent-error rates; add an LLM-as-judge check that the SQL answers the question.
- The data is synthetic and small; real schemas need table/column descriptions and sampling for profiling.
