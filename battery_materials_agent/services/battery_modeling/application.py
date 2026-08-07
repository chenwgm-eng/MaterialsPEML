"""Battery Modeling Application — 电池建模与仿真的核心实现。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ...contracts.artifact import Artifact, ArtifactType
from ...contracts.evidence import EvidencePackage
from ...contracts.run import Run
from ...contracts.task import Task
from ...domain.runtime import ScientificExecutionKernel
from ...infrastructure.executors.battery_adapter import BatteryAdapter
from ..base_service import NativeScientificService
from .evidence_mapper import batch_map_evidence
from .validators import BatteryModelingValidator


class RunBatterySimulation(BaseModel):
    """电池仿真命令 — 包含仿真所需的所有参数。"""

    project_id: str = Field(..., description="项目 ID")
    track: str = Field(..., description="仿真轨道: p2d, ecm, pybop")
    model_type: str = Field(default="DFN", description="模型类型: SPM, SPMe, DFN (仅 p2d 轨道)")
    parameter_set: str = Field(default="Chen2020", description="参数集名称")
    experiment_protocol: list[dict] = Field(
        default_factory=list,
        description="实验协议步骤定义列表",
    )
    thermal_option: str = Field(
        default="isothermal",
        description="热选项: isothermal, lumped, x-full",
    )
    requested_variables: list[str] = Field(
        default_factory=lambda: ["Terminal voltage [V]", "Current [A]"],
        description="请求输出的变量列表",
    )


class BatteryModelingApplication(NativeScientificService):
    """电池建模与仿真服务。

    基于 PyBaMM 的锂离子电池仿真，支持三条轨道：
    - p2d: P2D/DFN 机理模型 (SPM/SPMe/DFN)
    - ecm: 等效电路模型 (Thevenin)
    - pybop: PyBOP 参数辨识
    """

    def __init__(
        self,
        kernel: ScientificExecutionKernel | None = None,
        adapter: BatteryAdapter | None = None,
    ):
        super().__init__(kernel)
        self._adapter = adapter or BatteryAdapter()

    @property
    def capability_id(self) -> str:
        return "battery_modeling"

    @property
    def display_name(self) -> str:
        return "电池建模与仿真"

    @property
    def description(self) -> str:
        return "基于PyBaMM的锂离子电池仿真：P2D/DFN机理模型、ECM等效电路、PyBOP参数辨识"

    def validate(self, task: Task, context: dict[str, Any]) -> dict[str, Any]:
        """验证任务输入。"""
        cmd = RunBatterySimulation(**task.metadata)
        validator = BatteryModelingValidator(
            track=cmd.track,
            model_type=cmd.model_type,
            parameter_set=cmd.parameter_set,
            experiment_protocol=cmd.experiment_protocol,
            thermal_option=cmd.thermal_option,
            requested_variables=cmd.requested_variables,
        )
        return validator.validate_all()

    def prepare(self, task: Task) -> Run:
        """根据任务创建 Run 实例。"""
        cmd = RunBatterySimulation(**task.metadata)
        return Run(
            task_id=task.task_id,
            project_id=task.project_id,
            service_id=self.capability_id,
            command=f"run_battery_simulation {cmd.track} {cmd.model_type}",
            input=cmd.model_dump(),
        )

    def execute(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行电池仿真，返回 Artifact 列表。"""
        prepared_input = run.input

        # 调用执行适配器
        raw_output = self._adapter.execute(prepared_input)
        parsed = self._adapter.parse_output(raw_output)

        # 创建 Artifact
        result_artifact = Artifact(
            run_id=run.run_id,
            type=ArtifactType.RESULT_TABLE,
            name="battery_simulation_results",
            description=(
                f"电池仿真结果 ({prepared_input.get('track')} / "
                f"{prepared_input.get('model_type', 'N/A')})"
            ),
            content_type="application/json",
            data=parsed,
        )

        return [result_artifact]

    def postprocess(self, run: Run, artifacts: list[Artifact]) -> list[EvidencePackage]:
        """后处理，将 Artifact 转换为 EvidencePackage 列表。"""
        sim_data: dict[str, Any] = {}

        for art in artifacts:
            if art.data is not None:
                sim_data = art.data
                break

        if not sim_data:
            return []

        return batch_map_evidence(
            run_id=run.run_id,
            task_id=run.task_id,
            track=sim_data.get("track", "p2d"),
            model_type=sim_data.get("model_type", "DFN"),
            parameter_set=sim_data.get("parameter_set", ""),
            results=sim_data.get("results", {}),
            summary=sim_data.get("summary", {}),
        )

    def run_battery_simulation(
        self,
        project_id: str,
        track: str = "p2d",
        model_type: str = "DFN",
        parameter_set: str = "Chen2020",
        experiment_protocol: list[dict] | None = None,
        thermal_option: str = "isothermal",
        requested_variables: list[str] | None = None,
    ) -> list[EvidencePackage]:
        """外部调用入口 — 一次性完成电池仿真全流程。

        Args:
            project_id: 项目 ID
            track: 仿真轨道 (p2d, ecm, pybop)
            model_type: 模型类型 (SPM/SPMe/DFN — 仅 p2d 轨道)
            parameter_set: 参数集名称 (如 "Chen2020", "OKane2022")
            experiment_protocol: 实验协议步骤列表
            thermal_option: 热选项 (isothermal, lumped, x-full)
            requested_variables: 请求输出的变量列表

        Returns:
            证据包列表
        """
        cmd = RunBatterySimulation(
            project_id=project_id,
            track=track,
            model_type=model_type,
            parameter_set=parameter_set,
            experiment_protocol=experiment_protocol or [],
            thermal_option=thermal_option,
            requested_variables=requested_variables
            or ["Terminal voltage [V]", "Current [A]"],
        )

        task = Task(
            project_id=project_id,
            capability_id=self.capability_id,
            title="电池建模与仿真",
            description=f"轨道: {track}, 模型: {model_type}, 参数集: {parameter_set}",
            metadata=cmd.model_dump(),
        )

        context: dict[str, Any] = {}
        return self.run_full_cycle(task, context)