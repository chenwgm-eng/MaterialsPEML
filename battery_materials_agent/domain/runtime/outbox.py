"""事务 Outbox — 科学执行内核的可靠消息队列。"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import text

from ...db import get_engine

logger = logging.getLogger(__name__)


class OutboxMessage(BaseModel):
    """Outbox 消息。"""

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    subject_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"  # pending | sending | sent | failed
    retry_count: int = 0
    max_retries: int = 5
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: datetime | None = None


class ScientificOutbox:
    """科学执行内核的事务 Outbox。"""

    def __init__(self):
        self.engine = get_engine()

    def enqueue(
        self,
        event_type: str,
        subject_id: str,
        payload: dict[str, Any],
        max_retries: int = 5,
    ) -> OutboxMessage:
        """入队一条消息。"""
        msg = OutboxMessage(
            message_id=str(uuid4()),
            event_type=event_type,
            subject_id=subject_id,
            payload=payload,
            max_retries=max_retries,
        )
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO scientific_kernel.outbox
                       (message_id, event_type, subject_id, payload_json, status,
                        retry_count, max_retries, last_error, created_at, sent_at)
                       VALUES (:message_id, :event_type, :subject_id,
                               CAST(:payload_json AS JSONB), :status,
                               :retry_count, :max_retries, :last_error,
                               :created_at, :sent_at)"""
                ),
                {
                    "message_id": msg.message_id,
                    "event_type": msg.event_type,
                    "subject_id": msg.subject_id,
                    "payload_json": json.dumps(msg.payload),
                    "status": msg.status,
                    "retry_count": msg.retry_count,
                    "max_retries": msg.max_retries,
                    "last_error": msg.last_error,
                    "created_at": msg.created_at.isoformat(),
                    "sent_at": None,
                },
            )
        return msg

    def claim_pending(self, limit: int = 10) -> list[OutboxMessage]:
        """原子性地领取待发送消息。"""
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """SELECT message_id, event_type, subject_id, payload_json,
                              status, retry_count, max_retries, last_error, created_at, sent_at
                       FROM scientific_kernel.outbox
                       WHERE status = 'pending'
                       ORDER BY created_at ASC
                       LIMIT :limit
                       FOR UPDATE SKIP LOCKED"""
                ),
                {"limit": limit},
            ).fetchall()
            msg_ids = [r[0] for r in rows]
            if msg_ids:
                for mid in msg_ids:
                    conn.execute(
                        text(
                            "UPDATE scientific_kernel.outbox SET status = 'sending' "
                            "WHERE message_id = :mid AND status = 'pending'"
                        ),
                        {"mid": mid},
                    )
        return [self._row_to_message(r) for r in rows]

    def mark_sent(self, message_id: str) -> None:
        """标记消息为已发送。"""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE scientific_kernel.outbox SET status = 'sent', sent_at = :sent_at "
                    "WHERE message_id = :message_id"
                ),
                {"sent_at": datetime.now(timezone.utc).isoformat(), "message_id": message_id},
            )

    def mark_failed(self, message_id: str, error: str) -> None:
        """标记消息为失败；未达最大重试次数时重置回 pending 以便重试。"""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE scientific_kernel.outbox "
                    "SET retry_count = retry_count + 1, last_error = :error "
                    "WHERE message_id = :message_id"
                ),
                {"error": error, "message_id": message_id},
            )
            row = conn.execute(
                text(
                    "SELECT retry_count, max_retries FROM scientific_kernel.outbox "
                    "WHERE message_id = :mid"
                ),
                {"mid": message_id},
            ).fetchone()
            if row and row[0] >= row[1]:
                conn.execute(
                    text(
                        "UPDATE scientific_kernel.outbox SET status = 'failed' "
                        "WHERE message_id = :mid"
                    ),
                    {"mid": message_id},
                )
            else:
                # 未达最大重试次数：重置为 pending，允许再次被领取重试
                conn.execute(
                    text(
                        "UPDATE scientific_kernel.outbox SET status = 'pending' "
                        "WHERE message_id = :mid"
                    ),
                    {"mid": message_id},
                )

    @staticmethod
    def _row_to_message(row) -> OutboxMessage:
        payload = row[3]
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        return OutboxMessage(
            message_id=row[0],
            event_type=row[1],
            subject_id=row[2],
            payload=payload,
            status=row[4],
            retry_count=row[5],
            max_retries=row[6],
            last_error=row[7],
            created_at=row[8] if isinstance(row[8], datetime) else datetime.fromisoformat(row[8]),
            sent_at=row[9] if isinstance(row[9], datetime) else (datetime.fromisoformat(row[9]) if row[9] else None),
        )