"""Scientific Execution Kernel — 管理所有科学服务的 Task/Run 生命周期。"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import text

from ...contracts.task import Task, TaskStatus, TaskPriority
from ...contracts.run import Run, RunStatus, is_terminal
from ...contracts.artifact import Artifact, ArtifactType
from ...contracts.evidence import EvidencePackage, EvidenceLevel
from ...contracts.approval import ApprovalRequest, ApprovalStatus
from ...contracts.event import DomainEvent
from ...db import get_engine
from .state_machine import RunStateMachine, InvalidTransitionError
from .outbox import ScientificOutbox

logger = logging.getLogger(__name__)


class ScientificExecutionKernel:
    """管理所有科学服务的 Task/Run 生命周期。

    职责：
    - 创建/查询 Task
    - 提交/取消/恢复 Run（含状态机校验）
    - 查询 Artifact 和 Evidence
    - 管理审批流程
    - 发出领域事件（通过 Outbox 保证可靠性）
    """

    def __init__(self):
        self.engine = get_engine()
        self.state_machine = RunStateMachine()
        self.outbox = ScientificOutbox()

    # ── Task ───────────────────────────────────────────────

    def create_task(self, task: Task) -> Task:
        """创建科学任务。"""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO scientific_kernel.tasks
                       (task_id, project_id, capability_id, title, description,
                        status, priority, input_schema_version, metadata_json,
                        created_at, updated_at)
                       VALUES (:task_id, :project_id, :capability_id, :title, :description,
                               :status, :priority, :input_schema_version,
                               CAST(:metadata_json AS JSONB), :created_at, :updated_at)"""
                ),
                {
                    "task_id": task.task_id,
                    "project_id": task.project_id,
                    "capability_id": task.capability_id,
                    "title": task.title,
                    "description": task.description,
                    "status": task.status.value,
                    "priority": task.priority.value,
                    "input_schema_version": task.input_schema_version,
                    "metadata_json": json.dumps(task.metadata),
                    "created_at": task.created_at.isoformat(),
                    "updated_at": task.updated_at.isoformat(),
                },
            )
        self.outbox.enqueue(
            event_type="task.created",
            subject_id=task.task_id,
            payload={"task_id": task.task_id, "project_id": task.project_id},
        )
        logger.info("Task created: %s (%s)", task.task_id, task.title)
        return task

    def get_task(self, task_id: str) -> Task | None:
        """查询任务。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT task_id, project_id, capability_id, title, description,
                              status, priority, input_schema_version, metadata_json,
                              created_at, updated_at
                       FROM scientific_kernel.tasks WHERE task_id = :task_id"""
                ),
                {"task_id": task_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    def list_tasks(self, project_id: str | None = None, limit: int = 50, offset: int = 0) -> list[Task]:
        """列出任务。"""
        query = (
            "SELECT task_id, project_id, capability_id, title, description, "
            "status, priority, input_schema_version, metadata_json, "
            "created_at, updated_at FROM scientific_kernel.tasks WHERE 1=1"
        )
        params: dict = {}
        if project_id:
            query += " AND project_id = :project_id"
            params["project_id"] = project_id
        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).fetchall()
        return [self._row_to_task(r) for r in rows]

    # ── Run ────────────────────────────────────────────────

    def submit_run(self, run: Run) -> Run:
        """提交运行。"""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO scientific_kernel.runs
                       (run_id, task_id, project_id, service_id, command,
                        status, input_json, output_json, error_message,
                        started_at, completed_at, created_at, updated_at, metadata_json)
                       VALUES (:run_id, :task_id, :project_id, :service_id, :command,
                               :status, CAST(:input_json AS JSONB), :output_json, :error_message,
                               :started_at, :completed_at, :created_at, :updated_at,
                               CAST(:metadata_json AS JSONB))"""
                ),
                {
                    "run_id": run.run_id,
                    "task_id": run.task_id,
                    "project_id": run.project_id,
                    "service_id": run.service_id,
                    "command": run.command,
                    "status": run.status.value,
                    "input_json": json.dumps(run.input),
                    "output_json": None,
                    "error_message": None,
                    "started_at": None,
                    "completed_at": None,
                    "created_at": run.created_at.isoformat(),
                    "updated_at": run.updated_at.isoformat(),
                    "metadata_json": json.dumps(run.metadata),
                },
            )
        self.outbox.enqueue("run.submitted", run.run_id, {"run_id": run.run_id, "task_id": run.task_id})
        logger.info("Run submitted: %s (task=%s, service=%s)", run.run_id, run.task_id, run.service_id)
        return run

    def update_run_status(self, run_id: str, new_status: RunStatus) -> Run:
        """更新 Run 状态（含状态机校验与乐观锁守卫）。"""
        current = self.get_run(run_id)
        if current is None:
            raise ValueError(f"Run {run_id!r} not found")
        validated = self.state_machine.transition(current.status, new_status)
        now = datetime.now(timezone.utc).isoformat()
        update_fields = {"status": validated.value, "updated_at": now}
        if validated == RunStatus.RUNNING:
            update_fields["started_at"] = now
        elif is_terminal(validated):
            update_fields["completed_at"] = now
        set_clause = ", ".join(f"{k} = :{k}" for k in update_fields)
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    f"UPDATE scientific_kernel.runs SET {set_clause} "
                    "WHERE run_id = :run_id AND status = :current_status"
                ),
                {**update_fields, "run_id": run_id, "current_status": current.status.value},
            )
            if result.rowcount == 0:
                # 并发下状态已被其他写者改变，读-改-写失败，避免丢失更新
                raise ValueError(
                    f"Run {run_id!r} 状态并发更新冲突：期望从 {current.status.value} 迁移，但状态已被其他写者改变"
                )
        self.outbox.enqueue(
            f"run.status_changed.{validated.value}",
            run_id,
            {"run_id": run_id, "status": validated.value},
        )
        logger.info("Run %s status: %s -> %s", run_id, current.status.value, validated.value)
        return self.get_run(run_id)

    def cancel_run(self, run_id: str) -> Run:
        """取消运行（通过 CANCELLING 中间态过渡，非法时走合法直接 CANCELLED）。"""
        current = self.get_run(run_id)
        if current is None:
            raise ValueError(f"Run {run_id!r} not found")
        # 仅走状态机允许的路径：优先 CANCELLING，若当前状态不允许 CANCELLING
        # 但允许直接 CANCELLED（如 QUEUED/PREPARING），则直接取消；若两者都非法
        # （当前已是终态），则抛错，绝不在状态机之外强置终态。
        if RunStateMachine.can_transition(current.status, RunStatus.CANCELLING):
            return self.update_run_status(run_id, RunStatus.CANCELLING)
        if RunStateMachine.can_transition(current.status, RunStatus.CANCELLED):
            return self.update_run_status(run_id, RunStatus.CANCELLED)
        raise InvalidTransitionError(
            f"Run {run_id!r} 当前状态 {current.status.value} 不允许取消（可能已是终态）"
        )

    def resume_run(self, run_id: str) -> Run:
        """恢复运行（从 QUEUED/PREPARING 重新进入 RUNNING）。"""
        current = self.get_run(run_id)
        if current is None:
            raise ValueError(f"Run {run_id!r} not found")
        return self.update_run_status(run_id, RunStatus.RUNNING)

    def get_run(self, run_id: str) -> Run | None:
        """查询运行。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT run_id, task_id, project_id, service_id, command,
                              status, input_json, output_json, error_message,
                              started_at, completed_at, created_at, updated_at, metadata_json
                       FROM scientific_kernel.runs WHERE run_id = :run_id"""
                ),
                {"run_id": run_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_run(row)

    def list_runs(
        self,
        task_id: str | None = None,
        project_id: str | None = None,
        status: RunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Run]:
        """列出运行记录。"""
        query = (
            "SELECT run_id, task_id, project_id, service_id, command, "
            "status, input_json, output_json, error_message, "
            "started_at, completed_at, created_at, updated_at, metadata_json "
            "FROM scientific_kernel.runs WHERE 1=1"
        )
        params: dict = {}
        if task_id:
            query += " AND task_id = :task_id"
            params["task_id"] = task_id
        if project_id:
            query += " AND project_id = :project_id"
            params["project_id"] = project_id
        if status:
            query += " AND status = :status"
            params["status"] = status.value
        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).fetchall()
        return [self._row_to_run(r) for r in rows]

    # ── Artifacts ──────────────────────────────────────────

    def store_artifact(self, artifact: Artifact) -> Artifact:
        """存储工件。"""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO scientific_kernel.artifacts
                       (artifact_id, run_id, type, name, description,
                        content_type, data_json, file_path, checksum, created_at)
                       VALUES (:artifact_id, :run_id, :type, :name, :description,
                               :content_type, CAST(:data_json AS JSONB), :file_path,
                               :checksum, :created_at)"""
                ),
                {
                    "artifact_id": artifact.artifact_id,
                    "run_id": artifact.run_id,
                    "type": artifact.type.value,
                    "name": artifact.name,
                    "description": artifact.description,
                    "content_type": artifact.content_type,
                    "data_json": json.dumps(artifact.data) if artifact.data else None,
                    "file_path": artifact.file_path,
                    "checksum": artifact.checksum,
                    "created_at": artifact.created_at.isoformat(),
                },
            )
        return artifact

    def get_artifacts(self, run_id: str) -> list[Artifact]:
        """查询工件的运行。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT artifact_id, run_id, type, name, description,
                              content_type, data_json, file_path, checksum, created_at
                       FROM scientific_kernel.artifacts WHERE run_id = :run_id
                       ORDER BY created_at ASC"""
                ),
                {"run_id": run_id},
            ).fetchall()
        return [self._row_to_artifact(r) for r in rows]

    # ── Evidence ───────────────────────────────────────────

    def store_evidence(self, evidence: EvidencePackage) -> EvidencePackage:
        """存储证据包。"""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO scientific_kernel.evidence
                       (evidence_id, run_id, task_id, claim, value, unit,
                        confidence, level, method, source_type, source_service,
                        schema_version, metadata_json, created_at)
                       VALUES (:evidence_id, :run_id, :task_id, :claim, :value, :unit,
                               :confidence, :level, :method, :source_type, :source_service,
                               :schema_version, CAST(:metadata_json AS JSONB), :created_at)"""
                ),
                {
                    "evidence_id": evidence.evidence_id,
                    "run_id": evidence.run_id,
                    "task_id": evidence.task_id,
                    "claim": evidence.claim,
                    "value": json.dumps(evidence.value) if evidence.value is not None else None,
                    "unit": evidence.unit,
                    "confidence": evidence.confidence,
                    "level": evidence.level.value,
                    "method": evidence.method,
                    "source_type": evidence.source_type,
                    "source_service": evidence.source_service,
                    "schema_version": evidence.schema_version,
                    "metadata_json": json.dumps(evidence.metadata),
                    "created_at": evidence.created_at.isoformat(),
                },
            )
        return evidence

    def get_evidence(self, run_id: str) -> list[EvidencePackage]:
        """查询运行产生的证据包。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT evidence_id, run_id, task_id, claim, value, unit,
                              confidence, level, method, source_type, source_service,
                              schema_version, metadata_json, created_at
                       FROM scientific_kernel.evidence WHERE run_id = :run_id
                       ORDER BY created_at ASC"""
                ),
                {"run_id": run_id},
            ).fetchall()
        return [self._row_to_evidence(r) for r in rows]

    def get_evidence_by_id(self, evidence_id: str) -> EvidencePackage | None:
        """通过 evidence_id 直接查询单个证据包。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT evidence_id, run_id, task_id, claim, value, unit,
                              confidence, level, method, source_type, source_service,
                              schema_version, metadata_json, created_at
                       FROM scientific_kernel.evidence WHERE evidence_id = :evidence_id"""
                ),
                {"evidence_id": evidence_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_evidence(row)

    # ── Approval ───────────────────────────────────────────

    def request_approval(self, evidence_id: str) -> ApprovalRequest:
        """根据证据发起审批请求。"""
        request = ApprovalRequest(
            run_id="",
            evidence_id=evidence_id,
        )
        # 查找证据对应的 run_id
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT run_id, task_id FROM scientific_kernel.evidence WHERE evidence_id = :eid"),
                {"eid": evidence_id},
            ).fetchone()
            if row:
                request.run_id = row[0]
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO scientific_kernel.approvals
                       (approval_id, run_id, evidence_id, status, requested_by,
                        reviewed_by, comment, reviewed_at, created_at, metadata_json)
                       VALUES (:approval_id, :run_id, :evidence_id, :status, :requested_by,
                               :reviewed_by, :comment, :reviewed_at, :created_at,
                               CAST(:metadata_json AS JSONB))"""
                ),
                {
                    "approval_id": request.approval_id,
                    "run_id": request.run_id,
                    "evidence_id": request.evidence_id,
                    "status": request.status.value,
                    "requested_by": request.requested_by,
                    "reviewed_by": None,
                    "comment": None,
                    "reviewed_at": None,
                    "created_at": request.created_at.isoformat(),
                    "metadata_json": json.dumps(request.metadata),
                },
            )
        self.outbox.enqueue(
            "approval.requested", request.approval_id,
            {"approval_id": request.approval_id, "evidence_id": evidence_id},
        )
        logger.info("Approval requested: %s (evidence=%s)", request.approval_id, evidence_id)
        return request

    def approve(self, approval_id: str, reviewer: str, comment: str = "") -> ApprovalRequest:
        """批准审批。"""
        return self._review_approval(approval_id, ApprovalStatus.APPROVED, reviewer, comment)

    def reject(self, approval_id: str, reviewer: str, comment: str) -> ApprovalRequest:
        """拒绝审批。"""
        return self._review_approval(approval_id, ApprovalStatus.REJECTED, reviewer, comment)

    def _review_approval(self, approval_id: str, status: ApprovalStatus, reviewer: str, comment: str) -> ApprovalRequest:
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE scientific_kernel.approvals
                       SET status = :status, reviewed_by = :reviewer,
                           comment = :comment, reviewed_at = :reviewed_at
                       WHERE approval_id = :approval_id AND status = 'pending'"""
                ),
                {
                    "status": status.value,
                    "reviewer": reviewer,
                    "comment": comment,
                    "reviewed_at": now,
                    "approval_id": approval_id,
                },
            )
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        """查询审批请求。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT approval_id, run_id, evidence_id, status, requested_by,
                              reviewed_by, comment, reviewed_at, created_at, metadata_json
                       FROM scientific_kernel.approvals WHERE approval_id = :approval_id"""
                ),
                {"approval_id": approval_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_approval(row)

    def list_approvals(self, run_id: str | None = None, limit: int = 50) -> list[ApprovalRequest]:
        """列出审批请求。"""
        query = (
            "SELECT approval_id, run_id, evidence_id, status, requested_by, "
            "reviewed_by, comment, reviewed_at, created_at, metadata_json "
            "FROM scientific_kernel.approvals WHERE 1=1"
        )
        params: dict = {}
        if run_id:
            query += " AND run_id = :run_id"
            params["run_id"] = run_id
        query += " ORDER BY created_at DESC LIMIT :limit"
        params["limit"] = limit
        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).fetchall()
        return [self._row_to_approval(r) for r in rows]

    # ── Events ─────────────────────────────────────────────

    def emit_event(self, event: DomainEvent) -> None:
        """发出领域事件。"""
        self.outbox.enqueue(
            event_type=event.event_type,
            subject_id=event.subject_id,
            payload=event.data,
        )
        logger.info("Event emitted: %s (subject=%s)", event.event_type, event.subject_id)

    # ── Row parsers ────────────────────────────────────────

    @staticmethod
    def _parse_json(value, default=None):
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            return json.loads(value) if value else default
        return default

    @staticmethod
    def _to_dt(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value)

    @classmethod
    def _row_to_task(cls, row) -> Task:
        return Task(
            task_id=row[0],
            project_id=row[1],
            capability_id=row[2],
            title=row[3],
            description=row[4] or "",
            status=TaskStatus(row[5]),
            priority=TaskPriority(row[6]),
            input_schema_version=row[7],
            metadata=cls._parse_json(row[8], {}),
            created_at=cls._to_dt(row[9]),
            updated_at=cls._to_dt(row[10]),
        )

    @classmethod
    def _row_to_run(cls, row) -> Run:
        return Run(
            run_id=row[0],
            task_id=row[1],
            project_id=row[2],
            service_id=row[3],
            command=row[4],
            status=RunStatus(row[5]),
            input=cls._parse_json(row[6], {}),
            output=cls._parse_json(row[7]),
            error_message=row[8],
            started_at=cls._to_dt(row[9]),
            completed_at=cls._to_dt(row[10]),
            created_at=cls._to_dt(row[11]),
            updated_at=cls._to_dt(row[12]),
            metadata=cls._parse_json(row[13], {}),
        )

    @classmethod
    def _row_to_artifact(cls, row) -> Artifact:
        return Artifact(
            artifact_id=row[0],
            run_id=row[1],
            type=ArtifactType(row[2]),
            name=row[3],
            description=row[4] or "",
            content_type=row[5],
            data=cls._parse_json(row[6]),
            file_path=row[7],
            checksum=row[8],
            created_at=cls._to_dt(row[9]),
        )

    @classmethod
    def _row_to_evidence(cls, row) -> EvidencePackage:
        value = row[4]
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass
        return EvidencePackage(
            evidence_id=row[0],
            run_id=row[1],
            task_id=row[2],
            claim=row[3],
            value=value,
            unit=row[5] or "",
            confidence=row[6] if row[6] is not None else 1.0,
            level=EvidenceLevel(row[7]) if row[7] else EvidenceLevel.MEDIUM,
            method=row[8] or "",
            source_type=row[9] or "real_engine",
            source_service=row[10] or "",
            schema_version=row[11] or "1.0.0",
            metadata=cls._parse_json(row[12], {}),
            created_at=cls._to_dt(row[13]),
        )

    @classmethod
    def _row_to_approval(cls, row) -> ApprovalRequest:
        return ApprovalRequest(
            approval_id=row[0],
            run_id=row[1] or "",
            evidence_id=row[2],
            status=ApprovalStatus(row[3]),
            requested_by=row[4] or "",
            reviewed_by=row[5],
            comment=row[6],
            reviewed_at=cls._to_dt(row[7]),
            created_at=cls._to_dt(row[8]),
            metadata=cls._parse_json(row[9], {}),
        )