"""化工过程建模输入校验。"""

from __future__ import annotations

from typing import Any

# 允许的模块标识
VALID_MODULES = frozenset({"M1", "M2", "M3", "M4", "M5", "M6"})

# 每模块允许的计算类型
CALCULATION_TYPES: dict[str, list[str]] = {
    "M1": ["hess", "joback", "dft", "reaction_enthalpy"],
    "M2": ["wilke_chang", "stokes_einstein", "chapman_enskoq"],
    "M3": ["langmuir_hinshelwood", "eyring", "batch_reactor", "pfo_pso"],
    "M4": ["kremser"],
    "M5": ["fenske_underwood_gilliland", "fug"],
    "M6": ["skill_routing", "chem_properties", "dp_yamo", "lammps", "reactnet"],
}

# 模块名称映射
MODULE_NAMES: dict[str, str] = {
    "M1": "反应热与生成焓",
    "M2": "扩散系数",
    "M3": "反应动力学与反应器",
    "M4": "液液萃取",
    "M5": "蒸馏",
    "M6": "技能路由",
}


def validate_module(module: str) -> str | None:
    """验证模块标识。

    Returns:
        错误信息字符串，校验通过返回 None。
    """
    if not module:
        return "模块标识不能为空"
    if module not in VALID_MODULES:
        return f"无效模块 '{module}'，可选: {', '.join(sorted(VALID_MODULES))}"
    return None


def validate_calculation_type(module: str, calculation_type: str) -> str | None:
    """验证计算类型是否匹配模块。

    Returns:
        错误信息字符串，校验通过返回 None。
    """
    if not calculation_type:
        return "计算类型不能为空"
    allowed = CALCULATION_TYPES.get(module, [])
    if not allowed:
        return f"模块 {module} 未定义计算类型"
    if calculation_type not in allowed:
        return (
            f"模块 {module} 不支持计算类型 '{calculation_type}'，"
            f"可选: {', '.join(allowed)}"
        )
    return None


def validate_compounds(compounds: list[dict[str, Any]], module: str) -> list[str]:
    """验证化合物信息。

    Args:
        compounds: 化合物信息列表
        module: 模块标识

    Returns:
        错误信息列表，空列表表示无错误。
    """
    errors: list[str] = []

    if not compounds:
        if module in ("M1", "M2", "M3"):
            errors.append(f"模块 {module} 需要至少一个化合物")
        return errors

    for i, comp in enumerate(compounds):
        if not isinstance(comp, dict):
            errors.append(f"化合物 #{i} 格式错误，应为字典")
            continue
        if not comp.get("name") and not comp.get("smiles") and not comp.get("cas"):
            errors.append(f"化合物 #{i} 缺少名称/SMILES/CAS 标识")

    return errors


def validate_conditions(conditions: dict[str, Any]) -> list[str]:
    """验证操作条件。

    Args:
        conditions: 条件字典

    Returns:
        错误信息列表，空列表表示无错误。
    """
    errors: list[str] = []

    if not conditions:
        return errors

    temperature = conditions.get("temperature_k")
    if temperature is not None:
        if not isinstance(temperature, (int, float)):
            errors.append("temperature_k 必须为数值")
        elif temperature <= 0 or temperature > 10000:
            errors.append(f"温度范围异常: {temperature} K，应在 (0, 10000] 范围内")

    pressure = conditions.get("pressure_pa")
    if pressure is not None:
        if not isinstance(pressure, (int, float)):
            errors.append("pressure_pa 必须为数值")
        elif pressure <= 0 or pressure > 1e9:
            errors.append(f"压力范围异常: {pressure} Pa，应在 (0, 1e9] 范围内")

    composition = conditions.get("composition")
    if composition is not None:
        if not isinstance(composition, list) or len(composition) < 2:
            errors.append("composition 应为至少两个元素的列表")
        elif abs(sum(composition) - 1.0) > 1e-4:
            errors.append(f"composition 摩尔分数之和应为 1.0，当前为 {sum(composition):.6f}")

    return errors


def validate_module_parameters(module: str, parameters: dict[str, Any]) -> list[str]:
    """验证模块专属参数。

    Args:
        module: 模块标识
        parameters: 模块参数

    Returns:
        错误信息列表，空列表表示无错误。
    """
    errors: list[str] = []

    if not parameters:
        return errors

    # M1: 反应热参数
    if module == "M1":
        method = parameters.get("method")
        if method and method not in ("hess", "joback", "dft"):
            errors.append(f"M1 method 不支持 '{method}'，可选: hess, joback, dft")

    # M2: 扩散系数参数
    if module == "M2":
        method = parameters.get("method")
        if method and method not in ("wilke_chang", "stokes_einstein", "chapman_enskoq"):
            errors.append(
                f"M2 method 不支持 '{method}'，"
                f"可选: wilke_chang, stokes_einstein, chapman_enskoq"
            )

    # M3: 反应器参数
    if module == "M3":
        calc_type = parameters.get("calculation_type")
        if calc_type and calc_type not in ("langmuir_hinshelwood", "eyring", "batch_reactor", "pfo_pso"):
            errors.append(
                f"M3 calculation_type 不支持 '{calc_type}'，"
                f"可选: langmuir_hinshelwood, eyring, batch_reactor, pfo_pso"
            )

    # M4: 萃取参数
    if module == "M4":
        if parameters.get("k_value") is not None:
            k = parameters["k_value"]
            if not isinstance(k, (int, float)) or k <= 0:
                errors.append("M4 k_value 必须为正数")

    # M5: 蒸馏参数
    if module == "M5":
        alpha = parameters.get("relative_volatility")
        if alpha is not None and (not isinstance(alpha, (int, float)) or alpha <= 1):
            errors.append("M5 relative_volatility 必须大于 1")

    # M6: 路由参数
    if module == "M6":
        target = parameters.get("routing_target")
        if target and target not in ("chem_properties", "dp_yamo", "lammps", "reactnet"):
            errors.append(
                f"M6 routing_target 不支持 '{target}'，"
                f"可选: chem_properties, dp_yamo, lammps, reactnet"
            )

    return errors


class ProcessModelingValidator:
    """化工过程建模综合校验器。"""

    @staticmethod
    def validate_all(
        module: str,
        calculation_type: str,
        compounds: list[dict[str, Any]],
        conditions: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """全量校验，返回结构化结果。

        Returns:
            dict 包含 validated (bool) 和 errors (list[str])。
        """
        errors: list[str] = []

        # 验证模块
        module_err = validate_module(module)
        if module_err:
            errors.append(module_err)
            return {"validated": False, "errors": errors}

        # 验证计算类型
        type_err = validate_calculation_type(module, calculation_type)
        if type_err:
            errors.append(type_err)

        # 验证化合物
        comp_errors = validate_compounds(compounds, module)
        errors.extend(comp_errors)

        # 验证条件
        cond_errors = validate_conditions(conditions)
        errors.extend(cond_errors)

        # 验证模块参数
        param_errors = validate_module_parameters(module, parameters)
        errors.extend(param_errors)

        return {"validated": len(errors) == 0, "errors": errors}