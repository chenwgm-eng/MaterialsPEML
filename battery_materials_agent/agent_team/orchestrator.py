"""Task orchestrator: uses LLM to analyze tasks and recommend agent teams."""
from __future__ import annotations
import json
import logging
import re

import httpx

from .models import (
    AgentDefinition,
    ALLOWED_COMMITTEE_ROLES,
    ALLOWED_COMMITTEE_STEPS,
    CommitteeTaskStep,
    OrchestrationPlan,
    TaskStep,
)
from .registry import AgentRegistry
from ..audit import get_audit_logger, AuditEntry
from ..llm.schemas import ChatMessage, ChatRequest

logger = logging.getLogger(__name__)


class TaskOrchestrator:
    """任务编排器：用 LLM 分析任务并推荐 agent 小队与执行步骤。"""

    def __init__(self, registry: AgentRegistry, llm_config, llm_provider=None,
                 capability_router=None, execution_profile: str = "standard"):
        self.registry = registry
        self.llm_config = llm_config
        self._llm_provider = llm_provider
        # CapabilityRouter (optional) — resolves capability alias to binding
        # candidates for each plan step. When None, plan steps are unchanged.
        self._capability_router = capability_router
        self._execution_profile = execution_profile

    async def analyze_task(self, target: str, constraints: dict | None = None) -> OrchestrationPlan:
        """用 LLM 分析任务，推荐 agent 小队和任务分解方案。

        LLM 不可用或返回异常时，回退到基于规则的默认方案。
        """
        agents = self.registry.list_agents()
        # 尝试 LLM 编排
        if self.llm_config and getattr(self.llm_config, "api_key", ""):
            try:
                plan = await self._analyze_with_llm(target, constraints or {}, agents)
                if plan is not None:
                    self._audit_agent_expansion(agents, plan)
                    await self._resolve_step_capabilities(plan)
                    return plan
            except Exception as e:
                logger.warning("LLM 编排失败，回退到规则方案: %s", e)
        # 回退到规则方案
        plan = self._fallback_plan(target, agents)
        self._audit_agent_expansion(agents, plan)
        await self._resolve_step_capabilities(plan)
        return plan

    async def _resolve_step_capabilities(self, plan: OrchestrationPlan) -> None:
        """为 plan 中的每个 step 解析能力路由（仅记录，不改变现有 TaskStep 结构）。

        渐进式集成：仅当日志记录解析到的候选 binding，不影响现有 plan 结构
        和执行流程。当 ``self._capability_router`` 为 None 时直接返回。
        """
        if self._capability_router is None:
            return
        for step in plan.steps:
            capability = self._infer_capability_from_step(step)
            if not capability:
                continue
            try:
                candidates = await self._capability_router.resolve(
                    capability, self._execution_profile or "standard"
                )
                if candidates:
                    best = candidates[0]
                    logger.info(
                        "Step %s capability=%s resolved to %d candidates (top=%s)",
                        step.step_id, capability, len(candidates), best.binding_id,
                    )
            except Exception as e:
                logger.warning(
                    "CapabilityRouter resolve failed for step %s (capability=%s): %s",
                    step.step_id, capability, e,
                )

    def _infer_capability_from_step(self, step) -> str:
        """从步骤推断能力需求。"""
        task_lower = step.task.lower()
        if any(kw in task_lower for kw in ["生成", "候选", "设计", "generate", "design"]):
            if "聚合物" in step.task or "polymer" in task_lower:
                return "polymer_design"
            if "晶体" in step.task or "crystal" in task_lower:
                return "molecule_design"
            return "molecule_design"
        if any(kw in task_lower for kw in ["预测", "predict"]):
            return "property_prediction"
        if any(kw in task_lower for kw in ["合成", "synthesis", "可行性"]):
            return "reaction_engineering_check"
        if any(kw in task_lower for kw in ["验证", "verify", "dft"]):
            return "dft_verification"
        if any(kw in task_lower for kw in ["合规", "compliance", "安全"]):
            return "compliance_screening"
        if any(kw in task_lower for kw in ["实验", "experiment"]):
            return "experiment_qc_lookup"
        return ""

    def _audit_agent_expansion(self, all_agents: list[AgentDefinition], plan: OrchestrationPlan):
        """记录 Agent 扩容建议到审计日志。"""
        audit = get_audit_logger()
        audit.log(AuditEntry(
            event_type="ai_suggestion",
            module="orchestration",
            action="agent_expansion",
            detail={
                "available": [a.name for a in all_agents],
                "selected": [a.name for a in plan.team],
            },
            operator="system",
            confirmed=False,
        ))

    async def _analyze_with_llm(
        self, target: str, constraints: dict, agents: list[AgentDefinition]
    ) -> OrchestrationPlan | None:
        """调用 LLM 进行任务分析。"""
        system_prompt = (
            "你是电池材料研发任务编排 AI。根据用户的研究目标，"
            "从可用 agent 列表中推荐合适的 agent 小队，并分解出可执行的任务步骤。"
            "必须返回严格 JSON 格式，不要包含 markdown 代码块标记。"
        )
        # 构建 agent 清单摘要
        agent_lines = []
        for a in agents:
            tools_str = ", ".join(a.tools) if a.tools else "无"
            agent_lines.append(
                f"- id: {a.id} | 名称: {a.name} | 角色: {a.role.value} | "
                f"描述: {a.description} | 工具: [{tools_str}]"
            )
        agents_str = "\n".join(agent_lines)
        constraints_str = json.dumps(constraints, ensure_ascii=False) if constraints else "{}"
        user_prompt = (
            f"研究目标: {target}\n\n"
            f"约束条件: {constraints_str}\n\n"
            f"可用 agent 列表:\n{agents_str}\n\n"
            "请推荐 agent 小队和执行步骤，返回如下 JSON 格式（不要包含 ```json 标记）：\n"
            "{\n"
            '  "team": ["agent_id_1", "agent_id_2"],\n'
            '  "steps": [{"agent_id": "agent_id_1", "task": "子任务描述", '
            '"dependencies": [], "expected_output": "预期输出"}],\n'
            '  "rationale": "推荐理由"\n'
            "}\n\n"
            "要求：\n"
            "1. team 中的 agent_id 必须来自上面的可用 agent 列表\n"
            "2. steps 中的 agent_id 必须在 team 中\n"
            "3. dependencies 是前置步骤的序号列表（从 0 开始），可为空\n"
            "4. 步骤数量控制在 3-6 步之间"
        )

        # 优先使用注入的 LLMProvider
        if self._llm_provider is not None:
            try:
                request = ChatRequest(
                    model=getattr(self.llm_config, "model", "intern-s2-preview-397b"),
                    messages=[
                        ChatMessage(role="system", content=system_prompt),
                        ChatMessage(role="user", content=user_prompt),
                    ],
                    temperature=0.4,
                    max_tokens=min(4096, getattr(self.llm_config, "max_tokens", 4096)),
                )
                response = await self._llm_provider.complete(request)
                return self._parse_llm_response(response.content, agents)
            except Exception as e:
                logger.warning("LLM provider orchestrator call failed: %s", e)
                return None

        # 回退到现有 httpx 逻辑
        base_url = self.llm_config.base_url.rstrip("/")
        if "/v1" not in base_url:
            endpoint = f"{base_url}/v1/chat/completions"
        else:
            endpoint = f"{base_url}/chat/completions"

        headers = {"Authorization": f"Bearer {self.llm_config.api_key}"}
        payload = {
            "model": self.llm_config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
            "max_tokens": min(4096, getattr(self.llm_config, "max_tokens", 4096)),
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
        if response.status_code != 200:
            return None
        data = response.json()
        if "error" in data:
            raise RuntimeError(f"LLM API 返回错误: {data['error']}")
        if "choices" not in data:
            raise RuntimeError("LLM API 响应缺少 choices 字段")
        content = data["choices"][0]["message"]["content"]
        return self._parse_llm_response(content, agents)

    def _parse_llm_response(
        self, content: str, agents: list[AgentDefinition]
    ) -> OrchestrationPlan | None:
        """解析 LLM 返回的 JSON，映射 agent_id 到完整 AgentDefinition。"""
        # 提取 JSON 片段（兼容包含 markdown 代码块的情况）
        text = content.strip()
        if text.startswith("```"):
            # 去掉 markdown 代码块标记
            text = text.split("\n", 1)[1] if "\n" in text else text
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            text = text.strip()
        try:
            match = re.search(r'\{[\s\S]*\}', text)
            if not match:
                return None
            data = json.loads(match.group(0))
        except Exception:
            return None

        agent_map = {a.id: a for a in agents}
        team_ids = data.get("team", [])
        team = [agent_map[aid] for aid in team_ids if aid in agent_map]
        if not team:
            return None

        steps: list[TaskStep] = []
        for idx, s in enumerate(data.get("steps", [])):
            agent_id = s.get("agent_id", "")
            if agent_id not in agent_map:
                continue
            deps = s.get("dependencies", [])
            # 将数字序号依赖转换为 step_id（step_0, step_1, ...）
            dep_ids: list[str] = []
            for d in deps:
                if isinstance(d, int):
                    dep_ids.append(f"step_{d}")
                elif isinstance(d, str):
                    dep_ids.append(d)
            steps.append(TaskStep(
                step_id=f"step_{idx}",
                agent_id=agent_id,
                task=s.get("task", ""),
                dependencies=dep_ids,
                expected_output=s.get("expected_output", ""),
            ))
        if not steps:
            return None

        return OrchestrationPlan(
            team=team,
            steps=steps,
            rationale=data.get("rationale", ""),
            estimated_steps=len(steps),
            suggested_agents=team,
        )

    def _fallback_plan(self, target: str, agents: list[AgentDefinition]) -> OrchestrationPlan:
        """LLM 不可用时的基于规则的默认方案。"""
        agent_map = {a.id: a for a in agents}
        target_lower = target.lower()

        def _aid_builtin(suffix: str) -> str | None:
            return f"builtin_{suffix}" if f"builtin_{suffix}" in agent_map else None

        # 根据关键词选择 agent 小队
        if "晶体" in target or "crystal" in target_lower:
            chosen_ids = [
                _aid_builtin("material_discovery"),
                _aid_builtin("dft_verifier"),
                _aid_builtin("project_manager"),
            ]
            rationale = "检测到晶体材料相关目标，推荐材料学家 + DFT 专家 + 项目经理组合"
        elif "聚合物" in target or "polymer" in target_lower:
            chosen_ids = [
                _aid_builtin("material_discovery"),
                _aid_builtin("synthesis_planner"),
                _aid_builtin("quality_reviewer"),
            ]
            rationale = "检测到聚合物材料相关目标，推荐材料学家 + 合成规划师 + 质量审核员组合"
        elif "合成" in target or "synthesis" in target_lower:
            chosen_ids = [
                _aid_builtin("synthesis_planner"),
                _aid_builtin("quality_reviewer"),
                _aid_builtin("project_manager"),
            ]
            rationale = "检测到合成相关目标，推荐合成规划师 + 质量审核员 + 项目经理组合"
        else:
            chosen_ids = [
                _aid_builtin("project_manager"),
                _aid_builtin("material_discovery"),
                _aid_builtin("dft_verifier"),
                _aid_builtin("synthesis_planner"),
                _aid_builtin("industrialization"),
                _aid_builtin("quality_reviewer"),
            ]
            rationale = "默认全流程方案：项目经理 + 材料学家 + DFT 专家 + 合成规划师 + 配方工艺师 + 质量审核员"

        team = [agent_map[aid] for aid in chosen_ids if aid and aid in agent_map]
        if not team:
            # fallback 到所有 builtin agents 的前 3 个
            builtin_agents = [a for a in agents if a.id.startswith("builtin_")]
            team = builtin_agents[:3]
        # 构建串行依赖步骤
        steps: list[TaskStep] = []
        prev_step_id = ""
        for idx, a in enumerate(team):
            step_id = f"step_{idx}"
            deps = [prev_step_id] if prev_step_id else []
            steps.append(TaskStep(
                step_id=step_id,
                agent_id=a.id,
                task=f"{a.name} 执行与「{target}」相关的研究任务",
                dependencies=deps,
                expected_output=f"{a.name} 的分析结果与建议",
            ))
            prev_step_id = step_id

        return OrchestrationPlan(
            team=team,
            steps=steps,
            rationale=rationale,
            estimated_steps=len(steps),
            suggested_agents=team,
        )

    # ── Committee Task Generation ──

    @staticmethod
    def _validate_committee_step(step: CommitteeTaskStep) -> None:
        """Validate that a committee step only uses allowed templates, roles, and tools.

        Raises ValueError for any disallowed configuration.
        """
        if step.template not in ALLOWED_COMMITTEE_STEPS:
            raise ValueError(
                f"CommitteeStep template '{step.template}' is not allowed. "
                f"Allowed: {sorted(ALLOWED_COMMITTEE_STEPS)}"
            )
        if step.role and step.role not in ALLOWED_COMMITTEE_ROLES:
            raise ValueError(
                f"CommitteeStep role '{step.role}' is not allowed. "
                f"Allowed: {sorted(ALLOWED_COMMITTEE_ROLES)}"
            )
        # Prohibit dynamic remote URLs in task description
        forbidden_url_patterns = [
            "http://", "https://", "ws://", "wss://",
        ]
        for pattern in forbidden_url_patterns:
            if pattern in step.task or pattern in step.expected_output:
                raise ValueError(
                    f"CommitteeStep contains dynamic URL ({pattern}) in task/output. "
                    "Dynamic remote URLs are prohibited in committee tasks."
                )
        # Prohibit unknown MCP tools: if allowed_tools is set, all must be from known registry
        if step.allowed_tools:
            # Known tool names are validated at generation time; here we just ensure
            # no obviously malicious tool names (e.g., containing URL-like patterns)
            for tool in step.allowed_tools:
                if any(p in tool for p in forbidden_url_patterns):
                    raise ValueError(
                        f"CommitteeStep allowed_tool '{tool}' contains dynamic URL. "
                        "Unknown MCP tools are prohibited."
                    )

    def generate_committee_plan(
        self,
        committee_type: str,
        case_id: str,
        *,
        context: dict | None = None,
        tool_registry: set[str] | None = None,
    ) -> list[CommitteeTaskStep]:
        """Generate fixed-template committee steps for a case.

        Produces exactly 4 steps in order:
          1. thinker_propose  — Thinker generates hypothesis & verification plan
          2. collect_evidence  — Doer collects evidence from registered tools
          3. verify_gate       — Verifier executes hard rules gate
          4. persist_verdict   — Coordinator persists verdict

        Constraints enforced:
          - Only ALLOWED_COMMITTEE_STEPS can be produced
          - Only ALLOWED_COMMITTEE_ROLES can be assigned
          - No dynamic remote URLs in task descriptions
          - No unknown MCP tools outside registered tool_registry

        Returns:
            list[CommitteeTaskStep]: Ordered list of 4 fixed-template steps.
        """
        context = context or {}
        tool_registry = tool_registry or set()

        # Known tools that are valid for committee evidence collection
        known_tools = tool_registry & {
            "check_synthesis_feasibility", "verify_dft",
            "predict_crystal_properties", "predict_polymer_properties",
            "get_experiment_results", "design_formula",
            "generate_crystal_candidates", "generate_polymer_candidates",
        }

        # Template definitions: each step has fixed role, template, and task
        template_defs = [
            {
                "template": "thinker_propose",
                "role": "thinker",
                "task": f"生成 {committee_type} 委员会提案：分析触发条件，提出待验证假设与证据需求",
                "expected_output": "结构化提案（假设列表、验证计划、所需证据类型）",
                "evidence_capabilities": [],
                "allowed_tools": [],
            },
            {
                "template": "collect_evidence",
                "role": "doer",
                "task": f"收集 {committee_type} 委员会证据：调用注册工具采集数据，验证提案中的假设",
                "expected_output": "证据清单（包含来源、方法、数值、置信度）",
                "evidence_capabilities": context.get("evidence_capabilities", []),
                "allowed_tools": sorted(known_tools),
            },
            {
                "template": "verify_gate",
                "role": "verifier",
                "task": f"执行 {committee_type} 委员会门禁：硬约束检查 + 证据覆盖评估 + 决策生成",
                "expected_output": "门禁结论（pass/reject/request_evidence/human_review）",
                "evidence_capabilities": [],
                "allowed_tools": [],
            },
            {
                "template": "persist_verdict",
                "role": "coordinator",
                "task": f"持久化 {committee_type} 委员会结论：写入 verdict、更新 case 状态、记录审计事件",
                "expected_output": "持久化确认（verdict_id、case 状态、事件流）",
                "evidence_capabilities": [],
                "allowed_tools": [],
            },
        ]

        steps: list[CommitteeTaskStep] = []
        prev_step_id = ""
        for idx, tpl in enumerate(template_defs):
            step_id = f"committee_step_{idx}"
            deps = [prev_step_id] if prev_step_id else []
            step = CommitteeTaskStep(
                step_id=step_id,
                template=tpl["template"],
                role=tpl["role"],
                task=tpl["task"],
                dependencies=deps,
                expected_output=tpl["expected_output"],
                committee_type=committee_type,
                case_id=case_id,
                evidence_capabilities=tpl["evidence_capabilities"],
                allowed_tools=tpl["allowed_tools"],
            )
            # Validate before adding
            self._validate_committee_step(step)
            steps.append(step)
            prev_step_id = step_id

        # Audit log
        audit = get_audit_logger()
        audit.log(AuditEntry(
            event_type="committee_plan_generated",
            module="orchestration",
            action="generate_committee_plan",
            detail={
                "committee_type": committee_type,
                "case_id": case_id,
                "step_count": len(steps),
                "templates": [s.template for s in steps],
            },
            operator="system",
            confirmed=False,
        ))

        return steps
