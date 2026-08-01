import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')

from battery_materials_agent.agent_team.agents.literature_researcher import (
    LiteratureResearcherAgent,
    LLMKnowledgeRetriever,
    SCPRetriever,
    SemanticScholarRetriever,
    CrossrefRetriever,
)
from battery_materials_agent.config import get_config

async def main():
    config = get_config()
    query = "solid electrolyte"
    limit = 3

    print("=== LLM ===")
    try:
        llm = LLMKnowledgeRetriever()
        papers = await llm.search(query, limit)
        print(f"count={len(papers)}")
        for p in papers:
            print(f"  {p.get('source')} {p.get('year')} {p.get('title', '')[:60]}")
    except Exception as e:
        print(f"error: {e}")

    print("\n=== SCP ===")
    try:
        from battery_materials_agent.agent import BatteryMaterialsAgent
        agent = BatteryMaterialsAgent(config)
        scp = SCPRetriever(agent.tools)
        papers = await scp.search(query, limit)
        print(f"count={len(papers)}")
        for p in papers:
            print(f"  {p.get('source')} {p.get('year')} {p.get('title', '')[:60]}")
    except Exception as e:
        print(f"error: {e}")

    print("\n=== Semantic Scholar ===")
    try:
        ss = SemanticScholarRetriever()
        papers = await ss.search(query, limit)
        print(f"count={len(papers)}")
        for p in papers:
            print(f"  {p.get('source')} {p.get('year')} {p.get('title', '')[:60]}")
    except Exception as e:
        print(f"error: {e}")

    print("\n=== Crossref ===")
    try:
        cr = CrossrefRetriever()
        papers = await cr.search(query, limit)
        print(f"count={len(papers)}")
        for p in papers:
            print(f"  {p.get('source')} {p.get('year')} {p.get('title', '')[:60]}")
    except Exception as e:
        print(f"error: {e}")

    print("\n=== Combined ===")
    try:
        agent = BatteryMaterialsAgent(config)
        researcher = LiteratureResearcherAgent(
            config=config,
            tool_registry=agent.tools,
            enable_llm=True,
            enable_scp=True,
            enable_web_api=True,
            enable_template_fallback=True,
        )
        papers = await researcher.search(query, limit)
        print(f"count={len(papers)}")
        for p in papers:
            print(f"  {p.get('source')} {p.get('year')} {p.get('title', '')[:60]}")
    except Exception as e:
        print(f"error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
