"""Internal Tool Alias Registry — 业务语义工具名映射。"""
from __future__ import annotations

from pydantic import BaseModel, Field


_ALL_PROFILES = ["standard", "internlm_assisted", "committee_governed"]
_ASSISTED_PROFILES = ["internlm_assisted", "committee_governed"]
_COMMITTEE_PROFILES = ["committee_governed"]


class InternalToolAlias(BaseModel):
    """语义工具别名 — 将业务能力名映射到本地 MCP 或 SCP binding。"""

    alias: str
    category: str
    description: str = ""
    local_binding: str = ""              # 本地 MCP 工具名，如 generate_polymer_candidates
    scp_binding: str = ""                # SCP 绑定名，如 scp_scitool_chem
    fallback_binding: str = ""           # 回退 binding
    allowed_profiles: list[str] = Field(
        default_factory=lambda: ["standard", "internlm_assisted", "committee_governed"]
    )
    hard_requirement: bool = True        # 是否为硬需求（必须本地执行）
    scp_supplementary: bool = True       # SCP 是否为补充（不能覆盖本地）


class AliasRegistry:
    """语义工具别名注册表。"""

    def __init__(self):
        self._aliases: dict[str, InternalToolAlias] = {}
        self._init_default_aliases()

    def _init_default_aliases(self):
        """注册 11 个默认语义别名。"""
        defaults = [
            InternalToolAlias(
                alias="structure_validation",
                category="structure",
                description="晶体/分子结构合法性验证",
                local_binding="pymatgen_validate",
                scp_binding="",
                allowed_profiles=list(_ALL_PROFILES),
                hard_requirement=True,
            ),
            InternalToolAlias(
                alias="compliance_screening",
                category="compliance",
                description="合成可行性与合规性筛选",
                local_binding="check_synthesis_feasibility",
                scp_binding="scp_scitool_chem",
                allowed_profiles=list(_ALL_PROFILES),
                hard_requirement=True,
            ),
            InternalToolAlias(
                alias="property_prediction",
                category="prediction",
                description="材料物理性质预测",
                local_binding="predict_crystal_properties",
                scp_binding="scp_scitool_mat",
                allowed_profiles=list(_ALL_PROFILES),
                hard_requirement=True,
            ),
            InternalToolAlias(
                alias="dft_verification",
                category="dft",
                description="DFT 精确计算验证",
                local_binding="verify_dft",
                scp_binding="",
                allowed_profiles=list(_ALL_PROFILES),
                hard_requirement=True,
            ),
            InternalToolAlias(
                alias="experiment_qc_lookup",
                category="experiment",
                description="湿实验结果与 QC 数据查询",
                local_binding="get_experiment_results",
                scp_binding="",
                allowed_profiles=list(_ALL_PROFILES),
                hard_requirement=True,
            ),
            InternalToolAlias(
                alias="chemical_descriptors",
                category="chemical",
                description="分子描述符与聚合物候选生成",
                local_binding="generate_polymer_candidates",
                scp_binding="scp_scitool_chem",
                allowed_profiles=list(_ASSISTED_PROFILES),
                hard_requirement=False,
            ),
            InternalToolAlias(
                alias="compound_registry_lookup",
                category="registry",
                description="化合物注册信息检索（本地缓存 + SCP）",
                local_binding="",
                scp_binding="scp_origene_pubchem",
                allowed_profiles=list(_ASSISTED_PROFILES),
                hard_requirement=False,
            ),
            InternalToolAlias(
                alias="material_reference_lookup",
                category="reference",
                description="材料参考数据检索",
                local_binding="route_material",
                scp_binding="scp_scitool_mat",
                allowed_profiles=list(_ASSISTED_PROFILES),
                hard_requirement=False,
            ),
            InternalToolAlias(
                alias="material_knowledge_query",
                category="knowledge",
                description="材料/化学知识图谱查询",
                local_binding="",
                scp_binding="scp_scigraph_material",
                allowed_profiles=list(_ASSISTED_PROFILES),
                hard_requirement=False,
            ),
            InternalToolAlias(
                alias="reaction_engineering_check",
                category="reaction",
                description="反应工程与配方设计检查",
                local_binding="design_formula",
                scp_binding="scp_chem_reaction",
                allowed_profiles=list(_ASSISTED_PROFILES),
                hard_requirement=False,
            ),
            InternalToolAlias(
                alias="bioactivity_risk_lookup",
                category="bioactivity",
                description="生物活性与毒理风险检索",
                local_binding="",
                scp_binding="scp_origene_chembl",
                allowed_profiles=list(_COMMITTEE_PROFILES),
                hard_requirement=False,
            ),
            # ── 三期新增 SCP 工具的 alias 绑定（接入 Agent 路由层） ──
            InternalToolAlias(
                alias="deep_research",
                category="research",
                description="深度科研智能体（综述/调研/深度评估）",
                local_binding="",
                scp_binding="scp_intern_agent",
                allowed_profiles=list(_ASSISTED_PROFILES),
                hard_requirement=False,
            ),
            InternalToolAlias(
                alias="physical_unit_conversion",
                category="utility",
                description="物理量与单位换算",
                local_binding="",
                scp_binding="scp_unit_conversion",
                allowed_profiles=list(_ALL_PROFILES),
                hard_requirement=False,
            ),
            InternalToolAlias(
                alias="data_statistical_analysis",
                category="analysis",
                description="数据处理与统计分析",
                local_binding="",
                scp_binding="scp_data_analysis",
                allowed_profiles=list(_ASSISTED_PROFILES),
                hard_requirement=False,
            ),
            InternalToolAlias(
                alias="universal_knowledge_query",
                category="knowledge",
                description="通用科学知识图谱查询（跨学科）",
                local_binding="",
                scp_binding="scp_scigraph",
                allowed_profiles=list(_ASSISTED_PROFILES),
                hard_requirement=False,
            ),
            InternalToolAlias(
                alias="mechanics_fracture_analysis",
                category="mechanics",
                description="材料力学与断裂分析",
                local_binding="",
                scp_binding="scp_materials_mechanics",
                allowed_profiles=list(_ASSISTED_PROFILES),
                hard_requirement=False,
            ),
        ]
        for alias in defaults:
            self._aliases[alias.alias] = alias

    def get(self, alias: str) -> InternalToolAlias | None:
        return self._aliases.get(alias)

    def list_all(self) -> list[InternalToolAlias]:
        return list(self._aliases.values())

    def register(self, alias: InternalToolAlias):
        self._aliases[alias.alias] = alias

    def resolve(self, alias: str, profile: str) -> list[str]:
        """解析别名到候选 binding 列表（按优先级排序）。

        返回 binding 名称列表，格式为 'local:<tool>' 或 'scp:<binding>'。
        standard 策略只返回 local binding；
        internlm_assisted/committee_governed 返回 local + scp（如 allowed_profiles 允许）。
        """
        entry = self._aliases.get(alias)
        if entry is None:
            return []

        candidates: list[str] = []

        if entry.local_binding:
            candidates.append(f"local:{entry.local_binding}")

        if profile != "standard" and entry.scp_binding and profile in entry.allowed_profiles:
            candidates.append(f"scp:{entry.scp_binding}")

        return candidates
