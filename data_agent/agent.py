"""The agent loop: discover -> plan -> guard -> execute -> answer (or abstain)."""
import sqlite3
from dataclasses import dataclass

from . import guard, schema as sch
from .planner import get_planner


@dataclass
class Answer:
    question: str
    sql: str | None
    rows: list | None
    abstained: bool
    reason: str | None = None


class DataAgent:
    def __init__(self, con: sqlite3.Connection, planner=None):
        self.con = con
        con.execute("PRAGMA query_only = ON")  # second line of defence: connection is read-only
        self.schema = sch.discover(con)
        self.joins = sch.infer_joins(con, self.schema)
        self.planner = planner or get_planner()

    def ask(self, question: str) -> Answer:
        plan = self.planner.plan(question, self.schema)
        if plan.sql is None:
            return Answer(question, None, None, True, plan.abstain_reason)
        try:
            safe = guard.check(plan.sql, self.con, self.schema)
        except guard.GuardError as e:
            return Answer(question, plan.sql, None, True, f"blocked by guard: {e}")
        rows = self.con.execute(safe).fetchall()
        return Answer(question, safe, rows, False)
