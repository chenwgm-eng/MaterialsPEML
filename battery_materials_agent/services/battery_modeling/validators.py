"""电池建模输入验证 — 轨道/模型/参数集/协议的合法性校验。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── 常量定义 ──────────────────────────────────────────────────────────────

VALID_TRACKS: frozenset[str] = frozenset({"p2d", "ecm", "pybop"})

TRACK_NAMES: dict[str, str] = {
    "p2d": "P2D/DFN 机理模型",
    "ecm": "等效电路模型 (Thevenin)",
    "pybop": "PyBOP 参数辨识",
}

# 各轨道允许的模型类型
VALID_MODEL_TYPES: dict[str, list[str]] = {
    "p2d": ["SPM", "SPMe", "DFN"],
    "ecm": ["Thevenin", "PNGV", "RC"],
    "pybop": ["parameter_identification"],
}

# 支持的参数集
VALID_PARAMETER_SETS: dict[str, dict[str, Any]] = {
    "Chen2020": {
        "description": "NMC811/石墨 LG M50 21700 (5Ah)",
        "chemistry": "NMC811-Graphite",
        "use_case": "默认通用基线",
    },
    "Chen2020_composite": {
        "description": "NMC811/石墨+Si 复合负极",
        "chemistry": "NMC811-Graphite_Si",
        "use_case": "Si-C 复合负极",
    },
    "OKane2022": {
        "description": "NMC811/石墨 LG M50 (降解研究)",
        "chemistry": "NMC811-Graphite",
        "use_case": "降解研究 (SEI/镀锂/裂纹)",
    },
    "Prada2013": {
        "description": "LFP/石墨 A123 26650 (2.3Ah)",
        "chemistry": "LFP-Graphite",
        "use_case": "LFP 化学",
    },
    "OKane2022_graphite_SiOx_halfcell": {
        "description": "石墨+SiOx 半电池",
        "chemistry": "Graphite_SiOx-HalfCell",
        "use_case": "SiOx 负极降解",
    },
}

# 热选项
VALID_THERMAL_OPTIONS: frozenset[str] = frozenset({"isothermal", "lumped", "x-full"})

# 常见请求变量
KNOWN_VARIABLES: dict[str, str] = {
    "Terminal voltage [V]": "端电压",
    "Current [A]": "电流",
    "Discharge capacity [A.h]": "放电容量",
    "Charge capacity [A.h]": "充电容量",
    "Cell temperature [K]": "电池温度",
    "X-averaged cell temperature [K]": "X-平均电池温度",
    "Electrolyte concentration [mol.m-3]": "电解液浓度",
    "Negative electrode potential [V]": "负极电位",
    "Positive electrode potential [V]": "正极电位",
    "Total lithium concentration [mol.m-3]": "总锂浓度",
}


def validate_track(track: str) -> str | None:
    """验证轨道标识。

    Returns:
        错误信息字符串，校验通过返回 None。
    """
    if not track:
        return "轨道标识不能为空"
    if track not in VALID_TRACKS:
        return f"无效轨道 '{track}'，可选: {', '.join(sorted(VALID_TRACKS))}"
    return None


def validate_model_type(track: str, model_type: str) -> str | None:
    """验证模型类型是否匹配轨道。

    Returns:
        错误信息字符串，校验通过返回 None。
    """
    if not model_type:
        return "模型类型不能为空"
    allowed = VALID_MODEL_TYPES.get(track, [])
    if not allowed:
        return f"轨道 '{track}' 不支持模型类型"
    if model_type not in allowed:
        return f"轨道 '{track}' 不支持的模型类型 '{model_type}'，可选: {allowed}"
    return None


def validate_parameter_set(parameter_set: str) -> str | None:
    """验证参数集是否在已知列表中。

    Returns:
        错误信息字符串，校验通过返回 None。
    """
    if not parameter_set:
        return "参数集名称不能为空"
    if parameter_set not in VALID_PARAMETER_SETS:
        return (
            f"未知参数集 '{parameter_set}'，可选: "
            f"{', '.join(sorted(VALID_PARAMETER_SETS.keys()))}"
        )
    return None


def validate_experiment_protocol(protocol: list[dict]) -> list[str]:
    """验证实验协议步骤列表。

    每个步骤应包含 'type' 字段（如 'charge', 'discharge', 'rest', 'hold'），
    以及对应的参数（如 'current', 'voltage', 'duration' 等）。

    Returns:
        错误信息列表，空列表表示无错误。
    """
    errors: list[str] = []
    if not protocol:
        # 空协议是允许的 — 使用默认 CCCV 协议
        return errors

    valid_step_types = {"charge", "discharge", "rest", "hold", "cccv_cycle"}
    for i, step in enumerate(protocol):
        if not isinstance(step, dict):
            errors.append(f"步骤 {i}: 必须为 dict 类型")
            continue
        step_type = step.get("type", "")
        if not step_type:
            errors.append(f"步骤 {i}: 缺少 'type' 字段")
        elif step_type not in valid_step_types:
            errors.append(
                f"步骤 {i}: 无效步骤类型 '{step_type}'，"
                f"可选: {', '.join(sorted(valid_step_types))}"
            )

    return errors


def validate_thermal_option(thermal_option: str) -> str | None:
    """验证热选项。

    Returns:
        错误信息字符串，校验通过返回 None。
    """
    if thermal_option not in VALID_THERMAL_OPTIONS:
        return (
            f"无效热选项 '{thermal_option}'，"
            f"可选: {', '.join(sorted(VALID_THERMAL_OPTIONS))}"
        )
    return None


def validate_requested_variables(variables: list[str]) -> list[str]:
    """验证请求的变量列表。

    Returns:
        未知变量名称列表，空列表表示全部已知。
    """
    unknown: list[str] = []
    for v in variables:
        if v not in KNOWN_VARIABLES:
            unknown.append(v)
    return unknown


class BatteryModelingValidator(BaseModel):
    """电池建模输入验证器 — 封装完整的输入校验逻辑。"""

    track: str = Field(..., description="仿真轨道")
    model_type: str = Field(default="DFN")
    parameter_set: str = Field(default="Chen2020")
    experiment_protocol: list[dict] = Field(default_factory=list)
    thermal_option: str = Field(default="isothermal")
    requested_variables: list[str] = Field(
        default_factory=lambda: ["Terminal voltage [V]", "Current [A]"],
    )

    def validate_all(self) -> dict[str, Any]:
        """执行完整校验，返回校验结果。"""
        result: dict[str, Any] = {"valid": True, "errors": [], "warnings": []}

        # 1. 验证轨道
        track_err = validate_track(self.track)
        if track_err:
            result["valid"] = False
            result["errors"].append(track_err)
            return result  # 轨道无效则后续校验无意义

        # 2. 验证模型类型
        model_err = validate_model_type(self.track, self.model_type)
        if model_err:
            result["valid"] = False
            result["errors"].append(model_err)

        # 3. 验证参数集
        param_err = validate_parameter_set(self.parameter_set)
        if param_err:
            result["warnings"].append(param_err)

        # 4. 验证实验协议
        protocol_errors = validate_experiment_protocol(self.experiment_protocol)
        if protocol_errors:
            result["errors"].extend(protocol_errors)
            result["valid"] = False

        # 5. 验证热选项
        thermal_err = validate_thermal_option(self.thermal_option)
        if thermal_err:
            result["warnings"].append(thermal_err)

        # 6. 验证请求变量
        unknown_vars = validate_requested_variables(self.requested_variables)
        if unknown_vars:
            result["warnings"].append(f"未知变量: {unknown_vars}")

        return result