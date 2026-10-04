import hmac
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
try:  # On Streamlit Cloud, read settings from Secrets
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


# ---------- Cart (button callbacks run before the page redraws) ----------
def _to_int(v, default, lo, hi):
    """Read a number typed into a text box; fall back to default and keep it within lo..hi."""
    try:
        n = int(str(v).strip())
    except ValueError:
        n = default
    return max(lo, min(hi, n))


def add_to_cart(pid, stock):
    """Add the quantity chosen on the product card (never more than the stock)."""
    cart = st.session_state.setdefault("cart", {})
    n = _to_int(st.session_state.get(f"qty{pid}"), 1, 1, stock)
    cart[pid] = min(cart.get(pid, 0) + n, stock)


def step_qty(key, delta, hi):
    """The - / + buttons next to the quantity box on a product card."""
    n = _to_int(st.session_state.get(key), 1, 1, hi)
    st.session_state[key] = str(max(1, min(hi, n + delta)))


def step_cart(pid, delta, stock):
    """The - / + buttons next to the quantity box in the cart."""
    cart = st.session_state.setdefault("cart", {})
    cart[pid] = max(1, min(stock, cart.get(pid, 1) + delta))
    st.session_state[f"cq{pid}"] = str(cart[pid])


def set_cart_qty(pid, stock):
    """Called when the customer types a new quantity in the cart."""
    cart = st.session_state.setdefault("cart", {})
    cart[pid] = _to_int(st.session_state.get(f"cq{pid}"), cart.get(pid, 1), 1, stock)


def remove_from_cart(pid):
    st.session_state.get("cart", {}).pop(pid, None)
    st.session_state.pop(f"cq{pid}", None)


def do_checkout():
    user = st.session_state.get("user")
    if not user:
        st.session_state.notice = (False, "Please log in (Account, left side) before checking out")
        return
    ok, msg = store_db.checkout(st.session_state.get("cart", {}), user["name"])
    st.session_state.notice = (ok, msg)
    if ok:
        st.session_state.cart = {}


def load_image(uploaded):
    """Turn an uploaded file into image bytes for the database. Returns (bytes or None, error or None)."""
    if uploaded is None:
        return None, None
    if uploaded.size > 5 * 1024 * 1024:
        return None, "Image is too large. Please choose a file under 5MB"
    try:
        return store_db.process_image(uploaded.getvalue()), None
    except Exception:
        return None, "This file could not be read as an image. Please try another one"


# ---------- Account (sidebar) ----------
ss = st.session_state
ss.setdefault("user", None)          # {"name": ..., "admin": bool}
ss.setdefault("auth_view", "login")  # "login" or "register"
admin_pw = os.getenv("ADMIN_PASSWORD")

