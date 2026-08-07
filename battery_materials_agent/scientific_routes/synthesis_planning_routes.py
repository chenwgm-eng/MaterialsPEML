"""合成路线规划 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..contracts.task import Task
from ..contracts.artifact import Artifact
from ..contracts.evidence import EvidencePackage
from ..services.synthesis_planning.application import SynthesisPlanningApplication

router = APIRouter(prefix="/v1/synthesis-planning", tags=["synthesis-planning"])
service = SynthesisPlanningApplication()


class PlanSynthesisRequest(BaseModel):
    """逆合成分析请求（直接执行）。"""
    project_id: str = Field(..., description="项目 ID")
    target_smiles: str = Field(..., description="目标分子 SMILES")
    search_depth: int = Field(default=3, description="搜索深度")
    max_paths: int = Field(default=10, description="最大返回路线数")
    normalize_ions: bool = Field(default=True, description="是否归一化离子/盐")
    include_literature: bool = Field(default=True, description="是否包含文献验证")
    expansion_timeout: int = Field(default=300, description="搜索超时（秒）")


class PlanSynthesisFullRequest(PlanSynthesisRequest):
    """逆合成分析请求（全生命周期）。"""
    title: str = Field(default="", description="任务标题")
    description: str = Field(default="", description="任务描述")


@router.post("/plan", response_model=list[Artifact])
def plan_synthesis(req: PlanSynthesisRequest):
    """直接执行逆合成分析，返回 Artifact 列表。"""
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="合成路线规划",
        description=f"ReactNavi 逆合成分析: {req.target_smiles}",
        metadata=req.model_dump(),
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/plan/full", response_model=list[EvidencePackage])
def plan_synthesis_full(req: PlanSynthesisFullRequest):
    """全生命周期逆合成分析。"""
    evidence = service.plan_synthesis(
        project_id=req.project_id,
        target_smiles=req.target_smiles,
        search_depth=req.search_depth,
        max_paths=req.max_paths,
        normalize_ions=req.normalize_ions,
        include_literature=req.include_literature,
        expansion_timeout=req.expansion_timeout,
    )
    return evidence