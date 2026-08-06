"""Candidate material store for persisting discovery results.

Stores both crystal and polymer candidates with full JSON serialization,
enabling cross-module traceability (e.g. sample → candidate → discovery).
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from sqlalchemy import text
from enum import Enum
import hashlib
import json
import logging
from typing import Any

from ..db import get_engine
from ..generation.crystal_candidate_generator import _normalize_formula

logger = logging.getLogger(__name__)


class CandidateStatus(str, Enum):
    """候选材料两层流程状态机。

    配方设计阶段（第一层，formulator 主导）：
        screening → feasible
    工艺深化阶段（第二层，process_engineer 主导）：
        feasible → process_planning → process_confirmed → ready_for_experiment
    淘汰：screening / feasible / process_planning 均可 → rejected
    """
    SCREENING = "screening"                    # 初筛中（配方设计人员）
    FEASIBLE = "feasible"                      # 初筛通过，待工艺深化
    PROCESS_PLANNING = "process_planning"      # 工艺方案制定中（工艺人员）
    PROCESS_CONFIRMED = "process_confirmed"    # 工艺方案已确定
    READY_FOR_EXPERIMENT = "ready_for_experiment"  # 可下达实验
    REJECTED = "rejected"                      # 淘汰


# 合法状态迁移图
CANDIDATE_ALLOWED_TRANSITIONS: dict[CandidateStatus, set[CandidateStatus]] = {
    CandidateStatus.SCREENING: {CandidateStatus.FEASIBLE, CandidateStatus.REJECTED},
    CandidateStatus.FEASIBLE: {CandidateStatus.PROCESS_PLANNING, CandidateStatus.REJECTED},
    CandidateStatus.PROCESS_PLANNING: {CandidateStatus.PROCESS_CONFIRMED, CandidateStatus.REJECTED},
    CandidateStatus.PROCESS_CONFIRMED: {CandidateStatus.READY_FOR_EXPERIMENT, CandidateStatus.REJECTED},
    CandidateStatus.READY_FOR_EXPERIMENT: set(),  # 已可下达实验，终态
    CandidateStatus.REJECTED: set(),  # 终态
}

# 各状态对应的主导角色（用于负责人字段与权限记录）
CANDIDATE_STATUS_ROLE: dict[CandidateStatus, str] = {
    CandidateStatus.SCREENING: "formulator",
    CandidateStatus.FEASIBLE: "formulator",
    CandidateStatus.PROCESS_PLANNING: "process_engineer",
    CandidateStatus.PROCESS_CONFIRMED: "process_engineer",
    CandidateStatus.READY_FOR_EXPERIMENT: "process_engineer",
    CandidateStatus.REJECTED: "",
}


class IllegalCandidateTransitionError(ValueError):
    """候选材料非法状态迁移。"""

    def __init__(self, from_status: str, to_status: str, reason: str = ""):
        self.from_status = from_status
        self.to_status = to_status
        self.reason = reason
        msg = f"Illegal candidate transition: {from_status} -> {to_status}"
        if reason:
            msg = f"{msg}. {reason}"
        super().__init__(msg)


def _iso(value) -> str:
    """将 datetime 或字符串转换为 ISO 字符串；None 返回空字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class CandidateRecord(BaseModel):
    """Unified record for crystal/polymer candidates.

    业务链路：任务 1 → N 候选材料。task_id / project_id 由 0009 迁移新增，nullable。
    """
    candidate_id: str = ""
    candidate_type: str = ""  # crystal / polymer
    name: str = ""  # formula for crystal, name for polymer
    smiles: str = ""  # psmiles/smiles for polymer, empty for crystal
    source: str = ""  # discovery source (e.g. Materials Project, LLM)
    scenario_id: str = ""  # P0-001：关联研发场景 ID
    task_id: str = ""  # 业务链路：关联 projects.tasks(task_id)
    project_id: str = ""  # 业务链路：关联 projects.projects(project_id)（冗余字段，便于按项目查询）
    multi_objective_score: float = 0.0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # P2-输出：两层流程状态机字段
    status: str = CandidateStatus.SCREENING.value  # 见 CandidateStatus
    owner: str = ""  # 当前责任人（用户名）
    assigned_role: str = ""  # 当前环节角色 formulator / process_engineer
    # 评测修复 P1-004：预测结果顶层字段（模型版本/置信度/预测值/预测时间），
    # 持久化于 data JSONB 内，读写时与顶层字段双向同步
    prediction: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)  # full candidate JSON


