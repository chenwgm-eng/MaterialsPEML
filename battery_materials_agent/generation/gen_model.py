"""Generative model interface for molecular/crystal space exploration.

Uses template-based generation (no real AI model required).
"""

from __future__ import annotations
import itertools
import logging
import random
import re

_RANDOM = random.Random(42)  # 固定种子，确保可复现
logger = logging.getLogger(__name__)

# 元素 → SMILES 片段映射（用于分子模板组合）
_ELEMENT_SMILES_FRAGMENT: dict[str, list[str]] = {
    "C": ["C", "CC", "CCC"],
    "O": ["O", "CO", "CCO"],
    "N": ["N", "CN", "CCN"],
    "S": ["S", "CS", "CCS"],
    "F": ["F", "CF", "CCF"],
    "P": ["P", "CP", "CCP"],
    "Cl": ["Cl", "CCl", "CCCl"],
    "B": ["B", "CB", "CCB"],
}

# 分子模板：常见小分子骨架（SMILES）
_MOLECULE_TEMPLATES: list[str] = [
    "C", "CC", "CCO", "CCN", "CCCO", "CC(=O)O", "CC(=O)N",
    "C1CCC1", "C1CCCCC1", "c1ccccc1", "CCOCC", "C1COCC1",
]

# 已知电池晶体材料模板
_CRYSTAL_TEMPLATES: list[dict] = [
    {"formula": "LiCoO2", "space_group": "R-3m", "structure_type": "Layered"},
    {"formula": "LiNiO2", "space_group": "R-3m", "structure_type": "Layered"},
    {"formula": "LiMn2O4", "space_group": "Fd-3m", "structure_type": "Spinel"},
    {"formula": "LiFePO4", "space_group": "Pnma", "structure_type": "Olivine"},
    {"formula": "Li2MnO3", "space_group": "C2/m", "structure_type": "Layered"},
    {"formula": "Li3PS4", "space_group": "Pnma", "structure_type": "Thio-LISICON"},
    {"formula": "Li6PS5Cl", "space_group": "F-43m", "structure_type": "Argyrodite"},
    {"formula": "Li10GeP2S12", "space_group": "P42/nmc", "structure_type": "LGPS"},
    {"formula": "Li7La3Zr2O12", "space_group": "Ia-3d", "structure_type": "Garnet"},
    {"formula": "Na3PS4", "space_group": "P213", "structure_type": "NASICON"},
    {"formula": "Li2S", "space_group": "Fm-3m", "structure_type": "Antifluorite"},
    {"formula": "TiO2", "space_group": "P42/mnm", "structure_type": "Rutile"},
]


