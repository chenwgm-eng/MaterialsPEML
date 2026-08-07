"""反应网络分析输入验证 — 元素白名单、SMILES 合法性、网络参数、枚举参数校验。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── 元素白名单 ──────────────────────────────────────────────
ALLOWED_ELEMENTS: set[str] = {
    "H", "C", "N", "O", "F", "Cl", "Br", "I", "S", "P",
}

# ── 默认参数阈值 ────────────────────────────────────────────
DEFAULT_MAX_BARRIER_KCAL: float = 40.0
DEFAULT_MAX_REACTION_ENERGY_KCAL: float = 30.0
DEFAULT_MAX_BREAK_BONDS: int = 1
DEFAULT_MAX_FORM_BONDS: int = 1
DEFAULT_MAX_CANDIDATES_PER_PARENT: int = 300
DEFAULT_MAX_LAYERS: int = 3
DEFAULT_MAX_SPECIES: int = 250

# ── 校验函数 ────────────────────────────────────────────────


def validate_smiles(smiles: str) -> dict[str, Any]:
    """校验 SMILES 是否非空且格式合法。

    使用 RDKit 进行合法性检查；若 RDKit 不可用，仅做基本非空校验。

    Returns:
        dict: 包含 valid、errors、warnings 和 mol（可选）。
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not smiles or not smiles.strip():
        errors.append("SMILES 不能为空")
        return {"valid": False, "errors": errors, "warnings": warnings}

    # 尝试使用 RDKit 校验
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            errors.append(f"SMILES 格式无效: '{smiles}'")
            return {"valid": False, "errors": errors, "warnings": warnings}
        # 闭壳层检查：分子中所有原子价电子数为偶数（简化检查）
        even_electrons = all(
            atom.GetNumRadicalElectrons() == 0
            for atom in mol.GetAtoms()
        )
        if not even_electrons:
            warnings.append("SMILES 包含自由基，可能不是闭壳层分子")
        return {"valid": True, "errors": errors, "warnings": warnings, "mol": mol}
    except ImportError:
        warnings.append("RDKit 不可用，仅做基本 SMILES 非空校验")
        return {"valid": True, "errors": errors, "warnings": warnings}


def validate_elements(smiles: str) -> dict[str, Any]:
    """校验 SMILES 中的元素是否在允许的白名单内。

    Args:
        smiles: 待校验的 SMILES 字符串。

    Returns:
        dict: 包含 valid、errors、disallowed_elements。
    """
    errors: list[str] = []
    disallowed: set[str] = set()

    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"valid": False, "errors": ["无法解析 SMILES 进行元素检查"], "disallowed_elements": []}
        for atom in mol.GetAtoms():
            symbol = atom.GetSymbol()
            if symbol not in ALLOWED_ELEMENTS:
                disallowed.add(symbol)
    except ImportError:
        # RDKit 不可用时，尝试正则解析元素符号
        import re
        elements = re.findall(r'[A-Z][a-z]?', smiles)
        for el in elements:
            if el not in ALLOWED_ELEMENTS:
                disallowed.add(el)

    if disallowed:
        errors.append(f"包含不允许的元素: {', '.join(sorted(disallowed))}")
        return {"valid": False, "errors": errors, "disallowed_elements": sorted(disallowed)}

    return {"valid": True, "errors": errors, "disallowed_elements": []}


def validate_network_params(
    max_layers: int = DEFAULT_MAX_LAYERS,
    max_species: int = DEFAULT_MAX_SPECIES,
    max_barrier: float = DEFAULT_MAX_BARRIER_KCAL,
    max_reaction_energy: float = DEFAULT_MAX_REACTION_ENERGY_KCAL,
) -> dict[str, Any]:
    """校验反应网络扩展参数。

    Args:
        max_layers: 最大扩展层数 (1-3)。
        max_species: 最大物种数。
        max_barrier: 最大能垒阈值 (kcal/mol)。
        max_reaction_energy: 最大反应能量阈值 (kcal/mol)。

    Returns:
        dict: 包含 valid、errors、warnings。
    """
    errors: list[str] = []
    warnings: list[str] = []

    if max_layers < 1:
        errors.append("max_layers 必须至少为 1")
    elif max_layers > 3:
        warnings.append(f"max_layers={max_layers} 超出推荐范围 (1-3)，网络扩展可能过大")

    if max_species < 1:
        errors.append("max_species 必须至少为 1")
    elif max_species > 500:
        warnings.append(f"max_species={max_species} 较大，可能影响计算性能")

    if max_barrier <= 0:
        errors.append("max_barrier 必须为正数")
    elif max_barrier > 100:
        warnings.append(f"max_barrier={max_barrier} kcal/mol 过高，可能包含不合理的反应路径")

    if max_reaction_energy <= 0:
        errors.append("max_reaction_energy 必须为正数")
    elif max_reaction_energy > 100:
        warnings.append(f"max_reaction_energy={max_reaction_energy} kcal/mol 过高")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate_enumeration_params(
    max_break_bonds: int = DEFAULT_MAX_BREAK_BONDS,
    max_form_bonds: int = DEFAULT_MAX_FORM_BONDS,
    max_candidates_per_parent: int = DEFAULT_MAX_CANDIDATES_PER_PARENT,
) -> dict[str, Any]:
    """校验反应枚举参数。

    Args:
        max_break_bonds: 最多断键数。
        max_form_bonds: 最多成键数。
        max_candidates_per_parent: 每母体候选数上限。

    Returns:
        dict: 包含 valid、errors、warnings。
    """
    errors: list[str] = []
    warnings: list[str] = []

    if max_break_bonds < 0:
        errors.append("max_break_bonds 不能为负数")
    elif max_break_bonds > 2:
        warnings.append(f"max_break_bonds={max_break_bonds} 超过推荐值 (≤2)，候选数可能过大")

    if max_form_bonds < 0:
        errors.append("max_form_bonds 不能为负数")
    elif max_form_bonds > 2:
        warnings.append(f"max_form_bonds={max_form_bonds} 超过推荐值 (≤2)，候选数可能过大")

    if max_break_bonds == 0 and max_form_bonds == 0:
        errors.append("max_break_bonds 和 max_form_bonds 不能同时为 0")

    if max_candidates_per_parent < 1:
        errors.append("max_candidates_per_parent 必须至少为 1")
    elif max_candidates_per_parent > 1000:
        warnings.append(f"max_candidates_per_parent={max_candidates_per_parent} 较大，可能影响性能")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


