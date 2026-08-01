"""Battery cycle benchmark database (template-based, no external data source)."""
from __future__ import annotations

import math


def _build_curve(initial_capacity: float, decay_rate: float, cycle_count: int,
                 sample_points: int = 21) -> list[dict]:
    """根据初始容量与衰减率生成容量保持率曲线（采样 sample_points 个点）。

    模型：C(n) = initial_capacity * exp(-decay_rate * n)
    数据来源标注为"基准数据库"。
    """
    if cycle_count <= 0 or sample_points < 2:
        return [{"cycle": 0, "capacity_retention": round(initial_capacity, 2)}]
    curve: list[dict] = []
    step = cycle_count / (sample_points - 1)
    for i in range(sample_points):
        cyc = round(step * i, 1)
        cap = initial_capacity * math.exp(-decay_rate * cyc)
        curve.append({"cycle": cyc, "capacity_retention": round(cap, 2)})
    return curve


# 基准材料定义：初始容量保持率（%）与衰减率（/循环）参考典型文献量级
_RAW_MATERIALS: list[dict] = [
    {
        "formula": "LiCoO2",
        "name": "钴酸锂",
        "cathode": "LiCoO2",
        "anode": "石墨",
        "material_type": "cathode",
        "cycle_count": 500,
        "temperature": 25,
        "initial_capacity": 100.0,
        "decay_rate": 0.0008,
    },
    {
        "formula": "LiFePO4",
        "name": "磷酸铁锂",
        "cathode": "LiFePO4",
        "anode": "石墨",
        "material_type": "cathode",
        "cycle_count": 2000,
        "temperature": 25,
        "initial_capacity": 100.0,
        "decay_rate": 0.0002,
    },
    {
        "formula": "LiNi1/3Mn1/3Co1/3O2",
        "name": "三元 NMC111",
        "cathode": "NMC111",
        "anode": "石墨",
        "material_type": "cathode",
        "cycle_count": 1000,
        "temperature": 25,
        "initial_capacity": 100.0,
        "decay_rate": 0.0005,
    },
    {
        "formula": "LiNi0.8Co0.15Al0.05O2",
        "name": "镍钴铝 NCA",
        "cathode": "NCA",
        "anode": "石墨",
        "material_type": "cathode",
        "cycle_count": 800,
        "temperature": 25,
        "initial_capacity": 100.0,
        "decay_rate": 0.0007,
    },
    {
        "formula": "LiMn2O4",
        "name": "锰酸锂",
        "cathode": "LiMn2O4",
        "anode": "石墨",
        "material_type": "cathode",
        "cycle_count": 500,
        "temperature": 25,
        "initial_capacity": 100.0,
        "decay_rate": 0.0012,
    },
    {
        "formula": "LiNi0.5Mn0.3Co0.2O2",
        "name": "三元 NMC532",
        "cathode": "NMC532",
        "anode": "石墨",
        "material_type": "cathode",
        "cycle_count": 1000,
        "temperature": 25,
        "initial_capacity": 100.0,
        "decay_rate": 0.0006,
    },
    {
        "formula": "LiNi0.8Mn0.1Co0.1O2",
        "name": "高镍 NMC811",
        "cathode": "NMC811",
        "anode": "石墨",
        "material_type": "cathode",
        "cycle_count": 800,
        "temperature": 25,
        "initial_capacity": 100.0,
        "decay_rate": 0.0009,
    },
    {
        "formula": "LiNi0.6Mn0.2Co0.2O2",
        "name": "三元 NMC622",
        "cathode": "NMC622",
        "anode": "石墨",
        "material_type": "cathode",
        "cycle_count": 1000,
        "temperature": 25,
        "initial_capacity": 100.0,
        "decay_rate": 0.0007,
    },
    {
        "formula": "Li4Ti5O12",
        "name": "钛酸锂",
        "cathode": "NMC",
        "anode": "Li4Ti5O12",
        "material_type": "anode",
        "cycle_count": 3000,
        "temperature": 25,
        "initial_capacity": 100.0,
        "decay_rate": 0.0001,
    },
    {
        "formula": "Li2MnO3",
        "name": "富锂锰基",
        "cathode": "Li2MnO3",
        "anode": "石墨",
        "material_type": "cathode",
        "cycle_count": 500,
        "temperature": 25,
        "initial_capacity": 100.0,
        "decay_rate": 0.0015,
    },
    {
        "formula": "Na3V2(PO4)3",
        "name": "钠离子正极",
        "cathode": "Na3V2(PO4)3",
        "anode": "硬碳",
        "material_type": "cathode",
        "cycle_count": 1000,
        "temperature": 25,
        "initial_capacity": 100.0,
        "decay_rate": 0.0006,
    },
    {
        "formula": "Li2FeSiO4",
        "name": "硅酸铁锂",
        "cathode": "Li2FeSiO4",
        "anode": "石墨",
        "material_type": "cathode",
        "cycle_count": 800,
        "temperature": 25,
        "initial_capacity": 100.0,
        "decay_rate": 0.0010,
    },
]


class BatteryCycleDatabase:
    """电池循环基准数据库：预置常见正负极材料的循环基准数据。

    数据来源标注为"基准数据库"，提供按化学式查询、列举全部、按类型检索等接口。
    """

    DATA_SOURCE = "基准数据库"

    def __init__(self) -> None:
        self._materials: list[dict] = [self._normalize(m) for m in _RAW_MATERIALS]

    @staticmethod
    def _normalize(raw: dict) -> dict:
        """填充 capacity_retention_curve 与数据来源字段，返回完整材料记录。"""
        curve = _build_curve(
            initial_capacity=raw["initial_capacity"],
            decay_rate=raw["decay_rate"],
            cycle_count=raw["cycle_count"],
        )
        return {
            "formula": raw["formula"],
            "name": raw["name"],
            "cathode": raw["cathode"],
            "anode": raw["anode"],
            "material_type": raw["material_type"],
            "cycle_count": raw["cycle_count"],
            "temperature": raw["temperature"],
            "capacity_retention_curve": curve,
            "data_source": BatteryCycleDatabase.DATA_SOURCE,
        }

    def get_reference(self, formula: str) -> dict | None:
        """按化学式查询基准材料（大小写不敏感，精确匹配）。"""
        if not formula:
            return None
        target = formula.strip().lower()
        for m in self._materials:
            if m["formula"].lower() == target:
                return dict(m)
        return None

    def list_all(self) -> list[dict]:
        """列举全部基准材料。"""
        return [dict(m) for m in self._materials]

    def search(self, material_type: str = "") -> list[dict]:
        """按材料类型检索（cathode / anode 等），为空时返回全部。"""
        if not material_type:
            return self.list_all()
        key = material_type.strip().lower()
        return [dict(m) for m in self._materials if m["material_type"].lower() == key]
