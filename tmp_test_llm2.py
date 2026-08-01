import asyncio
import json
import os
import httpx

async def main():
    base_url = "https://api.longcat.chat/openai/v1"
    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "")
    query = "solid electrolyte"
    user_prompt = (
        f"研究主题：{query}\n\n"
        "请返回 3 篇与该主题最相关的学术文献，按相关度降序排列。"
        "每篇文献必须包含以下字段（JSON 数组）：\n"
        "[\n"
        "  {\n"
        '    "title": "文献标题（英文优先）",\n'
        '    "authors": ["作者1", "作者2"],\n'
        '    "journal": "期刊名称",\n'
        '    "year": 2020,\n'
        '    "abstract": "摘要，控制在 80-150 字",\n'
        '    "doi": "DOI，若无则留空字符串",\n'
        '    "keywords": ["关键词1", "关键词2"]\n'
        "  }\n"
        "]\n"
        "要求：\n"
        "1. 必须返回合法 JSON 数组，不要任何额外说明。\n"
        "2. 如果主题超出你的知识范围或你不确定，返回空数组 []。\n"
        "3. 年份必须是整数，作者必须是字符串数组。"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一位电池材料领域的资深文献调研员。请返回真实学术文献信息，不确定的不要编造。输出严格JSON数组。"},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 8192,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{base_url}/chat/completions", headers={"Authorization": f"Bearer {api_key}"}, json=payload)
    print("status:", resp.status_code)
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    print("=== content ===")
    print(content[:2000])
    # try parse
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
    try:
        papers = json.loads(text)
        print("=== parsed count ===", len(papers))
        for p in papers:
            print(" -", p.get("year"), p.get("title", "")[:80])
    except Exception as e:
        print("parse error:", e)

if __name__ == "__main__":
    asyncio.run(main())
