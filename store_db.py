"""資料庫層：讀取商店的 store.db（資料表名稱 product）。
若你的商店已有資料庫（MySQL / PostgreSQL 等），只需改 get_conn() 與 SQL 欄位名稱。"""
import os
import re
import sqlite3

DB_PATH = os.getenv("STORE_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "store.db"))
STOP = {"do", "you", "have", "in", "stock", "a", "the", "any", "got", "is", "are",
        "for", "me", "show", "i", "want", "need", "there", "some", "with", "and"}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


WANTED = [("quantity", "INTEGER NOT NULL DEFAULT 0"), ("category", "VARCHAR(50)"),
          ("color", "VARCHAR(30)"), ("description", "VARCHAR(300)")]


def ensure_schema():
    """檢查資料庫；缺少欄位就自動補上。有問題時回傳錯誤說明文字，沒問題回傳 None。"""
    with get_conn() as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(product)")}
        if not cols:
            tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            return f"這個 store.db 裡沒有 product 資料表，目前的資料表有：{tables}"
        for name, ddl in WANTED:
            if name not in cols:
                c.execute(f"ALTER TABLE product ADD COLUMN {name} {ddl}")
    return None


def _row(r):
    d = dict(r)
    d["in_stock"] = d["quantity"] > 0
    return d


def search_products(query="", category=None, color=None, max_price=None,
                    in_stock_only=False, limit=6):
    sql, params = "SELECT * FROM product WHERE 1=1", []
    tokens = [t for t in re.findall(r"\w+", (query or "").lower()) if t not in STOP]
    for t in tokens:
        sql += " AND (lower(name) LIKE ? OR lower(category) LIKE ? OR lower(color) LIKE ? OR lower(description) LIKE ?)"
        params += [f"%{t}%"] * 4
    if category:
        sql += " AND lower(category) LIKE ?"; params.append(f"%{category.lower()}%")
    if color:
        sql += " AND lower(color) LIKE ?"; params.append(f"%{color.lower()}%")
    if max_price is not None:
        sql += " AND price <= ?"; params.append(max_price)
    if in_stock_only:
        sql += " AND quantity > 0"
    sql += " ORDER BY quantity > 0 DESC, price LIMIT ?"; params.append(limit)
    with get_conn() as c:
        return [_row(r) for r in c.execute(sql, params)]


def get_product(product_id):
    with get_conn() as c:
        r = c.execute("SELECT * FROM product WHERE id = ?", (product_id,)).fetchone()
    return _row(r) if r else None


def get_similar(product_id, limit=4):
    """同類別、目前有庫存、價格最接近的商品。"""
    p = get_product(product_id)
    if not p:
        return []
    sql, params = "SELECT * FROM product WHERE id != ? AND quantity > 0", [product_id]
    if p["category"]:
        sql += " AND category = ?"; params.append(p["category"])
    sql += " ORDER BY ABS(price - ?) LIMIT ?"; params += [p["price"], limit]
    with get_conn() as c:
        return [_row(r) for r in c.execute(sql, params)]


def list_products():
    with get_conn() as c:
        return [_row(r) for r in c.execute("SELECT * FROM product ORDER BY category, name")]
