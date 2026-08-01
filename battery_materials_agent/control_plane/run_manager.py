"""Durable run management for the Agent Control Plane.

Manages the lifecycle of ECML runs, committee runs, and agent runs with
checkpoint-based recovery, idempotency, and status validation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import text

from ..db import get_engine
from ..mdm.reference_dict import ReferenceDictStore


class RunStatus(str, Enum):
    """Lifecycle status of a control-plane run."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_EXTERNAL = "waiting_external"
    WAITING_HUMAN = "waiting_human"
    PAUSED_BUDGET = "paused_budget"
    RECOVERY_REQUIRED = "recovery_required"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATUS_CODES: frozenset[str] = frozenset(
    {RunStatus.SUCCEEDED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value}
)

RunType = Literal["ecml", "committee", "agent"]


class Checkpoint(BaseModel):
    """A durable checkpoint capturing run progress at a step boundary."""

    checkpoint_id: str
    run_id: str
    step_name: str
    step_index: int
    status: str = "running"
    input_hash: str = ""
    output_summary: dict = Field(default_factory=dict)
    intent_log: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Run(BaseModel):
    """A durable control-plane run (ECML, committee, or agent)."""

    run_id: str
    run_type: RunType
    project_id: str | None = None
    parent_run_id: str | None = None
    status: RunStatus = RunStatus.QUEUED
    input_hash: str = ""
    plan_version: str | None = None
    policy_version: str = "cp-v1"
    idempotency_key: str | None = None
    checkpoint_ref: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)


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


