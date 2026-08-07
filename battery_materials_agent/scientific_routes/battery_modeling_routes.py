"""电池建模与仿真 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..contracts.task import Task
from ..contracts.artifact import Artifact
from ..contracts.evidence import EvidencePackage
from ..services.battery_modeling.application import BatteryModelingApplication

router = APIRouter(prefix="/v1/battery-modeling", tags=["battery-modeling"])
service = BatteryModelingApplication()


class RunBatterySimRequest(BaseModel):
    """电池仿真请求（直接执行）。"""
    project_id: str = Field(..., description="项目 ID")
    track: str = Field(..., description="仿真轨道: p2d, ecm, pybop")
    model_type: str = Field(default="DFN", description="模型类型: SPM, SPMe, DFN (仅 p2d 轨道)")
    parameter_set: str = Field(default="Chen2020", description="参数集名称")
    experiment_protocol: list[dict] = Field(default_factory=list, description="实验协议步骤定义")
    thermal_option: str = Field(default="isothermal", description="热选项: isothermal, lumped, x-full")
    requested_variables: list[str] = Field(
        default_factory=lambda: ["Terminal voltage [V]", "Current [A]"],
        description="请求输出的变量列表",
    )


class RunBatterySimFullRequest(RunBatterySimRequest):
    """电池仿真请求（全生命周期）。"""
    title: str = Field(default="", description="任务标题")
    description: str = Field(default="", description="任务描述")


@router.post("/simulate", response_model=list[Artifact])
def simulate(req: RunBatterySimRequest):
    """直接执行电池仿真，返回 Artifact 列表。"""
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="电池建模与仿真",
        description=f"轨道: {req.track}, 模型: {req.model_type}, 参数集: {req.parameter_set}",
        metadata=req.model_dump(),
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/simulate/full", response_model=list[EvidencePackage])
def simulate_full(req: RunBatterySimFullRequest):
    """全生命周期电池仿真。"""
    evidence = service.run_battery_simulation(
        project_id=req.project_id,
        track=req.track,
        model_type=req.model_type,
        parameter_set=req.parameter_set,
        experiment_protocol=req.experiment_protocol,
        thermal_option=req.thermal_option,
        requested_variables=req.requested_variables,
    )
    return evidence


@router.get("/tracks")
def list_tracks():
    """列出所有支持的仿真轨道。"""
    from ..services.battery_modeling.validators import TRACK_NAMES, VALID_MODEL_TYPES
    return {
        "tracks": [
            {
                "key": k,
                "name": v,
                "models": VALID_MODEL_TYPES.get(k, []),
            }
            for k, v in TRACK_NAMES.items()
        ],
    }