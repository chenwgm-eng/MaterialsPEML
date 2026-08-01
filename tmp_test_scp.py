import asyncio
import os
from battery_materials_agent.config import get_config
from battery_materials_agent.mcp_tools.scp_catalog import SCPCatalog
from battery_materials_agent.mcp_tools.scp_policy import SCPPolicy
from battery_materials_agent.mcp_tools.scp_client import SCPClientPool
from battery_materials_agent.mcp_tools.scp_adapters import (
    MoleculeDescriptorAdapter, ToxicityAssessmentAdapter, LiteratureSearchAdapter,
    ProtocolDraftAdapter, MaterialTransformAdapter,
)
from battery_materials_agent.mcp_tools.tools import MCPToolRegistry
from battery_materials_agent.integrations.audit_store import AuditStore
from battery_materials_agent.integrations import init_audit_db

async def main():
    config = get_config()
    print(f"SCP enabled: {config.scp.enabled}")
    print(f"SCP api_key present: {bool(config.scp.api_key and config.scp.api_key.get_secret_value())}")

    catalog = SCPCatalog()
    config.scp.apply_binding_overrides(catalog)
    print("\n=== catalog bindings ===")
    for b in catalog.list_enabled():
        print(f"  {b.internal_name} | server_id={b.server_id} | remote={b.remote_tool_name} | mapping={b.output_mapping}")

    policy = SCPPolicy(catalog)
    adapters = {
        "molecule_descriptor": MoleculeDescriptorAdapter(),
        "toxicity_assessment": ToxicityAssessmentAdapter(),
        "literature_search": LiteratureSearchAdapter(),
        "protocol_draft": ProtocolDraftAdapter(),
        "material_transform": MaterialTransformAdapter(),
    }
    init_audit_db()
    audit_store = AuditStore()

    if config.scp.enabled:
        pool = SCPClientPool(config.scp)
        registry = MCPToolRegistry()
        registry.register_scp_tools(catalog, pool, policy, adapters, audit_store)
        print("\n=== registered tools ===")
        for t in registry.list_tools():
            print(f"  {t.name} | source={t.source} | availability={t.availability}")
    else:
        print("SCP not enabled")

if __name__ == "__main__":
    asyncio.run(main())
