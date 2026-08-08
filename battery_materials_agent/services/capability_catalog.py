"""科学服务能力目录 —— 将原生科学服务注册为可路由能力。

设计目标（CapabilityRouter 集成层，保持分层清晰）：
- 单一数据源：别名 / 描述直接从 ``get_service_registry()`` 派生，新增科学服务
  无需改动路由配置，天然可维护。
- 可配置：可通过环境变量 ``SCIENTIFIC_CAPABILITIES_ENABLED``（JSON 数组，如
  '["mpa","chem_properties"]'）控制哪些服务可路由；缺省全部可路由。
- 优雅分层：本模块只做"能力发现 / 注册"，不触碰科学服务执行内核
  （ScientificExecutionKernel / CPU Worker），避免与工具治理层混层。

能力约定：
- 语义 alias：``sci_<capability_id>``（如 ``sci_mpa``），与 Agent 业务 alias 区分。
- local binding：``sci:<capability_id>``，经 CapabilityRouter 解析为 ``local:sci:mpa``，
  供下游按 service_id 定位对应科学服务。
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

# 与 alias_registry / eligibility_store 保持一致的 profile 定义
_ALL_PROFILES = ["standard", "internlm_assisted", "committee_governed"]

# 科学服务能力语义前缀（避免与 MCP 工具 binding 混淆）
_ALIAS_PREFIX = "sci_"
_BINDING_PREFIX = "sci:"

# ToolRiskLevel(A=最高风险) → 允许该工具的最低 max_risk_level 门禁(A=最安全)。
# 由于 ToolRiskLevel 与 max_risk_level 的字母含义相反，需翻转映射：
#   ToolRiskLevel.X 的本地风险分 = _LOCAL_RISK_SCORE[X]，
#   门禁放行条件为 risk_score <= _MAX_RISK_SCORE[max_risk_level]，
#   因此取恰好放行自身风险、同时拦截更高风险候选的最小门禁 == 翻转映射。
# CA3：若不注册工具风险，路由层恒得最低风险 0.1，max_risk_level 过滤形同虚设。
_RISK_TO_MAX_RISK: dict[str, str] = {"A": "D", "B": "C", "C": "B", "D": "A"}


def enabled_scientific_ids() -> set[str] | None:
    """读取可路由科学服务开关；None 表示全部可路由，[] 表示全部禁用。"""
    raw = os.environ.get("SCIENTIFIC_CAPABILITIES_ENABLED", "").strip()
    if not raw:
        return None
    try:
        ids = json.loads(raw)
        return {str(i) for i in ids} if isinstance(ids, list) else None
    except (json.JSONDecodeError, TypeError):
        logger.warning("SCIENTIFIC_CAPABILITIES_ENABLED 非法 JSON，忽略并启用全部")
        return None


def scientific_alias(capability_id: str) -> str:
    return f"{_ALIAS_PREFIX}{capability_id}"


def scientific_binding(capability_id: str) -> str:
    return f"{_BINDING_PREFIX}{capability_id}"


def build_scientific_aliases(enabled: set[str] | None = None) -> list:
    """从服务注册表派生科学服务能力别名（单一数据源）。

    Args:
        enabled: 允许可路由的 capability_id 集合；None 表示全部，空集合表示全部禁用。

    Returns:
        list[InternalToolAlias]
    """
    from ..mcp_tools.alias_registry import InternalToolAlias
    from .registry import get_service_registry

    registry = get_service_registry()
    aliases: list = []
    for capability_id, svc in registry.items():
        if enabled is not None and capability_id not in enabled:
            continue
        aliases.append(
            InternalToolAlias(
                alias=scientific_alias(capability_id),
                category="scientific",
                description=svc.description,
                local_binding=scientific_binding(capability_id),
                allowed_profiles=list(_ALL_PROFILES),
                hard_requirement=True,
            )
        )
    return aliases


def seed_scientific_eligibility(
    store, enabled: set[str] | None = None
) -> list[str]:
    """为科学服务能力创建默认工具资格规则（idempotent）。

    ``max_risk_level`` 由服务自身的 ``risk_level`` 派生（单一数据源），使门禁
    恰好放行该服务固有风险、同时拦截更高风险候选 —— 路由层据此真正做风险过滤。

    Args:
        store: EligibilityStore 实例。
        enabled: 允许可路由的 capability_id 集合；None 表示全部。

    Returns:
        本次实际创建的 rule_id 列表。
    """
    from ..agent_team.models import ToolEligibilityRule
    from .registry import get_service_registry

    registry = get_service_registry()
    existing = {r.rule_id for r in store.list_all()}
    created: list[str] = []
    for capability_id, svc in registry.items():
        if enabled is not None and capability_id not in enabled:
            continue
        alias = scientific_alias(capability_id)
        rule_id = f"seed_sci_{capability_id}"
        if rule_id in existing:
            continue
        store.create(
            ToolEligibilityRule(
                rule_id=rule_id,
                agent_id="*",
                capability=alias,
                profiles=list(_ALL_PROFILES),
                preferred_binding_order=[f"local:{scientific_binding(capability_id)}"],
                max_risk_level=_RISK_TO_MAX_RISK.get(svc.risk_level.value, "B"),
                requires_provenance=True,
                fallback_action="local_fallback",
            )
        )
        created.append(rule_id)
    return created


def register_scientific_tools(
    tool_catalog, enabled: set[str] | None = None
) -> int:
    """将科学服务注册进 ToolCatalog，使路由层能读取真实风险等级（CA3 修复）。

    每个服务以 tool_id = ``sci:<capability_id>`` 注册为 local 工具，risk_level
    取自服务自身的 ``risk_level``（单一数据源）。只有注入 ToolCatalog 的路由器，
    ``_local_risk_score`` 才会返回真实风险分；否则恒为最低 0.1，
    导致 max_risk_level 风险门禁对科学服务形同虚设。

    Args:
        tool_catalog: ToolCatalog 实例。
        enabled: 允许可路由的 capability_id 集合；None 表示全部。

    Returns:
        注册的工具数量。
    """
    from ..control_plane.tool_catalog import ToolDescriptor
    from .registry import get_service_registry

    registry = get_service_registry()
    count = 0
    for capability_id, svc in registry.items():
        if enabled is not None and capability_id not in enabled:
            continue
        tool_catalog.register(
            ToolDescriptor(
                tool_id=scientific_binding(capability_id),
                source="local",
                owner="scientific",
                risk_level=svc.risk_level,
                allowed_roles=["admin", "pm", "researcher"],
                timeout_seconds=300,
                description=svc.description,
            )
        )
        count += 1
    logger.info("Scientific tools registered in ToolCatalog: %d", count)
    return count


def register_scientific_capabilities(alias_registry, eligibility_store) -> int:
    """将科学服务注册到路由层（别名 + 资格规则）。

    基于当前生效的开关（SCIENTIFIC_CAPABILITIES_ENABLED）决定可路由集合。

    Returns:
        注册的别名数量。
    """
    enabled = enabled_scientific_ids()
    aliases = build_scientific_aliases(enabled)
    for alias in aliases:
        alias_registry.register(alias)
    seed_scientific_eligibility(eligibility_store, enabled)
    logger.info(
        "Scientific capabilities registered: %d aliases (enabled=%s)",
        len(aliases),
        sorted(enabled) if enabled is not None else "all",
    )
    return len(aliases)