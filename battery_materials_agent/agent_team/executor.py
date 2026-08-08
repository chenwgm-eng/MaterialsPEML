"""Agentic executor: runs orchestration plans and streams execution events."""
from __future__ import annotations
import asyncio
import uuid
import re
from typing import AsyncGenerator

from .models import (
    AgentDefinition,
    CommitteeTaskStep,
    ExecutionEvent,
    OrchestrationPlan,
    OrchestrationRecord,
    TaskStep,
)
from .registry import AgentRegistry


def _run_async_safe(coro):
    """Safely run a coroutine from a sync context.

    - No running event loop: use ``asyncio.run``.
    - Already in a loop (e.g. called from async): schedule via
      ``run_coroutine_threadsafe`` to avoid nesting loops.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


def alnum_only(s: str) -> bool:
    """判断字符串是否仅含字母和数字。"""
    return bool(re.fullmatch(r'[A-Za-z0-9]+', s))


def _is_valid_candidate(smiles: str) -> bool:
    """校验候选分子是否为合理结构。"""
    if not smiles or len(smiles) < 2:
        return False

    # 过滤单原子/双原子碎片
    if smiles in ("HO", "N", "HOO", "O", "F", "Cl", "H", "H2", "F2", "N2", "O2"):
        return False

    # 过滤明显不合理的简单片段
    # 只含 1-2 个原子的 SMILES
    atom_count = len(re.findall(r'[A-Z][a-z]?', smiles))
    if atom_count < 3:
        return False

    # 尝试用 RDKit 验证
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return False
        # 至少 3 个重原子
        heavy_atoms = mol.GetNumHeavyAtoms()
        if heavy_atoms < 3:
            return False
    except ImportError:
        pass

    return True


def _is_valid_smiles(token: str) -> bool:
    """用 RDKit 验证 token 是否为合法 SMILES（RDKit 不可用时回退为启发式判断）。"""
    try:
        from rdkit import Chem
        return Chem.MolFromSmiles(token) is not None
    except ImportError:
        # 无 RDKit 时回退：纯字母数字 + 长度 2-6 视为候选 SMILES
        return alnum_only(token) and 2 <= len(token) <= 6


def _is_valid_formula(token: str) -> bool:
    """用 pymatgen 验证 token 是否为合法化学式（pymatgen 不可用时回退到正则基本校验）。"""
    try:
        from pymatgen.core import Composition
        comp = Composition(token)
        return len(comp.elements) > 0
    except Exception:
        return bool(re.match(r'^[A-Z][a-zA-Z0-9\s\(\)\.]*$', token))


class AgenticExecutor:
    """Agent 小队执行器：按拓扑顺序执行编排方案，流式输出执行事件。"""

    # 工具名 → 动作类别映射（用于 prohibited_actions 检查）
    _TOOL_ACTION_MAP: dict[str, str] = {
        "subscribe_experiment_updates": "experiment.start",
        "verify_dft": "dft.submit",
        "check_synthesis_feasibility": "synthesis.execute",
        "design_formula": "formula.design",
    }

    def __init__(self, registry: AgentRegistry, agent, committee_event_store=None,
                 tool_gateway=None, capability_router=None,
                 execution_profile: str = "standard"):
        self.registry = registry
        self.agent = agent  # BatteryMaterialsAgent 实例，用于调用 MCP 工具
        self._records: dict[str, OrchestrationRecord] = {}
        # 限制内存中保留的执行记录数量，避免长时间运行导致无界增长
        self._max_records = 200
        self._committee_event_store = committee_event_store  # CommitteeEventStore 实例
        # Control Plane tool gateway (optional) — routes tool calls through
        # policy/budget/idempotency checks with fallback to direct invocation.
        self._cp_tool_gateway = tool_gateway
        # CapabilityRouter (optional) — resolves capability alias to binding
        # candidates. When None, existing gateway/direct path is unchanged.
        self._capability_router = capability_router
        self._execution_profile = execution_profile
        # 工具调用审批：approval_id -> {event, tool_name, agent_id, step_id, result}
        # result 为 None 表示待审批，True 表示批准，False 表示拒绝
        self._pending_approvals: dict[str, dict] = {}

    async def create_record(self, target: str, plan: OrchestrationPlan) -> str:
        """预先创建执行记录并返回 record_id，避免竞态条件。"""
        record_id = str(uuid.uuid4())
        record = OrchestrationRecord(
            id=record_id,
            target=target,
            team=plan.team,
            steps=plan.steps,
            status="running",
        )
        self._records[record_id] = record
        # 简单 LRU：超过上限时丢弃最早的记录
        if len(self._records) > self._max_records:
            oldest_id = next(iter(self._records))
            self._records.pop(oldest_id, None)
        return record_id

    async def execute(
        self, target: str, plan: OrchestrationPlan, record_id: str = ""
    ) -> AsyncGenerator[ExecutionEvent, None]:
        """执行编排方案，流式 yield 执行事件。

        record_id 可选，若未提供则内部创建。调用方可先调用 create_record 获取 record_id 再传入。
        """
        if not record_id or record_id not in self._records:
            record_id = await self.create_record(target, plan)
        record = self._records[record_id]
        # 从 target 文本中提取目标属性关键词，供工具调用时使用
        self._current_target_property = self._extract_target_property(target)
        # agent_id -> AgentDefinition 映射；优先用 plan.team，为空时从 registry 兜底
        team_for_map = plan.team if plan.team else [
            self.registry.get_agent(s.agent_id) for s in plan.steps
            if self.registry.get_agent(s.agent_id)
        ]
        agent_map: dict[str, AgentDefinition] = {a.id: a for a in team_for_map}
        try:
            # 拓扑排序步骤
            ordered_steps = self._topological_sort(plan.steps)
            summaries: list[str] = []
            step_outputs: list[dict] = []  # 维护工具输出历史，供下一步工具作为输入

            for step in ordered_steps:
                agent_def = agent_map.get(step.agent_id)
                if not agent_def:
                    agent_def = self.registry.get_agent(step.agent_id) or AgentDefinition(
                        id=step.agent_id, name=step.agent_id, role="custom",
                        description="", is_builtin=False,
                    )
                # 1. step_start
                start_event = ExecutionEvent(
                    event_type="step_start",
                    agent_id=agent_def.id,
                    agent_name=agent_def.name,
                    content=f"开始执行: {step.task}",
                    step_id=step.step_id,
                )
                record.events.append(start_event)
                yield start_event

                # 2. thinking（模拟 LLM 思考）
                await asyncio.sleep(0.5)
                thinking_text = self._simulate_thinking(agent_def, step, target)
                thinking_event = ExecutionEvent(
                    event_type="thinking",
                    agent_id=agent_def.id,
                    agent_name=agent_def.name,
                    content=thinking_text,
                    step_id=step.step_id,
                )
                record.events.append(thinking_event)
                yield thinking_event

                # 3. 工具调用（如果 agent 有工具且任务匹配）
                tool_name = self._select_tool(agent_def, step.task)
                if tool_name:
                    # ── 策略检查 1: max_autonomy_level（L0 禁止调用工具）──
                    if self._is_l0(agent_def):
                        policy_event = ExecutionEvent(
                            event_type="policy_violation",
                            agent_id=agent_def.id,
                            agent_name=agent_def.name,
                            content=f"Agent 自主等级为 L0（仅建议），禁止调用工具 {tool_name}，跳过执行",
                            step_id=step.step_id,
                            data={"tool": tool_name, "reason": "autonomy_l0_blocked"},
                            status="warning",
                        )
                        record.events.append(policy_event)
                        yield policy_event
                        step_status = "warning"
                        step_message = f"完成: {step.task}（L0 禁止工具调用）"
                        summaries.append(f"[{agent_def.name}] L0 等级，跳过工具 {tool_name}")
                        complete_event = ExecutionEvent(
                            event_type="step_complete",
                            agent_id=agent_def.id,
                            agent_name=agent_def.name,
                            content=step_message,
                            step_id=step.step_id,
                            status=step_status,
                        )
                        record.events.append(complete_event)
                        yield complete_event
                        continue

                    # ── 策略检查 2: prohibited_actions（L2 忽略）──
                    blocked_action = self._check_prohibited(agent_def, tool_name)
                    if blocked_action:
                        policy_event = ExecutionEvent(
                            event_type="policy_violation",
                            agent_id=agent_def.id,
                            agent_name=agent_def.name,
                            content=f"工具 {tool_name} 对应动作「{blocked_action}」被禁止，跳过执行",
                            step_id=step.step_id,
                            data={"tool": tool_name, "reason": "prohibited_action", "action": blocked_action},
                            status="warning",
                        )
                        record.events.append(policy_event)
                        yield policy_event
                        step_status = "warning"
                        step_message = f"完成: {step.task}（动作 {blocked_action} 被禁止）"
                        summaries.append(f"[{agent_def.name}] 工具 {tool_name} 被策略禁止")
                        complete_event = ExecutionEvent(
                            event_type="step_complete",
                            agent_id=agent_def.id,
                            agent_name=agent_def.name,
                            content=step_message,
                            step_id=step.step_id,
                            status=step_status,
                        )
                        record.events.append(complete_event)
                        yield complete_event
                        continue

                    # ── 策略检查 3: requires_human_review（阻塞等待审批）──
                    needs_review = await self._check_needs_human_review(agent_def, tool_name)
                    if needs_review:
                        approval_id = str(uuid.uuid4())
                        review_event = ExecutionEvent(
                            event_type="human_review_required",
                            agent_id=agent_def.id,
                            agent_name=agent_def.name,
                            content=f"工具 {tool_name} 需要人工审核，等待审批（approval_id={approval_id}）",
                            step_id=step.step_id,
                            data={
                                "tool": tool_name,
                                "approval_id": approval_id,
                                "reason": "eligibility_rule_requires_human_review",
                            },
                            status="warning",
                        )
                        record.events.append(review_event)
                        yield review_event

                        # 阻塞等待审批结果
                        approved = await self._wait_for_approval(
                            approval_id, agent_def.id, tool_name, step.step_id
                        )
                        if not approved:
                            skip_event = ExecutionEvent(
                                event_type="tool_result",
                                agent_id=agent_def.id,
                                agent_name=agent_def.name,
                                content=f"工具 {tool_name} 调用被审批拒绝，跳过执行",
                                step_id=step.step_id,
                                data={"tool": tool_name, "result": {"error": "审批被拒绝"}},
                                status="error",
                            )
                            record.events.append(skip_event)
                            yield skip_event
                            step_status = "error"
                            step_message = f"完成: {step.task}（审批拒绝）"
                            summaries.append(f"[{agent_def.name}] 工具 {tool_name} 审批被拒")
                            complete_event = ExecutionEvent(
                                event_type="step_complete",
                                agent_id=agent_def.id,
                                agent_name=agent_def.name,
                                content=step_message,
                                step_id=step.step_id,
                                status=step_status,
                            )
                            record.events.append(complete_event)
                            yield complete_event
                            continue

                        approved_event = ExecutionEvent(
                            event_type="tool_call",
                            agent_id=agent_def.id,
                            agent_name=agent_def.name,
                            content=f"工具 {tool_name} 审批通过，开始执行",
                            step_id=step.step_id,
                            data={"tool": tool_name, "approval_id": approval_id},
                        )
                        record.events.append(approved_event)
                        yield approved_event
                    else:
                        await asyncio.sleep(0.3)
                        tool_call_event = ExecutionEvent(
                            event_type="tool_call",
                            agent_id=agent_def.id,
                            agent_name=agent_def.name,
                            content=f"调用工具: {tool_name}",
                            step_id=step.step_id,
                            data={"tool": tool_name},
                        )
                        record.events.append(tool_call_event)
                        yield tool_call_event

                    # 实际调用 MCP 工具（放到线程中避免阻塞事件循环，加 15 秒超时）
                    # 关键修复：传入 step_outputs 让工具用上一步输出作为输入
                    try:
                        tool_result = await asyncio.wait_for(
                            asyncio.to_thread(self._invoke_tool, tool_name, target, step.task, step_outputs),
                            timeout=30.0,
                        )
                    except asyncio.TimeoutError:
                        tool_result = {"error": f"工具 {tool_name} 调用超时（30s）"}

                    # 6.1 DFT 未收敛检测
                    step_status = "success"
                    step_message = f"完成: {step.task}"
                    if isinstance(tool_result, dict):
                        if "error" in tool_result:
                            step_status = "error"
                            step_message = f"完成: {step.task}（{tool_result['error']}）"
                        else:
                            is_converged = tool_result.get("convergence", True) and tool_result.get("converged", True)
                            if not is_converged:
                                step_status = "warning"
                                step_message = f"完成: {step.task}（DFT 计算未收敛，结果仅供参考）"

                    # 6.2 候选生成后化学有效性校验
                    if tool_name in ("generate_crystal_candidates", "generate_polymer_candidates"):
                        self._filter_candidates(tool_result)

                    await asyncio.sleep(0.2)
                    result_summary = self._summarize_tool_result(tool_name, tool_result)
                    tool_result_event = ExecutionEvent(
                        event_type="tool_result",
                        agent_id=agent_def.id,
                        agent_name=agent_def.name,
                        content=result_summary,
                        step_id=step.step_id,
                        data={"tool": tool_name, "result": tool_result},
                    )
                    record.events.append(tool_result_event)
                    yield tool_result_event
                    summaries.append(f"[{agent_def.name}] {result_summary}")
                    # 关键修复：把本步输出加入历史，供下一步工具读取
                    if isinstance(tool_result, dict) and "error" not in tool_result:
                        step_outputs.append(tool_result)
                else:
                    # 无工具调用的 agent（如项目经理、文献调研员），仅输出思考
                    step_status = "success"
                    step_message = f"完成: {step.task}"
                    summaries.append(f"[{agent_def.name}] {thinking_text}")

                # 4. step_complete
                await asyncio.sleep(0.2)
                complete_event = ExecutionEvent(
                    event_type="step_complete",
                    agent_id=agent_def.id,
                    agent_name=agent_def.name,
                    content=step_message,
                    step_id=step.step_id,
                    status=step_status,
                )
                record.events.append(complete_event)
                yield complete_event

            # 最终完成事件
            result_summary = f"编排完成，共执行 {len(ordered_steps)} 步。" + "；".join(summaries)
            record.result_summary = result_summary
            record.status = "completed"
            from datetime import datetime, timezone
            record.completed_at = datetime.now(timezone.utc).isoformat()
            complete_event = ExecutionEvent(
                event_type="complete",
                content="编排完成",
                data={"record_id": record_id, "result_summary": result_summary},
            )
            record.events.append(complete_event)
            yield complete_event

        except Exception as e:
            record.status = "failed"
            from datetime import datetime, timezone
            record.completed_at = datetime.now(timezone.utc).isoformat()
            error_event = ExecutionEvent(
                event_type="error",
                content=f"执行出错: {e}",
                data={"record_id": record_id},
            )
            record.events.append(error_event)
            yield error_event

    def get_record(self, record_id: str) -> OrchestrationRecord | None:
        """获取执行记录。"""
        return self._records.get(record_id)

    def list_records(self, limit: int = 20) -> list[OrchestrationRecord]:
        """列出最近的执行记录（按创建时间倒序）。"""
        records = sorted(
            self._records.values(),
            key=lambda r: r.created_at,
            reverse=True,
        )
        return records[:limit]

    def _topological_sort(self, steps: list[TaskStep]) -> list[TaskStep]:
        """按 dependencies 对 steps 进行拓扑排序。"""
        step_map = {s.step_id: s for s in steps}
        visited: set[str] = set()
        result: list[TaskStep] = []

        def _visit(sid: str, path: set[str]):
            if sid in visited:
                return
            if sid in path:
                # 检测到环，跳过以避免死循环
                return
            step = step_map.get(sid)
            if not step:
                return
            path.add(sid)
            for dep in step.dependencies:
                _visit(dep, path)
            path.discard(sid)
            if sid not in visited:
                visited.add(sid)
                result.append(step)

        for s in steps:
            _visit(s.step_id, set())
        return result

    def _simulate_thinking(self, agent_def: AgentDefinition, step: TaskStep, target: str) -> str:
        """模拟 LLM 思考过程。"""
        role_thoughts = {
            "project_manager": f"分析任务「{target}」，分解为可执行子任务，分配给合适的小队成员。当前步骤: {step.task}",
            "material_discovery": f"从材料空间中筛选与「{target}」相关的候选材料，评估其潜力与可行性。",
            "synthesis_planning": f"评估候选材料的合成路径，分析反应可行性与成本。",
            "dft_verification": f"对候选材料进行量子化学计算验证，确认关键性质的准确性。",
            "experiment_analysis": f"查询相关实验数据，统计分析并提取性能指标。",
            "literature_research": f"检索「{target}」相关文献，整理理论依据与研究现状。",
            "quality_review": f"交叉验证各步骤结果，检查数据合理性与一致性。",
            "industrialization": f"基于企业物料库设计量产配方（BOM/BOP），评估合规性与成本可行性。",
        }
        return role_thoughts.get(
            agent_def.role.value,
            f"思考如何完成: {step.task}",
        )

    def _extract_target_property(self, target: str) -> str:
        """从任务目标文本中提取目标属性关键词，映射到标准属性 key。"""
        if not target:
            return "ionic_conductivity"
        t = target.lower()
        # 关键词到标准属性 key 的映射
        keyword_map = [
            (["离子电导率", "ionic conductivity", "电导率", "conductivity"], "ionic_conductivity"),
            (["带隙", "band gap", "bandgap", "禁带"], "band_gap"),
            (["形成能", "formation energy", "formation_energy"], "formation_energy"),
            (["电化学窗口", "electrochemical window", "ec window"], "electrochemical_window"),
            (["工作电压", "operating voltage", "voltage"], "operating_voltage"),
            (["理论容量", "theoretical capacity", "capacity"], "theoretical_capacity"),
            (["密度", "density"], "density"),
        ]
        for keywords, prop_key in keyword_map:
            for kw in keywords:
                if kw in t:
                    return prop_key
        return "ionic_conductivity"

    # ── 策略检查方法 ──────────────────────────────────────

    def _is_l0(self, agent_def: AgentDefinition) -> bool:
        """检查 agent 是否为 L0 自主等级（仅建议，禁止调用工具）。"""
        return agent_def.max_autonomy_level == "L0"

    def _check_prohibited(self, agent_def: AgentDefinition, tool_name: str) -> str | None:
        """检查工具是否对应被禁止的动作。

        L2 等级忽略 prohibited_actions 限制。
        返回被禁止的动作名，None 表示允许。
        """
        if agent_def.max_autonomy_level == "L2":
            return None
        action = self._TOOL_ACTION_MAP.get(tool_name)
        if action and action in agent_def.prohibited_actions:
            return action
        return None

    async def _check_needs_human_review(self, agent_def: AgentDefinition, tool_name: str) -> bool:
        """通过 CapabilityRouter 检查工具是否需要人工审核。

        注意：本方法在 async 上下文中被调用，必须直接 ``await``
        ``capability_router.resolve``，不能经 ``_run_async_safe`` 阻塞事件循环
        （``future.result()`` 会阻塞事件循环线程，导致同一 loop 上的协程永不执行，
        造成编排执行永久卡死）。
        """
        if self._capability_router is None:
            return False
        # 把 tool_name 当作 capability alias 来解析（MCP 工具名与 alias 一致）
        try:
            candidates = await self._capability_router.resolve(
                tool_name, self._execution_profile or "standard",
                agent_id=agent_def.id,
            )
            # 取第一个候选（排序后最优）检查 requires_human_review 标记
            if candidates and candidates[0].requires_human_review:
                return True
        except Exception:
            pass
        return False

    async def _wait_for_approval(
        self, approval_id: str, agent_id: str, tool_name: str, step_id: str
    ) -> bool:
        """阻塞等待人工审批结果。

        超时 5 分钟自动视为拒绝，避免永久阻塞。
        """
        import asyncio as _asyncio
        event = _asyncio.Event()
        self._pending_approvals[approval_id] = {
            "event": event,
            "tool_name": tool_name,
            "agent_id": agent_id,
            "step_id": step_id,
            "result": None,
            "created_at": __import__("time").time(),
        }
        try:
            await _asyncio.wait_for(event.wait(), timeout=300.0)
        except _asyncio.TimeoutError:
            return False
        entry = self._pending_approvals.get(approval_id, {})
        return entry.get("result") is True

    def resolve_approval(self, approval_id: str, approved: bool) -> bool:
        """外部调用：解决待审批的工具调用。

        返回 True 表示审批已处理，False 表示 approval_id 不存在或已处理。
        """
        entry = self._pending_approvals.get(approval_id)
        if not entry or entry.get("result") is not None:
            return False
        entry["result"] = approved
        event = entry.get("event")
        if event is not None:
            event.set()
        return True

    def list_pending_approvals(self) -> list[dict]:
        """列出所有待审批的工具调用。"""
        import time
        now = time.time()
        result = []
        for aid, entry in self._pending_approvals.items():
            if entry.get("result") is not None:
                continue
            result.append({
                "approval_id": aid,
                "tool_name": entry.get("tool_name", ""),
                "agent_id": entry.get("agent_id", ""),
                "step_id": entry.get("step_id", ""),
                "created_at": entry.get("created_at", now),
                "waiting_seconds": round(now - entry.get("created_at", now), 1),
            })
        return result

    def _select_tool(self, agent_def: AgentDefinition, task: str) -> str | None:
        """根据 agent 的 tools 列表和 task 内容选择调用的 MCP 工具。"""
        if not agent_def.tools:
            return None
        task_lower = task.lower()
        # 关键词到工具名的映射（按优先级）
        keyword_map = [
            (["晶体候选", "crystal candidate", "生成晶体", "generate_crystal"], "generate_crystal_candidates"),
            (["聚合物", "polymer", "生成聚合"], "generate_polymer_candidates"),
            (["验证", "verify", "dft", "量子", "quantum"], "verify_dft"),
            (["合成", "synthesis", "可行性"], "check_synthesis_feasibility"),
            (["实验", "experiment", "查询结果", "测试结果"], "get_experiment_results"),
            (["配方", "工业化", "量产", "BOM", "BOP", "合规", "成本", "formula", "industrial"], "design_formula"),
            (["预测", "predict"], None),  # 需要进一步区分晶体/聚合物
            (["路由", "route", "分发", "调度"], "route_material"),
        ]
        for keywords, tool_name in keyword_map:
            for kw in keywords:
                if kw in task_lower:
                    if tool_name is None:
                        # 预测类：根据 agent 角色或 tools 选择
                        if "predict_polymer_properties" in agent_def.tools and "polymer" in task_lower:
                            return "predict_polymer_properties"
                        if "predict_crystal_properties" in agent_def.tools:
                            return "predict_crystal_properties"
                        return None
                    if tool_name in agent_def.tools:
                        return tool_name
        # 无关键词匹配时不调用工具，仅输出 thinking
        return None

    def _invoke_tool(self, tool_name: str, target: str, task: str, prev_outputs: list | None = None) -> dict:
        """调用 MCP 工具，使用合理的默认参数。

        prev_outputs: 上一步工具的输出列表，用于从上一步结果中提取材料标识符。

        CapabilityRouter integration: if ``self._capability_router`` is set,
        resolve the tool_name as a capability alias to discover candidate
        bindings. 当对应契约被 deprecated/pending_high_risk 且 fallback 链
        全部不可用时，调用将被拒绝（fail-closed）；当走 fallback 链时，标记
        降级执行并继续。

        Control Plane integration: if ``self._cp_tool_gateway`` is set, route
        the call through the ToolGateway (with policy, budget, idempotency,
        provenance). Falls back to direct invocation on any failure.
        """
        kwargs = self._build_tool_kwargs(tool_name, target, task, prev_outputs or [])

        # ── CapabilityRouter (生效模式) — 契约门禁 ──
        # 解析 alias 到候选 binding；若契约不可调用且无 fallback，直接拒绝。
        _resolved_binding = None  # 优先使用 Router 解析出的 binding
        _degraded_info = ""
        if self._capability_router is not None and hasattr(self._capability_router, 'resolve'):
            import logging
            _cr_logger = logging.getLogger(__name__)
            try:
                candidates = _run_async_safe(
                    self._capability_router.resolve(
                        tool_name, self._execution_profile or "standard"
                    )
                )
                if not candidates:
                    # 契约门禁拒绝：主能力不可调用且 fallback 链全部不可用
                    _cr_logger.warning(
                        "CapabilityRouter blocked tool %s: no callable candidates "
                        "(contract deprecated/pending and no fallback available)",
                        tool_name,
                    )
                    return {
                        "error": f"工具 {tool_name} 被契约门禁拒绝：契约不可调用且无可用 fallback",
                        "blocked_by": "capability_contract",
                        "tool": tool_name,
                    }
                best = candidates[0]
                _resolved_binding = best.binding_id
                if best.degraded:
                    _degraded_info = f" (degraded from {best.fallback_from})"
                _cr_logger.info(
                    "CapabilityRouter resolved %s -> %s (source=%s, score=%.3f, status=%s%s)",
                    tool_name, best.binding_id, best.source,
                    getattr(best, 'relevance_score', 0.0),
                    best.contract_status or "unknown", _degraded_info,
                )
            except Exception as e:
                _cr_logger.warning(
                    "CapabilityRouter resolve failed for %s: %s (falling back to direct)",
                    tool_name, e
                )

        # ── Control Plane gateway routing (with fallback) ──
        if self._cp_tool_gateway is not None:
            try:
                from datetime import datetime, timezone, timedelta
                from ..control_plane.context import ExecutionContext
                now = datetime.now(timezone.utc)
                ctx = ExecutionContext(
                    correlation_id=str(uuid.uuid4()),
                    trace_id=str(uuid.uuid4()),
                    user_role="researcher",
                    agent_id="executor",
                    issued_at=now,
                    expires_at=now + timedelta(seconds=3600),
                )
                result = _run_async_safe(
                    self._cp_tool_gateway.invoke(ctx, tool_name, kwargs)
                )
                if result.status == "success":
                    return result.output if isinstance(result.output, dict) else {"result": result.output}
                # Gateway returned non-success (rejected/failed/timeout).
                # Honor Control Plane mode: enforce = fail-closed, observe = log & fall through.
                _cp = getattr(getattr(self.agent, "config", None), "control_plane", None)
                if _cp is not None and getattr(_cp, "tool_gateway_enforce", False):
                    # enforce 模式：拒绝直接调用，不绕过网关。
                    return {"error": f"工具 {tool_name} 被网关拒绝（{result.status}），enforce 模式阻止直接调用"}
                # observe 模式：记录后回退到直接调用。
                import logging
                logging.getLogger(__name__).warning(
                    "Gateway rejected %s (%s); observe mode, falling back to direct",
                    tool_name, result.status,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "Gateway invocation failed for %s: %s, falling back to direct",
                    tool_name, e,
                )

        # ── Direct invocation (original path) ──
        try:
            result = self.agent.tools.execute(tool_name, **kwargs)
            if isinstance(result, dict):
                return result
            if hasattr(result, "model_dump"):
                return result.model_dump()
            return {"result": str(result)}
        except Exception as e:
            return {"error": f"工具调用失败: {e}"}

    def _build_tool_kwargs(self, tool_name: str, target: str, task: str,
                           prev_outputs: list | None = None) -> dict:
        """为不同工具构建合理的默认参数。

        优先级：
        1. 从上一步工具输出中提取材料标识符（candidates/formula/smiles）
        2. 从 target 文本中用正则解析化学式或 SMILES
        3. 回退到与 target 关键词相关的默认材料
        """
        prev_outputs = prev_outputs or []
        material_id = self._extract_material_from_prev_outputs(prev_outputs)
        if not material_id:
            material_id = self._extract_material_id_from_text(target)

        # target 非化学式/SMILES 时，根据关键词选择默认材料
        if not material_id:
            material_id = self._default_material_from_keywords(target)

        if tool_name == "generate_crystal_candidates":
            return {"elements": [], "num_candidates": 5}
        if tool_name == "generate_polymer_candidates":
            target_prop = getattr(self, "_current_target_property", None) or "ionic_conductivity"
            return {"target_properties": {"target_property": target_prop}, "num_candidates": 5}
        if tool_name == "predict_crystal_properties":
            formula = material_id or "LiCoO2"
            prop = getattr(self, "_current_target_property", None) or "ionic_conductivity"
            return {"features": {"formula": formula}, "property_name": prop}
        if tool_name == "predict_polymer_properties":
            psmiles = material_id or "CCO"
            return {"features": {"psmiles": psmiles, "smiles": psmiles}, "property_name": "ionic_conductivity"}
        if tool_name == "check_synthesis_feasibility":
            smiles = material_id or "CC(=O)O"
            return {"smiles": smiles}
        if tool_name == "verify_dft":
            smiles = material_id or "CCO"
            return {"smiles": smiles, "property_name": "total_energy"}
        if tool_name == "get_experiment_results":
            formula = material_id or "LiCoO2"
            return {"formula": formula, "experiment_type": ""}
        if tool_name == "subscribe_experiment_updates":
            return {"callback_url": ""}
        if tool_name == "route_material":
            return {"material_input": {"name": target, "formula": material_id or "LiCoO2"}}
        if tool_name == "design_formula":
            return {"target_material": {"target_property": "ionic_conductivity", "candidate": material_id or target}}
        return {}

    def _default_material_from_keywords(self, target: str) -> str:
        """target 非化学式/SMILES 时，根据关键词推断默认材料标识符。"""
        t = (target or "").lower()
        if any(kw in t for kw in ["锂", "li", "负极", "anode", "金属锂"]):
            return "LiCoO2"
        if any(kw in t for kw in ["聚合", "polymer", "电解质", "electrolyte", "spe"]):
            return "CCO"
        if any(kw in t for kw in ["正极", "cathode"]):
            return "LiFePO4"
        return "LiCoO2"

    def _extract_material_id_from_text(self, text: str) -> str:
        """从文本中提取化学式或 SMILES 标识符。"""
        if not text or not isinstance(text, str):
            return ""
        # 1. 先尝试 SMILES 模式：包含 [C@H]、=、#、\、/、(、) 等特征，或纯字母数字混合的短 token
        smiles_chars = set("[=#\\()/@")
        tokens = re.split(r'[\s,;]+', text.strip())
        for token in tokens:
            if len(token) < 2:
                continue
            has_special = any(c in token for c in smiles_chars)
            # 纯字母数字 token（如 CCO, CCN）也作为候选 SMILES
            is_short_alnum = token.isascii() and alnum_only(token) and 2 <= len(token) <= 6
            if has_special or is_short_alnum:
                # 排除明显是普通英文单词（全字母且 >6 字符）
                if token.isalpha() and len(token) > 6:
                    continue
                # 用 RDKit 验证是否为合法 SMILES
                if _is_valid_smiles(token):
                    return token
        # 2. 尝试化学式模式：连续的 大写+小写?+数字? 段，至少 2 段
        # 如 LiCoO2, C6H12O6, NaCl
        formula_pattern = r'(?:[A-Z][a-z]?\d*){2,}'
        matches = re.findall(formula_pattern, text)
        if matches:
            # 取最长且包含数字的（更可能是真实化学式），并用 pymatgen 验证
            scored = [(m, len(m), any(c.isdigit() for c in m)) for m in matches]
            scored.sort(key=lambda x: (x[2], x[1]), reverse=True)
            for m, _, _ in scored:
                if _is_valid_formula(m):
                    return m
            # 无 pymatgen 可用时回退到最长匹配
            return scored[0][0]
        return ""

    def _extract_material_from_prev_outputs(self, prev_outputs: list) -> str:
        """从上一步工具的输出中提取材料标识符。"""
        if not prev_outputs:
            return ""
        # 倒序查找最后一个含候选/材料信息的输出
        for output in reversed(prev_outputs):
            if not isinstance(output, dict):
                continue
            # 1. generate_* 工具的输出包含 candidates 列表
            candidates = output.get("candidates", [])
            if candidates and isinstance(candidates, list):
                first = candidates[0]
                if isinstance(first, dict):
                    sid = first.get("smiles") or first.get("formula") or first.get("psmiles", "")
                    if sid:
                        return sid
            # 2. predict_* 工具的输出包含 formula/smiles
            smiles = output.get("smiles", "")
            if smiles:
                return smiles
            formula = output.get("formula", "")
            if formula:
                return formula
            # 3. route_material 输出
            routed = output.get("material_type", "")
            if routed and "formula" in output:
                return output["formula"]
        return ""

    def _summarize_tool_result(self, tool_name: str, result: dict) -> str:
        """将工具调用结果摘要为简短文本。"""
        if "error" in result:
            return f"工具 {tool_name} 调用失败: {result['error']}"
        if tool_name in ("generate_crystal_candidates", "generate_polymer_candidates"):
            count = result.get("count", 0)
            return f"生成 {count} 个候选材料"
        if tool_name == "predict_crystal_properties":
            prop = result.get("property_name", "性质")
            value = result.get("predicted_value", result.get("value", "未知"))
            return f"预测 {prop}: {value}"
        if tool_name == "predict_polymer_properties":
            prop = result.get("property_name", "性质")
            value = result.get("predicted_value", result.get("value", "未知"))
            return f"预测 {prop}: {value}"
        if tool_name == "check_synthesis_feasibility":
            score = result.get("feasibility_score", "未知")
            return f"合成可行性评分: {score}"
        if tool_name == "verify_dft":
            prop = result.get("property_name", "total_energy")
            value = result.get("value", result.get("total_energy", "未知"))
            return f"DFT 验证 {prop}: {value}"
        if tool_name == "get_experiment_results":
            count = result.get("count", 0)
            return f"查询到 {count} 条实验记录"
        if tool_name == "route_material":
            mtype = result.get("material_type", "未知")
            return f"路由结果: {mtype}"
        if tool_name == "design_formula":
            if "error" in result:
                return f"配方设计失败: {result['error']}"
            is_passed = result.get("is_passed", False)
            cost = result.get("estimated_unit_cost", 0)
            compliance = result.get("compliance", {})
            warnings = compliance.get("warnings", [])
            status = "通过" if is_passed else "未通过"
            detail = f"，警告: {'; '.join(warnings)}" if warnings else ""
            return f"配方{status}，估算成本 {cost:.1f} 元/kg{detail}"
        return f"工具 {tool_name} 执行完成"

    def _filter_candidates(self, result: dict) -> None:
        """过滤候选生成结果中不合理的分子片段。"""
        if not isinstance(result, dict):
            return
        candidates = result.get("candidates", [])
        if not isinstance(candidates, list):
            return
        filtered = []
        for c in candidates:
            if not isinstance(c, dict):
                continue
            smiles = c.get("smiles", "") or c.get("psmiles", "")
            if smiles and not _is_valid_candidate(smiles):
                continue
            filtered.append(c)
        result["candidates"] = filtered
        result["count"] = len(filtered)

    # ── Committee Step Execution ──

    async def execute_committee_steps(
        self,
        steps: list[CommitteeTaskStep],
        case_id: str,
        *,
        committee_type: str = "",
    ) -> AsyncGenerator[ExecutionEvent, None]:
        """Execute committee task steps and persist events to committee_events.

        Event types persisted:
          - case_created          — case is registered
          - proposal_ready        — thinker_propose completes
          - tool_started          — each tool invocation begins
          - tool_completed        — each tool invocation succeeds
          - tool_failed           — each tool invocation fails
          - verdict_ready         — verify_gate completes
          - human_review_requested — verdict is HUMAN_REVIEW
          - case_closed           — persist_verdict completes

        Yields ExecutionEvent for each step, same as the main execute() method.
        """
        event_store = self._committee_event_store

        def _persist(evt_type: str, data: dict) -> None:
            if event_store is not None:
                try:
                    event_store.append(case_id, evt_type, data)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("Failed to persist committee event: %s", e)

        # 1. case_created
        _persist("case_created", {
            "case_id": case_id,
            "committee_type": committee_type,
            "step_count": len(steps),
        })

        # Topological sort
        ordered_steps = self._topological_sort_committee(steps)

        verdict_decision = ""
        verdict_id = ""

        # Overall execution timeout — prevents a committee case from running forever.
        import time
        _overall_start = time.monotonic()
        _overall_timeout_s = 300.0

        for step in ordered_steps:
            # Timeout guard: abort remaining steps if overall budget is exceeded.
            if time.monotonic() - _overall_start > _overall_timeout_s:
                _persist("case_timeout", {
                    "case_id": case_id,
                    "committee_type": committee_type,
                    "elapsed_seconds": time.monotonic() - _overall_start,
                    "remaining_steps": True,
                })
                timeout_event = ExecutionEvent(
                    event_type="error",
                    content=f"委员会执行超时（{_overall_timeout_s}s），已中止剩余步骤",
                    data={"case_id": case_id, "decision": verdict_decision or "unknown"},
                )
                yield timeout_event
                break

            # step_start
            start_event = ExecutionEvent(
                event_type="step_start",
                agent_id=step.role,
                agent_name=step.role,
                content=f"[{step.template}] {step.task}",
                step_id=step.step_id,
            )
            yield start_event

            await asyncio.sleep(0.3)

            if step.template == "thinker_propose":
                # Thinker phase: generate proposal
                thinking_event = ExecutionEvent(
                    event_type="thinking",
                    agent_id=step.role,
                    agent_name="thinker",
                    content=f"分析委员会触发条件，生成提案与验证计划",
                    step_id=step.step_id,
                )
                yield thinking_event

                await asyncio.sleep(0.5)
                _persist("proposal_ready", {
                    "case_id": case_id,
                    "committee_type": committee_type,
                    "evidence_capabilities": step.evidence_capabilities,
                })

                complete_event = ExecutionEvent(
                    event_type="step_complete",
                    agent_id=step.role,
                    agent_name="thinker",
                    content="提案已生成，进入证据收集阶段",
                    step_id=step.step_id,
                    status="success",
                )
                yield complete_event

            elif step.template == "collect_evidence":
                # Doer phase: execute tools from allowed_tools
                results = []
                for tool_name in step.allowed_tools:
                    # tool_started
                    _persist("tool_started", {
                        "case_id": case_id,
                        "tool_name": tool_name,
                        "capabilities": step.evidence_capabilities,
                    })

                    tool_call_event = ExecutionEvent(
                        event_type="tool_call",
                        agent_id=step.role,
                        agent_name="doer",
                        content=f"调用工具: {tool_name}",
                        step_id=step.step_id,
                        data={"tool": tool_name},
                    )
                    yield tool_call_event

                    await asyncio.sleep(0.3)

                    try:
                        tool_result = await asyncio.wait_for(
                            asyncio.to_thread(
                                self._invoke_tool,
                                tool_name,
                                f"committee {committee_type} evidence collection",
                                f"collect evidence for committee {committee_type}",
                                prev_outputs=results,
                            ),
                            timeout=30.0,
                        )
                    except asyncio.TimeoutError:
                        tool_result = {"error": f"工具 {tool_name} 调用超时（30s）"}

                    if isinstance(tool_result, dict) and "error" in tool_result:
                        _persist("tool_failed", {
                            "case_id": case_id,
                            "tool_name": tool_name,
                            "error": tool_result.get("error", "unknown"),
                        })
                        tool_result_event = ExecutionEvent(
                            event_type="tool_result",
                            agent_id=step.role,
                            agent_name="doer",
                            content=f"工具 {tool_name} 失败: {tool_result.get('error', 'unknown')}",
                            step_id=step.step_id,
                            data={"tool": tool_name, "result": tool_result},
                            status="error",
                        )
                    else:
                        _persist("tool_completed", {
                            "case_id": case_id,
                            "tool_name": tool_name,
                            "result_summary": self._summarize_tool_result(tool_name, tool_result),
                        })
                        tool_result_event = ExecutionEvent(
                            event_type="tool_result",
                            agent_id=step.role,
                            agent_name="doer",
                            content=self._summarize_tool_result(tool_name, tool_result),
                            step_id=step.step_id,
                            data={"tool": tool_name, "result": tool_result},
                        )
                    yield tool_result_event
                    results.append(tool_result)

                complete_event = ExecutionEvent(
                    event_type="step_complete",
                    agent_id=step.role,
                    agent_name="doer",
                    content=f"证据收集完成，共执行 {len(step.allowed_tools)} 个工具",
                    step_id=step.step_id,
                    status="success",
                    data={"tool_results": results},
                )
                yield complete_event

            elif step.template == "verify_gate":
                # Verifier phase: execute gate checks
                thinking_event = ExecutionEvent(
                    event_type="thinking",
                    agent_id=step.role,
                    agent_name="verifier",
                    content="执行硬约束检查、证据覆盖评估，生成门禁决策",
                    step_id=step.step_id,
                )
                yield thinking_event

                await asyncio.sleep(0.5)

                # Default verdict; replace with a real verifier call when a
                # committee coordinator is wired into the executor.
                verdict_decision = "pass"
                verdict_id = f"v-{case_id}-{uuid.uuid4().hex[:8]}"
                if hasattr(self, "_committee_coordinator") and self._committee_coordinator:
                    try:
                        case = self._committee_coordinator.repository.get_case(case_id)
                        if case:
                            evidence = self._committee_coordinator.repository.get_evidence_by_case(case_id)
                            verdict = self._committee_coordinator.verifier.evaluate(case, None, evidence)
                            verdict_decision = verdict.decision.value if hasattr(verdict.decision, "value") else str(verdict.decision)
                            self._committee_coordinator.repository.save_verdict(verdict)
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning("Committee verification failed: %s", e)
                        verdict_decision = "unknown"

                _persist("verdict_ready", {
                    "case_id": case_id,
                    "verdict_id": verdict_id,
                    "decision": verdict_decision,
                })

                if verdict_decision == "human_review":
                    _persist("human_review_requested", {
                        "case_id": case_id,
                        "verdict_id": verdict_id,
                        "reason": "Committee verdict requires human review",
                    })

                complete_event = ExecutionEvent(
                    event_type="step_complete",
                    agent_id=step.role,
                    agent_name="verifier",
                    content=f"门禁结论: {verdict_decision}",
                    step_id=step.step_id,
                    status="success",
                    data={"verdict_id": verdict_id, "decision": verdict_decision},
                )
                yield complete_event

            elif step.template == "persist_verdict":
                # Coordinator phase: persist verdict
                await asyncio.sleep(0.3)

                _persist("case_closed", {
                    "case_id": case_id,
                    "verdict_id": verdict_id,
                    "decision": verdict_decision,
                    "committee_type": committee_type,
                })

                complete_event = ExecutionEvent(
                    event_type="step_complete",
                    agent_id=step.role,
                    agent_name="coordinator",
                    content=f"结论已持久化: {verdict_decision}",
                    step_id=step.step_id,
                    status="success",
                    data={"verdict_id": verdict_id, "decision": verdict_decision},
                )
                yield complete_event

        # Final complete event
        final_event = ExecutionEvent(
            event_type="complete",
            content=f"委员会执行完成，结论: {verdict_decision}",
            data={
                "case_id": case_id,
                "committee_type": committee_type,
                "verdict_id": verdict_id,
                "decision": verdict_decision,
            },
        )
        yield final_event

    def _topological_sort_committee(self, steps: list[CommitteeTaskStep]) -> list[CommitteeTaskStep]:
        """Topological sort for committee steps (same logic as main executor)."""
        step_map = {s.step_id: s for s in steps}
        visited: set[str] = set()
        result: list[CommitteeTaskStep] = []

        def _visit(sid: str, path: set[str]):
            if sid in visited:
                return
            if sid in path:
                return
            step = step_map.get(sid)
            if not step:
                return
            path.add(sid)
            for dep in step.dependencies:
                _visit(dep, path)
            path.discard(sid)
            if sid not in visited:
                visited.add(sid)
                result.append(step)

        for s in steps:
            _visit(s.step_id, set())
        return result
