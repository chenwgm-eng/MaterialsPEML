import sys
sys.path.insert(0, r'd:\BattleFish\BatteryEMCL Lab')

from battery_materials_agent.db import get_engine
from battery_materials_agent.mdm.reference_dict import ReferenceDictStore
from battery_materials_agent.agent_team.registry import AgentRegistry
from battery_materials_agent.agent_team.models import AgentRole

engine = get_engine()
store = ReferenceDictStore()
print('engine id:', id(engine))
print('store engine id:', id(store.engine))

# 1. 直接查 dimension
dim = store.get_dimension(domain='agent_role', code='material_discovery')
print('get_dimension material_discovery:', dim)

# 2. 列出所有 agent_role dimensions
items = store.list_dimensions(domain='agent_role')
print('agent_role dimensions count:', len(items))
for i in items:
    print(' -', i.code, i.label, i.is_active)

# 3. 用 registry 校验
reg = AgentRegistry()
print('registry engine id:', id(reg.engine))
print('registry ref_dict engine id:', id(reg._ref_dict.engine))
role = AgentRole.MATERIAL_DISCOVERY
print('role str:', repr(str(role)), 'type:', type(str(role)))
print('role repr:', repr(role))
print('code param:', repr(str(role)))
print('lookup direct:', store.get_dimension(domain='agent_role', code=str(role)))
try:
    reg._validate_role(role)
    print('_validate_role OK')
except Exception as e:
    print('_validate_role FAILED:', e)
