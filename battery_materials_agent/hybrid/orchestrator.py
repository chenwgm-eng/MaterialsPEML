"""Hybrid Orchestrator — 统一研发请求入口。

整合 IntentInterpreter（意图解析）、CapabilityRouter（能力路由）、
ModelRouter（模型路由）和 PlanValidator（计划校验），将研发请求转化为
可执行的 ResearchPlan，并提供 plan/validate/execute/replan 四个核心流程。
"""
from __future__ import annotations

import inspect
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .intent_interpreter import IntentInterpreter, MaterialScope, RiskAssessment
from .plan_validator import PlanValidator, ValidationResult

logger = logging.getLogger(__name__)

# 编排步骤 action → MCP 工具名的映射（action 为业务语义名，工具名为注册表名）
_ACTION_TOOL_ALIAS = {
    "compliance_check": "check_synthesis_feasibility",
    "generate_polymer_candidates": "generate_polymer_candidates",
    "generate_crystal_candidates": "generate_crystal_candidates",
    "route_material": "route_material",
    "design_formula": "design_formula",
    "predict_properties": "predict_polymer_properties",
    "verify_dft": "verify_dft",
}


# ── 数据模型 ──────────────────────────────────────────────────────


class ResearchRequest(BaseModel):
    """研发请求。"""

    request_id: str = ""
    scenario_id: str = ""  # P0-001：全局研发场景 ID，贯穿发现/预测/合成/ECML
    goal: str  # 用户目标描述
    material_scope: str = ""  # 材料类型枚举（crystal/polymer/molecule），与 material_system 解耦
    material_system: str = ""  # 材料体系名（领域包 material_systems.name，如"改性塑料"）
    target_properties: list[dict] = Field(default_factory=list)  # [{name, direction, min, max, weight}]
    constraints: dict = Field(default_factory=dict)
    preference: str = "balanced"  # balanced/rapid_exploration/conservative
    domain_key: str = ""  # 领域包关键字（如 battery/kingfa）；为空时使用默认领域包
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
    executor_kind: str = "native"  # native/scp/skill/agent（由领域包 pipeline 声明）
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

