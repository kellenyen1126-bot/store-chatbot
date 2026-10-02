"""資料庫層：所有商品資料都從這裡讀取。
若你的商店已有資料庫（MySQL / PostgreSQL 等），只需改 get_conn() 與 SQL 欄位名稱。"""
import os
import re
import sqlite3

DB_PATH = os.getenv("STORE_DB_PATH", "store.db")
STOP = {"do", "you", "have", "in", "stock", "a", "the", "any", "got", "is", "are",
        "for", "me", "show", "i", "want", "need", "there", "some", "with", "and"}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _row(r):
    d = dict(r)
    d["in_stock"] = d["quantity"] > 0
    return d


def search_products(query="", category=None, color=None, max_price=None,
                    in_stock_only=False, limit=6):
    sql, params = "SELECT * FROM products WHERE 1=1", []
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
        r = c.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return _row(r) if r else None


def get_similar(product_id, limit=4):
    """同類別、目前有庫存、價格最接近的商品。"""
    p = get_product(product_id)
    if not p:
        return []
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM products WHERE category = ? AND id != ? AND quantity > 0 "
            "ORDER BY ABS(price - ?) LIMIT ?", (p["category"], product_id, p["price"], limit))
        return [_row(r) for r in rows]


def list_products():
    with get_conn() as c:
        return [_row(r) for r in c.execute("SELECT * FROM products ORDER BY category, name")]
