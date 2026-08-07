"""化学性质查询输入校验。"""

from __future__ import annotations

import re
from typing import Any

# 允许的模块标识
VALID_MODULES = frozenset({"M1", "M2", "M3", "M4", "M5"})

# 模块名称映射
MODULE_NAMES: dict[str, str] = {
    "M1": "标准常数",
    "M2": "T/P 依赖性质",
    "M3": "气液平衡 (VLE)",
    "M4": "闪蒸计算",
    "M5": "溶解度",
}

# 化合物名称基本格式（允许字母、数字、括号、连字符、斜杠、空格）
_COMPOUND_PATTERN = re.compile(r"^[A-Za-z0-9\u0370-\u03ff\u0400-\u04ff()\[\]\-/,.\s]+$")


def validate_compound_name(name: str) -> str | None:
    """验证化合物名称 / SMILES / CAS。

    Returns:
        错误信息字符串，校验通过返回 None。
    """
    if not name or not name.strip():
        return "化合物名称不能为空"
    stripped = name.strip()
    if len(stripped) > 200:
        return "化合物名称过长（最多 200 字符）"
    if not _COMPOUND_PATTERN.match(stripped):
        return "化合物名称包含不支持的字符"
    return None


def validate_module_parameters(
    module: str,
    temperature_k: float | None = None,
    pressure_pa: float | None = None,
    composition: list[float] | None = None,
) -> list[str]:
    """校验模块参数。

    Args:
        module: 模块标识 (M1-M5)
        temperature_k: 温度 (K)
        pressure_pa: 压力 (Pa)
        composition: 摩尔分数列表

    Returns:
        错误信息列表，空列表表示无错误。
    """
    errors: list[str] = []

    if module not in VALID_MODULES:
        errors.append(f"无效模块 '{module}'，可选: {', '.join(sorted(VALID_MODULES))}")
        return errors

    # M1 不需要额外参数
    if module == "M1":
        return errors

    # M2 需要温度或压力
    if module == "M2":
        if temperature_k is None and pressure_pa is None:
            errors.append("M2 (T/P 依赖性质) 需要 temperature_k 或 pressure_pa")
        if temperature_k is not None and (temperature_k <= 0 or temperature_k > 10000):
            errors.append(f"温度范围异常: {temperature_k} K，应在 (0, 10000] 范围内")
        if pressure_pa is not None and (pressure_pa <= 0 or pressure_pa > 1e9):
            errors.append(f"压力范围异常: {pressure_pa} Pa，应在 (0, 1e9] 范围内")

    # M3 需要 composition
    if module == "M3":
        if not composition or len(composition) < 2:
            errors.append("M3 (VLE) 需要至少两组分的 composition")
        elif abs(sum(composition) - 1.0) > 1e-4:
            errors.append(f"composition 摩尔分数之和应为 1.0，当前为 {sum(composition):.6f}")

    # M4 需要温度、压力和 composition
    if module == "M4":
        if temperature_k is None:
            errors.append("M4 (闪蒸) 需要 temperature_k")
        if pressure_pa is None:
            errors.append("M4 (闪蒸) 需要 pressure_pa")
        if not composition or len(composition) < 2:
            errors.append("M4 (闪蒸) 需要至少两组分的 composition")
        elif abs(sum(composition) - 1.0) > 1e-4:
            errors.append(f"composition 摩尔分数之和应为 1.0，当前为 {sum(composition):.6f}")

    # M5 不需要额外参数（溶解度由化合物名称决定）
    if module == "M5":
        pass

    return errors


class ChemicalPropertyValidator:
    """化学性质查询综合校验器。"""

    @staticmethod
    def validate_all(
        compound_name: str,
        module: str,
        temperature_k: float | None = None,
        pressure_pa: float | None = None,
        composition: list[float] | None = None,
    ) -> dict[str, Any]:
        """全量校验，返回结构化结果。

        Returns:
            dict 包含 validated (bool) 和 errors (list[str])。
        """
        errors: list[str] = []

        name_err = validate_compound_name(compound_name)
        if name_err:
            errors.append(name_err)

        if module not in VALID_MODULES:
            errors.append(f"无效模块 '{module}'，可选: {', '.join(sorted(VALID_MODULES))}")
        else:
            param_errors = validate_module_parameters(module, temperature_k, pressure_pa, composition)
            errors.extend(param_errors)

        return {"validated": len(errors) == 0, "errors": errors}