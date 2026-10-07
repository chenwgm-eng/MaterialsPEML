"""租户管理路由（T12：从 api.py 抽出的最小模块化原型）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .middleware import require_permission
from .tenant_store import TenantStore

router = APIRouter()


class TenantCreateRequest(BaseModel):
    tenant_id: str = ""
    name: str = ""
    status: str = "active"


@router.get("/tenants", dependencies=[Depends(require_permission("tenant.manage"))])
async def list_tenants():
    """列出所有租户（tenant.manage 权限）。"""
    return [t.model_dump() for t in TenantStore().list_all()]


@router.post("/tenants", dependencies=[Depends(require_permission("tenant.manage"))])
async def create_tenant(req: TenantCreateRequest):
    """创建租户（tenant.manage 权限）。"""
    store = TenantStore()
    if store.get(req.tenant_id) is not None:
        raise HTTPException(status_code=409, detail=f"租户 {req.tenant_id} 已存在")
    tenant = store.create(req.tenant_id, req.name, req.status or "active")
    return tenant.model_dump()


@router.post("/tenants/{tenant_id}/status", dependencies=[Depends(require_permission("tenant.manage"))])
async def set_tenant_status(tenant_id: str, status: str):
    """启用/停用租户（tenant.manage 权限）。"""
    if not TenantStore().set_status(tenant_id, status):
        raise HTTPException(status_code=404, detail="租户不存在")
    return {"ok": True, "tenant_id": tenant_id, "status": status}
