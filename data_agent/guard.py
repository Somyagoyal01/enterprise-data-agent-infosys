"""SQL guardrails: read-only, single statement, only known tables, bounded output."""
import re
import sqlite3

FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|pragma|vacuum)\b", re.I)


class GuardError(ValueError):
    pass


def check(sql: str, con: sqlite3.Connection, schema: dict, max_rows: int = 200) -> str:
    s = sql.strip().rstrip(";")
    if ";" in s:
        raise GuardError("more than one statement")
    if not re.match(r"(?is)^\s*(select|with)\b", s):
        raise GuardError("only SELECT queries are allowed")
    if FORBIDDEN.search(s):
        raise GuardError("write or admin keyword found")
    used = set(re.findall(r"(?i)\b(?:from|join)\s+\"?(\w+)", s))
    unknown = used - set(schema)
    if unknown:
        raise GuardError(f"unknown table(s): {sorted(unknown)}")
    try:  # sqlite validates column names at prepare time
        con.execute("EXPLAIN " + s)
    except sqlite3.Error as e:
        raise GuardError(f"invalid SQL: {e}") from e
    if not re.search(r"(?i)\blimit\s+\d+", s):
        s += f" LIMIT {max_rows}"
    return s
