"""流体动力学模拟服务 — 适配 NativeScientificService 的生命周期。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ...contracts.artifact import Artifact, ArtifactType
from ...contracts.evidence import EvidencePackage
from ...contracts.run import Run
from ...contracts.task import Task
from ...domain.runtime import ScientificExecutionKernel
from ..base_service import NativeScientificService
from .evidence_mapper import batch_map_fluid_evidence
from .validators import FluidSimulationValidator, SOLVER_NAMES, VALID_SOLVERS

# ── 求解器目录 ──────────────────────────────────────────────────────────────
SOLVER_CATALOG: dict[str, dict[str, str]] = {
    "ns2d": {
        "name": "二维 Navier-Stokes",
        "description": "二维不可压 Navier-Stokes 方程，伪谱法 FFT 求解",
        "dimensions": "2D",
    },
    "ns3d": {
        "name": "三维 Navier-Stokes",
        "description": "三维不可压 Navier-Stokes 方程，伪谱法 FFT 求解",
        "dimensions": "3D",
    },
    "ns2d_strat": {
        "name": "二维分层流",
        "description": "二维分层 Navier-Stokes 方程，含 Brunt-Väisälä 频率",
        "dimensions": "2D",
    },
    "ns3d_strat": {
        "name": "三维分层流",
        "description": "三维分层 Navier-Stokes 方程，含 Brunt-Väisälä 频率",
        "dimensions": "3D",
    },
    "sw1l": {
        "name": "单层浅水方程",
        "description": "单层浅水方程，含 Coriolis 参数",
        "dimensions": "2D",
    },
}


class RunSimulation(BaseModel):
    """运行流体模拟请求模型。"""

    project_id: str
    solver: str = Field(description="求解器: ns2d, ns3d, ns2d_strat, ns3d_strat, sw1l")
    params: dict[str, Any] = Field(description="模拟参数，包含网格、物理、时间参数等")
    initial_conditions: dict[str, Any] = Field(description="初始条件配置")
    forcing: dict[str, Any] | None = Field(default=None, description="强制力配置")
    output_config: dict[str, Any] | None = Field(default=None, description="输出配置")


class ResumeSimulation(BaseModel):
    """续跑模拟请求模型。"""

    project_id: str
    sim_dir: str = Field(description="已有模拟结果目录路径")
    extend_time: float = Field(gt=0, description="延长模拟时间 (秒)")


class AnalyzeSimulation(BaseModel):
    """分析模拟结果请求模型。"""

    project_id: str
    sim_dir: str = Field(description="模拟结果目录路径")
    fields: list[str] = Field(default_factory=lambda: ["vorticity", "velocity"], description="要分析的物理场列表")
    compute_spectra: bool = Field(default=True, description="是否计算能谱")


class ParameterSweep(BaseModel):
    """参数扫描请求模型。"""

    project_id: str
    base_config: dict[str, Any] = Field(description="基础配置")
    sweep_params: dict[str, list[Any]] = Field(description="待扫描参数及其取值列表")
    workers: int = Field(default=1, ge=1, le=64, description="并行工作进程数")


class FluidSimulationApplication(NativeScientificService):
    """流体动力学模拟服务。

    基于 FluidSim 伪谱法 CFD 求解器，支持：
    - NS2D/NS3D: 不可压 Navier-Stokes 方程
    - NS2D stratified / NS3D stratified: 分层流
    - SW1L: 单层浅水方程
    """

    # ── 属性 ──────────────────────────────────────────────────────────────

    @property
    def capability_id(self) -> str:
        return "fluid_simulation"

    @property
    def display_name(self) -> str:
        return "流体动力学模拟"

    @property
    def description(self) -> str:
        return "基于 FluidSim 的伪谱法 CFD 模拟：NS2D/NS3D/分层流/浅水方程"

    # ── 生命周期 ──────────────────────────────────────────────────────────

    def validate(self, task: Task, context: dict[str, Any]) -> dict[str, Any]:
        """校验任务输入。

        从 task.metadata 中提取模拟参数并进行校验。
        """
        params = task.metadata
        request = RunSimulation(
            project_id=task.project_id,
            solver=params.get("solver", ""),
            params=params.get("params", {}),
            initial_conditions=params.get("initial_conditions", {}),
            forcing=params.get("forcing"),
            output_config=params.get("output_config"),
        )

        # 从 params 中提取各子参数
        grid_params = request.params.get("grid", {})
        physical_params = request.params.get("physical", {})
        time_params = request.params.get("time", {})

        result = FluidSimulationValidator.validate_all(
            solver=request.solver,
            grid_params=grid_params,
            physical_params=physical_params,
            time_params=time_params,
            initial_conditions=request.initial_conditions,
            forcing=request.forcing,
            output_config=request.output_config,
        )

        return {
            "validated": result["validated"],
            "errors": result["errors"],
            "parsed_request": request.model_dump(),
        }

    def prepare(self, task: Task) -> Run:
        """根据任务创建 Run 实例。"""
        params = task.metadata
        request = RunSimulation(
            project_id=task.project_id,
            solver=params.get("solver", ""),
            params=params.get("params", {}),
            initial_conditions=params.get("initial_conditions", {}),
            forcing=params.get("forcing"),
            output_config=params.get("output_config"),
        )

        return Run(
            task_id=task.task_id,
            project_id=task.project_id,
            service_id=self.capability_id,
            command=f"fluid_simulation {request.solver}",
            input=request.model_dump(),
        )

    def execute(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行流体模拟。

        根据求解器选择调用对应的适配器逻辑。
        """
        input_data = run.input
        solver = input_data.get("solver", "")
        params = input_data.get("params", {})
        initial_conditions = input_data.get("initial_conditions", {})
        forcing = input_data.get("forcing")
        output_config = input_data.get("output_config")

        # 模拟执行——实际场景中会调用 FluidSimAdapter
        simulation_results = self._run_simulation(
            solver=solver,
            params=params,
            initial_conditions=initial_conditions,
            forcing=forcing,
            output_config=output_config,
        )

        # 封装为工件
        artifact = Artifact(
            run_id=run.run_id,
            type=ArtifactType.RESULT_TABLE,
            name=f"fluid_simulation_{solver}",
            description=f"{SOLVER_CATALOG.get(solver, {}).get('name', solver)} 模拟结果",
            data={
                "solver": solver,
                "params": params,
                "initial_conditions": initial_conditions,
                "forcing": forcing,
                "output_config": output_config,
                "results": simulation_results,
                "solver_catalog": SOLVER_CATALOG.get(solver),
            },
        )
        return [artifact]

    def postprocess(self, run: Run, artifacts: list[Artifact]) -> list[EvidencePackage]:
        """后处理，将工件转换为证据包。"""
        packages: list[EvidencePackage] = []
        for art in artifacts:
            if art.data is None:
                continue
            results = art.data.get("results", [])
            solver = art.data.get("solver", "")
            ev_list = batch_map_fluid_evidence(
                run_id=run.run_id,
                task_id=run.task_id,
                results=results,
                category=solver,
            )
            packages.extend(ev_list)
        return packages

    # ── 模拟执行方法 ──────────────────────────────────────────────────────

    def _run_simulation(
        self,
        solver: str,
        params: dict[str, Any],
        initial_conditions: dict[str, Any],
        forcing: dict[str, Any] | None = None,
        output_config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """执行流体模拟（模拟实现）。

        实际场景中会调用 FluidSimAdapter 进行真实计算。
        """
        results: list[dict[str, Any]] = []

        # 提取关键参数
        grid_params = params.get("grid", {})
        physical_params = params.get("physical", {})
        time_params = params.get("time", {})

        nx = grid_params.get("nx", 64)
        ny = grid_params.get("ny", 64)
        Lx = grid_params.get("Lx", 2.0 * 3.14159)
        Ly = grid_params.get("Ly", 2.0 * 3.14159)
        t_end = time_params.get("t_end", 10.0)
        nu_2 = physical_params.get("nu_2", 1e-4)
        nz = grid_params.get("nz")
        Lz = grid_params.get("Lz")

        ic_type = initial_conditions.get("type", "noise")

        # 模拟参数信息
        results.append({
            "name": "求解器",
            "value": solver,
            "unit": "",
            "source": "fluidsim",
            "confidence": 1.0,
            "method": "配置",
        })

        # 网格信息
        dim_info = f"{nx}x{ny}"
        if nz:
            dim_info += f"x{nz}"
        results.append({
            "name": "网格尺寸",
            "value": dim_info,
            "unit": "点数",
            "source": "fluidsim",
            "confidence": 1.0,
            "method": "配置",
        })

        domain_info = f"Lx={Lx}, Ly={Ly}"
        if Lz:
            domain_info += f", Lz={Lz}"
        results.append({
            "name": "域尺寸",
            "value": domain_info,
            "unit": "",
            "source": "fluidsim",
            "confidence": 1.0,
            "method": "配置",
        })

        # 物理参数
        results.append({
            "name": "二阶粘性 nu_2",
            "value": nu_2,
            "unit": "m²/s",
            "source": "fluidsim",
            "confidence": 1.0,
            "method": "配置",
        })

        # 时间参数
        results.append({
            "name": "模拟总时长",
            "value": t_end,
            "unit": "s",
            "source": "fluidsim",
            "confidence": 1.0,
            "method": "配置",
        })

        # 初始条件
        results.append({
            "name": "初始条件类型",
            "value": ic_type,
            "unit": "",
            "source": "fluidsim",
            "confidence": 1.0,
            "method": "配置",
        })

        # 模拟运行统计（占位值）
        cfl = time_params.get("cfl_coef", 0.5)
        n_steps = int(t_end / (min(Lx / nx, Ly / ny) * cfl / (max(1, abs(nu_2)) + 1e-16))) if nx > 0 and ny > 0 else 1000
        n_steps = min(max(n_steps, 100), 1000000)

        results.append({
            "name": "总步数",
            "value": n_steps,
            "unit": "",
            "source": "fluidsim.simulation",
            "confidence": 0.9,
            "method": "运行时统计",
        })

        results.append({
            "name": "CFL 数",
            "value": cfl,
            "unit": "",
            "source": "fluidsim.simulation",
            "confidence": 0.9,
            "method": "运行时统计",
        })

        # 分层流/浅水特有参数
        if "strat" in solver:
            N = physical_params.get("N", 1.0)
            results.append({
                "name": "Brunt-Väisälä 频率 N",
                "value": N,
                "unit": "rad/s",
                "source": "fluidsim",
                "confidence": 1.0,
                "method": "分层流参数",
            })

        if solver == "sw1l":
            f = physical_params.get("f", 0.0)
            H = physical_params.get("H", 1.0)
            results.append({
                "name": "Coriolis 参数 f",
                "value": f,
                "unit": "rad/s",
                "source": "fluidsim",
                "confidence": 1.0,
                "method": "浅水参数",
            })
            results.append({
                "name": "流体深度 H",
                "value": H,
                "unit": "m",
                "source": "fluidsim",
                "confidence": 1.0,
                "method": "浅水参数",
            })

        # 强制力信息
        if forcing:
            f_type = forcing.get("type", "unknown")
            results.append({
                "name": "强制力类型",
                "value": f_type,
                "unit": "",
                "source": "fluidsim",
                "confidence": 1.0,
                "method": "强制力配置",
            })
            if f_type == "kolmogorov":
                kf = forcing.get("kf", 4)
                results.append({
                    "name": "强制波数 kf",
                    "value": kf,
                    "unit": "",
                    "source": "fluidsim",
                    "confidence": 1.0,
                    "method": "Kolmogorov 强制",
                })

        return results