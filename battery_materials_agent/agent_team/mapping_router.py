"""映射控制台 API 路由 —— 决策 4-C 的主入口。

提供业务活动↔智能体↔工具 三层绑定的 CRUD + 新工具注册向导接口。
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import UserRole, require_role
from .activity_mapping import (
    ActivityAgentBinding,
    AgentToolBinding,
    ToolRegistration,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mappings", tags=["mappings"])

# 依赖注入点：由应用启动时 configure() 注入，替代反向 import api 模块
# （领域子路由不得依赖 API 单体，否则形成运行时循环依赖）
_store_provider = None
_proxy_provider = None


def configure(store, proxy) -> None:
    """启动时注入 ActivityMappingStore 与 AgentProxy（api.py startup 调用）。"""
    global _store_provider, _proxy_provider
    _store_provider = store
    _proxy_provider = proxy


def _get_store():
    """获取注入的 ActivityMappingStore 实例。"""
    store = _store_provider
    if store is None:
        raise HTTPException(status_code=503, detail="映射存储未初始化")
    return store


def _get_proxy():
    """获取注入的 AgentProxy 实例。"""
    proxy = _proxy_provider
    if proxy is None:
        raise HTTPException(status_code=503, detail="AgentProxy 未初始化")
    return proxy


# ===========================================================================
# 1. 业务活动 → 智能体 绑定
# ===========================================================================

class ActivityBindingUpdate(BaseModel):
    activity_id: str
    activity_name: str = ""
    activity_category: str = "ecml"
    agent_id: str
    capability_need: str = ""
    enabled: bool = True
    notes: str = ""


@router.get("/activities")
async def list_activity_bindings(category: str = ""):
    """列出所有业务活动→智能体绑定（决策 13-B：主从详情视图主表数据）。"""
    store = _get_store()
    items = store.list_activity_bindings(category)
    return {
        "items": [b.model_dump() for b in items],
        "total": len(items),
    }


@router.put("/activities/{activity_id}")
async def upsert_activity_binding(
    activity_id: str,
    req: ActivityBindingUpdate,
    user=Depends(require_role(UserRole.ADMIN)),
):
    """更新或创建业务活动→智能体绑定。"""
    store = _get_store()
    existing = store.get_agent_for_activity(activity_id)
    binding = ActivityAgentBinding(
        binding_id=existing.binding_id if existing else f"ab_{activity_id.replace('.', '_')}",
        activity_id=activity_id,
        activity_name=req.activity_name,
        activity_category=req.activity_category,
        agent_id=req.agent_id,
        capability_need=req.capability_need,
        enabled=req.enabled,
        notes=req.notes,
    )
    store.upsert_activity_binding(binding)
    return binding.model_dump()


@router.delete("/activities/{binding_id}")
async def delete_activity_binding(
    binding_id: str,
    user=Depends(require_role(UserRole.ADMIN)),
):
    """删除业务活动→智能体绑定。"""
    store = _get_store()
    if not store.delete_activity_binding(binding_id):
        raise HTTPException(status_code=404, detail="绑定不存在")
    return {"deleted": True}


# ===========================================================================
# 2. 智能体 → 工具 绑定
# ===========================================================================

class ToolBindingUpdate(BaseModel):
    agent_id: str
    capability: str
    primary_tool_id: str
    tools_whitelist: list[str] = Field(default_factory=list)
    tools_blacklist: list[str] = Field(default_factory=list)
    tool_model_override: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


@router.get("/agent-tools")
async def list_tool_bindings(agent_id: str = ""):
    """列出智能体→工具绑定（决策 13-B：详情面板数据）。"""
    store = _get_store()
    items = store.list_tool_bindings(agent_id)
    return {
        "items": [b.model_dump() for b in items],
        "total": len(items),
    }


@router.put("/agent-tools/{agent_id}/{capability}")
async def upsert_tool_binding(
    agent_id: str,
    capability: str,
    req: ToolBindingUpdate,
    user=Depends(require_role(UserRole.ADMIN)),
):
    """更新或创建智能体→工具绑定。"""
    store = _get_store()
    existing = store.get_tool_binding(agent_id, capability)
    binding = AgentToolBinding(
        binding_id=existing.binding_id if existing else f"tb_{agent_id}_{capability}",
        agent_id=agent_id,
        capability=capability,
        primary_tool_id=req.primary_tool_id,
        tools_whitelist=req.tools_whitelist,
        tools_blacklist=req.tools_blacklist,
        tool_model_override=req.tool_model_override,
        enabled=req.enabled,
    )
    store.upsert_tool_binding(binding)
    return binding.model_dump()


@router.delete("/agent-tools/{binding_id}")
async def delete_tool_binding(
    binding_id: str,
    user=Depends(require_role(UserRole.ADMIN)),
):
    """删除智能体→工具绑定。"""
    store = _get_store()
    if not store.delete_tool_binding(binding_id):
        raise HTTPException(status_code=404, detail="绑定不存在")
    return {"deleted": True}


# ===========================================================================
# 3. 工具注册（决策 11-C：基础向导 + 高级声明）
# ===========================================================================

class ToolRegistrationUpdate(BaseModel):
    name: str
    source: str  # local / scp / skill / mcp
    capability_refs: list[str] = Field(default_factory=list)
    execution_mode: str = "sync"  # sync / async
    scp_internal_name: str = ""
    skill_id: str = ""
    mcp_tool_name: str = ""
    default_params: dict = Field(default_factory=dict)
    risk_level: str = "B"
    enabled: bool = True
    description: str = ""


@router.get("/tools")
async def list_tool_registrations(source: str = ""):
    """列出所有注册的工具。"""
    store = _get_store()
    items = store.list_tool_registrations(source)
    return {
        "items": [t.model_dump() for t in items],
        "total": len(items),
    }


@router.post("/tools")
async def register_tool(
    req: ToolRegistrationUpdate,
    user=Depends(require_role(UserRole.ADMIN)),
):
    """决策 11-C：新工具注册向导。

    注册新工具后自动进入能力关联工具池，智能体按能力标签感知到它。
    """
    store = _get_store()
    reg = ToolRegistration(
        tool_id=f"tool_{req.source}_{req.name.replace(' ', '_').lower()[:20]}",
        name=req.name,
        source=req.source,
        capability_refs=req.capability_refs,
        execution_mode=req.execution_mode,
        scp_internal_name=req.scp_internal_name,
        skill_id=req.skill_id,
        mcp_tool_name=req.mcp_tool_name,
        default_params=req.default_params,
        risk_level=req.risk_level,
        enabled=req.enabled,
        description=req.description,
        user_registered=True,
    )
    store.upsert_tool_registration(reg)
    return reg.model_dump()


@router.put("/tools/{tool_id}")
async def update_tool(
    tool_id: str,
    req: ToolRegistrationUpdate,
    user=Depends(require_role(UserRole.ADMIN)),
):
    """更新工具注册信息。"""
    store = _get_store()
    existing = store.get_tool_registration(tool_id)
    if not existing:
        raise HTTPException(status_code=404, detail="工具不存在")
    reg = ToolRegistration(
        tool_id=tool_id,
        name=req.name,
        source=req.source,
        capability_refs=req.capability_refs,
        execution_mode=req.execution_mode,
        scp_internal_name=req.scp_internal_name,
        skill_id=req.skill_id,
        mcp_tool_name=req.mcp_tool_name,
        default_params=req.default_params,
        risk_level=req.risk_level,
        enabled=req.enabled,
        description=req.description,
        user_registered=existing.user_registered,
    )
    store.upsert_tool_registration(reg)
    return reg.model_dump()


@router.delete("/tools/{tool_id}")
async def delete_tool(
    tool_id: str,
    user=Depends(require_role(UserRole.ADMIN)),
):
    """删除工具注册。"""
    store = _get_store()
    if not store.delete_tool_registration(tool_id):
        raise HTTPException(status_code=404, detail="工具不存在")
    return {"deleted": True}


# ===========================================================================
# 4. 综合视图（决策 13-B：主从详情视图）
# ===========================================================================

@router.get("/overview")
async def get_mapping_overview(
    user=Depends(require_role(UserRole.RESEARCHER)),
):
    """决策 13-B：主从详情视图综合数据。

    返回业务活动列表 + 每个活动绑定的智能体 + 智能体的工具绑定。
    """
    store = _get_store()
    activities = store.list_activity_bindings()
    tool_bindings = store.list_tool_bindings()
    tools = store.list_tool_registrations()

    # 按智能体分组工具绑定
    tool_bindings_by_agent: dict[str, list[dict]] = {}
    for tb in tool_bindings:
        tool_bindings_by_agent.setdefault(tb.agent_id, []).append(tb.model_dump())

    # 构建主表数据：业务活动 + 智能体信息 + 该智能体的工具绑定
    overview_items = []
    for ab in activities:
        item = ab.model_dump()
        item["tool_bindings"] = tool_bindings_by_agent.get(ab.agent_id, [])
        overview_items.append(item)

    return {
        "activities": overview_items,
        "tools": [t.model_dump() for t in tools],
        "categories": list({ab.activity_category for ab in activities}),
        "total_activities": len(activities),
        "total_tools": len(tools),
    }


# ===========================================================================
# 5. 智能体可用工具查询（决策 9-C：白名单）
# ===========================================================================

@router.get("/agents/{agent_id}/tools")
async def get_agent_available_tools(
    agent_id: str,
    user=Depends(require_role(UserRole.RESEARCHER)),
):
    """返回智能体可用的工具列表（能力标签关联 + 白名单 - 黑名单）。"""
    proxy = _get_proxy()
    tool_ids = proxy.get_agent_tool_whitelist(agent_id)
    store = _get_store()
    tools = []
    for tid in tool_ids:
        reg = store.get_tool_registration(tid)
        if reg:
            tools.append(reg.model_dump())
    return {
        "agent_id": agent_id,
        "tools": tools,
        "total": len(tools),
    }
