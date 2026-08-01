"""Experiment controller for self-driving lab hardware integration with real data flow."""

from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from datetime import datetime, timezone
from typing import Any
import uuid
import json
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
import logging

from ..db import get_engine

logger = logging.getLogger(__name__)


class ExperimentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExperimentOrderStatus(str, Enum):
    """实验任务单状态枚举。

    使用大写字符串值以与现有数据库中已存储的状态字符串保持向后兼容。
    """

    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    IN_EXECUTION = "IN_EXECUTION"
    WAITING_FOR_DATA = "WAITING_FOR_DATA"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class IllegalStateTransitionError(ValueError):
    """Raised when an invalid status transition is attempted."""

    def __init__(self, from_status: str, to_status: str, reason: str = ""):
        self.from_status = from_status
        self.to_status = to_status
        self.reason = reason
        msg = f"Illegal transition: {from_status} -> {to_status}"
        if reason:
            msg = f"{msg}. {reason}"
        super().__init__(msg)


# 合法状态迁移图。COMPLETED / CANCELLED 为终态，不可迁出。
# WAITING_FOR_DATA 只能从 IN_EXECUTION 迁入，且只能迁回 IN_EXECUTION 或 COMPLETED。
ALLOWED_TRANSITIONS: dict[ExperimentOrderStatus, set[ExperimentOrderStatus]] = {
    ExperimentOrderStatus.DRAFT: {ExperimentOrderStatus.PENDING_APPROVAL, ExperimentOrderStatus.CANCELLED},
    ExperimentOrderStatus.PENDING_APPROVAL: {ExperimentOrderStatus.APPROVED, ExperimentOrderStatus.CANCELLED},
    ExperimentOrderStatus.APPROVED: {ExperimentOrderStatus.SCHEDULED, ExperimentOrderStatus.IN_EXECUTION, ExperimentOrderStatus.CANCELLED},
    ExperimentOrderStatus.SCHEDULED: {ExperimentOrderStatus.IN_EXECUTION, ExperimentOrderStatus.CANCELLED},
    ExperimentOrderStatus.IN_EXECUTION: {ExperimentOrderStatus.WAITING_FOR_DATA, ExperimentOrderStatus.COMPLETED, ExperimentOrderStatus.VALIDATION_FAILED, ExperimentOrderStatus.CANCELLED},
    ExperimentOrderStatus.WAITING_FOR_DATA: {ExperimentOrderStatus.IN_EXECUTION, ExperimentOrderStatus.COMPLETED},
    ExperimentOrderStatus.COMPLETED: set(),  # 终态
    ExperimentOrderStatus.CANCELLED: set(),  # 终态
    ExperimentOrderStatus.VALIDATION_FAILED: {ExperimentOrderStatus.IN_EXECUTION, ExperimentOrderStatus.CANCELLED},  # 可重试
}

# 旧 API 使用 REJECTED 表示拒绝，统一映射为 CANCELLED 以保持向后兼容
_STATUS_ALIASES: dict[str, str] = {
    "REJECTED": ExperimentOrderStatus.CANCELLED.value,
}


class ExperimentType(str, Enum):
    IONIC_CONDUCTIVITY = "ionic_conductivity"
    ELECTROCHEMICAL = "electrochemical"
    XRD = "xrd"
    SEM = "sem"
    DSC = "dsc"
    TGA = "tga"
    EIS = "eis"
    CV = "cv"


class ExperimentTask(BaseModel):
    task_id: str
    experiment_type: ExperimentType
    recipe: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: ExperimentStatus = ExperimentStatus.PENDING
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    provenance: list[dict] = Field(default_factory=list)


class ExperimentResult(BaseModel):
    task_id: str
    experiment_type: ExperimentType
    status: ExperimentStatus
    measured_values: dict[str, float] = Field(default_factory=dict)
    raw_data_path: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""
    provenance: list[dict] = Field(default_factory=list)


class ExperimentOrder(BaseModel):
    """实验任务单。"""
    order_id: str = ""
    project_id: str = ""
    rd_package_id: str = ""
    candidate_id: str = ""
    formulation_version: str = ""
    process_version: str = ""
    test_protocol_version: str = ""
    execution_mode: str = "MANUAL_ENTRY"  # AUTO_DEVICE / SEMI_AUTO / EXTERNAL_LIMS / EXTERNAL_ELN / MANUAL_ENTRY / SIMULATION_ONLY
    priority: str = "P2"  # P0 / P1 / P2 / P3
    assignee: str = ""
    material_requirements: list[dict] = Field(default_factory=list)
    procedure: list[dict] = Field(default_factory=list)
    required_results: list[str] = Field(default_factory=list)
    acceptance_criteria: dict[str, Any] = Field(default_factory=dict)
    status: str = "DRAFT"  # DRAFT / PENDING_APPROVAL / APPROVED / SCHEDULED / IN_EXECUTION / WAITING_FOR_DATA / COMPLETED / CANCELLED / VALIDATION_FAILED
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_by: str = ""
    approved_at: str | None = None
    notes: str = ""
    protocol_provenance: dict | None = None
    ai_draft: bool = False
    provenance: list[dict] = Field(default_factory=list)
    scenario_id: str = ""  # P0-001：关联研发场景 ID
    bom_id: str = ""  # 业务链路：关联 experiment.bom_schemes(bom_id)
    task_id: str = ""  # 业务链路：关联 projects.tasks(task_id)
    idempotency_key: str = ""  # 幂等键：防止重复提交创建重复任务单

    @field_validator('scenario_id', 'project_id', 'rd_package_id', 'candidate_id',
                     'formulation_version', 'process_version', 'test_protocol_version',
                     'assignee', 'approved_by', 'notes', 'execution_mode', 'priority', 'status',
                     'bom_id', 'task_id', 'idempotency_key',
                     mode='before')
    @classmethod
    def _coerce_none_to_empty(cls, v):
        """前端或上游可能传入 None（如 JSON null），统一转为空字符串。"""
        return "" if v is None else v


