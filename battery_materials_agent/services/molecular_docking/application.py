"""分子对接服务核心实现 — 基于扩散模型的蛋白-小分子对接。

支持三种工作流：
  - DockSingle：单次对接
  - DockBatch：批量虚拟筛选
  - AnalyzeDocking：对接结果分析
  - ExportDocking：结果导出
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
from .validators import MolecularDockingValidator
from .evidence_mapper import batch_map_docking_evidence, map_screen_summary


# ── 命令模型 ────────────────────────────────────────────────


class DockSingle(BaseModel):
    """单次分子对接命令 — 对一个蛋白-配体对进行对接。"""

    project_id: str = Field(..., description="项目 ID")
    protein_path: str = Field(..., description="受体蛋白文件路径 (PDB/mmCIF)")
    ligand: str = Field(..., description="配体数据（SMILES 字符串或文件路径）")
    ligand_format: str = Field(default="smiles", description="配体格式: smiles, sdf, mol2")
    samples_per_complex: int = Field(default=10, description="每个复合物采样数 (1-50)")
    inference_steps: int = Field(default=20, description="扩散模型推理步数 (10-50)")
    device: str = Field(default="cpu", description="推理设备: cpu, cuda")


class DockBatch(BaseModel):
    """批量虚拟筛选命令 — 对多个蛋白-配体对进行并行对接。"""

    project_id: str = Field(..., description="项目 ID")
    complexes: list[dict[str, Any]] = Field(
        ..., description="复合物列表，每项包含 receptor_path, ligand, ligand_format 等"
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="全局配置，可覆盖 samples_per_complex, inference_steps, device 等",
    )
    workers: int = Field(default=1, description="并行工作进程数 (1-16)")


class AnalyzeDocking(BaseModel):
    """对接结果分析命令 — 对已完成的对接结果进行排序和筛选。"""

    project_id: str = Field(..., description="项目 ID")
    workdir: str = Field(..., description="对接结果工作目录")
    top_n: int = Field(default=20, description="返回 Top-N 位姿 (1-1000)")
    confidence_threshold: float = Field(default=0.0, description="置信度过滤阈值 (0.0-1.0)")


class ExportDocking(BaseModel):
    """对接结果导出命令 — 将对接结果导出为指定格式。"""

    project_id: str = Field(..., description="项目 ID")
    workdir: str = Field(..., description="对接结果工作目录")
    format: str = Field(default="sdf", description="导出格式: sdf, csv, html")


# ── 占位适配器 ──────────────────────────────────────────────


class _PlaceholderAdapter:
    """分子对接占位适配器。

    当扩散模型不可用时，提供占位对接结果。
    实际部署时替换为真实 DockingAdapter。
    """

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        protein_path = prepared_input.get("protein_path", "unknown.pdb")
        ligand = prepared_input.get("ligand", "CCO")
        samples = prepared_input.get("samples_per_complex", 10)
        steps = prepared_input.get("inference_steps", 20)

        poses: list[dict[str, Any]] = []
        for rank in range(1, min(samples, 5) + 1):
            confidence = max(0.0, 0.95 - (rank - 1) * 0.1)
            poses.append({
                "rank": rank,
                "confidence": round(confidence, 3),
                "sdf_path": f"poses/{rank:04d}_pose.sdf",
                "metadata": {"method": "placeholder", "seed": rank * 42},
            })

        return {
            "status": "completed",
            "complex_index": prepared_input.get("complex_index", 0),
            "runtime_seconds": 15.0 + samples * 2.0 + steps * 0.5,
            "receptor_path": protein_path,
            "ligand": ligand,
            "poses": poses,
            "warnings": ["扩散模型适配器不可用，使用占位对接结果"],
        }

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        return {"status": "unknown", "poses": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {"cpu": 4, "memory_mb": 4096, "walltime_minutes": 30, "gpu": 0}

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        return []


# ── 服务实现 ────────────────────────────────────────────────


class MolecularDockingApplication(NativeScientificService):
    """分子对接服务 (Molecular Docking)。

    基于扩散模型的蛋白-小分子对接，支持：
    - 单次对接：给定受体和配体，生成对接位姿
    - 虚拟筛选：批量对接多个复合物
    - 结果分析：排序、过滤、聚类
    - 结果导出：SDF / CSV / HTML
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
        return "molecular_docking"

    @property
    def display_name(self) -> str:
        return "分子对接"

    @property
    def description(self) -> str:
        return "基于扩散模型的蛋白-小分子对接：单对接、虚拟筛选、结果分析"

    # ── 生命周期 ───────────────────────────────────────────

    def validate(self, task: Task, context: dict[str, Any]) -> dict[str, Any]:
        """校验任务输入。"""
        metadata = task.metadata
        command = metadata.get("command", "dock_single")

        if command == "dock_single":
            cmd = DockSingle(**metadata)
            validator = MolecularDockingValidator(
                receptor_path=cmd.protein_path,
                ligand=cmd.ligand,
                ligand_format=cmd.ligand_format,
                samples_per_complex=cmd.samples_per_complex,
                inference_steps=cmd.inference_steps,
            )
            return validator.validate_all()
        elif command == "dock_batch":
            cmd = DockBatch(**metadata)
            from .validators import validate_batch_params
            return validate_batch_params(cmd.complexes, cmd.workers)
        elif command == "analyze_docking":
            cmd = AnalyzeDocking(**metadata)
            from .validators import validate_confidence_threshold, validate_top_n
            result: dict[str, Any] = {"valid": True, "errors": [], "warnings": []}
            tn_result = validate_top_n(cmd.top_n)
            result["errors"].extend(tn_result["errors"])
            ct_result = validate_confidence_threshold(cmd.confidence_threshold)
            result["errors"].extend(ct_result["errors"])
            if result["errors"]:
                result["valid"] = False
            return result
        elif command == "export_docking":
            cmd = ExportDocking(**metadata)
            if cmd.format not in ("sdf", "csv", "html"):
                return {"valid": False, "errors": [f"不支持的导出格式 '{cmd.format}'，支持: sdf, csv, html"], "warnings": []}
            return {"valid": True, "errors": [], "warnings": []}
        else:
            return {"valid": False, "errors": [f"未知命令: {command}"], "warnings": []}

    def prepare(self, task: Task) -> Run:
        """根据任务创建 Run 实例。"""
        metadata = task.metadata
        command = metadata.get("command", "dock_single")

        run_input: dict[str, Any] = {}
        if command == "dock_single":
            cmd = DockSingle(**metadata)
            run_input = cmd.model_dump()
        elif command == "dock_batch":
            cmd = DockBatch(**metadata)
            run_input = cmd.model_dump()
        elif command == "analyze_docking":
            cmd = AnalyzeDocking(**metadata)
            run_input = cmd.model_dump()
        elif command == "export_docking":
            cmd = ExportDocking(**metadata)
            run_input = cmd.model_dump()

        return Run(
            task_id=task.task_id,
            project_id=task.project_id,
            service_id=self.capability_id,
            command=command,
            input=run_input,
        )

    def execute(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行分子对接，返回 Artifact 列表。"""
        adapter = self._resolve_adapter()
        command = run.input.get("command", "dock_single")

        if command == "dock_single":
            return self._execute_dock_single(run, adapter)
        elif command == "dock_batch":
            return self._execute_dock_batch(run, adapter)
        elif command == "analyze_docking":
            return self._execute_analyze(run)
        elif command == "export_docking":
            return self._execute_export(run)
        else:
            return []

    def postprocess(self, run: Run, artifacts: list[Artifact]) -> list[EvidencePackage]:
        """后处理，将 Artifact 转换为 EvidencePackage 列表。"""
        command = run.input.get("command", "dock_single")
        results: list[dict[str, Any]] = []

        for art in artifacts:
            if art.data and "results" in art.data:
                results = art.data["results"]
            elif art.data and "summary" in art.data:
                # 筛选摘要
                summary = art.data["summary"]
                return [
                    map_screen_summary(
                        run_id=run.run_id,
                        task_id=run.task_id,
                        best_confidence=summary.get("best_confidence", 0.0),
                        best_rank=summary.get("best_rank", 0),
                        best_pose_path=summary.get("best_pose_path", ""),
                        total_complexes=summary.get("total_complexes", 0),
                        total_poses=summary.get("total_poses", 0),
                    )
                ]

        if not results:
            return []

        if command == "dock_batch":
            return batch_map_docking_evidence(
                run_id=run.run_id,
                task_id=run.task_id,
                results=results,
            )
        else:
            # 单次对接结果也走 batch 映射
            single_results = [{
                "complex_index": 0,
                "status": "success",
                "runtime_seconds": results[0].get("runtime_seconds") if results else None,
                "poses": results[0].get("poses", []) if results else [],
            }] if results and isinstance(results[0], dict) and "poses" in results[0] else []
            return batch_map_docking_evidence(
                run_id=run.run_id,
                task_id=run.task_id,
                results=single_results,
            )

    # ── 外部调用入口 ───────────────────────────────────────

    def dock_single(
        self,
        project_id: str,
        protein_path: str,
        ligand: str,
        ligand_format: str = "smiles",
        samples_per_complex: int = 10,
        inference_steps: int = 20,
        device: str = "cpu",
    ) -> list[EvidencePackage]:
        """单次分子对接入口。

        Args:
            project_id: 项目 ID。
            protein_path: 受体蛋白文件路径。
            ligand: 配体数据（SMILES 或文件路径）。
            ligand_format: 配体格式。
            samples_per_complex: 采样数。
            inference_steps: 推理步数。
            device: 推理设备。

        Returns:
            证据包列表。
        """
        cmd = DockSingle(
            project_id=project_id,
            protein_path=protein_path,
            ligand=ligand,
            ligand_format=ligand_format,
            samples_per_complex=samples_per_complex,
            inference_steps=inference_steps,
            device=device,
        )
        metadata = cmd.model_dump()
        metadata["command"] = "dock_single"

        task = Task(
            project_id=project_id,
            capability_id=self.capability_id,
            title="分子对接（单次）",
            description=f"受体 {protein_path}，配体 {ligand[:60]}",
            metadata=metadata,
        )
        return self.run_full_cycle(task)

    def dock_batch(
        self,
        project_id: str,
        complexes: list[dict[str, Any]],
        config: dict[str, Any] | None = None,
        workers: int = 1,
    ) -> list[EvidencePackage]:
        """批量虚拟筛选入口。

        Args:
            project_id: 项目 ID。
            complexes: 复合物列表。
            config: 全局配置。
            workers: 并行工作进程数。

        Returns:
            证据包列表。
        """
        cmd = DockBatch(
            project_id=project_id,
            complexes=complexes,
            config=config or {},
            workers=workers,
        )
        metadata = cmd.model_dump()
        metadata["command"] = "dock_batch"

        task = Task(
            project_id=project_id,
            capability_id=self.capability_id,
            title="分子对接（批量虚拟筛选）",
            description=f"批量筛选 {len(complexes)} 个复合物，{workers} 个工作进程",
            metadata=metadata,
        )
        return self.run_full_cycle(task)

    def analyze_docking(
        self,
        project_id: str,
        workdir: str,
        top_n: int = 20,
        confidence_threshold: float = 0.0,
    ) -> list[EvidencePackage]:
        """对接结果分析入口。

        Args:
            project_id: 项目 ID。
            workdir: 对接结果工作目录。
            top_n: 返回 Top-N 位姿。
            confidence_threshold: 置信度过滤阈值。

        Returns:
            证据包列表。
        """
        cmd = AnalyzeDocking(
            project_id=project_id,
            workdir=workdir,
            top_n=top_n,
            confidence_threshold=confidence_threshold,
        )
        metadata = cmd.model_dump()
        metadata["command"] = "analyze_docking"

        task = Task(
            project_id=project_id,
            capability_id=self.capability_id,
            title="对接结果分析",
            description=f"分析 {workdir} 中的对接结果，Top-{top_n}，置信度阈值 {confidence_threshold}",
            metadata=metadata,
        )
        return self.run_full_cycle(task)

    def export_docking(
        self,
        project_id: str,
        workdir: str,
        format: str = "sdf",
    ) -> list[EvidencePackage]:
        """对接结果导出入口。

        Args:
            project_id: 项目 ID。
            workdir: 对接结果工作目录。
            format: 导出格式 (sdf/csv/html)。

        Returns:
            证据包列表。
        """
        cmd = ExportDocking(
            project_id=project_id,
            workdir=workdir,
            format=format,
        )
        metadata = cmd.model_dump()
        metadata["command"] = "export_docking"

        task = Task(
            project_id=project_id,
            capability_id=self.capability_id,
            title="对接结果导出",
            description=f"导出 {workdir} 中的对接结果，格式 {format}",
            metadata=metadata,
        )
        return self.run_full_cycle(task)

    # ── 内部执行 ───────────────────────────────────────────

    def _execute_dock_single(
        self,
        run: Run,
        adapter: ExecutionAdapter | _PlaceholderAdapter,
    ) -> list[Artifact]:
        """执行单次对接。"""
        cmd = DockSingle(**run.input)
        prepared_input = cmd.model_dump()

        raw_output = adapter.execute(prepared_input)
        parsed = adapter.parse_output(raw_output)

        poses = parsed.get("poses", [])
        warnings = parsed.get("warnings", [])

        result_artifact = Artifact(
            run_id=run.run_id,
            type=ArtifactType.RESULT_TABLE,
            name="docking_results",
            description="分子对接结果",
            content_type="application/json",
            data={
                "results": [parsed],
                "warnings": warnings,
                "receptor_path": cmd.protein_path,
                "ligand": cmd.ligand,
                "total_poses": len(poses),
            },
        )

        artifacts: list[Artifact] = [result_artifact]

        # 为高置信度位姿添加结构工件
        for pose in poses:
            if pose.get("confidence", 0) >= 0.9:
                artifacts.append(
                    Artifact(
                        run_id=run.run_id,
                        type=ArtifactType.STRUCTURE,
                        name=f"pose_top{pose.get('rank', 0)}",
                        description=f"对接位姿 Top-{pose.get('rank', 0)}（置信度 {pose.get('confidence', 0):.2f}）",
                        content_type="chemical/x-mdl-sdfile",
                        file_path=pose.get("sdf_path"),
                    )
                )

        return artifacts

    def _execute_dock_batch(
        self,
        run: Run,
        adapter: ExecutionAdapter | _PlaceholderAdapter,
    ) -> list[Artifact]:
        """执行批量虚拟筛选。"""
        cmd = DockBatch(**run.input)
        all_results: list[dict[str, Any]] = []
        total_poses = 0

        for i, cx in enumerate(cmd.complexes):
            prepared_input = {
                "protein_path": cx.get("receptor_path", ""),
                "ligand": cx.get("ligand", ""),
                "ligand_format": cx.get("ligand_format", "smiles"),
                "samples_per_complex": cmd.config.get("samples_per_complex", 10),
                "inference_steps": cmd.config.get("inference_steps", 20),
                "device": cmd.config.get("device", "cpu"),
                "complex_index": i,
            }
            raw_output = adapter.execute(prepared_input)
            parsed = adapter.parse_output(raw_output)
            all_results.append(parsed)
            total_poses += len(parsed.get("poses", []))

        # 筛选摘要
        best_confidence = 0.0
        best_rank = 0
        best_pose_path = ""
        for result in all_results:
            for pose in result.get("poses", []):
                if pose.get("confidence", 0) > best_confidence:
                    best_confidence = pose.get("confidence", 0)
                    best_rank = pose.get("rank", 0)
                    best_pose_path = pose.get("sdf_path", "")

        result_artifact = Artifact(
            run_id=run.run_id,
            type=ArtifactType.RESULT_TABLE,
            name="batch_docking_results",
            description="批量虚拟筛选结果",
            content_type="application/json",
            data={
                "results": all_results,
                "total_complexes": len(cmd.complexes),
                "total_poses": total_poses,
                "summary": {
                    "best_confidence": best_confidence,
                    "best_rank": best_rank,
                    "best_pose_path": best_pose_path,
                    "total_complexes": len(cmd.complexes),
                    "total_poses": total_poses,
                },
            },
        )

        return [result_artifact]

    def _execute_analyze(self, run: Run) -> list[Artifact]:
        """执行对接结果分析。"""
        cmd = AnalyzeDocking(**run.input)
        # 占位分析逻辑
        return [
            Artifact(
                run_id=run.run_id,
                type=ArtifactType.REPORT,
                name="docking_analysis",
                description="对接结果分析报告",
                content_type="application/json",
                data={
                    "workdir": cmd.workdir,
                    "top_n": cmd.top_n,
                    "confidence_threshold": cmd.confidence_threshold,
                    "analysis": {
                        "total_poses_found": 0,
                        "filtered_poses": 0,
                        "top_poses": [],
                        "clusters": [],
                    },
                    "warnings": ["分析功能使用占位实现"],
                },
            )
        ]

    def _execute_export(self, run: Run) -> list[Artifact]:
        """执行对接结果导出。"""
        cmd = ExportDocking(**run.input)
        return [
            Artifact(
                run_id=run.run_id,
                type=ArtifactType.REPORT,
                name=f"docking_export.{cmd.format}",
                description=f"对接结果导出（{cmd.format} 格式）",
                content_type="application/json",
                data={
                    "workdir": cmd.workdir,
                    "format": cmd.format,
                    "export_path": f"{cmd.workdir}/export/docking_results.{cmd.format}",
                    "warnings": ["导出功能使用占位实现"],
                },
            )
        ]

    # ── 内部辅助 ───────────────────────────────────────────

    def _resolve_adapter(self) -> ExecutionAdapter | _PlaceholderAdapter:
        """解析执行适配器。

        优先级：
        1. 注入的适配器（用于测试）
        2. VinaAdapter（AutoDock Vina 真实对接，CPU，Apache 2.0）
        3. DockingAdapter（DiffDock 占位，向后兼容）
        4. _PlaceholderAdapter（最终兜底）
        """
        if self._adapter is not None:
            return self._adapter

        # 优先尝试 VinaAdapter（真实对接引擎）
        try:
            from ...infrastructure.executors.vina_adapter import VinaAdapter
            return VinaAdapter()
        except ImportError:
            pass

        # 回退到 DockingAdapter（占位实现，向后兼容）
        try:
            from ...infrastructure.executors.docking_adapter import DockingAdapter
            return DockingAdapter()
        except ImportError:
            pass

        return _PlaceholderAdapter()