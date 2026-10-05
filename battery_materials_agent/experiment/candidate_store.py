"""Candidate material store for persisting discovery results.

Stores both crystal and polymer candidates with full JSON serialization,
enabling cross-module traceability (e.g. sample → candidate → discovery).
"""

from __future__ import annotations
from pydantic import BaseModel, Field, computed_field
from datetime import datetime, timezone
from sqlalchemy import text
from enum import Enum
import hashlib
import json
import logging
from typing import Any

from ..db import get_engine, get_tenant, tenant_filter
from ..generation.formula_utils import normalize_formula

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


# ADR-0001 术语分层：候选来源 → 数据可信度档的唯一权威映射。
# 前端（EvidenceBadge 等）必须消费本派生结果，不得自行从 property_source 推导。
# - estimated：查表/规则/启发式/结构数据库来源（未经带真实权重模型验证）
# - predicted：LLM 生成来源（领域决策 2026-08-23：按模型预测展示）
CANDIDATE_SOURCE_EVIDENCE_LEVEL: dict[str, str] = {
    # 聚合物生成器来源
    "engineering_plastics": "estimated",   # 工程塑料查表法（REFERENCE_PROPERTIES）
    "rule_based": "estimated",             # 规则启发式
    "derivative": "estimated",             # 派生变体（启发式增量）
    "known": "estimated",                  # 内置已知材料库
    "internlm_generated": "predicted",     # 领域决策：LLM 生成 → 模型预测
    "llm_generated": "predicted",          # 领域决策：LLM 生成 → 模型预测
    # 晶体生成器来源（结构数据库/生成模型，属性未经带权重模型验证 → 保守估算）
    "gnome_pg": "estimated",
    "gnome_mp_mirror": "estimated",
    "gnome_local": "estimated",
    "materials_project": "estimated",
    "local_database": "estimated",
}


