"""Candidate material store for persisting discovery results.

Stores both crystal and polymer candidates with full JSON serialization,
enabling cross-module traceability (e.g. sample → candidate → discovery).
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from sqlalchemy import text
import hashlib
import json
import logging
from typing import Any

from ..db import get_engine
from ..generation.crystal_candidate_generator import _normalize_formula

logger = logging.getLogger(__name__)


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
                     "multi_objective_score, created_at, data "
                     "FROM experiment.candidates WHERE content_hash = :content_hash"),
                {"content_hash": content_hash},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

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
                 task_id, project_id, multi_objective_score, created_at, data, content_hash)
                VALUES (:candidate_id, :candidate_type, :name, :smiles, :source, :scenario_id,
                 :task_id, :project_id, :multi_objective_score, :created_at, CAST(:data AS JSONB),
                 :content_hash)
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
                    content_hash = EXCLUDED.content_hash
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
                },
            )
        return record

    def get(self, candidate_id: str) -> CandidateRecord | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT candidate_id, candidate_type, name, smiles, source, "
                     "scenario_id, task_id, project_id, "
                     "multi_objective_score, created_at, data "
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
                "SELECT candidate_id, candidate_type, name, smiles, source, "
                "scenario_id, task_id, project_id, "
                "multi_objective_score, created_at, data "
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
        )
