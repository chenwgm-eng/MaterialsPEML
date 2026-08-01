"""Intent Interpreter — 从用户目标抽取结构化需求。"""
from __future__ import annotations

import re
from pydantic import BaseModel, Field


class MaterialScope(BaseModel):
    """材料范围。"""

    material_type: str = ""  # crystal/polymer/molecule/electrolyte
    composition: str = ""  # 成分约束
    structure_constraints: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    """风险评估。"""

    risk_level: str = "low"  # low/medium/high
    requires_dft: bool = False
    requires_experiment: bool = False
    requires_committee: bool = False


# 关键词 → material_type 映射（按优先级排序：先匹配 crystal/polymer，再匹配 molecule）
_MATERIAL_KEYWORDS: list[tuple[list[str], str]] = [
    (["晶体", "crystal"], "crystal"),
    (["聚合物", "polymer"], "polymer"),
    (["电解液", "electrolyte", "分子", "molecule"], "molecule"),
]


# 元素中文名 → 元素符号映射（P0-4：NL 约束抽取）
_ELEMENT_CN_TO_SYMBOL: dict[str, str] = {
    "锂": "Li", "钴": "Co", "镍": "Ni", "锰": "Mn", "钠": "Na",
    "钙": "Ca", "镁": "Mg", "铁": "Fe", "铜": "Cu", "锌": "Zn",
    "铝": "Al", "磷": "P", "硫": "S", "氧": "O", "氮": "N",
    "氟": "F", "氯": "Cl", "溴": "Br", "碘": "I", "氢": "H",
    "碳": "C", "硅": "Si", "锗": "Ge", "钛": "Ti", "钒": "V",
    "铬": "Cr", "钾": "K", "银": "Ag", "钡": "Ba", "锶": "Sr",
    "钇": "Y", "锆": "Zr", "钼": "Mo", "钨": "W", "铅": "Pb", "锡": "Sn",
}

# 属性名（中文/英文）→ 内部属性 key 映射
_PROPERTY_ALIAS_TO_KEY: dict[str, str] = {
    "离子电导率": "ionic_conductivity",
    "ionic_conductivity": "ionic_conductivity",
    "电子电导率": "electronic_conductivity",
    "electronic_conductivity": "electronic_conductivity",
    "带隙": "band_gap",
    "禁带宽度": "band_gap",
    "band_gap": "band_gap",
    "形成能": "formation_energy",
    "formation_energy": "formation_energy",
    "稳定性": "stability",
    "stability": "stability",
    "能量凸包": "energy_above_hull",
    "energy_above_hull": "energy_above_hull",
    "电导率": "ionic_conductivity",  # 默认按离子电导率处理
}

# 属性默认方向
_PROPERTY_DEFAULT_DIRECTION: dict[str, str] = {
    "ionic_conductivity": "maximize",
    "electronic_conductivity": "maximize",
    "band_gap": "maximize",
    "formation_energy": "minimize",
    "stability": "maximize",
    "energy_above_hull": "minimize",
}


# 单个元素匹配模式：中文元素名或英文符号
# 锂使用负向先行断言避免匹配"锂离子"复合词（如"不含钴、锂离子固态电解质"中的锂不应被排除）
_ELEMENT_PATTERN = (
    r"(?:锂(?!离子)|钴|镍|锰|钠|钙|镁|铁|铜|锌|铝|磷|硫|氧|氮|"
    r"氟|氯|溴|碘|氢|碳|硅|锗|钛|钒|铬|钾|银|钡|锶|钇|锆|钼|钨|铅|锡|"
    r"Li|Co|Ni|Mn|Na|Ca|Mg|Fe|Cu|Zn|Al|P|S|O|N|F|Cl|Br|I|H|C|Si|Ge|Ti|V|Cr|K|Ag|Ba|Sr|Y|Zr|Mo|W|Pb|Sn)"
)

# 匹配 "不含X" / "无X" → exclude_elements
# 支持中英文逗号、顿号分隔多个元素，例如 "不含钴、镍" → ["Co", "Ni"]
_RE_EXCLUDE_ELEMENTS = re.compile(
    r"(?:不含|不要|剔除|排除|无)\s*(" + _ELEMENT_PATTERN + r"(?:[、,，\s]+" + _ELEMENT_PATTERN + r")*)"
)

# 匹配 "含X" / "包含X" / "含有X" → require_elements（排除"不含"前缀）
_RE_REQUIRE_ELEMENTS = re.compile(
    r"(?<!不)(?:含|包含|含有|需要)\s*(" + _ELEMENT_PATTERN + r"(?:[、,，\s]+" + _ELEMENT_PATTERN + r")*)"
)

