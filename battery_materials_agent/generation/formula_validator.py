"""候选材料化学式 / SMILES 合法性校验引擎（P1-1）。

解决产品评审发现的问题：未经验证的候选材料（如单元素 "Ac"、括号不匹配的
"Ca(H8O5)2"、预测值全为 0 的模型失效输出）直接展示给用户，严重损害专业可信度。

校验规则：
1. 化学式必须包含至少两种元素（拒绝单元素候选，电池材料均为化合物/合金体系）
2. 元素符号必须属于周期表，括号必须配对，系数必须为正数
3. SMILES 必须通过基本字符集与括号配对校验
4. 批量层面：全部候选预测值为 0 判定为模型推理失效（data_quality_flag=invalid）
"""

from __future__ import annotations

import re
from typing import Any

# 周期表 1-118 号元素符号
_ELEMENTS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne",
    "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar",
    "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr",
    "Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd",
    "In", "Sn", "Sb", "Te", "I", "Xe",
    "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy",
    "Ho", "Er", "Tm", "Yb", "Lu",
    "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Tl", "Pb", "Bi", "Po", "At", "Rn",
    "Fr", "Ra", "Ac", "Th", "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf",
    "Es", "Fm", "Md", "No", "Lr",
    "Rf", "Db", "Sg", "Bh", "Hs", "Mt", "Ds", "Rg", "Cn",
    "Nh", "Fl", "Mc", "Lv", "Ts", "Og",
}

_FORMULA_TOKEN = re.compile(r"([A-Z][a-z]?|\(|\)|\d*\.?\d+)")
_SMILES_VALID_CHARS = re.compile(r"^[A-Za-z0-9@+\-\[\]\(\)=#$:/\\.%*]+$")


def parse_formula(formula: str) -> dict[str, float] | None:
    """解析化学式为 {元素: 系数}，支持一层及嵌套括号。非法输入返回 None。"""
    if not formula or not formula.strip():
        return None
    tokens = _FORMULA_TOKEN.findall(formula.strip())
    if not tokens or "".join(tokens) != formula.strip():
        return None  # 存在无法识别的字符

    # 栈式解析：每帧为当前括号层级的元素计数字典
    stack: list[dict[str, float]] = [{}]
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "(":
            stack.append({})
        elif tok == ")":
            if len(stack) < 2:
                return None  # 括号不匹配
            group = stack.pop()
            multiplier = 1.0
            if i + 1 < len(tokens) and re.fullmatch(r"\d*\.?\d+", tokens[i + 1]):
                multiplier = float(tokens[i + 1])
                i += 1
            if multiplier <= 0:
                return None
            for el, cnt in group.items():
                stack[-1][el] = stack[-1].get(el, 0.0) + cnt * multiplier
        elif re.fullmatch(r"[A-Z][a-z]?", tok):
            if tok not in _ELEMENTS:
                return None  # 未知元素符号
            count = 1.0
            if i + 1 < len(tokens) and re.fullmatch(r"\d*\.?\d+", tokens[i + 1]):
                count = float(tokens[i + 1])
                i += 1
            if count <= 0:
                return None
            stack[-1][tok] = stack[-1].get(tok, 0.0) + count
        else:
            return None  # 孤立数字（系数前无元素/括号）
        i += 1
    if len(stack) != 1:
        return None  # 括号未闭合
    return stack[0] or None


def parse_formula_elements(formula: str) -> set[str]:
    """从化学式中提取元素符号集合（公共 API）。

    支持嵌套括号与小数系数，例如：
        "Li2O"               → {"Li", "O"}
        "Na2CaMg(SO4)3"      → {"Na", "Ca", "Mg", "S", "O"}
        "LiNi0.8Mn0.1Co0.1O2" → {"Li", "Ni", "Mn", "Co", "O"}

    非法化学式（未知元素、括号不匹配）返回空集合，调用方据此判定失败。
    """
    composition = parse_formula(formula)
    if composition is None:
        return set()
    return set(composition.keys())


