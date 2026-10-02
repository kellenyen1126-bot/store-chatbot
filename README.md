# AI Store Chatbot
## 執行
pip install -r requirements.txt
python seed_db.py          # 只有在沒有真實商店資料庫時才需要
cp .env.example .env       # 填入 XAI_API_KEY
streamlit run app.py

## 接上你現有的商店
修改 store_db.py 的 get_conn() 與 SQL 欄位（products 表：id, name, category, color, price, quantity, description）。

## API Key 安全
- 金鑰只放 .env 或 .streamlit/secrets.toml，兩者都已在 .gitignore。
- Streamlit Cloud：在 App settings → Secrets 貼上 XAI_API_KEY="..."
- 若金鑰曾被 commit，請立刻到 xAI 後台作廢並重新產生。

## 部署：GitHub + Streamlit Community Cloud
1. 把整個資料夾推到 GitHub（.env 不會被上傳）。
2. 到 share.streamlit.io → New app → 選你的 repo、分支，Main file path 填 app.py。
3. Advanced settings → Secrets 貼上：XAI_API_KEY = "你的金鑰"
4. Deploy。
注意：示範用的 SQLite 在雲端重啟後會重置；正式商店請改接外部資料庫。
