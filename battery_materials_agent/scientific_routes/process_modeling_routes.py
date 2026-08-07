"""化工过程建模 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from typing import Any

from ..contracts.task import Task
from ..contracts.artifact import Artifact
from ..contracts.evidence import EvidencePackage
from ..services.process_modeling.application import ProcessModelingApplication, MODULE_CATALOG

router = APIRouter(prefix="/v1/process-modeling", tags=["process-modeling"])
service = ProcessModelingApplication()


class RunProcessCalcRequest(BaseModel):
    """化工过程计算请求（直接执行）。"""
    project_id: str = Field(..., description="项目 ID")
    module: str = Field(..., description="计算模块: M1-M6")
    calculation_type: str = Field(..., description="模块内具体计算类型")
    compounds: list[dict] = Field(default_factory=list, description="化合物信息列表")
    conditions: dict[str, Any] = Field(default_factory=dict, description="操作条件")
    parameters: dict[str, Any] = Field(default_factory=dict, description="模块专属参数")


class RunProcessCalcFullRequest(RunProcessCalcRequest):
    """化工过程计算请求（全生命周期）。"""
    title: str = Field(default="", description="任务标题")
    description: str = Field(default="", description="任务描述")


@router.post("/calculate", response_model=list[Artifact])
def calculate(req: RunProcessCalcRequest):
    """直接执行化工过程计算，返回 Artifact 列表。"""
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="化工过程计算",
        description=f"模块: {req.module}, 计算类型: {req.calculation_type}",
        metadata=req.model_dump(),
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/calculate/full", response_model=list[EvidencePackage])
def calculate_full(req: RunProcessCalcFullRequest):
    """全生命周期化工过程计算。"""
    # 构建通过 run_full_cycle 执行
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title=req.title or "化工过程计算",
        description=req.description or f"模块: {req.module}, 计算类型: {req.calculation_type}",
        metadata=req.model_dump(),
    )
    return service.run_full_cycle(task)


@router.get("/modules")
def list_modules():
    """列出所有支持的化工计算模块。"""
    from ..services.process_modeling.validators import CALCULATION_TYPES
    return {
        "count": len(MODULE_CATALOG),
        "modules": [
            {
                "key": k,
                "name": v["name"],
                "description": v["description"],
                "methods": v["methods"],
                "calculation_types": CALCULATION_TYPES.get(k, []),
            }
            for k, v in MODULE_CATALOG.items()
        ],
    }