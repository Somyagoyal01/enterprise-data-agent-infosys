"""Synthetic enterprise sales database (clearly synthetic; no real or company data).

Tables: customers, products, orders, order_items. A few data-quality issues are
injected on purpose (missing emails, a duplicate customer, negative quantity)
so the profiler has something real to find.
"""
import random
import sqlite3
from datetime import date, timedelta

REGIONS = ["North", "South", "East", "West"]
SEGMENTS = ["Enterprise", "SMB", "Public Sector"]
CATEGORIES = {
    "Cloud": ["Cloud Migration Pack", "Managed Kubernetes", "Backup Vault"],
    "Data": ["Data Lake Starter", "BI Dashboards", "Data Quality Suite"],
    "AI": ["Document AI", "Chat Assistant", "Forecasting Engine"],
}


def build(path: str = ":memory:", seed: int = 7) -> sqlite3.Connection:
    rng = random.Random(seed)
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.executescript(
        """
        DROP TABLE IF EXISTS order_items; DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS products; DROP TABLE IF EXISTS customers;
        CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT,
            email TEXT, region TEXT, segment TEXT, signup_date TEXT);
        CREATE TABLE products (product_id INTEGER PRIMARY KEY, product_name TEXT,
            category TEXT, unit_price REAL);
        CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER,
            order_date TEXT, status TEXT);
        CREATE TABLE order_items (item_id INTEGER PRIMARY KEY, order_id INTEGER,
            product_id INTEGER, quantity INTEGER);
        """
    )
    pid = 1
    for cat, names in CATEGORIES.items():
        for n in names:
            cur.execute("INSERT INTO products VALUES (?,?,?,?)",
                        (pid, n, cat, round(rng.uniform(500, 9000), 2)))
            pid += 1
    for cid in range(1, 121):
        email = None if rng.random() < 0.08 else f"buyer{cid}@example.com"
        d = date(2024, 1, 1) + timedelta(days=rng.randint(0, 700))
        cur.execute("INSERT INTO customers VALUES (?,?,?,?,?,?)",
                    (cid, f"Client {cid:03d}", email, rng.choice(REGIONS),
                     rng.choice(SEGMENTS), d.isoformat()))
    # injected duplicate customer (same name/email, new id)
    cur.execute("INSERT INTO customers VALUES (121,'Client 005','buyer5@example.com','North','SMB','2025-03-01')")
    item = 1
    for oid in range(1, 601):
        d = date(2025, 1, 1) + timedelta(days=rng.randint(0, 545))
        status = rng.choices(["completed", "cancelled", "pending"], [0.8, 0.1, 0.1])[0]
        cur.execute("INSERT INTO orders VALUES (?,?,?,?)",
                    (oid, rng.randint(1, 121), d.isoformat(), status))
        for _ in range(rng.randint(1, 3)):
            q = rng.randint(1, 10)
            cur.execute("INSERT INTO order_items VALUES (?,?,?,?)",
                        (item, oid, rng.randint(1, pid - 1), q))
            item += 1
    cur.execute("UPDATE order_items SET quantity = -2 WHERE item_id = 17")  # injected bad row
    con.commit()
    return con


if __name__ == "__main__":
    build("data/sales.db")
    print("wrote data/sales.db")
