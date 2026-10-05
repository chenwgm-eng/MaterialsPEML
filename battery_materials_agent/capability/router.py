"""能力契约 REST 路由。主程序挂载时不加 prefix。"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..audit import AuditEntry, get_audit_logger
from ..auth import User, UserRole, get_current_user, require_role
from .models import CapabilityContract
from .registry import CapabilityRegistry

logger = logging.getLogger(__name__)

router = APIRouter()

registry = CapabilityRegistry()
registry.seed_builtin()

# capability_id 格式校验：仅允许字母、数字、下划线、连字符
_CAP_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_capability_id(capability_id: str) -> None:
    if not _CAP_ID_PATTERN.match(capability_id):
        raise HTTPException(
            status_code=400,
            detail="capability_id 仅允许字母、数字、下划线和连字符",
        )


def _audit(request: Request, action: str, detail: dict, operator: str = "system") -> None:
    """记录能力契约相关审计日志，失败不阻断主流程，但必须留痕可诊断。"""
    try:
        get_audit_logger().log(AuditEntry(
            event_type="decision",
            module="capability",
            action=action,
            detail=detail,
            operator=operator,
            confirmed=True,
        ))
    except Exception:
        # 审计记录不允许静默丢失：至少 warning 级日志保留证据线索
        logger.warning("能力契约审计写入失败 action=%s detail=%s", action, detail, exc_info=True)


@router.get("/capabilities", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def list_capabilities(
    domain: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
):
    """查询能力契约列表，支持适用域/风险等级/状态/关键词过滤。"""
    contracts = registry.list_all(domain=domain, risk_level=risk_level, status=status, q=q)
    return {"capabilities": [c.model_dump() for c in contracts], "count": len(contracts)}


@router.get("/capabilities/{capability_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def get_capability(capability_id: str):
    """查询单个能力契约。"""
    contract = registry.get(capability_id)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"契约 '{capability_id}' 不存在")
    return contract.model_dump()


@router.post("/capabilities", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def create_capability(contract: CapabilityContract, request: Request):
    """人工登记契约，初始状态为待审批。"""
    _validate_capability_id(contract.capability_id)
    if registry.get(contract.capability_id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"能力 ID '{contract.capability_id}' 已存在，请使用编辑或更换 ID",
        )
    contract.status = "pending_approval"
    contract.source = "manual"
    saved = registry.save(contract)
    user = get_current_user(request)
    _audit(request, "create", {"capability_id": saved.capability_id, "name": saved.name},
           operator=user.username if user else "system")
    return saved.model_dump()


@router.put("/capabilities/{capability_id}", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def update_capability(capability_id: str, contract: CapabilityContract, request: Request):
    """更新已登记的契约。"""
    _validate_capability_id(capability_id)
    if registry.get(capability_id) is None:
        raise HTTPException(status_code=404, detail=f"契约 '{capability_id}' 不存在")
    contract.capability_id = capability_id
    saved = registry.save(contract)
    user = get_current_user(request)
    _audit(request, "update", {"capability_id": capability_id, "name": saved.name},
           operator=user.username if user else "system")
    return saved.model_dump()


@router.post("/capabilities/{capability_id}/approve", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def approve_capability(capability_id: str, request: Request):
    """审批通过，状态置为 active。"""
    contract = registry.get(capability_id)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"契约 '{capability_id}' 不存在")
    if contract.status == "active":
        raise HTTPException(status_code=400, detail=f"契约 '{capability_id}' 已是活跃状态")
    contract.status = "active"
    saved = registry.save(contract)
    user = get_current_user(request)
    _audit(request, "approve", {"capability_id": capability_id},
           operator=user.username if user else "system")
    return saved.model_dump()


@router.post("/capabilities/{capability_id}/deprecate", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def deprecate_capability(capability_id: str, request: Request):
    """废止契约。"""
    contract = registry.get(capability_id)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"契约 '{capability_id}' 不存在")
    if contract.status == "deprecated":
        raise HTTPException(status_code=400, detail=f"契约 '{capability_id}' 已废止")
    contract.status = "deprecated"
    saved = registry.save(contract)
    user = get_current_user(request)
    _audit(request, "deprecate", {"capability_id": capability_id},
           operator=user.username if user else "system")
    return saved.model_dump()


@router.delete("/capabilities/{capability_id}", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def delete_capability(capability_id: str, request: Request):
    """删除契约（仅 admin，且记录审计日志）。"""
    if registry.get(capability_id) is None:
        raise HTTPException(status_code=404, detail=f"契约 '{capability_id}' 不存在")
    if not registry.delete(capability_id):
        raise HTTPException(status_code=404, detail=f"契约 '{capability_id}' 不存在")
    user = get_current_user(request)
    _audit(request, "delete", {"capability_id": capability_id},
           operator=user.username if user else "system")
    return {"deleted": capability_id}


@router.get("/capabilities/{capability_id}/fallback-chain", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def get_fallback_chain(capability_id: str):
    """解析契约回退链（含起点，防循环）。"""
    if registry.get(capability_id) is None:
        raise HTTPException(status_code=404, detail=f"契约 '{capability_id}' 不存在")
    chain = registry.get_fallback_chain(capability_id)
    return {
        "capability_id": capability_id,
        "chain": [c.model_dump() for c in chain],
        "count": len(chain),
    }
