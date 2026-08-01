"""Observability service for trace events and metrics aggregation.

Records structured trace events (tool invocations, policy decisions, committee
events, state transitions, budget events) keyed by correlation_id and run_id,
and aggregates them into summary metrics. Sensitive fields are redacted before
display.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import text

from ..db import get_engine


EventType = Literal[
    "tool_invoke",
    "policy_decision",
    "committee_event",
    "state_transition",
    "budget_event",
]

# Keys whose values should be redacted from display and storage.
_SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|token|secret|password|credential|authorization|"
    r"internal[_-]?reasoning|auth[_-]?secret[_-]?ref|payload|prompt|"
    r"response|content|provenance)",
    re.IGNORECASE,
)

# Pattern for redacting "sensitive_key (=|:) value" in free text such as
# event summaries. Group 1 captures the key, group 2 the separator.
_SENSITIVE_KV_RE = re.compile(
    r"(api[_-]?key|token|secret|password|credential|authorization|"
    r"internal[_-]?reasoning|auth[_-]?secret[_-]?ref|payload|prompt|"
    r"response|content|provenance)(\s*[:=]\s*)[^\s,;}\]]+",
    re.IGNORECASE,
)


class TraceEvent(BaseModel):
    """A single observability event in a distributed trace."""

    event_id: str
    correlation_id: str
    trace_id: str | None = None
    run_id: str | None = None
    event_type: EventType
    entity_type: str | None = None
    entity_id: str | None = None
    summary: str | None = None
    details: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _parse_json_field(value, default):
    """解析 JSON 字段，兼容 psycopg3 自动反序列化或字符串两种来源。"""
    if value is None:
        return default
    if isinstance(value, str):
        if not value:
            return default
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
    return value


def _to_datetime(value):
    """兼容 psycopg3 返回的 datetime 对象或 ISO 字符串。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


