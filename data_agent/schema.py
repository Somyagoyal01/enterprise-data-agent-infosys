"""Data discovery: list tables/columns, profile them, infer join keys."""
import sqlite3
from dataclasses import dataclass, field


@dataclass
class Column:
    table: str
    name: str
    dtype: str
    null_rate: float = 0.0
    distinct: int = 0
    sample_values: list = field(default_factory=list)
    min: object = None
    max: object = None


def discover(con: sqlite3.Connection) -> dict:
    """Return {table: {column_name: Column}} with a basic profile per column."""
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    out = {}
    for t in tables:
        n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] or 1
        cols = {}
        for _, name, dtype, *_ in con.execute(f'PRAGMA table_info("{t}")'):
            nulls, distinct, lo, hi = con.execute(
                f'SELECT SUM("{name}" IS NULL), COUNT(DISTINCT "{name}"), MIN("{name}"), MAX("{name}") FROM "{t}"'
            ).fetchone()
            sample = []
            if dtype == "TEXT" and distinct <= 12:
                sample = [r[0] for r in con.execute(
                    f'SELECT DISTINCT "{name}" FROM "{t}" WHERE "{name}" IS NOT NULL ORDER BY 1')]
            cols[name] = Column(t, name, dtype, (nulls or 0) / n, distinct, sample, lo, hi)
        out[t] = cols
    return out


def infer_joins(con: sqlite3.Connection, schema: dict, min_overlap: float = 0.95) -> list:
    """Guess foreign keys: a column named like another table's *_id primary key whose
    values are (almost) all present in that table."""
    joins = []
    pks = {t: next(iter(cols)) for t, cols in schema.items()}
    for t, cols in schema.items():
        for c in cols:
            for t2, pk in pks.items():
                if t2 == t or c != pk:
                    continue
                total, hit = con.execute(
                    f'SELECT COUNT(*), SUM("{c}" IN (SELECT "{pk}" FROM "{t2}")) FROM "{t}"').fetchone()
                if total and hit / total >= min_overlap:
                    joins.append((t, c, t2, pk))
    return joins


def quality_report(con: sqlite3.Connection, schema: dict) -> list:
    """Plain-language data-quality findings a data steward would want to see."""
    issues = []
    for t, cols in schema.items():
        for c in cols.values():
            if c.null_rate > 0:
                issues.append(f"{t}.{c.name}: {c.null_rate:.1%} missing")
            if c.dtype == "INTEGER" and isinstance(c.min, int) and c.min < 0 and "quantity" in c.name:
                issues.append(f"{t}.{c.name}: negative values (min {c.min})")
    if "customers" in schema:
        dup = con.execute(
            "SELECT COUNT(*) FROM (SELECT email FROM customers WHERE email IS NOT NULL GROUP BY email HAVING COUNT(*)>1)"
        ).fetchone()[0]
        if dup:
            issues.append(f"customers: {dup} email(s) shared by more than one customer_id (possible duplicates)")
    return issues


def schema_prompt(schema: dict, joins: list) -> str:
    """Compact schema context for an LLM prompt (used by the real-LLM path)."""
    lines = []
    for t, cols in schema.items():
        parts = []
        for c in cols.values():
            hint = f" e.g. {c.sample_values[:4]}" if c.sample_values else ""
            parts.append(f"{c.name} {c.dtype}{hint}")
        lines.append(f"{t}({', '.join(parts)})")
    lines += [f"JOIN {a}.{b} = {c}.{d}" for a, b, c, d in joins]
    return "\n".join(lines)