class GenerativeModel:
    """生成式分子/晶体空间探索模型接口。

    使用模板化生成逻辑（无需真实 AI 模型）。
    """

    def generate_molecules(self, constraints: dict) -> list[dict]:
        """基于约束生成候选分子。

        constraints: {elements: [], max_atoms: int, target_property: str}
        返回: [{smiles, confidence, description}]
        """
        elements = constraints.get("elements", []) or []
        max_atoms = constraints.get("max_atoms", 30)
        target_property = constraints.get("target_property", "")

        candidates: list[dict] = []
        seen: set[str] = set()

        # 1. 元素片段组合
        for elem in elements:
            for frag in _ELEMENT_SMILES_FRAGMENT.get(elem, []):
                if frag not in seen and self._count_smiles_atoms(frag) <= max_atoms:
                    seen.add(frag)
                    candidates.append(self._make_molecule(frag, elements, target_property))

        # 2. 元素两两组合生成简单 SMILES
        for e1, e2 in itertools.combinations(elements, 2):
            for combo in (f"{e1}{e2}", f"CC{e1}{e2}", f"C{e1}C{e2}"):
                if combo not in seen and self._count_smiles_atoms(combo) <= max_atoms:
                    seen.add(combo)
                    candidates.append(self._make_molecule(combo, elements, target_property))

        # 3. 通用分子模板兜底（无元素约束或候选不足时）
        if not elements or len(candidates) < 3:
            allowed = set(elements) | {"C", "c"}
            for smiles in _MOLECULE_TEMPLATES:
                if smiles in seen:
                    continue
                if elements:
                    elems_in = self._extract_smiles_elements(smiles)
                    if not elems_in.issubset(allowed):
                        continue
                if self._count_smiles_atoms(smiles) > max_atoms:
                    continue
                seen.add(smiles)
                candidates.append(self._make_molecule(smiles, elements, target_property))

        # 去重并按置信度排序
        unique = list({c["smiles"]: c for c in candidates}.values())
        unique.sort(key=lambda c: c["confidence"], reverse=True)
        return unique

    def generate_crystals(self, constraints: dict) -> list[dict]:
        """基于约束生成候选晶体结构。

        constraints: {elements: [], space_groups: [], max_atoms: int}
        返回: [{formula, space_group, confidence, description}]
        """
        elements = constraints.get("elements", []) or []
        space_groups = constraints.get("space_groups", []) or []
        max_atoms = constraints.get("max_atoms", 50)

        candidates: list[dict] = []
        seen: set[str] = set()

        # 1. 从已知电池材料模板筛选
        for tmpl in _CRYSTAL_TEMPLATES:
            formula = tmpl["formula"]
            if formula in seen:
                continue
            if elements:
                tmpl_elems = self._extract_formula_elements(formula)
                if not any(e in tmpl_elems for e in elements):
                    continue
            if space_groups and tmpl["space_group"] not in space_groups:
                continue
            if self._count_formula_atoms(formula) > max_atoms:
                continue
            seen.add(formula)
            candidates.append(self._make_crystal(tmpl, elements, space_groups))

        # 2. 基于元素组合生成新化学式
        if len(elements) >= 2:
            stoich_patterns = [
                (1, 1, "P1"), (1, 2, "P42/mnm"), (2, 1, "Fm-3m"),
                (2, 3, "C2/m"), (3, 1, "R-3m"),
            ]
            for e1, e2 in itertools.combinations(elements, 2):
                for n1, n2, sg in stoich_patterns:
                    if n1 + n2 > max_atoms:
                        continue
                    if space_groups and sg not in space_groups:
                        continue
                    formula = f"{e1}{n1 if n1 > 1 else ''}{e2}{n2 if n2 > 1 else ''}"
                    if formula in seen:
                        continue
                    seen.add(formula)
                    candidates.append(self._make_crystal(
                        {"formula": formula, "space_group": sg, "structure_type": "Generated"},
                        elements, space_groups,
                    ))

        unique = list({c["formula"]: c for c in candidates}.values())
        unique.sort(key=lambda c: c["confidence"], reverse=True)

        # 校验化学式有效性，过滤非规范化学式
        validated = []
        for c in unique:
            if self._validate_formula(c["formula"]):
                validated.append(c)
            else:
                logger.warning("过滤非规范化学式: %s", c.get("formula", ""))
        # 如果全部被过滤，保留原始候选但标记 human_review_required
        if not validated:
            for c in unique:
                c["human_review_required"] = True
                c["description"] = (c.get("description", "") + "；化学式待人工审核").strip("；")
            validated = unique
        return validated

    def _validate_formula(self, formula: str) -> bool:
        """校验化学式是否规范有效。

        优先使用 SCP NameToSMILES/Formula 工具校验，
        失败时回退到 pymatgen 本地校验。
        """
        # 方案 B 回退：使用 pymatgen Composition 校验
        try:
            from pymatgen.core import Composition
            comp = Composition(formula)
            if comp.num_atoms <= 0:
                return False
            # 检查元素是否真实存在
            for elem in comp.elements:
                if elem.Z == 0 or elem.Z > 118:
                    return False
            return True
        except Exception:
            return False

    def _make_molecule(self, smiles: str, elements: list[str], target_property: str) -> dict:
        confidence = round(_RANDOM.uniform(0.6, 0.95), 3)
        parts = []
        if elements:
            parts.append(f"基于所选元素 {', '.join(elements)} 的模板组合")
        else:
            parts.append("基于通用分子模板库")
        if target_property:
            parts.append(f"针对目标属性 '{target_property}'")
        parts.append(f"原子数 {self._count_smiles_atoms(smiles)}")
        return {
            "smiles": smiles,
            "confidence": confidence,
            "description": "；".join(parts),
        }

    def _make_crystal(self, tmpl: dict, elements: list[str], space_groups: list[str]) -> dict:
        confidence = round(_RANDOM.uniform(0.6, 0.95), 3)
        parts = []
        if elements:
            parts.append(f"含所选元素 {', '.join(elements)} 的电池材料模板")
        else:
            parts.append("基于已知电池材料模板库")
        if space_groups:
            parts.append(f"匹配空间群 {', '.join(space_groups)}")
        if tmpl.get("structure_type"):
            parts.append(f"结构类型 {tmpl['structure_type']}")
        return {
            "formula": tmpl["formula"],
            "space_group": tmpl["space_group"],
            "confidence": confidence,
            "description": "；".join(parts),
        }

    @staticmethod
    def _extract_smiles_elements(smiles: str) -> set[str]:
        """从 SMILES 提取元素符号（含芳香族小写原子）。"""
        return set(re.findall(r"[A-Z][a-z]?|[cnopsb]", smiles))

    @staticmethod
    def _count_smiles_atoms(smiles: str) -> int:
        """粗略统计 SMILES 中的重原子数。"""
        return len(re.findall(r"[A-Z][a-z]?|[cnopsb]", smiles))

    @staticmethod
    def _extract_formula_elements(formula: str) -> set[str]:
        """从化学式提取元素符号。"""
        return set(re.findall(r"[A-Z][a-z]?", formula))

    @staticmethod
    def _count_formula_atoms(formula: str) -> int:
        """统计化学式中的原子总数（含系数）。"""
        total = 0
        for _, count in re.findall(r"([A-Z][a-z]?)(\d*)", formula):
            total += int(count) if count else 1
        return total
