"""Demo: profile the database, print data-quality findings, answer a few questions, run both evals."""
import json
from pathlib import Path

from data_agent.agent import DataAgent
from data_agent.make_db import build
from data_agent.schema import quality_report, schema_prompt
from eval.run_eval import evaluate

con = build()
agent = DataAgent(con)
print("== Schema context (what an LLM planner would see) ==")
print(schema_prompt(agent.schema, agent.joins))
print("\n== Data-quality findings ==")
for issue in quality_report(con, agent.schema):
    print(" -", issue)
print("\n== Questions ==")
for q in ["Revenue by region", "Top 3 products by revenue", "What is our profit margin?"]:
    a = agent.ask(q)
    print(f"Q: {q}\n   SQL: {a.sql}\n   -> {a.rows if not a.abstained else 'ABSTAIN: ' + a.reason}")
Path("results").mkdir(exist_ok=True)
summary = {}
for name in ["dev", "blind"]:
    r = evaluate(f"eval/cases_{name}.json")
    summary[name] = r
    print(f"\n== {name} eval: {r['correct']}/{r['n']} correct | answerable {r['answer_correct']}/{r['answerable']} | "
          f"abstain {r['abstain_correct']}/{r['abstain_cases']} | silent wrong answers {r['wrong_answers']} | false abstains {r['false_abstain']}")
Path("results/eval_summary.json").write_text(json.dumps(summary, indent=1))
