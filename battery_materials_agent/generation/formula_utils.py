"""化学式工具：元素提取与归一化，供生成器、候选存储与导入脚本共用。

避免各模块互相引用私有函数（跨模块私有依赖），统一从这里取公共实现。
"""
from __future__ import annotations

import re as _re


def normalize_formula(formula: str) -> str:
    """归一化化学式用于去重：使用 pymatgen 的 reduced_formula 保留化学计量比。

    这样 LiCoO2 与 Li2CoO3 不会被误判为同一材料（仅按元素集合去重会导致此问题）。
    """
    if not formula:
        return ""
    try:
        from pymatgen.core import Composition
        return Composition(formula).reduced_formula
    except Exception:
        # 回退：元素符号排序拼接（不精确，但好过无去重）
        elems = extract_elements(formula)
        return "".join(sorted(elems))


def extract_elements(formula: str) -> set[str]:
    """从化学式中提取元素符号集合（保留原大小写：Co、Li、O、C）。

    使用 pymatgen.core.Composition 精确解析，正确区分 Co（钴）与 C+O（碳+氧）。
    """
    if not formula:
        return set()
    try:
        from pymatgen.core import Composition
        comp = Composition(formula)
        return {str(e) for e in comp.elements}
    except Exception:
        # 回退到正则（不精确，但好过无过滤）
        matches = _re.findall(r"[A-Z][a-z]?", formula)
        return {m for m in matches if m}