class ExperimentResultRecord(BaseModel):
    """实验结果记录（扩展版，含样品和质量信息）。

    业务链路：测试任务 1 → N 实验数据。test_task_id 由 0009 迁移新增，nullable。
    test_conditions 由 TEXT 改为 JSONB（0009 迁移）。
    """
    result_id: str = ""
    experiment_order_id: str = ""  # 关联实验任务单
    sample_id: str = ""
    sample_batch_id: str = ""
    source_type: str = "MANUAL_ENTRY"  # MANUAL_ENTRY / CSV_IMPORT / EXCEL_IMPORT / API_PUSH / DEVICE
    source_system: str = ""
    uploaded_by: str = ""
    uploaded_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    property_name: str = ""
    value: float = 0.0
    unit: str = ""
    test_method: str = ""
    test_conditions: dict[str, Any] = Field(default_factory=dict)  # JSONB（0009 迁移后）
    instrument_id: str = ""
    raw_file_uri: str = ""
    qc_status: str = "PENDING"  # PENDING / VALID / VALID_WITH_WARNING / INVALID / REQUIRES_REVIEW / REJECTED
    qc_issues: list[str] = Field(default_factory=list)
    reviewed_by: str = ""
    reviewed_at: str | None = None
    learning_eligible: bool = False
    scenario_id: str = ""  # P0-001：关联研发场景 ID
    test_task_id: str = ""  # 业务链路：关联 experiment.test_tasks(test_task_id)
    # 评测修复 P2-5：数据质量分层标记（verified 实测已审 / estimated 估算 / simulated 模拟 / literature 文献）
    # 默认 estimated；QC 审批通过后置为 verified
    data_quality: str = "estimated"

    @field_validator('scenario_id', 'experiment_order_id', 'sample_id', 'sample_batch_id',
                     'source_type', 'source_system', 'uploaded_by', 'property_name',
                     'unit', 'test_method', 'instrument_id', 'raw_file_uri', 'qc_status',
                     'reviewed_by', 'test_task_id', 'data_quality',
                     mode='before')
    @classmethod
    def _coerce_none_to_empty(cls, v):
        """前端或上游可能传入 None（如 JSON null），统一转为空字符串。"""
        return "" if v is None else v

    @field_validator('qc_issues', mode='before')
    @classmethod
    def _normalize_qc_issues_field(cls, v):
        """模型层兜底：无论调用方传入何种格式（list[str] / list[dict] / dict / None），
        统一归一化为 list[str]。根治 DB 历史脏数据（dict 格式如
        {'msg': '...', 'type': 'GOVERNANCE'}）导致的 ValidationError。
        """
        return _normalize_qc_issues(v)


class ApprovalRule(BaseModel):
    """审批规则。"""
    rule_id: str = ""
    rule_name: str = ""
    condition_field: str = ""  # cost / is_hazardous / is_new_supplier / model_confidence
    operator: str = ">"  # > / < / >= / <= / == / in
    threshold: float = 0.0
    action: str = "REQUIRE_MANUAL"  # AUTO_APPROVE / REQUIRE_MANUAL / BLOCK
    description: str = ""


class ApprovalDecision(BaseModel):
    """审批决策结果。"""
    action: str = "AUTO_APPROVE"  # AUTO_APPROVE / REQUIRE_MANUAL / BLOCK
    matched_rules: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    estimated_cost: float = 0.0
    is_hazardous: bool = False
    model_confidence: float = 0.0
    notes: str = ""


def _safe_json_load(value, default=None):
    """Safely parse JSON, returning default on failure.

    兼容 JSONB（psycopg3 自动解析为 Python 对象）与 TEXT（返回字符串）两种来源。
    """
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


def _normalize_qc_issues(raw) -> list[str]:
    """将 qc_issues 归一化为 list[str]。

    DB 中可能存在历史脏数据（dict 格式如 {'msg': '...', 'type': 'GOVERNANCE'}），
    统一转为字符串列表，避免 Pydantic list[str] 验证失败。
    """
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            msg = item.get("msg") or item.get("message") or ""
            issue_type = item.get("type") or item.get("rule_id") or ""
            if msg:
                result.append(f"{msg}（{issue_type}）" if issue_type else msg)
            elif issue_type:
                result.append(issue_type)
    return result


def _iso(v) -> str:
    """TIMESTAMPTZ 列由 psycopg3 返回 datetime 对象，需转为 ISO 字符串以匹配 Pydantic 模型。"""
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


