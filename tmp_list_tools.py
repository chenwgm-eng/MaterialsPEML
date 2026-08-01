import asyncio
from battery_materials_agent.agent import BatteryMaterialsAgent
from battery_materials_agent.config import get_config

async def main():
    config = get_config()
    agent = BatteryMaterialsAgent(config)
    tools = agent.tools.list_tools()
    for t in tools:
        print(f"{t.name} | source={t.source} | availability={t.availability}")

if __name__ == "__main__":
    asyncio.run(main())
