"""MPA 输入验证 — SMILES 合法性检查与属性键校验。"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

# ── 属性目录 ────────────────────────────────────────────────
# 42 种分子物理化学性质，每种包含 描述 / 单位 / 典型范围

PROPERTY_CATALOG: dict[str, dict[str, Any]] = {
    "BP_K": {"description": "常压沸点", "unit": "K", "typical_range": (50, 1000)},
    "fusion_T_K": {"description": "熔点", "unit": "K", "typical_range": (50, 800)},
    "flash_point_K": {"description": "闪点", "unit": "K", "typical_range": (100, 800)},
    "density_liq_298K_gcm3": {"description": "液体密度 (298K)", "unit": "g/cm³", "typical_range": (0.5, 5.0)},
    "logP": {"description": "正辛醇/水分配系数", "unit": "log10", "typical_range": (-10, 20)},
    "logD": {"description": "分布系数 (pH 7.4)", "unit": "log10", "typical_range": (-10, 20)},
    "MW": {"description": "分子量", "unit": "g/mol", "typical_range": (1, 2000)},
    "T_c_K": {"description": "临界温度", "unit": "K", "typical_range": (100, 1500)},
    "P_c_bar": {"description": "临界压力", "unit": "bar", "typical_range": (5, 200)},
    "V_c_cm3mol": {"description": "临界体积", "unit": "cm³/mol", "typical_range": (30, 2000)},
    "omega": {"description": "偏心因子", "unit": "无量纲", "typical_range": (-0.5, 2.0)},
    "Z_c": {"description": "临界压缩因子", "unit": "无量纲", "typical_range": (0.15, 0.35)},
    "HVAP_298K_Jmol": {"description": "汽化焓 (298K)", "unit": "J/mol", "typical_range": (5000, 150000)},
    "S_298K": {"description": "标准熵 (298K)", "unit": "J/(mol·K)", "typical_range": (50, 1000)},
    "Cp_298K_JmolK": {"description": "液体定压热容 (298K)", "unit": "J/(mol·K)", "typical_range": (30, 800)},
    "Cp_gas_298K_JmolK": {"description": "气体定压热容 (298K)", "unit": "J/(mol·K)", "typical_range": (20, 500)},
    "G_f_gas_kJmol": {"description": "气体标准生成吉布斯自由能", "unit": "kJ/mol", "typical_range": (-500, 500)},
    "H_f_gas_kJmol": {"description": "气体标准生成焓", "unit": "kJ/mol", "typical_range": (-500, 500)},
    "H_f_liq_kJmol": {"description": "液体标准生成焓", "unit": "kJ/mol", "typical_range": (-500, 500)},
    "H_comb_kJmol": {"description": "燃烧焓", "unit": "kJ/mol", "typical_range": (-10000, 0)},
    "surface_tension_mNm": {"description": "表面张力", "unit": "mN/m", "typical_range": (5, 80)},
    "refractive_index": {"description": "折射率", "unit": "无量纲", "typical_range": (1.0, 2.5)},
    "dielectric_constant": {"description": "介电常数", "unit": "无量纲", "typical_range": (1, 100)},
    "dipole_moment_D": {"description": "偶极矩", "unit": "Debye", "typical_range": (0, 15)},
    "viscosity_Pas": {"description": "粘度", "unit": "Pa·s", "typical_range": (1e-5, 1e3)},
    "thermal_conductivity_WmK": {"description": "热导率", "unit": "W/(m·K)", "typical_range": (0.01, 1.0)},
    "LFL": {"description": "爆炸下限", "unit": "vol%", "typical_range": (0.1, 20)},
    "UFL": {"description": "爆炸上限", "unit": "vol%", "typical_range": (1, 100)},
    "T_autoignition_K": {"description": "自燃温度", "unit": "K", "typical_range": (400, 1000)},
    "water_solubility_gL": {"description": "水溶性", "unit": "g/L", "typical_range": (0, 2000)},
    "henry_const_atm": {"description": "亨利常数", "unit": "atm", "typical_range": (1e-10, 1e5)},
    "vapor_pressure_298K_Pa": {"description": "蒸气压 (298K)", "unit": "Pa", "typical_range": (1e-10, 1e6)},
    "pKa": {"description": "酸解离常数", "unit": "log10", "typical_range": (-10, 50)},
    "pKb": {"description": "碱解离常数", "unit": "log10", "typical_range": (-10, 50)},
    "logS": {"description": "水溶性对数", "unit": "log10(mol/L)", "typical_range": (-15, 5)},
    "polarizability_A3": {"description": "极化率", "unit": "Å³", "typical_range": (1, 100)},
    "HOMO_ev": {"description": "最高占据分子轨道能级", "unit": "eV", "typical_range": (-20, 0)},
    "LUMO_ev": {"description": "最低未占分子轨道能级", "unit": "eV", "typical_range": (-10, 10)},
    "band_gap_ev": {"description": "带隙", "unit": "eV", "typical_range": (0, 15)},
    "heavy_atom_count": {"description": "重原子数", "unit": "计数", "typical_range": (1, 200)},
    "rotatable_bond_count": {"description": "可旋转键数", "unit": "计数", "typical_range": (0, 100)},
    "h_bond_acceptors": {"description": "氢键受体数", "unit": "计数", "typical_range": (0, 50)},
    "h_bond_donors": {"description": "氢键供体数", "unit": "计数", "typical_range": (0, 50)},
}

KNOWN_PROPERTY_KEYS: set[str] = set(PROPERTY_CATALOG.keys())

# 简易 SMILES 正则（非 RDKit 时的兜底检查）
_SMILES_PATTERN = re.compile(r"^[A-Za-z0-9@+\-\[\](){}#%=.$\\/|~:&*!,_]+$")


def validate_smiles(smiles_list: list[str]) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """验证 SMILES 字符串列表。

    返回 (valid, invalid) 两个列表，每个元素为 (index, smiles)。
    优先尝试 RDKit；若不可用则使用正则模式兜底。
    """
    valid: list[tuple[int, str]] = []
    invalid: list[tuple[int, str]] = []

    try:
        from rdkit import Chem  # type: ignore[import-untyped]

        for i, smi in enumerate(smiles_list):
            mol = Chem.MolFromSmiles(smi)
            if mol is not None:
                valid.append((i, smi))
            else:
                invalid.append((i, smi))
    except ImportError:
        # RDKit 不可用，使用正则兜底
        for i, smi in enumerate(smiles_list):
            if _SMILES_PATTERN.match(smi):
                valid.append((i, smi))
            else:
                invalid.append((i, smi))

    return valid, invalid


def validate_property_keys(keys: list[str]) -> tuple[list[str], list[str]]:
    """检查属性键是否在已知的 42 种性质中。

    返回 (valid_keys, unknown_keys)。
    """
    valid_keys: list[str] = []
    unknown_keys: list[str] = []
    for k in keys:
        if k in KNOWN_PROPERTY_KEYS:
            valid_keys.append(k)
        else:
            unknown_keys.append(k)
    return valid_keys, unknown_keys


class MPAInputValidator(BaseModel):
    """MPA 输入验证器 — 封装完整的输入校验逻辑。"""

    smiles_list: list[str] = Field(..., description="SMILES 字符串列表")
    property_keys: list[str] = Field(default_factory=lambda: list(KNOWN_PROPERTY_KEYS))
    conditions: dict[str, Any] = Field(default_factory=dict)

    def validate_all(self) -> dict[str, Any]:
        """执行完整校验，返回校验结果。"""
        result: dict[str, Any] = {"valid": True, "errors": [], "warnings": []}

        # 1. 检查 SMILES 列表非空
        if not self.smiles_list:
            result["valid"] = False
            result["errors"].append("SMILES 列表为空")
            return result

        # 2. 验证 SMILES
        valid_smiles, invalid_smiles = validate_smiles(self.smiles_list)
        if invalid_smiles:
            indices = [idx for idx, _ in invalid_smiles]
            result["warnings"].append(f"以下索引的 SMILES 无效: {indices}")
            if not valid_smiles:
                result["valid"] = False
                result["errors"].append("所有 SMILES 均无效")

        result["valid_smiles"] = [smi for _, smi in valid_smiles]
        result["invalid_smiles"] = [smi for _, smi in invalid_smiles]

        # 3. 验证属性键
        valid_keys, unknown_keys = validate_property_keys(self.property_keys)
        if unknown_keys:
            result["warnings"].append(f"未知属性键: {unknown_keys}")
        if not valid_keys:
            result["valid"] = False
            result["errors"].append("未指定有效的属性键")

        result["valid_property_keys"] = valid_keys

        # 4. 检查 conditions 中的温度/压力范围（如果提供）
        temp = self.conditions.get("temperature")
        pres = self.conditions.get("pressure")
        if temp is not None and not (50 <= temp <= 2000):
            result["warnings"].append(f"温度 {temp} K 超出典型范围 (50-2000 K)")
        if pres is not None and not (0.01 <= pres <= 1000):
            result["warnings"].append(f"压力 {pres} bar 超出典型范围 (0.01-1000 bar)")

        return result