"""审计日志 - 记录 AI 建议、人工修改、最终决策。"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from sqlalchemy import text
from .db import get_engine


def _iso(value) -> str:
    """将 datetime 或字符串转换为 ISO 字符串；None 返回空字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class AuditEntry(BaseModel):
    entry_id: str = ""
    event_type: str = ""  # ai_suggestion / human_edit / decision / agent_action
    module: str = ""  # ecml / orchestration / prediction / synthesis
    action: str = ""
    detail: dict = Field(default_factory=dict)
    operator: str = "system"
    confirmed: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AuditLogger:
    def __init__(self):
        self.engine = get_engine()

    def log(self, entry: AuditEntry):
        import uuid
        if not entry.entry_id:
            entry.entry_id = uuid.uuid4().hex[:12]
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO audit.audit_log
                (entry_id, event_type, module, action, detail, operator, confirmed, created_at)
                VALUES (:entry_id, :event_type, :module, :action,
                        CAST(:detail AS JSONB), :operator, :confirmed, :created_at)"""),
                {
                    "entry_id": entry.entry_id,
                    "event_type": entry.event_type,
                    "module": entry.module,
                    "action": entry.action,
                    "detail": json.dumps(entry.detail),
                    "operator": entry.operator,
                    "confirmed": entry.confirmed,
                    "created_at": entry.created_at,
                },
            )

    def query(self, module: str | None = None, limit: int = 50) -> list[AuditEntry]:
        with self.engine.connect() as conn:
            if module:
                rows = conn.execute(
                    text("SELECT * FROM audit.audit_log WHERE module=:module "
                         "ORDER BY created_at DESC LIMIT :limit"),
                    {"module": module, "limit": limit},
                ).fetchall()
            else:
                rows = conn.execute(
                    text("SELECT * FROM audit.audit_log ORDER BY created_at DESC LIMIT :limit"),
                    {"limit": limit},
                ).fetchall()
        return [AuditEntry(
            entry_id=r[0], event_type=r[1], module=r[2], action=r[3],
            detail=r[4] or {}, operator=r[5], confirmed=bool(r[6]),
            created_at=_iso(r[7]),
        ) for r in rows]

    def query_by_detail(self, module: str, key: str, value: str, limit: int = 50) -> list[AuditEntry]:
        """查询指定模块且 detail JSON 中 key=value 的审计日志。"""
        filter_json = json.dumps({key: value})
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM audit.audit_log "
                     "WHERE module=:module AND detail @> CAST(:filter AS JSONB) "
                     "ORDER BY created_at DESC LIMIT :limit"),
                {"module": module, "filter": filter_json, "limit": limit},
            ).fetchall()
        return [AuditEntry(
            entry_id=r[0], event_type=r[1], module=r[2], action=r[3],
            detail=r[4] or {}, operator=r[5], confirmed=bool(r[6]),
            created_at=_iso(r[7]),
        ) for r in rows]


# 全局单例
_audit_logger: AuditLogger | None = None

def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
