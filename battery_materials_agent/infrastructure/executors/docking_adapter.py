"""分子对接适配器 — 封装蛋白-配体对接推理。

基于 AutoDock Vina 的真实对接（委托 VinaAdapter，经 Docker 常驻容器执行）。
仅当 Vina 引擎不可用时，才回退到占位推理。
"""

from __future__ import annotations

from typing import Any

from .execution_adapter import ExecutionAdapter


class DockingAdapter(ExecutionAdapter):
    """分子对接适配器 — 委托 AutoDock Vina（VinaAdapter）执行真实对接。

    保留输入校验/RDKit 配体验证语义；实际位姿生成委托给 VinaAdapter。
    仅当 Vina 引擎不可用时回退到占位推理。
    """

    def __init__(self) -> None:
        try:
            from .vina_adapter import VinaAdapter
            self._vina: Any = VinaAdapter()
        except Exception:  # noqa: BLE001
            self._vina = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """执行分子对接推理。

        Input format::

            {
                "protein_path": "/path/to/receptor.pdb",
                "ligand": "CCO",              # SMILES 或文件路径
                "ligand_format": "smiles",     # smiles | sdf | mol2
                "samples_per_complex": 10,
                "inference_steps": 20,
                "device": "cpu",
                "complex_index": 0,
                "box_center": [x, y, z],   # 可选，结合口袋中心（Å）
                "box_size": [dx, dy, dz],  # 可选，搜索盒尺寸（Å）
            }

        Output format::

            {
                "status": "completed",
                "complex_index": 0,
                "runtime_seconds": 45.2,
                "receptor_path": "...",
                "ligand": "...",
                "poses": [
                    {
                        "rank": 1,
                        "confidence": 0.95,
                        "sdf_path": "/path/to/pose_1.sdf",
                        "metadata": {...},
                    },
                    ...
                ],
                "warnings": [...],
            }
        """
        protein_path = prepared_input.get("protein_path", "")
        ligand = prepared_input.get("ligand", "")
        ligand_format = prepared_input.get("ligand_format", "smiles")
        samples = prepared_input.get("samples_per_complex", 10)
        steps = prepared_input.get("inference_steps", 20)
        device = prepared_input.get("device", "cpu")

        # 1. 输入检查
        input_errors = self._check_input(protein_path, ligand, ligand_format)
        if input_errors:
            return {
                "status": "failed",
                "complex_index": prepared_input.get("complex_index", 0),
                "errors": input_errors,
                "poses": [],
                "warnings": [],
            }

        # 2. 配体 RDKit 验证
        ligand_ok, ligand_warnings = self._validate_ligand_rdkit(ligand, ligand_format)
        if not ligand_ok:
            return {
                "status": "failed",
                "complex_index": prepared_input.get("complex_index", 0),
                "errors": [f"配体验证失败: {ligand_warnings}"],
                "poses": [],
                "warnings": [],
            }

        # 3. 执行推理：优先真实 AutoDock Vina，否则回退推理（显式降级，不伪装成功）
        if self._vina is not None:
            result = self._vina.execute(prepared_input)
            if result.get("status") == "completed":
                result["warnings"] = (result.get("warnings") or []) + ligand_warnings
                return result

        # Vina 引擎不可用或失败 → 降级推理：明确标记为模拟数据，不进入正式证据链
        result = self._run_fallback(protein_path, ligand, samples, steps)
        result["warnings"] = (result.get("warnings") or []) + ligand_warnings
        return result

    def parse_output(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        """解析原始输出为结构化 dict。"""
        if isinstance(raw_output, dict):
            return raw_output
        return {"status": "unknown", "poses": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """返回资源需求。"""
        device = input_data.get("device", "cpu")
        samples = input_data.get("samples_per_complex", 10)

        if device == "cuda":
            return {"cpu": 8, "memory_mb": 8192, "walltime_minutes": 15, "gpu": 1, "gpu_memory_mb": 4096}
        return {"cpu": 4, "memory_mb": 4096, "walltime_minutes": 30, "gpu": 0}

    # ------------------------------------------------------------------
    # 输入检查
    # ------------------------------------------------------------------

    def _check_input(
        self,
        protein_path: str,
        ligand: str,
        ligand_format: str,
    ) -> list[str]:
        """检查输入完整性。"""
        errors: list[str] = []

        if not protein_path:
            errors.append("protein_path 不能为空")
        else:
            ext = self._extract_extension(protein_path)
            if ext not in (".pdb", ".ent", ".cif", ".mmcif"):
                errors.append(f"不支持的受体格式 '{ext}'，支持: .pdb, .ent, .cif, .mmcif")

        if not ligand:
            errors.append("ligand 不能为空")

        if ligand_format not in ("smiles", "sdf", "mol2"):
            errors.append(f"不支持的配体格式 '{ligand_format}'，支持: smiles, sdf, mol2")

        return errors

    def _validate_ligand_rdkit(self, ligand: str, ligand_format: str) -> tuple[bool, list[str]]:
        """使用 RDKit 验证配体（如果可用）。"""
        warnings: list[str] = []

        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors

            if ligand_format == "smiles":
                mol = Chem.MolFromSmiles(ligand)
                if mol is None:
                    return False, [f"无效 SMILES: {ligand}"]
                mw = Descriptors.MolWt(mol)
                if mw < 100 or mw > 1000:
                    warnings.append(f"配体分子量 {mw:.1f} Da 超出推荐范围 (100-1000 Da)")
            elif ligand_format in ("sdf", "mol2"):
                # 文件路径模式，仅检查文件存在性
                import os
                if not os.path.exists(ligand):
                    return False, [f"配体文件不存在: {ligand}"]
                return True, warnings
        except ImportError:
            warnings.append("RDKit 不可用，跳过配体结构验证")

        return True, warnings

    # ------------------------------------------------------------------
    # 推理（Vina 不可用时的回退）
    # ------------------------------------------------------------------

    def _run_fallback(
        self,
        protein_path: str,
        ligand: str,
        samples: int,
        steps: int,
    ) -> dict[str, Any]:
        """降级推理（AutoDock Vina 不可用时的模拟结果）。

        返回 ``status: degraded`` 并携带 ``source: simulated`` 标记，明确区分于
        真实引擎结果，禁止以 ``completed`` 呈现伪造位姿（避免进入正式证据链）。
        """
        poses: list[dict[str, Any]] = []
        for rank in range(1, min(samples, 5) + 1):
            confidence = max(0.0, 0.90 - (rank - 1) * 0.12)
            poses.append({
                "rank": rank,
                "confidence": round(confidence, 3),
                "sdf_path": f"poses/{rank:04d}_pose.sdf",
                "metadata": {"method": "simulated", "seed": rank * 42},
            })

        return {
            "status": "degraded",
            "source": "simulated",
            "complex_index": 0,
            "runtime_seconds": 10.0 + samples * 1.0 + steps * 0.3,
            "receptor_path": protein_path,
            "ligand": ligand,
            "poses": poses,
            "warnings": ["AutoDock Vina 引擎不可用，返回模拟位姿（非正式对接结果）"],
        }

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_extension(path: str) -> str:
        """提取文件扩展名（小写）。"""
        idx = path.rfind(".")
        if idx == -1:
            return ""
        return path[idx:].lower()