"""分子对接输入验证 — 受体/配体格式、参数范围、适用范围校验。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── 受体格式定义 ────────────────────────────────────────────

RECEPTOR_FORMATS: dict[str, dict[str, Any]] = {
    "pdb": {
        "description": "Protein Data Bank 格式",
        "extensions": {".pdb", ".ent"},
        "requires_ligand": False,
    },
    "mmcif": {
        "description": "mmCIF 格式",
        "extensions": {".cif", ".mmcif"},
        "requires_ligand": False,
    },
}

# ── 配体格式定义 ────────────────────────────────────────────

LIGAND_FORMATS: dict[str, dict[str, Any]] = {
    "smiles": {
        "description": "SMILES 字符串",
        "requires_structure_file": False,
        "max_length": 1024,
    },
    "sdf": {
        "description": "SDF 分子文件",
        "requires_structure_file": True,
        "extensions": {".sdf"},
    },
    "mol2": {
        "description": "MOL2 分子文件",
        "requires_structure_file": True,
        "extensions": {".mol2",".mol"},
    },
}

# ── 参数范围 ────────────────────────────────────────────────

LIGAND_MW_RANGE: tuple[float, float] = (100.0, 1000.0)
SAMPLES_PER_COMPLEX_RANGE: tuple[int, int] = (1, 50)
INFERENCE_STEPS_RANGE: tuple[int, int] = (10, 50)
CONFIDENCE_THRESHOLD_RANGE: tuple[float, float] = (0.0, 1.0)
BATCH_WORKERS_RANGE: tuple[int, int] = (1, 16)
TOP_N_RANGE: tuple[int, int] = (1, 1000)

# ── 适用范围 ────────────────────────────────────────────────

REJECTED_DOCKING_TYPES: dict[str, str] = {
    "protein_protein": "蛋白-蛋白对接（非小分子配体，请使用蛋白-蛋白对接工具）",
    "covalent": "共价对接（当前版本不支持共价配体对接）",
    "large_peptide": "大肽分子对接（肽链长度超过 15 个氨基酸残基）",
}


# ── 校验函数 ────────────────────────────────────────────────


def validate_receptor_format(receptor_path: str) -> dict[str, Any]:
    """校验受体文件格式是否为 PDB / mmCIF。"""
    ext = _extract_extension(receptor_path)
    for fmt, info in RECEPTOR_FORMATS.items():
        if ext in info["extensions"]:
            return {"valid": True, "errors": [], "receptor_format": fmt}
    return {
        "valid": False,
        "errors": [
            f"不支持的受体文件格式 '{ext}'。支持: PDB (.pdb, .ent), mmCIF (.cif, .mmcif)"
        ],
    }


def validate_ligand_format(ligand_format: str) -> dict[str, Any]:
    """校验配体格式是否受支持。"""
    key = ligand_format.strip().lower()
    if key not in LIGAND_FORMATS:
        return {
            "valid": False,
            "errors": [
                f"不支持的配体格式 '{ligand_format}'。支持: {', '.join(sorted(LIGAND_FORMATS))}"
            ],
        }
    return {"valid": True, "errors": [], "ligand_format_info": LIGAND_FORMATS[key]}


def validate_ligand_molecular_weight(mw: float | None) -> dict[str, Any]:
    """校验配体分子量是否在合理范围内。"""
    errors: list[str] = []
    warnings: list[str] = []

    if mw is None:
        return {"valid": True, "errors": errors, "warnings": warnings}

    if mw <= 0:
        errors.append("分子量必须为正数")
    elif mw < LIGAND_MW_RANGE[0] or mw > LIGAND_MW_RANGE[1]:
        warnings.append(
            f"分子量 {mw:.1f} Da 超出典型范围 ({LIGAND_MW_RANGE[0]}-{LIGAND_MW_RANGE[1]} Da)"
        )

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate_sampling_params(
    samples_per_complex: int = 10,
    inference_steps: int = 20,
) -> dict[str, Any]:
    """校验采样参数范围。"""
    errors: list[str] = []
    warnings: list[str] = []

    if not (SAMPLES_PER_COMPLEX_RANGE[0] <= samples_per_complex <= SAMPLES_PER_COMPLEX_RANGE[1]):
        errors.append(
            f"samples_per_complex 必须在 {SAMPLES_PER_COMPLEX_RANGE[0]}-{SAMPLES_PER_COMPLEX_RANGE[1]} 范围内"
        )

    if not (INFERENCE_STEPS_RANGE[0] <= inference_steps <= INFERENCE_STEPS_RANGE[1]):
        errors.append(
            f"inference_steps 必须在 {INFERENCE_STEPS_RANGE[0]}-{INFERENCE_STEPS_RANGE[1]} 范围内"
        )

    if inference_steps > 30:
        warnings.append(f"inference_steps={inference_steps} 较高，预计推理时间较长")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate_confidence_threshold(threshold: float) -> dict[str, Any]:
    """校验置信度阈值范围。"""
    errors: list[str] = []
    warnings: list[str] = []

    if threshold < CONFIDENCE_THRESHOLD_RANGE[0] or threshold > CONFIDENCE_THRESHOLD_RANGE[1]:
        errors.append(
            f"confidence_threshold 必须在 {CONFIDENCE_THRESHOLD_RANGE[0]}-{CONFIDENCE_THRESHOLD_RANGE[1]} 范围内"
        )

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate_batch_params(
    complexes: list[dict[str, Any]],
    workers: int = 1,
) -> dict[str, Any]:
    """校验批处理参数。"""
    errors: list[str] = []
    warnings: list[str] = []

    if not complexes:
        errors.append("complexes 列表不能为空")
        return {"valid": False, "errors": errors, "warnings": warnings}

    if len(complexes) > 1000:
        warnings.append(f"批量任务数量 {len(complexes)} 较大，建议分批处理")

    if not (BATCH_WORKERS_RANGE[0] <= workers <= BATCH_WORKERS_RANGE[1]):
        errors.append(
            f"workers 必须在 {BATCH_WORKERS_RANGE[0]}-{BATCH_WORKERS_RANGE[1]} 范围内"
        )

    # 校验每个 complex 的必需字段
    for i, cx in enumerate(complexes):
        if "receptor_path" not in cx:
            errors.append(f"complexes[{i}] 缺少必需的 'receptor_path' 字段")
        if "ligand" not in cx:
            errors.append(f"complexes[{i}] 缺少必需的 'ligand' 字段")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate_docking_scope(docking_type: str) -> dict[str, Any]:
    """校验对接类型是否在适用范围之内。"""
    key = docking_type.strip().lower()
    if key in REJECTED_DOCKING_TYPES:
        return {
            "valid": False,
            "errors": [
                f"不支持的对接类型 '{docking_type}': {REJECTED_DOCKING_TYPES[key]}"
            ],
        }
    return {"valid": True, "errors": []}


def validate_top_n(top_n: int, total_poses: int | None = None) -> dict[str, Any]:
    """校验 top_n 参数范围。"""
    errors: list[str] = []

    if not (TOP_N_RANGE[0] <= top_n <= TOP_N_RANGE[1]):
        errors.append(f"top_n 必须在 {TOP_N_RANGE[0]}-{TOP_N_RANGE[1]} 范围内")

    if total_poses is not None and top_n > total_poses:
        errors.append(f"top_n ({top_n}) 不能超过已有位姿总数 ({total_poses})")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": []}


# ── 辅助函数 ────────────────────────────────────────────────


def _extract_extension(path: str) -> str:
    """提取文件扩展名（小写）。"""
    idx = path.rfind(".")
    if idx == -1:
        return ""
    return path[idx:].lower()


# ── 验证器类 ────────────────────────────────────────────────


class MolecularDockingValidator(BaseModel):
    """分子对接输入验证器 — 封装完整的输入校验逻辑。"""

    receptor_path: str = Field(..., description="受体文件路径")
    ligand: str = Field(..., description="配体数据（SMILES 或文件路径）")
    ligand_format: str = Field(default="smiles", description="配体格式: smiles, sdf, mol2")
    ligand_mw: float | None = Field(default=None, description="配体分子量 (Da)")
    samples_per_complex: int = Field(default=10, description="每个复合物采样数 (1-50)")
    inference_steps: int = Field(default=20, description="推理步数 (10-50)")
    docking_type: str = Field(default="small_molecule", description="对接类型: small_molecule")

    def validate_all(self) -> dict[str, Any]:
        """执行完整校验，返回校验结果。"""
        result: dict[str, Any] = {"valid": True, "errors": [], "warnings": []}

        # 1. 校验受体文件格式
        rec_result = validate_receptor_format(self.receptor_path)
        if not rec_result["valid"]:
            result["errors"].extend(rec_result["errors"])
            result["valid"] = False
            return result
        result["receptor_format"] = rec_result["receptor_format"]

        # 2. 校验配体非空
        if not self.ligand or not self.ligand.strip():
            result["errors"].append("ligand 不能为空")
            result["valid"] = False
            return result

        # 3. 校验配体格式
        lig_result = validate_ligand_format(self.ligand_format)
        if not lig_result["valid"]:
            result["errors"].extend(lig_result["errors"])
            result["valid"] = False
        else:
            result["ligand_format_info"] = lig_result["ligand_format_info"]

        # 4. 校验配体分子量
        mw_result = validate_ligand_molecular_weight(self.ligand_mw)
        result["errors"].extend(mw_result["errors"])
        result["warnings"].extend(mw_result["warnings"])

        # 5. 校验采样参数
        sp_result = validate_sampling_params(
            samples_per_complex=self.samples_per_complex,
            inference_steps=self.inference_steps,
        )
        result["errors"].extend(sp_result["errors"])
        result["warnings"].extend(sp_result["warnings"])

        # 6. 校验对接类型范围
        scope_result = validate_docking_scope(self.docking_type)
        if not scope_result["valid"]:
            result["errors"].extend(scope_result["errors"])
            result["valid"] = False

        if result["errors"]:
            result["valid"] = False

        return result