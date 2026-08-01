"""Repository for policy decisions and tool invocations.

Thin CRUD layer that stores authorization decisions (from the policy engine)
and tool invocation records (from the tool gateway), enabling audit trails
and replay analysis.

PostgreSQL via SQLAlchemy Engine；schema 由 alembic 管理
（control_plane.policy_decisions / control_plane.tool_invocations）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from ...db import get_engine


SCHEMA = """
-- 表结构由 alembic 管理，运行时无需 executescript。
-- 此处保留 SCHEMA 字符串仅为兼容旧调用方的 _init_db() no-op 引用。
"""


class ControlPlaneRepository:
    """PostgreSQL CRUD for policy decisions and tool invocations.

    使用 SQLAlchemy Engine；schema 由 alembic 管理。
    """

    def __init__(self, db_path: str = "data/control_plane.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.db_path = db_path
        self.engine = get_engine()

    @staticmethod
    def _get_conn(self):  # pragma: no cover - 兼容旧调用
        """No-op：旧 sqlite3 风格 _get_conn 已废弃，使用 self.engine 即可。"""
        raise RuntimeError("Use self.engine.begin()/connect() instead of _get_conn()")

    def _init_db(self) -> None:  # pragma: no cover - 兼容旧调用
        """No-op：表结构由 alembic 管理。"""
        return

    # ── policy decisions ───────────────────────────────────

    def save_policy_decision(self, decision: dict) -> dict:
        """Save a policy decision (upsert by decision_id).

        Required keys: ``correlation_id``, ``action``, ``resource``,
        ``allowed``, ``reason_code``, ``policy_version``.
        Optional keys: ``decision_id`` (auto-generated if absent), ``subject_id``,
        ``obligations`` (dict), ``limits`` (dict), ``created_at``.
        """
        decision_id = decision.get("decision_id") or str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        obligations = decision.get("obligations")
        limits = decision.get("limits")
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO control_plane.policy_decisions
                       (decision_id, correlation_id, subject_id, action, resource,
                        allowed, reason_code, obligations_json, limits_json,
                        policy_version, created_at)
                       VALUES (:decision_id, :correlation_id, :subject_id, :action, :resource,
                                :allowed, :reason_code, CAST(:obligations_json AS JSONB),
                                CAST(:limits_json AS JSONB), :policy_version, :created_at)
                       ON CONFLICT (decision_id) DO UPDATE SET
                         correlation_id = EXCLUDED.correlation_id,
                         subject_id = EXCLUDED.subject_id,
                         action = EXCLUDED.action,
                         resource = EXCLUDED.resource,
                         allowed = EXCLUDED.allowed,
                         reason_code = EXCLUDED.reason_code,
                         obligations_json = EXCLUDED.obligations_json,
                         limits_json = EXCLUDED.limits_json,
                         policy_version = EXCLUDED.policy_version,
                         created_at = EXCLUDED.created_at"""
                ),
                {
                    "decision_id": decision_id,
                    "correlation_id": decision["correlation_id"],
                    "subject_id": decision.get("subject_id"),
                    "action": decision["action"],
                    "resource": decision["resource"],
                    "allowed": bool(decision["allowed"]),
                    "reason_code": decision["reason_code"],
                    "obligations_json": json.dumps(obligations, default=str)
                    if obligations is not None
                    else None,
                    "limits_json": json.dumps(limits, default=str)
                    if limits is not None
                    else None,
                    "policy_version": decision["policy_version"],
                    "created_at": decision.get("created_at") or now,
                },
            )
        result = dict(decision)
        result["decision_id"] = decision_id
        result["created_at"] = result.get("created_at") or now
        return result

    def get_policy_decisions(
        self,
        correlation_id: str | None = None,
        run_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Query policy decisions.

        ``run_id`` is accepted for API symmetry but not filtered here since
        the ``policy_decisions`` table has no ``run_id`` column; callers
        should filter by ``correlation_id`` instead.
        """
        sql = (
            "SELECT decision_id, correlation_id, subject_id, action, resource, "
            "allowed, reason_code, obligations_json, limits_json, policy_version, "
            "created_at FROM control_plane.policy_decisions"
        )
        params: dict[str, Any] = {}
        conditions: list[str] = []
        if correlation_id is not None:
            conditions.append("correlation_id = :correlation_id")
            params["correlation_id"] = correlation_id
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY created_at DESC LIMIT :limit"
        params["limit"] = limit

        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_policy_dict(row) for row in rows]

    # ── tool invocations ───────────────────────────────────

    def save_tool_invocation(self, invocation: dict) -> dict:
        """Save a tool invocation record (upsert by invocation_id).

        Required keys: ``correlation_id``, ``tool_id``, ``status``,
        ``input_hash``.
        Optional keys: ``invocation_id`` (auto-generated), ``run_id``,
        ``provider_id``, ``idempotency_key``, ``output_artifact_ref``,
        ``provenance`` (dict), ``latency_ms``, ``cost_amount``, ``created_at``.
        """
        invocation_id = invocation.get("invocation_id") or str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        provenance = invocation.get("provenance") or {}
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO control_plane.tool_invocations
                       (invocation_id, run_id, correlation_id, tool_id, provider_id,
                        idempotency_key, status, input_hash, output_artifact_ref,
                        provenance_json, latency_ms, cost_amount, created_at)
                       VALUES (:invocation_id, :run_id, :correlation_id, :tool_id, :provider_id,
                                :idempotency_key, :status, :input_hash, :output_artifact_ref,
                                CAST(:provenance_json AS JSONB), :latency_ms, :cost_amount, :created_at)
                       ON CONFLICT (invocation_id) DO UPDATE SET
                         run_id = EXCLUDED.run_id,
                         correlation_id = EXCLUDED.correlation_id,
                         tool_id = EXCLUDED.tool_id,
                         provider_id = EXCLUDED.provider_id,
                         idempotency_key = EXCLUDED.idempotency_key,
                         status = EXCLUDED.status,
                         input_hash = EXCLUDED.input_hash,
                         output_artifact_ref = EXCLUDED.output_artifact_ref,
                         provenance_json = EXCLUDED.provenance_json,
                         latency_ms = EXCLUDED.latency_ms,
                         cost_amount = EXCLUDED.cost_amount,
                         created_at = EXCLUDED.created_at"""
                ),
                {
                    "invocation_id": invocation_id,
                    "run_id": invocation.get("run_id"),
                    "correlation_id": invocation["correlation_id"],
                    "tool_id": invocation["tool_id"],
                    "provider_id": invocation.get("provider_id"),
                    "idempotency_key": invocation.get("idempotency_key"),
                    "status": invocation["status"],
                    "input_hash": invocation["input_hash"],
                    "output_artifact_ref": invocation.get("output_artifact_ref"),
                    "provenance_json": json.dumps(provenance, default=str),
                    "latency_ms": invocation.get("latency_ms"),
                    "cost_amount": invocation.get("cost_amount"),
                    "created_at": invocation.get("created_at") or now,
                },
            )
        result = dict(invocation)
        result["invocation_id"] = invocation_id
        result["created_at"] = result.get("created_at") or now
        return result

    def get_tool_invocations(
        self,
        run_id: str | None = None,
        tool_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Query tool invocations by run_id and/or tool_id."""
        sql = (
            "SELECT invocation_id, run_id, correlation_id, tool_id, provider_id, "
            "idempotency_key, status, input_hash, output_artifact_ref, "
            "provenance_json, latency_ms, cost_amount, created_at "
            "FROM control_plane.tool_invocations"
        )
        params: dict[str, Any] = {}
        conditions: list[str] = []
        if run_id is not None:
            conditions.append("run_id = :run_id")
            params["run_id"] = run_id
        if tool_id is not None:
            conditions.append("tool_id = :tool_id")
            params["tool_id"] = tool_id
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY created_at DESC LIMIT :limit"
        params["limit"] = limit

        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_invocation_dict(row) for row in rows]

    # ── helpers ────────────────────────────────────────────

    @staticmethod
    def _row_to_policy_dict(row) -> dict:
        return {
            "decision_id": row[0],
            "correlation_id": row[1],
            "subject_id": row[2],
            "action": row[3],
            "resource": row[4],
            "allowed": bool(row[5]),
            "reason_code": row[6],
            "obligations": _parse_json_field(row[7], default=None),
            "limits": _parse_json_field(row[8], default=None),
            "policy_version": row[9],
            "created_at": row[10],
        }

    @staticmethod
    def _row_to_invocation_dict(row) -> dict:
        return {
            "invocation_id": row[0],
            "run_id": row[1],
            "correlation_id": row[2],
            "tool_id": row[3],
            "provider_id": row[4],
            "idempotency_key": row[5],
            "status": row[6],
            "input_hash": row[7],
            "output_artifact_ref": row[8],
            "provenance": _parse_json_field(row[9], default={}) or {},
            "latency_ms": row[10],
            "cost_amount": row[11],
            "created_at": row[12],
        }


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
