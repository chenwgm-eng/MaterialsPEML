"""流体动力学模拟 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from typing import Any

from ..contracts.task import Task
from ..contracts.artifact import Artifact
from ..contracts.evidence import EvidencePackage
from ..services.fluid_simulation.application import FluidSimulationApplication, SOLVER_CATALOG, VALID_SOLVERS

router = APIRouter(prefix="/v1/fluid-simulation", tags=["fluid-simulation"])
service = FluidSimulationApplication()


class RunFluidSimRequest(BaseModel):
    """流体模拟运行请求（直接执行）。"""
    project_id: str = Field(..., description="项目 ID")
    solver: str = Field(..., description="求解器: ns2d, ns3d, ns2d_strat, ns3d_strat, sw1l")
    params: dict[str, Any] = Field(..., description="模拟参数，包含 grid, physical, time 等子参数")
    initial_conditions: dict[str, Any] = Field(..., description="初始条件配置")
    forcing: dict[str, Any] | None = Field(default=None, description="强制力配置")
    output_config: dict[str, Any] | None = Field(default=None, description="输出配置")


class RunFluidSimFullRequest(RunFluidSimRequest):
    """流体模拟运行请求（全生命周期）。"""
    title: str = Field(default="", description="任务标题")
    description: str = Field(default="", description="任务描述")


class ResumeFluidSimRequest(BaseModel):
    """流体模拟续跑请求。"""
    project_id: str = Field(..., description="项目 ID")
    sim_dir: str = Field(..., description="已有模拟结果目录路径")
    extend_time: float = Field(..., gt=0, description="延长模拟时间 (秒)")


class AnalyzeFluidSimRequest(BaseModel):
    """流体模拟分析请求。"""
    project_id: str = Field(..., description="项目 ID")
    sim_dir: str = Field(..., description="模拟结果目录路径")
    fields: list[str] = Field(default_factory=lambda: ["vorticity", "velocity"], description="要分析的物理场列表")
    compute_spectra: bool = Field(default=True, description="是否计算能谱")


class SweepFluidSimRequest(BaseModel):
    """流体模拟参数扫描请求。"""
    project_id: str = Field(..., description="项目 ID")
    base_config: dict[str, Any] = Field(..., description="基础配置")
    sweep_params: dict[str, list[Any]] = Field(..., description="待扫描参数及其取值列表")
    workers: int = Field(default=1, ge=1, le=64, description="并行工作进程数")


@router.post("/run", response_model=list[Artifact])
def run_simulation(req: RunFluidSimRequest):
    """直接执行流体模拟，返回 Artifact 列表。"""
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="流体动力学模拟",
        description=f"求解器: {req.solver}",
        metadata=req.model_dump(),
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/run/full", response_model=list[EvidencePackage])
def run_simulation_full(req: RunFluidSimFullRequest):
    """全生命周期流体模拟。"""
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title=req.title or "流体动力学模拟",
        description=req.description or f"求解器: {req.solver}",
        metadata=req.model_dump(),
    )
    return service.run_full_cycle(task)


@router.post("/resume", response_model=dict)
def resume_simulation(req: ResumeFluidSimRequest):
    """续跑已有流体模拟。"""
    from ..infrastructure.executors.fluidsim_adapter import FluidSimAdapter
    adapter = FluidSimAdapter()
    result = adapter.resume_simulation(req.sim_dir, req.extend_time)
    return result


@router.post("/analyze", response_model=dict)
def analyze_simulation(req: AnalyzeFluidSimRequest):
    """分析已完成的流体模拟结果。"""
    return {
        "project_id": req.project_id,
        "sim_dir": req.sim_dir,
        "fields": req.fields,
        "compute_spectra": req.compute_spectra,
        "status": "analyze_placeholder",
        "message": "分析功能将在后续版本实现",
    }


@router.post("/sweep", response_model=dict)
def parameter_sweep(req: SweepFluidSimRequest):
    """执行参数扫描。"""
    from ..infrastructure.executors.fluidsim_adapter import FluidSimAdapter
    adapter = FluidSimAdapter()
    result = adapter.run_parameter_sweep(req.base_config, req.sweep_params, req.workers)
    return result


@router.get("/solvers")
def list_solvers():
    """列出所有支持的流体求解器。"""
    return {
        "count": len(SOLVER_CATALOG),
        "solvers": [
            {
                "key": k,
                "name": v["name"],
                "description": v["description"],
                "dimensions": v["dimensions"],
            }
            for k, v in SOLVER_CATALOG.items()
        ],
    }