"""波函数分析服务核心实现 — 基于 Multiwfn 的 ESP 分析、轨道分析、本地 VMD 渲染。

基于 OpenMultiwfnFlow 设计文档：
  文件选择 → 格式识别 → 参数校验 → Multiwfn 驱动 → 结果解析 → 渲染
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ...contracts.task import Task
from ...contracts.run import Run
from ...contracts.artifact import Artifact, ArtifactType
from ...contracts.evidence import EvidencePackage
from ...domain.runtime import ScientificExecutionKernel
from ..base_service import NativeScientificService
from .validators import WavefunctionValidator
from .evidence_mapper import batch_map_wavefunction_evidence


# ── 命令模型 ────────────────────────────────────────────────


class AnalyzeESP(BaseModel):
    """ESP 分析命令 — 基于 Multiwfn 的分子表面静电势分析。"""

    project_id: str = Field(..., description="项目 ID")
    input_file: str = Field(..., description="波函数文件路径")
    file_format: str = Field(..., description="文件格式: molden, fchk, wfn, wfx")
    surface_type: str = Field(default="molecular", description="ESP 表面类型: molecular, vdw, electron_density")
    bins: int = Field(default=100, description="ESP 区间数")
    generate_cubes: bool = Field(default=True, description="是否生成 Cube 文件")


class AnalyzeOrbitals(BaseModel):
    """轨道分析命令 — HOMO/LUMO 识别与 Cube 输出。"""

    project_id: str = Field(..., description="项目 ID")
    input_file: str = Field(..., description="波函数文件路径")
    file_format: str = Field(..., description="文件格式: molden, fchk, wfn, wfx")
    below_homo: int = Field(default=3, description="HOMO 以下轨道数")
    above_lumo: int = Field(default=3, description="LUMO 以上轨道数")
    grid_quality: str = Field(default="high", description="网格质量: low, medium, high, very_high")


class RenderOrbital(BaseModel):
    """渲染命令 — 将分析结果渲染为图片。"""

    project_id: str = Field(..., description="项目 ID")
    input_dir: str = Field(..., description="含有 Cube 文件的目录路径")
    render_type: str = Field(..., description="渲染类型: esp, orbital")
    image_format: str = Field(default="png", description="图片格式: png, tiff, bmp, jpg, tga")
    width: int = Field(default=1800, description="渲染宽度 (px)")
    height: int = Field(default=1200, description="渲染高度 (px)")


class BatchAnalysis(BaseModel):
    """批量分析命令 — 对多个文件执行 ESP 或轨道分析。"""

    project_id: str = Field(..., description="项目 ID")
    files: list[str] = Field(..., description="波函数文件路径列表")
    mode: str = Field(..., description="分析模式: esp, orbital")
    workers: int = Field(default=1, description="并行 worker 数")
    fail_fast: bool = Field(default=False, description="失败时是否立即停止")


# ── 占位适配器（当 MultiwfnAdapter 不可用时回退） ─────────────


class _PlaceholderAdapter:
    """波函数分析占位适配器。

    当 Multiwfn 二进制或 VMD 不可用时，提供占位分析结果。
    实际部署时替换为 MultiwfnAdapter。
    """

    def execute_esp(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        file_format = prepared_input.get("file_format", "fchk")
        surface_type = prepared_input.get("surface_type", "molecular")
        bins = prepared_input.get("bins", 100)
        generate_cubes = prepared_input.get("generate_cubes", True)

        results: list[dict[str, Any]] = [
            {
                "type": "esp_surface",
                "claim": "ESP 表面统计分析",
                "value": {
                    "min": -25.4,
                    "max": 18.7,
                    "mean": -3.2,
                    "variance": 120.5,
                    "positive_area_pct": 32.1,
                    "negative_area_pct": 67.9,
                },
                "unit": "kcal/mol",
                "confidence": 0.85,
                "metadata": {
                    "file_format": file_format,
                    "surface_type": surface_type,
                    "bins": bins,
                    "method": "placeholder",
                    "warning": "Multiwfn 适配器不可用，返回占位 ESP 结果",
                },
            },
            {
                "type": "esp_area",
                "claim": "ESP 区间面积分布",
                "value": {
                    "bins": bins,
                    "distribution": [f"# placeholder: bin {i} area distribution" for i in range(bins)],
                },
                "unit": "kcal/mol",
                "confidence": 0.80,
                "metadata": {"method": "placeholder"},
            },
            {
                "type": "esp_atomic",
                "claim": "原子局部 ESP 统计",
                "value": {
                    "atom_count": 10,
                    "local_min_esp": -25.4,
                    "local_max_esp": 18.7,
                    "surface_area_ang2": 85.3,
                },
                "unit": "kcal/mol",
                "confidence": 0.80,
                "metadata": {"method": "placeholder"},
            },
        ]
        if generate_cubes:
            results.append({
                "type": "esp_cube",
                "claim": "ESP Cube 文件",
                "value": "esp.cube",
                "unit": "",
                "confidence": 0.85,
                "metadata": {"cube_path": "esp.cube", "method": "placeholder"},
            })

        return {"status": "completed", "results": results, "warnings": ["Multiwfn 适配器不可用，使用占位 ESP 分析"]}

    def execute_orbitals(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        file_format = prepared_input.get("file_format", "fchk")
        below_homo = prepared_input.get("below_homo", 3)
        above_lumo = prepared_input.get("above_lumo", 3)
        grid_quality = prepared_input.get("grid_quality", "high")

        total_orbitals = below_homo + above_lumo + 1  # +1 for HOMO itself
        orbital_list: list[dict[str, Any]] = []
        for i in range(below_homo, 0, -1):
            orbital_list.append({
                "index": f"HOMO-{i}",
                "energy_eV": -8.5 - i * 0.3,
                "occupation": 2.0,
                "symmetry": "A",
            })
        orbital_list.append({
            "index": "HOMO",
            "energy_eV": -5.2,
            "occupation": 2.0,
            "symmetry": "A",
        })
        for i in range(1, above_lumo + 1):
            orbital_list.append({
                "index": f"LUMO+{i}",
                "energy_eV": 1.5 + i * 0.4,
                "occupation": 0.0,
                "symmetry": "A",
            })

        homo_energy = orbital_list[below_homo]["energy_eV"]
        lumo_energy = orbital_list[below_homo + 1]["energy_eV"]
        gap = lumo_energy - homo_energy

        results: list[dict[str, Any]] = [
            {
                "type": "orbital_energy",
                "claim": f"轨道能级分析（{below_homo} below HOMO + {above_lumo} above LUMO）",
                "value": {
                    "orbitals": orbital_list,
                    "homo_index": "HOMO",
                    "lumo_index": "LUMO+1",
                    "homo_energy_eV": homo_energy,
                    "lumo_energy_eV": lumo_energy,
                },
                "unit": "eV",
                "confidence": 0.90,
                "metadata": {
                    "file_format": file_format,
                    "grid_quality": grid_quality,
                    "method": "placeholder",
                    "warning": "Multiwfn 适配器不可用，返回占位轨道分析结果",
                },
            },
            {
                "type": "orbital_gap",
                "claim": "HOMO-LUMO 能隙",
                "value": round(gap, 4),
                "unit": "eV",
                "confidence": 0.95,
                "metadata": {"method": "placeholder"},
            },
        ]

        # 添加 Cube 路径占位
        for orb in orbital_list:
            results.append({
                "type": "orbital_cube",
                "claim": f"{orb['index']} 轨道 Cube 文件",
                "value": f"{orb['index'].lower().replace('+', 'p').replace('-', 'm')}.cube",
                "unit": "",
                "confidence": 0.85,
                "metadata": {"orbital": orb["index"], "method": "placeholder"},
            })

        return {"status": "completed", "results": results, "warnings": ["Multiwfn 适配器不可用，使用占位轨道分析"]}

    def execute_render(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        input_dir = prepared_input.get("input_dir", ".")
        render_type = prepared_input.get("render_type", "orbital")
        image_format = prepared_input.get("image_format", "png")
        width = prepared_input.get("width", 1800)
        height = prepared_input.get("height", 1200)

        results: list[dict[str, Any]] = [
            {
                "type": "render_script",
                "claim": f"{'ESP' if render_type == 'esp' else '轨道'} 渲染 VMD Tcl 脚本",
                "value": {
                    "script": f"# placeholder VMD script for {render_type} rendering",
                    "engine": "vmd",
                    "input_dir": input_dir,
                },
                "unit": "",
                "confidence": 0.85,
                "metadata": {
                    "render_type": render_type,
                    "engine": "vmd",
                    "method": "placeholder",
                    "warning": "VMD 适配器不可用，返回占位渲染脚本",
                },
            },
            {
                "type": "render_image",
                "claim": f"{'ESP' if render_type == 'esp' else '轨道'} 渲染图片",
                "value": f"{render_type}_render.{image_format}",
                "unit": "",
                "confidence": 0.80,
                "metadata": {
                    "render_type": render_type,
                    "image_format": image_format,
                    "width": width,
                    "height": height,
                    "method": "placeholder",
                },
            },
        ]

        return {"status": "completed", "results": results, "warnings": ["VMD 不可用，使用占位渲染结果"]}

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        return {"status": "unknown", "results": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {"cpu": 2, "memory_mb": 1024, "walltime_minutes": 10}

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        return []


def _looks_like_path(s: str) -> bool:
    """判断字符串是否像文件路径而非 SMILES。"""
    if not s:
        return True
    if "/" in s or "\\" in s:
        return True
    lower = s.lower()
    for ext in (".fchk", ".molden", ".wfn", ".wfx", ".fch", ".mold", ".xyz", ".pdb", ".mol2"):
        if lower.endswith(ext):
            return True
    return False


# ── 服务实现 ────────────────────────────────────────────────


class WavefunctionAnalysisApplication(NativeScientificService):
    """波函数分析服务 (Wavefunction Analysis)。

    基于 Multiwfn 的波函数后处理，支持：
    - ESP 分析：分子表面静电势分析（表面统计 → 区间分布 → 原子统计 → Cube）
    - 轨道分析：HOMO/LUMO 识别 + Cube 输出
    - 渲染：VMD Tcl 脚本生成（本地 VMD 渲染）
    """

    def __init__(
        self,
        kernel: ScientificExecutionKernel | None = None,
        adapter: _PlaceholderAdapter | None = None,
    ):
        super().__init__(kernel)
        self._adapter = adapter

    @property
    def capability_id(self) -> str:
        return "wavefunction_analysis"

    @property
    def display_name(self) -> str:
        return "波函数分析"

    @property
    def description(self) -> str:
        return "基于 Multiwfn 的波函数后处理：ESP 分析、HOMO/LUMO 轨道分析、本地 VMD 渲染"

    # ── 生命周期 ───────────────────────────────────────────

    def validate(self, task: Task, context: dict[str, Any]) -> dict[str, Any]:
        """校验任务输入。"""
        cmd = self._parse_command(task)
        command = cmd.get("command", "")
        # Render 命令不需要校验 input_file
        input_file = cmd.get("input_file", "")
        if command == "render_orbital":
            input_file = input_file or "render_placeholder"
        validator = WavefunctionValidator(
            input_file=input_file,
            file_format=cmd.get("file_format", "fchk"),
            surface_type=cmd.get("surface_type", "molecular"),
            bins=cmd.get("bins", 100),
            generate_cubes=cmd.get("generate_cubes", True),
            below_homo=cmd.get("below_homo", 3),
            above_lumo=cmd.get("above_lumo", 3),
            grid_quality=cmd.get("grid_quality", "high"),
            render_engine=cmd.get("render_engine", "vmd"),
            image_format=cmd.get("image_format", "png"),
            width=cmd.get("width", 1800),
            height=cmd.get("height", 1200),
            workers=cmd.get("workers", 1),
            fail_fast=cmd.get("fail_fast", False),
        )
        return validator.validate_all()

    def prepare(self, task: Task) -> Run:
        """根据任务创建 Run 实例。"""
        cmd = self._parse_command(task)
        return Run(
            task_id=task.task_id,
            project_id=task.project_id,
            service_id=self.capability_id,
            command=task.metadata.get("command", "unknown"),
            input=cmd,
        )

    def execute(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行波函数分析，返回 Artifact 列表。"""
        prepared_input = run.input
        command = run.command

        adapter = self._resolve_adapter(prepared_input)

        # 根据命令类型分发
        if command == "analyze_esp":
            raw_output = adapter.execute_esp(prepared_input)
        elif command == "analyze_orbitals":
            raw_output = adapter.execute_orbitals(prepared_input)
        elif command == "render_orbital":
            raw_output = adapter.execute_render(prepared_input)
        else:
            raw_output = {"status": "unknown", "results": [], "warnings": [f"未知命令: {command}"]}

        parsed = adapter.parse_output(raw_output)
        results = parsed.get("results", [])
        warnings = parsed.get("warnings", [])

        # 创建结果 Artifact
        result_artifact = Artifact(
            run_id=run.run_id,
            type=ArtifactType.RESULT_TABLE,
            name=f"{command}_results",
            description=f"波函数分析 {command} 结果",
            content_type="application/json",
            data={
                "results": results,
                "warnings": warnings,
                "command": command,
            },
        )

        artifacts: list[Artifact] = [result_artifact]

        # 为 ESP/轨道/渲染结果创建额外的 PLOT/CUBE 工件
        for entry in results:
            etype = entry.get("type", "")
            if etype in ("esp_cube", "orbital_cube"):
                artifacts.append(
                    Artifact(
                        run_id=run.run_id,
                        type=ArtifactType.OTHER,
                        name=f"{etype}_{entry.get('claim', 'unknown')}",
                        description=entry.get("claim", ""),
                        content_type="application/octet-stream",
                        data={"type": etype, "file": entry.get("value"), "metadata": entry.get("metadata", {})},
                    )
                )
            elif etype == "render_image":
                artifacts.append(
                    Artifact(
                        run_id=run.run_id,
                        type=ArtifactType.PLOT,
                        name=f"render_{entry.get('claim', 'image')}",
                        description=entry.get("claim", ""),
                        content_type=f"image/{entry.get('metadata', {}).get('image_format', 'png')}",
                        data={"type": "render", "file": entry.get("value"), "metadata": entry.get("metadata", {})},
                    )
                )

        return artifacts

    def postprocess(self, run: Run, artifacts: list[Artifact]) -> list[EvidencePackage]:
        """后处理，将 Artifact 转换为 EvidencePackage 列表。"""
        results: list[dict[str, Any]] = []

        for art in artifacts:
            if art.data and "results" in art.data:
                results = art.data["results"]
                break

        if not results:
            return []

        return batch_map_wavefunction_evidence(
            run_id=run.run_id,
            task_id=run.task_id,
            results=results,
        )

    # ── 外部调用入口 ───────────────────────────────────────

    def analyze_esp(
        self,
        project_id: str,
        input_file: str,
        file_format: str,
        surface_type: str = "molecular",
        bins: int = 100,
        generate_cubes: bool = True,
    ) -> list[EvidencePackage]:
        """外部调用入口 — 执行 ESP 分析全流程。

        Args:
            project_id: 项目 ID。
            input_file: 波函数文件路径。
            file_format: 文件格式 (molden, fchk, wfn, wfx)。
            surface_type: ESP 表面类型。
            bins: ESP 区间数。
            generate_cubes: 是否生成 Cube 文件。

        Returns:
            证据包列表。
        """
        cmd = AnalyzeESP(
            project_id=project_id,
            input_file=input_file,
            file_format=file_format,
            surface_type=surface_type,
            bins=bins,
            generate_cubes=generate_cubes,
        )

        task = Task(
            project_id=project_id,
            capability_id=self.capability_id,
            title="ESP 分析",
            description=f"文件格式 {file_format}，表面类型 {surface_type}，{bins} 区间",
            metadata={"command": "analyze_esp", **cmd.model_dump()},
        )

        return self.run_full_cycle(task)

    def analyze_orbitals(
        self,
        project_id: str,
        input_file: str,
        file_format: str,
        below_homo: int = 3,
        above_lumo: int = 3,
        grid_quality: str = "high",
    ) -> list[EvidencePackage]:
        """外部调用入口 — 执行轨道分析全流程。

        Args:
            project_id: 项目 ID。
            input_file: 波函数文件路径。
            file_format: 文件格式 (molden, fchk, wfn, wfx)。
            below_homo: HOMO 以下轨道数。
            above_lumo: LUMO 以上轨道数。
            grid_quality: 网格质量。

        Returns:
            证据包列表。
        """
        cmd = AnalyzeOrbitals(
            project_id=project_id,
            input_file=input_file,
            file_format=file_format,
            below_homo=below_homo,
            above_lumo=above_lumo,
            grid_quality=grid_quality,
        )

        task = Task(
            project_id=project_id,
            capability_id=self.capability_id,
            title="轨道分析",
            description=f"文件格式 {file_format}，{below_homo} below HOMO + {above_lumo} above LUMO",
            metadata={"command": "analyze_orbitals", **cmd.model_dump()},
        )

        return self.run_full_cycle(task)

    def render_orbital(
        self,
        project_id: str,
        input_dir: str,
        render_type: str = "orbital",
        image_format: str = "png",
        width: int = 1800,
        height: int = 1200,
    ) -> list[EvidencePackage]:
        """外部调用入口 — 执行渲染全流程。

        Args:
            project_id: 项目 ID。
            input_dir: 含有 Cube 文件的目录路径。
            render_type: 渲染类型 (esp, orbital)。
            image_format: 图片格式。
            width: 渲染宽度 (px)。
            height: 渲染高度 (px)。

        Returns:
            证据包列表。
        """
        cmd = RenderOrbital(
            project_id=project_id,
            input_dir=input_dir,
            render_type=render_type,
            image_format=image_format,
            width=width,
            height=height,
        )

        task = Task(
            project_id=project_id,
            capability_id=self.capability_id,
            title="波函数渲染",
            description=f"渲染类型 {render_type}，格式 {image_format}，{width}x{height}",
            metadata={"command": "render_orbital", **cmd.model_dump()},
        )

        return self.run_full_cycle(task)

    def batch_analysis(
        self,
        project_id: str,
        files: list[str],
        mode: str = "esp",
        workers: int = 1,
        fail_fast: bool = False,
    ) -> list[list[EvidencePackage]]:
        """外部调用入口 — 批量分析全流程。

        Args:
            project_id: 项目 ID。
            files: 波函数文件路径列表。
            mode: 分析模式 (esp, orbital)。
            workers: 并行 worker 数。
            fail_fast: 失败时是否立即停止。

        Returns:
            每个文件的证据包列表的列表。
        """
        cmd = BatchAnalysis(
            project_id=project_id,
            files=files,
            mode=mode,
            workers=workers,
            fail_fast=fail_fast,
        )

        all_evidence: list[list[EvidencePackage]] = []
        for file_path in cmd.files:
            if mode == "esp":
                evidence = self.analyze_esp(
                    project_id=project_id,
                    input_file=file_path,
                    file_format="fchk",  # 批量模式默认 fchk
                )
            else:
                evidence = self.analyze_orbitals(
                    project_id=project_id,
                    input_file=file_path,
                    file_format="fchk",
                )
            all_evidence.append(evidence)

        return all_evidence

    # ── 内部辅助 ───────────────────────────────────────────

    @staticmethod
    def _parse_command(task: Task) -> dict[str, Any]:
        """从 task.metadata 解析命令参数。"""
        return task.metadata

    def _resolve_adapter(
        self, prepared_input: dict[str, Any] | None = None
    ) -> _PlaceholderAdapter:
        """解析执行适配器。

        优先级：
        1. 注入的 adapter（测试或显式注入）
        2. input_file 为 SMILES 时，优先 PySCF Docker（真实 DFT），其次 RDKit ESP（经验电荷近似）
        3. 尝试加载 MultiwfnAdapter（波函数文件输入）
        4. 回退到 _PlaceholderAdapter
        """
        if self._adapter is not None:
            return self._adapter

        # SMILES 输入 → PySCF Docker 优先，RDKit ESP 兜底
        if prepared_input is not None:
            input_file = prepared_input.get("input_file", "")
            if isinstance(input_file, str) and input_file and not _looks_like_path(input_file):
                # PySCF Docker（真实 B3LYP/6-31G* DFT + ESP）
                try:
                    from ...infrastructure.executors.pyscf_adapter import PySCFAdapter
                    adapter = PySCFAdapter()
                    # 仅当 Docker science-engine 可用时启用
                    if adapter.is_available():
                        return adapter
                except ImportError:
                    pass
                # RDKit ESP（Gasteiger 电荷近似）
                try:
                    from ...infrastructure.executors.rdkit_esp_adapter import RDKitESPAdapter
                    return RDKitESPAdapter()
                except ImportError:
                    pass

        try:
            from ...infrastructure.executors.multiwfn_adapter import MultiwfnAdapter
            return MultiwfnAdapter()
        except ImportError:
            return _PlaceholderAdapter()