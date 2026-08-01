"""Tool Catalog — registry of tool descriptors with risk levels, health, and access control."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ToolRiskLevel(str, Enum):
    """Risk levels for tools (A = highest, D = lowest)."""

    A = "A"  # highest risk, e.g. DFT submission
    B = "B"  # high risk, e.g. SCP remote calls
    C = "C"  # medium risk, e.g. pymatgen local computation
    D = "D"  # low risk, e.g. local lookup / LLM generation


class ToolHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


ToolSource = Literal["local", "mcp", "scp", "database", "human"]


# 评测修复 P1-001：默认降级回退链。
# 主工具失败/不可用时，自动降级到更便宜/更安全的替代工具。
# 映射 value 必须是目录中已注册的 tool_id，未注册的目标会被跳过。
DEFAULT_FALLBACK_MAP: dict[str, str] = {
    # A 级：远程 DFT 提交 → 本地 ASE/PySCF 近似验证
    "dft_vasp": "verify_dft",
    # 本地 DFT 验证 → M3GNet 通用势弛豫近似
    "verify_dft": "m3gnet_relax",
    # M3GNet 弛豫 → pymatgen 基础结构校验
    "m3gnet_relax": "pymatgen_validate",
    # pymatgen 校验 → SCP 描述符计算兜底
    "pymatgen_validate": "scp_molecule_descriptors",
    # 晶体性质预测（CGCNN 等）→ M3GNet 近似
    "predict_crystal_properties": "m3gnet_relax",
    # 聚合物性质预测 → 描述符估算
    "predict_polymer_properties": "scp_molecule_descriptors",
    # 合成可行性（ASKCOS）→ 文献检索兜底
    "check_synthesis_feasibility": "scp_literature_search",
    # 晶体候选生成（MP/GNoME）→ LLM 生成兜底
    "generate_crystal_candidates": "internlm_generate",
    # 聚合物候选生成 → 文献检索兜底
    "generate_polymer_candidates": "scp_literature_search",
    # LLM 文本生成 → SCP 深度研究 agent
    "internlm_generate": "scp_intern_agent",
    # 材料路由 → LLM 分类兜底
    "route_material": "internlm_generate",
    # 实验结果查询 → SCP 数据分析兜底
    "get_experiment_results": "scp_data_analysis",
    # 实验订阅推送 → 轮询查询兜底
    "subscribe_experiment_updates": "get_experiment_results",
    # 工业化配方设计 → SCP 数据分析兜底
    "design_formula": "scp_data_analysis",
    # ChEMBL 活性数据查询 → PubChem 同族数据库兜底
    "scp_origene_chembl": "scp_origene_pubchem",
}


class ToolDescriptor(BaseModel):
    tool_id: str
    source: ToolSource
    owner: str = ""
    risk_level: ToolRiskLevel = ToolRiskLevel.D
    input_schema_ref: str = ""
    output_schema_ref: str = ""
    allowed_roles: list[str] = Field(default_factory=list)
    allowed_agents: list[str] = Field(default_factory=list)
    allowed_ecml_steps: list[int] = Field(default_factory=list)
    timeout_seconds: int = 60
    max_concurrency: int = 1
    retry_policy: dict = Field(default_factory=dict)
    idempotency_required: bool = False
    fallback_tool_id: str | None = None
    health_status: ToolHealthStatus = ToolHealthStatus.UNKNOWN
    version: str = "v1"
    description: str = ""


class ToolCatalog:
    """Registry of tool descriptors with access-control and health tracking."""

    def __init__(self):
        self._tools: dict[str, ToolDescriptor] = {}
        self._register_standard_tools()

    def _register_standard_tools(self) -> None:
        standard = [
            ToolDescriptor(
                tool_id="internlm_generate",
                source="mcp",
                owner="llm",
                risk_level=ToolRiskLevel.D,
                allowed_roles=["admin", "pm", "researcher"],
                timeout_seconds=90,
                retry_policy={"max": 2, "backoff": 1.0},
                description="InternLM text generation via MCP",
            ),
            ToolDescriptor(
                tool_id="pymatgen_validate",
                source="local",
                owner="materials",
                risk_level=ToolRiskLevel.C,
                allowed_roles=["admin", "pm", "researcher", "viewer"],
                timeout_seconds=30,
                description="Validate crystal/molecule structure with pymatgen",
            ),
            ToolDescriptor(
                tool_id="m3gnet_relax",
                source="local",
                owner="materials",
                risk_level=ToolRiskLevel.C,
                allowed_roles=["admin", "pm", "researcher"],
                timeout_seconds=60,
                description="Relax structure with M3GNet universal potential",
            ),
            ToolDescriptor(
                tool_id="dft_vasp",
                source="scp",
                owner="verification",
                risk_level=ToolRiskLevel.A,
                allowed_roles=["admin", "pm"],
                timeout_seconds=300,
                idempotency_required=True,
                description="Submit DFT calculation job via SCP",
            ),
        ]
        for desc in standard:
            self._tools[desc.tool_id] = desc

        # SCP tool family (scp_*) — risk B, broad researcher access.
        # allowed_ecml_steps 与 ECML 7 步对齐：1=路由 2=候选生成 3=合成/工业化
        # 4=性质预测 5=DFT 验证 6=实验分析 7=反馈学习
        # 空 list 表示该工具不受 ECML step 门禁约束（任意 step 均可调用）。
        scp_tools = [
            ("scp_molecule_descriptors", "Molecule descriptor computation", [2, 4]),
            ("scp_toxicity_assessment", "Toxicity / ADMET assessment", [3]),
            ("scp_literature_search", "Literature search", [1, 2, 6]),
            ("scp_protocol_draft", "Experiment protocol draft", [6]),
            ("scp_material_transform", "Material transformation", [2, 6]),
            ("scp_unit_conversion", "Physical quantity and unit conversion", [3, 4, 6]),
            ("scp_data_analysis", "Data processing and statistical analysis", [4, 6, 7]),
            ("scp_intern_agent", "InternAgent deep research and scientific tools", [1, 7]),
            ("scp_scigraph", "SciGraph universal science knowledge graph", [1, 2, 4]),
        ]
        for tool_id, description, allowed_steps in scp_tools:
            self._tools[tool_id] = ToolDescriptor(
                tool_id=tool_id,
                source="scp",
                owner="scp",
                risk_level=ToolRiskLevel.B,
                allowed_roles=["admin", "pm", "researcher"],
                allowed_ecml_steps=allowed_steps,
                timeout_seconds=120,
                description=description,
            )

    def register(self, descriptor: ToolDescriptor) -> None:
        """Register (or replace) a tool descriptor."""
        self._tools[descriptor.tool_id] = descriptor

    def unregister(self, tool_id: str) -> None:
        """Remove a tool from the catalog. No-op if not registered."""
        self._tools.pop(tool_id, None)

    def get(self, tool_id: str) -> ToolDescriptor | None:
        return self._tools.get(tool_id)

    def list_tools(
        self,
        source: str | None = None,
        risk_level: ToolRiskLevel | None = None,
    ) -> list[ToolDescriptor]:
        result = list(self._tools.values())
        if source is not None:
            result = [t for t in result if t.source == source]
        if risk_level is not None:
            result = [t for t in result if t.risk_level == risk_level]
        return result

    def is_registered(self, tool_id: str) -> bool:
        return tool_id in self._tools

    def is_allowed_for(
        self,
        tool_id: str,
        role: str,
        agent_id: str | None = None,
        ecml_step: int | None = None,
    ) -> bool:
        desc = self._tools.get(tool_id)
        if desc is None:
            return False
        if role not in desc.allowed_roles:
            return False
        if desc.allowed_agents and agent_id is not None and agent_id not in desc.allowed_agents:
            return False
        if desc.allowed_ecml_steps and ecml_step is not None and ecml_step not in desc.allowed_ecml_steps:
            return False
        return True

    def update_health(self, tool_id: str, health: ToolHealthStatus) -> None:
        desc = self._tools.get(tool_id)
        if desc is None:
            raise KeyError(f"Tool '{tool_id}' not registered")
        desc.health_status = health

    def get_fallback(self, tool_id: str) -> str | None:
        desc = self._tools.get(tool_id)
        if desc is None:
            return None
        return desc.fallback_tool_id

    def apply_default_fallbacks(self) -> int:
        """评测修复 P1-001：按 DEFAULT_FALLBACK_MAP 为未配置 fallback 的工具补默认回退。

        仅当回退目标已注册且当前 fallback_tool_id 为空时生效，
        不覆盖调用方显式配置的回退关系。返回新配置的数量。
        """
        applied = 0
        for tool_id, fallback_id in DEFAULT_FALLBACK_MAP.items():
            desc = self._tools.get(tool_id)
            if desc is None or desc.fallback_tool_id:
                continue
            if fallback_id not in self._tools or fallback_id == tool_id:
                continue
            desc.fallback_tool_id = fallback_id
            applied += 1
        return applied

    def refresh_health(self, provider_health: dict[str, str] | None = None) -> dict[str, int]:
        """评测修复 P1-018：刷新工具健康状态。

        规则：
        - local 工具（本地进程内执行）→ healthy
        - scp / mcp 工具 → 依据 provider 健康映射：
          healthy → healthy，degraded → degraded，unhealthy → unhealthy，
          无 provider 信息保持 unknown
        返回各健康状态的工具计数。
        """
        provider_health = provider_health or {}
        counts: dict[str, int] = {"healthy": 0, "degraded": 0, "unhealthy": 0, "unknown": 0}
        for desc in self._tools.values():
            if desc.source == "local":
                desc.health_status = ToolHealthStatus.HEALTHY
            elif desc.source in ("scp", "mcp"):
                ph = (provider_health.get(desc.source) or "").lower()
                if ph == "healthy":
                    desc.health_status = ToolHealthStatus.HEALTHY
                elif ph == "degraded":
                    desc.health_status = ToolHealthStatus.DEGRADED
                elif ph == "unhealthy":
                    desc.health_status = ToolHealthStatus.UNHEALTHY
            counts[desc.health_status.value] += 1
        return counts
