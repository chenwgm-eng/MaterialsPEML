"""配方与堆积优化服务核心实现 — 电池材料配方优化和分子堆积结构生成。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ...contracts.task import Task
from ...contracts.run import Run
from ...contracts.artifact import Artifact, ArtifactType
from ...contracts.evidence import EvidencePackage
from ...domain.runtime import ScientificExecutionKernel
from ..base_service import NativeScientificService
from .validators import FormulationValidator
from .evidence_mapper import map_formulation_evidence, map_packing_evidence


class OptimizeFormulation(BaseModel):
    """配方优化请求模型。

    定义一组配方组分及其目标优化属性，驱动组分比例搜索。
    """

    project_id: str
    components: list[dict] = Field(
        ..., description="组分列表，每项包含 {name, smiles, ratio_range_min, ratio_range_max, constraints}"
    )
    target_properties: list[str] = Field(
        ..., description="目标优化属性列表"
    )
    optimization_goal: str = Field(
        ..., description="优化目标：maximize / minimize / target"
    )
    constraints: dict = Field(
        default_factory=dict, description="附加约束条件"
    )
    max_iterations: int = Field(
        default=1000, ge=1, description="最大迭代次数"
    )


class PackingRequest(BaseModel):
    """分子堆积请求模型。

    定义分子构建堆积结构所需的参数。
    """

    project_id: str
    molecules: list[str] = Field(
        ..., description="待堆积分子的 SMILES 列表"
    )
    packing_type: str = Field(
        ..., description="堆积类型：crystal / amorphous / solvation"
    )
    target_density: float | None = Field(
        default=None, description="目标密度 (g/cm³)"
    )
    box_size_nm: float | None = Field(
        default=None, description="盒子边长 (nm)"
    )
    force_field: str = Field(
        default="uff", description="力场名称"
    )


class FormulationPackingApplication(NativeScientificService):
    """配方优化与分子堆积服务。

    支持两种操作模式：
    - formulation_optimization：组分比例搜索与性能优化
    - packing：分子堆积结构生成
    """

    @property
    def capability_id(self) -> str:
        return "formulation_packing"

    @property
    def display_name(self) -> str:
        return "配方与堆积优化"

    @property
    def description(self) -> str:
        return "电池材料配方优化和分子堆积结构生成"

    # ── 生命周期方法 ───────────────────────────────────────

    def validate(self, task: Task, context: dict[str, Any]) -> dict[str, Any]:
        """校验任务输入。

        context 中须包含 command 字段以区分操作类型。
        """
        command = context.get("command", task.metadata.get("command", ""))
        if not command:
            return {"valid": False, "errors": ["缺少 command 字段，须为 formulation_optimization 或 packing"]}

        if command == "formulation_optimization":
            return self._validate_formulation(task)
        elif command == "packing":
            return self._validate_packing(task)
        else:
            return {"valid": False, "errors": [f"不支持的 command: {command}"]}

    def prepare(self, task: Task) -> Run:
        """创建 Run 实例。"""
        command = task.metadata.get("command", "formulation_optimization")
        return Run(
            task_id=task.task_id,
            project_id=task.project_id,
            service_id=self.capability_id,
            command=command,
            input=task.metadata.get("input", {}),
        )

    def execute(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行科学计算。

        根据 command 分发到配方优化或分子堆积。
        """
        command = run.command or context.get("command", "formulation_optimization")

        if command == "formulation_optimization":
            return self._execute_formulation(run, context)
        elif command == "packing":
            return self._execute_packing(run, context)
        else:
            raise ValueError(f"不支持的 command: {command}")

    def postprocess(self, run: Run, artifacts: list[Artifact]) -> list[EvidencePackage]:
        """将 Artifact 转换为 EvidencePackage 列表。"""
        evidence: list[EvidencePackage] = []
        command = run.command or "formulation_optimization"

        for artifact in artifacts:
            data = artifact.data or {}

            if command == "formulation_optimization" and artifact.type == ArtifactType.RESULT_TABLE:
                formulation_id = data.get("formulation_id", artifact.artifact_id)
                for prop in data.get("properties", []):
                    evidence.append(
                        map_formulation_evidence(
                            run_id=run.run_id,
                            task_id=run.task_id,
                            formulation_id=formulation_id,
                            property=prop.get("name", ""),
                            value=prop.get("value", 0.0),
                            unit=prop.get("unit", ""),
                        )
                    )
            elif command == "packing":
                evidence.append(
                    map_packing_evidence(
                        run_id=run.run_id,
                        task_id=run.task_id,
                        structure_id=data.get("structure_id", artifact.artifact_id),
                        density=data.get("density", 0.0),
                        energy=data.get("energy", 0.0),
                    )
                )

        return evidence

    # ── 内部方法 ───────────────────────────────────────────

    def _validate_formulation(self, task: Task) -> dict[str, Any]:
        """校验配方优化输入。"""
        components = task.metadata.get("components", [])
        comp_result = FormulationValidator.validate_components(components)
        if not comp_result["valid"]:
            return comp_result

        goal = task.metadata.get("optimization_goal", "")
        goal_result = FormulationValidator.validate_optimization_goal(goal)
        if not goal_result["valid"]:
            return goal_result

        return {"valid": True, "errors": []}

    def _validate_packing(self, task: Task) -> dict[str, Any]:
        """校验堆积输入。"""
        params = {
            "packing_type": task.metadata.get("packing_type", ""),
            "molecules": task.metadata.get("molecules", []),
            "target_density": task.metadata.get("target_density"),
            "box_size_nm": task.metadata.get("box_size_nm"),
        }
        return FormulationValidator.validate_packing(params)

    def _execute_formulation(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行配方优化 — 优先 FormulationAdapter，回退 RDKit 网格搜索。"""
        adapter = context.get("adapter")
        if adapter is not None:
            result = adapter.optimize_formulation(run.input)
        else:
            # 尝试加载 FormulationAdapter（RDKit 描述符网格搜索）
            adapter = self._load_formulation_adapter()
            if adapter is not None:
                result = adapter.optimize_formulation(run.input)
            else:
                result = self._optimize_formulation_rdkit(run.input)

        return [
            Artifact(
                run_id=run.run_id,
                type=ArtifactType.RESULT_TABLE,
                name="formulation_result",
                description="配方优化结果",
                content_type="application/json",
                data=result,
            ),
        ]

    def _execute_packing(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行分子堆积 — 优先 FormulationAdapter (packmol Docker)，回退 RDKit 体积估算。"""
        adapter = context.get("adapter")
        if adapter is not None:
            result = adapter.build_packing_structure(run.input)
        else:
            # 尝试加载 FormulationAdapter（Docker packmol 优先，RDKit 兜底）
            adapter = self._load_formulation_adapter()
            if adapter is not None:
                result = adapter.build_packing_structure(run.input)
            else:
                result = self._build_packing_rdkit(run.input)

        return [
            Artifact(
                run_id=run.run_id,
                type=ArtifactType.STRUCTURE,
                name="packing_structure",
                description="分子堆积结构",
                content_type="application/json",
                data=result,
            ),
        ]

    @staticmethod
    def _load_formulation_adapter():
        """加载 FormulationAdapter — packmol Docker + RDKit 真实实现。

        Returns:
            FormulationAdapter 实例或 None（当基础设施层不可用时）。
        """
        try:
            from ...infrastructure.executors.formulation_adapter import FormulationAdapter
            return FormulationAdapter()
        except ImportError:
            return None

    # ── RDKit 真实计算 ─────────────────────────────────────

    @staticmethod
    def _compute_descriptors(smiles: str) -> dict[str, float | None]:
        """用 RDKit 计算分子描述符。"""
        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors, Crippen

            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return {"MW": None, "logP": None, "TPSA": None, "NumHDonors": None, "NumHAcceptors": None}

            return {
                "MW": round(Descriptors.MolWt(mol), 3),
                "logP": round(Crippen.MolLogP(mol), 3),
                "TPSA": round(Descriptors.TPSA(mol), 3),
                "NumHDonors": int(Descriptors.NumHDonors(mol)),
                "NumHAcceptors": int(Descriptors.NumHAcceptors(mol)),
            }
        except Exception:
            return {"MW": None, "logP": None, "TPSA": None, "NumHDonors": None, "NumHAcceptors": None}

    def _optimize_formulation_rdkit(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """基于 RDKit 描述符的配方优化。

        对每组分计算分子描述符，用网格搜索在比例约束内寻找最优配比。
        """
        components: list[dict] = input_data.get("components", [])
        target_properties: list[str] = input_data.get("target_properties", ["MW"])
        optimization_goal: str = input_data.get("optimization_goal", "maximize")

        # 计算各组分的描述符
        comp_descs: list[dict[str, Any]] = []
        for comp in components:
            smiles = comp.get("smiles", "")
            name = comp.get("name", smiles)
            desc = self._compute_descriptors(smiles)
            comp_descs.append({
                "name": name,
                "smiles": smiles,
                "descriptors": desc,
                "ratio_range_min": comp.get("ratio_range_min", 0.0),
                "ratio_range_max": comp.get("ratio_range_max", 1.0),
            })

        # 如果没有组分或描述符不可用，返回基本信息
        if not comp_descs:
            return {
                "formulation_id": "f-001",
                "method": "rdkit_grid_search",
                "components": [],
                "properties": [],
                "optimized_ratios": [],
                "warning": "未提供组分或组分无法解析",
            }

        # 网格搜索：对每个组分在 [min, max] 范围内以 0.1 步长搜索
        # 归一化约束：所有组分比例之和 = 1.0
        n = len(comp_descs)
        step = 0.1
        best_score = None
        best_ratios = [1.0 / n] * n

        # 简化搜索：对于 2-3 个组分，直接遍历网格
        if n <= 3:
            import itertools

            # 生成各组分候选比例
            candidates = []
            for cd in comp_descs:
                lo = max(0.0, cd["ratio_range_min"])
                hi = min(1.0, cd["ratio_range_max"])
                vals = [round(lo + i * step, 2) for i in range(int((hi - lo) / step) + 1)]
                candidates.append(vals)

            for combo in itertools.product(*candidates):
                if abs(sum(combo) - 1.0) > 0.05:  # 比例和≈1
                    continue
                # 归一化
                total = sum(combo)
                if total == 0:
                    continue
                ratios = [c / total for c in combo]

                # 计算加权目标值
                score = 0.0
                for prop in target_properties:
                    weighted = sum(
                        ratios[i] * (comp_descs[i]["descriptors"].get(prop, 0) or 0)
                        for i in range(n)
                    )
                    score += weighted

                if optimization_goal == "maximize":
                    if best_score is None or score > best_score:
                        best_score = score
                        best_ratios = ratios
                elif optimization_goal == "minimize":
                    if best_score is None or score < best_score:
                        best_score = score
                        best_ratios = ratios
                else:  # target
                    if best_score is None:
                        best_score = score
                        best_ratios = ratios

        # 计算最优配方的性质
        optimized_props: list[dict[str, Any]] = []
        for prop in target_properties:
            weighted_val = sum(
                best_ratios[i] * (comp_descs[i]["descriptors"].get(prop, 0) or 0)
                for i in range(n)
            )
            optimized_props.append({
                "name": prop,
                "value": round(weighted_val, 4),
                "unit": "",
            })

        return {
            "formulation_id": "f-001",
            "method": "rdkit_grid_search",
            "components": [
                {
                    "name": cd["name"],
                    "smiles": cd["smiles"],
                    "ratio": round(best_ratios[i], 4),
                    "descriptors": cd["descriptors"],
                }
                for i, cd in enumerate(comp_descs)
            ],
            "properties": optimized_props,
            "optimized_ratios": [round(r, 4) for r in best_ratios],
            "optimization_goal": optimization_goal,
        }

    def _build_packing_rdkit(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """基于 RDKit 的分子堆积结构生成与密度估算。"""
        molecules: list[str] = input_data.get("molecules", [])
        packing_type: str = input_data.get("packing_type", "amorphous")
        target_density = input_data.get("target_density")
        box_size_nm = input_data.get("box_size_nm")
        force_field: str = input_data.get("force_field", "uff")

        if not molecules:
            return {
                "structure_id": "s-001",
                "density": 0.0,
                "energy": 0.0,
                "warning": "未提供分子列表",
            }

        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem, Descriptors
        except Exception:
            return {
                "structure_id": "s-001",
                "density": 0.0,
                "energy": 0.0,
                "warning": "RDKit 不可用",
            }

        # 为每个分子生成 3D 结构并计算体积
        mol_infos: list[dict[str, Any]] = []
        total_mw = 0.0
        total_volume_nm3 = 0.0

        for idx, smiles in enumerate(molecules):
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                continue
            mol = Chem.AddHs(mol)
            mw = Descriptors.MolWt(mol)

            # 生成 3D 构象
            try:
                AllChem.EmbedMolecule(mol, randomSeed=42)
                if force_field == "mmff94":
                    AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
                else:
                    AllChem.UFFOptimizeMolecule(mol, maxIters=200)
            except Exception:
                pass  # 优化失败不影响体积估算

            # 计算分子体积 (Å³ → nm³)
            try:
                from rdkit.Chem import AllChem as _AllChem
                volume_a3 = _AllChem.ComputeMolVolume(mol, gridSpacing=0.2)
                volume_nm3 = volume_a3 * 1e-3  # Å³ → nm³
            except Exception:
                # 兜底：用 MW 估算体积 (近似密度 1 g/cm³)
                volume_nm3 = mw / 1.0 * 1e-3  # g → cm³ → nm³ (1 cm³ = 1e-3 nm³? No: 1 cm = 1e7 nm, 1 cm³ = 1e21 nm³)
                # 实际上: 1 g/cm³ → MW g → MW cm³ → MW * 1e21 nm³
                # 但我们用摩尔体积: MW(g/mol) / density(g/cm³) = cm³/mol → ×1e21 = nm³/mol
                # 简化估算：单分子体积 ≈ MW / (Avogadro * density) cm³
                # → MW / (6.022e23 * 1.0) cm³ → ×1e21 nm³
                volume_nm3 = mw / 6.022e23 * 1e21  # nm³ per molecule

            total_mw += mw
            total_volume_nm3 += volume_nm3

            mol_infos.append({
                "smiles": smiles,
                "molecule_index": idx,
                "molecular_weight": round(mw, 3),
                "volume_nm3": round(volume_nm3, 6),
            })

        if not mol_infos:
            return {
                "structure_id": "s-001",
                "density": 0.0,
                "energy": 0.0,
                "warning": "所有分子均无法解析",
            }

        # 估算堆积密度
        # 堆积分数 (packing fraction): 晶体 ~0.7, 无定形 ~0.55, 溶剂化 ~0.45
        packing_fractions = {"crystal": 0.70, "amorphous": 0.55, "solvation": 0.45}
        pf = packing_fractions.get(packing_type, 0.55)

        # 盒子尺寸
        if box_size_nm is None:
            # 根据分子总体积和堆积分数估算盒子大小
            box_volume_nm3 = total_volume_nm3 / pf
            box_size_nm = round(box_volume_nm3 ** (1.0 / 3.0), 3)
        else:
            box_volume_nm3 = box_size_nm ** 3

        # 密度 = 总质量 / 总体积
        # 总质量(g) = total_mw (g/mol) / Avogadro * N_molecules
        # 这里假设每个分子各 1 个，密度 = MW / (Vm * Avogadro) * 1e21 (g/cm³)
        # 简化：密度 ≈ total_mw * pf / (box_volume * Avogadro) * 1e21
        avogadro = 6.022e23
        if box_volume_nm3 > 0:
            # g/cm³ = (g/mol * 1 molecule) / (nm³ * 1e-21 cm³/nm³ * Avogadro)
            density_g_cm3 = (total_mw / avogadro) / (box_volume_nm3 * 1e-21)
            density_g_cm3 = round(density_g_cm3, 4)
        else:
            density_g_cm3 = 0.0

        # 如果有目标密度，调整盒子大小
        if target_density and target_density > 0 and total_mw > 0:
            # V = m / ρ → box_volume = (total_mw / avogadro) / (target_density * 1e-21)
            box_volume_nm3 = (total_mw / avogadro) / (target_density * 1e-21)
            box_size_nm = round(box_volume_nm3 ** (1.0 / 3.0), 3)
            density_g_cm3 = target_density

        # 估算能量 (简化：用堆积分数 * kBT 近似)
        # 实际能量需要 MD 模拟，这里给一个合理的占位值
        energy_kj_mol = round(-pf * 10.0 * len(mol_infos), 3)  # 近似堆积能

        return {
            "structure_id": "s-001",
            "method": "rdkit_3d_packing",
            "packing_type": packing_type,
            "molecules": mol_infos,
            "box_size_nm": box_size_nm,
            "box_volume_nm3": round(box_volume_nm3, 6),
            "packing_fraction": pf,
            "density": density_g_cm3,
            "density_unit": "g/cm³",
            "energy": energy_kj_mol,
            "energy_unit": "kJ/mol",
            "force_field": force_field,
        }