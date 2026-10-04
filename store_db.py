"""資料庫層：讀取商店的 store.db（資料表名稱 product 或 products 都可以）。
若你的商店已有資料庫（MySQL / PostgreSQL 等），只需改 get_conn() 與 SQL 欄位名稱。"""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3

DB_PATH = os.getenv("STORE_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "store.db"))
STOP = {"do", "you", "have", "in", "stock", "a", "the", "any", "got", "is", "are",
        "for", "me", "show", "i", "want", "need", "there", "some", "with", "and"}
WANTED = [("quantity", "INTEGER NOT NULL DEFAULT 0"), ("category", "VARCHAR(50)"),
          ("color", "VARCHAR(30)"), ("description", "VARCHAR(300)"), ("image", "BLOB")]
# 查詢給 AI 用的欄位（不含圖片，圖片是二進位資料，不能傳給 AI）
COLS = "id, name, price, quantity, category, color, description"


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
    with get_conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS shop_orders(id INTEGER PRIMARY KEY, "
                  "created_at TEXT, total REAL, items TEXT, username TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS shop_users(id INTEGER PRIMARY KEY, "
                  "username TEXT UNIQUE COLLATE NOCASE, password_hash TEXT, salt TEXT, created_at TEXT)")
        if "username" not in {r[1] for r in c.execute("PRAGMA table_info(shop_orders)")}:
            c.execute("ALTER TABLE shop_orders ADD COLUMN username TEXT")
    t = table_name()
    if not t:
        with get_conn() as c:
            c.execute("CREATE TABLE products(id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, "
                      "price FLOAT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0, "
                      "category VARCHAR(50), color VARCHAR(30), description VARCHAR(300), image BLOB)")
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
    sql, params = f"SELECT {COLS} FROM {table_name()} WHERE 1=1", []
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
        r = c.execute(f"SELECT {COLS} FROM {table_name()} WHERE id = ?", (product_id,)).fetchone()
    return _row(r) if r else None


def get_similar(product_id, limit=4):
    """同類別、目前有庫存、價格最接近的商品。"""
    p = get_product(product_id)
    if not p:
        return []
    sql, params = f"SELECT {COLS} FROM {table_name()} WHERE id != ? AND quantity > 0", [product_id]
    if p["category"]:
        sql += " AND category = ?"; params.append(p["category"])
    sql += " ORDER BY ABS(price - ?) LIMIT ?"; params += [p["price"], limit]
    with get_conn() as c:
        return [_row(r) for r in c.execute(sql, params)]


def list_products():
    with get_conn() as c:
        return [_row(r) for r in c.execute(f"SELECT {COLS}, image FROM {table_name()} ORDER BY category, name")]


def process_image(raw):
    """把上傳的圖片縮小、轉成 JPEG（最長邊 600px），回傳 bytes。失敗時丟出例外。"""
    import io
    from PIL import Image
    img = Image.open(io.BytesIO(raw))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    img.thumbnail((600, 600))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()


def add_product(name, price, quantity=0, category=None, color=None, description=None, image=None):
    with get_conn() as c:
        c.execute(f"INSERT INTO {table_name()}(name, price, quantity, category, color, description, image) "
                  "VALUES (?,?,?,?,?,?,?)",
                  (name.strip(), float(price), int(quantity),
                   (category or "").strip() or None, (color or "").strip() or None,
                   (description or "").strip() or None, image))


def import_products_csv(raw):
    """批次匯入 CSV（欄位：name,price,quantity,category,color,description）。
    名稱已存在的會略過。回傳 (新增數, 略過數, 錯誤清單)。"""
    import csv
    import io
    added, skipped, errors = 0, 0, []
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    for i, row in enumerate(reader, start=2):
        try:
            name = (row.get("name") or "").strip()
            if not name:
                raise ValueError("缺少 name")
            with get_conn() as c:
                exists = c.execute(f"SELECT 1 FROM {table_name()} WHERE lower(name) = lower(?)", (name,)).fetchone()
            if exists:
                skipped += 1
                continue
            add_product(name, float(row.get("price") or 0), int(float(row.get("quantity") or 0)),
                        row.get("category"), row.get("color"), row.get("description"))
            added += 1
        except Exception as e:
            errors.append(f"第 {i} 列：{e}")
    return added, skipped, errors


def set_image(product_id, image):
    """image 為 bytes 代表更換圖片，None 代表移除圖片。"""
    with get_conn() as c:
        c.execute(f"UPDATE {table_name()} SET image = ? WHERE id = ?", (image, product_id))


def update_product(product_id, quantity, price):
    with get_conn() as c:
        c.execute(f"UPDATE {table_name()} SET quantity = ?, price = ? WHERE id = ?",
                  (int(quantity), float(price), product_id))


def delete_product(product_id):
    with get_conn() as c:
        c.execute(f"DELETE FROM {table_name()} WHERE id = ?", (product_id,))


def checkout(cart, username=None):
    """cart: {商品id: 數量}。庫存夠才成立，成立後扣庫存並記錄訂單。回傳 (成功與否, 訊息)。"""
    if not cart:
        return False, "購物車是空的"
    t = table_name()
    conn = sqlite3.connect(DB_PATH, isolation_level=None)  # 手動控制交易
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        total, lines = 0.0, []
        for pid, qty in cart.items():
            r = conn.execute(f"SELECT name, price, quantity FROM {t} WHERE id = ?", (pid,)).fetchone()
            if not r:
                conn.execute("ROLLBACK")
                return False, "有商品已下架，請重新整理頁面"
            if r["quantity"] < qty:
                conn.execute("ROLLBACK")
                return False, f"{r['name']} 庫存不足（目前剩 {r['quantity']}）"
            total += r["price"] * qty
            lines.append(f"{r['name']} x{qty}")
        for pid, qty in cart.items():
            conn.execute(f"UPDATE {t} SET quantity = quantity - ? WHERE id = ?", (qty, pid))
        conn.execute("INSERT INTO shop_orders(created_at, total, items, username) "
                     "VALUES (datetime('now'), ?, ?, ?)", (total, "; ".join(lines), username))
        conn.execute("COMMIT")
        return True, f"訂單完成！合計 ${total:.2f}（{'、'.join(lines)}）"
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def list_orders(limit=30, username=None):
    sql, params = "SELECT * FROM shop_orders", []
    if username:
        sql += " WHERE username = ?"; params.append(username)
    sql += " ORDER BY id DESC LIMIT ?"; params.append(limit)
    with get_conn() as c:
        return [dict(r) for r in c.execute(sql, params)]


# ---------------- 顧客帳號 ----------------
def _hash(password, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                               bytes.fromhex(salt_hex), 200_000).hex()


def create_user(username, password):
    """建立顧客帳號。回傳 (成功與否, 訊息, 帳號名稱)。"""
    username = (username or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
        return False, "Username 需為 3 到 30 個英文字母、數字或底線", None
    if username.lower() == "admin":
        return False, "這個名稱已被保留，請換一個", None
    if len(password or "") < 6:
        return False, "密碼至少 6 個字元", None
    salt = secrets.token_hex(16)
    try:
        with get_conn() as c:
            c.execute("INSERT INTO shop_users(username, password_hash, salt, created_at) "
                      "VALUES (?,?,?, datetime('now'))", (username, _hash(password, salt), salt))
    except sqlite3.IntegrityError:
        return False, "這個 Username 已經有人使用", None
    return True, "帳號建立完成", username


def verify_user(username, password):
    """帳號密碼正確回傳帳號名稱，否則回傳 None。"""
    with get_conn() as c:
        r = c.execute("SELECT username, password_hash, salt FROM shop_users WHERE username = ?",
                      ((username or "").strip(),)).fetchone()
    if r and hmac.compare_digest(_hash(password or "", r["salt"]), r["password_hash"]):
        return r["username"]
    return None
