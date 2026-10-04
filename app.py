import hmac
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
try:  # Streamlit Cloud 部署時從 secrets 讀取
    for k in ("GROQ_API_KEY", "GROQ_MODEL", "ADMIN_PASSWORD"):
        if k in st.secrets:
            os.environ[k] = st.secrets[k]
except Exception:
    pass

import store_db, chatbot

st.set_page_config(page_title="My Online Store", page_icon="🛍️", layout="wide")
st.title("🛍️ My Online Store")

problem = store_db.ensure_schema()
if problem:
    st.error(problem)
    st.stop()


# ---------- 購物車（按鈕的 callback，會在畫面重畫前先執行） ----------
def add_to_cart(pid, stock):
    cart = st.session_state.setdefault("cart", {})
    if cart.get(pid, 0) < stock:
        cart[pid] = cart.get(pid, 0) + 1


def remove_from_cart(pid):
    st.session_state.get("cart", {}).pop(pid, None)


def do_checkout():
    ok, msg = store_db.checkout(st.session_state.get("cart", {}))
    st.session_state.notice = (ok, msg)
    if ok:
        st.session_state.cart = {}


# ---------- 管理員登入（側邊欄） ----------
admin_pw = os.getenv("ADMIN_PASSWORD")
is_admin = False
with st.sidebar:
    st.header("🔐 管理員")
    if not admin_pw:
        st.caption("尚未設定 ADMIN_PASSWORD，管理功能已關閉。")
    else:
        pw = st.text_input("密碼", type="password")
        is_admin = bool(pw) and hmac.compare_digest(pw, admin_pw)
        if pw and not is_admin:
            st.error("密碼錯誤")
    if is_admin:
        st.success("已登入")
        with open(store_db.DB_PATH, "rb") as f:
            st.download_button("⬇️ 下載 store.db 備份", f.read(), file_name="store.db")
        st.caption("雲端重啟後新增的商品與訂單會消失。請下載備份，再上傳到 GitHub 覆蓋舊的 store.db。")
        with st.expander("📦 訂單紀錄"):
            orders = store_db.list_orders()
            if not orders:
                st.caption("還沒有訂單")
            for o in orders:
                st.write(f"#{o['id']}　{o['created_at']}　${o['total']:.2f}")
                st.caption(o["items"])

shop, chat = st.columns([3, 2], gap="large")

with shop:
    st.subheader("商品")

    if is_admin:
        with st.expander("➕ 新增商品"):
            with st.form("add_product", clear_on_submit=True):
                name = st.text_input("名稱（英文）")
                c1, c2 = st.columns(2)
                price = c1.number_input("價格", min_value=0.0, step=0.5)
                qty = c2.number_input("庫存數量", min_value=0, step=1)
                category = c1.text_input("類別（英文，如 shoes）")
                color = c2.text_input("顏色（英文，如 black）")
                desc = st.text_input("說明（英文一句話）")
                if st.form_submit_button("新增"):
                    if not name.strip():
                        st.error("請輸入商品名稱")
                    else:
                        store_db.add_product(name, price, qty, category, color, desc)
                        st.success(f"已新增：{name}")

    products = store_db.list_products()
    by_id = {p["id"]: p for p in products}

    if "notice" in st.session_state:
        ok, msg = st.session_state.pop("notice")
        (st.success if ok else st.error)(msg)

    # 購物車
    lines = []
    for pid, n in st.session_state.get("cart", {}).items():
        p = by_id.get(pid)
        if p and p["quantity"] > 0:
            lines.append((p, min(n, p["quantity"])))
    if lines:
        with st.container(border=True):
            st.markdown("**🛒 購物車**")
            total = 0.0
            for p, n in lines:
                c1, c2, c3 = st.columns([5, 2, 1])
                c1.write(f"{p['name']} × {n}")
                c2.write(f"${p['price'] * n:.2f}")
                c3.button("✕", key=f"rm{p['id']}", on_click=remove_from_cart, args=(p["id"],))
                total += p["price"] * n
            st.markdown(f"**合計：${total:.2f}**")
            st.button("結帳", type="primary", on_click=do_checkout)

    # 商品列表
    if not products:
        st.info("目前沒有商品。" + ("請用上方「新增商品」加入。" if is_admin else ""))
    for p in products:
        with st.container(border=True):
            a, b = st.columns([5, 2])
            a.markdown(f"**{p['name']}**  \n{p['description'] or ''}")
            b.markdown(f"**${p['price']:.2f}**")
            b.caption(f"有現貨（{p['quantity']}）" if p["in_stock"] else "缺貨")
            b.button("加入購物車", key=f"add{p['id']}", disabled=not p["in_stock"],
                     on_click=add_to_cart, args=(p["id"], p["quantity"]))
            if is_admin:
                with st.expander("編輯 / 刪除"):
                    nq = st.number_input("庫存", min_value=0, value=int(p["quantity"]), key=f"q{p['id']}")
                    npr = st.number_input("價格", min_value=0.0, value=float(p["price"]),
                                          step=0.5, key=f"p{p['id']}")
                    e1, e2 = st.columns(2)
                    if e1.button("儲存", key=f"s{p['id']}"):
                        store_db.update_product(p["id"], nq, npr)
                        st.rerun()
                    if e2.button("刪除", key=f"d{p['id']}"):
                        store_db.delete_product(p["id"])
                        st.rerun()

# 輸入框必須放在欄位外面，才會固定在整個頁面最下方
q = st.chat_input("問問商品、價格、庫存…")

with chat:
    st.subheader("💬 AI 購物助理")
    if "history" not in st.session_state:
        st.session_state.history = []
    for m in st.session_state.history:
        st.chat_message(m["role"]).write(m["content"])
    if q:
        st.session_state.history.append({"role": "user", "content": q})
        st.chat_message("user").write(q)
        with st.chat_message("assistant"):
            with st.spinner("查詢中…"):
                try:
                    reply = chatbot.answer(st.session_state.history[-10:])
                except Exception as e:
                    reply = f"發生錯誤：{e}"
            st.write(reply)
        st.session_state.history.append({"role": "assistant", "content": reply})
