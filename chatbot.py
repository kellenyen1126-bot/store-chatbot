"""AI 客服：Groq 上的模型透過 tool calling 查詢資料庫，再用真實資料回答。"""
import json
import os
from openai import OpenAI
import store_db

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
SYSTEM = (
    "You are a friendly shop assistant for an online store. "
    "ALWAYS call the tools to get product data; never guess or invent prices, stock or products. "
    "If the customer asks something broad (what do you sell, anything to buy, recommend something), "
    "call search_products with in_stock_only=true and list some items instead of asking a clarifying question. "
    "If a tool returns nothing, say the store does not carry it, and do not suggest or mention any item, "
    "category or product type that did not come from a tool result. "
    "Report real price and quantity. When asked for similar items, call get_similar_products "
    "and only suggest items that are in stock. Keep answers short. "
    "Reply in the same language as the customer's latest message (Traditional Chinese if they write Chinese); "
    "if the language is unclear, reply in English."
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
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("找不到 GROQ_API_KEY（請放在 .env 或 .streamlit/secrets.toml）")
    return OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")


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
