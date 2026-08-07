"""分子动力学模拟服务核心实现 — 基于LAMMPS的MD仿真与轨迹分析。

基于 lammps_architecture.md 的 5 步工作流：
  数据准备 → 输入生成 → 三级验证 → 执行 → 轨迹分析
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ...contracts.task import Task
from ...contracts.run import Run
from ...contracts.artifact import Artifact, ArtifactType
from ...contracts.evidence import EvidencePackage
from ...domain.runtime import ScientificExecutionKernel
from ...infrastructure.executors import ExecutionAdapter
from ..base_service import NativeScientificService
from .validators import MolecularSimulationValidator
from .evidence_mapper import batch_map_md_evidence


class RunMolecularDynamics(BaseModel):
    """分子动力学模拟命令 — 包含 MD 模拟所需的所有参数。"""

    project_id: str = Field(..., description="项目 ID")
    system_type: str = Field(
        ..., description="系统类型: A (晶体/无机材料), B (有机/聚合物), C (生物分子)"
    )
    structure_data: str = Field(
        ..., description="结构数据: SMILES (Path B), CIF 路径 (Path A), 或 data 文件路径 (Path C)"
    )
    forcefield: str | None = Field(
        default=None, description="力场名称: EAM, OPLS-AA, ReaxFF, CHARMM, AMBER, Buckingham, Tersoff, SW 等"
    )
    protocol: str = Field(
        default="nvt", description="系综协议: nvt, npt, nve, minimize, npt_nvt"
    )
    temperature_k: float = Field(
        default=300.0, description="模拟温度 (K)"
    )
    pressure_atm: float | None = Field(
        default=None, description="模拟压力 (atm)，npt/npt_nvt 协议必需"
    )
    timestep_fs: float = Field(
        default=1.0, description="积分时间步长 (fs)"
    )
    run_steps: int = Field(
        default=100000, description="总运行步数"
    )
    requested_metrics: list[str] = Field(
        default_factory=lambda: ["rdf", "msd", "energy"],
        description="请求分析的指标列表: rdf, msd, diffusion_coefficient, rmsd, rmsf, energy, temperature, pressure, density, cna",
    )


# ── 占位适配器（当 LAMMPSAdapter 不可用时回退） ─────────────


class _PlaceholderAdapter:
    """分子动力学模拟占位适配器。

    当 LAMMPS 二进制或 Python 生态工具不可用时，提供占位模拟结果。
    实际部署时替换为 LAMMPSAdapter。
    """

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        system_type = prepared_input.get("system_type", "A")
        protocol = prepared_input.get("protocol", "nvt")
        temperature_k = prepared_input.get("temperature_k", 300.0)
        run_steps = prepared_input.get("run_steps", 100000)
        requested_metrics = prepared_input.get("requested_metrics", ["rdf", "msd", "energy"])

        analysis: list[dict[str, Any]] = []
        for metric in requested_metrics:
            analysis.append({
                "metric": metric,
                "value": f"# placeholder: {metric} 分析结果（system={system_type}, protocol={protocol}）",
                "unit": "",
                "confidence": 0.7,
                "metadata": {"method": "placeholder", "warning": "LAMMPS 适配器不可用，返回占位结果"},
            })

        return {
            "status": "completed",
            "data_file": "data.lammps",
            "script_file": "input.in",
            "log_file": "log.lammps",
            "trajectory_file": "trajectory.dump",
            "analysis": analysis,
            "warnings": ["LAMMPS 适配器不可用，使用占位模拟"],
        }

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        return {"status": "unknown", "analysis": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {"cpu": 4, "memory_mb": 2048, "walltime_minutes": 30}

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        return []


def _looks_like_path(s: str) -> bool:
    """判断字符串是否像文件路径而非 SMILES。"""
    if not s:
        return True
    if "/" in s or "\\" in s:
        return True
    lower = s.lower()
    for ext in (".cif", ".data", ".lammps", ".xyz", ".pdb", ".mol2"):
        if lower.endswith(ext):
            return True
    return False


# ── 服务实现 ────────────────────────────────────────────────


class MolecularSimulationApplication(NativeScientificService):
    """分子动力学模拟服务 (Molecular Simulation)。

    基于 LAMMPS 的分子动力学仿真，支持：
    - 三条路径：A（晶体/无机）、B（有机/聚合物）、C（生物分子）
    - 五步工作流：数据准备 → 输入生成 → 验证 → 执行 → 分析
    - 多种系综协议：NVT, NPT, NVE, minimize, NPT+NVT
    - 轨迹分析：RDF, MSD, 扩散系数, RMSD, RMSF, CNA 等
    """

    def __init__(
        self,
        kernel: ScientificExecutionKernel | None = None,
        adapter: ExecutionAdapter | None = None,
    ):
        super().__init__(kernel)
        self._adapter = adapter

    @property
    def capability_id(self) -> str:
        return "molecular_simulation"

    @property
    def display_name(self) -> str:
        return "分子动力学模拟"

    @property
    def description(self) -> str:
        return "基于LAMMPS的分子动力学仿真：数据准备、模拟执行、轨迹分析"

    # ── 生命周期 ───────────────────────────────────────────

    def validate(self, task: Task, context: dict[str, Any]) -> dict[str, Any]:
        """校验任务输入。"""
        cmd = RunMolecularDynamics(**task.metadata)
        validator = MolecularSimulationValidator(
            system_type=cmd.system_type,
            structure_data=cmd.structure_data,
            forcefield=cmd.forcefield,
            protocol=cmd.protocol,
            temperature_k=cmd.temperature_k,
            pressure_atm=cmd.pressure_atm,
            timestep_fs=cmd.timestep_fs,
            run_steps=cmd.run_steps,
            requested_metrics=cmd.requested_metrics,
        )
        return validator.validate_all()

    def prepare(self, task: Task) -> Run:
        """根据任务创建 Run 实例。"""
        cmd = RunMolecularDynamics(**task.metadata)
        return Run(
            task_id=task.task_id,
            project_id=task.project_id,
            service_id=self.capability_id,
            command="run_molecular_dynamics",
            input={
                "system_type": cmd.system_type,
                "structure_data": cmd.structure_data,
                "forcefield": cmd.forcefield,
                "protocol": cmd.protocol,
                "temperature_k": cmd.temperature_k,
                "pressure_atm": cmd.pressure_atm,
                "timestep_fs": cmd.timestep_fs,
                "run_steps": cmd.run_steps,
                "requested_metrics": cmd.requested_metrics,
            },
        )

    def execute(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行 MD 模拟，返回 Artifact 列表。"""
        prepared_input = run.input

        # 解析执行适配器（根据输入类型选择 RDKit MD 或 LAMMPS）
        adapter = self._resolve_adapter(prepared_input)

        # 执行模拟
        raw_output = adapter.execute(prepared_input)
        parsed = adapter.parse_output(raw_output)

        analysis = parsed.get("analysis", [])
        warnings = parsed.get("warnings", [])

        # 创建分析结果 Artifact
        result_artifact = Artifact(
            run_id=run.run_id,
            type=ArtifactType.RESULT_TABLE,
            name="md_analysis_results",
            description="分子动力学模拟轨迹分析结果",
            content_type="application/json",
            data={
                "analysis": analysis,
                "warnings": warnings,
                "data_file": parsed.get("data_file"),
                "script_file": parsed.get("script_file"),
                "log_file": parsed.get("log_file"),
                "trajectory_file": parsed.get("trajectory_file"),
            },
        )

        artifacts: list[Artifact] = [result_artifact]

        # 如果有 RDF 或结构数据，添加结构工件
        for entry in analysis:
            metric = entry.get("metric", "")
            if metric in ("rdf", "cna") and entry.get("value"):
                artifacts.append(
                    Artifact(
                        run_id=run.run_id,
                        type=ArtifactType.PLOT,
                        name=f"{metric}_analysis",
                        description=f"MD 模拟 {metric} 分析图",
                        content_type="application/json",
                        data={"metric": metric, "data": entry["value"]},
                    )
                )

        return artifacts

    def postprocess(self, run: Run, artifacts: list[Artifact]) -> list[EvidencePackage]:
        """后处理，将 Artifact 转换为 EvidencePackage 列表。"""
        analysis_results: list[dict[str, Any]] = []

        for art in artifacts:
            if art.data and "analysis" in art.data:
                analysis_results = art.data["analysis"]
                break

        if not analysis_results:
            return []

        return batch_map_md_evidence(
            run_id=run.run_id,
            task_id=run.task_id,
            results=analysis_results,
        )

    # ── 外部调用入口 ───────────────────────────────────────

    def run_molecular_dynamics(
        self,
        project_id: str,
        system_type: str,
        structure_data: str,
        forcefield: str | None = None,
        protocol: str = "nvt",
        temperature_k: float = 300.0,
        pressure_atm: float | None = None,
        timestep_fs: float = 1.0,
        run_steps: int = 100000,
        requested_metrics: list[str] | None = None,
    ) -> list[EvidencePackage]:
        """外部调用入口 — 一次性完成分子动力学模拟全流程。

        Args:
            project_id: 项目 ID。
            system_type: 系统类型 (A/B/C)。
            structure_data: 结构数据（SMILES、CIF 路径或 data 文件路径）。
            forcefield: 力场名称；为 None 时使用系统类型默认力场。
            protocol: 系综协议。
            temperature_k: 温度 (K)。
            pressure_atm: 压力 (atm)。
            timestep_fs: 时间步长 (fs)。
            run_steps: 运行步数。
            requested_metrics: 请求分析的指标列表。

        Returns:
            证据包列表。
        """
        cmd = RunMolecularDynamics(
            project_id=project_id,
            system_type=system_type,
            structure_data=structure_data,
            forcefield=forcefield,
            protocol=protocol,
            temperature_k=temperature_k,
            pressure_atm=pressure_atm,
            timestep_fs=timestep_fs,
            run_steps=run_steps,
            requested_metrics=requested_metrics or ["rdf", "msd", "energy"],
        )

        task = Task(
            project_id=project_id,
            capability_id=self.capability_id,
            title="分子动力学模拟",
            description=f"系统类型 {system_type}，协议 {protocol}，温度 {temperature_k}K，{run_steps} 步",
            metadata=cmd.model_dump(),
        )

        context: dict[str, Any] = {}
        return self.run_full_cycle(task, context)

    # ── 内部辅助 ───────────────────────────────────────────

    def _resolve_adapter(
        self, prepared_input: dict[str, Any] | None = None
    ) -> ExecutionAdapter | _PlaceholderAdapter:
        """解析执行适配器。

        优先级：
        1. 注入的 adapter（测试或显式注入）
        2. system_type=B 且输入为 SMILES 时，优先 OpenMM（真实 MD），其次 RDKit MD（准 MD）
        3. 尝试加载 LAMMPSAdapter（晶体/周期性体系，Docker 优先）
        4. 回退到 _PlaceholderAdapter
        """
        if self._adapter is not None:
            return self._adapter

        # 有机小分子 + SMILES 输入 → OpenMM 优先，RDKit MD 兜底
        if prepared_input is not None:
            system_type = prepared_input.get("system_type", "")
            structure_data = prepared_input.get("structure_data", "")
            if (
                system_type == "B"
                and isinstance(structure_data, str)
                and structure_data
                and not _looks_like_path(structure_data)
            ):
                # OpenMM（真实 MD，AMBER14/GAFF 力场）
                try:
                    from ...infrastructure.executors.openmm_adapter import (
                        OpenMMAdapter,
                    )
                    adapter = OpenMMAdapter()
                    if adapter.is_available():
                        return adapter
                except ImportError:
                    pass
                # RDKit MD（准 MD，MMFF94/UFF 力场）
                try:
                    from ...infrastructure.executors.rdkit_md_adapter import (
                        RDKitMDAdapter,
                    )
                    return RDKitMDAdapter()
                except ImportError:
                    pass

        # 尝试加载 LAMMPSAdapter（晶体/周期性体系）
        try:
            from ...infrastructure.executors.lammps_adapter import LAMMPSAdapter
            return LAMMPSAdapter()
        except ImportError:
            return _PlaceholderAdapter()