class ObservabilityService:
    """PostgreSQL-backed trace event store with metrics aggregation.

    使用 SQLAlchemy Engine；schema 由 alembic 管理
    （control_plane.trace_events）。
    """

    def __init__(self, db_path: str = "data/control_plane.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.db_path = db_path
        self.engine = get_engine()

    def _init_db(self) -> None:  # pragma: no cover - 兼容旧调用
        """No-op：表结构由 alembic 管理。"""
        return

    # ── logging ────────────────────────────────────────────

    def log_event(self, event: TraceEvent) -> TraceEvent:
        """Log a trace event (upsert by event_id).

        Sensitive data in ``details`` and ``summary`` is redacted before
        persistence (storage-layer sanitization) so that secrets never
        reach the database.
        """
        sanitized_details = self._sanitize_dict(event.details)
        sanitized_summary = self._sanitize_text(event.summary)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO control_plane.trace_events
                       (event_id, correlation_id, trace_id, run_id, event_type,
                        entity_type, entity_id, summary, details_json, timestamp)
                       VALUES (:event_id, :correlation_id, :trace_id, :run_id, :event_type,
                               :entity_type, :entity_id, :summary,
                               CAST(:details_json AS JSONB), :timestamp)
                       ON CONFLICT (event_id) DO UPDATE SET
                         correlation_id = EXCLUDED.correlation_id,
                         trace_id = EXCLUDED.trace_id,
                         run_id = EXCLUDED.run_id,
                         event_type = EXCLUDED.event_type,
                         entity_type = EXCLUDED.entity_type,
                         entity_id = EXCLUDED.entity_id,
                         summary = EXCLUDED.summary,
                         details_json = EXCLUDED.details_json,
                         timestamp = EXCLUDED.timestamp"""
                ),
                {
                    "event_id": event.event_id,
                    "correlation_id": event.correlation_id,
                    "trace_id": event.trace_id,
                    "run_id": event.run_id,
                    "event_type": event.event_type,
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "summary": sanitized_summary,
                    "details_json": json.dumps(sanitized_details, default=str),
                    "timestamp": event.timestamp.isoformat(),
                },
            )
        return event

    # ── queries ────────────────────────────────────────────

    def get_trace(self, correlation_id: str) -> list[TraceEvent]:
        """Get all events for a correlation_id, ordered by timestamp."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT event_id, correlation_id, trace_id, run_id, event_type,
                              entity_type, entity_id, summary, details_json, timestamp
                       FROM control_plane.trace_events
                       WHERE correlation_id = :correlation_id
                       ORDER BY timestamp ASC"""
                ),
                {"correlation_id": correlation_id},
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def get_run_events(self, run_id: str) -> list[TraceEvent]:
        """Get all events for a run_id, ordered by timestamp."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT event_id, correlation_id, trace_id, run_id, event_type,
                              entity_type, entity_id, summary, details_json, timestamp
                       FROM control_plane.trace_events
                       WHERE run_id = :run_id
                       ORDER BY timestamp ASC"""
                ),
                {"run_id": run_id},
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def get_metrics_summary(
        self,
        project_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """Aggregate metrics over a filtered set of trace events.

        Returns a dict with:
          - ``total_events``: count of all matching events.
          - ``event_counts_by_type``: count per event_type.
          - ``avg_latency_ms``: mean ``latency_ms`` from event details.
          - ``tool_invocations``: count of ``tool_invoke`` events.
          - ``tool_failures``: count of tool_invoke events with failed status.
          - ``tool_failure_rate``: ``tool_failures / tool_invocations``.

        When ``project_id`` is given, events are joined to the ``runs`` table
        to filter by project.
        """
        if project_id is not None:
            sql = (
                "SELECT t.event_id, t.correlation_id, t.trace_id, t.run_id, t.event_type, "
                "t.entity_type, t.entity_id, t.summary, t.details_json, t.timestamp "
                "FROM control_plane.trace_events t "
                "LEFT JOIN control_plane.runs r ON t.run_id = r.run_id"
            )
        else:
            sql = (
                "SELECT event_id, correlation_id, trace_id, run_id, event_type, "
                "entity_type, entity_id, summary, details_json, timestamp "
                "FROM control_plane.trace_events t"
            )
        params: dict[str, Any] = {}
        conditions: list[str] = []
        if project_id is not None:
            conditions.append("r.project_id = :project_id")
            params["project_id"] = project_id
        if start_date is not None:
            conditions.append("t.timestamp >= :start_date")
            params["start_date"] = start_date
        if end_date is not None:
            conditions.append("t.timestamp <= :end_date")
            params["end_date"] = end_date
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()

        event_counts: dict[str, int] = {}
        latencies: list[int] = []
        tool_total = 0
        tool_failed = 0
        for row in rows:
            etype = row[4]
            event_counts[etype] = event_counts.get(etype, 0) + 1
            details = _parse_json_field(row[8], default={}) or {}
            latency = details.get("latency_ms")
            if isinstance(latency, (int, float)):
                latencies.append(int(latency))
            if etype == "tool_invoke":
                tool_total += 1
                status = details.get("status", "")
                if status in ("failed", "timeout", "rejected"):
                    tool_failed += 1

        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        failure_rate = (tool_failed / tool_total) if tool_total > 0 else 0.0
        return {
            "total_events": len(rows),
            "event_counts_by_type": event_counts,
            "avg_latency_ms": round(avg_latency, 2),
            "tool_invocations": tool_total,
            "tool_failures": tool_failed,
            "tool_failure_rate": round(failure_rate, 4),
        }

    # ── display sanitization ───────────────────────────────

    def sanitize_for_display(self, events: list[TraceEvent]) -> list[dict]:
        """Convert events to dicts with sensitive data redacted.

        Keys matching api_key, token, secret, password, credential,
        authorization, or internal_reasoning (case-insensitive) have their
        values replaced with ``"[REDACTED]"``.
        """
        sanitized: list[dict] = []
        for event in events:
            sanitized.append(
                {
                    "event_id": event.event_id,
                    "correlation_id": event.correlation_id,
                    "trace_id": event.trace_id,
                    "run_id": event.run_id,
                    "event_type": event.event_type,
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "summary": event.summary,
                    "details": self._sanitize_dict(event.details),
                    "timestamp": event.timestamp.isoformat()
                    if isinstance(event.timestamp, datetime)
                    else str(event.timestamp),
                }
            )
        return sanitized

    def _sanitize_dict(self, data: dict) -> dict:
        """Recursively redact sensitive values in a dict."""
        result: dict = {}
        for key, value in data.items():
            if isinstance(key, str) and _SENSITIVE_KEY_RE.search(key):
                result[key] = "[REDACTED]"
            elif isinstance(value, dict):
                result[key] = self._sanitize_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self._sanitize_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    @staticmethod
    def _sanitize_text(text: str | None) -> str | None:
        """Redact ``sensitive_key=value`` patterns in a free-text string."""
        if not text:
            return text
        return _SENSITIVE_KV_RE.sub(r"\1\2[REDACTED]", text)

    # ── helpers ────────────────────────────────────────────

    @staticmethod
    def _row_to_event(row) -> TraceEvent:
        return TraceEvent(
            event_id=row[0],
            correlation_id=row[1],
            trace_id=row[2],
            run_id=row[3],
            event_type=row[4],
            entity_type=row[5],
            entity_id=row[6],
            summary=row[7],
            details=_parse_json_field(row[8], default={}) or {},
            timestamp=_to_datetime(row[9]),
        )
