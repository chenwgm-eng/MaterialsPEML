import asyncio
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')

from battery_materials_agent.agent_team.agents.literature_researcher import LiteratureResearcherAgent
from battery_materials_agent.agent import BatteryMaterialsAgent
from battery_materials_agent.config import get_config

async def main():
    config = get_config()
    agent = BatteryMaterialsAgent(config)
    # 模拟 api.py startup 中的初始化
    researcher = LiteratureResearcherAgent(
        config=config,
        tool_registry=agent.tools,
        enable_llm=True,
        enable_scp=True,
        enable_web_api=True,
        enable_template_fallback=True,
    )
    query = "solid electrolyte"
    papers = await researcher.search(query, 3)
    print(f"count={len(papers)}")
    for p in papers:
        print(f"  source={p.get('source')} score={p.get('score')} year={p.get('year')} title={p.get('title', '')[:60]}")

if __name__ == "__main__":
    asyncio.run(main())
