"""配方与堆积输入验证 — 校验配方组分定义和堆积参数。"""

from __future__ import annotations

from typing import Any


def validate_formulation_components(components: list[dict]) -> dict[str, Any]:
    """校验配方组分定义列表。

    每个组分必须包含 name、smiles、ratio_range_min、ratio_range_max。
    ratio_range 必须满足 0 <= min <= max <= 1。
    """
    errors: list[str] = []
    if not components:
        errors.append("组分列表不能为空")
        return {"valid": False, "errors": errors}

    for i, comp in enumerate(components):
        prefix = f"组分[{i}]"
        if "name" not in comp or not comp["name"]:
            errors.append(f"{prefix}: 缺少 name 字段")
        if "smiles" not in comp or not comp["smiles"]:
            errors.append(f"{prefix}: 缺少 smiles 字段")

        r_min = comp.get("ratio_range_min")
        r_max = comp.get("ratio_range_max")
        if r_min is None or r_max is None:
            errors.append(f"{prefix}: 缺少 ratio_range_min 或 ratio_range_max")
        elif not (0.0 <= r_min <= r_max <= 1.0):
            errors.append(f"{prefix}: ratio_range 必须满足 0 <= min <= max <= 1")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_packing_parameters(params: dict) -> dict[str, Any]:
    """校验堆积参数。

    支持的 packing_type: crystal, amorphous, solvation。
    若提供 target_density 或 box_size_nm，必须为正数。
    """
    errors: list[str] = []
    valid_types = {"crystal", "amorphous", "solvation"}

    packing_type = params.get("packing_type")
    if not packing_type:
        errors.append("packing_type 不能为空")
    elif packing_type not in valid_types:
        errors.append(f"packing_type 必须是 {valid_types} 之一，收到: {packing_type}")

    molecules = params.get("molecules", [])
    if not molecules:
        errors.append("molecules 列表不能为空")

    target_density = params.get("target_density")
    if target_density is not None and target_density <= 0:
        errors.append("target_density 必须为正数")

    box_size_nm = params.get("box_size_nm")
    if box_size_nm is not None and box_size_nm <= 0:
        errors.append("box_size_nm 必须为正数")

    return {"valid": len(errors) == 0, "errors": errors}


class FormulationValidator:
    """配方与堆积参数校验器。"""

    @staticmethod
    def validate_components(components: list[dict]) -> dict[str, Any]:
        """校验组分定义。"""
        return validate_formulation_components(components)

    @staticmethod
    def validate_packing(params: dict) -> dict[str, Any]:
        """校验堆积参数。"""
        return validate_packing_parameters(params)

    @staticmethod
    def validate_optimization_goal(goal: str) -> dict[str, Any]:
        """校验优化目标。"""
        valid_goals = {"maximize", "minimize", "target"}
        if goal not in valid_goals:
            return {
                "valid": False,
                "errors": [f"optimization_goal 必须是 {valid_goals} 之一，收到: {goal}"],
            }
        return {"valid": True, "errors": []}