"""补种数据录入模板主属性与缺失单位

Revision ID: 0025_mdm_props_units_fill
Revises: 0024_mdm_methods_idem
Create Date: 2026-07-27

评测修复（v7 续，见 doc/BatteryEMCL_全功能实操评测与整改建议书_20260727_v7.md）：

P0 同类根因：数据录入模板的字段 key（operating_voltage / bulk_resistance 等裸值）
经前端作为 property_name 直写 experiment_result_records.property_name，
0015 迁移的 fk_results_property（→ mdm.properties.property_id）导致提交 500。
单位同理：模板单位 Ω 不存在于 mdm.units（fk_results_unit）。

本次补种：
- mdm.units：Ω（电阻，模板 EIS 主字段单位）
- mdm.properties：6 个模板主字段对应特性（ionic_conductivity / particle_size
  0013 已有，不重复）
后端在写入边界做别名规范化（裸 key → prop.*；°C → C；m²/g → m2/g）。
"""
from __future__ import annotations

from alembic import op

revision = "0025_mdm_props_units_fill"
down_revision = "0024_mdm_methods_idem"
branch_labels = None
depends_on = None


# 模板主字段（前端提交 property_name 的字段） ↔ MDM 特性映射的种子数据
_PROPERTIES = [
    # (property_id, name, property_type, default_unit, description, sort_order)
    ("prop.operating_voltage",      "工作电压",       "electrochemical", "V",      "电池充放电工作电压",   110),
    ("prop.bulk_resistance",        "体电阻",         "electrochemical", "Ω",      "电解质体相欧姆电阻",   120),
    ("prop.oxidation_potential",    "氧化电位",       "electrochemical", "V",      "CV 氧化峰电位",       130),
    ("prop.crystallinity",          "结晶度",         "structural",      "%",      "XRD 结晶度",          140),
    ("prop.glass_transition_temp",  "玻璃化转变温度", "thermal",         "C",      "DSC 玻璃化转变温度",  150),
    ("prop.decomposition_temp",     "分解温度",       "thermal",         "C",      "TGA 热分解温度",      160),
]


def upgrade() -> None:
    # 1. 补 Ω 单位（prop.bulk_resistance.default_unit 引用，须先插）
    op.execute(
        "INSERT INTO mdm.units (unit_code, name, symbol, dimension, is_base, is_active) "
        "VALUES ('Ω', '欧姆', 'Ω', 'resistance', TRUE, TRUE) "
        "ON CONFLICT (unit_code) DO NOTHING"
    )
    # 2. 补 6 个模板主字段特性
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}','{r[4]}',{r[5]},TRUE)" for r in _PROPERTIES
    )
    op.execute(
        f"INSERT INTO mdm.properties (property_id, name, property_type, default_unit, "
        f"description, sort_order, is_active) "
        f"VALUES {values} ON CONFLICT (property_id) DO NOTHING"
    )


def downgrade() -> None:
    ids = ",".join(f"'{r[0]}'" for r in _PROPERTIES)
    op.execute(f"DELETE FROM mdm.properties WHERE property_id IN ({ids})")
    op.execute("DELETE FROM mdm.units WHERE unit_code = 'Ω'")