class CandidateStore:
    """PostgreSQL-backed persistent storage for candidate materials."""

    def __init__(self, db_path: str = "data/candidates.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.engine = get_engine()
        self._init_db()

    def _init_db(self):
        # 表已由 alembic 迁移创建，这里仅保留 IF NOT EXISTS 兜底
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.candidates (
                    candidate_id TEXT PRIMARY KEY,
                    candidate_type TEXT,
                    name TEXT,
                    smiles TEXT,
                    source TEXT,
                    multi_objective_score DOUBLE PRECISION,
                    created_at TIMESTAMPTZ,
                    data JSONB,
                    scenario_id TEXT,
                    task_id TEXT,
                    project_id TEXT,
                    content_hash TEXT
                )
            """))
            # 兜底：为已有表补列（alembic 迁移已处理的环境无需执行）
            conn.execute(text(
                "ALTER TABLE experiment.candidates "
                "ADD COLUMN IF NOT EXISTS content_hash TEXT"
            ))
            # 两层流程状态机字段兜底
            conn.execute(text(
                "ALTER TABLE experiment.candidates "
                "ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'screening'"
            ))
            conn.execute(text(
                "ALTER TABLE experiment.candidates "
                "ADD COLUMN IF NOT EXISTS owner TEXT DEFAULT ''"
            ))
            conn.execute(text(
                "ALTER TABLE experiment.candidates "
                "ADD COLUMN IF NOT EXISTS assigned_role TEXT DEFAULT ''"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_candidates_type "
                "ON experiment.candidates(candidate_type)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_candidates_name "
                "ON experiment.candidates(name)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_candidates_scenario "
                "ON experiment.candidates(scenario_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_candidates_task_id "
                "ON experiment.candidates(task_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_candidates_content_hash "
                "ON experiment.candidates(content_hash)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_candidates_status "
                "ON experiment.candidates(status)"
            ))

    @staticmethod
    def _compute_content_hash(formula: str, target_application: str) -> str:
        """计算 content_hash = sha256(normalized_formula + "|" + target_application)。

        D-08：去重粒度为"化学式 + 目标应用"。归一化化学式复用
        _normalize_formula（pymatgen reduced_formula）。
        """
        normalized = _normalize_formula(formula)
        payload = f"{normalized}|{target_application or ''}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def find_by_content_hash(
        self, formula: str, target_application: str = ""
    ) -> CandidateRecord | None:
        """按 content_hash 查询已存在的候选。

        content_hash = sha256(normalized_formula + "|" + target_application)。
        返回已存在的候选或 None。
        """
        content_hash = self._compute_content_hash(formula, target_application)
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT candidate_id, candidate_type, name, smiles, source, "
                     "scenario_id, task_id, project_id, "
                     "multi_objective_score, created_at, data, "
                     "status, owner, assigned_role "
                     "FROM experiment.candidates WHERE content_hash = :content_hash"),
                {"content_hash": content_hash},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    _SELECT_COLS = (
        "candidate_id, candidate_type, name, smiles, source, scenario_id, task_id, "
        "project_id, multi_objective_score, created_at, data, status, owner, assigned_role"
    )

    def save(self, record: CandidateRecord) -> CandidateRecord:
        # P1-004：prediction 顶层字段同步进 data JSONB，保证持久化后读回一致
        if record.prediction and record.data.get("prediction") != record.prediction:
            record.data = {**record.data, "prediction": record.prediction}
        # T-020：基于 content_hash 去重——化学式 + 目标应用相同则跳过创建
        formula = record.data.get("formula") or record.name
        target_application = record.data.get("target_application", "")
        if formula:
            content_hash = self._compute_content_hash(formula, target_application)
            existing = self.find_by_content_hash(formula, target_application)
            if existing is not None:
                logger.info(
                    "候选已存在，跳过创建 content_hash=%s candidate_id=%s",
                    content_hash, existing.candidate_id,
                )
                return existing
        else:
            content_hash = None

        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.candidates
                (candidate_id, candidate_type, name, smiles, source, scenario_id,
                 task_id, project_id, multi_objective_score, created_at, data, content_hash,
                 status, owner, assigned_role)
                VALUES (:candidate_id, :candidate_type, :name, :smiles, :source, :scenario_id,
                 :task_id, :project_id, :multi_objective_score, :created_at, CAST(:data AS JSONB),
                 :content_hash, :status, :owner, :assigned_role)
                ON CONFLICT (candidate_id) DO UPDATE SET
                    candidate_type = EXCLUDED.candidate_type,
                    name = EXCLUDED.name,
                    smiles = EXCLUDED.smiles,
                    source = EXCLUDED.source,
                    scenario_id = EXCLUDED.scenario_id,
                    task_id = EXCLUDED.task_id,
                    project_id = EXCLUDED.project_id,
                    multi_objective_score = EXCLUDED.multi_objective_score,
                    created_at = EXCLUDED.created_at,
                    data = EXCLUDED.data,
                    content_hash = EXCLUDED.content_hash,
                    status = EXCLUDED.status,
                    owner = EXCLUDED.owner,
                    assigned_role = EXCLUDED.assigned_role
                """),
                {
                    "candidate_id": record.candidate_id,
                    "candidate_type": record.candidate_type,
                    "name": record.name,
                    "smiles": record.smiles,
                    "source": record.source,
                    "scenario_id": record.scenario_id,
                    # FK 约束不允许空字符串，需转为 NULL（PostgreSQL FK 仅对 NULL 跳过校验）
                    "task_id": record.task_id or None,
                    "project_id": record.project_id or None,
                    "multi_objective_score": record.multi_objective_score,
                    "created_at": record.created_at,
                    "data": json.dumps(record.data, ensure_ascii=False),
                    "content_hash": content_hash,
                    "status": record.status or CandidateStatus.SCREENING.value,
                    "owner": record.owner or "",
                    "assigned_role": record.assigned_role or "",
                },
            )
        return record

    def get(self, candidate_id: str) -> CandidateRecord | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.candidates WHERE candidate_id = :candidate_id"),
                {"candidate_id": candidate_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_all(self, candidate_type: str = "", scenario_id: str = "",
                 task_id: str = "", project_id: str = "") -> list[CandidateRecord]:
        """查询候选材料列表。

        支持按 candidate_type / scenario_id / task_id / project_id 过滤，
        所有参数可选，组合使用 AND 关系。
        """
        with self.engine.connect() as conn:
            conditions = []
            params: dict[str, Any] = {}
            if candidate_type:
                conditions.append("candidate_type = :candidate_type")
                params["candidate_type"] = candidate_type
            if scenario_id:
                conditions.append("scenario_id = :scenario_id")
                params["scenario_id"] = scenario_id
            if task_id:
                conditions.append("task_id = :task_id")
                params["task_id"] = task_id
            if project_id:
                conditions.append("project_id = :project_id")
                params["project_id"] = project_id
            query = (
                f"SELECT {self._SELECT_COLS} "
                "FROM experiment.candidates"
            )
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(text(query), params).fetchall()
        return [self._row_to_record(r) for r in rows]

    def delete(self, candidate_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM experiment.candidates WHERE candidate_id = :candidate_id"),
                {"candidate_id": candidate_id},
            )
            return cur.rowcount > 0

    def update_status(self, candidate_id: str, to_status: str, actor_role: str = "",
                      owner: str = "", triggered_by: str = "system",
                      reason: str = "") -> CandidateRecord:
        """更新候选材料状态，强制校验两层状态机迁移图与角色归属。

        角色校验（采用角色）：
            screening → feasible / rejected     配方设计人员（formulator）
            feasible  → process_planning / rejected   交棒给工艺人员（process_engineer）
            process_planning → process_confirmed / rejected   工艺人员（process_engineer）
            process_confirmed → ready_for_experiment / rejected   工艺人员（process_engineer）

        各状态对应的允许角色见 CANDIDATE_STATUS_ROLE。

        Args:
            candidate_id: 候选材料 ID
            to_status: 目标状态（screening / feasible / process_planning /
                       process_confirmed / ready_for_experiment / rejected）
            actor_role: 操作者角色（formulator / process_engineer），传入则强制校验
            owner: 新的责任人（用户名）
            triggered_by: 触发主体标识
            reason: 迁移原因

        Raises:
            IllegalCandidateTransitionError: 非法迁移或角色不符
        """
        record = self.get(candidate_id)
        if record is None:
            raise IllegalCandidateTransitionError(
                "UNKNOWN", to_status, f"Candidate {candidate_id!r} not found",
            )

        from_status = record.status or CandidateStatus.SCREENING.value
        try:
            from_enum = CandidateStatus(from_status)
            to_enum = CandidateStatus(to_status)
        except ValueError as e:
            raise IllegalCandidateTransitionError(from_status, to_status, str(e)) from e

        allowed = CANDIDATE_ALLOWED_TRANSITIONS.get(from_enum, set())
        if to_enum not in allowed:
            allowed_str = [s.value for s in allowed] if allowed else "none (terminal state)"
            raise IllegalCandidateTransitionError(
                from_status, to_status,
                f"Allowed transitions from {from_enum.value}: {allowed_str}",
            )

        # 角色校验：目标状态对应的主导角色
        expected_role = CANDIDATE_STATUS_ROLE.get(to_enum, "")
        if actor_role and expected_role and actor_role != expected_role:
            raise IllegalCandidateTransitionError(
                from_status, to_status,
                f"状态 {to_enum.value} 须由 {expected_role} 角色执行，当前角色 {actor_role!r}",
            )

        with self.engine.begin() as conn:
            if owner:
                conn.execute(
                    text("UPDATE experiment.candidates SET status = :status, "
                         "owner = :owner, assigned_role = :assigned_role "
                         "WHERE candidate_id = :candidate_id"),
                    {
                        "status": to_status,
                        "owner": owner,
                        "assigned_role": expected_role,
                        "candidate_id": candidate_id,
                    },
                )
            else:
                conn.execute(
                    text("UPDATE experiment.candidates SET status = :status, "
                         "assigned_role = :assigned_role "
                         "WHERE candidate_id = :candidate_id"),
                    {
                        "status": to_status,
                        "assigned_role": expected_role,
                        "candidate_id": candidate_id,
                    },
                )
        return self.get(candidate_id)  # type: ignore[return-value]

    def _row_to_record(self, row) -> CandidateRecord:
        # 防御性类型转换：旧表数据可能存在 None / 类型错位
        def _str(v) -> str:
            if v is None:
                return ""
            return str(v)

        def _float(v) -> float:
            if v is None:
                return 0.0
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0

        # data 字段为 JSONB，psycopg3 自动解析为 dict；兼容历史字符串
        data_val = row[10] if len(row) > 10 and row[10] is not None else {}
        if isinstance(data_val, str):
            try:
                data_val = json.loads(data_val)
            except (json.JSONDecodeError, TypeError):
                data_val = {}

        # P1-004：prediction 持久化在 data JSONB 中，读取时提升为顶层字段
        prediction_val = data_val.get("prediction")
        if not isinstance(prediction_val, dict):
            prediction_val = {}

        return CandidateRecord(
            candidate_id=_str(row[0]),
            candidate_type=_str(row[1]),
            name=_str(row[2]),
            smiles=_str(row[3]),
            source=_str(row[4]),
            scenario_id=_str(row[5]) if len(row) > 5 else "",
            task_id=_str(row[6]) if len(row) > 6 else "",
            project_id=_str(row[7]) if len(row) > 7 else "",
            multi_objective_score=_float(row[8]) if len(row) > 8 else 0.0,
            created_at=_iso(row[9]) if len(row) > 9 else "",
            prediction=prediction_val,
            data=data_val,
            status=_str(row[11]) if len(row) > 11 else CandidateStatus.SCREENING.value,
            owner=_str(row[12]) if len(row) > 12 else "",
            assigned_role=_str(row[13]) if len(row) > 13 else "",
        )