def resolve_candidate_evidence_level(source: str, data: dict | None) -> str:
    """解析候选的权威可信度档。

    优先级：候选 data 中显式 evidence_level（逐条标注逃生通道）>
    来源映射 > 默认 estimated（ADR-0001 保守取向：无法证明是真实权重模型的不得称预测）。
    """
    if isinstance(data, dict):
        explicit = str(data.get("evidence_level") or "").strip().lower()
        if explicit:
            return explicit
        # T06：实验证据优先——有 qc 通过 / verified 数据质量 / learning_eligible
        # 时，候选性能值属于实测，绝不能误标 estimated。
        qc = str(data.get("qc_status") or "").upper()
        dq = str(data.get("data_quality") or "").lower()
        if qc in {"VALID", "VERIFIED"} and dq in {"verified", "measured"}:
            return "measured"
        if dq in {"simulated"}:
            return "simulated"
    return CANDIDATE_SOURCE_EVIDENCE_LEVEL.get(source or "", "estimated")


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
    # P3-B2：合成可行性（best feasibility_score + 关联任务/时间），持久化于 data JSONB
    synthesis_feasibility: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str = ""  # 多租户隔离：归属租户；空=default
    data: dict[str, Any] = Field(default_factory=dict)  # full candidate JSON

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_level(self) -> str:
        """ADR-0001 权威可信度档（随 model_dump 输出，前端徽标唯一数据源）。

        仅作用于 API 序列化边界：save() 按显式列参数落库、content_hash 只由
        formula+target_application 派生，本字段不进入存储内容与去重逻辑。
        """
        return resolve_candidate_evidence_level(self.source, self.data)


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
        normalize_formula（pymatgen reduced_formula）。
        """
        normalized = normalize_formula(formula)
        payload = f"{normalized}|{target_application or ''}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def find_by_content_hash(
        self, formula: str, target_application: str = ""
    ) -> CandidateRecord | None:
        """按 content_hash 查询已存在的候选。

        content_hash = sha256(normalized_formula + "|" + target_application)。
        返回已存在的候选或 None。查询按当前租户隔离。
        """
        content_hash = self._compute_content_hash(formula, target_application)
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT candidate_id, candidate_type, name, smiles, source, "
                     "scenario_id, task_id, project_id, "
                     "multi_objective_score, created_at, data, "
                     "status, owner, assigned_role, tenant_id "
                     "FROM experiment.candidates "
                     f"WHERE content_hash = :content_hash AND {tenant_filter()}"),
                {"content_hash": content_hash, "tenant_id": get_tenant()},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    _SELECT_COLS = (
        "candidate_id, candidate_type, name, smiles, source, scenario_id, task_id, "
        "project_id, multi_objective_score, created_at, data, status, owner, "
        "assigned_role, tenant_id"
    )

    def save(self, record: CandidateRecord, dedup: bool = True) -> CandidateRecord:
        # P1-004：prediction 顶层字段同步进 data JSONB，保证持久化后读回一致
        if record.prediction and record.data.get("prediction") != record.prediction:
            record.data = {**record.data, "prediction": record.prediction}
        # P3-B2：synthesis_feasibility 顶层字段同步进 data JSONB
        if record.synthesis_feasibility and record.data.get("synthesis_feasibility") != record.synthesis_feasibility:
            record.data = {**record.data, "synthesis_feasibility": record.synthesis_feasibility}
        # T-020：基于 content_hash 去重——化学式 + 目标应用相同则跳过创建。
        # dedup=False 时跳过去重（如临时预测转正：每个临时结果应创建独立候选）。
        formula = record.data.get("formula") or record.name
        target_application = record.data.get("target_application", "")
        if dedup and formula:
            content_hash = self._compute_content_hash(formula, target_application)
            existing = self.find_by_content_hash(formula, target_application)
            if existing is not None:
                logger.info(
                    "候选已存在，跳过创建 content_hash=%s candidate_id=%s",
                    content_hash, existing.candidate_id,
                )
                return existing
        elif dedup:
            content_hash = None
        else:
            content_hash = self._compute_content_hash(formula, target_application) if formula else None

        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.candidates
                (candidate_id, candidate_type, name, smiles, source, scenario_id,
                 task_id, project_id, multi_objective_score, created_at, data, content_hash,
                 status, owner, assigned_role, tenant_id)
                VALUES (:candidate_id, :candidate_type, :name, :smiles, :source, :scenario_id,
                 :task_id, :project_id, :multi_objective_score, :created_at, CAST(:data AS JSONB),
                 :content_hash, :status, :owner, :assigned_role, :tenant_id)
                -- 冲突分支不覆盖 status/owner/assigned_role/tenant_id：
                -- 状态只能经 update_status 状态机迁移（防止重复 save 把已推进候选回卷为
                -- screening，审查 2026-08 MINOR#7）；租户归属一经写入不得搬移
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
                    -- T03：跨租户不更新（若冲突行属于别的租户则静默跳过该更新，
                    -- 防 tenant A 用相同 candidate_id upsert 覆盖 tenant B 的数据）
                WHERE candidates.tenant_id = EXCLUDED.tenant_id
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
                    "tenant_id": record.tenant_id or get_tenant(),
                },
            )
        return record

    def update_synthesis_feasibility(self, candidate_id: str, feasibility: dict) -> bool:
        """按 candidate_id 更新合成可行性（仅更新 data.synthesis_feasibility）。

        直接 UPDATE data JSONB，不走 content-hash 去重分支——save() 的去重短路
        会丢弃对已存在候选的字段更新，因此回写必须走专用更新通道。
        """
        patch = {"synthesis_feasibility": feasibility}
        with self.engine.begin() as conn:
            res = conn.execute(
                text("""UPDATE experiment.candidates
                        SET data = data || CAST(:patch AS JSONB)
                        WHERE candidate_id = :candidate_id"""),
                {"patch": json.dumps(patch, ensure_ascii=False), "candidate_id": candidate_id},
            )
        return (res.rowcount or 0) > 0

    def find_by_origin_temp_id(self, origin_temp_id: str) -> CandidateRecord | None:
        """按来源谱系标识 origin_temp_id 查询已转正的候选。

        转正时在 data.provenance 中写入 {"step": "promote_from_temporary", "origin_temp_id": ...}，
        用于幂等去重：重复的转正请求返回同一候选，避免创建重复候选。
        """
        if not origin_temp_id:
            return None
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.candidates "
                     f"WHERE data::text LIKE :pattern AND {tenant_filter()} "
                     "ORDER BY created_at DESC LIMIT 1"),
                {"pattern": f"%{origin_temp_id}%", "tenant_id": get_tenant()},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def get(self, candidate_id: str) -> CandidateRecord | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.candidates "
                     f"WHERE candidate_id = :candidate_id AND {tenant_filter()}"),
                {"candidate_id": candidate_id, "tenant_id": get_tenant()},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_all(self, candidate_type: str = "", scenario_id: str = "",
                 task_id: str = "", project_id: str = "") -> list[CandidateRecord]:
        """查询候选材料列表。

        支持按 candidate_type / scenario_id / task_id / project_id 过滤，
        所有参数可选，组合使用 AND 关系。始终按当前租户隔离。
        """
        with self.engine.connect() as conn:
            conditions = [tenant_filter()]
            params: dict[str, Any] = {"tenant_id": get_tenant()}
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
                text("DELETE FROM experiment.candidates "
                     f"WHERE candidate_id = :candidate_id AND {tenant_filter()}"),
                {"candidate_id": candidate_id, "tenant_id": get_tenant()},
            )
            return cur.rowcount > 0

    def update_status(self, candidate_id: str, to_status: str,
                      actor_operation_roles: set[str] | None = None,
                      owner: str = "", triggered_by: str = "system",
                      reason: str = "") -> CandidateRecord:
        """更新候选材料状态，强制校验两层状态机迁移图与角色归属。

        角色校验（目标状态所对应的主导角色，见 CANDIDATE_STATUS_ROLE）：
            screening / feasible → formulator
            process_planning / process_confirmed / ready_for_experiment → process_engineer

        规则：
            - ``actor_operation_roles=None``：系统/后端自动流转，跳过人工角色校验
              （如合成成功后 screening→feasible 的自动推进）。
            - ``actor_operation_roles`` 为集合：要求目标状态对应的主导角色
              ``expected_role`` 必须在该集合内，否则拒绝迁移。

        该参数由调用方从可信来源推导（API 层由认证用户权限映射），
        不接受客户端直接传入，杜绝伪造角色绕过状态机校验。

        Args:
            candidate_id: 候选材料 ID
            to_status: 目标状态（screening / feasible / process_planning /
                       process_confirmed / ready_for_experiment / rejected）
            actor_operation_roles: 调用方可执行的操作角色集合
                （formulator / process_engineer 的子集）；None 表示系统自动流转跳过校验
            owner: 新的责任人（用户名）
            triggered_by: 触发主体标识
            reason: 迁移原因

        Raises:
            IllegalCandidateTransitionError: 非法迁移或角色不符
        """
        # 校验与写入同一事务 + FOR UPDATE 行锁：防止并发下两个请求基于旧状态
        # 双双通过校验（如 feasible→rejected 与 feasible→process_planning 同时成功），
        # 与 experiment_controller.update_order_status 的原子化做法对齐。
        with self.engine.begin() as conn:
            cur_row = conn.execute(
                text("SELECT status FROM experiment.candidates "
                     f"WHERE candidate_id = :candidate_id AND {tenant_filter()} FOR UPDATE"),
                {"candidate_id": candidate_id, "tenant_id": get_tenant()},
            ).fetchone()
            if cur_row is None:
                raise IllegalCandidateTransitionError(
                    "UNKNOWN", to_status, f"Candidate {candidate_id!r} not found",
                )

            from_status = cur_row[0] or CandidateStatus.SCREENING.value
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
            if expected_role and actor_operation_roles is not None and expected_role not in actor_operation_roles:
                raise IllegalCandidateTransitionError(
                    from_status, to_status,
                    f"状态 {to_enum.value} 须由 {expected_role} 角色执行，"
                    f"当前可用操作角色 {sorted(actor_operation_roles) or '无'}",
                )

            if owner:
                conn.execute(
                    text("UPDATE experiment.candidates SET status = :status, "
                         "owner = :owner, assigned_role = :assigned_role "
                         f"WHERE candidate_id = :candidate_id AND {tenant_filter()}"),
                    {
                        "status": to_status,
                        "owner": owner,
                        "assigned_role": expected_role,
                        "candidate_id": candidate_id,
                        "tenant_id": get_tenant(),
                    },
                )
            else:
                conn.execute(
                    text("UPDATE experiment.candidates SET status = :status, "
                         "assigned_role = :assigned_role "
                         f"WHERE candidate_id = :candidate_id AND {tenant_filter()}"),
                    {
                        "status": to_status,
                        "assigned_role": expected_role,
                        "candidate_id": candidate_id,
                        "tenant_id": get_tenant(),
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

        # P3-B2：synthesis_feasibility 持久化在 data JSONB 中，读取时提升为顶层字段
        synth_feas_val = data_val.get("synthesis_feasibility")
        if not isinstance(synth_feas_val, dict):
            synth_feas_val = {}

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
            synthesis_feasibility=synth_feas_val,
            tenant_id=_str(row[14]) if len(row) > 14 else "",
        )