class ExperimentDataStore:
    """PostgreSQL-backed persistent storage for experiment tasks and results."""

    def __init__(self, db_path: str = "data/experiments.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.engine = get_engine()
        # MDM 参考字典 Store，用于状态码校验（与 ExperimentController 保持一致）
        from ..mdm.reference_dict import ReferenceDictStore
        self._mdm = ReferenceDictStore()
        self._init_db()

    def _init_db(self):
        # 表已由 alembic 迁移创建，这里仅保留 IF NOT EXISTS 兜底
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.experiment_tasks (
                    task_id TEXT PRIMARY KEY,
                    experiment_type TEXT,
                    recipe JSONB,
                    parameters JSONB,
                    status TEXT,
                    created_at TIMESTAMPTZ,
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.experiment_results (
                    task_id TEXT PRIMARY KEY,
                    experiment_type TEXT,
                    status TEXT,
                    measured_values JSONB,
                    raw_data_path TEXT,
                    metadata JSONB,
                    error_message TEXT
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.analysis_results (
                    analysis_id TEXT PRIMARY KEY,
                    order_id TEXT,
                    analysis_json JSONB,
                    created_at TIMESTAMPTZ
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.notifications (
                    notification_id TEXT PRIMARY KEY,
                    order_id TEXT,
                    assignee TEXT,
                    message TEXT,
                    created_at TIMESTAMPTZ,
                    read BOOLEAN DEFAULT FALSE
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.experiment_orders (
                    order_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    rd_package_id TEXT,
                    candidate_id TEXT,
                    formulation_version TEXT,
                    process_version TEXT,
                    test_protocol_version TEXT,
                    execution_mode TEXT,
                    priority TEXT,
                    assignee TEXT,
                    material_requirements JSONB,
                    procedure TEXT,
                    required_results JSONB,
                    acceptance_criteria JSONB,
                    status TEXT,
                    created_at TIMESTAMPTZ,
                    approved_by TEXT,
                    approved_at TIMESTAMPTZ,
                    notes TEXT,
                    protocol_provenance JSONB,
                    ai_draft BOOLEAN DEFAULT FALSE,
                    provenance JSONB DEFAULT '[]',
                    scenario_id TEXT,
                    bom_id TEXT,
                    task_id TEXT
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.experiment_result_records (
                    result_id TEXT PRIMARY KEY,
                    experiment_order_id TEXT,
                    sample_id TEXT,
                    sample_batch_id TEXT,
                    source_type TEXT,
                    source_system TEXT,
                    uploaded_by TEXT,
                    uploaded_at TIMESTAMPTZ,
                    property_name TEXT,
                    value DOUBLE PRECISION,
                    unit TEXT,
                    test_method TEXT,
                    test_conditions JSONB,
                    instrument_id TEXT,
                    raw_file_uri TEXT,
                    qc_status TEXT,
                    qc_issues JSONB,
                    reviewed_by TEXT,
                    reviewed_at TIMESTAMPTZ,
                    learning_eligible BOOLEAN,
                    scenario_id TEXT,
                    test_task_id TEXT,
                    data_quality TEXT
                )
            """))
            # 评测修复 P2-5：历史库兜底补列（新库由上方 CREATE TABLE / alembic 0031 创建）
            conn.execute(text(
                "ALTER TABLE experiment.experiment_result_records "
                "ADD COLUMN IF NOT EXISTS data_quality TEXT"
            ))
            # 状态迁移事件日志表（alembic 0002 创建，此处兜底）
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.experiment_order_status_transitions (
                    transition_id    BIGSERIAL PRIMARY KEY,
                    order_id         TEXT NOT NULL,
                    from_status      TEXT NOT NULL,
                    to_status        TEXT NOT NULL,
                    triggered_by     TEXT NOT NULL DEFAULT 'system',
                    reason           TEXT DEFAULT '',
                    timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_transitions_order
                ON experiment.experiment_order_status_transitions(order_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_transitions_timestamp
                ON experiment.experiment_order_status_transitions(timestamp DESC)
            """))

    def save_analysis(self, order_id: str, analysis: dict) -> str:
        """保存实验分析简报到 analysis_results 表，返回 analysis_id。"""
        analysis_id = f"ANL_{uuid.uuid4().hex[:8]}"
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.analysis_results
                (analysis_id, order_id, analysis_json, created_at)
                VALUES (:analysis_id, :order_id, CAST(:analysis_json AS JSONB), :created_at)
                """),
                {
                    "analysis_id": analysis_id,
                    "order_id": order_id,
                    "analysis_json": json.dumps(analysis, ensure_ascii=False),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        return analysis_id

    def get_analysis_by_order(self, order_id: str) -> dict | None:
        """获取指定任务单最新一条分析简报。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT analysis_id, order_id, analysis_json, created_at "
                     "FROM experiment.analysis_results "
                     "WHERE order_id = :order_id ORDER BY created_at DESC LIMIT 1"),
                {"order_id": order_id},
            ).fetchone()
        if not row:
            return None
        return {
            "analysis_id": row[0],
            "order_id": row[1],
            "analysis": _safe_json_load(row[2], default={}),
            "created_at": row[3],
        }

    def save_task(self, task: ExperimentTask):
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.experiment_tasks
                (task_id, experiment_type, recipe, parameters, status, created_at, started_at, completed_at)
                VALUES (:task_id, :experiment_type, CAST(:recipe AS JSONB), CAST(:parameters AS JSONB),
                 :status, :created_at, :started_at, :completed_at)
                ON CONFLICT (task_id) DO UPDATE SET
                    experiment_type = EXCLUDED.experiment_type,
                    recipe = EXCLUDED.recipe,
                    parameters = EXCLUDED.parameters,
                    status = EXCLUDED.status,
                    created_at = EXCLUDED.created_at,
                    started_at = EXCLUDED.started_at,
                    completed_at = EXCLUDED.completed_at
                """),
                {
                    "task_id": task.task_id,
                    "experiment_type": task.experiment_type.value,
                    "recipe": json.dumps(task.recipe),
                    "parameters": json.dumps(task.parameters),
                    "status": task.status.value,
                    "created_at": task.created_at,
                    "started_at": task.started_at,
                    "completed_at": task.completed_at,
                },
            )

    def save_result(self, result: ExperimentResult):
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.experiment_results
                (task_id, experiment_type, status, measured_values, raw_data_path, metadata, error_message)
                VALUES (:task_id, :experiment_type, :status, CAST(:measured_values AS JSONB),
                 :raw_data_path, CAST(:metadata AS JSONB), :error_message)
                ON CONFLICT (task_id) DO UPDATE SET
                    experiment_type = EXCLUDED.experiment_type,
                    status = EXCLUDED.status,
                    measured_values = EXCLUDED.measured_values,
                    raw_data_path = EXCLUDED.raw_data_path,
                    metadata = EXCLUDED.metadata,
                    error_message = EXCLUDED.error_message
                """),
                {
                    "task_id": result.task_id,
                    "experiment_type": result.experiment_type.value,
                    "status": result.status.value,
                    "measured_values": json.dumps(result.measured_values),
                    "raw_data_path": result.raw_data_path,
                    "metadata": json.dumps(result.metadata),
                    "error_message": result.error_message,
                },
            )

    def get_task(self, task_id: str) -> ExperimentTask | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM experiment.experiment_tasks WHERE task_id = :task_id"),
                {"task_id": task_id},
            ).fetchone()
        if row is None:
            return None
        return ExperimentTask(
            task_id=row[0], experiment_type=ExperimentType(row[1]),
            recipe=_safe_json_load(row[2], default={}),
            parameters=_safe_json_load(row[3], default={}),
            status=ExperimentStatus(row[4]), created_at=_iso(row[5]),
            started_at=_iso(row[6]) or None, completed_at=_iso(row[7]) or None,
        )

    def get_result(self, task_id: str) -> ExperimentResult | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM experiment.experiment_results WHERE task_id = :task_id"),
                {"task_id": task_id},
            ).fetchone()
        if row is None:
            return None
        return ExperimentResult(
            task_id=row[0], experiment_type=ExperimentType(row[1]),
            status=ExperimentStatus(row[2]),
            measured_values=_safe_json_load(row[3], default={}),
            raw_data_path=row[4], metadata=_safe_json_load(row[5], default={}),
            error_message=row[6] or "",
        )

    def list_tasks(self, status: ExperimentStatus | None = None) -> list[ExperimentTask]:
        with self.engine.connect() as conn:
            if status:
                rows = conn.execute(
                    text("SELECT * FROM experiment.experiment_tasks WHERE status = :status"),
                    {"status": status.value},
                ).fetchall()
            else:
                rows = conn.execute(
                    text("SELECT * FROM experiment.experiment_tasks")
                ).fetchall()
        return [ExperimentTask(
            task_id=r[0], experiment_type=ExperimentType(r[1]),
            recipe=_safe_json_load(r[2], default={}),
            parameters=_safe_json_load(r[3], default={}),
            status=ExperimentStatus(r[4]), created_at=_iso(r[5]),
            started_at=_iso(r[6]) or None, completed_at=_iso(r[7]) or None,
        ) for r in rows]

    def save_order(self, order: "ExperimentOrder"):
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.experiment_orders
                (order_id, project_id, rd_package_id, candidate_id, formulation_version,
                 process_version, test_protocol_version, execution_mode, priority, assignee,
                 material_requirements, procedure, required_results, acceptance_criteria,
                 status, created_at, approved_by, approved_at, notes, protocol_provenance,
                 ai_draft, provenance, scenario_id, bom_id, task_id, idempotency_key)
                VALUES (:order_id, :project_id, :rd_package_id, :candidate_id, :formulation_version,
                 :process_version, :test_protocol_version, :execution_mode, :priority, :assignee,
                 CAST(:material_requirements AS JSONB), :procedure,
                 CAST(:required_results AS JSONB), CAST(:acceptance_criteria AS JSONB),
                 :status, :created_at, :approved_by, :approved_at, :notes,
                 CAST(:protocol_provenance AS JSONB),
                 :ai_draft, CAST(:provenance AS JSONB), :scenario_id,
                 :bom_id, :task_id, :idempotency_key)
                ON CONFLICT (order_id) DO UPDATE SET
                    project_id = EXCLUDED.project_id,
                    rd_package_id = EXCLUDED.rd_package_id,
                    candidate_id = EXCLUDED.candidate_id,
                    formulation_version = EXCLUDED.formulation_version,
                    process_version = EXCLUDED.process_version,
                    test_protocol_version = EXCLUDED.test_protocol_version,
                    execution_mode = EXCLUDED.execution_mode,
                    priority = EXCLUDED.priority,
                    assignee = EXCLUDED.assignee,
                    material_requirements = EXCLUDED.material_requirements,
                    procedure = EXCLUDED.procedure,
                    required_results = EXCLUDED.required_results,
                    acceptance_criteria = EXCLUDED.acceptance_criteria,
                    status = EXCLUDED.status,
                    created_at = EXCLUDED.created_at,
                    approved_by = EXCLUDED.approved_by,
                    approved_at = EXCLUDED.approved_at,
                    notes = EXCLUDED.notes,
                    protocol_provenance = EXCLUDED.protocol_provenance,
                    ai_draft = EXCLUDED.ai_draft,
                    provenance = EXCLUDED.provenance,
                    scenario_id = EXCLUDED.scenario_id,
                    bom_id = EXCLUDED.bom_id,
                    task_id = EXCLUDED.task_id,
                    idempotency_key = EXCLUDED.idempotency_key
                """),
                {
                    "order_id": order.order_id,
                    # Task 14.1：FK 约束不允许空字符串，需转为 NULL（PostgreSQL FK 仅对 NULL 跳过校验）
                    "project_id": order.project_id or None,
                    "rd_package_id": order.rd_package_id,
                    "candidate_id": order.candidate_id or None,
                    "formulation_version": order.formulation_version,
                    "process_version": order.process_version,
                    "test_protocol_version": order.test_protocol_version,
                    "execution_mode": order.execution_mode,
                    "priority": order.priority,
                    "assignee": order.assignee,
                    "material_requirements": json.dumps(order.material_requirements),
                    "procedure": json.dumps(order.procedure),
                    "required_results": json.dumps(order.required_results),
                    "acceptance_criteria": json.dumps(order.acceptance_criteria),
                    "status": order.status,
                    "created_at": order.created_at,
                    "approved_by": order.approved_by,
                    "approved_at": order.approved_at,
                    "notes": order.notes,
                    "protocol_provenance": json.dumps(order.protocol_provenance) if order.protocol_provenance else None,
                    "ai_draft": order.ai_draft,
                    "provenance": json.dumps(order.provenance),
                    "scenario_id": order.scenario_id or "",
                    "bom_id": order.bom_id or None,
                    "task_id": order.task_id or None,
                    "idempotency_key": order.idempotency_key or None,
                },
            )

    def get_order(self, order_id: str) -> "ExperimentOrder | None":
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM experiment.experiment_orders WHERE order_id = :order_id"),
                {"order_id": order_id},
            ).fetchone()
        if row is None:
            return None
        return ExperimentOrder(
            order_id=row[0], project_id=row[1] or "", rd_package_id=row[2] or "",
            candidate_id=row[3] or "",
            formulation_version=row[4], process_version=row[5], test_protocol_version=row[6],
            execution_mode=row[7], priority=row[8], assignee=row[9],
            material_requirements=_safe_json_load(row[10], default=[]),
            procedure=_safe_json_load(row[11], default=[]),
            required_results=_safe_json_load(row[12], default=[]),
            acceptance_criteria=_safe_json_load(row[13], default={}),
            status=row[14], created_at=_iso(row[15]), approved_by=row[16],
            approved_at=_iso(row[17]) or None, notes=row[18],
            protocol_provenance=_safe_json_load(row[19]),
            ai_draft=bool(row[20]) if row[20] is not None else False,
            provenance=_safe_json_load(row[21], default=[]),
            scenario_id=row[22] if row[22] is not None else "",
            bom_id=row[23] if len(row) > 23 and row[23] is not None else "",
            task_id=row[24] if len(row) > 24 and row[24] is not None else "",
            idempotency_key=row[25] if len(row) > 25 and row[25] is not None else "",
        )

    def get_order_by_idempotency_key(self, key: str) -> "ExperimentOrder | None":
        """按幂等键查询任务单（用于创建去重）。未找到返回 None。"""
        if not key:
            return None
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT order_id FROM experiment.experiment_orders "
                     "WHERE idempotency_key = :key"),
                {"key": key},
            ).fetchone()
        if row is None:
            return None
        return self.get_order(row[0])

    def list_orders(self, status: str | None = None, project_id: str | None = None,
                    task_id: str | None = None) -> list["ExperimentOrder"]:
        """查询实验任务单列表，支持按 status / project_id / task_id 过滤。"""
        with self.engine.connect() as conn:
            query = "SELECT * FROM experiment.experiment_orders"
            conditions = []
            params: dict[str, str] = {}
            if status:
                conditions.append("status = :status")
                params["status"] = status
            if project_id:
                conditions.append("project_id = :project_id")
                params["project_id"] = project_id
            if task_id:
                conditions.append("task_id = :task_id")
                params["task_id"] = task_id
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(text(query), params).fetchall()
        return [ExperimentOrder(
            order_id=r[0], project_id=r[1] or "", rd_package_id=r[2] or "",
            candidate_id=r[3] or "",
            formulation_version=r[4], process_version=r[5], test_protocol_version=r[6],
            execution_mode=r[7], priority=r[8], assignee=r[9],
            material_requirements=_safe_json_load(r[10], default=[]),
            procedure=_safe_json_load(r[11], default=[]),
            required_results=_safe_json_load(r[12], default=[]),
            acceptance_criteria=_safe_json_load(r[13], default={}),
            status=r[14], created_at=_iso(r[15]), approved_by=r[16],
            approved_at=_iso(r[17]) or None, notes=r[18],
            protocol_provenance=_safe_json_load(r[19]),
            ai_draft=bool(r[20]) if r[20] is not None else False,
            provenance=_safe_json_load(r[21], default=[]),
            scenario_id=r[22] if r[22] is not None else "",
            bom_id=r[23] if len(r) > 23 and r[23] is not None else "",
            task_id=r[24] if len(r) > 24 and r[24] is not None else "",
            idempotency_key=r[25] if len(r) > 25 and r[25] is not None else "",
        ) for r in rows]

    def save_result_record(self, record: "ExperimentResultRecord"):
        # Task 14.4：自动关联设备台账 — 若 instrument_id 缺失但 order 的 procedure
        # 中包含设备分配（step.equipment），自动填充 instrument_id
        if not record.instrument_id and record.experiment_order_id:
            try:
                order = self.get_order(record.experiment_order_id)
                if order is not None:
                    for step in order.procedure:
                        if isinstance(step, dict):
                            eq = step.get("equipment", "") or ""
                            if eq:
                                record.instrument_id = eq
                                break
            except Exception as e:
                logger.debug("自动填充 instrument_id 失败: %s", e)

        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text("""INSERT INTO experiment.experiment_result_records
                    (result_id, experiment_order_id, sample_id, sample_batch_id, source_type,
                     source_system, uploaded_by, uploaded_at, property_name, value, unit,
                     test_method, test_conditions, instrument_id, raw_file_uri, qc_status,
                     qc_issues, reviewed_by, reviewed_at, learning_eligible, scenario_id,
                     test_task_id, data_quality)
                    VALUES (:result_id, :experiment_order_id, :sample_id, :sample_batch_id, :source_type,
                     :source_system, :uploaded_by, :uploaded_at, :property_name, :value, :unit,
                     :test_method, CAST(:test_conditions AS JSONB), :instrument_id, :raw_file_uri, :qc_status,
                     CAST(:qc_issues AS JSONB), :reviewed_by, :reviewed_at, :learning_eligible, :scenario_id,
                     :test_task_id, :data_quality)
                    ON CONFLICT (result_id) DO UPDATE SET
                        experiment_order_id = EXCLUDED.experiment_order_id,
                        sample_id = EXCLUDED.sample_id,
                        sample_batch_id = EXCLUDED.sample_batch_id,
                        source_type = EXCLUDED.source_type,
                        source_system = EXCLUDED.source_system,
                        uploaded_by = EXCLUDED.uploaded_by,
                        uploaded_at = EXCLUDED.uploaded_at,
                        property_name = EXCLUDED.property_name,
                        value = EXCLUDED.value,
                        unit = EXCLUDED.unit,
                        test_method = EXCLUDED.test_method,
                        test_conditions = EXCLUDED.test_conditions,
                        instrument_id = EXCLUDED.instrument_id,
                        raw_file_uri = EXCLUDED.raw_file_uri,
                        qc_status = EXCLUDED.qc_status,
                        qc_issues = EXCLUDED.qc_issues,
                        reviewed_by = EXCLUDED.reviewed_by,
                        reviewed_at = EXCLUDED.reviewed_at,
                        learning_eligible = EXCLUDED.learning_eligible,
                        scenario_id = EXCLUDED.scenario_id,
                        test_task_id = EXCLUDED.test_task_id,
                        data_quality = EXCLUDED.data_quality
                    """),
                    {
                        "result_id": record.result_id,
                        # Task 14.1：FK 约束不允许空字符串，需转为 NULL
                        "experiment_order_id": record.experiment_order_id or None,
                        "sample_id": record.sample_id or None,
                        "sample_batch_id": record.sample_batch_id,
                        "source_type": record.source_type,
                        "source_system": record.source_system,
                        "uploaded_by": record.uploaded_by,
                        "uploaded_at": record.uploaded_at,
                        # P5 FK 加固：property_name/unit/test_method 引用 MDM 主数据，空字符串需转为 NULL
                        "property_name": record.property_name or None,
                        "value": record.value,
                        "unit": record.unit or None,
                        "test_method": record.test_method or None,
                        "test_conditions": json.dumps(record.test_conditions),
                        "instrument_id": record.instrument_id or None,
                        "raw_file_uri": record.raw_file_uri,
                        "qc_status": record.qc_status,
                        "qc_issues": json.dumps(record.qc_issues),
                        "reviewed_by": record.reviewed_by,
                        "reviewed_at": record.reviewed_at,
                        "learning_eligible": record.learning_eligible,
                        "scenario_id": record.scenario_id or "",
                        "test_task_id": record.test_task_id or None,
                        "data_quality": record.data_quality or "estimated",
                    },
                )
        except IntegrityError as e:
            raise ValueError("该样品的此属性在此时间点已有实验结果记录") from e

    def get_result_record(self, result_id: str) -> "ExperimentResultRecord | None":
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM experiment.experiment_result_records WHERE result_id = :result_id"),
                {"result_id": result_id},
            ).fetchone()
        if row is None:
            return None
        return ExperimentResultRecord(
            result_id=row[0], experiment_order_id=row[1] or "", sample_id=row[2] or "",
            sample_batch_id=row[3] or "", source_type=row[4] or "", source_system=row[5] or "",
            uploaded_by=row[6] or "", uploaded_at=_iso(row[7]), property_name=row[8] or "",
            value=row[9] if row[9] is not None else 0.0,
            unit=row[10] or "", test_method=row[11] or "",
            test_conditions=_safe_json_load(row[12], default={}),
            instrument_id=row[13] or "", raw_file_uri=row[14] or "", qc_status=row[15] or "PENDING",
            qc_issues=_normalize_qc_issues(_safe_json_load(row[16], default=[])),
            reviewed_by=row[17] or "", reviewed_at=_iso(row[18]) or None,
            learning_eligible=bool(row[19]) if row[19] is not None else False,
            scenario_id=row[20] if row[20] is not None else "",
            test_task_id=row[21] if len(row) > 21 and row[21] is not None else "",
            data_quality=(row[22] if len(row) > 22 and row[22] else "estimated"),
        )

    def list_result_records(self, qc_status: str | None = None, order_id: str | None = None,
                             sample_id: str | None = None,
                             test_task_id: str | None = None) -> list["ExperimentResultRecord"]:
        """查询实验结果记录，支持按 qc_status / order_id / sample_id / test_task_id 过滤。"""
        with self.engine.connect() as conn:
            query = "SELECT * FROM experiment.experiment_result_records"
            conditions = []
            params: dict[str, str] = {}
            if qc_status:
                conditions.append("qc_status = :qc_status")
                params["qc_status"] = qc_status
            if order_id:
                conditions.append("experiment_order_id = :order_id")
                params["order_id"] = order_id
            if sample_id:
                conditions.append("sample_id = :sample_id")
                params["sample_id"] = sample_id
            if test_task_id:
                conditions.append("test_task_id = :test_task_id")
                params["test_task_id"] = test_task_id
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY uploaded_at DESC"
            rows = conn.execute(text(query), params).fetchall()
        return [ExperimentResultRecord(
            result_id=r[0], experiment_order_id=r[1] or "", sample_id=r[2] or "",
            sample_batch_id=r[3] or "", source_type=r[4] or "", source_system=r[5] or "",
            uploaded_by=r[6] or "", uploaded_at=_iso(r[7]), property_name=r[8] or "",
            value=r[9] if r[9] is not None else 0.0,
            unit=r[10] or "", test_method=r[11] or "",
            test_conditions=_safe_json_load(r[12], default={}),
            instrument_id=r[13] or "", raw_file_uri=r[14] or "", qc_status=r[15] or "PENDING",
            qc_issues=_normalize_qc_issues(_safe_json_load(r[16], default=[])),
            reviewed_by=r[17] or "", reviewed_at=_iso(r[18]) or None,
            learning_eligible=bool(r[19]) if r[19] is not None else False,
            scenario_id=r[20] if r[20] is not None else "",
            test_task_id=r[21] if len(r) > 21 and r[21] is not None else "",
            data_quality=(r[22] if len(r) > 22 and r[22] else "estimated"),
        ) for r in rows]

    def count_result_records(self, order_id: str | None = None) -> int | dict[str, int]:
        """统计实验结果记录数量。

        指定 order_id 时返回该任务单下的记录数；否则返回所有任务单的记录数分布。
        """
        with self.engine.connect() as conn:
            if order_id:
                row = conn.execute(
                    text("SELECT COUNT(*) FROM experiment.experiment_result_records "
                         "WHERE experiment_order_id = :order_id"),
                    {"order_id": order_id},
                ).fetchone()
                return row[0] if row else 0

            rows = conn.execute(
                text("SELECT experiment_order_id, COUNT(*) FROM experiment.experiment_result_records "
                     "GROUP BY experiment_order_id")
            ).fetchall()
        return {oid or "": count for oid, count in rows}

    def update_result_qc(self, result_id: str, qc_status: str, qc_issues: list[str],
                         reviewed_by: str = "", learning_eligible: bool = False,
                         data_quality: str | None = None):
        # 评测修复 P2-5：QC 审批通过时可一并更新 data_quality（如 verified）
        with self.engine.begin() as conn:
            conn.execute(
                text("""UPDATE experiment.experiment_result_records
                SET qc_status = :qc_status, qc_issues = CAST(:qc_issues AS JSONB),
                    reviewed_by = :reviewed_by, learning_eligible = :learning_eligible,
                    data_quality = COALESCE(:data_quality, data_quality)
                WHERE result_id = :result_id"""),
                {
                    "qc_status": qc_status,
                    "qc_issues": json.dumps(qc_issues),
                    "reviewed_by": reviewed_by,
                    "learning_eligible": learning_eligible,
                    "data_quality": data_quality,
                    "result_id": result_id,
                },
            )

    def update_order_status(
        self,
        order_id: str,
        status: str,
        approved_by: str = "",
        raw_material_db=None,
        triggered_by: str = "system",
        reason: str = "",
    ):
        """更新任务单状态，强制校验迁移合法性并记录事件日志。

        Args:
            order_id: 任务单 ID
            status: 目标状态字符串（支持旧别名 REJECTED → CANCELLED）
            approved_by: 审批人（若提供则一并更新 approved_by / approved_at）
            raw_material_db: 库存数据库实例，状态变为 COMPLETED 时触发扣减
            triggered_by: 触发迁移的主体标识，写入事件日志
            reason: 迁移原因说明，写入事件日志

        Raises:
            IllegalStateTransitionError: 当 (current_status, new_status) 不在 ALLOWED_TRANSITIONS 中
        """
        # 兼容旧别名（REJECTED → CANCELLED）
        normalized_target = _STATUS_ALIASES.get(status, status)

        # 解析目标状态为枚举
        try:
            to_status_enum = ExperimentOrderStatus(normalized_target)
        except ValueError:
            valid = [s.value for s in ExperimentOrderStatus]
            raise IllegalStateTransitionError(
                "UNKNOWN", status,
                f"Unknown target status: {status!r}. Valid statuses: {valid}",
            )

        # MDM 校验：目标状态值必须在 mdm.status_codes (domain='order') 中存在
        if self._mdm.get_status_code("order", normalized_target) is None:
            raise IllegalStateTransitionError(
                "UNKNOWN", normalized_target,
                f"目标状态 {normalized_target!r} 不在 MDM 主数据 (domain=order) 中",
            )

        # 评测修复 P2-2：读取（行锁）→ 校验 → 更新 → 事件日志放入同一事务，
        # SELECT FOR UPDATE 防止两个并发请求读到相同旧状态后分别通过校验造成迁移覆盖
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT status FROM experiment.experiment_orders "
                     "WHERE order_id = :order_id FOR UPDATE"),
                {"order_id": order_id},
            ).fetchone()

            if row is None:
                raise IllegalStateTransitionError(
                    "UNKNOWN", normalized_target,
                    f"Order {order_id!r} not found",
                )

            current_status_raw = row[0] if row[0] is not None else ""
            current_status_normalized = _STATUS_ALIASES.get(current_status_raw, current_status_raw)

            # 解析当前状态为枚举
            try:
                from_status_enum = ExperimentOrderStatus(current_status_normalized)
            except ValueError:
                # 数据库中存在未知状态（历史脏数据），记录警告并放行
                logger.warning(
                    "Unknown current status %r for order %s; skipping transition validation",
                    current_status_raw, order_id,
                )
                from_status_enum = None

            # 校验迁移合法性
            if from_status_enum is not None:
                allowed = ALLOWED_TRANSITIONS.get(from_status_enum, set())
                if to_status_enum not in allowed:
                    allowed_str = [s.value for s in allowed] if allowed else "none (terminal state)"
                    raise IllegalStateTransitionError(
                        current_status_normalized, normalized_target,
                        f"Allowed transitions from {from_status_enum.value}: {allowed_str}",
                    )

            if approved_by:
                conn.execute(
                    text("UPDATE experiment.experiment_orders SET status = :status, "
                         "approved_by = :approved_by, approved_at = :approved_at "
                         "WHERE order_id = :order_id"),
                    {
                        "status": normalized_target,
                        "approved_by": approved_by,
                        "approved_at": datetime.now(timezone.utc).isoformat(),
                        "order_id": order_id,
                    },
                )
            else:
                conn.execute(
                    text("UPDATE experiment.experiment_orders SET status = :status "
                         "WHERE order_id = :order_id"),
                    {"status": normalized_target, "order_id": order_id},
                )
            conn.execute(
                text("""INSERT INTO experiment.experiment_order_status_transitions
                    (order_id, from_status, to_status, triggered_by, reason, timestamp)
                    VALUES (:order_id, :from_status, :to_status, :triggered_by, :reason, :timestamp)
                """),
                {
                    "order_id": order_id,
                    "from_status": current_status_normalized,
                    "to_status": normalized_target,
                    "triggered_by": triggered_by,
                    "reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        # 状态变为 COMPLETED 时自动触发库存扣减
        if normalized_target == ExperimentOrderStatus.COMPLETED.value:
            if raw_material_db is None:
                # 调用方未传入 raw_material_db 时，尝试从已初始化的 agent 实例自动获取
                try:
                    from .. import api as _api_module
                    _agent_instance = getattr(_api_module, "agent", None)
                    if _agent_instance is not None:
                        raw_material_db = getattr(_agent_instance, "raw_material_db", None)
                except Exception:
                    pass
            if raw_material_db is not None:
                order = self.get_order(order_id)
                if order and order.material_requirements:
                    for item in order.material_requirements:
                        mid = item.get("material_id", "")
                        qty = item.get("required_quantity", 1.0)
                        if mid:
                            try:
                                raw_material_db.deduct_inventory(mid, qty)
                                logger.info("库存扣减: material_id=%s, amount=%s", mid, qty)
                            except Exception as e:
                                logger.warning("库存扣减失败: material_id=%s, error=%s", mid, e)

    def save_notification(self, order_id: str, assignee: str, message: str) -> str:
        """记录一条通知到 notifications 表，返回 notification_id。"""
        notification_id = f"NTF_{uuid.uuid4().hex[:8]}"
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.notifications
                (notification_id, order_id, assignee, message, created_at, read)
                VALUES (:notification_id, :order_id, :assignee, :message, :created_at, FALSE)
                """),
                {
                    "notification_id": notification_id,
                    "order_id": order_id,
                    "assignee": assignee,
                    "message": message,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        return notification_id


class ExperimentController:
    """Controller for self-driving lab experiment hardware with real data flow."""

    def __init__(self, hardware_config: dict | None = None, db_path: str = "data/experiments.db", run_mode: str = "demo",
                 scp_client_pool=None, approval_engine=None):
        self.hardware_config = hardware_config or {}
        self._store = ExperimentDataStore(db_path)
        self._subscribers: list[callable] = []
        self.run_mode = run_mode
        self._scp_client_pool = scp_client_pool
        self._approval_engine = approval_engine
        # MDM 参考字典 Store 复用，避免每次校验都新建实例
        from ..mdm.reference_dict import ReferenceDictStore
        self._mdm = ReferenceDictStore()

    def create_order(self, order: "ExperimentOrder") -> "ExperimentOrder":
        """创建实验任务单。

        若 order_id 为空则自动生成；若 status 为空则默认 DRAFT。
        保存后返回带填充字段的 order。
        """
        if not order.order_id:
            order.order_id = f"ORD_{uuid.uuid4().hex[:10].upper()}"
        if not order.status:
            order.status = ExperimentOrderStatus.DRAFT.value
        if not order.created_at:
            order.created_at = datetime.now(timezone.utc).isoformat()
        self._store.save_order(order)
        return order

    def ensure_draft_order_for_candidate(
        self,
        candidate_id: str,
        project_id: str = "",
        scenario_id: str = "",
    ) -> "ExperimentOrder | None":
        """Task 14.2：候选材料 → 实验任务自动关联。

        如果 candidate_id 存在但当前候选无任何关联实验任务单，
        自动创建一个 DRAFT 状态的实验任务单并关联 candidate_id。

        Args:
            candidate_id: 候选材料 ID（必填）
            project_id: 关联项目 ID（可选）
            scenario_id: 关联研发场景 ID（可选）

        Returns:
            新创建的 ExperimentOrder；若已存在关联订单或 candidate_id 为空，返回 None
        """
        if not candidate_id:
            return None
        with self._store.engine.connect() as conn:
            row = conn.execute(
                text("SELECT order_id FROM experiment.experiment_orders "
                     "WHERE candidate_id = :cid LIMIT 1"),
                {"cid": candidate_id},
            ).fetchone()
        if row is not None:
            return None
        order = ExperimentOrder(
            order_id=f"ORD_{uuid.uuid4().hex[:10].upper()}",
            project_id=project_id,
            candidate_id=candidate_id,
            status=ExperimentOrderStatus.DRAFT.value,
            ai_draft=True,
            scenario_id=scenario_id,
            notes="候选材料自动创建的实验任务草稿",
        )
        self._store.save_order(order)
        return order

    def submit_task(self, task: ExperimentTask) -> str:
        self._store.save_task(task)
        return task.task_id

    def start_task(self, task_id: str) -> bool:
        task = self._store.get_task(task_id)
        if not task:
            return False
        task.status = ExperimentStatus.RUNNING
        task.started_at = datetime.now(timezone.utc).isoformat()
        self._store.save_task(task)
        return True

    def complete_task(self, task_id: str, result: ExperimentResult) -> bool:
        task = self._store.get_task(task_id)
        if not task:
            return False
        task.status = ExperimentStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc).isoformat()
        self._store.save_task(task)
        self._store.save_result(result)
        self._notify_subscribers(result)
        return True

    def fail_task(self, task_id: str, error_message: str) -> bool:
        task = self._store.get_task(task_id)
        if not task:
            return False
        task.status = ExperimentStatus.FAILED
        task.completed_at = datetime.now(timezone.utc).isoformat()
        self._store.save_task(task)
        self._store.save_result(ExperimentResult(
            task_id=task_id, experiment_type=task.experiment_type,
            status=ExperimentStatus.FAILED, error_message=error_message,
        ))
        return True

    def get_task(self, task_id: str) -> ExperimentTask | None:
        return self._store.get_task(task_id)

    def get_result(self, task_id: str) -> ExperimentResult | None:
        return self._store.get_result(task_id)

    def list_tasks(self, status: ExperimentStatus | None = None) -> list[ExperimentTask]:
        return self._store.list_tasks(status)

    def cancel_task(self, task_id: str) -> bool:
        task = self._store.get_task(task_id)
        if not task or task.status == ExperimentStatus.COMPLETED:
            return False
        task.status = ExperimentStatus.CANCELLED
        self._store.save_task(task)
        return True

    async def draft_protocol_with_scp(self, order: ExperimentOrder) -> ExperimentOrder:
        """Generate experiment protocol using SCP protocol_draft tool.

        AI-generated protocols are created as DRAFT status.
        Only after approval engine passes can the task become executable.

        注：scp_protocol_draft 在能力契约中标注为"内部 LLM 能力，无 SCP 远端"，
        不存在可调用的远端 server。协议草案由 ECML 引擎或 LLM 节点内部生成，
        此方法仅作占位与提示，不发起 SCP 远程调用。
        """
        if self._scp_client_pool is None:
            order.notes = (order.notes + "; " if order.notes else "") + "SCP 不可用，协议未生成"
            return order

        # scp_protocol_draft 无远端 server 绑定（catalog 中 server_id 为空），
        # 直接调用 SCP 会因 server_id 错误而失败。协议生成由 LLM 引擎处理。
        order.notes = (order.notes + "; " if order.notes else "") + "协议草案由 LLM 引擎生成（scp_protocol_draft 为内部能力，无 SCP 远端）"
        return order

    def validate_protocol(self, order: ExperimentOrder, known_equipment: list[str] | None = None) -> list[str]:
        """Validate an experiment protocol for common issues.

        Returns list of validation issues. Empty list means valid.
        Issues include: missing safety info, non-standard units, references to non-existent equipment.
        """
        issues: list[str] = []

        # Check for missing safety info
        if not order.procedure:
            issues.append("实验步骤为空")
        else:
            for i, step in enumerate(order.procedure):
                if not isinstance(step, dict):
                    continue
                if not step.get("safety_notes") and not step.get("hazards"):
                    issues.append(f"步骤 {i + 1} 缺少安全信息")
                # Check for non-standard units
                for key in ("temperature", "duration_min", "pressure", "voltage"):
                    if key in step:
                        val = step[key]
                        if isinstance(val, str) and not val.replace(".", "").replace("-", "").isdigit():
                            issues.append(f"步骤 {i + 1} 的 {key} 值包含非标准单位: {val}")

        # Check for references to non-existent equipment
        if known_equipment is not None and hasattr(order, 'procedure'):
            for step in order.procedure:
                if isinstance(step, dict):
                    eq = step.get("equipment", "")
                    if eq and known_equipment and eq not in known_equipment:
                        issues.append(f"引用了不存在的设备: {eq}")

        if issues:
            order.status = "VALIDATION_FAILED"
            order.notes = (order.notes + "; " if order.notes else "") + f"验证失败: {'; '.join(issues)}"
        return issues

    def approve_order(self, order: ExperimentOrder, approved_by: str = "") -> ExperimentOrder:
        """Run approval engine on draft order. Only after approval passes can the task become executable."""
        if self._approval_engine is not None:
            decision = self._approval_engine.judge(
                candidate={"order_id": order.order_id, "status": order.status},
                estimated_cost=order.acceptance_criteria.get("estimated_cost", 0.0),
                model_confidence=order.acceptance_criteria.get("model_confidence", 1.0),
            )
            if decision.action == "BLOCK":
                order.status = "VALIDATION_FAILED"
                order.notes = (order.notes + "; " if order.notes else "") + f"审批拒绝: {decision.risk_factors}"
                return order
            elif decision.action == "REQUIRE_MANUAL":
                order.status = "PENDING_APPROVAL"
                order.notes = (order.notes + "; " if order.notes else "") + "需要人工审批"
                return order
            # AUTO_APPROVE falls through
        order.status = "APPROVED"
        order.approved_by = approved_by
        order.approved_at = datetime.now(timezone.utc).isoformat()
        return order

    def notify_assignee(self, order_id: str, message: str) -> str | None:
        """通知实验任务负责人，记录到 notifications 表。返回 notification_id 或 None。"""
        order = self._store.get_order(order_id)
        if not order or not order.assignee:
            logger.warning("notify_assignee: 任务 %s 无负责人或不存在，跳过通知", order_id)
            return None
        return self._store.save_notification(order_id, order.assignee, message)

    def subscribe(self, callback):
        self._subscribers.append(callback)

    def unsubscribe(self, callback):
        self._subscribers = [s for s in self._subscribers if s is not callback]

    def _notify_subscribers(self, result: ExperimentResult):
        for subscriber in self._subscribers:
            try:
                subscriber(result)
            except Exception as e:
                logger.warning(f"Subscriber callback failed: {e}")

    def execute_experiment(self, recipe: dict, experiment_type: ExperimentType) -> ExperimentResult:
        task_id = str(uuid.uuid4())[:12]
        task = ExperimentTask(
            task_id=task_id, experiment_type=experiment_type, recipe=recipe,
        )
        self.submit_task(task)
        self.start_task(task_id)

        if self.run_mode == "production":
            # 生产模式：不生成模拟数据，等待真实数据输入
            task.status = ExperimentStatus.PENDING
            task.started_at = None
            self._store.save_task(task)
            result = ExperimentResult(
                task_id=task_id, experiment_type=experiment_type,
                status=ExperimentStatus.PENDING,
                measured_values={},
                metadata={"recipe": recipe, "timestamp": datetime.now(timezone.utc).isoformat(), "mode": "production_waiting"},
            )
            return result

        # demo 模式：保留原有模拟逻辑
        measured = self._simulate_measurement(experiment_type, recipe)
        result = ExperimentResult(
            task_id=task_id, experiment_type=experiment_type,
            status=ExperimentStatus.COMPLETED,
            measured_values=measured,
            metadata={"recipe": recipe, "timestamp": datetime.now(timezone.utc).isoformat()},
        )
        self.complete_task(task_id, result)
        return result

    def _simulate_measurement(self, exp_type: ExperimentType, recipe: dict) -> dict:
        import hashlib
        import numpy as np
        h = int(hashlib.md5(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(h)
        # 使用 [0,1) 区间均匀分布生成更合理的模拟测量值
        u = rng.random()
        u2 = rng.random()
        u3 = rng.random()

        if exp_type == ExperimentType.IONIC_CONDUCTIVITY:
            base_conductivity = 1e-4 + u * 1e-3
            return {
                "ionic_conductivity_S_cm": base_conductivity,
                "activation_energy_eV": 0.2 + u2 * 0.3,
                "temperature_K": 298.15,
                "frequency_Hz": 1e6,
            }
        elif exp_type == ExperimentType.EIS:
            return {
                "bulk_resistance_ohm": 10 + u * 90,
                "charge_transfer_resistance_ohm": 50 + u2 * 450,
                "warburg_coefficient": 0.5 + u3 * 0.5,
            }
        elif exp_type == ExperimentType.CV:
            return {
                "oxidation_potential_V": 4.2 + u * 0.5,
                "reduction_potential_V": 3.5 + u2 * 0.5,
                "peak_separation_V": 0.1 + u3 * 0.1,
                "coulombic_efficiency": 0.95 + u * 0.05,
            }
        elif exp_type == ExperimentType.XRD:
            return {
                "peak_2theta_deg": [18.5, 20.3, 23.8, 27.1, 31.5],
                "peak_intensity_counts": [1000 + int(u * 500), 800 + int(u2 * 300), 600 + int(u3 * 200), 400 + int(u * 100), 200 + int(u2 * 50)],
                "crystallinity_percent": 45.0 + u * 30,
            }
        elif exp_type == ExperimentType.SEM:
            return {
                "particle_size_nm": 500 + int(u * 5000),
                "morphology": "spherical" if h % 2 == 0 else "irregular",
                "surface_area_m2_g": 1.0 + u2 * 10,
            }
        elif exp_type == ExperimentType.DSC:
            return {
                "glass_transition_temp_C": 40 + u * 100,
                "melting_point_C": 65 + u2 * 50,
                "crystallization_temp_C": 30 + u3 * 40,
                "enthalpy_fusion_J_g": 50 + u * 200,
            }
        elif exp_type == ExperimentType.TGA:
            return {
                "decomposition_temp_C": 250 + u * 200,
                "weight_loss_percent": 5 + u2 * 30,
                "residual_mass_percent": 60 + u3 * 30,
            }
        elif exp_type == ExperimentType.ELECTROCHEMICAL:
            return {
                "open_circuit_voltage_V": 2.5 + u * 2,
                "discharge_capacity_mAh_g": 100.0 + u2 * 100,
                "charge_capacity_mAh_g": 95.0 + u3 * 105,
                "coulombic_efficiency_pct": 90.0 + u * 10,
                "voltage_plateau_V": 3.0 + u2 * 1.5,
                "capacity_retention_pct_100cyc": 70.0 + u3 * 30,
                "internal_resistance_ohm": 5.0 + u * 4.5,
                "rate_capability_1C_pct": 85.0 + u2 * 15,
            }
        else:
            return {
                "raw_measurement": float(u * 1000),
                "experiment_type": str(exp_type),
                "note": "placeholder - real hardware integration required",
            }

    def detect_prediction_deviation(self, order_id: str, predicted_values: dict,
                                    threshold: float = 0.2) -> list[dict]:
        """检测实测值与预测值的偏差。

        Args:
            order_id: 关联的实验任务ID
            predicted_values: 预测值字典 {property_name: value}
            threshold: 偏差阈值（默认20%）

        Returns:
            异常样本列表 [{result_id, sample_id, property_name, predicted,
                          measured, deviation_pct, is_anomaly}]
        """
        if not predicted_values:
            return []
        records = self._store.list_result_records(order_id=order_id)
        results: list[dict] = []
        for rec in records:
            predicted = predicted_values.get(rec.property_name)
            if predicted is None:
                continue
            try:
                predicted_val = float(predicted)
            except (TypeError, ValueError):
                continue
            # 转 float 后再判零，避免字符串 "0"/"0.0" 绕过检查导致 ZeroDivisionError
            if predicted_val == 0:
                continue
            deviation_pct = abs(rec.value - predicted_val) / abs(predicted_val) * 100.0
            is_anomaly = deviation_pct > threshold * 100.0
            results.append({
                "result_id": rec.result_id,
                "sample_id": rec.sample_id,
                "property_name": rec.property_name,
                "predicted": predicted_val,
                "measured": rec.value,
                "unit": rec.unit,
                "deviation_pct": round(deviation_pct, 2),
                "is_anomaly": is_anomaly,
            })
        return results

    def mark_anomaly_samples(self, result_ids: list[str], analysis: str,
                             reviewed_by: str = "DEVIATION_CHECKER") -> int:
        """将指定结果记录标记为异常（REQUIRES_REVIEW），并记录交叉验证分析。

        Args:
            result_ids: 需要标记的结果记录 ID 列表
            analysis: 交叉验证分析结果文本
            reviewed_by: 标记操作者标识（如 user_id），默认 DEVIATION_CHECKER

        Returns:
            成功标记的记录数
        """
        marked = 0
        analysis_tag = "预测偏差异常"
        analysis_entry = f"交叉验证分析: {analysis}" if analysis else ""
        for rid in result_ids:
            rec = self._store.get_result_record(rid)
            if not rec:
                continue
            issues = list(rec.qc_issues)
            if analysis_tag not in issues:
                issues.append(analysis_tag)
            if analysis_entry and analysis_entry not in issues:
                issues.append(analysis_entry)
            self._store.update_result_qc(
                rid, "REQUIRES_REVIEW", issues,
                reviewed_by=reviewed_by,
                learning_eligible=False,
            )
            marked += 1
        return marked
