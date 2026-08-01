"""Agent team models for agentic task orchestration."""
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from datetime import datetime, timezone

from ..capability.models import validate_semver


class AgentRole(str, Enum):
    """Agent 角色枚举，仅用于类型安全。

    实际允许值以 MDM dimensions (domain='agent_role') 为准。
    """
    MATERIAL_DISCOVERY = "material_discovery"      # 材料发现
    SYNTHESIS_PLANNING = "synthesis_planning"       # 合成规划
    DFT_VERIFICATION = "dft_verification"           # DFT 验证
    EXPERIMENT_ANALYSIS = "experiment_analysis"     # 实验分析
    PROJECT_MANAGER = "project_manager"            # 项目经理
    LITERATURE_RESEARCH = "literature_research"    # 文献调研
    QUALITY_REVIEW = "quality_review"              # 质量审核
    INDUSTRIALIZATION = "industrialization"        # 工业化配方验证
    CUSTOM = "custom"                               # 自定义


class AgentDefinition(BaseModel):
    id: str
    name: str                                          # 显示名称
    role: AgentRole
    description: str                                   # 角色描述
    expertise: list[str] = Field(default_factory=list)  # 专长领域
    tools: list[str] = Field(default_factory=list)       # 可使用的 MCP 工具名称
    avatar: str = ""                                    # 头像 emoji（空则前端取名字首字母兜底）
    is_builtin: bool = True                             # 是否内置
    llm_model: str = "LongCat-2.0"                      # 使用的 LLM 模型
    # 模型提供方："llm"=通用 LLM（config.llm），"internlm"=AI 引擎（config.internlm）
    # 空字符串=自动（llm_model 非空走 LLM，否则走 InternLM），保持向后兼容
    provider: str = ""
    # 备选模型（fallback）：优先模型失败时自动调用
    # provider_secondary 为空表示无 fallback
    provider_secondary: str = ""
    llm_model_secondary: str = ""
    status: str = "active"                               # active / development
    # V2 字段（由 registry 通过 _migrate_to_v2 填充，executor 强制执行）
    capabilities: list[str] = Field(default_factory=list)
    allowed_profiles: list[str] = Field(default_factory=list)
    max_autonomy_level: str = ""                        # L0/L1/L2/L3，空表示不限制
    prohibited_actions: list[str] = Field(default_factory=list)


class TaskStep(BaseModel):
    """任务分解中的一步"""
    step_id: str
    agent_id: str                                      # 执行此步的 agent
    task: str                                          # 子任务描述
    dependencies: list[str] = Field(default_factory=list)  # 依赖的前置 step_id
    expected_output: str = ""


# ── Committee Task Step ──

# Allowed template step names for committee tasks
ALLOWED_COMMITTEE_STEPS = frozenset({
    "thinker_propose",
    "collect_evidence",
    "verify_gate",
    "persist_verdict",
})

# Allowed committee roles (fixed, no dynamic creation)
ALLOWED_COMMITTEE_ROLES = frozenset({
    "thinker",
    "doer",
    "verifier",
    "coordinator",
})


class CommitteeTaskStep(BaseModel):
    """Committee task step — fixed template only.

    Prohibits: undefined roles, dynamic remote URLs, unknown MCP tools.
    Only produces: thinker_propose / collect_evidence / verify_gate / persist_verdict.
    """
    step_id: str
    template: str  # one of ALLOWED_COMMITTEE_STEPS
    role: str = ""  # one of ALLOWED_COMMITTEE_ROLES
    task: str = ""
    dependencies: list[str] = Field(default_factory=list)
    expected_output: str = ""
    # Committee-specific fields
    committee_type: str = ""
    case_id: str = ""
    evidence_capabilities: list[str] = Field(default_factory=list)
    # Tool constraints: only tools from registered allowlist
    allowed_tools: list[str] = Field(default_factory=list)


class OrchestrationPlan(BaseModel):
    """AI 推荐的编排方案"""
    team: list[AgentDefinition]
    steps: list[TaskStep]
    rationale: str = ""                                # 推荐理由
    estimated_steps: int = 0
    suggested_agents: list[AgentDefinition] = Field(default_factory=list)


class ExecutionEvent(BaseModel):
    """执行过程中的事件"""
    event_type: str  # "thinking" | "tool_call" | "tool_result" | "step_start" | "step_complete" | "error" | "complete"
    agent_id: str = ""
    agent_name: str = ""
    content: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    step_id: str = ""
    data: dict = Field(default_factory=dict)
    status: str = "success"  # "success" | "warning" | "error"


class OrchestrationRecord(BaseModel):
    """一次编排的历史记录"""
    id: str
    target: str
    team: list[AgentDefinition]
    steps: list[TaskStep]
    status: str = "pending"  # "pending" | "running" | "completed" | "failed"
    events: list[ExecutionEvent] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""
    result_summary: str = ""


# ── V2: Capability-driven Agent definitions ──


class AutonomyLevel(str, Enum):
    """Agent 自主等级"""
    L0_SUGGEST = "L0"        # 建议：只读取和生成假设
    L1_CONTROLLED = "L1"     # 受控执行：调用已批准只读工具
    L2_GATE = "L2"           # 门禁：基于规则写 Verdict


class AgentDefinitionV2(BaseModel):
    """Agent 定义 V2 — 声明能力需求而非直接绑定工具"""
    agent_id: str
    name: str
    role: str  # planner/thinker/doer/verifier/analyst/reviewer
    description: str
    capabilities: list[str] = Field(default_factory=list)
    allowed_profiles: list[str] = Field(default_factory=lambda: ["standard", "internlm_assisted", "committee_governed"])
    model_policy_id: str | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    optional_capabilities: list[str] = Field(default_factory=list)
    prohibited_actions: list[str] = Field(default_factory=list)
    default_evidence_requirements: list[str] = Field(default_factory=list)
    max_autonomy_level: str = "L0"
    status: str = "active"
    version: str = "2.0.0"
    legacy_agent_id: str = ""  # 原始 Agent ID，用于历史关联
    legacy_tools_json: str = "[]"  # 原始 tools 字段，仅供历史展示

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        return validate_semver(v)


class ToolEligibilityRule(BaseModel):
    """工具资格规则 — 将 Agent 能力映射到候选工具 alias 和 binding 优先级链"""
    rule_id: str
    agent_id: str
    capability: str
    profiles: list[str] = Field(default_factory=lambda: ["standard", "internlm_assisted", "committee_governed"])
    allowed_internal_tool_ids: list[str] = Field(default_factory=list)
    preferred_binding_order: list[str] = Field(default_factory=list)
    max_risk_level: str = "B"  # A/B/C/D
    requires_provenance: bool = True
    requires_human_review: bool = False
    budget_class: str = "default"
    fallback_action: str = "local_fallback"  # local_fallback/request_evidence/human_review/fail
