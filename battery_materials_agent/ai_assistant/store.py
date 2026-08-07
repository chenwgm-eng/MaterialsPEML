"""AiSessionStore — AI 助手会话与消息持久化（SQLAlchemy Engine）。

Schema 由 alembic 管理（scientific_kernel.ai_sessions / ai_messages）。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from ..db import get_engine


def _parse_json_field(value: Any, default: Any) -> Any:
    """解析 JSON 字段，兼容 psycopg3 自动反序列化或返回原始字符串两种情况。"""
    if value is None:
        return default
    if isinstance(value, str):
        if not value:
            return default
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AiSessionStore:
    """AI 助手会话/消息的 SQLAlchemy 持久化（user_id 隔离 + project_id 隔离）。"""

    def __init__(self, db_path: str | None = None):
        # db_path 已废弃：统一通过 get_engine() 获取 Engine。
        self.engine = get_engine()

    # ── 会话 CRUD ───────────────────────────────────────────

    def create_session(
        self,
        user_id: str,
        project_id: str = "",
        title: str = "新会话",
        mode: str = "global",
        focus: dict | None = None,
        context: dict | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """创建会话，返回会话字典。"""
        session_id = f"ai-{uuid.uuid4().hex[:16]}"
        now = _now()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO scientific_kernel.ai_sessions
                       (session_id, user_id, project_id, title, mode, focus_json,
                        status, context_json, metadata_json, created_at, updated_at)
                       VALUES (:session_id, :user_id, :project_id, :title, :mode, :focus_json,
                               'active', :context_json, :metadata_json, :created_at, :updated_at)"""
                ),
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "project_id": project_id or "",
                    "title": title or "新会话",
                    "mode": mode or "global",
                    "focus_json": json.dumps(focus or {}, ensure_ascii=False),
                    "context_json": json.dumps(context or {}, ensure_ascii=False),
                    "metadata_json": json.dumps(metadata or {}, ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM scientific_kernel.ai_sessions "
                    "WHERE session_id = :session_id"
                ),
                {"session_id": session_id},
            ).mappings().first()
        if row is None:
            return None
        return self._row_to_session(row)

    def list_sessions(self, user_id: str, project_id: str = "", limit: int = 50) -> list[dict]:
        """按用户隔离查询会话列表；project_id 非空时再做项目隔离。"""
        query = "SELECT * FROM scientific_kernel.ai_sessions WHERE user_id = :user_id"
        params: dict[str, Any] = {"user_id": user_id}
        if project_id:
            query += " AND project_id = :project_id"
            params["project_id"] = project_id
        query += " ORDER BY updated_at DESC LIMIT :limit"
        params["limit"] = limit
        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).mappings().all()
        return [self._row_to_session(row) for row in rows]

    def touch_session(self, session_id: str, title: str | None = None) -> None:
        """更新会话 updated_at（可选刷新标题）。"""
        now = _now()
        params: dict[str, Any] = {"updated_at": now, "session_id": session_id}
        query = "UPDATE scientific_kernel.ai_sessions SET updated_at = :updated_at"
        if title is not None and title.strip():
            query += ", title = :title"
            params["title"] = title.strip()[:80]
        query += " WHERE session_id = :session_id"
        with self.engine.begin() as conn:
            conn.execute(text(query), params)

    def delete_session(self, session_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM scientific_kernel.ai_messages WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
            conn.execute(
                text("DELETE FROM scientific_kernel.ai_sessions WHERE session_id = :session_id"),
                {"session_id": session_id},
            )

    # ── 消息 CRUD ───────────────────────────────────────────

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        provider: str = "",
        model: str = "",
        status: str = "done",
        meta: dict | None = None,
    ) -> dict:
        """插入一条消息，并刷新会话 updated_at。返回消息字典。"""
        message_id = f"aim-{uuid.uuid4().hex[:16]}"
        now = _now()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO scientific_kernel.ai_messages
                       (message_id, session_id, role, content, provider, model, status, meta_json, created_at)
                       VALUES (:message_id, :session_id, :role, :content, :provider, :model, :status, :meta_json, :created_at)"""
                ),
                {
                    "message_id": message_id,
                    "session_id": session_id,
                    "role": role,
                    "content": content,
                    "provider": provider,
                    "model": model,
                    "status": status,
                    "meta_json": json.dumps(meta or {}, ensure_ascii=False),
                    "created_at": now,
                },
            )
            conn.execute(
                text(
                    "UPDATE scientific_kernel.ai_sessions SET updated_at = :updated_at "
                    "WHERE session_id = :session_id"
                ),
                {"updated_at": now, "session_id": session_id},
            )
        return self.get_message(message_id)

    def get_message(self, message_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM scientific_kernel.ai_messages WHERE message_id = :message_id"
                ),
                {"message_id": message_id},
            ).mappings().first()
        if row is None:
            return None
        return self._row_to_message(row)

    def list_messages(self, session_id: str, limit: int = 200) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM scientific_kernel.ai_messages "
                    "WHERE session_id = :session_id ORDER BY created_at ASC LIMIT :limit"
                ),
                {"session_id": session_id, "limit": limit},
            ).mappings().all()
        return [self._row_to_message(row) for row in rows]

    def update_message_feedback(self, message_id: str, value: int) -> None:
        """持久化单条消息的用户反馈（-1 / 0 / 1）到 meta_json。

        反馈是真实信任信号，必须入库而非仅存前端内存，否则刷新后丢失且无意义。
        """
        msg = self.get_message(message_id)
        if msg is None:
            raise KeyError(f"消息不存在: {message_id}")
        meta = {**(msg.get("meta") or {}), "_fb": value}
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE scientific_kernel.ai_messages SET meta_json = :meta_json "
                    "WHERE message_id = :message_id"
                ),
                {"meta_json": json.dumps(meta, ensure_ascii=False), "message_id": message_id},
            )

    def update_message_status(self, message_id: str, status: str, content: str | None = None) -> None:
        """更新消息状态；流式完成时回填全文 content。"""
        params: dict[str, Any] = {"status": status, "message_id": message_id}
        query = "UPDATE scientific_kernel.ai_messages SET status = :status"
        if content is not None:
            query += ", content = :content"
            params["content"] = content
        query += " WHERE message_id = :message_id"
        with self.engine.begin() as conn:
            conn.execute(text(query), params)

    # ── helpers ─────────────────────────────────────────────

    @staticmethod
    def _row_to_session(row) -> dict:
        return {
            "session_id": row["session_id"],
            "user_id": row["user_id"],
            "project_id": row["project_id"] or "",
            "title": row["title"],
            "mode": row["mode"],
            "focus": _parse_json_field(row["focus_json"], {}) or {},
            "status": row["status"],
            "context": _parse_json_field(row["context_json"], {}) or {},
            "metadata": _parse_json_field(row["metadata_json"], {}) or {},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _row_to_message(row) -> dict:
        return {
            "message_id": row["message_id"],
            "session_id": row["session_id"],
            "role": row["role"],
            "content": row["content"],
            "provider": row["provider"],
            "model": row["model"],
            "status": row["status"],
            "meta": _parse_json_field(row["meta_json"], {}) or {},
            "created_at": row["created_at"],
        }