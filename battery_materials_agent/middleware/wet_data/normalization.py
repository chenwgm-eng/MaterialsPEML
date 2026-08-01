"""数据标准化 - 字段映射与单位换算。"""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class FieldMapper:
    """字段名映射器。"""

    DEFAULT_MAPPING = {
        "实验ID": "experiment_order_id",
        "样品ID": "sample_id",
        "样品": "sample_id",
        "属性": "property_name",
        "值": "value",
        "单位": "unit",
        "方法": "test_method",
        "仪器": "instrument_id",
        "操作员": "uploaded_by",
    }

    def map(self, field_name: str) -> str:
        return self.DEFAULT_MAPPING.get(field_name.strip(), field_name.strip().lower())


class UnitConverter:
    """单位识别与换算。"""

    # 常见单位换算因子（到 SI 基本单位）
    CONVERSIONS = {
        # 电导率
        "S/cm": 1.0,
        "mS/cm": 0.001,
        "uS/cm": 0.000001,
        # 电压
        "V": 1.0,
        "mV": 0.001,
        # 温度
        "C": 1.0,
        "K": 1.0,  # 绝对值不同，但标记为有效
        # 通用
        "g/cm3": 1.0,
        "kg/m3": 0.001,
        "mAh/g": 1.0,
        "eV": 1.0,
    }

    def convert(self, value: float, from_unit: str, to_unit: str = "") -> tuple[float, str]:
        if not from_unit or not to_unit or from_unit == to_unit:
            return value, from_unit

        from_factor = self.CONVERSIONS.get(from_unit)
        to_factor = self.CONVERSIONS.get(to_unit)

        if from_factor is None or to_factor is None:
            return value, from_unit

        return value * from_factor / to_factor, to_unit

    def is_valid_unit(self, unit: str) -> bool:
        return unit in self.CONVERSIONS or not unit
