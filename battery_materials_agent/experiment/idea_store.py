"""Idea store for tracking material hypotheses through parallel verification."""

from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, timezone
from sqlalchemy import text
import json
import logging

from ..db import get_engine
from ..mdm.reference_dict import ReferenceDictStore

logger = logging.getLogger(__name__)


def _iso(value) -> str:
    """将 datetime 或字符串转换为 ISO 字符串；None 返回空字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class IdeaStatus(str, Enum):
    DRAFT = "draft"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    FAILED = "failed"
    PREFERRED = "preferred"  # 优选
    ELIMINATED = "eliminated"  # 淘汰


class Idea(BaseModel):
    idea_id: str = ""
    name: str = ""
    description: str = ""
    material_type: str = "molecule"  # molecule / crystal
    smiles: str = ""
    formula: str = ""
    target_properties: list[dict] = []  # [{name, direction, target_value}]
    status: IdeaStatus = IdeaStatus.DRAFT
    verification_result: dict = {}  # 验证结果
    score: float = 0.0  # 综合评分
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str = ""
    provenance: list[dict] = Field(default_factory=list)


class IdeaStore:
    """PostgreSQL-backed persistent storage for material hypotheses (ideas)."""

    def __init__(self, db_path: str = "data/ideas.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.engine = get_engine()
        self._mdm = ReferenceDictStore()
        self._init_db()

    def _init_db(self):
        # 表已由 alembic 迁移创建，这里仅保留 IF NOT EXISTS 兜底
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.ideas (
                    idea_id TEXT PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    material_type TEXT,
                    smiles TEXT,
                    formula TEXT,
                    target_properties JSONB,
                    status TEXT,
                    verification_result TEXT,
                    score DOUBLE PRECISION,
                    created_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ,
                    notes TEXT,
                    provenance JSONB DEFAULT '[]'
                )
            """))

    def _validate_status(self, status: IdeaStatus) -> None:
        """校验 status 必须存在于 MDM status_codes (domain='idea') 中。"""
        if self._mdm.get_status_code(domain="idea", code=status.value) is None:
            raise ValueError(f"Invalid status '{status.value}' for idea domain")

    def create(self, idea: Idea) -> Idea:
        """创建 Idea（含 MDM status 校验）。"""
        self._validate_status(idea.status)
        now = datetime.now(timezone.utc).isoformat()
        if not idea.created_at:
            idea.created_at = now
        idea.updated_at = now
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.ideas
                (idea_id, name, description, material_type, smiles, formula,
                 target_properties, status, verification_result, score,
                 created_at, updated_at, notes, provenance)
                VALUES (:idea_id, :name, :description, :material_type, :smiles, :formula,
                 CAST(:target_properties AS JSONB), :status, :verification_result, :score,
                 :created_at, :updated_at, :notes, CAST(:provenance AS JSONB))
                """),
                {
                    "idea_id": idea.idea_id,
                    "name": idea.name,
                    "description": idea.description,
                    "material_type": idea.material_type,
                    "smiles": idea.smiles,
                    "formula": idea.formula,
                    "target_properties": json.dumps(idea.target_properties),
                    "status": idea.status.value,
                    "verification_result": json.dumps(idea.verification_result),
                    "score": idea.score,
                    "created_at": idea.created_at,
                    "updated_at": idea.updated_at,
                    "notes": idea.notes,
                    "provenance": json.dumps(idea.provenance),
                },
            )
        return idea

    def update(self, idea: Idea) -> Idea:
        """更新 Idea（含 MDM status 校验）。"""
        self._validate_status(idea.status)
        idea.updated_at = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text("""UPDATE experiment.ideas SET
                    name = :name,
                    description = :description,
                    material_type = :material_type,
                    smiles = :smiles,
                    formula = :formula,
                    target_properties = CAST(:target_properties AS JSONB),
                    status = :status,
                    verification_result = :verification_result,
                    score = :score,
                    created_at = :created_at,
                    updated_at = :updated_at,
                    notes = :notes,
                    provenance = CAST(:provenance AS JSONB)
                WHERE idea_id = :idea_id
                """),
                {
                    "idea_id": idea.idea_id,
                    "name": idea.name,
                    "description": idea.description,
                    "material_type": idea.material_type,
                    "smiles": idea.smiles,
                    "formula": idea.formula,
                    "target_properties": json.dumps(idea.target_properties),
                    "status": idea.status.value,
                    "verification_result": json.dumps(idea.verification_result),
                    "score": idea.score,
                    "created_at": idea.created_at,
                    "updated_at": idea.updated_at,
                    "notes": idea.notes,
                    "provenance": json.dumps(idea.provenance),
                },
            )
        return idea

    def save(self, idea: Idea) -> Idea:
        """兼容旧调用方的 upsert：存在则更新，否则创建。"""
        existing = self.get(idea.idea_id)
        if existing is None:
            return self.create(idea)
        return self.update(idea)

    def get(self, idea_id: str) -> Idea | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM experiment.ideas WHERE idea_id = :idea_id"),
                {"idea_id": idea_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_idea(row)

    def list_all(self) -> list[Idea]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM experiment.ideas ORDER BY created_at DESC")
            ).fetchall()
        return [self._row_to_idea(r) for r in rows]

    def list_by_status(self, status: IdeaStatus) -> list[Idea]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM experiment.ideas WHERE status = :status "
                     "ORDER BY created_at DESC"),
                {"status": status.value},
            ).fetchall()
        return [self._row_to_idea(r) for r in rows]

    def update_status(self, idea_id: str, status: IdeaStatus, notes: str = "") -> bool:
        idea = self.get(idea_id)
        if not idea:
            return False
        idea.status = status
        if notes:
            idea.notes = notes
        self.save(idea)
        return True

    def _row_to_idea(self, row) -> Idea:
        # target_properties / provenance 为 JSONB，psycopg3 自动解析；verification_result 为 TEXT
        target_properties = row[6]
        if isinstance(target_properties, str):
            try:
                target_properties = json.loads(target_properties)
            except (json.JSONDecodeError, TypeError):
                target_properties = []
        target_properties = target_properties or []

        try:
            verification_result = json.loads(row[8]) if row[8] else {}
        except (json.JSONDecodeError, TypeError):
            verification_result = {}

        provenance = row[13] if len(row) > 13 else []
        if isinstance(provenance, str):
            try:
                provenance = json.loads(provenance)
            except (json.JSONDecodeError, TypeError):
                provenance = []
        provenance = provenance or []

        try:
            status = IdeaStatus(row[7]) if row[7] else IdeaStatus.DRAFT
        except (ValueError, KeyError):
            status = IdeaStatus.DRAFT

        return Idea(
            idea_id=row[0] or "", name=row[1] or "", description=row[2] or "",
            material_type=row[3] or "molecule",
            smiles=row[4] or "", formula=row[5] or "",
            target_properties=target_properties,
            status=status,
            verification_result=verification_result,
            score=row[9] if row[9] is not None else 0.0,
            created_at=_iso(row[10]), updated_at=_iso(row[11]), notes=row[12] or "",
            provenance=provenance,
        )
