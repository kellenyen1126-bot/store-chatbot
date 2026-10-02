    """AI 客服：Grok 透過 tool calling 查詢資料庫，再用真實資料回答。"""
import json
import os
from openai import OpenAI
import store_db

MODEL = os.getenv("XAI_MODEL", "grok-3-mini")
SYSTEM = (
    "You are a friendly shop assistant for an online store. "
    "ALWAYS call the tools to get product data; never guess or invent prices, stock or products. "
    "If a tool returns nothing, say the store does not carry it. "
    "Report real price and quantity. When asked for similar items, call get_similar_products "
    "and only suggest items that are in stock. Keep answers short. "
    "Reply in the customer's language."
)
TOOLS = [
    {"type": "function", "function": {
        "name": "search_products",
        "description": "Search products by keywords, category, color, max price.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "keywords, e.g. 'shoes'"},
            "category": {"type": "string"}, "color": {"type": "string"},
            "max_price": {"type": "number"}, "in_stock_only": {"type": "boolean"}}}}},
    {"type": "function", "function": {
        "name": "get_similar_products",
        "description": "Get in-stock products similar to a product id.",
        "parameters": {"type": "object", "properties": {"product_id": {"type": "integer"}},
                       "required": ["product_id"]}}},
]


def _client():
    key = os.getenv("XAI_API_KEY")
    if not key:
        raise RuntimeError("找不到 XAI_API_KEY（請放在 .env 或 .streamlit/secrets.toml）")
    return OpenAI(api_key=key, base_url="https://api.x.ai/v1")


def _run_tool(name, args):
    if name == "search_products":
        return store_db.search_products(**args)
    if name == "get_similar_products":
        return store_db.get_similar(**args)
    return {"error": "unknown tool"}


def answer(history):
    """history: [{'role','content'}, ...]，回傳 AI 回覆文字。"""
    client = _client()
    msgs = [{"role": "system", "content": SYSTEM}] + history
    for _ in range(4):  # 最多 4 輪工具呼叫
        resp = client.chat.completions.create(model=MODEL, messages=msgs, tools=TOOLS)
        m = resp.choices[0].message
        if not m.tool_calls:
            return m.content
        msgs.append(m)
        for tc in m.tool_calls:
            result = _run_tool(tc.function.name, json.loads(tc.function.arguments or "{}"))
            msgs.append({"role": "tool", "tool_call_id": tc.id,
                         "content": json.dumps(result, ensure_ascii=False)})
    return "抱歉，我暫時無法完成查詢，請再試一次。"

    
