import asyncio
from battery_materials_agent.agent_team.agents.literature_researcher import TemplateLibraryRetriever

async def main():
    t = TemplateLibraryRetriever()
    papers = await t.search("solid electrolyte", 3)
    print(f"count={len(papers)}")
    for p in papers:
        print(f"  source={p.get('source')!r} score={p.get('score')} year={p.get('year')} title={p.get('title', '')[:60]}")

if __name__ == "__main__":
    asyncio.run(main())