# 匹配 "离子电导率>1e-3" / "离子电导率≥1e-3" / "ionic_conductivity > 1e-3"
# 属性名 + 比较符 + 数值（支持科学计数法）
_RE_PROPERTY_COMPARISON = re.compile(
    r"(离子电导率|电子电导率|带隙|禁带宽度|形成能|稳定性|能量凸包|"
    r"ionic_conductivity|electronic_conductivity|band_gap|formation_energy|stability|energy_above_hull|"
    r"电导率)"
    r"\s*(>=|≤|<=|≥|>|<|≤)\s*"
    r"(\d+(?:\.\d+)?[eE][+-]?\d+|\d+(?:\.\d+)?|\.\d+)"
    r"\s*(?:[Ss]/[cC][mM]|\S)?"
)

# 比较符 → 方向
_COMPARISON_TO_DIRECTION = {
    ">": "min_gt",  # > 表示最小值约束
    "≥": "min_gt",
    ">=": "min_gt",
    "<": "max_lt",  # < 表示最大值约束
    "≤": "max_lt",
    "<=": "max_lt",
}


def _parse_element_list(raw: str) -> list[str]:
    """从原始字符串中提取元素符号列表。

    支持中文名（如"钴、镍"）和英文符号（如"Co, Ni"）混合输入。
    """
    if not raw:
        return []
    # 按常见分隔符切分
    tokens = re.split(r"[、,，\s]+", raw.strip())
    symbols: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        # 中文 → 符号
        if tok in _ELEMENT_CN_TO_SYMBOL:
            sym = _ELEMENT_CN_TO_SYMBOL[tok]
        elif tok.capitalize() in {
            "Li", "Co", "Ni", "Mn", "Na", "Ca", "Mg", "Fe", "Cu", "Zn",
            "Al", "P", "S", "O", "N", "F", "Cl", "Br", "I", "H", "C",
            "Si", "Ge", "Ti", "V", "Cr", "K", "Ag", "Ba", "Sr", "Y",
            "Zr", "Mo", "W", "Pb", "Sn",
        }:
            sym = tok.capitalize()
        else:
            # 单字中文元素名（如"钴"已在上一个分支匹配，这里跳过未知）
            continue
        if sym not in seen:
            seen.add(sym)
            symbols.append(sym)
    return symbols


def _parse_exclude_elements(goal: str) -> list[str]:
    """解析'不含X'类约束 → exclude_elements。"""
    if not goal:
        return []
    symbols: list[str] = []
    seen: set[str] = set()
    for match in _RE_EXCLUDE_ELEMENTS.finditer(goal):
        for sym in _parse_element_list(match.group(1)):
            if sym not in seen:
                seen.add(sym)
                symbols.append(sym)
    return symbols


def _parse_require_elements(goal: str) -> list[str]:
    """解析'含X'类约束 → require_elements（排除'不含'）。"""
    if not goal:
        return []
    symbols: list[str] = []
    seen: set[str] = set()
    for match in _RE_REQUIRE_ELEMENTS.finditer(goal):
        for sym in _parse_element_list(match.group(1)):
            if sym not in seen:
                seen.add(sym)
                symbols.append(sym)
    return symbols


def _parse_target_properties(goal: str) -> list[dict]:
    """解析'X>Y' / 'X<Y' 类约束 → target_properties。"""
    if not goal:
        return []
    results: list[dict] = []
    seen_props: set[str] = set()
    for match in _RE_PROPERTY_COMPARISON.finditer(goal):
        prop_alias = match.group(1)
        op = match.group(2)
        value_str = match.group(3)
        prop_key = _PROPERTY_ALIAS_TO_KEY.get(prop_alias, "")
        if not prop_key:
            continue
        try:
            value = float(value_str)
        except ValueError:
            continue
        direction_kind = _COMPARISON_TO_DIRECTION.get(op, "")
        direction = _PROPERTY_DEFAULT_DIRECTION.get(prop_key, "maximize")
        entry: dict = {
            "property": prop_key,
            "direction": direction,
            "weight": 1.0,
        }
        if direction_kind == "min_gt":
            entry["min"] = value
        elif direction_kind == "max_lt":
            entry["max"] = value
        # 同一属性只保留首次解析结果
        if prop_key in seen_props:
            continue
        seen_props.add(prop_key)
        results.append(entry)
    return results


