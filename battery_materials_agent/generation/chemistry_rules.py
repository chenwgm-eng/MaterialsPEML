"""化学规则引擎 — 候选生成阶段的硬性化学约束过滤。

Task 15（阶段 3：AI 可信度加固）将 Task 4 建立的 ``require_elements`` /
``exclude_elements`` 基础抽离为可配置的硬规则引擎，统一在候选生成阶段执行：
元素包含/排除、元素种类数上限、结构类型白名单等。

设计要点：
- 规则引擎只做**硬过滤**：违反任一规则的候选直接剔除，不进入多目标评分。
- 委员会（``committee/adapters/crystal.py``）做**软评分**：对存活候选做结构、
  对称性、新颖性等评估。二者形成"硬过滤 + 软评分"的两段式管线。
- 元素解析复用 :func:`formula_validator.parse_formula_elements`，支持嵌套括号
  （``Na2CaMg(SO4)3``）与小数系数（``LiNi0.8Mn0.1Co0.1O2``）。
- 不引入新的重量级依赖（pymatgen 仍为可选回退，正则解析为默认实现）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .formula_validator import parse_formula_elements


@dataclass
class ChemistryRuleSet:
    """化学规则集合。

    所有字段均可为空（默认空规则集），空规则集等价于"不做硬过滤"。

    Attributes:
        required_elements: 必须包含的元素符号列表（如 ``["Li"]``）。
            候选缺少任一必需元素即判失败。
        forbidden_elements: 必须排除的元素符号列表（如 ``["Co"]``）。
            候选包含任一禁含元素即判失败。
        max_elements_count: 最大元素种类数上限。候选元素种类数超过此值即判失败。
        required_structure_types: 结构类型白名单（如 ``["Layered", "Spinel"]``）。
            候选 ``structure_type`` 不在白名单内即判失败；``structure_type`` 为空时跳过该项。
    """

    required_elements: list[str] = field(default_factory=list)
    forbidden_elements: list[str] = field(default_factory=list)
    max_elements_count: int | None = None
    required_structure_types: list[str] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "ChemistryRuleSet":
        """构造空规则集（不做任何过滤）。"""
        return cls()

    def is_empty(self) -> bool:
        """是否为空规则集（所有规则字段都未配置）。"""
        return (
            not self.required_elements
            and not self.forbidden_elements
            and self.max_elements_count is None
            and not self.required_structure_types
        )

    def validate(
        self,
        formula: str,
        structure_type: str | None = None,
    ) -> tuple[bool, list[str]]:
        """对单个候选执行硬性化学约束校验。

        Args:
            formula: 候选化学式（如 ``"LiCoO2"``、``"Na2CaMg(SO4)3"``）。
            structure_type: 候选结构类型（如 ``"Layered"``），可选。

        Returns:
            ``(passed, reasons)``：``passed`` 为 ``True`` 时 ``reasons`` 为空列表；
            ``passed`` 为 ``False`` 时 ``reasons`` 列出每条违反原因。
        """
        reasons: list[str] = []
        elements = parse_formula_elements(formula)

        # required_elements：缺少任一必需元素即失败
        for el in self.required_elements:
            if el.capitalize() not in elements:
                reasons.append(f"missing required element: {el}")

        # forbidden_elements：包含任一禁含元素即失败
        for el in self.forbidden_elements:
            if el.capitalize() in elements:
                reasons.append(f"contains forbidden element: {el}")

        # max_elements_count：元素种类数超过上限即失败
        if self.max_elements_count is not None and len(elements) > self.max_elements_count:
            reasons.append(
                f"too many elements: {len(elements)} > {self.max_elements_count}"
            )

        # required_structure_types：结构类型不在白名单即失败
        # （structure_type 为空时跳过，避免误伤本地库未标注结构类型的候选）
        if self.required_structure_types and structure_type:
            if structure_type not in self.required_structure_types:
                reasons.append(
                    f"structure type '{structure_type}' not in allowed: "
                    f"{self.required_structure_types}"
                )

        return (len(reasons) == 0, reasons)

    def filter_candidates(
        self,
        candidates: list,
    ) -> tuple[list, list]:
        """批量过滤候选，返回 ``(passed, filtered_out_pairs)``。

        ``candidates`` 中每个元素需支持 ``.formula`` 与 ``.structure_type`` 属性
        （``CrystalCandidate`` 即满足），或为带 ``formula`` / ``structure_type``
        键的 dict。

        Args:
            candidates: 待过滤的候选列表。

        Returns:
            ``(passed, filtered_out_pairs)``：
            - ``passed``：通过规则引擎的候选（保持原对象类型不变）
            - ``filtered_out_pairs``：被剔除的候选列表，每个元素为
              ``(candidate, reasons)`` 元组，``reasons`` 为违反原因列表。
              不修改原候选对象（避免对 Pydantic BaseModel 等不可变对象 setattr 失败）。
        """
        if self.is_empty():
            return list(candidates), []

        passed: list = []
        filtered_out_pairs: list[tuple] = []
        for c in candidates:
            formula, structure_type = _extract_candidate_fields(c)
            ok, reasons = self.validate(formula, structure_type)
            if ok:
                passed.append(c)
            else:
                filtered_out_pairs.append((c, reasons))
        return passed, filtered_out_pairs


def _extract_candidate_fields(candidate) -> tuple[str, str | None]:
    """从候选对象中提取 ``formula`` 与 ``structure_type``。

    同时支持 dict 与具备属性的对象。返回 ``(formula, structure_type)``。
    """
    if isinstance(candidate, dict):
        return (
            str(candidate.get("formula", "") or ""),
            candidate.get("structure_type"),
        )
    return (
        getattr(candidate, "formula", "") or "",
        getattr(candidate, "structure_type", None),
    )
