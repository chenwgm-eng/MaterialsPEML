"""智能体代理运行时（AgentProxy）—— 决策 7-A 的核心实现。

业务活动不直接调用工具，而是通过 AgentProxy 中介：
    业务活动 → AgentProxy.invoke_tool(agent_id, capability, params)
                ↓
              1. 解析智能体定义（决策 9-C：能力标签关联工具池 + 白名单/黑名单）
              2. 选择主工具（决策 2-C：主工具显式绑定 + CapabilityRouter 评分回退）
              3. 通过三层门禁（决策 10-B：智能体只管白名单，三层门禁复用）
              4. 感知 sync/async（决策 8-C：自动适配等待/返回句柄）
              5. 应用工具模型覆盖（决策 6-C：工具可声明覆盖智能体模型）

返回 AgentInvocationResult，包含 agent_id/tool_id/used_fallback/耗时/结果。
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .activity_mapping import ActivityMappingStore, AgentToolBinding, ToolRegistration
from .registry import AgentRegistry
from ..contracts.task import Task

logger = logging.getLogger(__name__)


def _run_async_safe(coro):
    """Safely run a coroutine from a sync context.

    - No running event loop: use ``asyncio.run``.
    - Already in a loop (e.g. FastAPI async 端点调用 sync 入口):
      通过 ``run_coroutine_threadsafe`` 调度到现有 loop，避免
      ``RuntimeError: asyncio.run() cannot be called from a running event loop``。
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


@dataclass
class AgentInvocationResult:
    """智能体工具调用结果。"""
    invocation_id: str = field(default_factory=lambda: f"inv_{uuid.uuid4().hex[:12]}")
    agent_id: str = ""
    tool_id: str = ""
    capability: str = ""
    success: bool = False
    used_fallback: bool = False  # 是否走了回退（主工具失败或不可用）
    fallback_from: str = ""  # 主工具 ID（如果走了回退）
    sync_mode: str = "sync"  # sync / async
    async_handle: Any = None  # async 模式下的句柄（task_id 或 coroutine）
    result: Any = None
    error: str = ""
    duration_ms: float = 0.0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""


