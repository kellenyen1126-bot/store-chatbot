"""資料庫層：讀取商店的 store.db（資料表名稱 product 或 products 都可以）。
若你的商店已有資料庫（MySQL / PostgreSQL 等），只需改 get_conn() 與 SQL 欄位名稱。"""
import os
import re
import sqlite3

DB_PATH = os.getenv("STORE_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "store.db"))
STOP = {"do", "you", "have", "in", "stock", "a", "the", "any", "got", "is", "are",
        "for", "me", "show", "i", "want", "need", "there", "some", "with", "and"}
WANTED = [("quantity", "INTEGER NOT NULL DEFAULT 0"), ("category", "VARCHAR(50)"),
          ("color", "VARCHAR(30)"), ("description", "VARCHAR(300)")]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_name():
    """自動判斷商品資料表叫 product 還是 products；都沒有就回傳 None。"""
    with get_conn() as c:
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("product", "products"):
        if t in names:
            return t
    return None


def ensure_schema():
    """檢查資料庫：沒有商品資料表就建立一個空的；缺少欄位就自動補上。"""
    t = table_name()
    if not t:
        with get_conn() as c:
            c.execute("CREATE TABLE products(id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, "
                      "price FLOAT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0, "
                      "category VARCHAR(50), color VARCHAR(30), description VARCHAR(300))")
        return None
    with get_conn() as c:
        cols = {r[1] for r in c.execute(f"PRAGMA table_info({t})")}
        for name, ddl in WANTED:
            if name not in cols:
                c.execute(f"ALTER TABLE {t} ADD COLUMN {name} {ddl}")
    return None


def _row(r):
    d = dict(r)
    d["in_stock"] = d["quantity"] > 0
    return d


def search_products(query="", category=None, color=None, max_price=None,
                    in_stock_only=False, limit=6):
    sql, params = f"SELECT * FROM {table_name()} WHERE 1=1", []
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
        r = c.execute(f"SELECT * FROM {table_name()} WHERE id = ?", (product_id,)).fetchone()
    return _row(r) if r else None


def get_similar(product_id, limit=4):
    """同類別、目前有庫存、價格最接近的商品。"""
    p = get_product(product_id)
    if not p:
        return []
    sql, params = f"SELECT * FROM {table_name()} WHERE id != ? AND quantity > 0", [product_id]
    if p["category"]:
        sql += " AND category = ?"; params.append(p["category"])
    sql += " ORDER BY ABS(price - ?) LIMIT ?"; params += [p["price"], limit]
    with get_conn() as c:
        return [_row(r) for r in c.execute(sql, params)]


def list_products():
    with get_conn() as c:
        return [_row(r) for r in c.execute(f"SELECT * FROM {table_name()} ORDER BY category, name")]


def add_product(name, price, quantity=0, category=None, color=None, description=None):
    with get_conn() as c:
        c.execute(f"INSERT INTO {table_name()}(name, price, quantity, category, color, description) "
                  "VALUES (?,?,?,?,?,?)",
                  (name.strip(), float(price), int(quantity),
                   (category or "").strip() or None, (color or "").strip() or None,
                   (description or "").strip() or None))


def update_product(product_id, quantity, price):
    with get_conn() as c:
        c.execute(f"UPDATE {table_name()} SET quantity = ?, price = ? WHERE id = ?",
                  (int(quantity), float(price), product_id))


def delete_product(product_id):
    with get_conn() as c:
        c.execute(f"DELETE FROM {table_name()} WHERE id = ?", (product_id,))
