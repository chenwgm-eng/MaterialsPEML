"""配方与工艺版本持久化存储。

基于已有的 VersionStore 封装，提供配方（FORMULA）实体的 CRUD 与版本管理。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Any
import uuid

from ..version_store import VersionStore, Version, VersionType


class FormulaVersion(BaseModel):
    """配方版本数据模型。"""

    formula_id: str = ""
    version_id: str = ""
    version_number: int = 1
    target_material: str = ""
    quantity: float = 1.0          # 配方目标产量（单位由 metadata.unit 或上下文决定）
    bom: list[dict] = Field(default_factory=list)
    bop: list[dict] = Field(default_factory=list)
    ehs: dict = Field(default_factory=dict)
    material_cost: float = 0.0
    process_cost: float = 0.0
    total_unit_cost: float = 0.0    # 单位成本（货币+单位由 metadata.unit 决定）
    process_cost_breakdown: list[dict] = Field(default_factory=list)
    created_by: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    change_summary: str = ""
    is_active: bool = True
    scenario_id: str = ""  # P0-001：关联研发场景 ID
    # P1-2：AI 可信度元信息（confidence/key_assumptions/evidence_sources/human_review_required）
    ai_meta: dict = Field(default_factory=dict)

    def to_snapshot(self) -> dict:
        # 排除所有在 from_version 中显式传入的字段，避免 **snap 与显式 kwarg 冲突
        return self.model_dump(exclude={
            "formula_id", "version_id", "version_number", "is_active",
            "created_at", "created_by", "change_summary",
        })

    @classmethod
    def from_version(cls, version: Version) -> "FormulaVersion":
        snap = dict(version.snapshot or {})
        # 弹出在下面显式传入的字段，避免 **snap 与显式 kwarg 冲突
        # （旧数据 snapshot 中可能残留这些字段）
        for k in ("formula_id", "version_id", "version_number", "created_by",
                  "created_at", "change_summary", "is_active"):
            snap.pop(k, None)
        return cls(
            formula_id=version.entity_id,
            version_id=version.version_id,
            version_number=version.version_number,
            created_by=version.created_by,
            created_at=version.created_at,
            change_summary=version.change_summary,
            is_active=version.is_active,
            **snap,
        )


class FormulaStore:
    """配方版本存储。"""

    def __init__(self, version_store: VersionStore | None = None):
        self._store = version_store or VersionStore()

    def save(self, formula: FormulaVersion) -> FormulaVersion:
        if not formula.formula_id:
            formula.formula_id = f"FORM-{uuid.uuid4().hex[:8].upper()}"
        # 追加版本时自动递增 version_number：若 formula_id 已有历史版本，
        # 且当前 version_number 未超过已有最大值，则置 0 触发 VersionStore 自动递增
        existing = self.list_history(formula.formula_id)
        if existing:
            max_ver = max(v.version_number for v in existing)
            if formula.version_number <= max_ver:
                formula.version_number = 0
        version = Version(
            entity_type=VersionType.FORMULA,
            entity_id=formula.formula_id,
            version_number=formula.version_number,
            snapshot=formula.to_snapshot(),
            change_summary=formula.change_summary,
            created_by=formula.created_by,
            created_at=formula.created_at,
            is_active=formula.is_active,
        )
        saved = self._store.save(version)
        return FormulaVersion.from_version(saved)

    def get(self, formula_id: str, version_id: str | None = None) -> FormulaVersion | None:
        if version_id:
            version = self._store.get(version_id)
            if version is None or version.entity_type != VersionType.FORMULA or version.entity_id != formula_id:
                return None
            return FormulaVersion.from_version(version)
        version = self._store.get_latest(VersionType.FORMULA.value, formula_id)
        return FormulaVersion.from_version(version) if version else None

    def list_all(self, target_material: str | None = None) -> list[FormulaVersion]:
        versions = self._store.list_latest(VersionType.FORMULA.value)
        formulas = [FormulaVersion.from_version(v) for v in versions]
        if target_material:
            formulas = [f for f in formulas if target_material.lower() in (f.target_material or "").lower()]
        return formulas

    def list_history(self, formula_id: str) -> list[FormulaVersion]:
        versions = self._store.list_by_entity(VersionType.FORMULA.value, formula_id)
        return [FormulaVersion.from_version(v) for v in versions]

    def set_active(self, formula_id: str, version_id: str) -> FormulaVersion | None:
        version = self._store.set_active(version_id)
        if version is None:
            return None
        formula = FormulaVersion.from_version(version)
        # Task 14.5：配方版本发布后自动创建样品提案（status="proposed"）
        # 样品的 source_candidate_id 关联到配方对应的候选（按 target_material 名称匹配）
        try:
            self._create_sample_proposal_for_formula(formula)
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).debug(
                "配方 %s 自动创建样品提案失败: %s", formula_id, exc
            )
        return formula

    def _create_sample_proposal_for_formula(self, formula: "FormulaVersion") -> None:
        """配方发布后自动创建样品提案。

        - 按 formula.target_material 在 candidates 表中模糊匹配候选
        - 若匹配到候选，source_candidate_id 关联之；否则留空
        - 样品 status="proposed"，name 标注配方来源
        """
        import uuid as _uuid
        from sqlalchemy import text as _sql_text
        from ..experiment.sample_store import Sample, SampleStatus, SampleStore

        sample_store = SampleStore()
        # 按 target_material 在 candidates 表中查找候选
        candidate_id = ""
        target = (formula.target_material or "").strip()
        if target:
            with sample_store.engine.connect() as conn:
                row = conn.execute(
                    _sql_text(
                        "SELECT candidate_id FROM experiment.candidates "
                        "WHERE name = :name ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"name": target},
                ).fetchone()
            if row is not None:
                candidate_id = row[0] or ""

        sample = Sample(
            sample_id=f"SMP_{_uuid.uuid4().hex[:8]}",
            name=f"配方 {formula.formula_id} v{formula.version_number} 样品提案",
            source_type="formula",
            source_candidate_id=candidate_id,
            quantity=formula.quantity,
            unit="kg",  # 0727b：单位由 sample_store 默认值兜底，后续可由 MDM 主数据获取
            status=SampleStatus.PROPOSED,
            notes=f"配方版本发布自动创建的样品提案；formula_id={formula.formula_id}, "
                  f"version_id={formula.version_id}",
            chemical_formula=target,
            scenario_id=formula.scenario_id or "",
        )
        sample_store.save(sample)


_formula_store: FormulaStore | None = None


def get_formula_store() -> FormulaStore:
    global _formula_store
    if _formula_store is None:
        _formula_store = FormulaStore()
    return _formula_store