class AgentProxy:
    """智能体代理层 —— 所有业务活动调用工具的统一入口。

    决策 7-A：业务活动只与 AgentProxy 交互，不直接调工具。
    决策 10-B：AgentProxy 只做白名单+主工具选择，三层门禁由 CapabilityRouter/ToolGateway 复用。
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        mapping_store: ActivityMappingStore,
        mcp_tool_registry,
        capability_router=None,
        tool_gateway=None,
        scp_client_pool=None,
        scp_catalog=None,
        skill_catalog=None,
        skill_executor=None,
        scientific_registry=None,
    ):
        self._agent_registry = agent_registry
        self._mapping_store = mapping_store
        self._mcp_tools = mcp_tool_registry
        self._capability_router = capability_router
        self._tool_gateway = tool_gateway
        self._scp_client_pool = scp_client_pool
        self._scp_catalog = scp_catalog
        self._skill_catalog = skill_catalog
        self._skill_executor = skill_executor
        # 原生科学服务注册表：{capability_id: NativeScientificService}，供 sci_* 能力执行
        self._scientific_registry = scientific_registry

    def set_capability_router(self, router) -> None:
        """注入 CapabilityRouter（延迟到 _init_hybrid_stack 之后，避免初始化顺序耦合）。"""
        self._capability_router = router

    # ===================================================================
    # 核心：业务活动 → 智能体 → 工具
    # ===================================================================

    def resolve_agent_for_activity(self, activity_id: str) -> Optional[str]:
        """决策 1-C：业务活动→智能体（静态绑定，不可用时由调用方按 capability_need 回退）。"""
        binding = self._mapping_store.get_agent_for_activity(activity_id)
        if binding and binding.enabled:
            # 校验智能体是否存在且 active
            agent = self._agent_registry.get_agent(binding.agent_id)
            if agent and agent.status == "active":
                return binding.agent_id
            logger.warning(
                "Activity %s bound agent %s not available (status=%s), "
                "caller should fallback by capability_need=%s",
                activity_id, binding.agent_id,
                agent.status if agent else "missing",
                binding.capability_need,
            )
        return None

    def find_agent_by_capability(self, capability: str) -> Optional[str]:
        """决策 1-C 回退：按 capability_need 查找首个 active 智能体。"""
        for binding in self._mapping_store.list_activity_bindings():
            if not binding.enabled or binding.capability_need != capability:
                continue
            agent = self._agent_registry.get_agent(binding.agent_id)
            if agent and agent.status == "active":
                return binding.agent_id
        return None

    # ===================================================================
    # 工具调用入口
    # ===================================================================

    def invoke_tool(
        self,
        agent_id: str,
        capability: str,
        params: dict,
        activity_id: str = "",
        timeout: float = 120.0,
    ) -> AgentInvocationResult:
        """同步调用入口（决策 8-C：sync 工具直接执行，async 工具阻塞等待）。"""
        started = time.time()
        result = AgentInvocationResult(
            agent_id=agent_id, capability=capability, sync_mode="sync",
        )
        try:
            # 科学服务能力（sci_*）：经 CapabilityRouter 路由后执行，其余走常规工具选择
            if self._is_scientific_capability(capability):
                evidence, tool_id, used_fallback, fallback_from = _run_async_safe(
                    self._invoke_scientific_async(capability, params, timeout)
                )
                result.tool_id = tool_id
                result.used_fallback = used_fallback
                result.fallback_from = fallback_from
                result.result = evidence
                result.success = True
                return result

            tool_id, tool_reg, used_fallback, fallback_from = self._select_tool(
                agent_id, capability
            )
            if not tool_id:
                raise ValueError(
                    f"No available tool for agent={agent_id} capability={capability}"
                )
            result.tool_id = tool_id
            result.used_fallback = used_fallback
            result.fallback_from = fallback_from

            # 决策 8-C：感知 sync/async
            if tool_reg.execution_mode == "async":
                result.sync_mode = "async"
                # async 工具在 sync 入口里阻塞等待（不能用 asyncio.run：
                # FastAPI async 端点已有事件循环，会抛 RuntimeError）
                async_result = _run_async_safe(self._invoke_async_tool(
                    agent_id, tool_id, tool_reg, params, activity_id, timeout
                ))
                result.result = async_result
            else:
                self._invoke_sync_tool(
                    agent_id, tool_id, tool_reg, params, activity_id, result
                )

            result.success = True
        except Exception as e:
            result.error = f"{type(e).__name__}: {e}"
            logger.exception("AgentProxy.invoke_tool failed: agent=%s cap=%s",
                             agent_id, capability)
        finally:
            result.duration_ms = (time.time() - started) * 1000
            result.completed_at = datetime.now(timezone.utc).isoformat()
        return result

    async def invoke_tool_async(
        self,
        agent_id: str,
        capability: str,
        params: dict,
        activity_id: str = "",
        timeout: float = 120.0,
    ) -> AgentInvocationResult:
        """异步调用入口（决策 8-C：async 工具返回句柄，sync 工具在线程池执行）。"""
        started = time.time()
        result = AgentInvocationResult(
            agent_id=agent_id, capability=capability, sync_mode="async",
        )
        try:
            # 科学服务能力（sci_*）：经 CapabilityRouter 路由后执行，其余走常规工具选择
            if self._is_scientific_capability(capability):
                evidence, tool_id, used_fallback, fallback_from = await self._invoke_scientific_async(
                    capability, params, timeout
                )
                result.tool_id = tool_id
                result.used_fallback = used_fallback
                result.fallback_from = fallback_from
                result.result = evidence
                result.success = True
                return result

            tool_id, tool_reg, used_fallback, fallback_from = self._select_tool(
                agent_id, capability
            )
            if not tool_id:
                raise ValueError(
                    f"No available tool for agent={agent_id} capability={capability}"
                )
            result.tool_id = tool_id
            result.used_fallback = used_fallback
            result.fallback_from = fallback_from

            if tool_reg.execution_mode == "async":
                # async 工具直接 await
                handle = await self._invoke_async_tool(
                    agent_id, tool_id, tool_reg, params, activity_id, timeout
                )
                result.result = handle
                result.async_handle = handle
            else:
                # sync 工具放线程池执行
                sync_res = await asyncio.to_thread(
                    self._invoke_sync_tool_blocking,
                    agent_id, tool_id, tool_reg, params, activity_id,
                )
                result.result = sync_res
        except Exception as e:
            result.error = f"{type(e).__name__}: {e}"
            logger.exception("AgentProxy.invoke_tool_async failed: agent=%s cap=%s",
                             agent_id, capability)
        finally:
            result.duration_ms = (time.time() - started) * 1000
            result.completed_at = datetime.now(timezone.utc).isoformat()
        return result

    # ===================================================================
    # 科学服务能力（sci_*）—— 经 CapabilityRouter 路由后执行
    # ===================================================================

    def _is_scientific_capability(self, capability: str) -> bool:
        """是否为原生科学服务能力（sci_*），且已注入科学服务注册表。"""
        return bool(capability.startswith("sci_") and self._scientific_registry)

    @staticmethod
    def _capability_id_from_binding(binding_id: str) -> str:
        """从路由 binding 提取服务 capability_id：'local:sci:mpa' → 'mpa'。"""
        parts = binding_id.split(":")
        if len(parts) >= 3 and parts[0] == "local" and parts[1] == "sci":
            return parts[2]
        return binding_id

    async def _invoke_scientific_async(
        self, capability: str, params: dict, timeout: float
    ) -> tuple[Any, str, bool, str]:
        """经 CapabilityRouter 解析 sci_* 能力并执行对应科学服务。

        返回 (evidence, tool_id, used_fallback, fallback_from)。
        """
        router = self._capability_router
        if router is None:
            raise RuntimeError("CapabilityRouter 未配置，无法路由科学服务")
        candidates = await router.resolve(capability, "standard")
        if not candidates:
            raise ValueError(f"No routable scientific capability for {capability}")
        candidate = candidates[0]
        capability_id = self._capability_id_from_binding(candidate.binding_id)
        service = self._scientific_registry.get(capability_id)
        if service is None:
            raise ValueError(f"Scientific service not registered: {capability_id}")
        task = Task(
            project_id=params.get("project_id", ""),
            capability_id=capability_id,
            title=capability,
            metadata=params,
        )
        # run_full_cycle 为同步计算，放入线程池避免阻塞事件循环
        evidence = await asyncio.to_thread(service.run_full_cycle, task, params)
        return evidence, candidate.binding_id, candidate.degraded, candidate.fallback_from

    # ===================================================================
    # 工具选择（决策 2-C + 9-C）
    # ===================================================================

    def _select_tool(
        self, agent_id: str, capability: str
    ) -> tuple[str, Optional[ToolRegistration], bool, str]:
        """选择工具：主工具优先，失败按能力标签候选池回退。

        返回 (tool_id, tool_reg, used_fallback, fallback_from)。
        """
        # 1. 主工具绑定
        binding = self._mapping_store.get_tool_binding(agent_id, capability)
        primary_tool_id = binding.primary_tool_id if binding and binding.enabled else ""

        # 2. 候选池 = 能力标签关联工具 + 白名单 - 黑名单（决策 9-C）
        candidates = self._mapping_store.find_tools_by_capability(capability)
        if binding:
            # 追加白名单
            for wid in binding.tools_whitelist:
                if not any(c.tool_id == wid for c in candidates):
                    reg = self._mapping_store.get_tool_registration(wid)
                    if reg and reg.enabled:
                        candidates.append(reg)
            # 排除黑名单
            candidates = [c for c in candidates if c.tool_id not in binding.tools_blacklist]

        # 3. 主工具可用则用主工具
        if primary_tool_id:
            for c in candidates:
                if c.tool_id == primary_tool_id:
                    return primary_tool_id, c, False, ""
            # 主工具不在候选池（可能被黑名单排除或未注册），单独查
            reg = self._mapping_store.get_tool_registration(primary_tool_id)
            if reg and reg.enabled:
                return primary_tool_id, reg, False, ""

        # 4. 主工具不可用，按候选池顺序回退（决策 2-C：评分回退简化为顺序回退）
        #    注：完整的 CapabilityRouter 评分排序由三层门禁层处理，这里只做候选选择
        for c in candidates:
            if c.tool_id != primary_tool_id:
                return c.tool_id, c, True, primary_tool_id

        return "", None, False, ""

    # ===================================================================
    # 工具执行
    # ===================================================================

    def _invoke_sync_tool(
        self,
        agent_id: str,
        tool_id: str,
        tool_reg: ToolRegistration,
        params: dict,
        activity_id: str,
        result: AgentInvocationResult,
    ):
        """同步工具执行（结果写入 result）。"""
        # 决策 6-C：应用工具模型覆盖
        params = self._apply_model_override(agent_id, tool_id, params)

        if tool_reg.source == "local" or tool_reg.source == "mcp":
            # 本地 MCP 工具：通过 MCPToolRegistry.execute
            tool_name = tool_reg.mcp_tool_name or tool_id
            # 决策 10-B：三层门禁由调用方在 agent_team/executor 中已实现，
            # 这里直接走 MCPToolRegistry.execute
            result.result = self._mcp_tools.execute(tool_name, **params)
        elif tool_reg.source == "scp":
            # SCP 同步调用（部分 SCP 工具注册为同步）
            result.result = self._invoke_scp_sync(tool_reg, params)
        elif tool_reg.source == "skill":
            result.result = self._invoke_skill_sync(tool_reg, params)
        else:
            raise ValueError(f"Unknown tool source: {tool_reg.source}")

    def _invoke_sync_tool_blocking(
        self,
        agent_id: str,
        tool_id: str,
        tool_reg: ToolRegistration,
        params: dict,
        activity_id: str,
    ) -> Any:
        """同步工具的阻塞执行（用于 async 入口在线程池调用）。"""
        params = self._apply_model_override(agent_id, tool_id, params)
        if tool_reg.source in ("local", "mcp"):
            tool_name = tool_reg.mcp_tool_name or tool_id
            return self._mcp_tools.execute(tool_name, **params)
        elif tool_reg.source == "scp":
            return self._invoke_scp_sync(tool_reg, params)
        elif tool_reg.source == "skill":
            return self._invoke_skill_sync(tool_reg, params)
        raise ValueError(f"Unknown tool source: {tool_reg.source}")

    async def _invoke_async_tool(
        self,
        agent_id: str,
        tool_id: str,
        tool_reg: ToolRegistration,
        params: dict,
        activity_id: str,
        timeout: float,
    ) -> Any:
        """异步工具执行。"""
        params = self._apply_model_override(agent_id, tool_id, params)

        if tool_reg.source == "scp":
            return await self._invoke_scp_async(tool_reg, params, timeout)
        elif tool_reg.source == "skill":
            return await self._invoke_skill_async(tool_reg, params, timeout)
        elif tool_reg.source in ("local", "mcp"):
            # 本地工具本应为 sync，但 async 入口走 execute_async
            tool_name = tool_reg.mcp_tool_name or tool_id
            return await self._mcp_tools.execute_async(tool_name, params)
        raise ValueError(f"Unknown async tool source: {tool_reg.source}")

    # ----- SCP 工具调用 -----

    def _invoke_scp_sync(self, tool_reg: ToolRegistration, params: dict) -> Any:
        """SCP 同步调用（阻塞等待 async SCP 完成）。"""
        return _run_async_safe(self._invoke_scp_async(tool_reg, params, timeout=120.0))

    async def _invoke_scp_async(
        self, tool_reg: ToolRegistration, params: dict, timeout: float
    ) -> Any:
        """SCP 异步调用。"""
        if not self._scp_client_pool or not self._scp_catalog:
            raise RuntimeError("SCP client pool or catalog not configured")
        binding = self._scp_catalog.get(tool_reg.scp_internal_name)
        if not binding:
            raise ValueError(f"SCP binding not found: {tool_reg.scp_internal_name}")
        if not (binding.server_id and binding.server_url):
            raise RuntimeError(f"SCP binding {tool_reg.scp_internal_name} not fully configured")

        # 决策 8-C：SCP 工具为 async，调用后等待结果
        result = await self._scp_client_pool.call_tool(
            server_id=binding.server_id,
            tool_name=binding.remote_tool_name,
            arguments=params,
            server_url=binding.server_url,
        )
        return result

    # ----- SKILL 调用 -----

    def _invoke_skill_sync(self, tool_reg: ToolRegistration, params: dict) -> Any:
        return _run_async_safe(self._invoke_skill_async(tool_reg, params, timeout=120.0))

    async def _invoke_skill_async(
        self, tool_reg: ToolRegistration, params: dict, timeout: float
    ) -> Any:
        if not self._skill_executor:
            raise RuntimeError("Skill executor not configured")
        return await self._skill_executor.execute(tool_reg.skill_id, params, timeout=timeout)

    # ===================================================================
    # 工具模型覆盖（决策 6-C）
    # ===================================================================

    def _apply_model_override(self, agent_id: str, tool_id: str, params: dict) -> dict:
        """应用工具级 LLM 模型覆盖。

        决策 6-C：默认跟随智能体模型，工具可声明覆盖。
        """
        # 查找该工具的所有绑定，看是否有 tool_model_override
        # 这里简化：只检查 capability 对应的绑定
        for binding in self._mapping_store.list_tool_bindings(agent_id):
            if tool_id in binding.tool_model_override:
                override_model = binding.tool_model_override[tool_id]
                if override_model:
                    params = dict(params)
                    params["_model_override"] = override_model
                    params["_model_provider"] = "internlm"
                break
        return params

    # ===================================================================
    # 工具白名单查询（决策 9-C）
    # ===================================================================

    def get_agent_tool_whitelist(self, agent_id: str) -> list[str]:
        """返回智能体可用的工具 ID 列表（能力标签关联 + 白名单 - 黑名单）。"""
        agent = self._agent_registry.get_agent(agent_id)
        if not agent:
            return []

        # 从智能体所有能力标签聚合候选工具
        all_tools: list[str] = []
        seen: set[str] = set()

        # 1. 能力关联工具
        for reg in self._mapping_store.list_tool_registrations():
            if not reg.enabled:
                continue
            # 通过 AgentToolBinding 检查该 agent 是否绑定了对应 capability
            for binding in self._mapping_store.list_tool_bindings(agent_id):
                if binding.enabled and binding.capability in reg.capability_refs:
                    if reg.tool_id not in seen:
                        # 检查黑名单
                        if reg.tool_id not in binding.tools_blacklist:
                            all_tools.append(reg.tool_id)
                            seen.add(reg.tool_id)
                    break

        # 2. 各 binding 的额外白名单
        for binding in self._mapping_store.list_tool_bindings(agent_id):
            if not binding.enabled:
                continue
            for wid in binding.tools_whitelist:
                if wid not in seen:
                    all_tools.append(wid)
                    seen.add(wid)

        return all_tools
