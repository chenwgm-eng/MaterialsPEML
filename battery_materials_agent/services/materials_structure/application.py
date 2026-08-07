"""材料结构生成与优化服务 — 分子/晶体结构生成、格式转换和几何优化。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ...contracts.task import Task
from ...contracts.run import Run, RunStatus
from ...contracts.artifact import Artifact, ArtifactType
from ...contracts.evidence import EvidencePackage, build_source_fields
from ...domain.runtime import ScientificExecutionKernel
from ...infrastructure.executors.structure_adapter import StructureAdapter
from ..base_service import NativeScientificService
from .validators import StructureValidator
from .evidence_mapper import map_structure_evidence

# ── 请求模型 ────────────────────────────────────────────────


class GenerateStructure(BaseModel):
    """结构生成请求模型。"""

    project_id: str
    input_format: str = Field(description="输入格式: smiles, formula, cif, xyz")
    input_data: str = Field(description="输入数据字符串")
    output_formats: list[str] = Field(
        default=["smiles", "xyz", "cif", "mol"],
        description="请求的输出格式列表",
    )
    optimization_level: str = Field(
        default="none",
        description="优化级别: none, basic, full",
    )
    force_field: str | None = Field(
        default=None,
        description="力场类型: uff, mmff94 等",
    )


class OptimizeStructure(BaseModel):
    """结构优化请求模型。"""

    project_id: str
    structure_data: str = Field(description="待优化的结构数据")
    format: str = Field(description="输入格式")
    optimization_level: str = Field(description="优化级别: basic, full")
    max_iterations: int = Field(default=500, description="最大迭代次数")


# ── 服务实现 ────────────────────────────────────────────────

_SUPPORTED_OPTIMIZATION_LEVELS: frozenset[str] = frozenset({"none", "basic", "full"})
_SUPPORTED_FORCE_FIELDS: frozenset[str | None] = frozenset({None, "uff", "mmff94"})


class StructureApplication(NativeScientificService):
    """材料结构生成与优化服务。

    提供分子/晶体结构生成、格式转换和几何优化功能。
    作为 ``materials_structure`` 能力域的统一入口。
    """

    def __init__(self, kernel: ScientificExecutionKernel | None = None) -> None:
        super().__init__(kernel)
        # 延迟初始化真实适配器，避免在不可用时阻塞
        self._adapter_instance: StructureAdapter | None = None
        self._adapter_init_failed = False

    @property
    def capability_id(self) -> str:
        return "materials_structure"

    @property
    def display_name(self) -> str:
        return "材料结构生成与优化"

    @property
    def description(self) -> str:
        return "分子/晶体结构生成、格式转换和几何优化"

    # ── 生命周期 ───────────────────────────────────────────

    def validate(self, task: Task, context: dict[str, Any]) -> dict[str, Any]:
        """校验任务输入，返回校验结果。

        Returns:
            dict: 包含 ``errors`` 和 ``warnings`` 两个列表。
        """
        errors: list[str] = []
        warnings: list[str] = []

        operation = task.metadata.get("operation", "generate")
        input_data = task.metadata.get("input_data", "")
        input_format = task.metadata.get("input_format", "")

        if not input_data:
            errors.append("input_data 不能为空")
        if not input_format:
            errors.append("input_format 不能为空")

        if input_format and input_data:
            result = StructureValidator.validate(input_format, input_data)
            errors.extend(result["errors"])
            warnings.extend(result["warnings"])

        if operation == "generate":
            opt_level = task.metadata.get("optimization_level", "none")
            if opt_level not in _SUPPORTED_OPTIMIZATION_LEVELS:
                errors.append(
                    f"不支持的优化级别 '{opt_level}'。支持: {', '.join(sorted(_SUPPORTED_OPTIMIZATION_LEVELS))}"
                )
            force_field = task.metadata.get("force_field")
            if force_field is not None and force_field not in _SUPPORTED_FORCE_FIELDS:
                errors.append(f"不支持的力场 '{force_field}'。支持: uff, mmff94")

        elif operation == "optimize":
            max_iter = task.metadata.get("max_iterations", 500)
            if not isinstance(max_iter, int) or max_iter < 1:
                errors.append("max_iterations 必须为正整数")

        if not errors:
            output_formats = task.metadata.get("output_formats", [])
            if isinstance(output_formats, list):
                for fmt in output_formats:
                    try:
                        from .validators import validate_input_format
                        validate_input_format(fmt)
                    except ValueError as exc:
                        errors.append(str(exc))

        return {"errors": errors, "warnings": warnings}

    def prepare(self, task: Task) -> Run:
        """根据任务创建一次 Run 实例。"""
        return Run(
            task_id=task.task_id,
            project_id=task.project_id,
            service_id=self.capability_id,
            command=task.metadata.get("operation", "generate"),
            input={
                "input_format": task.metadata.get("input_format", ""),
                "input_data": task.metadata.get("input_data", ""),
                "output_formats": task.metadata.get("output_formats", []),
                "optimization_level": task.metadata.get("optimization_level", "none"),
                "force_field": task.metadata.get("force_field"),
                "max_iterations": task.metadata.get("max_iterations", 500),
            },
        )

    def execute(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行结构生成或优化，返回工件列表。

        通过 StructureAdapter 委托给 RDKit / OpenBabel 等第三方库。
        """
        operation = run.command
        input_data = run.input.get("input_data", "")
        input_format = run.input.get("input_format", "")
        output_formats: list[str] = run.input.get("output_formats", [])
        optimization_level = run.input.get("optimization_level", "none")
        force_field = run.input.get("force_field")
        max_iterations = run.input.get("max_iterations", 500)

        # 解析真实适配器
        adapter = self._resolve_adapter(operation)

        # ── 将应用层输入映射为 StructureAdapter 期望的字段 ──
        if operation == "generate":
            # generate: StructureAdapter 期望 smiles / num_conformers / optimize / output_format
            adapter_input: dict[str, Any] = {
                "operation": "generate",
                "smiles": input_data,
                "num_conformers": 1,
                "optimize": optimization_level in ("basic", "full"),
                "output_format": output_formats[0] if output_formats else "pdb",
            }
        elif operation == "optimize":
            # optimize: StructureAdapter 期望 input_format / input_data / method / max_iterations
            method = "mmff" if (force_field in (None, "mmff94")) else "uff"
            adapter_input = {
                "operation": "optimize",
                "input_format": input_format or "smi",
                "input_data": input_data,
                "method": method,
                "max_iterations": max_iterations,
            }
        else:
            # convert / validate
            adapter_input = {
                "operation": operation,
                "input_format": input_format,
                "input_data": input_data,
            }
            if output_formats:
                adapter_input["output_format"] = output_formats[0]

        raw_output = adapter.execute(adapter_input)
        parsed = adapter.parse_output(raw_output)

        # ── 将适配器输出映射回应用层统一结构 ──
        structures: list[dict[str, Any]] = []
        if "error" in parsed:
            # 适配器报错，保留错误信息作为结果工件
            return [
                Artifact(
                    run_id=run.run_id,
                    type=ArtifactType.RESULT_TABLE,
                    name="structure_error",
                    description="结构操作失败",
                    data=parsed,
                )
            ]

        if "structure" in parsed:
            # 单结构输出（generate/optimize/convert）
            fmt = parsed.get("format", output_formats[0] if output_formats else "smiles")
            structures.append({
                "structure_id": f"{operation}_result",
                "format": fmt,
                "data": parsed["structure"],
                "metadata": {
                    k: v for k, v in parsed.items()
                    if k not in ("structure", "format") and v is not None
                },
            })

        # 构建 Artifact
        artifacts: list[Artifact] = []
        for idx, struct in enumerate(structures):
            fmt = struct.get("format", "unknown")
            data_str = struct.get("data", "")
            # 占位数据使用 text/plain，避免 MIME 与内容不符
            is_placeholder = isinstance(data_str, str) and data_str.startswith("# placeholder")
            if is_placeholder:
                content_type = "text/plain"
                struct["degraded"] = True
                struct["note"] = "StructureAdapter 不可用，返回占位数据；需接入 RDKit/pymatgen 获得真实结构"
            else:
                content_type = self._content_type_for_format(fmt)
            artifact = Artifact(
                run_id=run.run_id,
                type=ArtifactType.STRUCTURE,
                name=f"structure_{idx + 1}",
                description=f"结构 {idx + 1}（格式: {fmt}）",
                content_type=content_type,
                data=struct,
            )
            artifacts.append(artifact)

        # 如果没有结构产出，创建一个包含原始结果的工件
        if not artifacts:
            artifacts.append(
                Artifact(
                    run_id=run.run_id,
                    type=ArtifactType.RESULT_TABLE,
                    name="structure_result",
                    description="结构操作结果",
                    data=parsed,
                )
            )

        return artifacts

    @staticmethod
    def _content_type_for_format(fmt: str) -> str:
        """根据结构格式返回 MIME 类型。"""
        mapping = {
            "smiles": "chemical/x-smiles",
            "smi": "chemical/x-smiles",
            "mol": "chemical/x-mdl-molfile",
            "molblock": "chemical/x-mdl-molfile",
            "pdb": "chemical/x-pdb",
            "xyz": "chemical/x-xyz",
            "cif": "chemical/x-cif",
        }
        return mapping.get(fmt.lower(), "application/octet-stream")

    def postprocess(self, run: Run, artifacts: list[Artifact]) -> list[EvidencePackage]:
        """将工件转换为 EvidencePackage 列表。"""
        evidence_list: list[EvidencePackage] = []

        for art in artifacts:
            if art.type == ArtifactType.STRUCTURE and art.data:
                struct_id = art.data.get("structure_id", art.name)
                fmt = art.data.get("format", "unknown")
                data_str = art.data.get("data", "")
                evidence = map_structure_evidence(
                    run_id=run.run_id,
                    task_id=run.task_id,
                    structure_id=struct_id,
                    fmt=fmt,
                    data=data_str,
                    method=run.command,
                )
                evidence_list.append(evidence)
            elif art.data:
                # 对非结构工件，生成摘要证据
                sf = build_source_fields("materials_structure")
                evidence_list.append(
                    EvidencePackage(
                        run_id=run.run_id,
                        task_id=run.task_id,
                        claim=f"结构操作完成: {art.name}",
                        value=art.data,
                        method=run.command,
                        source_type=sf["source_type"],
                        source_service=sf["source_service"],
                        metadata=sf["metadata_patch"],
                    )
                )

        return evidence_list

    # ── 内部辅助 ───────────────────────────────────────────

    def _resolve_adapter(self, operation: str) -> Any:
        """解析操作对应的执行适配器。

        优先使用基于 RDKit 的真实 StructureAdapter；
        初始化失败时回退到占位适配器以保证服务可用性。
        """
        if self._adapter_instance is not None:
            return self._adapter_instance
        if self._adapter_init_failed:
            return _PlaceholderAdapter()
        try:
            self._adapter_instance = StructureAdapter()
            return self._adapter_instance
        except Exception:
            self._adapter_init_failed = True
            return _PlaceholderAdapter()


class _PlaceholderAdapter:
    """占位适配器 — StructureAdapter 不可用时的回退实现。"""

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        operation = prepared_input.get("operation", "generate")
        input_format = prepared_input.get("input_format", "")
        input_data = prepared_input.get("input_data", "")
        output_formats: list[str] = prepared_input.get("output_formats", [])

        structures: list[dict[str, Any]] = []
        for fmt in output_formats:
            structures.append({
                "structure_id": f"{operation}_{fmt}",
                "format": fmt,
                "data": f"# placeholder {fmt} data for: {input_data[:50]}",
            })

        return {"structures": structures}

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        return {"structures": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {"cpu": 1, "memory_mb": 512, "walltime_minutes": 5}

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        return []