"""导航可见性覆盖表 auth.nav_visibility 的读写存储（Step B）。

仅控制「导航是否显示」，不替代任何操作权限。每个 (tenant_id, role, entry_key) 一行，
visible 默认 TRUE；visible=false 表示该角色的该入口被隐藏。
权限下限由前端 requiredAnyPermission + 后端 permission 判定保证：visible=true
不能把无最小权限的入口变可见（见设计文档 4.B3）。

稳定一级入口 key 与默认隐藏矩阵（与权限推导一致）由本模块定义；管理页可覆盖。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from sqlalchemy import text
from ..db import get_engine, get_tenant, DEFAULT_TENANT

logger = logging.getLogger(__name__)

# 稳定一级入口 key（与前端 menuConfig.js 的 key 保持一致）
NAV_ENTRIES: tuple[str, ...] = ("workbench", "project", "capability", "admin")

# 默认隐藏矩阵：role -> 默认隐藏的 entry_key 集合。
# 与权限推导一致：admin 入口仅对系统管理员可见；其余入口对全部角色可见，
# 由权限下限再做细粒度裁剪。管理页可覆盖。
DEFAULT_HIDDEN: dict[str, set[str]] = {
    "admin": set(),
    "pm": {"admin"},
    "researcher": {"admin"},
    "reviewer": {"admin"},
    "viewer": {"admin"},
    "data_engineer": {"admin"},
}


class NavVisibilityRow(BaseModel):
    role: str = ""
    entry_key: str = ""
    visible: bool = True
    updated_by: str = ""
    tenant_id: str = ""


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class NavVisibilityStore:
    """PostgreSQL 持久化导航可见性存储（仿 UserStore）。"""

    def __init__(self):
        self.engine = get_engine()
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        """幂等写入与权限推导一致的默认隐藏矩阵。

        ON CONFLICT DO NOTHING：已有行不覆盖，保证管理页的自定义不被重放。
        """
        tenant = get_tenant() or DEFAULT_TENANT
        try:
            with self.engine.begin() as conn:
                for role, hidden in DEFAULT_HIDDEN.items():
                    for entry in NAV_ENTRIES:
                        conn.execute(
                            text(
                                """INSERT INTO auth.nav_visibility
                                   (tenant_id, role, entry_key, visible)
                                   VALUES (:tenant_id, :role, :entry_key, :visible)
                                   ON CONFLICT (tenant_id, role, entry_key) DO NOTHING"""
                            ),
                            {
                                "tenant_id": tenant,
                                "role": role,
                                "entry_key": entry,
                                "visible": entry not in hidden,
                            },
                        )
        except Exception:
            # 表未就绪（迁移未跑）时不阻塞启动，路由层会再兜底
            logger.warning("nav_visibility 默认矩阵 seed 失败（表可能未初始化）", exc_info=True)

    def list_all(self) -> list[NavVisibilityRow]:
        """返回当前租户全部覆盖行。"""
        tenant = get_tenant() or DEFAULT_TENANT
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT role, entry_key, visible, updated_by, tenant_id
                       FROM auth.nav_visibility WHERE tenant_id=:tenant_id
                       ORDER BY role, entry_key"""
                ),
                {"tenant_id": tenant},
            ).fetchall()
        result: list[NavVisibilityRow] = []
        for r in rows:
            m = r._mapping
            result.append(
                NavVisibilityRow(
                    role=m["role"],
                    entry_key=m["entry_key"],
                    visible=bool(m["visible"]),
                    updated_by=m.get("updated_by") or "",
                    tenant_id=m.get("tenant_id") or tenant,
                )
            )
        return result

    def role_matrix(self, role: str) -> dict[str, bool]:
        """返回指定角色在当前租户下的 entry_key -> visible 映射（含默认值）。"""
        rows = {r.entry_key: r.visible for r in self.list_all() if r.role == role}
        return {e: rows.get(e, True) for e in NAV_ENTRIES}

    def visible_entries(self, role: str) -> list[str]:
        """返回指定角色可见的入口 key 列表（按 NAV_ENTRIES 顺序）。"""
        matrix = self.role_matrix(role)
        return [e for e in NAV_ENTRIES if matrix.get(e, True)]

    def upsert_batch(self, updates: dict[str, dict[str, bool]], updated_by: str = "") -> None:
        """批量 upsert 覆盖行。updates: {role: {entry_key: visible}}。

        仅写入合法 entry_key；非法 key 忽略。调用方负责审计 before/after。
        """
        tenant = get_tenant() or DEFAULT_TENANT
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            for role, entries in updates.items():
                for entry_key, visible in (entries or {}).items():
                    if entry_key not in NAV_ENTRIES:
                        logger.warning("忽略非法导航入口 key: %s", entry_key)
                        continue
                    conn.execute(
                        text(
                            """INSERT INTO auth.nav_visibility
                               (tenant_id, role, entry_key, visible, updated_by, updated_at)
                               VALUES (:tenant_id, :role, :entry_key, :visible, :updated_by, :updated_at)
                               ON CONFLICT (tenant_id, role, entry_key) DO UPDATE SET
                                   visible=EXCLUDED.visible,
                                   updated_by=EXCLUDED.updated_by,
                                   updated_at=EXCLUDED.updated_at"""
                        ),
                        {
                            "tenant_id": tenant,
                            "role": role,
                            "entry_key": entry_key,
                            "visible": bool(visible),
                            "updated_by": updated_by,
                            "updated_at": now,
                        },
                    )