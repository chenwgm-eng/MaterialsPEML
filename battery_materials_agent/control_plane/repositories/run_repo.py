"""Thin repository for runs and checkpoints.

PostgreSQL via SQLAlchemy Engine；schema 由 alembic 管理
（control_plane.runs / control_plane.checkpoints）。

Follows the same pattern as ``committee/repository.py``: Pydantic models in,
Pydantic models out, with JSON serialization for dict/list fields. 使用
self.engine.begin()/connect() 管理连接生命周期。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from ...db import get_engine
from ..run_manager import (
    Checkpoint,
    Run,
    RunStatus,
    RunType,
)


class RunRepository:
    """PostgreSQL CRUD for runs and checkpoints.

    使用 SQLAlchemy Engine；schema 由 alembic 管理。
    """

    def __init__(self, db_path: str = "data/control_plane.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.db_path = db_path
        self.engine = get_engine()

    def _init_db(self) -> None:  # pragma: no cover - 兼容旧调用
        """No-op：表结构由 alembic 管理。"""
        return

    # ── runs ───────────────────────────────────────────────

    def create_run(self, run: Run) -> Run:
        """Insert a new run row."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO control_plane.runs
                       (run_id, run_type, project_id, parent_run_id, status,
                        input_hash, plan_version, policy_version, idempotency_key,
                        checkpoint_ref, metadata_json, created_at, updated_at)
                       VALUES (:run_id, :run_type, :project_id, :parent_run_id, :status,
                                :input_hash, :plan_version, :policy_version, :idempotency_key,
                                :checkpoint_ref, CAST(:metadata_json AS JSONB),
                                :created_at, :updated_at)"""
                ),
                {
                    "run_id": run.run_id,
                    "run_type": run.run_type,
                    "project_id": run.project_id,
                    "parent_run_id": run.parent_run_id,
                    "status": run.status.value,
                    "input_hash": run.input_hash,
                    "plan_version": run.plan_version,
                    "policy_version": run.policy_version,
                    "idempotency_key": run.idempotency_key,
                    "checkpoint_ref": run.checkpoint_ref,
                    "metadata_json": json.dumps(run.metadata),
                    "created_at": run.created_at.isoformat(),
                    "updated_at": run.updated_at.isoformat(),
                },
            )
        return run

    def get_run(self, run_id: str) -> Run | None:
        """Get a run by ID, or ``None`` if not found."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT run_id, run_type, project_id, parent_run_id, status,
                              input_hash, plan_version, policy_version, idempotency_key,
                              checkpoint_ref, metadata_json, created_at, updated_at
                       FROM control_plane.runs WHERE run_id = :run_id"""
                ),
                {"run_id": run_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_run(row)

    def update_run(self, run: Run) -> None:
        """Update all mutable fields of a run."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE control_plane.runs SET
                         run_type = :run_type, project_id = :project_id,
                         parent_run_id = :parent_run_id, status = :status,
                         input_hash = :input_hash, plan_version = :plan_version,
                         policy_version = :policy_version,
                         idempotency_key = :idempotency_key,
                         checkpoint_ref = :checkpoint_ref,
                         metadata_json = CAST(:metadata_json AS JSONB),
                         updated_at = :updated_at
                       WHERE run_id = :run_id"""
                ),
                {
                    "run_type": run.run_type,
                    "project_id": run.project_id,
                    "parent_run_id": run.parent_run_id,
                    "status": run.status.value,
                    "input_hash": run.input_hash,
                    "plan_version": run.plan_version,
                    "policy_version": run.policy_version,
                    "idempotency_key": run.idempotency_key,
                    "checkpoint_ref": run.checkpoint_ref,
                    "metadata_json": json.dumps(run.metadata),
                    "updated_at": run.updated_at.isoformat(),
                    "run_id": run.run_id,
                },
            )

    def update_run_status(self, run_id: str, status: RunStatus) -> None:
        """Update only the status (and ``updated_at``) of a run."""
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE control_plane.runs
                       SET status = :status, updated_at = :updated_at
                       WHERE run_id = :run_id"""
                ),
                {"status": status.value, "updated_at": now, "run_id": run_id},
            )

    def update_run_checkpoint_ref(self, run_id: str, checkpoint_id: str | None) -> None:
        """Update the ``checkpoint_ref`` (and ``updated_at``) of a run."""
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE control_plane.runs
                       SET checkpoint_ref = :checkpoint_ref, updated_at = :updated_at
                       WHERE run_id = :run_id"""
                ),
                {
                    "checkpoint_ref": checkpoint_id,
                    "updated_at": now,
                    "run_id": run_id,
                },
            )

    def delete_run(self, run_id: str) -> None:
        """Delete a run row."""
        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM control_plane.runs WHERE run_id = :run_id"),
                {"run_id": run_id},
            )

    def list_runs(
        self,
        project_id: str | None = None,
        status: RunStatus | None = None,
        run_type: RunType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Run]:
        """List runs with optional filters, newest first."""
        query = (
            "SELECT run_id, run_type, project_id, parent_run_id, status, "
            "input_hash, plan_version, policy_version, idempotency_key, "
            "checkpoint_ref, metadata_json, created_at, updated_at "
            "FROM control_plane.runs WHERE 1=1"
        )
        params: dict[str, Any] = {}
        if project_id is not None:
            query += " AND project_id = :project_id"
            params["project_id"] = project_id
        if status is not None:
            query += " AND status = :status"
            params["status"] = status.value
        if run_type is not None:
            query += " AND run_type = :run_type"
            params["run_type"] = run_type
        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).fetchall()
        return [self._row_to_run(row) for row in rows]

    # ── checkpoints ────────────────────────────────────────

    def create_checkpoint(self, checkpoint: Checkpoint) -> Checkpoint:
        """Insert a new checkpoint row."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO control_plane.checkpoints
                       (checkpoint_id, run_id, step_name, step_index, status,
                        input_hash, output_summary_json, intent_log_json, created_at)
                       VALUES (:checkpoint_id, :run_id, :step_name, :step_index, :status,
                                :input_hash, CAST(:output_summary_json AS JSONB),
                                CAST(:intent_log_json AS JSONB), :created_at)"""
                ),
                {
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "run_id": checkpoint.run_id,
                    "step_name": checkpoint.step_name,
                    "step_index": checkpoint.step_index,
                    "status": checkpoint.status,
                    "input_hash": checkpoint.input_hash,
                    "output_summary_json": json.dumps(checkpoint.output_summary),
                    "intent_log_json": json.dumps(checkpoint.intent_log),
                    "created_at": checkpoint.created_at.isoformat(),
                },
            )
        return checkpoint

    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        """Get a checkpoint by ID, or ``None`` if not found."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT checkpoint_id, run_id, step_name, step_index, status,
                              input_hash, output_summary_json, intent_log_json, created_at
                       FROM control_plane.checkpoints
                       WHERE checkpoint_id = :checkpoint_id"""
                ),
                {"checkpoint_id": checkpoint_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_checkpoint(row)

    def get_latest_checkpoint(self, run_id: str) -> Checkpoint | None:
        """Get the latest checkpoint for a run (highest step_index)."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT checkpoint_id, run_id, step_name, step_index, status,
                              input_hash, output_summary_json, intent_log_json, created_at
                       FROM control_plane.checkpoints
                       WHERE run_id = :run_id
                       ORDER BY step_index DESC, created_at DESC
                       LIMIT 1"""
                ),
                {"run_id": run_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_checkpoint(row)

    def list_checkpoints(self, run_id: str) -> list[Checkpoint]:
        """List all checkpoints for a run, ordered by step_index."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT checkpoint_id, run_id, step_name, step_index, status,
                              input_hash, output_summary_json, intent_log_json, created_at
                       FROM control_plane.checkpoints
                       WHERE run_id = :run_id
                       ORDER BY step_index ASC, created_at ASC"""
                ),
                {"run_id": run_id},
            ).fetchall()
        return [self._row_to_checkpoint(row) for row in rows]

    def delete_checkpoints(self, run_id: str) -> None:
        """Delete all checkpoints for a run."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM control_plane.checkpoints WHERE run_id = :run_id"
                ),
                {"run_id": run_id},
            )

    # ── helpers ────────────────────────────────────────────

    @staticmethod
    def _row_to_run(row) -> Run:
        return Run(
            run_id=row[0],
            run_type=row[1],
            project_id=row[2],
            parent_run_id=row[3],
            status=RunStatus(row[4]),
            input_hash=row[5],
            plan_version=row[6],
            policy_version=row[7],
            idempotency_key=row[8],
            checkpoint_ref=row[9],
            metadata=_parse_json_field(row[10], default={}) or {},
            created_at=_to_datetime(row[11]),
            updated_at=_to_datetime(row[12]),
        )

    @staticmethod
    def _row_to_checkpoint(row) -> Checkpoint:
        return Checkpoint(
            checkpoint_id=row[0],
            run_id=row[1],
            step_name=row[2],
            step_index=row[3],
            status=row[4],
            input_hash=row[5],
            output_summary=_parse_json_field(row[6], default={}) or {},
            intent_log=_parse_json_field(row[7], default=[]) or [],
            created_at=_to_datetime(row[8]),
        )


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
