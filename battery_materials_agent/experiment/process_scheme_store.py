"""工艺方案存储（独立于 BOM 的工艺路线信息）。

0021 迁移新增：将工艺方案从 BomScheme.process_route JSONB 嵌入字段独立成表，
便于记录从合成路径生成的工艺路线详情，并与 BOM 1:1 关联。

业务链路：
    合成路径（SynthesisRoute）→ 选中某条路径 → 生成 BOM + 工艺方案
    BOM 方案 1 ↔ 1 工艺方案（process_schemes）

0040 两层流程（第二层：工艺深化阶段）：
    工艺人员针对初筛通过的候选配方，做详细的合成路径规划，产出可执行工艺方案。
"""
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
import json
from sqlalchemy import text

from ..db import get_engine


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class ProcessSchemeStatus(str, Enum):
    """工艺方案状态机（两层流程第二层：工艺深化阶段）。

    工艺人员制定方案：draft → reviewing → confirmed
        进行时：draft（草稿）→ reviewing（评审中）→ confirmed（已确认，可下达实验）
    淘汰/中止：draft / reviewing 均可 → abandoned（放弃）
    """
    DRAFT = "draft"                # 草稿（工艺人员制定中）
    REVIEWING = "reviewing"        # 评审中
    CONFIRMED = "confirmed"        # 已确认（可作为实验单的工艺来源）
    ABANDONED = "abandoned"        # 放弃/中止

    @classmethod
    def is_valid_value(cls, v: str) -> bool:
        return v in {s.value for s in cls}


# 工艺方案状态迁移图
PROCESS_ALLOWED_TRANSITIONS: dict[ProcessSchemeStatus, set[ProcessSchemeStatus]] = {
    ProcessSchemeStatus.DRAFT: {ProcessSchemeStatus.REVIEWING, ProcessSchemeStatus.ABANDONED},
    ProcessSchemeStatus.REVIEWING: {ProcessSchemeStatus.CONFIRMED, ProcessSchemeStatus.DRAFT, ProcessSchemeStatus.ABANDONED},
    ProcessSchemeStatus.CONFIRMED: set(),  # 已确认，作为工艺来源引用（不可再改）
    ProcessSchemeStatus.ABANDONED: set(),  # 终态
}


class IllegalProcessSchemeTransitionError(ValueError):
    """工艺方案非法状态迁移。"""

    def __init__(self, from_status: str, to_status: str, reason: str = ""):
        self.from_status = from_status
        self.to_status = to_status
        self.reason = reason
        msg = f"Illegal process scheme transition: {from_status} -> {to_status}"
        if reason:
            msg = f"{msg}. {reason}"
        super().__init__(msg)


class ProcessScheme(BaseModel):
    """工艺方案（与 BomScheme 1:1 关联）。

    source_route_id / source_synthesis_task_id 用于追溯 BOM+工艺方案
    是从哪条合成路径生成的。

    0040 结构化扩展：
        routes        多路径比选（工艺人员在深化阶段的候选路径清单）
        evidence_refs 能力来源记录（每条工艺步骤/能力由哪个 SCP/本地服务/LLM 产出）
        status        状态机：draft → reviewing → confirmed / abandoned
        owner         当前责任人（工艺人员用户名）
    """
    process_id: str = ""
    candidate_id: str = ""
    bom_id: str = ""  # 关联 BomScheme（1:1）
    source_route_id: str = ""  # 如 "R1"，标识合成路径任务结果中的某条路径
    source_synthesis_task_id: str = ""  # 关联 synthesis.synthesis_tasks
    steps: list[dict[str, Any]] = Field(default_factory=list)  # 工艺步骤
    routes: list[dict[str, Any]] = Field(default_factory=list)  # 多路径比选
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)  # 能力来源记录
    status: str = ProcessSchemeStatus.DRAFT.value  # draft → reviewing → confirmed / abandoned
    owner: str = ""  # 当前责任人（工艺人员用户名）
    raw_materials: list[dict[str, Any]] = Field(default_factory=list)  # 原料清单
    metadata: dict[str, Any] = Field(default_factory=dict)  # 其他元数据（如 feasibility_score）
    created_by: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = ""

    @field_validator('candidate_id', 'bom_id', 'source_route_id',
                     'source_synthesis_task_id', 'created_by', 'owner',
                     mode='before')
    @classmethod
    def _coerce_none_to_empty(cls, v):
        return "" if v is None else v


