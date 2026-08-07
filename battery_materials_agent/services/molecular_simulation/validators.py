"""分子动力学模拟输入验证 — 系统类型、力场、协议、参数范围校验。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── 系统类型定义 ────────────────────────────────────────────

SYSTEM_TYPES: dict[str, dict[str, Any]] = {
    "A": {
        "description": "晶体/无机材料",
        "example": "纯金属、合金、离子氧化物、共价晶体",
        "compatible_forcefields": {"EAM", "Buckingham", "Tersoff", "SW", "ReaxFF"},
        "default_forcefield": "EAM",
        "atom_style": "atomic",
        "units": "metal",
    },
    "B": {
        "description": "有机分子/聚合物",
        "example": "C,H,O,N,S,F,Cl,Br 组成的有机分子",
        "compatible_forcefields": {"OPLS-AA", "ReaxFF", "MMFF94", "UFF"},
        "default_forcefield": "OPLS-AA",
        "atom_style": "full",
        "units": "real",
    },
    "C": {
        "description": "生物分子",
        "example": "蛋白质、核酸、脂质双分子层",
        "compatible_forcefields": {"CHARMM", "AMBER", "OPLS-AA"},
        "default_forcefield": "CHARMM",
        "atom_style": "full",
        "units": "real",
    },
}

# ── 协议定义 ────────────────────────────────────────────────

SUPPORTED_PROTOCOLS: dict[str, dict[str, Any]] = {
    "nvt": {
        "description": "等温等容 (NVT) 系综 — 恒温动力学平衡",
        "requires_temperature": True,
        "requires_pressure": False,
        "typical_timestep_fs": (0.5, 2.0),
    },
    "npt": {
        "description": "等温等压 (NPT) 系综 — 恒温恒压结构平衡",
        "requires_temperature": True,
        "requires_pressure": True,
        "typical_timestep_fs": (0.5, 2.0),
    },
    "nve": {
        "description": "微正则 (NVE) 系综 — 能量守恒产出阶段",
        "requires_temperature": False,
        "requires_pressure": False,
        "typical_timestep_fs": (0.5, 2.0),
    },
    "minimize": {
        "description": "能量最小化 — 结构弛豫",
        "requires_temperature": False,
        "requires_pressure": False,
        "typical_timestep_fs": (0.5, 2.0),
    },
    "npt_nvt": {
        "description": "两步流程: NPT 平衡 → NVT 产出",
        "requires_temperature": True,
        "requires_pressure": True,
        "typical_timestep_fs": (0.5, 2.0),
    },
}

# ── 温度/压力范围 ───────────────────────────────────────────

TEMPERATURE_RANGE_K: tuple[float, float] = (0.1, 10000.0)
PRESSURE_RANGE_ATM: tuple[float, float] = (0.0, 100000.0)

# ── 支持的指标 ──────────────────────────────────────────────

SUPPORTED_METRICS: dict[str, str] = {
    "rdf": "径向分布函数 (Radial Distribution Function)",
    "msd": "均方位移 (Mean Square Displacement)",
    "diffusion_coefficient": "扩散系数",
    "rmsd": "均方根偏差 (Root Mean Square Deviation)",
    "rmsf": "均方根涨落 (Root Mean Square Fluctuation)",
    "energy": "体系能量轨迹",
    "temperature": "温度轨迹",
    "pressure": "压力轨迹",
    "density": "密度轨迹",
    "cna": "共近邻分析 (Common Neighbor Analysis)",
    "angular_distribution": "角分布",
}


# ── 校验函数 ────────────────────────────────────────────────


def validate_system_type(system_type: str) -> dict[str, Any]:
    """校验系统类型是否为 A/B/C 之一。

    Returns:
        dict: 包含 valid、errors、system_info（可选）。
    """
    st = system_type.strip().upper()
    if st not in SYSTEM_TYPES:
        return {
            "valid": False,
            "errors": [f"不支持的 system_type '{system_type}'。必须为 A, B 或 C"],
        }
    return {"valid": True, "errors": [], "system_info": SYSTEM_TYPES[st]}


def validate_forcefield(forcefield: str | None, system_type: str) -> dict[str, Any]:
    """校验力场与系统类型的兼容性。

    Args:
        forcefield: 力场名称；若为 None 则使用系统类型默认力场。
        system_type: 系统类型 (A/B/C)。

    Returns:
        dict: 包含 valid、errors、resolved_forcefield（可选）。
    """
    info = SYSTEM_TYPES.get(system_type)
    if info is None:
        return {"valid": False, "errors": [f"未知系统类型: {system_type}"]}

    compatible = info["compatible_forcefields"]
    resolved = (forcefield or info["default_forcefield"]).strip()

    if resolved not in compatible:
        return {
            "valid": False,
            "errors": [
                f"力场 '{resolved}' 与系统类型 {system_type} 不兼容。"
                f"兼容的力场: {', '.join(sorted(compatible))}"
            ],
        }
    return {"valid": True, "errors": [], "resolved_forcefield": resolved}


def validate_protocol(protocol: str) -> dict[str, Any]:
    """校验协议是否受支持。

    Returns:
        dict: 包含 valid、errors、protocol_info（可选）。
    """
    key = protocol.strip().lower()
    if key not in SUPPORTED_PROTOCOLS:
        return {
            "valid": False,
            "errors": [
                f"不支持的 protocol '{protocol}'。支持: {', '.join(sorted(SUPPORTED_PROTOCOLS))}"
            ],
        }
    return {"valid": True, "errors": [], "protocol_info": SUPPORTED_PROTOCOLS[key]}


def validate_temperature(temperature_k: float | None, required: bool = False) -> dict[str, Any]:
    """校验温度是否在合理范围内。

    Returns:
        dict: 包含 valid、errors、warnings。
    """
    errors: list[str] = []
    warnings: list[str] = []

    if temperature_k is None:
        if required:
            errors.append("该协议需要提供 temperature_k")
        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    if temperature_k <= 0:
        errors.append("temperature_k 必须为正数")
    elif temperature_k < TEMPERATURE_RANGE_K[0] or temperature_k > TEMPERATURE_RANGE_K[1]:
        warnings.append(
            f"温度 {temperature_k} K 超出典型范围 ({TEMPERATURE_RANGE_K[0]}-{TEMPERATURE_RANGE_K[1]} K)"
        )

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate_pressure(pressure_atm: float | None, required: bool = False) -> dict[str, Any]:
    """校验压力是否在合理范围内。

    Returns:
        dict: 包含 valid、errors、warnings。
    """
    errors: list[str] = []
    warnings: list[str] = []

    if pressure_atm is None:
        if required:
            errors.append("该协议需要提供 pressure_atm")
        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    if pressure_atm < 0:
        errors.append("pressure_atm 不能为负数")
    elif pressure_atm < PRESSURE_RANGE_ATM[0] or pressure_atm > PRESSURE_RANGE_ATM[1]:
        warnings.append(
            f"压力 {pressure_atm} atm 超出典型范围 ({PRESSURE_RANGE_ATM[0]}-{PRESSURE_RANGE_ATM[1]} atm)"
        )

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate_metrics(requested_metrics: list[str]) -> dict[str, Any]:
    """校验请求的指标是否受支持。

    Returns:
        dict: 包含 valid、errors、warnings、valid_metrics、unknown_metrics。
    """
    valid: list[str] = []
    unknown: list[str] = []
    for m in requested_metrics:
        key = m.strip().lower()
        if key in SUPPORTED_METRICS:
            valid.append(key)
        else:
            unknown.append(m)

    result: dict[str, Any] = {
        "valid": len(unknown) == 0,
        "errors": [],
        "warnings": [],
        "valid_metrics": valid,
        "unknown_metrics": unknown,
    }
    if unknown:
        result["warnings"].append(f"未知指标: {unknown}")
    return result


# ── 验证器类 ────────────────────────────────────────────────


class MolecularSimulationValidator(BaseModel):
    """分子动力学模拟输入验证器 — 封装完整的输入校验逻辑。"""

    system_type: str = Field(..., description="系统类型: A (晶体/无机), B (有机/聚合物), C (生物分子)")
    structure_data: str = Field(..., description="结构数据: SMILES, CIF 或 data 文件路径")
    forcefield: str | None = Field(default=None, description="力场名称")
    protocol: str = Field(..., description="系综协议: nvt, npt, nve, minimize, npt_nvt")
    temperature_k: float | None = Field(default=None, description="温度 (K)")
    pressure_atm: float | None = Field(default=None, description="压力 (atm)")
    timestep_fs: float = Field(default=1.0, description="时间步长 (fs)")
    run_steps: int = Field(default=100000, description="运行步数")
    requested_metrics: list[str] = Field(default_factory=list, description="请求分析的指标列表")

    def validate_all(self) -> dict[str, Any]:
        """执行完整校验，返回校验结果。"""
        result: dict[str, Any] = {"valid": True, "errors": [], "warnings": []}

        # 1. 校验结构数据非空
        if not self.structure_data or not self.structure_data.strip():
            result["errors"].append("structure_data 不能为空")
            result["valid"] = False
            return result

        # 2. 校验系统类型
        st_result = validate_system_type(self.system_type)
        if not st_result["valid"]:
            result["errors"].extend(st_result["errors"])
            result["valid"] = False
            return result
        result["system_info"] = st_result["system_info"]

        # 3. 校验力场兼容性
        ff_result = validate_forcefield(self.forcefield, self.system_type)
        if not ff_result["valid"]:
            result["errors"].extend(ff_result["errors"])
            result["valid"] = False
        else:
            result["resolved_forcefield"] = ff_result["resolved_forcefield"]

        # 4. 校验协议
        proto_result = validate_protocol(self.protocol)
        if not proto_result["valid"]:
            result["errors"].extend(proto_result["errors"])
            result["valid"] = False
        else:
            proto_info = proto_result["protocol_info"]
            result["protocol_info"] = proto_info

            # 5. 根据协议要求校验温度/压力
            temp_result = validate_temperature(
                self.temperature_k, required=proto_info["requires_temperature"]
            )
            result["errors"].extend(temp_result["errors"])
            result["warnings"].extend(temp_result["warnings"])

            pres_result = validate_pressure(
                self.pressure_atm, required=proto_info["requires_pressure"]
            )
            result["errors"].extend(pres_result["errors"])
            result["warnings"].extend(pres_result["warnings"])

        # 6. 校验时间步长
        if self.timestep_fs <= 0:
            result["errors"].append("timestep_fs 必须为正数")
            result["valid"] = False
        elif self.timestep_fs > 5.0:
            result["warnings"].append(f"时间步长 {self.timestep_fs} fs 偏大，可能影响数值稳定性")

        # 7. 校验运行步数
        if self.run_steps <= 0:
            result["errors"].append("run_steps 必须为正整数")
            result["valid"] = False

        # 8. 校验指标
        if self.requested_metrics:
            metrics_result = validate_metrics(self.requested_metrics)
            result["warnings"].extend(metrics_result["warnings"])
            result["valid_metrics"] = metrics_result["valid_metrics"]

        return result