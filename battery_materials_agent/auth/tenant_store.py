"""租户管理存储。

``auth.tenants`` 表由 alembic 0050 迁移创建。本模块提供租户 CRUD 与状态管理，
供管理员后端/前端「租户管理」入口使用。业务数据隔离由 ``db.tenant_filter()``
在 store 层统一追加 ``tenant_id`` 过滤实现，本模块不负责行级过滤。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from sqlalchemy import text

from ..db import get_engine, DEFAULT_TENANT

logger = logging.getLogger(__name__)


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class Tenant(BaseModel):
    tenant_id: str = ""
    name: str = ""
    status: str = "active"  # active / disabled
    quota: dict = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class TenantStore:
    """PostgreSQL 租户持久化存储。"""

    def __init__(self):
        self.engine = get_engine()

    def create(self, tenant_id: str, name: str, status: str = "active") -> Tenant:
        now = datetime.now(timezone.utc).isoformat()
        tenant = Tenant(
            tenant_id=tenant_id or DEFAULT_TENANT,
            name=name,
            status=status,
            created_at=now,
            updated_at=now,
        )
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO auth.tenants
                        (tenant_id, name, status, quota, created_at, updated_at)
                        VALUES (:tenant_id, :name, :status, CAST(:quota AS JSONB),
                                :created_at, :updated_at)
                        ON CONFLICT (tenant_id) DO UPDATE SET
                            name=EXCLUDED.name,
                            status=EXCLUDED.status,
                            updated_at=EXCLUDED.updated_at"""),
                {
                    "tenant_id": tenant.tenant_id,
                    "name": name,
                    "status": status,
                    "quota": "{}",
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return tenant

    def get(self, tenant_id: str) -> Tenant | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT tenant_id, name, status, quota, created_at, updated_at "
                     "FROM auth.tenants WHERE tenant_id=:tenant_id"),
                {"tenant_id": tenant_id},
            ).fetchone()
        if row is None:
            return None
        return Tenant(
            tenant_id=row[0], name=row[1], status=row[2],
            quota=row[3] or {}, created_at=_iso(row[4]), updated_at=_iso(row[5]),
        )

    def list_all(self) -> list[Tenant]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT tenant_id, name, status, quota, created_at, updated_at "
                     "FROM auth.tenants ORDER BY created_at ASC")
            ).fetchall()
        return [Tenant(
            tenant_id=r[0], name=r[1], status=r[2],
            quota=r[3] or {}, created_at=_iso(r[4]), updated_at=_iso(r[5]),
        ) for r in rows]

    def set_status(self, tenant_id: str, status: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("UPDATE auth.tenants SET status=:status, updated_at=:now "
                     "WHERE tenant_id=:tenant_id"),
                {"status": status, "now": now, "tenant_id": tenant_id},
            )
            return (cur.rowcount or 0) > 0

    def is_active(self, tenant_id: str) -> bool:
        tenant = self.get(tenant_id)
        return tenant is not None and tenant.status == "active"