with st.sidebar:
    st.header("Account")
    if ss.user:
        st.success(f"Logged in as {ss.user['name']}" + (" (admin)" if ss.user["admin"] else ""))
        if st.button("Log Out"):
            ss.user = None
            ss.cart = {}
            st.rerun()
    elif ss.auth_view == "login":
        st.subheader("Log In")
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            do_login = st.form_submit_button("Log In")
            go_register = st.form_submit_button("Create a customer account")
        if go_register:
            ss.auth_view = "register"
            st.rerun()
        if do_login:
            if u.strip().lower() == "admin" and admin_pw and hmac.compare_digest(p, admin_pw):
                ss.user = {"name": "admin", "admin": True}
                st.rerun()
            name = None if u.strip().lower() == "admin" else store_db.verify_user(u, p)
            if name:
                ss.user = {"name": name, "admin": False}
                st.rerun()
            st.error("Incorrect username or password")
    else:
        st.subheader("Create a customer account")
        with st.form("register_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            p2 = st.text_input("Confirm password", type="password")
            do_create = st.form_submit_button("Create account")
            go_login = st.form_submit_button("Back to Log In")
        if go_login:
            ss.auth_view = "login"
            st.rerun()
        if do_create:
            if p != p2:
                st.error("Passwords do not match")
            else:
                ok, msg, name = store_db.create_user(u, p)
                if ok:
                    ss.user = {"name": name, "admin": False}
                    ss.auth_view = "login"
                    st.rerun()
                st.error(msg)

    is_admin = bool(ss.user and ss.user["admin"])
    if is_admin:
        with open(store_db.DB_PATH, "rb") as f:
            st.download_button("⬇️ Download store.db backup", f.read(), file_name="store.db")
        st.caption("Products, accounts and orders added in the app are lost when the cloud app restarts. Download a backup and upload it to GitHub to replace the old store.db.")
        with st.expander("📦 All orders"):
            orders = store_db.list_orders()
            if not orders:
                st.caption("No orders yet")
            for o in orders:
                st.write(f"#{o['id']}  |  {o['username'] or '-'}  |  {o['created_at']}  |  ${o['total']:.2f}")
                st.caption(o["items"])
    elif ss.user:
        with st.expander("📦 My orders"):
            mine = store_db.list_orders(username=ss.user["name"])
            if not mine:
                st.caption("No orders yet")
            for o in mine:
                st.write(f"#{o['id']}  |  {o['created_at']}  |  ${o['total']:.2f}")
                st.caption(o["items"])

shop, chat = st.columns([3, 2], gap="large")

with shop:
    st.subheader("Products")

    if is_admin:
        with st.expander("➕ Add product"):
            with st.form("add_product", clear_on_submit=True):
                name = st.text_input("Name")
                c1, c2 = st.columns(2)
                price = c1.number_input("Price", min_value=0.0, step=0.5)
                qty = c2.number_input("Stock quantity", min_value=0, step=1)
                category = c1.text_input("Category (e.g. pen)")
                color = c2.text_input("Color (e.g. black)")
                desc = st.text_input("Description (one short sentence)")
                photo = st.file_uploader("Product image (optional)", type=["png", "jpg", "jpeg", "webp"])
                if st.form_submit_button("Add"):
                    if not name.strip():
                        st.error("Please enter a product name")
                    else:
                        img, err = load_image(photo)
                        if err:
                            st.error(err)
                        else:
                            store_db.add_product(name, price, qty, category, color, desc, img)
                            st.success(f"Added: {name}")

    if is_admin:
        with st.expander("📥 Bulk import products (paste CSV text)"):
            st.caption("First line is the header: name,price,quantity,category,color,description. Products whose name already exists are skipped.")
            csv_text = st.text_area("Paste CSV text", height=200, key="csv_text")
            if st.button("Start import"):
                if not csv_text.strip():
                    st.error("Please paste the CSV text first")
                else:
                    try:
                        n_add, n_skip, errs = store_db.import_products_csv(csv_text.encode("utf-8"))
                        st.success(f"Added {n_add}, skipped {n_skip} (duplicate names)")
                        for e in errs:
                            st.error(e)
                    except Exception:
                        st.error("Could not read this text. Please check the format")

    products = store_db.list_products()
    by_id = {p["id"]: p for p in products}

    if "notice" in st.session_state:
        ok, msg = st.session_state.pop("notice")
        (st.success if ok else st.error)(msg)

    # Cart
    lines = []
    for pid, n in st.session_state.get("cart", {}).items():
        p = by_id.get(pid)
        if p and p["quantity"] > 0:
            lines.append((p, min(n, p["quantity"])))
    if lines:
        with st.container(border=True):
            st.markdown("**🛒 Cart**")
            total = 0.0
            for p, n in lines:
                st.session_state[f"cq{p['id']}"] = str(n)  # keep the box in sync with the cart
                c1, cm, cb, cp, c3, c4 = st.columns([4, 1, 1.6, 1, 2, 1])
                c1.write(f"{p['name']}  \n${p['price']:.2f} each")
                cm.button("−", key=f"cm{p['id']}", on_click=step_cart, args=(p["id"], -1, p["quantity"]))
                cb.text_input("Quantity", key=f"cq{p['id']}", label_visibility="collapsed",
                              on_change=set_cart_qty, args=(p["id"], p["quantity"]))
                cp.button("+", key=f"cp{p['id']}", on_click=step_cart, args=(p["id"], 1, p["quantity"]))
                c3.write(f"${p['price'] * n:.2f}")
                c4.button("✕", key=f"rm{p['id']}", on_click=remove_from_cart, args=(p["id"],))
                total += p["price"] * n
            st.markdown(f"**Total: ${total:.2f}**")
            if not ss.user:
                st.caption("Please log in (Account, left side) before checking out")
            st.button("Checkout", type="primary", on_click=do_checkout)

    # Product list
    if not products:
        st.info("No products yet." + (" Use \"Add product\" above to create some." if is_admin else ""))
    for p in products:
        with st.container(border=True):
            im, a, b = st.columns([2, 4, 2])
            if p["image"]:
                im.image(p["image"], width=110)
            else:
                im.markdown("<div style='font-size:48px;text-align:center'>✏️</div>", unsafe_allow_html=True)
            a.markdown(f"**{p['name']}**  \n{p['description'] or ''}")
            b.markdown(f"**${p['price']:.2f}**")
            b.caption(f"In stock ({p['quantity']})" if p["in_stock"] else "Out of stock")
            if p["in_stock"]:
                qkey = f"qty{p['id']}"
                maxq = int(p["quantity"])
                st.session_state[qkey] = str(_to_int(st.session_state.get(qkey), 1, 1, maxq))
                cm, cb, cp, ca, _sp = st.columns([1, 1.5, 1, 3, 2])
                cm.button("−", key=f"m{p['id']}", on_click=step_qty, args=(qkey, -1, maxq))
                cb.text_input("Qty", key=qkey, label_visibility="collapsed")
                cp.button("+", key=f"p{p['id']}b", on_click=step_qty, args=(qkey, 1, maxq))
                ca.button("Add to cart", key=f"add{p['id']}", on_click=add_to_cart, args=(p["id"], maxq))
            else:
                st.button("Add to cart", key=f"add{p['id']}", disabled=True)
            if is_admin:
                with st.expander("Edit / Delete"):
                    nq = st.number_input("Stock", min_value=0, value=int(p["quantity"]), key=f"q{p['id']}")
                    npr = st.number_input("Price", min_value=0.0, value=float(p["price"]),
                                          step=0.5, key=f"p{p['id']}")
                    newpic = st.file_uploader("Replace image", type=["png", "jpg", "jpeg", "webp"], key=f"img{p['id']}")
                    rmpic = st.checkbox("Remove image", key=f"rmimg{p['id']}") if p["image"] else False
                    e1, e2 = st.columns(2)
                    if e1.button("Save", key=f"s{p['id']}"):
                        img, err = load_image(newpic)
                        if err:
                            st.error(err)
                        else:
                            store_db.update_product(p["id"], nq, npr)
                            if img:
                                store_db.set_image(p["id"], img)
                            elif rmpic:
                                store_db.set_image(p["id"], None)
                            st.rerun()
                    if e2.button("Delete", key=f"d{p['id']}"):
                        store_db.delete_product(p["id"])
                        st.rerun()

# The chat input must sit outside the columns so it stays pinned to the bottom of the page
q = st.chat_input("Ask about products, prices, stock…")

with chat:
    st.subheader("💬 AI Shopping Assistant")
    if "history" not in st.session_state:
        st.session_state.history = []
    for m in st.session_state.history:
        st.chat_message(m["role"]).write(m["content"])
    if q:
        st.session_state.history.append({"role": "user", "content": q})
        st.chat_message("user").write(q)
        with st.chat_message("assistant"):
            with st.spinner("Looking it up…"):
                try:
                    reply = chatbot.answer(st.session_state.history[-10:])
                except Exception as e:
                    reply = f"Something went wrong: {e}"
            st.write(reply)
        st.session_state.history.append({"role": "assistant", "content": reply})
