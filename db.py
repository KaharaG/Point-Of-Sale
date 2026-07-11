"""
db.py
Data layer for the POS system. Raw sqlite3 — no ORM.
Handles schema creation, connections, and every query the app needs.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pos.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        category TEXT,
        price REAL NOT NULL,
        cost REAL DEFAULT 0,
        track_by TEXT NOT NULL CHECK(track_by IN ('imei','qty')),
        qty INTEGER DEFAULT 0,
        reorder_level INTEGER DEFAULT 5,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS imei_units (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL REFERENCES products(id),
        imei TEXT UNIQUE NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('in_stock','sold')) DEFAULT 'in_stock',
        added_at TEXT NOT NULL,
        sold_at TEXT
    );

    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        total REAL NOT NULL,
        payment_method TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sale_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER NOT NULL REFERENCES sales(id),
        product_id INTEGER NOT NULL REFERENCES products(id),
        imei TEXT,
        qty INTEGER NOT NULL,
        unit_price REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS stock_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL REFERENCES products(id),
        imei TEXT,
        change INTEGER NOT NULL,
        reason TEXT NOT NULL,
        timestamp TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);
    CREATE INDEX IF NOT EXISTS idx_imei_units_imei ON imei_units(imei);
    CREATE INDEX IF NOT EXISTS idx_imei_units_product ON imei_units(product_id);
    CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items(sale_id);

    CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
        name, sku, content='products', content_rowid='id'
    );

    CREATE TRIGGER IF NOT EXISTS products_ai AFTER INSERT ON products BEGIN
        INSERT INTO products_fts(rowid, name, sku) VALUES (new.id, new.name, new.sku);
    END;
    CREATE TRIGGER IF NOT EXISTS products_ad AFTER DELETE ON products BEGIN
        INSERT INTO products_fts(products_fts, rowid, name, sku) VALUES ('delete', old.id, old.name, old.sku);
    END;
    CREATE TRIGGER IF NOT EXISTS products_au AFTER UPDATE ON products BEGIN
        INSERT INTO products_fts(products_fts, rowid, name, sku) VALUES ('delete', old.id, old.name, old.sku);
        INSERT INTO products_fts(rowid, name, sku) VALUES (new.id, new.name, new.sku);
    END;
    """)
    conn.commit()
    conn.close()


def _now():
    return datetime.now().isoformat(timespec="seconds")


# ---------- Product management ----------

def add_product(sku, name, category, price, cost, track_by, qty=0, reorder_level=5):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO products (sku, name, category, price, cost, track_by, qty, reorder_level, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (sku, name, category, price, cost, track_by, qty, reorder_level, _now())
        )
        conn.commit()
        return {"ok": True}
    except sqlite3.IntegrityError as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def add_imei_units(product_id, imei_list):
    """Bulk-add serialized units for a product. Skips duplicates, reports them."""
    conn = get_connection()
    added, skipped = [], []
    now = _now()
    try:
        for imei in imei_list:
            imei = imei.strip()
            if not imei:
                continue
            try:
                conn.execute(
                    "INSERT INTO imei_units (product_id, imei, status, added_at) VALUES (?,?,?,?)",
                    (product_id, imei, "in_stock", now)
                )
                conn.execute(
                    "INSERT INTO stock_log (product_id, imei, change, reason, timestamp) VALUES (?,?,?,?,?)",
                    (product_id, imei, 1, "restock", now)
                )
                added.append(imei)
            except sqlite3.IntegrityError:
                skipped.append(imei)
        conn.commit()
    finally:
        conn.close()
    return {"added": added, "skipped": skipped}


