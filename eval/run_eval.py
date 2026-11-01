"""Execution-accuracy eval: compare the agent's result set with a hand-written gold query."""
import json
import sys
from pathlib import Path

from data_agent.agent import DataAgent
from data_agent.make_db import build


def _norm(rows, ordered):
    rows = [tuple(round(x, 2) if isinstance(x, float) else x for x in r) for r in rows]
    return rows if ordered else sorted(rows, key=repr)


def evaluate(path: str, verbose: bool = False) -> dict:
    con = build()
    agent = DataAgent(con)
    cases = json.loads(Path(path).read_text())
    res = {"n": len(cases), "correct": 0, "answerable": 0, "answer_correct": 0,
           "abstain_cases": 0, "abstain_correct": 0, "wrong_answers": 0, "false_abstain": 0, "fails": []}
    for c in cases:
        a = agent.ask(c["q"])
        if c["gold"] == "ABSTAIN":
            res["abstain_cases"] += 1
            ok = a.abstained
            res["abstain_correct"] += ok
            if not ok:
                res["wrong_answers"] += 1
        else:
            res["answerable"] += 1
            if a.abstained:
                ok = False
                res["false_abstain"] += 1
            else:
                gold = con.execute(c["gold"]).fetchall()
                ok = _norm(a.rows, c.get("ordered")) == _norm(gold, c.get("ordered"))
                res["wrong_answers"] += not ok
            res["answer_correct"] += ok
        res["correct"] += ok
        if not ok:
            res["fails"].append({"q": c["q"], "sql": a.sql, "reason": a.reason})
        if verbose:
            print(("PASS " if ok else "FAIL ") + c["q"])
    res["accuracy"] = round(res["correct"] / res["n"], 3)
    return res


if __name__ == "__main__":
    for p in sys.argv[1:] or ["eval/cases_dev.json"]:
        r = evaluate(p, verbose=True)
        print(json.dumps({k: v for k, v in r.items() if k != "fails"}, indent=1))
        for f in r["fails"]:
            print("  ", f)
