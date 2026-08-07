"""MPA 分子性质预测 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..contracts.task import Task
from ..contracts.artifact import Artifact
from ..contracts.evidence import EvidencePackage
from ..services.mpa.application import MPAApplication
from ..services.mpa.validators import PROPERTY_CATALOG, KNOWN_PROPERTY_KEYS

router = APIRouter(prefix="/v1/mpa", tags=["mpa"])
service = MPAApplication()


# ── Request/Response Schemas ───────────────────────────────

class PredictRequest(BaseModel):
    """分子性质预测请求（直接执行）。"""
    project_id: str = Field(..., description="项目 ID")
    molecule_revision_ids: list[str] = Field(..., description="SMILES 列表")
    property_keys: list[str] | None = Field(
        default=None, description="待预测的属性键列表，默认全部"
    )
    conditions: dict = Field(default_factory=dict, description="条件参数")
    model_selection_policy: str = Field(default="auto", description="模型选择策略")
    require_uncertainty: bool = Field(default=True, description="是否要求不确定性估计")


class PredictFullRequest(BaseModel):
    """分子性质预测请求（全生命周期）。"""
    project_id: str = Field(..., description="项目 ID")
    molecule_revision_ids: list[str] = Field(..., description="SMILES 列表")
    property_keys: list[str] | None = Field(
        default=None, description="待预测的属性键列表，默认全部"
    )
    conditions: dict = Field(default_factory=dict, description="条件参数")
    model_selection_policy: str = Field(default="auto", description="模型选择策略")
    require_uncertainty: bool = Field(default=True, description="是否要求不确定性估计")
    title: str = Field(default="", description="任务标题")
    description: str = Field(default="", description="任务描述")


# ── Routes ─────────────────────────────────────────────────

@router.post("/predict", response_model=list[Artifact])
def predict(req: PredictRequest):
    """直接执行分子性质预测，返回 Artifact 列表。

    创建 Task 和 Run，执行预测，返回结果工件。不经过证据包后处理。
    """
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="分子性质预测",
        description=f"预测 {len(req.molecule_revision_ids)} 个分子的性质",
        metadata={
            "project_id": req.project_id,
            "molecule_revision_ids": req.molecule_revision_ids,
            "property_keys": req.property_keys or list(KNOWN_PROPERTY_KEYS),
            "conditions": req.conditions,
            "model_selection_policy": req.model_selection_policy,
            "require_uncertainty": req.require_uncertainty,
        },
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/predict/full", response_model=list[EvidencePackage])
def predict_full(req: PredictFullRequest):
    """全生命周期分子性质预测。

    创建 Task → 创建 Run → 执行 → 后处理 → 返回 EvidencePackage。
    """
    title = req.title or "分子性质预测"
    desc = req.description or f"预测 {len(req.molecule_revision_ids)} 个分子的 {len(req.property_keys or KNOWN_PROPERTY_KEYS)} 种性质"

    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title=title,
        description=desc,
        metadata={
            "project_id": req.project_id,
            "molecule_revision_ids": req.molecule_revision_ids,
            "property_keys": req.property_keys or list(KNOWN_PROPERTY_KEYS),
            "conditions": req.conditions,
            "model_selection_policy": req.model_selection_policy,
            "require_uncertainty": req.require_uncertainty,
        },
    )
    return service.run_full_cycle(task)


@router.get("/properties")
def list_properties():
    """列出所有可预测的 42 种分子性质。"""
    return {
        "count": len(PROPERTY_CATALOG),
        "properties": [
            {
                "key": key,
                "description": meta["description"],
                "unit": meta["unit"],
                "typical_range": meta.get("typical_range"),
            }
            for key, meta in PROPERTY_CATALOG.items()
        ],
    }