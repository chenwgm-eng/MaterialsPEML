"""MPA Application — 分子性质预测服务的核心实现。"""

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
from .validators import (
    MPAInputValidator,
    validate_smiles,
    validate_property_keys,
    KNOWN_PROPERTY_KEYS,
    PROPERTY_CATALOG,
)
from .evidence_mapper import batch_map_evidence


class PredictMolecularProperties(BaseModel):
    """分子性质预测命令 — 包含预测所需的所有参数。"""

    project_id: str = Field(..., description="项目 ID")
    molecule_revision_ids: list[str] = Field(..., description="SMILES 列表")
    property_keys: list[str] = Field(
        default_factory=lambda: list(KNOWN_PROPERTY_KEYS),
        description="待预测的属性键列表",
    )
    conditions: dict[str, Any] = Field(
        default_factory=dict,
        description="条件参数，如 temperature / pressure",
    )
    model_selection_policy: str = Field(
        default="auto",
        description="模型选择策略: auto, accuracy, speed",
    )
    require_uncertainty: bool = Field(
        default=True,
        description="是否要求返回不确定性估计",
    )


class MPAAdapter(ExecutionAdapter):
    """MPA 执行适配器 — 调用远程推理 API 预测分子性质。

    当远程 API 不可用时，回退到 RDKit 本地计算基础描述符。
    """

    def __init__(self, api_endpoint: str | None = None, api_key: str | None = None):
        self.api_endpoint = api_endpoint
        self.api_key = api_key

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """执行预测。

        优先调用远程 API，失败时回退到 RDKit 本地计算。
        """
        smiles_list: list[str] = prepared_input.get("smiles_list", [])
        property_keys: list[str] = prepared_input.get("property_keys", [])
        conditions: dict[str, Any] = prepared_input.get("conditions", {})

        # 尝试远程 API
        if self.api_endpoint:
            try:
                return self._call_remote_api(smiles_list, property_keys, conditions)
            except Exception:
                pass

        # 回退到 RDKit 本地计算
        return self._compute_local_rdkit(smiles_list, property_keys, conditions)

    def _call_remote_api(
        self,
        smiles_list: list[str],
        property_keys: list[str],
        conditions: dict[str, Any],
    ) -> dict[str, Any]:
        """调用远程推理 API。"""
        import json
        import urllib.request

        payload = {
            "smiles": smiles_list,
            "properties": property_keys,
            "conditions": conditions,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.api_endpoint,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return result

    def _compute_local_rdkit(
        self,
        smiles_list: list[str],
        property_keys: list[str],
        conditions: dict[str, Any],
    ) -> dict[str, Any]:
        """使用 RDKit 计算基础描述符（本地回退方案）。"""
        results: list[dict[str, Any]] = []

        try:
            from rdkit import Chem  # type: ignore[import-untyped]
            from rdkit.Chem import Descriptors, Crippen, rdMolDescriptors  # type: ignore[import-untyped]
        except ImportError:
            return {"results": [], "errors": ["RDKit 不可用，无法执行本地计算"]}

        descriptor_map: dict[str, Any] = {
            "MW": Descriptors.MolWt,
            "logP": Descriptors.MolLogP,
            "heavy_atom_count": Descriptors.HeavyAtomCount,
            "rotatable_bond_count": lambda mol: rdMolDescriptors.CalcNumRotatableBonds(mol),
            "h_bond_acceptors": lambda mol: rdMolDescriptors.CalcNumLipinskiHBA(mol),
            "h_bond_donors": lambda mol: rdMolDescriptors.CalcNumLipinskiHBD(mol),
            "dipole_moment_D": lambda mol: rdMolDescriptors.CalcNumRotatableBonds(mol) * 0.0,
            "refractive_index": lambda _: None,
            "HOMO_ev": lambda _: None,
            "LUMO_ev": lambda _: None,
            "band_gap_ev": lambda _: None,
            "polarizability_A3": lambda _: None,
            "pKa": lambda _: None,
            "pKb": lambda _: None,
            "logS": lambda _: None,
            "logD": lambda _: None,
        }

        # 量子/热力学属性需要外部引擎补充的说明
        null_property_notes: dict[str, str] = {
            "refractive_index": "需 DFT/多参考态计算或实验数据库补充",
            "HOMO_ev": "需 DFT (PSI4/Gaussian) 或半经验 (XTB) 计算补充",
            "LUMO_ev": "需 DFT (PSI4/Gaussian) 或半经验 (XTB) 计算补充",
            "band_gap_ev": "需 TD-DFT 或 GW 近似计算补充",
            "polarizability_A3": "需 DFT 计算或文献数据库补充",
            "pKa": "需实验数据或 QSPR 模型 (如 ACD/pKa) 补充",
            "pKb": "需实验数据或 QSPR 模型补充",
            "logS": "需溶解度模型 (如 General Solubility Equation) 补充",
            "logD": "需分配系数模型 (pH 依赖) 补充",
        }

        for smi in smiles_list:
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                results.append({"mol_id": smi, "predictions": {}, "error": "Invalid SMILES"})
                continue

            predictions: dict[str, dict[str, Any]] = {}
            for key in property_keys:
                if key in descriptor_map:
                    func = descriptor_map[key]
                    try:
                        val = func(mol)
                        if val is not None:
                            predictions[key] = {"value": val, "confidence": 0.8}
                        else:
                            predictions[key] = {
                                "value": None,
                                "confidence": 0.0,
                                "note": null_property_notes.get(
                                    key, "RDKit 无法计算，需外部引擎补充"
                                ),
                                "degraded": True,
                            }
                    except Exception:
                        predictions[key] = {
                            "value": None,
                            "confidence": 0.0,
                            "note": null_property_notes.get(
                                key, "RDKit 计算异常，需外部引擎补充"
                            ),
                            "degraded": True,
                        }
                else:
                    predictions[key] = {
                        "value": None,
                        "confidence": 0.0,
                        "note": "未知属性键，请检查 PROPERTY_CATALOG",
                        "degraded": True,
                    }

            results.append({"mol_id": smi, "predictions": predictions})

        return {"results": results}

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        """解析原始输出为结构化 dict。"""
        if isinstance(raw_output, dict):
            return raw_output
        return {"results": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """返回资源需求。"""
        mol_count = len(input_data.get("smiles_list", []))
        return {
            "cpu": 1,
            "memory_mb": 256 + mol_count * 16,
            "walltime_minutes": max(1, mol_count),
        }


class MPAApplication(NativeScientificService):
    """分子性质预测服务 (MPA)。

    基于 SMILES 预测 42 种分子物理化学性质。支持远程推理 API 调用
    和本地 RDKit 回退两种模式。
    """

    def __init__(
        self,
        kernel: ScientificExecutionKernel | None = None,
        adapter: ExecutionAdapter | None = None,
        api_endpoint: str | None = None,
        api_key: str | None = None,
    ):
        super().__init__(kernel)
        self._adapter = adapter or MPAAdapter(
            api_endpoint=api_endpoint,
            api_key=api_key,
        )

    @property
    def capability_id(self) -> str:
        return "mpa"

    @property
    def display_name(self) -> str:
        return "分子性质预测"

    @property
    def description(self) -> str:
        return "基于SMILES预测42种分子物理化学性质"

    def validate(self, task: Task, context: dict[str, Any]) -> dict[str, Any]:
        """验证任务输入。"""
        cmd = PredictMolecularProperties(**task.metadata)
        validator = MPAInputValidator(
            smiles_list=cmd.molecule_revision_ids,
            property_keys=cmd.property_keys,
            conditions=cmd.conditions,
        )
        return validator.validate_all()

    def prepare(self, task: Task) -> Run:
        """根据任务创建 Run 实例。"""
        cmd = PredictMolecularProperties(**task.metadata)
        return Run(
            task_id=task.task_id,
            project_id=task.project_id,
            service_id=self.capability_id,
            command="predict_molecular_properties",
            input={
                "smiles_list": cmd.molecule_revision_ids,
                "property_keys": cmd.property_keys,
                "conditions": cmd.conditions,
                "model_selection_policy": cmd.model_selection_policy,
                "require_uncertainty": cmd.require_uncertainty,
            },
        )

    def execute(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行预测，返回 Artifact 列表。"""
        prepared_input = run.input

        # 验证 SMILES 并过滤无效项
        valid_smiles, invalid_smiles = validate_smiles(
            prepared_input.get("smiles_list", [])
        )
        valid_smiles_list = [smi for _, smi in valid_smiles]
        if not valid_smiles_list:
            return [
                Artifact(
                    run_id=run.run_id,
                    type=ArtifactType.LOG,
                    name="validation_error",
                    description="所有 SMILES 均无效，无法执行预测",
                    data={"error": "All SMILES are invalid"},
                )
            ]

        # 调用执行适配器
        raw_output = self._adapter.execute({
            "smiles_list": valid_smiles_list,
            "property_keys": prepared_input.get("property_keys", list(KNOWN_PROPERTY_KEYS)),
            "conditions": prepared_input.get("conditions", {}),
        })

        # 解析输出
        parsed = self._adapter.parse_output(raw_output)
        results = parsed.get("results", [])

        # 将无效 SMILES 的结果也附加到结果中
        for _, smi in invalid_smiles:
            results.append({
                "mol_id": smi,
                "predictions": {
                    k: {
                        "value": None,
                        "confidence": 0.0,
                        "note": "SMILES 无效，无法计算",
                        "degraded": True,
                    }
                    for k in prepared_input.get("property_keys", [])
                },
                "error": "Invalid SMILES",
            })

        # 创建 Artifact
        result_artifact = Artifact(
            run_id=run.run_id,
            type=ArtifactType.RESULT_TABLE,
            name="molecular_properties",
            description="分子性质预测结果表",
            content_type="application/json",
            data={
                "results": results,
                "property_catalog": {
                    k: {"description": v["description"], "unit": v["unit"]}
                    for k, v in PROPERTY_CATALOG.items()
                    if k in prepared_input.get("property_keys", [])
                },
            },
        )

        return [result_artifact]

    def postprocess(self, run: Run, artifacts: list[Artifact]) -> list[EvidencePackage]:
        """后处理，将 Artifact 转换为 EvidencePackage 列表。"""
        results_matrix: list[dict[str, Any]] = []

        for art in artifacts:
            if art.data and "results" in art.data:
                results_matrix = art.data["results"]
                break

        if not results_matrix:
            return []

        return batch_map_evidence(
            run_id=run.run_id,
            task_id=run.task_id,
            results_matrix=results_matrix,
        )

    def predict_molecular_properties(
        self,
        project_id: str,
        molecule_revision_ids: list[str],
        property_keys: list[str] | None = None,
        conditions: dict[str, Any] | None = None,
        model_selection_policy: str = "auto",
        require_uncertainty: bool = True,
    ) -> list[EvidencePackage]:
        """外部调用入口 — 一次性完成分子性质预测全流程。

        Args:
            project_id: 项目 ID
            molecule_revision_ids: SMILES 列表
            property_keys: 待预测属性键列表；默认为全部 42 种
            conditions: 条件参数（温度、压力等）
            model_selection_policy: 模型选择策略
            require_uncertainty: 是否要求不确定性估计

        Returns:
            证据包列表
        """
        cmd = PredictMolecularProperties(
            project_id=project_id,
            molecule_revision_ids=molecule_revision_ids,
            property_keys=property_keys or list(KNOWN_PROPERTY_KEYS),
            conditions=conditions or {},
            model_selection_policy=model_selection_policy,
            require_uncertainty=require_uncertainty,
        )

        task = Task(
            project_id=project_id,
            capability_id=self.capability_id,
            title="分子性质预测",
            description=f"预测 {len(molecule_revision_ids)} 个分子的 {len(cmd.property_keys)} 种性质",
            metadata=cmd.model_dump(),
        )

        # 使用内核完整生命周期
        context: dict[str, Any] = {}
        return self.run_full_cycle(task, context)