# ── 验证器类 ────────────────────────────────────────────────


class ReactionNetworkValidator(BaseModel):
    """反应网络分析输入验证器 — 封装完整的输入校验逻辑。"""

    reactant_smiles: list[str] = Field(..., description="反应物 SMILES 列表")
    charge: int = Field(default=0, description="总电荷")
    multiplicity: int = Field(default=1, description="自旋多重度")
    max_break_bonds: int = Field(default=DEFAULT_MAX_BREAK_BONDS, description="最多断键数")
    max_form_bonds: int = Field(default=DEFAULT_MAX_FORM_BONDS, description="最多成键数")
    max_candidates: int = Field(default=DEFAULT_MAX_CANDIDATES_PER_PARENT, description="每母体候选数上限")
    max_layers: int = Field(default=DEFAULT_MAX_LAYERS, description="最大扩展层数")
    max_species: int = Field(default=DEFAULT_MAX_SPECIES, description="最大物种数")
    max_barrier: float = Field(default=DEFAULT_MAX_BARRIER_KCAL, description="最大能垒阈值 (kcal/mol)")
    max_reaction_energy: float = Field(default=DEFAULT_MAX_REACTION_ENERGY_KCAL, description="最大反应能量阈值 (kcal/mol)")

    def validate_all(self) -> dict[str, Any]:
        """执行完整校验，返回校验结果。"""
        result: dict[str, Any] = {"valid": True, "errors": [], "warnings": []}

        # 1. 校验反应物列表
        if not self.reactant_smiles:
            result["errors"].append("reactant_smiles 不能为空")
            result["valid"] = False
            return result

        # 2. 校验每个 SMILES
        for i, smi in enumerate(self.reactant_smiles):
            smi_result = validate_smiles(smi)
            if not smi_result["valid"]:
                result["errors"].extend([f"reactant[{i}]: {e}" for e in smi_result["errors"]])
                result["valid"] = False
            else:
                result["warnings"].extend([f"reactant[{i}]: {w}" for w in smi_result.get("warnings", [])])

            # 3. 元素白名单检查
            elem_result = validate_elements(smi)
            if not elem_result["valid"]:
                result["errors"].extend([f"reactant[{i}]: {e}" for e in elem_result["errors"]])
                result["valid"] = False

        # 若 SMILES 有错误，提前返回
        if not result["valid"]:
            return result

        # 4. 校验电荷与多重度
        if self.multiplicity < 1:
            result["errors"].append("multiplicity 必须至少为 1")
            result["valid"] = False
        elif self.multiplicity > 1:
            result["warnings"].append(f"multiplicity={self.multiplicity}，非单重态，注意反应性")

        # 5. 校验枚举参数
        enum_result = validate_enumeration_params(
            max_break_bonds=self.max_break_bonds,
            max_form_bonds=self.max_form_bonds,
            max_candidates_per_parent=self.max_candidates,
        )
        result["errors"].extend(enum_result["errors"])
        result["warnings"].extend(enum_result["warnings"])
        if not enum_result["valid"]:
            result["valid"] = False

        # 6. 校验网络参数
        net_result = validate_network_params(
            max_layers=self.max_layers,
            max_species=self.max_species,
            max_barrier=self.max_barrier,
            max_reaction_energy=self.max_reaction_energy,
        )
        result["errors"].extend(net_result["errors"])
        result["warnings"].extend(net_result["warnings"])
        if not net_result["valid"]:
            result["valid"] = False

        return result