class RunManager:
    """Durable run lifecycle manager with checkpoint-based recovery.

    PostgreSQL via SQLAlchemy Engine；schema 由 alembic 管理
    （control_plane.runs / control_plane.checkpoints）。
    """

    def __init__(self, db_path: str = "data/control_plane.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.db_path = db_path
        self.engine = get_engine()
        self._mdm = ReferenceDictStore()

    def _init_db(self) -> None:  # pragma: no cover - 兼容旧调用
        """No-op：表结构由 alembic 管理。"""
        return

    def _valid_run_status_codes(self) -> set[str]:
        """从 MDM 查询 run 域的有效状态码列表。"""
        return {
            sc.code
            for sc in self._mdm.list_status_codes(domain="run")
            if sc.is_active
        }

    def _terminal_run_status_codes(self) -> set[str]:
        """从 MDM 查询 run 域的终态列表（取与业务终态码的交集）。"""
        valid = self._valid_run_status_codes()
        return valid & _TERMINAL_STATUS_CODES

    def _validate_run_status(self, status: RunStatus) -> None:
        """校验 status 必须存在于 MDM 的 run 域状态码中。"""
        if status.value not in self._valid_run_status_codes():
            raise ValueError(
                f"Invalid run status {status.value!r}: not defined in mdm.status_codes (domain='run')"
            )

    # ── runs ───────────────────────────────────────────────

    def create_run(
        self,
        run_type: RunType,
        project_id: str | None = None,
        parent_run_id: str | None = None,
        input_hash: str = "",
        idempotency_key: str | None = None,
        policy_version: str = "cp-v1",
        metadata: dict | None = None,
    ) -> Run:
        """Create a new run, honoring idempotency."""
        self._validate_run_status(RunStatus.QUEUED)
        now = datetime.now(timezone.utc)
        run = Run(
            run_id=str(uuid4()),
            run_type=run_type,
            project_id=project_id,
            parent_run_id=parent_run_id,
            status=RunStatus.QUEUED,
            input_hash=input_hash,
            policy_version=policy_version,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        try:
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
        except Exception:
            if idempotency_key is None:
                raise
            existing = self._find_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing
            raise
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

    def update_status(self, run_id: str, status: RunStatus) -> None:
        """Update a run's status with terminal-status precondition."""
        self._validate_run_status(status)
        terminal_statuses = self._terminal_run_status_codes()
        now = datetime.now(timezone.utc).isoformat()
        params: dict[str, Any] = {
            "status": status.value,
            "updated_at": now,
            "run_id": run_id,
        }
        if terminal_statuses:
            in_clause = ", ".join(f":term_{i}" for i in range(len(terminal_statuses)))
            for i, term in enumerate(terminal_statuses):
                params[f"term_{i}"] = term
            where_clause = f"""AND (status = :status
                              OR status NOT IN ({in_clause}))"""
        else:
            where_clause = "AND status = :status"
        with self.engine.begin() as conn:
            cursor = conn.execute(
                text(
                    f"""UPDATE control_plane.runs SET status = :status, updated_at = :updated_at
                       WHERE run_id = :run_id
                         {where_clause}"""
                ),
                params,
            )
            if cursor.rowcount == 0:
                row = conn.execute(
                    text("SELECT status FROM control_plane.runs WHERE run_id = :run_id"),
                    {"run_id": run_id},
                ).fetchone()
                if row is None:
                    raise ValueError(f"Run {run_id!r} not found")
                raise ValueError(
                    f"Run {run_id!r} is in terminal status {row[0]!r}; "
                    f"cannot transition to {status.value!r}"
                )

    def get_runs(
        self,
        project_id: str | None = None,
        status: RunStatus | None = None,
        limit: int = 50,
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
        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).fetchall()
        return [self._row_to_run(row) for row in rows]

    def get_recovery_runs(self) -> list[Run]:
        """Get all runs in RECOVERY_REQUIRED status."""
        return self.get_runs(status=RunStatus.RECOVERY_REQUIRED, limit=10000)

    # ── checkpoints ────────────────────────────────────────

    def write_checkpoint(
        self,
        run_id: str,
        step_name: str,
        step_index: int,
        input_hash: str,
        output_summary: dict,
        intent_log: list[str],
    ) -> Checkpoint:
        """Write a checkpoint for a run and update the run's ``checkpoint_ref``."""
        checkpoint = Checkpoint(
            checkpoint_id=str(uuid4()),
            run_id=run_id,
            step_name=step_name,
            step_index=step_index,
            input_hash=input_hash,
            output_summary=output_summary,
            intent_log=intent_log,
        )
        now = datetime.now(timezone.utc).isoformat()
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
            conn.execute(
                text(
                    "UPDATE control_plane.runs SET checkpoint_ref = :checkpoint_ref, updated_at = :updated_at WHERE run_id = :run_id"
                ),
                {
                    "checkpoint_ref": checkpoint.checkpoint_id,
                    "updated_at": now,
                    "run_id": run_id,
                },
            )
        return checkpoint

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

    # ── lifecycle ──────────────────────────────────────────

    def resume(self, run_id: str) -> Run:
        """Resume a run from its latest checkpoint."""
        run = self.get_run(run_id)
        if run is None:
            raise ValueError(f"Run {run_id!r} not found")
        if run.status.value in self._terminal_run_status_codes():
            raise ValueError(
                f"Run {run_id!r} is in terminal status {run.status.value!r}; cannot resume"
            )
        checkpoint = self.get_latest_checkpoint(run_id)
        if checkpoint is None:
            raise ValueError(f"Run {run_id!r} has no checkpoint to resume from")
        self.update_status(run_id, RunStatus.RUNNING)
        run = self.get_run(run_id)
        if run is None:
            raise ValueError(f"Run {run_id!r} disappeared after resume")
        return run

    def cancel(self, run_id: str) -> Run:
        """Cancel a run by marking it as ``CANCELLED``."""
        self.update_status(run_id, RunStatus.CANCELLED)
        run = self.get_run(run_id)
        if run is None:
            raise ValueError(f"Run {run_id!r} disappeared after cancel")
        return run

    # ── internals ──────────────────────────────────────────

    def _find_by_idempotency_key(self, key: str) -> Run | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT run_id, run_type, project_id, parent_run_id, status,
                              input_hash, plan_version, policy_version, idempotency_key,
                              checkpoint_ref, metadata_json, created_at, updated_at
                       FROM control_plane.runs WHERE idempotency_key = :key"""
                ),
                {"key": key},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_run(row)

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
