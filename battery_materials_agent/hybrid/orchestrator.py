"""Hybrid Orchestrator — 统一研发请求入口。

整合 IntentInterpreter（意图解析）、CapabilityRouter（能力路由）、
ModelRouter（模型路由）和 PlanValidator（计划校验），将研发请求转化为
可执行的 ResearchPlan，并提供 plan/validate/execute/replan 四个核心流程。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .intent_interpreter import IntentInterpreter, MaterialScope, RiskAssessment
from .plan_validator import PlanValidator, ValidationResult


# ── 数据模型 ──────────────────────────────────────────────────────


class ResearchRequest(BaseModel):
    """研发请求。"""

    request_id: str = ""
    scenario_id: str = ""  # P0-001：全局研发场景 ID，贯穿发现/预测/合成/ECML
    goal: str  # 用户目标描述
    material_scope: str = ""  # 材料范围
    target_properties: list[dict] = Field(default_factory=list)  # [{name, direction, min, max, weight}]
    constraints: dict = Field(default_factory=dict)
    preference: str = "balanced"  # balanced/rapid_exploration/conservative
    user_id: str = ""
    project_id: str = ""
    task_id: str = ""  # 业务链路：关联 projects.tasks(task_id)，由 0009 迁移新增列
    created_at: str = ""


class ToolIntent(BaseModel):
    """LLM 输出的工具调用意图。"""

    internal_tool_id: str  # 语义 alias，不是 endpoint
    purpose: str
    arguments: dict = Field(default_factory=dict)
    expected_evidence_type: str = ""
    confidence: float = 0.5


class EvidenceSummary(BaseModel):
    """证据摘要。"""

    evidence_id: str
    source_type: Literal["local_mcp", "scp", "experiment", "model", "human"] = "local_mcp"
    provider_id: str | None = None
    tool_id: str | None = None
    result_status: str = "success"
    facts: dict = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    provenance_ref: str = ""


class TaskStepV3(BaseModel):
    """任务步骤 V3。"""

    step_id: str
    agent_id: str
    action: str
    required_capabilities: list[str] = Field(default_factory=list)
    allowed_tool_aliases: list[str] = Field(default_factory=list)
    model_route_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    output_schema_ref: str = ""
    evidence_requirements: list[str] = Field(default_factory=list)
    autonomy_level: str = "L0"
    on_failure: str = "fallback"  # fallback/request_evidence/human_review/stop
    status: str = "pending"  # pending/running/completed/failed/skipped


class ResearchPlan(BaseModel):
    """研发计划。"""

    plan_id: str = ""
    request_id: str = ""
    execution_profile: str = "standard"
    steps: list[TaskStepV3] = Field(default_factory=list)
    rationale: str = ""
    estimated_budget: dict = Field(default_factory=dict)  # {tokens, scp_calls, dft_jobs}
    risk_summary: str = ""
    capabilities_needed: list[str] = Field(default_factory=list)
    status: str = "draft"  # draft/confirmed/running/completed/failed/invalid


# ── 步骤模板 ──────────────────────────────────────────────────────

# action → capability 别名映射（用于 CapabilityRouter/ModelRouter 解析）
_ACTION_CAPABILITY_MAP: dict[str, str] = {
    "route_material": "material_reference_lookup",
    "generate_crystal_candidates": "chemical_descriptors",
    "generate_polymer_candidates": "chemical_descriptors",
    "predict_crystal_properties": "property_prediction",
    "predict_polymer_properties": "property_prediction",
    "check_synthesis_feasibility": "compliance_screening",
    "verify_dft": "dft_verification",
    "design_formula": "reaction_engineering_check",
    "compliance_check": "compliance_screening",
}


def _action_sequence(material_type: str, requires_dft: bool) -> list[tuple[str, str, str]]:
    """返回 (action, agent_role, autonomy_level) 列表。

    crystal: route → generate_crystal → predict → [verify_dft] → compliance
    polymer: route → generate_polymer → predict_polymer → design_formula → compliance
    molecule: route → generate_polymer → check_synthesis → predict_crystal → compliance
    """
    if material_type == "crystal":
        seq = [
            ("route_material", "planner", "L1"),
            ("generate_crystal_candidates", "thinker", "L0"),
            ("predict_crystal_properties", "doer", "L1"),
        ]
        if requires_dft:
            seq.append(("verify_dft", "doer", "L1"))
        seq.append(("compliance_check", "verifier", "L2"))
        return seq
    if material_type == "polymer":
        return [
            ("route_material", "planner", "L1"),
            ("generate_polymer_candidates", "thinker", "L0"),
            ("predict_polymer_properties", "doer", "L1"),
            ("design_formula", "doer", "L1"),
            ("compliance_check", "verifier", "L2"),
        ]
    # molecule（默认）
    return [
        ("route_material", "planner", "L1"),
        ("generate_polymer_candidates", "thinker", "L0"),
        ("check_synthesis_feasibility", "doer", "L1"),
        ("predict_crystal_properties", "doer", "L1"),
        ("compliance_check", "verifier", "L2"),
    ]


# ── HybridOrchestrator ───────────────────────────────────────────


class HybridOrchestrator:
    """统一研发请求入口。

    流程：
    1. plan(): IntentInterpreter → 生成步骤 → CapabilityRouter → ModelRouter → PlanValidator
    2. validate(): PlanValidator
    3. execute(): 按拓扑顺序派发步骤，yield 执行事件
    4. replan(): 基于已完成步骤生成新计划
    """

    def __init__(
        self,
        capability_router,
        model_router,
        intent_interpreter: IntentInterpreter | None = None,
        plan_validator: PlanValidator | None = None,
        agent_registry=None,
        tool_gateway=None,
        run_manager=None,
        committee_trigger=None,
    ):
        self._capability_router = capability_router
        self._model_router = model_router
        self._intent_interpreter = intent_interpreter or IntentInterpreter()
        self._plan_validator = plan_validator or PlanValidator()
        self._agent_registry = agent_registry
        self._tool_gateway = tool_gateway
        self._run_manager = run_manager
        self._committee_trigger = committee_trigger

    async def plan(self, request: ResearchRequest) -> ResearchPlan:
        """生成研发计划。"""
        # 1. 意图解析
        intent = await self._intent_interpreter.interpret(
            request.goal, request.constraints
        )
        # 2. 确定执行策略
        profile = intent["execution_profile"]
        # 3. 生成步骤
        steps = self._generate_steps(intent, request)
        # 4. 为每步解析能力路由和模型路由
        for step in steps:
            capability = (
                step.required_capabilities[0] if step.required_capabilities else ""
            )
            if capability:
                candidates = await self._capability_router.resolve(
                    capability, profile
                )
                if candidates:
                    step.allowed_tool_aliases = [c.binding_id for c in candidates]
                route = self._model_router.route(capability, profile)
                if route:
                    step.model_route_id = route.route_id
        # 5. 预估预算
        estimated_budget = self._estimate_budget(steps, profile)
        # 6. 汇总能力需求
        capabilities_needed = sorted(
            {cap for s in steps for cap in s.required_capabilities}
        )
        # 7. 构建计划
        risk_assessment: RiskAssessment = intent["risk_assessment"]
        material_scope: MaterialScope = intent["material_scope"]
        plan = ResearchPlan(
            plan_id=f"plan-{uuid4().hex[:12]}",
            request_id=request.request_id,
            execution_profile=profile,
            steps=steps,
            rationale=(
                f"意图解析: material_type={material_scope.material_type}, "
                f"profile={profile}, risk={risk_assessment.risk_level}"
            ),
            estimated_budget=estimated_budget,
            risk_summary=(
                f"risk_level={risk_assessment.risk_level}, "
                f"requires_dft={risk_assessment.requires_dft}, "
                f"requires_experiment={risk_assessment.requires_experiment}"
            ),
            capabilities_needed=capabilities_needed,
            status="draft",
        )
        # 8. 校验
        validation = self._plan_validator.validate(plan)
        if not validation.valid:
            plan.status = "invalid"
            plan.rationale = "; ".join(validation.errors)
        return plan

    async def validate(self, plan: ResearchPlan) -> ValidationResult:
        """校验计划。"""
        return self._plan_validator.validate(plan)

    async def execute(
        self, plan: ResearchPlan, request: ResearchRequest
    ) -> AsyncGenerator[dict, None]:
        """执行计划。

        简化实现：按拓扑顺序遍历步骤，yield 执行事件。
        实际工具调用由 Task 13 实现，此处只产出事件流。
        """
        plan.status = "running"
        yield {
            "event_type": "plan_start",
            "plan_id": plan.plan_id,
            "request_id": request.request_id,
            "execution_profile": plan.execution_profile,
            "step_count": len(plan.steps),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        for step in plan.steps:
            step.status = "running"
            yield {
                "event_type": "step_start",
                "step_id": step.step_id,
                "agent_id": step.agent_id,
                "action": step.action,
                "autonomy_level": step.autonomy_level,
                "allowed_tool_aliases": list(step.allowed_tool_aliases),
                "model_route_id": step.model_route_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # 实际工具调用由 Task 13 实现；此处仅产出占位事件
            yield {
                "event_type": "step_progress",
                "step_id": step.step_id,
                "content": (
                    f"派发 {step.agent_id} 执行 {step.action}"
                    f"（实际工具调用由后续任务实现）"
                ),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            step.status = "completed"
            yield {
                "event_type": "step_complete",
                "step_id": step.step_id,
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # 委员会触发检查：依据计划状态自动检测是否需要创建委员会 case
            if self._committee_trigger:
                triggers = self._committee_trigger.check_all(
                    plan, step=step.step_id
                )
                for trigger in triggers:
                    if trigger.triggered:
                        yield {
                            "event_type": "committee_triggered",
                            "step_id": step.step_id,
                            "trigger_type": trigger.trigger_type,
                            "reason": trigger.reason,
                            "severity": trigger.severity,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }

        plan.status = "completed"
        yield {
            "event_type": "plan_complete",
            "plan_id": plan.plan_id,
            "status": "completed",
            "completed_steps": [s.step_id for s in plan.steps],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def replan(
        self, plan: ResearchPlan, completed_steps: list[str]
    ) -> ResearchPlan:
        """重新规划。

        保留已完成步骤，将剩余步骤重新生成（保持能力路由与模型路由配置）。
        """
        completed_set = set(completed_steps)
        # 标记已完成步骤
        for step in plan.steps:
            if step.step_id in completed_set:
                step.status = "completed"

        remaining = [s for s in plan.steps if s.step_id not in completed_set]
        if not remaining:
            plan.status = "completed"
            return plan

        # 重新生成剩余步骤：保留原 action/能力配置，重置 step_id 与依赖
        new_steps: list[TaskStepV3] = []
        prev_step_id = completed_steps[-1] if completed_steps else ""
        for idx, step in enumerate(remaining):
            new_step_id = f"replan_step_{idx}"
            deps = [prev_step_id] if prev_step_id else list(step.depends_on)
            new_step = TaskStepV3(
                step_id=new_step_id,
                agent_id=step.agent_id,
                action=step.action,
                required_capabilities=list(step.required_capabilities),
                allowed_tool_aliases=list(step.allowed_tool_aliases),
                model_route_id=step.model_route_id,
                depends_on=deps,
                output_schema_ref=step.output_schema_ref,
                evidence_requirements=list(step.evidence_requirements),
                autonomy_level=step.autonomy_level,
                on_failure=step.on_failure,
                status="pending",
            )
            new_steps.append(new_step)
            prev_step_id = new_step_id

        # 合并已完成步骤 + 新步骤
        merged_steps = [
            s for s in plan.steps if s.step_id in completed_set
        ] + new_steps

        new_plan = ResearchPlan(
            plan_id=f"{plan.plan_id}-replan",
            request_id=plan.request_id,
            execution_profile=plan.execution_profile,
            steps=merged_steps,
            rationale=f"基于已完成步骤 {completed_steps} 重新规划",
            estimated_budget=plan.estimated_budget,
            risk_summary=plan.risk_summary,
            capabilities_needed=plan.capabilities_needed,
            status="draft",
        )

        validation = self._plan_validator.validate(new_plan)
        if not validation.valid:
            new_plan.status = "invalid"
            new_plan.rationale = "; ".join(validation.errors)
        return new_plan

    # ── 内部方法 ──────────────────────────────────────────────────

    def _generate_steps(
        self, intent: dict, request: ResearchRequest
    ) -> list[TaskStepV3]:
        """基于意图生成步骤。"""
        material_scope: MaterialScope = intent["material_scope"]
        risk_assessment: RiskAssessment = intent["risk_assessment"]
        material_type = material_scope.material_type or "molecule"

        actions = _action_sequence(material_type, risk_assessment.requires_dft)

        steps: list[TaskStepV3] = []
        prev_step_id = ""
        for idx, (action, role, autonomy) in enumerate(actions):
            step_id = f"step_{idx}"
            deps = [prev_step_id] if prev_step_id else []
            capability = _ACTION_CAPABILITY_MAP.get(action, "")
            steps.append(
                TaskStepV3(
                    step_id=step_id,
                    agent_id=role,
                    action=action,
                    required_capabilities=[capability] if capability else [],
                    depends_on=deps,
                    autonomy_level=autonomy,
                    status="pending",
                )
            )
            prev_step_id = step_id
        return steps

    def _estimate_budget(
        self, steps: list[TaskStepV3], profile: str
    ) -> dict:
        """预估预算。"""
        # 每步预估 token 消耗
        tokens_per_step = {
            "standard": 0,
            "internlm_assisted": 2000,
            "committee_governed": 4000,
        }.get(profile, 0)

        total_tokens = tokens_per_step * len(steps)

        # 潜在 SCP 调用：统计含 scp: binding 的步骤数
        scp_calls = sum(
            1
            for s in steps
            if any(alias.startswith("scp:") for alias in s.allowed_tool_aliases)
        )

        # DFT 任务：统计 verify_dft 步骤
        dft_jobs = sum(1 for s in steps if s.action == "verify_dft")

        return {
            "tokens": total_tokens,
            "scp_calls": scp_calls,
            "dft_jobs": dft_jobs,
        }
