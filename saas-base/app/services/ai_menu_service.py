import json
import httpx
import logging
from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个餐厅菜单助手。用户会输入菜单文字（可能格式混乱），
你需要提取出菜品列表，返回 JSON 数组，每个元素包含：
- name: 菜品名称（字符串，必填）
- price: 价格（数字，单位元，必填，无法识别则填0）
- category: 分类（字符串，从文字中推断，默认"热销推荐"）
- description: 简介（字符串，从文字中提取，没有则填null）

只返回 JSON 数组，不要任何解释文字。示例：
[{"name":"红烧肉","price":28,"category":"热菜","description":null}]"""


async def _call_deepseek(messages: list, temperature: float = 0.7, max_tokens: int = 512) -> str:
    """通用 DeepSeek 调用，返回文本内容。"""
    if not settings.DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY 未配置")
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.DEEPSEEK_BASE_URL}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


async def generate_dish_description(name: str, price: float, category: str) -> str:
    """给菜品生成一句吸引人的卖点描述（20字以内）。"""
    messages = [
        {"role": "system", "content": (
            "你是餐厅菜品文案助手。根据菜品信息，写一句简短吸引人的卖点描述，"
            "要求：口语化、有食欲感、20字以内、不要感叹号结尾、不要用'本店'开头。"
            "只返回描述文字，不要任何解释。"
        )},
        {"role": "user", "content": f"菜名：{name}，价格：{price}元，分类：{category}"},
    ]
    return await _call_deepseek(messages, temperature=0.8, max_tokens=60)


async def parse_menu_text(text: str) -> list[dict]:
    """调用 DeepSeek 解析菜单文字，返回菜品列表。"""
    if not settings.DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY 未配置，请在服务器 .env 中添加")

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text.strip()},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    }
    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.DEEPSEEK_BASE_URL}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        body = resp.json()

    raw = body["choices"][0]["message"]["content"].strip()
    # 去掉可能的 markdown 代码块包裹
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    items = json.loads(raw)
    if not isinstance(items, list):
        raise ValueError("AI 返回格式错误")

    result = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        result.append({
            "name": name,
            "price": float(item.get("price") or 0),
            "category": str(item.get("category") or "热销推荐").strip(),
            "description": item.get("description") or None,
        })
    return result