# action → capability 别名映射与内置流水线已迁移至 pipeline.py，
# 由 PipelineResolver 从领域包解析（无配置时回退内置默认）。


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
        domain_pack: dict | None = None,
        domain_pack_provider=None,
        stage_executors: dict | None = None,
        tool_executor: Any | None = None,
    ):
        self._capability_router = capability_router
        self._model_router = model_router
        self._intent_interpreter = intent_interpreter or IntentInterpreter()
        self._plan_validator = plan_validator or PlanValidator()
        self._agent_registry = agent_registry
        self._tool_gateway = tool_gateway
        self._run_manager = run_manager
        self._committee_trigger = committee_trigger
        from .pipeline import PipelineResolver
        from .stage_executor import StageExecutor

        # 领域包解析：默认注入的领域包 + 按 request.domain_key 动态解析的 provider。
        # domain_pack_provider 为可调用对象（domain_key: str -> dict | None），
        # 由 api.py 传入 DomainPackStore 解析逻辑，支持多领域包（battery/kingfa）切换。
        self._default_domain_pack = domain_pack
        self._domain_pack_provider = domain_pack_provider
        # 研发流水线从领域包解析；无匹配时使用内置默认（兼容旧行为）。
        self._pipeline_resolver = PipelineResolver(domain_pack)
        # 真实工具执行器（action → kwargs → MCP 工具调用结果）：
        # 由 api.py 注入 agent.tools.execute，使 native 阶段真实产出数据而非仅解析路由。
        self._tool_executor = tool_executor
        # 统一阶段执行器：按 executor_kind 分派（native/scp/skill/agent）。
        # 未显式注入时注册默认 native 执行器：基于 CapabilityRouter 真实解析
        # 步骤所需能力，返回解析结果接入真实执行路径；scp/skill/agent 未注册
        # 时由 StageExecutor 返回明确错误，避免静默占位。
        kind_executors = dict(stage_executors or {})
        if "native" not in kind_executors:
            kind_executors["native"] = self._native_capability_dispatch
        self._stage_executor = StageExecutor(kind_executors)

    async def _native_capability_dispatch(self, stage, context: dict | None = None) -> dict:
        """默认 native 执行器：解析步骤能力并通过 tool_executor 真实执行。

        解析出候选 binding（aliases）后，按 step.action 映射到真实 MCP 工具调用，
        把工具输出回填 result——保证 /research 流水线每一步都有真实数据产出
        （候选材料/配方/校验结果），而非仅返回路由信息。

        返回 dict：{status, capability, aliases, model_route, action, result}
        """
        capability = getattr(stage, "resolved_capability", "") or (
            stage.required_capabilities[0] if getattr(stage, "required_capabilities", None) else ""
        )
        action = getattr(stage, "action", "") or ""
        profile = getattr(self, "_execution_profile_cache", "standard")
        aliases: list[str] = []
        route = None
        if capability and self._capability_router is not None:
            try:
                candidates = self._capability_router.resolve(capability, profile)
                if inspect.isawaitable(candidates):
                    candidates = await candidates
                aliases = [c.binding_id for c in candidates] if candidates else []
            except Exception as e:  # noqa: BLE001
                logger.warning("native dispatch 路由解析失败: %s", e)
            if self._model_router is not None:
                try:
                    route_obj = self._model_router.route(capability, profile)
                    route = route_obj.route_id if route_obj else None
                except Exception:  # noqa: BLE001
                    route = None

        # 真实执行：action → MCP 工具（tool_executor 由 api.py 注入 agent.tools.execute）
        tool_result = None
        tool_error = ""
        if self._tool_executor is not None and action:
            tool_name = _ACTION_TOOL_ALIAS.get(action, action)
            try:
                kwargs = self._stage_tool_kwargs(action, stage, context or {})
                tool_result = self._tool_executor(tool_name, **kwargs)
                if inspect.isawaitable(tool_result):
                    tool_result = await tool_result
            except Exception as e:  # noqa: BLE001 - 工具失败不阻断编排，结果带错误说明
                tool_error = f"{type(e).__name__}: {e}"
                logger.warning("native 工具 %s 执行失败: %s", tool_name, e)

        base = {
            "status": "error" if tool_error and tool_result is None else "success",
            "capability": capability,
            "aliases": aliases,
            "model_route": route,
            "action": action,
            "tool": action,
        }
        if tool_result is not None:
            base["result"] = tool_result
        if tool_error:
            base["error"] = tool_error
            base["note"] = "工具执行失败，步骤结果不可用"
        return base

    @staticmethod
    def _stage_tool_kwargs(action: str, stage, context: dict | None = None) -> dict:
        """按步骤 action 构造工具调用参数（材料体系/目标属性透传给生成器）。"""
        ctx = context or {}
        target = ctx.get("target") or getattr(stage, "task", "") or ""
        material_system = ctx.get("material_system") or ""
        kwargs: dict = {}
        if action == "route_material":
            kwargs["material_input"] = {"name": target or "材料", "formula": target or ""}
        elif action == "generate_polymer_candidates":
            kwargs["target_properties"] = {}
            kwargs["num_candidates"] = 8
            # 材料体系透传：工程塑料/改性体系走工程塑料生成模式
            kwargs["material_system"] = material_system
        elif action == "generate_crystal_candidates":
            # 晶体生成器无 material_system 参数，仅透传数量（避免 TypeError）
            kwargs["elements"] = []
            kwargs["num_candidates"] = 8
        elif action == "predict_polymer_properties":
            kwargs["features"] = {"smiles": target or "[*]CC[*]", "psmiles": target or "[*]CC[*]"}
            kwargs["property_name"] = ctx.get("target_property") or "tensile_strength"
        elif action == "predict_crystal_properties":
            kwargs["features"] = {"formula": target or "LiCoO2"}
            kwargs["property_name"] = ctx.get("target_property") or "band_gap"
        elif action == "design_formula":
            kwargs["target_material"] = {
                "target_property": ctx.get("target_property") or "tensile_strength",
                "candidate": material_system or target,
            }
            # 材料体系透传：工程塑料体系走改性配方通道
            kwargs["material_system"] = material_system
        elif action == "compliance_check":
            kwargs["smiles"] = "[*]CC[*]"
        return kwargs

    def register_stage_executor(self, kind: str, executor) -> None:
        """注册某类阶段执行器（native/scp/skill/agent），运行期可扩展。"""
        self._stage_executor.register(kind, executor)

    def _resolve_domain_pack(self, request: ResearchRequest) -> dict | None:
        """按 request.domain_key 解析领域包数据；未指定时回退默认领域包。"""
        key = (getattr(request, "domain_key", "") or "").strip()
        if key and self._domain_pack_provider is not None:
            data = self._domain_pack_provider(key)
            if data is not None:
                return data
        return self._default_domain_pack

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

        按拓扑顺序遍历步骤，依据每步的 executor_kind 通过 StageExecutor 分派
        到对应执行引擎（native/scp/skill/agent），并 yield 执行事件。
        未注册的执行类型回退为占位事件，保证无回归。
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
                "executor_kind": step.executor_kind,
                "allowed_tool_aliases": list(step.allowed_tool_aliases),
                "model_route_id": step.model_route_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # 按 executor_kind 通过 StageExecutor 分派真实执行路径
            # context 透传研发请求上下文（材料体系/领域包/目标），供 native 工具调用使用
            context = {
                "material_system": getattr(request, "material_system", "") or "",
                "domain_key": getattr(request, "domain_key", "") or "",
                "target": getattr(request, "goal", "") or "",
            }
            result = await self._stage_executor.execute(step, context)
            step_output = result.get("result", result)
            if result.get("status") == "error":
                step.status = "failed"
                yield {
                    "event_type": "step_progress",
                    "step_id": step.step_id,
                    "agent_id": step.agent_id,
                    "action": step.action,
                    "content": f"派发 {step.agent_id} 执行 {step.action} 失败: {result.get('error', '')}",
                    "executor_kind": step.executor_kind,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            else:
                yield {
                    "event_type": "step_progress",
                    "step_id": step.step_id,
                    "agent_id": step.agent_id,
                    "action": step.action,
                    "content": f"派发 {step.agent_id} 执行 {step.action}",
                    "executor_kind": step.executor_kind,
                    "result": step_output,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            step.status = "completed" if result.get("status") != "error" else "failed"
            yield {
                "event_type": "step_complete",
                "step_id": step.step_id,
                "status": step.status,
                "executor_kind": step.executor_kind,
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
                executor_kind=step.executor_kind,
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
        """基于意图从领域包解析研发流水线并生成步骤。"""
        material_scope: MaterialScope = intent["material_scope"]
        risk_assessment: RiskAssessment = intent["risk_assessment"]
        material_type = material_scope.material_type or "molecule"

        # 从领域包解析流水线（带内置兜底）；context 用于计算 when 条件
        # 支持按 request.domain_key 动态切换领域包（如 battery/kingfa）
        pack = self._resolve_domain_pack(request)
        from .pipeline import PipelineResolver

        resolver = PipelineResolver(pack) if pack is not None else self._pipeline_resolver
        stages = resolver.resolve(
            material_type, {"requires_dft": risk_assessment.requires_dft}
        )

        steps: list[TaskStepV3] = []
        prev_step_id = ""
        for idx, stage in enumerate(stages):
            step_id = f"step_{idx}"
            deps = [prev_step_id] if prev_step_id else []
            capability = stage.resolved_capability
            steps.append(
                TaskStepV3(
                    step_id=step_id,
                    agent_id=stage.agent_role,
                    action=stage.action,
                    required_capabilities=[capability] if capability else [],
                    depends_on=deps,
                    autonomy_level=stage.autonomy_level,
                    executor_kind=stage.executor_kind,
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
