"""审计日志 - 记录 AI 建议、人工修改、最终决策。

合规级审计：
- 全链路事务埋点：认证、权限拒绝、关键数据变更（候选状态迁移、审批、删除）
- 字段：operator / user_id / ip / resource_type / resource_id / before / after
- 多租户隔离：每条审计记录带 tenant_id，查询按当前租户过滤
- DB 层追加防篡改：由 alembic 迁移创建 RULE，禁止 UPDATE/DELETE
- 独立归档：超期记录可归档至 audit.audit_archive（见 A4）
"""

from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy import text
from .db import get_engine, get_tenant, tenant_filter


def _iso(value) -> str:
    """将 datetime 或字符串转换为 ISO 字符串；None 返回空字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class AuditEntry(BaseModel):
    entry_id: str = ""
    event_type: str = ""  # ai_suggestion / human_edit / decision / agent_action / auth / permission_denied / data_change
    module: str = ""  # ecml / orchestration / prediction / synthesis / auth / candidate / report
    action: str = ""
    detail: dict = Field(default_factory=dict)
    operator: str = "system"
    user_id: str = ""
    ip: str = ""
    resource_type: str = ""  # candidate / project / experiment / report / user
    resource_id: str = ""
    before: dict = Field(default_factory=dict)  # 变更前快照
    after: dict = Field(default_factory=dict)  # 变更后快照
    confirmed: bool = False
    tenant_id: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AuditLogger:
    def __init__(self):
        self.engine = get_engine()

    def log(self, entry: AuditEntry):
        if not entry.entry_id:
            entry.entry_id = uuid.uuid4().hex[:12]
        if not entry.tenant_id:
            entry.tenant_id = get_tenant()
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO audit.audit_log
                (entry_id, event_type, module, action, detail, operator, confirmed,
                 created_at, tenant_id, user_id, ip, resource_type, resource_id,
                 before, after)
                VALUES (:entry_id, :event_type, :module, :action,
                        CAST(:detail AS JSONB), :operator, :confirmed, :created_at,
                        :tenant_id, :user_id, :ip, :resource_type, :resource_id,
                        CAST(:before AS JSONB), CAST(:after AS JSONB))"""),
                {
                    "entry_id": entry.entry_id,
                    "event_type": entry.event_type,
                    "module": entry.module,
                    "action": entry.action,
                    "detail": json.dumps(entry.detail, ensure_ascii=False),
                    "operator": entry.operator,
                    "confirmed": entry.confirmed,
                    "created_at": entry.created_at,
                    "tenant_id": entry.tenant_id,
                    "user_id": entry.user_id,
                    "ip": entry.ip,
                    "resource_type": entry.resource_type,
                    "resource_id": entry.resource_id,
                    "before": json.dumps(entry.before, ensure_ascii=False),
                    "after": json.dumps(entry.after, ensure_ascii=False),
                },
            )

    def query(self, module: str | None = None, limit: int = 50) -> list[AuditEntry]:
        """向后兼容查询：仅按模块过滤，按当前租户隔离。"""
        with self.engine.connect() as conn:
            if module:
                rows = conn.execute(
                    text("SELECT * FROM audit.audit_log "
                         f"WHERE module=:module AND {tenant_filter()}"
                         " ORDER BY created_at DESC LIMIT :limit"),
                    {"module": module, "tenant_id": get_tenant(), "limit": limit},
                ).fetchall()
            else:
                rows = conn.execute(
                    text("SELECT * FROM audit.audit_log "
                         f"WHERE {tenant_filter()} "
                         "ORDER BY created_at DESC LIMIT :limit"),
                    {"tenant_id": get_tenant(), "limit": limit},
                ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def query_by_detail(self, module: str, key: str, value: str, limit: int = 50) -> list[AuditEntry]:
        """查询指定模块且 detail JSON 中 key=value 的审计日志。"""
        filter_json = json.dumps({key: value})
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM audit.audit_log "
                     f"WHERE module=:module AND detail @> CAST(:filter AS JSONB) AND {tenant_filter()} "
                     "ORDER BY created_at DESC LIMIT :limit"),
                {"module": module, "filter": filter_json, "tenant_id": get_tenant(), "limit": limit},
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def query_paged(
        self,
        module: str | None = None,
        action: str | None = None,
        operator: str | None = None,
        event_type: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """多条件分页查询（A4）。返回 ``{items, total, page, page_size}``。

        所有过滤条件可选，组合使用 AND 关系；始终按当前租户隔离。
        """
        conditions = [tenant_filter()]
        params: dict[str, Any] = {"tenant_id": get_tenant()}
        if module:
            conditions.append("module = :module")
            params["module"] = module
        if action:
            conditions.append("action = :action")
            params["action"] = action
        if operator:
            conditions.append("operator = :operator")
            params["operator"] = operator
        if event_type:
            conditions.append("event_type = :event_type")
            params["event_type"] = event_type
        if resource_type:
            conditions.append("resource_type = :resource_type")
            params["resource_type"] = resource_type
        if resource_id:
            conditions.append("resource_id = :resource_id")
            params["resource_id"] = resource_id
        if start_at:
            conditions.append("created_at >= :start_at")
            params["start_at"] = start_at
        if end_at:
            conditions.append("created_at <= :end_at")
            params["end_at"] = end_at
        where = " WHERE " + " AND ".join(conditions)
        page = max(1, page)
        page_size = max(1, min(200, page_size))
        offset = (page - 1) * page_size
        params["limit"] = page_size
        params["offset"] = offset

        with self.engine.connect() as conn:
            total = conn.execute(
                text(f"SELECT COUNT(*) FROM audit.audit_log{where}"), params
            ).scalar()
            rows = conn.execute(
                text(f"SELECT * FROM audit.audit_log{where} "
                     "ORDER BY created_at DESC LIMIT :limit OFFSET :offset"),
                params,
            ).fetchall()
        return {
            "items": [self._row_to_entry(r).model_dump() for r in rows],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    def archive(self, before_at: str) -> int:
        """将早于 before_at 的审计记录归档至 audit.audit_archive（A4）。

        仅归档当前租户的记录。归档后从主表删除。
        注意：主表有 DB 层追加防篡改 RULE（禁止 DELETE），归档是唯一受信任的
        瘦身通道，故此处临时禁用 DELETE 规则，仅作用于本事务。
        """
        with self.engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE audit.audit_log DISABLE RULE audit_log_no_delete"
            ))
            try:
                conn.execute(
                    text("""INSERT INTO audit.audit_archive
                            SELECT * FROM audit.audit_log
                            WHERE created_at < :before_at AND :before_at IS NOT NULL
                              AND tenant_id = :tenant_id
                            ON CONFLICT (entry_id) DO NOTHING"""),
                    {"before_at": before_at, "tenant_id": get_tenant()},
                )
                cur = conn.execute(
                    text("DELETE FROM audit.audit_log "
                         f"WHERE created_at < :before_at AND {tenant_filter()}"),
                    {"before_at": before_at, "tenant_id": get_tenant()},
                )
                return cur.rowcount or 0
            finally:
                conn.execute(text(
                    "ALTER TABLE audit.audit_log ENABLE RULE audit_log_no_delete"
                ))

    _COLUMN_ORDER = (
        "entry_id", "event_type", "module", "action", "detail", "operator",
        "confirmed", "created_at", "tenant_id", "user_id", "ip",
        "resource_type", "resource_id", "before", "after",
    )

    def _row_to_entry(self, r) -> AuditEntry:
        m = dict(r._mapping)
        return AuditEntry(
            entry_id=m.get("entry_id") or "",
            event_type=m.get("event_type") or "",
            module=m.get("module") or "",
            action=m.get("action") or "",
            detail=m.get("detail") or {},
            operator=m.get("operator") or "system",
            confirmed=bool(m.get("confirmed")),
            created_at=_iso(m.get("created_at")),
            tenant_id=m.get("tenant_id") or "",
            user_id=m.get("user_id") or "",
            ip=m.get("ip") or "",
            resource_type=m.get("resource_type") or "",
            resource_id=m.get("resource_id") or "",
            before=m.get("before") or {},
            after=m.get("after") or {},
        )


# 全局单例
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger