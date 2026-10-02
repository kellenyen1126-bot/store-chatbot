"""建立示範資料庫（只在沒有真實商店資料庫時使用）。執行：python seed_db.py"""
import sqlite3
from store_db import DB_PATH

DATA = [
    ("Classic Leather Shoes", "shoes", "black", 79.90, 12, "Formal black leather shoes"),
    ("Urban Runner Sneakers", "shoes", "black", 59.00, 0, "Lightweight black running sneakers"),
    ("Street Canvas Sneakers", "shoes", "white", 45.50, 25, "White canvas everyday sneakers"),
    ("Trail Hiking Boots", "shoes", "brown", 99.00, 4, "Waterproof hiking boots"),
    ("Slip-on Loafers", "shoes", "black", 65.00, 7, "Comfortable black casual loafers"),
    ("Cotton T-Shirt", "clothing", "white", 15.00, 80, "Soft 100% cotton tee"),
    ("Denim Jacket", "clothing", "blue", 69.00, 3, "Classic blue denim jacket"),
    ("Everyday Backpack", "bags", "black", 39.00, 18, "Water-resistant 20L backpack"),
    ("Leather Wallet", "accessories", "brown", 25.00, 0, "Slim brown leather wallet"),
]


def seed():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    DROP TABLE IF EXISTS products;
    CREATE TABLE products(id INTEGER PRIMARY KEY, name TEXT, category TEXT, color TEXT,
                          price REAL, quantity INTEGER, description TEXT);""")
    conn.executemany(
        "INSERT INTO products(name,category,color,price,quantity,description) VALUES (?,?,?,?,?,?)",
        DATA)
    conn.commit()
    print(f"已建立 {DB_PATH}，共 {len(DATA)} 件商品")


if __name__ == "__main__":
    seed()
