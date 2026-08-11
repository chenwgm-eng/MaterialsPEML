"""补种改性塑料领域 MDM 主数据（属性/单位/检测方法）

Revision ID: 0058_kingfa_mdm_master
Revises: 0057_user_disciplines
Create Date: 2026-08-11

v4.1 领域切换（kingfa 改性塑料）完整化：实验模板（_EXPERIMENT_TYPE_TEMPLATES）
主字段/单位/测试方法已切换为高分子体系，但 mdm.properties / mdm.units /
mdm.test_methods 仍是电池主数据 → 实验数据录入（ExperimentWorkbench）提交
高分子属性必 400 / FK 失败。本次补种对齐模板：

- mdm.units：kJ/m2（冲击强度）、g/10min（熔体流动速率）
- mdm.properties：12 个高分子模板主字段（tensile_strength 等）
- mdm.test_methods：GB/T / ISO / ASTM 标准检测方法（standard_code 置 NULL，
  与 0024 迁移一致，避免 fk_methods_standard 失败）

注意：material 分类（BASE_POLYMER / material.reinforcement / material.flame_retardant
等）已在既有迁移中播种，不重复。
"""
from __future__ import annotations

from alembic import op

revision = "0058_kingfa_mdm_master"
down_revision = "0057_user_disciplines"
branch_labels = None
depends_on = None

# (unit_code, name, symbol, dimension)
_UNITS = [
    ("kJ/m2", "千焦每平方米", "kJ/m²", "impact_energy"),
    ("g/10min", "克每十分钟", "g/10min", "melt_flow_rate"),
]

# (property_id, name, property_type, default_unit, description, sort_order)
_PROPERTIES = [
    ("prop.tensile_strength",    "拉伸强度",       "mechanical", "MPa",     "拉伸测试最大应力",            210),
    ("prop.elongation_at_break", "断裂伸长率",     "mechanical", "%",       "断裂时相对伸长",              220),
    ("prop.tensile_modulus",     "拉伸模量",       "mechanical", "MPa",     "拉伸弹性模量",                230),
    ("prop.impact_strength",     "冲击强度",       "mechanical", "kJ/m2",   "冲击韧性（缺口冲击）",        240),
    ("prop.flexural_modulus",    "弯曲模量",       "mechanical", "MPa",     "弯曲弹性模量",                250),
    ("prop.flexural_strength",   "弯曲强度",       "mechanical", "MPa",     "弯曲最大应力",                260),
    ("prop.heat_deflection_temp","热变形温度",     "thermal",    "C",       "载荷下热变形温度",            270),
    ("prop.melt_flow_index",     "熔体流动速率",   "rheological","g/10min", "熔融指数",                    280),
    ("prop.melting_point",       "熔点",           "thermal",    "C",       "DSC 熔融峰温度",              290),
    ("prop.thermal_stability",   "热稳定温度",     "thermal",    "C",       "TGA 5% 失重温度",             300),
    ("prop.weight_loss",         "失重率",         "thermal",    "%",       "TGA 失重比例",                310),
    ("prop.residual_mass",       "残余质量",       "thermal",    "%",       "TGA 残余质量比例",            320),
    ("prop.flame_retardancy",    "阻燃等级",       "flame",      None,      "UL94/GB 阻燃等级",            330),
]

