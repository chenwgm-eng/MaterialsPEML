"""反应网络分析服务核心实现 — 基于 RDKit/xTB/PyGSM 的自动化反应网络发现。

基于 OpenReactNet 设计文档的 5 步工作流：
  标准化 → 反应枚举 → 化学规则筛选 → 构象采样 → TS 搜索
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
from .validators import ReactionNetworkValidator
from .evidence_mapper import batch_map_reaction_evidence


# ── 核心命令模型 ────────────────────────────────────────────


class EnumerateReactions(BaseModel):
    """反应枚举命令 — 枚举给定反应物可能的化学反应。"""

    project_id: str = Field(..., description="项目 ID")
    reactant_smiles: list[str] = Field(..., description="反应物 SMILES 列表")
    charge: int = Field(default=0, description="总电荷")
    multiplicity: int = Field(default=1, description="自旋多重度")
    max_break_bonds: int = Field(default=1, description="最多断键数")
    max_form_bonds: int = Field(default=1, description="最多成键数")
    max_candidates: int = Field(default=300, description="最大候选反应数")


class SearchTransitionState(BaseModel):
    """过渡态搜索命令 — 对给定反应搜索过渡态。"""

    project_id: str = Field(..., description="项目 ID")
    reaction_smiles: str = Field(..., description="反应 SMILES (Reactant>>Product)")
    charge: int = Field(default=0, description="总电荷")
    multiplicity: int = Field(default=1, description="自旋多重度")
    config: dict[str, Any] | None = Field(default=None, description="TS 搜索配置（可选）")


class GrowNetwork(BaseModel):
    """网络扩展命令 — 分层扩展反应网络。"""

    project_id: str = Field(..., description="项目 ID")
    reactants: list[str] = Field(..., description="初始反应物 SMILES 列表")
    max_layers: int = Field(default=3, description="最大扩展层数")
    max_species: int = Field(default=250, description="最大物种数")
    barrier_threshold: float = Field(default=40.0, description="能垒阈值 (kcal/mol)")


# ── 占位适配器 ──────────────────────────────────────────────


class _PlaceholderReactionAdapter:
    """反应网络分析占位适配器。

    当 ReactionAdapter（RDKit/xTB/PyGSM）不可用时，提供占位分析结果。
    实际部署时替换为完整的 ReactionAdapter。
    """

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        command = prepared_input.get("command", "enumerate")
        reactant_smiles = prepared_input.get("reactant_smiles", [])

        if command == "enumerate":
            return self._placeholder_enumerate(reactant_smiles)
        elif command == "ts_search":
            return self._placeholder_ts_search(prepared_input.get("reaction_smiles", ""))
        elif command == "grow_network":
            return self._placeholder_grow_network(reactant_smiles, prepared_input)
        return {"status": "unknown", "reactions": [], "warnings": ["未知命令"]}

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        return {"status": "unknown", "reactions": [], "warnings": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {"cpu": 2, "memory_mb": 1024, "walltime_minutes": 15}

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        return []

    def _placeholder_enumerate(self, reactant_smiles: list[str]) -> dict[str, Any]:
        reactions: list[dict[str, Any]] = []
        for smi in reactant_smiles:
            reactions.append({
                "reaction_smiles": f"{smi}>>{smi}_product",
                "evidence_stage": 0,
                "confidence": 0.5,
                "metadata": {"method": "placeholder", "warning": "ReactionAdapter 不可用，返回占位结果"},
            })
        return {
            "status": "completed",
            "reactions": reactions,
            "warnings": ["ReactionAdapter 不可用，使用占位枚举"],
        }

    def _placeholder_ts_search(self, reaction_smiles: str) -> dict[str, Any]:
        return {
            "status": "completed",
            "reaction_smiles": reaction_smiles,
            "ts_found": False,
            "barrier_kcal": None,
            "frequency": None,
            "degraded": True,
            "reactions": [
                {
                    "reaction_smiles": reaction_smiles,
                    "evidence_stage": 2,
                    "confidence": 0.8,
                    "metadata": {"method": "placeholder_ts", "ts_found": False},
                },
            ],
            "warnings": ["ReactionAdapter 不可用，使用占位 TS 搜索"],
        }

    def _placeholder_grow_network(self, reactants: list[str], params: dict[str, Any]) -> dict[str, Any]:
        max_layers = params.get("max_layers", 3)
        reactions: list[dict[str, Any]] = []
        species: set[str] = set(reactants)

        for layer in range(max_layers):
            for smi in list(species):
                reactions.append({
                    "reaction_smiles": f"{smi}>>{smi}_layer{layer + 1}",
                    "evidence_stage": 0,
                    "confidence": 0.5,
                    "metadata": {"layer": layer + 1, "source": smi},
                })
                species.add(f"{smi}_layer{layer + 1}")
                if len(species) >= params.get("max_species", 250):
                    break
            if len(species) >= params.get("max_species", 250):
                break

        return {
            "status": "completed",
            "reactions": reactions,
            "species": list(species),
            "layers_explored": min(max_layers, 3),
            "warnings": ["ReactionAdapter 不可用，使用占位网络生长"],
        }


# ── 服务实现 ────────────────────────────────────────────────


class ReactionNetworkApplication(NativeScientificService):
    """反应网络分析服务 (Reaction Network)。

    基于 RDKit/xTB/PyGSM 的自动化反应网络发现，支持：
    - 反应枚举：断键/成键组合枚举可能的化学反应
    - 过渡态搜索：使用 PyGSM 搜索反应过渡态
    - 分层网络扩展：逐层扩展反应网络
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
        return "reaction_network"

    @property
    def display_name(self) -> str:
        return "反应网络分析"

    @property
    def description(self) -> str:
        return "基于 RDKit/xTB/PyGSM 的自动化反应网络发现：反应枚举、过渡态搜索、分层网络扩展"

    # ── 生命周期 ───────────────────────────────────────────

    def validate(self, task: Task, context: dict[str, Any]) -> dict[str, Any]:
        """校验任务输入。"""
        metadata = task.metadata
        cmd_type = metadata.get("command", "enumerate")

        if cmd_type == "enumerate":
            cmd = EnumerateReactions(**metadata)
            validator = ReactionNetworkValidator(
                reactant_smiles=cmd.reactant_smiles,
                charge=cmd.charge,
                multiplicity=cmd.multiplicity,
                max_break_bonds=cmd.max_break_bonds,
                max_form_bonds=cmd.max_form_bonds,
                max_candidates=cmd.max_candidates,
            )
        elif cmd_type == "grow_network":
            cmd = GrowNetwork(**metadata)
            validator = ReactionNetworkValidator(
                reactant_smiles=cmd.reactants,
                max_layers=cmd.max_layers,
                max_species=cmd.max_species,
                max_barrier=cmd.barrier_threshold,
            )
        elif cmd_type == "ts_search":
            # TS 搜索：校验反应 SMILES 的 Reactant 和 Product 部分
            cmd = SearchTransitionState(**metadata)
            from .validators import validate_smiles, validate_elements
            rxn = cmd.reaction_smiles
            if ">>" not in rxn:
                return {"valid": False, "errors": [f"反应 SMILES 必须包含 '>>' 分隔符: '{rxn}'"]}
            reactant_part, product_part = rxn.split(">>", 1)
            if not reactant_part.strip():
                return {"valid": False, "errors": ["反应 SMILES 缺少反应物部分"]}
            if not product_part.strip():
                return {"valid": False, "errors": ["反应 SMILES 缺少产物部分"]}
            # 校验反应物和产物的 SMILES
            for label, part in [("反应物", reactant_part), ("产物", product_part)]:
                smi_result = validate_smiles(part)
                if not smi_result["valid"]:
                    return {"valid": False, "errors": [f"{label} SMILES 无效: '{part}'"]}
                elem_result = validate_elements(part)
                if not elem_result["valid"]:
                    return {"valid": False, "errors": [f"{label} {elem_result['errors'][0]}"]}
            return {"valid": True, "errors": []}
        else:
            return {"valid": False, "errors": [f"未知命令类型: {cmd_type}"]}

        return validator.validate_all()

    def prepare(self, task: Task) -> Run:
        """根据任务创建 Run 实例。"""
        metadata = task.metadata
        cmd_type = metadata.get("command", "enumerate")

        input_data: dict[str, Any] = {"command": cmd_type}

        if cmd_type == "enumerate":
            cmd = EnumerateReactions(**metadata)
            input_data.update({
                "reactant_smiles": cmd.reactant_smiles,
                "charge": cmd.charge,
                "multiplicity": cmd.multiplicity,
                "max_break_bonds": cmd.max_break_bonds,
                "max_form_bonds": cmd.max_form_bonds,
                "max_candidates": cmd.max_candidates,
            })
        elif cmd_type == "ts_search":
            cmd = SearchTransitionState(**metadata)
            input_data.update({
                "reaction_smiles": cmd.reaction_smiles,
                "charge": cmd.charge,
                "multiplicity": cmd.multiplicity,
                "config": cmd.config,
            })
        elif cmd_type == "grow_network":
            cmd = GrowNetwork(**metadata)
            input_data.update({
                "reactant_smiles": cmd.reactants,
                "max_layers": cmd.max_layers,
                "max_species": cmd.max_species,
                "barrier_threshold": cmd.barrier_threshold,
            })

        return Run(
            task_id=task.task_id,
            project_id=task.project_id,
            service_id=self.capability_id,
            command=f"reaction_network_{cmd_type}",
            input=input_data,
        )

    def execute(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行反应网络分析，返回 Artifact 列表。"""
        prepared_input = run.input

        # 解析执行适配器
        adapter = self._resolve_adapter()

        # 执行分析
        raw_output = adapter.execute(prepared_input)
        parsed = adapter.parse_output(raw_output)

        reactions = parsed.get("reactions", [])
        warnings = parsed.get("warnings", [])
        species = parsed.get("species")

        # 创建结果 Artifact
        result_artifact = Artifact(
            run_id=run.run_id,
            type=ArtifactType.RESULT_TABLE,
            name="reaction_network_results",
            description="反应网络分析结果",
            content_type="application/json",
            data={
                "reactions": reactions,
                "warnings": warnings,
                "species": species,
                "status": parsed.get("status"),
            },
        )

        artifacts: list[Artifact] = [result_artifact]

        # 如果是 TS 搜索，添加额外信息
        if parsed.get("ts_found") is not None:
            artifacts.append(
                Artifact(
                    run_id=run.run_id,
                    type=ArtifactType.PLOT,
                    name="transition_state_info",
                    description="过渡态搜索信息",
                    content_type="application/json",
                    data={
                        "ts_found": parsed.get("ts_found"),
                        "barrier_kcal": parsed.get("barrier_kcal"),
                        "frequency": parsed.get("frequency"),
                    },
                )
            )

        return artifacts

    def postprocess(self, run: Run, artifacts: list[Artifact]) -> list[EvidencePackage]:
        """后处理，将 Artifact 转换为 EvidencePackage 列表。"""
        reactions: list[dict[str, Any]] = []

        for art in artifacts:
            if art.data and "reactions" in art.data:
                reactions = art.data["reactions"]
                break

        if not reactions:
            return []

        # 为每个反应结果创建 EvidencePackage
        results_for_mapping: list[dict[str, Any]] = []
        for rxn in reactions:
            results_for_mapping.append({
                "reaction_smiles": rxn.get("reaction_smiles", ""),
                "evidence_stage": rxn.get("evidence_stage", 0),
                "confidence": rxn.get("confidence", 0.5),
                "metadata": rxn.get("metadata", {}),
            })

        return batch_map_reaction_evidence(
            run_id=run.run_id,
            task_id=run.task_id,
            results=results_for_mapping,
        )

    # ── 外部调用入口 ───────────────────────────────────────

    def enumerate_reactions(
        self,
        project_id: str,
        reactant_smiles: list[str],
        charge: int = 0,
        multiplicity: int = 1,
        max_break_bonds: int = 1,
        max_form_bonds: int = 1,
        max_candidates: int = 300,
    ) -> list[EvidencePackage]:
        """外部调用入口 — 反应枚举。

        Args:
            project_id: 项目 ID。
            reactant_smiles: 反应物 SMILES 列表。
            charge: 总电荷。
            multiplicity: 自旋多重度。
            max_break_bonds: 最多断键数。
            max_form_bonds: 最多成键数。
            max_candidates: 最大候选反应数。

        Returns:
            证据包列表。
        """
        cmd = EnumerateReactions(
            project_id=project_id,
            reactant_smiles=reactant_smiles,
            charge=charge,
            multiplicity=multiplicity,
            max_break_bonds=max_break_bonds,
            max_form_bonds=max_form_bonds,
            max_candidates=max_candidates,
        )

        task = Task(
            project_id=project_id,
            capability_id=self.capability_id,
            title="反应枚举",
            description=f"枚举 {len(reactant_smiles)} 个反应物的可能反应",
            metadata={"command": "enumerate", **cmd.model_dump()},
        )

        return self.run_full_cycle(task, {})

    def search_transition_state(
        self,
        project_id: str,
        reaction_smiles: str,
        charge: int = 0,
        multiplicity: int = 1,
        config: dict[str, Any] | None = None,
    ) -> list[EvidencePackage]:
        """外部调用入口 — 过渡态搜索。

        Args:
            project_id: 项目 ID。
            reaction_smiles: 反应 SMILES (Reactant>>Product)。
            charge: 总电荷。
            multiplicity: 自旋多重度。
            config: TS 搜索配置（可选）。

        Returns:
            证据包列表。
        """
        cmd = SearchTransitionState(
            project_id=project_id,
            reaction_smiles=reaction_smiles,
            charge=charge,
            multiplicity=multiplicity,
            config=config,
        )

        task = Task(
            project_id=project_id,
            capability_id=self.capability_id,
            title="过渡态搜索",
            description=f"搜索反应 {reaction_smiles} 的过渡态",
            metadata={"command": "ts_search", **cmd.model_dump()},
        )

        return self.run_full_cycle(task, {})

    def grow_network(
        self,
        project_id: str,
        reactants: list[str],
        max_layers: int = 3,
        max_species: int = 250,
        barrier_threshold: float = 40.0,
    ) -> list[EvidencePackage]:
        """外部调用入口 — 分层网络扩展。

        Args:
            project_id: 项目 ID。
            reactants: 初始反应物 SMILES 列表。
            max_layers: 最大扩展层数。
            max_species: 最大物种数。
            barrier_threshold: 能垒阈值 (kcal/mol)。

        Returns:
            证据包列表。
        """
        cmd = GrowNetwork(
            project_id=project_id,
            reactants=reactants,
            max_layers=max_layers,
            max_species=max_species,
            barrier_threshold=barrier_threshold,
        )

        task = Task(
            project_id=project_id,
            capability_id=self.capability_id,
            title="反应网络扩展",
            description=f"分层扩展反应网络，最大 {max_layers} 层，{max_species} 物种",
            metadata={"command": "grow_network", **cmd.model_dump()},
        )

        return self.run_full_cycle(task, {})

    # ── 内部辅助 ───────────────────────────────────────────

    def _resolve_adapter(self) -> ExecutionAdapter | _PlaceholderReactionAdapter:
        """解析执行适配器。

        优先使用注入的 ReactionAdapter，不可用时使用占位适配器。
        """
        if self._adapter is not None:
            return self._adapter

        try:
            from ...infrastructure.executors.reaction_adapter import ReactionAdapter
            return ReactionAdapter()
        except ImportError:
            return _PlaceholderReactionAdapter()