"""Committee event store — append-only event log for committee cases (SQLAlchemy Engine)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import text

from ..db import get_engine
from .enums import CaseStatus


def _safe_json(value, default):
    """安全解析 JSON 字段，兼容 psycopg3 对 JSONB 列的自动反序列化。"""
    if not value:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
    return value


class CommitteeEventStore:
    """Append-only event log for committee cases with replay capability.

    Schema 由 alembic 管理（committee.committee_events，主键 id BIGSERIAL）。
    """

    def __init__(self, db_path: str | None = None):
        # db_path 参数已废弃：schema 由 alembic 管理，统一通过 get_engine() 获取 Engine。
        self.engine = get_engine()

    def append(self, case_id: str, event_type: str, data: dict) -> None:
        """Append an event to the event stream."""
        timestamp = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO committee.committee_events
                       (case_id, event_type, data_json, timestamp)
                       VALUES (:case_id, :event_type, :data_json, :timestamp)"""
                ),
                {
                    "case_id": case_id,
                    "event_type": event_type,
                    "data_json": json.dumps(data),
                    "timestamp": timestamp,
                },
            )

    def get_events(self, case_id: str) -> list[dict]:
        """Get all events for a case."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, case_id, event_type, data_json, timestamp "
                    "FROM committee.committee_events WHERE case_id = :case_id "
                    "ORDER BY timestamp"
                ),
                {"case_id": case_id},
            ).mappings().all()

        return [
            {
                "id": row["id"],
                "case_id": row["case_id"],
                "event_type": row["event_type"],
                "data": _safe_json(row["data_json"], {}),
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    def replay(self, case_id: str) -> CaseStatus:
        """Replay events to determine current status."""
        events = self.get_events(case_id)
        if not events:
            return CaseStatus.PENDING

        status_transitions = {
            # Coordinator-driven events
            "assessment_started": CaseStatus.THINKING,
            "proposal_generated": CaseStatus.THINKING,
            "evidence_round_start": CaseStatus.EXECUTING_EVIDENCE,
            "evidence_collected": CaseStatus.EXECUTING_EVIDENCE,
            "verdict_reached": CaseStatus.VERIFYING,
            "assessment_completed": CaseStatus.PASS,
            # Specialized workflow events
            "candidate_priority_started": CaseStatus.THINKING,
            "candidate_priority_completed": CaseStatus.PASS,
            "deviation_review_started": CaseStatus.THINKING,
            "deviation_review_completed": CaseStatus.PASS,
            # Executor-driven events (AgenticExecutor)
            "case_created": CaseStatus.THINKING,
            "proposal_ready": CaseStatus.THINKING,
            "tool_started": CaseStatus.EXECUTING_EVIDENCE,
            "tool_completed": CaseStatus.EXECUTING_EVIDENCE,
            "tool_failed": CaseStatus.EXECUTING_EVIDENCE,
            "verdict_ready": CaseStatus.VERIFYING,
            "case_closed": CaseStatus.PASS,
        }

        current_status = CaseStatus.PENDING
        for event in events:
            event_type = event["event_type"]
            if event_type in status_transitions:
                new_status = status_transitions[event_type]
                if event_type in ("assessment_completed", "case_closed",
                                  "candidate_priority_completed", "deviation_review_completed"):
                    data = event.get("data", {})
                    final_decision = data.get("final_decision", data.get("decision", "failed"))
                    decision_map = {
                        "pass": CaseStatus.PASS,
                        "reject": CaseStatus.REJECT,
                        "request_evidence": CaseStatus.REQUEST_EVIDENCE,
                        "human_review": CaseStatus.HUMAN_REVIEW,
                        "failed": CaseStatus.FAILED,
                    }
                    current_status = decision_map.get(final_decision, CaseStatus.FAILED)
                else:
                    current_status = new_status

        return current_status