def _infer_lithium_context(
    goal: str,
    require_elements: list[str],
    exclude_elements: list[str] | None = None,
) -> list[str]:
    """锂电池语境默认推断：检测'锂'/'lithium'/'Li'关键词，未显式指定时默认 require_elements=['Li']。

    P0-4 修复：用户说'固态电解质'/'锂电解质'/'锂电池'/'锂离子'时，应默认要求含 Li 元素。
    若 Li 被显式排除（在 exclude_elements 中），则不应用默认推断。
    """
    if require_elements:
        return require_elements
    if not goal:
        return require_elements
    # Li 被显式排除时不应用 lithium context 默认推断
    if exclude_elements and "Li" in exclude_elements:
        return require_elements
    goal_lower = goal.lower()
    lithium_keywords = ["锂", "lithium", "li"]
    lithium_context_keywords = [
        "固态电解质", "锂电解质", "锂电池", "锂离子", "锂电", "lithium battery",
        "lithium ion", "li-ion", "li battery",
    ]
    has_lithium_keyword = any(kw in goal or kw in goal_lower for kw in lithium_keywords)
    has_context_keyword = any(kw in goal or kw in goal_lower for kw in lithium_context_keywords)
    if has_lithium_keyword or has_context_keyword:
        return ["Li"]
    return require_elements


class IntentInterpreter:
    """从用户目标抽取材料类型、约束、风险和数据缺口。

    纯关键词匹配实现，不依赖 LLM。
    """

    async def interpret(self, goal: str, constraints: dict | None = None) -> dict:
        """解析用户目标。

        Returns:
            {
                "material_scope": MaterialScope,
                "risk_assessment": RiskAssessment,
                "data_gaps": list[str],
                "execution_profile": str,
                "suggested_capabilities": list[str],
                "require_elements": list[str],   # P0-4：必需元素
                "exclude_elements": list[str],   # P0-4：排除元素
                "target_properties": list[dict], # P0-4：从 NL 解析的属性约束
            }
        """
        goal_lower = goal.lower()
        constraints = constraints or {}

        # 1. 材料类型识别
        material_type = ""
        for keywords, mtype in _MATERIAL_KEYWORDS:
            if any(kw in goal or kw in goal_lower for kw in keywords):
                material_type = mtype
                break

        # 2. 风险识别
        requires_dft = "dft" in goal_lower or "高精度" in goal
        requires_experiment = "实验" in goal or "experiment" in goal_lower

        if requires_dft:
            risk_level = "high"
        elif requires_experiment:
            risk_level = "medium"
        else:
            risk_level = "low"

        requires_committee = risk_level == "high"

        # 3. 执行策略
        if risk_level == "high" or requires_dft:
            execution_profile = "committee_governed"
        elif "探索" in goal or "候选" in goal or "设计" in goal:
            execution_profile = "internlm_assisted"
        else:
            execution_profile = "standard"

        # 4. 材料范围
        material_scope = MaterialScope(
            material_type=material_type,
            composition=str(constraints.get("composition", "")),
            structure_constraints=list(constraints.get("structure_constraints", [])),
        )

        # 5. 风险评估
        risk_assessment = RiskAssessment(
            risk_level=risk_level,
            requires_dft=requires_dft,
            requires_experiment=requires_experiment,
            requires_committee=requires_committee,
        )

        # 6. 数据缺口（启发式）
        data_gaps: list[str] = []
        if material_type == "crystal":
            data_gaps.append("crystal_structure_database")
        if material_type in ("polymer", "molecule"):
            data_gaps.append("monomer_structure_library")
        if requires_dft:
            data_gaps.append("dft_computation_resources")
        if requires_experiment:
            data_gaps.append("experiment_facility_availability")

        # 7. 建议能力
        suggested_capabilities: list[str] = []
        if material_type:
            suggested_capabilities.append("material_reference_lookup")
        if material_type in ("molecule", "polymer"):
            suggested_capabilities.append("chemical_descriptors")
        if material_type == "crystal":
            suggested_capabilities.append("property_prediction")
            if requires_dft:
                suggested_capabilities.append("dft_verification")
        if material_type == "polymer":
            suggested_capabilities.append("reaction_engineering_check")
        suggested_capabilities.append("compliance_screening")

        # 8. P0-4：NL 约束抽取——元素包含/排除、属性比较
        exclude_elements = _parse_exclude_elements(goal)
        require_elements = _parse_require_elements(goal)
        # 锂电池语境默认推断（未显式指定 require_elements 时）
        require_elements = _infer_lithium_context(goal, require_elements, exclude_elements)
        # 冲突解决：require 优先于 exclude（同一元素不会同时出现在两边）
        if require_elements and exclude_elements:
            exclude_elements = [e for e in exclude_elements if e not in require_elements]
        target_properties = _parse_target_properties(goal)

        return {
            "material_scope": material_scope,
            "risk_assessment": risk_assessment,
            "data_gaps": data_gaps,
            "execution_profile": execution_profile,
            "suggested_capabilities": suggested_capabilities,
            "require_elements": require_elements,
            "exclude_elements": exclude_elements,
            "target_properties": target_properties,
        }