def restock_qty(product_id, amount):
    conn = get_connection()
    now = _now()
    try:
        conn.execute("UPDATE products SET qty = qty + ? WHERE id = ?", (amount, product_id))
        conn.execute(
            "INSERT INTO stock_log (product_id, imei, change, reason, timestamp) VALUES (?,?,?,?,?)",
            (product_id, None, amount, "restock", now)
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ---------- Lookup (scan / search) ----------

def lookup_by_imei(imei):
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT p.id as product_id, p.sku, p.name, p.category, p.price, u.imei, u.status
               FROM imei_units u JOIN products p ON p.id = u.product_id
               WHERE u.imei = ?""", (imei,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def lookup_by_sku(sku):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def search_products(query, limit=20):
    conn = get_connection()
    try:
        q = query.strip()
        if not q:
            return []
        # FTS5 needs escaping of special chars; wrap as prefix match
        fts_query = f'"{q}"*'
        try:
            rows = conn.execute(
                """SELECT p.* FROM products_fts f
                   JOIN products p ON p.id = f.rowid
                   WHERE products_fts MATCH ?
                   LIMIT ?""", (fts_query, limit)
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if not rows:
            rows = conn.execute(
                "SELECT * FROM products WHERE name LIKE ? OR sku LIKE ? LIMIT ?",
                (f"%{q}%", f"%{q}%", limit)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_available_imeis(product_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT imei FROM imei_units WHERE product_id = ? AND status = 'in_stock'",
            (product_id,)
        ).fetchall()
        return [r["imei"] for r in rows]
    finally:
        conn.close()


# ---------- Checkout ----------

def record_sale(cart_items, payment_method):
    """
    cart_items: list of dicts:
      { product_id, track_by, qty, unit_price, imei (optional, required if track_by == 'imei') }
    All-or-nothing transaction.
    """
    conn = get_connection()
    now = _now()
    try:
        conn.execute("BEGIN")

        # Validate stock availability first
        for item in cart_items:
            if item["track_by"] == "imei":
                row = conn.execute(
                    "SELECT status FROM imei_units WHERE imei = ? AND product_id = ?",
                    (item["imei"], item["product_id"])
                ).fetchone()
                if row is None:
                    raise ValueError(f"IMEI {item['imei']} not found")
                if row["status"] == "sold":
                    raise ValueError(f"IMEI {item['imei']} already sold")
            else:
                row = conn.execute(
                    "SELECT qty FROM products WHERE id = ?", (item["product_id"],)
                ).fetchone()
                if row is None or row["qty"] < item["qty"]:
                    raise ValueError(f"Insufficient stock for product {item['product_id']}")

        total = sum(i["qty"] * i["unit_price"] for i in cart_items)
        cur = conn.execute(
            "INSERT INTO sales (timestamp, total, payment_method) VALUES (?,?,?)",
            (now, total, payment_method)
        )
        sale_id = cur.lastrowid

        for item in cart_items:
            conn.execute(
                """INSERT INTO sale_items (sale_id, product_id, imei, qty, unit_price)
                   VALUES (?,?,?,?,?)""",
                (sale_id, item["product_id"], item.get("imei"), item["qty"], item["unit_price"])
            )
            if item["track_by"] == "imei":
                conn.execute(
                    "UPDATE imei_units SET status = 'sold', sold_at = ? WHERE imei = ?",
                    (now, item["imei"])
                )
                conn.execute(
                    "INSERT INTO stock_log (product_id, imei, change, reason, timestamp) VALUES (?,?,?,?,?)",
                    (item["product_id"], item["imei"], -1, "sale", now)
                )
            else:
                conn.execute(
                    "UPDATE products SET qty = qty - ? WHERE id = ?",
                    (item["qty"], item["product_id"])
                )
                conn.execute(
                    "INSERT INTO stock_log (product_id, imei, change, reason, timestamp) VALUES (?,?,?,?,?)",
                    (item["product_id"], None, -item["qty"], "sale", now)
                )

        conn.commit()
        return {"ok": True, "sale_id": sale_id, "total": total}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


# ---------- Reporting ----------

def get_low_stock():
    conn = get_connection()
    try:
        qty_rows = conn.execute(
            "SELECT * FROM products WHERE track_by = 'qty' AND qty <= reorder_level"
        ).fetchall()
        imei_rows = conn.execute("""
            SELECT p.*, COUNT(u.id) as available
            FROM products p
            LEFT JOIN imei_units u ON u.product_id = p.id AND u.status = 'in_stock'
            WHERE p.track_by = 'imei'
            GROUP BY p.id
            HAVING available <= p.reorder_level
        """).fetchall()
        return {
            "qty_items": [dict(r) for r in qty_rows],
            "imei_items": [dict(r) for r in imei_rows],
        }
    finally:
        conn.close()


def get_sales_history(limit=50):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM sales ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for r in rows:
            items = conn.execute(
                """SELECT si.*, p.name FROM sale_items si
                   JOIN products p ON p.id = si.product_id
                   WHERE si.sale_id = ?""", (r["id"],)
            ).fetchall()
            d = dict(r)
            d["items"] = [dict(i) for i in items]
            result.append(d)
        return result
    finally:
        conn.close()


def get_all_products():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM products ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