# (method_id, name, standard_code, sop_version, preparation_req, calculation_formula, description)
# standard_code 统一置 NULL（mdm.standards 未登记，置值会导致 fk_methods_standard 失败，同 0024 迁移）
_METHODS = [
    ("method.gbt_1040", "GB/T 1040 塑料拉伸性能试验",    None, "v1.0", "标准哑铃型样条", "sigma = F/A",       "拉伸强度/断裂伸长率"),
    ("method.iso_527",  "ISO 527 塑料拉伸性能试验",       None, "v1.0", "标准哑铃型样条", "sigma = F/A",       "拉伸强度/断裂伸长率"),
    ("method.astm_d638","ASTM D638 塑料拉伸性能试验",     None, "v1.0", "标准哑铃型样条", "sigma = F/A",       "拉伸强度/断裂伸长率"),
    ("method.gbt_1843", "GB/T 1843 塑料冲击性能试验",     None, "v1.0", "缺口/无缺口样条", "a = E/(b*d)",     "悬臂梁冲击强度"),
    ("method.iso_180",  "ISO 180 塑料冲击性能试验",       None, "v1.0", "缺口样条",       "a = E/(b*d)",     "悬臂梁冲击强度"),
    ("method.astm_d256","ASTM D256 塑料冲击性能试验",     None, "v1.0", "缺口样条",       "a = E/(b*d)",     "悬臂梁冲击强度"),
    ("method.gbt_9341", "GB/T 9341 塑料弯曲性能试验",     None, "v1.0", "标准样条",       "Ef = L^3*F/(4*b*h^3)", "弯曲模量/弯曲强度"),
    ("method.iso_178",  "ISO 178 塑料弯曲性能试验",       None, "v1.0", "标准样条",       "Ef = L^3*F/(4*b*h^3)", "弯曲模量/弯曲强度"),
    ("method.astm_d790","ASTM D790 塑料弯曲性能试验",     None, "v1.0", "标准样条",       "Ef = L^3*F/(4*b*h^3)", "弯曲模量/弯曲强度"),
    ("method.gbt_1634", "GB/T 1634 塑料热变形温度试验",   None, "v1.0", "标准样条",       "—",                 "热变形温度"),
    ("method.iso_75",   "ISO 75 塑料热变形温度试验",      None, "v1.0", "标准样条",       "—",                 "热变形温度"),
    ("method.astm_d648","ASTM D648 塑料热变形温度试验",   None, "v1.0", "标准样条",       "—",                 "热变形温度"),
    ("method.gbt_3682", "GB/T 3682 塑料熔体流动速率试验", None, "v1.0", "颗粒料",         "MFR = 600*m/t",     "熔体流动速率"),
    ("method.iso_1133", "ISO 1133 塑料熔体流动速率试验",  None, "v1.0", "颗粒料",         "MFR = 600*m/t",     "熔体流动速率"),
    ("method.astm_d1238","ASTM D1238 熔体流动速率试验",   None, "v1.0", "颗粒料",         "MFR = 600*m/t",     "熔体流动速率"),
    ("method.gbt_2408", "GB/T 2408 塑料水平垂直燃烧试验", None, "v1.0", "标准样条",       "—",                 "阻燃等级 V-0/V-1/V-2/HB"),
    ("method.ul94",     "UL94 塑料燃烧等级试验",          None, "v1.0", "标准样条",       "—",                 "阻燃等级 V-0/V-1/V-2/HB"),
    ("method.iso_1210", "ISO 1210 塑料燃烧等级试验",      None, "v1.0", "标准样条",       "—",                 "阻燃等级"),
    ("method.gbt_1033", "GB/T 1033 塑料密度试验",         None, "v1.0", "标准样块",       "rho = m/V",         "密度"),
    ("method.iso_1183", "ISO 1183 塑料密度试验",          None, "v1.0", "标准样块",       "rho = m/V",         "密度"),
    ("method.astm_d792","ASTM D792 塑料密度试验",         None, "v1.0", "标准样块",       "rho = m/V",         "密度"),
    ("method.gbt_19466","GB/T 19466 塑料差示扫描量热",    None, "v1.0", "标准样块",       "—",                 "Tg/熔点/结晶度"),
    ("method.iso_11357","ISO 11357 塑料差示扫描量热",     None, "v1.0", "标准样块",       "—",                 "Tg/熔点/结晶度"),
    ("method.gbt_33047","GB/T 33047 塑料热重分析",        None, "v1.0", "标准样块",       "—",                 "热稳定温度/失重率"),
    ("method.iso_11358","ISO 11358 塑料热重分析",         None, "v1.0", "标准样块",       "—",                 "热稳定温度/失重率"),
]


def upgrade() -> None:
    for unit_code, name, symbol, dimension in _UNITS:
        op.execute(
            "INSERT INTO mdm.units (unit_code, name, symbol, dimension, is_base, is_active) "
            f"VALUES ('{unit_code}', '{name}', '{symbol}', '{dimension}', TRUE, TRUE) "
            "ON CONFLICT (unit_code) DO NOTHING"
        )

    def _prop_sql(p):
        unit = "NULL" if p[3] is None else "'%s'" % p[3]
        return f"('{p[0]}','{p[1]}','{p[2]}',{unit},'{p[4]}',{p[5]},TRUE)"

    prop_values = ",".join(_prop_sql(p) for p in _PROPERTIES)
    op.execute(
        f"INSERT INTO mdm.properties (property_id, name, property_type, default_unit, "
        f"description, sort_order, is_active) "
        f"VALUES {prop_values} ON CONFLICT (property_id) DO NOTHING"
    )

    method_values = ",".join(
        f"('{m[0]}','{m[1]}',NULL,'{m[3]}','{m[4]}','{m[5]}','{m[6]}',TRUE)" for m in _METHODS
    )
    op.execute(
        f"INSERT INTO mdm.test_methods (method_id, name, standard_code, sop_version, "
        f"preparation_req, calculation_formula, description, is_active) "
        f"VALUES {method_values} ON CONFLICT (method_id) DO NOTHING"
    )


def downgrade() -> None:
    method_ids = ",".join("'%s'" % m[0] for m in _METHODS)
    prop_ids = ",".join("'%s'" % p[0] for p in _PROPERTIES)
    unit_ids = ",".join("'%s'" % u[0] for u in _UNITS)
    op.execute(f"DELETE FROM mdm.test_methods WHERE method_id IN ({method_ids})")
    op.execute(f"DELETE FROM mdm.properties WHERE property_id IN ({prop_ids})")
    op.execute(f"DELETE FROM mdm.units WHERE unit_code IN ({unit_ids})")
