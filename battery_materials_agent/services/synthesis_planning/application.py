"""合成路线规划服务核心实现 — 基于 ReactNavi 的逆合成分析。"""

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
from .validators import SynthesisInputValidator
from .evidence_mapper import (
    batch_map_routes,
    map_stats_evidence,
    map_normalization_evidence,
    map_error_evidence,
)


class PlanSynthesis(BaseModel):
    """逆合成分析请求模型 — 定义目标分子及搜索参数。"""

    project_id: str = Field(..., description="项目 ID")
    target_smiles: str = Field(..., description="目标分子 SMILES")
    search_depth: int = Field(default=3, description="逆合成树搜索深度")
    max_paths: int = Field(default=10, description="最大返回路线数")
    normalize_ions: bool = Field(default=True, description="是否将离子/盐归一化为中性母体")
    include_literature: bool = Field(default=True, description="是否包含文献/专利验证")
    expansion_timeout: int = Field(default=300, description="单次搜索超时时间（秒）")


class SynthesisPlanningApplication(NativeScientificService):
    """合成路线规划服务 (ReactNavi)。

    基于 Retrosynthesis API 进行逆合成分析，支持：
    - 目标分子离子/盐形式归一化
    - 多步逆合成树搜索（深度可配置）
    - 路线评判与证据分级（E0-E4）
    - 错误诊断与回退策略
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
        return "synthesis_planning"

    @property
    def display_name(self) -> str:
        return "合成路线规划"

    @property
    def description(self) -> str:
        return "基于ReactNavi的逆合成分析：目标分子归一化、多步逆合成树搜索、路线评判"

    # ── 生命周期方法 ───────────────────────────────────────

    def validate(self, task: Task, context: dict[str, Any]) -> dict[str, Any]:
        """验证任务输入。"""
        cmd = PlanSynthesis(**task.metadata)
        validator = SynthesisInputValidator(
            target_smiles=cmd.target_smiles,
            search_depth=cmd.search_depth,
            max_paths=cmd.max_paths,
            expansion_timeout=cmd.expansion_timeout,
            normalize_ions=cmd.normalize_ions,
            include_literature=cmd.include_literature,
        )
        return validator.validate_all()

    def prepare(self, task: Task) -> Run:
        """根据任务创建 Run 实例。"""
        cmd = PlanSynthesis(**task.metadata)
        return Run(
            task_id=task.task_id,
            project_id=task.project_id,
            service_id=self.capability_id,
            command="plan_synthesis",
            input={
                "target_smiles": cmd.target_smiles,
                "search_depth": cmd.search_depth,
                "max_paths": cmd.max_paths,
                "normalize_ions": cmd.normalize_ions,
                "include_literature": cmd.include_literature,
                "expansion_timeout": cmd.expansion_timeout,
            },
        )

    def execute(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行逆合成分析，返回 Artifact 列表。

        通过 SynthesisAdapter 调用 Retrosynthesis API：
        1. 目标分子归一化（离子/盐 → 中性母体）
        2. 调用 call_retrosynthesis API
        3. 路线解析与错误诊断
        """
        prepared_input = run.input

        # 解析输入
        target_smiles: str = prepared_input.get("target_smiles", "")
        search_depth: int = prepared_input.get("search_depth", 3)
        max_paths: int = prepared_input.get("max_paths", 10)
        normalize_ions: bool = prepared_input.get("normalize_ions", True)
        expansion_timeout: int = prepared_input.get("expansion_timeout", 300)

        # 获取适配器（优先使用注入的适配器，否则创建默认的）
        adapter = self._resolve_adapter()

        # 构建适配器输入
        adapter_input: dict[str, Any] = {
            "target_smiles": target_smiles,
            "search_depth": search_depth,
            "max_paths": max_paths,
            "normalize_ions": normalize_ions,
            "expansion_timeout": expansion_timeout,
        }

        # 执行适配器
        raw_output = adapter.execute(adapter_input)
        parsed = adapter.parse_output(raw_output)

        # 构建 Artifact 列表
        artifacts: list[Artifact] = []

        # 归一化信息
        if parsed.get("normalized_smiles") and parsed["normalized_smiles"] != target_smiles:
            artifacts.append(
                Artifact(
                    run_id=run.run_id,
                    type=ArtifactType.LOG,
                    name="normalization",
                    description="目标分子归一化信息",
                    data={
                        "original_smiles": target_smiles,
                        "normalized_smiles": parsed["normalized_smiles"],
                    },
                )
            )

        # 搜索统计
        stats = parsed.get("stats", {})
        artifacts.append(
            Artifact(
                run_id=run.run_id,
                type=ArtifactType.RESULT_TABLE,
                name="search_stats",
                description="逆合成搜索统计",
                data=stats,
            )
        )

        # 路线结果
        routes = parsed.get("routes", [])
        if routes:
            artifacts.append(
                Artifact(
                    run_id=run.run_id,
                    type=ArtifactType.RESULT_TABLE,
                    name="synthesis_routes",
                    description=f"逆合成路线结果（共 {len(routes)} 条）",
                    data={"routes": routes},
                )
            )

        # 诊断信息（错误或警告）
        diagnostics = parsed.get("diagnostics")
        if diagnostics:
            artifacts.append(
                Artifact(
                    run_id=run.run_id,
                    type=ArtifactType.LOG,
                    name="diagnostics",
                    description="逆合成搜索诊断信息",
                    data=diagnostics,
                )
            )

        return artifacts

    def postprocess(self, run: Run, artifacts: list[Artifact]) -> list[EvidencePackage]:
        """后处理，将 Artifact 转换为 EvidencePackage 列表。"""
        evidence_list: list[EvidencePackage] = []

        # 暂存解析结果
        stats: dict[str, Any] = {}
        routes: list[dict[str, Any]] = []
        normalized_smiles: str | None = None
        original_smiles: str | None = None
        diagnostics: dict[str, Any] | None = None

        for art in artifacts:
            data = art.data or {}

            if art.name == "normalization":
                original_smiles = data.get("original_smiles")
                normalized_smiles = data.get("normalized_smiles")

            elif art.name == "search_stats":
                stats = data

            elif art.name == "synthesis_routes":
                routes = data.get("routes", [])

            elif art.name == "diagnostics":
                diagnostics = data

        # 1. 归一化证据
        if original_smiles and normalized_smiles and original_smiles != normalized_smiles:
            evidence_list.append(
                map_normalization_evidence(
                    run_id=run.run_id,
                    task_id=run.task_id,
                    original_smiles=original_smiles,
                    normalized_smiles=normalized_smiles,
                )
            )

        # 2. 搜索统计证据
        if stats:
            evidence_list.append(
                map_stats_evidence(
                    run_id=run.run_id,
                    task_id=run.task_id,
                    stats=stats,
                )
            )

        # 3. 路线证据
        if routes:
            evidence_list.extend(
                batch_map_routes(
                    run_id=run.run_id,
                    task_id=run.task_id,
                    routes=routes,
                )
            )

        # 4. 错误诊断证据
        if diagnostics:
            error_type = diagnostics.get("error_type", "unknown")
            error_message = diagnostics.get("error_message", "未知诊断信息")
            evidence_list.append(
                map_error_evidence(
                    run_id=run.run_id,
                    task_id=run.task_id,
                    error_type=error_type,
                    error_message=error_message,
                    diagnostics=diagnostics,
                )
            )

        return evidence_list

    # ── 外部调用入口 ───────────────────────────────────────

    def plan_synthesis(
        self,
        project_id: str,
        target_smiles: str,
        search_depth: int = 3,
        max_paths: int = 10,
        normalize_ions: bool = True,
        include_literature: bool = True,
        expansion_timeout: int = 300,
    ) -> list[EvidencePackage]:
        """外部调用入口 — 一次性完成逆合成分析全流程。

        Args:
            project_id: 项目 ID。
            target_smiles: 目标分子 SMILES。
            search_depth: 搜索深度（默认 3）。
            max_paths: 最大返回路线数（默认 10）。
            normalize_ions: 是否归一化离子/盐（默认 True）。
            include_literature: 是否包含文献验证（默认 True）。
            expansion_timeout: 搜索超时秒数（默认 300）。

        Returns:
            证据包列表。
        """
        cmd = PlanSynthesis(
            project_id=project_id,
            target_smiles=target_smiles,
            search_depth=search_depth,
            max_paths=max_paths,
            normalize_ions=normalize_ions,
            include_literature=include_literature,
            expansion_timeout=expansion_timeout,
        )

        task = Task(
            project_id=project_id,
            capability_id=self.capability_id,
            title="合成路线规划",
            description=f"ReactNavi 逆合成分析: {target_smiles}",
            metadata=cmd.model_dump(),
        )

        context: dict[str, Any] = {}
        return self.run_full_cycle(task, context)

    # ── 内部辅助 ───────────────────────────────────────────

    def _resolve_adapter(self) -> ExecutionAdapter:
        """解析执行适配器。

        优先使用注入的适配器，否则创建默认的 SynthesisAdapter。
        """
        if self._adapter is not None:
            return self._adapter

        # 延迟导入，避免循环依赖
        from ...infrastructure.executors.synthesis_adapter import SynthesisAdapter  # type: ignore[import-untyped]  # noqa: E501

        self._adapter = SynthesisAdapter()
        return self._adapter