class ProcessSchemeStore:
    """工艺方案存储。"""

    def __init__(self, db_path: str = ""):
        self.engine = get_engine()
        self._init_db()

    def _init_db(self):
        # 表由 0021 alembic 迁移创建，这里仅 IF NOT EXISTS 兜底
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.process_schemes (
                    process_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    bom_id TEXT,
                    source_route_id TEXT,
                    source_synthesis_task_id TEXT,
                    steps JSONB DEFAULT '[]'::jsonb,
                    routes JSONB DEFAULT '[]'::jsonb,
                    evidence_refs JSONB DEFAULT '[]'::jsonb,
                    status TEXT DEFAULT 'draft',
                    owner TEXT DEFAULT '',
                    raw_materials JSONB DEFAULT '[]'::jsonb,
                    metadata JSONB DEFAULT '{}'::jsonb,
                    created_by TEXT DEFAULT '',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            # 0040 兜底补列（alembic 已迁移的环境无需执行）
            conn.execute(text(
                "ALTER TABLE experiment.process_schemes "
                "ADD COLUMN IF NOT EXISTS routes JSONB DEFAULT '[]'::jsonb"
            ))
            conn.execute(text(
                "ALTER TABLE experiment.process_schemes "
                "ADD COLUMN IF NOT EXISTS evidence_refs JSONB DEFAULT '[]'::jsonb"
            ))
            conn.execute(text(
                "ALTER TABLE experiment.process_schemes "
                "ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'draft'"
            ))
            conn.execute(text(
                "ALTER TABLE experiment.process_schemes "
                "ADD COLUMN IF NOT EXISTS owner TEXT DEFAULT ''"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_process_candidate_id "
                "ON experiment.process_schemes(candidate_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_process_bom_id "
                "ON experiment.process_schemes(bom_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_process_status "
                "ON experiment.process_schemes(status)"
            ))

    _SELECT_COLS = (
        "process_id, candidate_id, bom_id, source_route_id, "
        "source_synthesis_task_id, steps, routes, evidence_refs, status, owner, "
        "raw_materials, metadata, "
        "created_by, created_at, updated_at"
    )

    @staticmethod
    def _row_to_scheme(r) -> ProcessScheme:
        return ProcessScheme(
            process_id=r[0] or "",
            candidate_id=r[1] or "",
            bom_id=r[2] or "",
            source_route_id=r[3] or "",
            source_synthesis_task_id=r[4] or "",
            steps=r[5] if r[5] is not None else [],
            routes=r[6] if r[6] is not None else [],
            evidence_refs=r[7] if r[7] is not None else [],
            status=r[8] or ProcessSchemeStatus.DRAFT.value,
            owner=r[9] or "",
            raw_materials=r[10] if r[10] is not None else [],
            metadata=r[11] if r[11] is not None else {},
            created_by=r[12] or "",
            created_at=_iso(r[13]),
            updated_at=_iso(r[14]),
        )

    def create(self, scheme: ProcessScheme) -> ProcessScheme:
        if not scheme.candidate_id:
            raise ValueError("candidate_id 不能为空")
        if not scheme.process_id:
            scheme.process_id = f"PROC-{uuid.uuid4().hex[:10].upper()}"
        now = datetime.now(timezone.utc).isoformat()
        if not scheme.created_at:
            scheme.created_at = now
        scheme.updated_at = now

        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.process_schemes
                (process_id, candidate_id, bom_id, source_route_id,
                 source_synthesis_task_id, steps, routes, evidence_refs, status, owner,
                 raw_materials, metadata,
                 created_by, created_at, updated_at)
                VALUES (:process_id, :candidate_id, :bom_id, :source_route_id,
                 :source_synthesis_task_id,
                 CAST(:steps AS JSONB), CAST(:routes AS JSONB), CAST(:evidence_refs AS JSONB),
                 :status, :owner,
                 CAST(:raw_materials AS JSONB), CAST(:metadata AS JSONB),
                 :created_by, :created_at, :updated_at)
                """),
                {
                    "process_id": scheme.process_id,
                    "candidate_id": scheme.candidate_id,
                    "bom_id": scheme.bom_id or None,
                    "source_route_id": scheme.source_route_id,
                    "source_synthesis_task_id": scheme.source_synthesis_task_id,
                    "steps": json.dumps(scheme.steps, ensure_ascii=False),
                    "routes": json.dumps(scheme.routes, ensure_ascii=False),
                    "evidence_refs": json.dumps(scheme.evidence_refs, ensure_ascii=False),
                    "status": scheme.status or ProcessSchemeStatus.DRAFT.value,
                    "owner": scheme.owner or "",
                    "raw_materials": json.dumps(scheme.raw_materials, ensure_ascii=False),
                    "metadata": json.dumps(scheme.metadata, ensure_ascii=False),
                    "created_by": scheme.created_by,
                    "created_at": scheme.created_at,
                    "updated_at": scheme.updated_at,
                },
            )
        return scheme

    def get(self, process_id: str) -> ProcessScheme | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.process_schemes WHERE process_id = :process_id"),
                {"process_id": process_id},
            ).fetchone()
        return self._row_to_scheme(row) if row else None

    def get_by_bom(self, bom_id: str) -> ProcessScheme | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.process_schemes WHERE bom_id = :bom_id LIMIT 1"),
                {"bom_id": bom_id},
            ).fetchone()
        return self._row_to_scheme(row) if row else None

    def list_by_candidate(self, candidate_id: str) -> list[ProcessScheme]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.process_schemes WHERE candidate_id = :candidate_id "
                     "ORDER BY created_at DESC"),
                {"candidate_id": candidate_id},
            ).fetchall()
        return [self._row_to_scheme(r) for r in rows]

    def update(self, scheme: ProcessScheme) -> ProcessScheme:
        scheme.updated_at = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text("""UPDATE experiment.process_schemes SET
                bom_id = :bom_id,
                source_route_id = :source_route_id,
                source_synthesis_task_id = :source_synthesis_task_id,
                steps = CAST(:steps AS JSONB),
                routes = CAST(:routes AS JSONB),
                evidence_refs = CAST(:evidence_refs AS JSONB),
                status = :status,
                owner = :owner,
                raw_materials = CAST(:raw_materials AS JSONB),
                metadata = CAST(:metadata AS JSONB),
                created_by = :created_by,
                updated_at = :updated_at
                WHERE process_id = :process_id"""),
                {
                    "bom_id": scheme.bom_id or None,
                    "source_route_id": scheme.source_route_id,
                    "source_synthesis_task_id": scheme.source_synthesis_task_id,
                    "steps": json.dumps(scheme.steps, ensure_ascii=False),
                    "routes": json.dumps(scheme.routes, ensure_ascii=False),
                    "evidence_refs": json.dumps(scheme.evidence_refs, ensure_ascii=False),
                    "status": scheme.status or ProcessSchemeStatus.DRAFT.value,
                    "owner": scheme.owner or "",
                    "raw_materials": json.dumps(scheme.raw_materials, ensure_ascii=False),
                    "metadata": json.dumps(scheme.metadata, ensure_ascii=False),
                    "created_by": scheme.created_by,
                    "updated_at": scheme.updated_at,
                    "process_id": scheme.process_id,
                },
            )
        return scheme

    def update_status(self, process_id: str, to_status: str, owner: str = "",
                      triggered_by: str = "system", reason: str = "",
                      require_role: str = "") -> ProcessScheme:
        """更新工艺方案状态，强制校验迁移图。

        Args:
            process_id: 工艺方案 ID
            to_status: 目标状态（draft / reviewing / confirmed / abandoned）
            owner: 新的责任人（工艺人员用户名）
            triggered_by: 触发主体标识
            reason: 迁移原因
            require_role: 若提供，校验当前 owner 对应的角色（process_engineer）
        """
        to_status_enum = ProcessSchemeStatus(to_status)
        scheme = self.get(process_id)
        if scheme is None:
            raise IllegalProcessSchemeTransitionError(
                "UNKNOWN", to_status, f"ProcessScheme {process_id!r} not found",
            )

        from_status = scheme.status or ProcessSchemeStatus.DRAFT.value
        from_status_enum = ProcessSchemeStatus(from_status)
        allowed = PROCESS_ALLOWED_TRANSITIONS.get(from_status_enum, set())
        if to_status_enum not in allowed:
            allowed_str = [s.value for s in allowed] if allowed else "none (terminal state)"
            raise IllegalProcessSchemeTransitionError(
                from_status, to_status,
                f"Allowed transitions from {from_status_enum.value}: {allowed_str}",
            )

        if require_role and require_role != "process_engineer":
            raise IllegalProcessSchemeTransitionError(
                from_status, to_status,
                f"工艺方案深化仅允许 process_engineer 角色操作，当前角色 {require_role!r}",
            )

        with self.engine.begin() as conn:
            if owner:
                conn.execute(
                    text("UPDATE experiment.process_schemes SET status = :status, "
                         "owner = :owner, updated_at = :updated_at "
                         "WHERE process_id = :process_id"),
                    {
                        "status": to_status,
                        "owner": owner,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "process_id": process_id,
                    },
                )
            else:
                conn.execute(
                    text("UPDATE experiment.process_schemes SET status = :status, "
                         "updated_at = :updated_at "
                         "WHERE process_id = :process_id"),
                    {
                        "status": to_status,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "process_id": process_id,
                    },
                )
        return self.get(process_id)  # type: ignore[return-value]

    def delete(self, process_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM experiment.process_schemes WHERE process_id = :process_id"),
                {"process_id": process_id},
            )
        return cur.rowcount > 0