def validate_formula(formula: str) -> tuple[bool, str]:
    """化学式合法性校验。返回 (is_valid, reason)。"""
    if not formula or not formula.strip():
        return False, "化学式为空"
    composition = parse_formula(formula)
    if composition is None:
        return False, "化学式格式非法（未知元素、括号不匹配或系数异常）"
    if len(composition) < 2:
        return False, "仅含单一元素，不构成电池材料化合物体系"
    return True, ""


def validate_smiles(smiles: str) -> tuple[bool, str]:
    """SMILES 基本合法性校验（字符集 + 括号配对）。返回 (is_valid, reason)。"""
    if not smiles or not smiles.strip():
        return False, "SMILES 为空"
    s = smiles.strip()
    if not _SMILES_VALID_CHARS.match(s):
        return False, "SMILES 含非法字符"
    if s.count("(") != s.count(")"):
        return False, "SMILES 括号不匹配"
    if s.count("[") != s.count("]"):
        return False, "SMILES 方括号不匹配"
    return True, ""


def _extract_elements_from_formula(formula: str) -> set[str]:
    """从化学式中提取元素符号集合（优先使用 pymatgen，失败时回退到正则）。"""
    if not formula:
        return set()
    try:
        from pymatgen.core import Composition
        comp = Composition(formula)
        return {str(e) for e in comp.elements}
    except Exception:
        # 回退到正则（不精确，但好过无过滤）
        matches = re.findall(r"[A-Z][a-z]?", formula)
        return {m for m in matches if m in _ELEMENTS}


def _check_element_constraints(
    formula: str,
    require_elements: list[str] | None = None,
    exclude_elements: list[str] | None = None,
) -> tuple[bool, str]:
    """检查化学式是否满足元素包含/排除约束（P0-4）。

    Args:
        formula: 化学式
        require_elements: 必需包含的元素符号列表（如 ["Li"]）
        exclude_elements: 必须排除的元素符号列表（如 ["Co"]）

    Returns:
        (passed, reason)：passed=False 时 reason 说明违反原因
    """
    if not formula or (not require_elements and not exclude_elements):
        return True, ""
    elements = _extract_elements_from_formula(formula)
    if require_elements:
        required = {e.capitalize() for e in require_elements if e}
        missing = required - elements
        if missing:
            return False, f"缺少必需元素: {','.join(sorted(missing))}"
    if exclude_elements:
        excluded = {e.capitalize() for e in exclude_elements if e}
        present = excluded & elements
        if present:
            return False, f"包含排除元素: {','.join(sorted(present))}"
    return True, ""


def assess_candidate_quality(
    candidate: dict[str, Any],
    require_elements: list[str] | None = None,
    exclude_elements: list[str] | None = None,
) -> dict[str, Any]:
    """评估单个候选材料的数据质量。

    返回 {flag: "valid" | "invalid", issues: [str, ...]}：
    - invalid: 化学式/SMILES 未通过合法性校验，或违反元素约束，应阻止进入推荐池
    - valid: 通过校验

    P0-4：扩展 require_elements / exclude_elements 元素约束校验。
    """
    issues: list[str] = []
    formula = (candidate.get("formula") or "").strip()
    smiles = (candidate.get("smiles") or candidate.get("psmiles") or "").strip()

    if formula:
        ok, reason = validate_formula(formula)
        if not ok:
            issues.append(f"化学式异常：{reason}")
    if smiles:
        ok, reason = validate_smiles(smiles)
        if not ok:
            issues.append(f"SMILES 异常：{reason}")
    if not formula and not smiles:
        issues.append("缺少化学式与 SMILES 标识")

    # P0-4：元素包含/排除约束校验（仅在有 formula 时进行）
    if formula and (require_elements or exclude_elements):
        ok, reason = _check_element_constraints(formula, require_elements, exclude_elements)
        if not ok:
            issues.append(f"元素约束违反：{reason}")

    return {
        "flag": "invalid" if issues else "valid",
        "issues": issues,
    }


def assess_batch_quality(candidates: list[dict[str, Any]]) -> str:
    """批量质量评估：全部候选预测值为 0 判定模型推理失效。

    返回 "valid" | "all_zero_predictions"。
    """
    values = [
        c.get("expected_performance")
        for c in candidates
        if c.get("expected_performance") is not None
    ]
    if values and all(v == 0 for v in values):
        return "all_zero_predictions"
    return "valid"
