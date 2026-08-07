"""分子动力学模拟 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..contracts.task import Task
from ..contracts.artifact import Artifact
from ..contracts.evidence import EvidencePackage
from ..services.molecular_simulation.application import MolecularSimulationApplication

router = APIRouter(prefix="/v1/molecular-simulation", tags=["molecular-simulation"])
service = MolecularSimulationApplication()


class RunMDRequest(BaseModel):
    """分子动力学模拟请求（直接执行）。"""
    project_id: str = Field(..., description="项目 ID")
    system_type: str = Field(..., description="系统类型: A (晶体/无机), B (有机/聚合物), C (生物分子)")
    structure_data: str = Field(..., description="结构数据: SMILES, CIF 路径或 data 文件路径")
    forcefield: str | None = Field(default=None, description="力场名称")
    protocol: str = Field(default="nvt", description="系综协议: nvt, npt, nve, minimize, npt_nvt")
    temperature_k: float = Field(default=300.0, description="模拟温度 (K)")
    pressure_atm: float | None = Field(default=None, description="模拟压力 (atm)")
    timestep_fs: float = Field(default=1.0, description="时间步长 (fs)")
    run_steps: int = Field(default=100000, description="运行步数")
    requested_metrics: list[str] = Field(default_factory=lambda: ["rdf", "msd", "energy"])


class RunMDFullRequest(RunMDRequest):
    """分子动力学模拟请求（全生命周期）。"""
    title: str = Field(default="", description="任务标题")
    description: str = Field(default="", description="任务描述")


@router.post("/run", response_model=list[Artifact])
def run_md(req: RunMDRequest):
    """直接执行分子动力学模拟，返回 Artifact 列表。"""
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="分子动力学模拟",
        description=f"系统类型 {req.system_type}，协议 {req.protocol}",
        metadata=req.model_dump(),
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/run/full", response_model=list[EvidencePackage])
def run_md_full(req: RunMDFullRequest):
    """全生命周期分子动力学模拟。"""
    evidence = service.run_molecular_dynamics(
        project_id=req.project_id,
        system_type=req.system_type,
        structure_data=req.structure_data,
        forcefield=req.forcefield,
        protocol=req.protocol,
        temperature_k=req.temperature_k,
        pressure_atm=req.pressure_atm,
        timestep_fs=req.timestep_fs,
        run_steps=req.run_steps,
        requested_metrics=req.requested_metrics,
    )
    return evidence


@router.get("/metrics")
def list_metrics():
    """列出所有支持的轨迹分析指标。"""
    from ..services.molecular_simulation.validators import SUPPORTED_METRICS
    return {
        "count": len(SUPPORTED_METRICS),
        "metrics": [
            {"key": k, "description": v}
            for k, v in SUPPORTED_METRICS.items()
        ],
    }