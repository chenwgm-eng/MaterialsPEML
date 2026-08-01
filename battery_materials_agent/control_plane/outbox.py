"""Transactional outbox for the Agent Control Plane.

Durable message queue for external side-effects (DFT jobs, experiments, SCP
calls, MCP tool invocations). Supports idempotent enqueue, retry tracking,
and run-scoped cancellation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import text

from ..db import get_engine

TargetType = Literal["dft", "experiment", "scp", "mcp"]
OutboxStatus = Literal["pending", "sending", "sent", "failed", "cancelled"]


def _to_datetime(value):
    """兼容 psycopg3 返回的 datetime 对象或 ISO 字符串。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


class OutboxMessage(BaseModel):
    """A single message in the transactional outbox."""

    message_id: str
    run_id: str | None = None
    target_type: TargetType
    target_endpoint: str
    payload: dict = Field(default_factory=dict)
    idempotency_key: str | None = None
    status: OutboxStatus = "pending"
    retry_count: int = 0
    max_retries: int = 5
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: datetime | None = None


class Outbox:
    """Transactional outbox with idempotent enqueue and retry tracking.

    PostgreSQL via SQLAlchemy Engine；schema 由 alembic 管理
    （control_plane.outbox_messages）。
    """

    def __init__(self, db_path: str = "data/control_plane.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.db_path = db_path
        self.engine = get_engine()

    def _init_db(self) -> None:  # pragma: no cover - 兼容旧调用
        """No-op：表结构由 alembic 管理。"""
        return

    # ── public API ─────────────────────────────────────────

    def enqueue(
        self,
        run_id: str | None,
        target_type: TargetType,
        target_endpoint: str,
        payload: dict,
        idempotency_key: str | None = None,
        max_retries: int = 5,
    ) -> OutboxMessage:
        """Add a message to the outbox.

        If ``idempotency_key`` is provided and a message with that key already
        exists, the existing message is returned instead of creating a
        duplicate. Idempotency is enforced atomically via the UNIQUE constraint
        on ``idempotency_key``: on conflict, the existing message is re-queried
        and returned.
        """
        message = OutboxMessage(
            message_id=str(uuid4()),
            run_id=run_id,
            target_type=target_type,
            target_endpoint=target_endpoint,
            payload=payload,
            idempotency_key=idempotency_key,
            max_retries=max_retries,
        )
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        """INSERT INTO control_plane.outbox_messages
                           (message_id, run_id, target_type, target_endpoint,
                            payload_json, idempotency_key, status, retry_count,
                            max_retries, last_error, created_at, sent_at)
                           VALUES (:message_id, :run_id, :target_type, :target_endpoint,
                                   CAST(:payload_json AS JSONB), :idempotency_key, :status,
                                   :retry_count, :max_retries, :last_error,
                                   :created_at, :sent_at)"""
                    ),
                    {
                        "message_id": message.message_id,
                        "run_id": message.run_id,
                        "target_type": message.target_type,
                        "target_endpoint": message.target_endpoint,
                        "payload_json": json.dumps(message.payload),
                        "idempotency_key": message.idempotency_key,
                        "status": message.status,
                        "retry_count": message.retry_count,
                        "max_retries": message.max_retries,
                        "last_error": message.last_error,
                        "created_at": message.created_at.isoformat(),
                        "sent_at": message.sent_at.isoformat() if message.sent_at else None,
                    },
                )
        except Exception:
            # UNIQUE constraint violation on idempotency_key — re-query
            if idempotency_key is None:
                raise
            existing = self.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing
            raise
        return message

    def get_pending(self, limit: int = 10) -> list[OutboxMessage]:
        """Get pending messages, oldest first.

        Note: this is a non-claiming read. Use ``claim_pending`` for
        concurrent workers that need to atomically reserve messages.
        """
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT message_id, run_id, target_type, target_endpoint,
                              payload_json, idempotency_key, status, retry_count,
                              max_retries, last_error, created_at, sent_at
                       FROM control_plane.outbox_messages
                       WHERE status = 'pending'
                       ORDER BY created_at ASC
                       LIMIT :limit"""
                ),
                {"limit": limit},
            ).fetchall()
        return [self._row_to_message(row) for row in rows]

    def claim_pending(self, limit: int = 10) -> list[OutboxMessage]:
        """Atomically claim pending messages for processing.

        Selected messages are transitioned from ``pending`` to ``sending``
        within the same transaction so that concurrent workers do not pick
        up the same messages. Returns the claimed messages (in ``sending``
        status), oldest first.
        """
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """SELECT message_id, run_id, target_type, target_endpoint,
                              payload_json, idempotency_key, status, retry_count,
                              max_retries, last_error, created_at, sent_at
                       FROM control_plane.outbox_messages
                       WHERE status = 'pending'
                       ORDER BY created_at ASC
                       LIMIT :limit"""
                ),
                {"limit": limit},
            ).fetchall()
            msg_ids = [row[0] for row in rows]
            if msg_ids:
                # 逐行 UPDATE 以兼容 psycopg3 的 IN 列表参数
                for mid in msg_ids:
                    conn.execute(
                        text(
                            """UPDATE control_plane.outbox_messages
                               SET status = 'sending'
                               WHERE message_id = :mid AND status = 'pending'"""
                        ),
                        {"mid": mid},
                    )
        messages = [self._row_to_message(row) for row in rows]
        for msg in messages:
            msg.status = "sending"
        return messages

    def mark_sent(self, message_id: str) -> None:
        """Mark a message as successfully sent."""
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE control_plane.outbox_messages
                       SET status = 'sent', sent_at = :sent_at
                       WHERE message_id = :message_id"""
                ),
                {"sent_at": now, "message_id": message_id},
            )

    def mark_failed(self, message_id: str, error: str) -> None:
        """Mark a message as failed and increment retry count.

        The retry count is incremented atomically via
        ``retry_count = retry_count + 1``. If ``retry_count`` reaches
        ``max_retries``, the status is set to ``failed``; otherwise the status
        is left unchanged for another retry.
        """
        with self.engine.begin() as conn:
            cursor = conn.execute(
                text(
                    """UPDATE control_plane.outbox_messages
                       SET retry_count = retry_count + 1, last_error = :error
                       WHERE message_id = :message_id"""
                ),
                {"error": error, "message_id": message_id},
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Outbox message {message_id!r} not found")
            row = conn.execute(
                text(
                    "SELECT retry_count, max_retries FROM control_plane.outbox_messages WHERE message_id = :mid"
                ),
                {"mid": message_id},
            ).fetchone()
            if row is not None and row[0] >= row[1]:
                conn.execute(
                    text(
                        "UPDATE control_plane.outbox_messages SET status = 'failed' WHERE message_id = :mid"
                    ),
                    {"mid": message_id},
                )

    def cancel(self, run_id: str) -> None:
        """Cancel all pending messages for a run.

        Only ``pending`` messages are cancelled; already-sent or failed
        messages are left as-is.
        """
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE control_plane.outbox_messages
                       SET status = 'cancelled'
                       WHERE run_id = :run_id AND status = 'pending'"""
                ),
                {"run_id": run_id},
            )

    def get_by_idempotency_key(self, key: str) -> OutboxMessage | None:
        """Check if a message with this idempotency key already exists."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT message_id, run_id, target_type, target_endpoint,
                              payload_json, idempotency_key, status, retry_count,
                              max_retries, last_error, created_at, sent_at
                       FROM control_plane.outbox_messages WHERE idempotency_key = :key"""
                ),
                {"key": key},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_message(row)

    # ── internals ──────────────────────────────────────────

    @staticmethod
    def _row_to_message(row) -> OutboxMessage:
        payload = row[4]
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        return OutboxMessage(
            message_id=row[0],
            run_id=row[1],
            target_type=row[2],
            target_endpoint=row[3],
            payload=payload,
            idempotency_key=row[5],
            status=row[6],
            retry_count=row[7],
            max_retries=row[8],
            last_error=row[9],
            created_at=_to_datetime(row[10]),
            sent_at=_to_datetime(row[11]) if row[11] else None,
        )
