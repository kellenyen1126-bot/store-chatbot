    import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
try:  # Streamlit Cloud 部署時從 secrets 讀取
    if "XAI_API_KEY" in st.secrets:
        os.environ["XAI_API_KEY"] = st.secrets["XAI_API_KEY"]
except Exception:
    pass

import store_db, chatbot
from seed_db import seed

# 雲端上沒有資料庫時，自動建立示範資料
if not os.path.exists(store_db.DB_PATH):
    seed()

st.set_page_config(page_title="My Online Store", page_icon="🛍️", layout="wide")
st.title("🛍️ My Online Store")

shop, chat = st.columns([3, 2], gap="large")

with shop:
    st.subheader("商品")
    for p in store_db.list_products():
        with st.container(border=True):
            a, b = st.columns([3, 1])
            a.markdown(f"**{p['name']}**  \n{p['description']}")
            b.markdown(f"**${p['price']:.2f}**")
            b.caption("有現貨" if p["in_stock"] else "缺貨")

with chat:
    st.subheader("💬 AI 購物助理")
    if "history" not in st.session_state:
        st.session_state.history = []
    for m in st.session_state.history:
        st.chat_message(m["role"]).write(m["content"])
    if q := st.chat_input("問問商品、價格、庫存…"):
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

    

