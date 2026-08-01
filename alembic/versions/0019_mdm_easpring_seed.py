"""0019_mdm_easpring_seed

参照当升科技（Easpring）电池正极材料业务场景，补充 MDM 主数据：
- 电池行业专用单位与换算（容量/面积/粒径/粘度/面密度/面容量等）
- 电池材料分类树（正极/负极/锂源/前驱体/导电剂/粘结剂/隔膜/电解液/集流体）
- 物料分类治理数据（NCM/LFP/LCO/LMFP/LMO/NCA 等级 + 集流体/电解液等）
- 电池相关方法标准（GB/T 30835、37201、26055、11075 等）
- 正极材料专用物性（振实密度、BET 比表面积、磁性异物、首次库伦效率、循环寿命）
- 检测方法（振实密度法、BET 氮吸附、ICP-MS 磁性异物法）
- 指标项目与规格判定（NCM523/NCM622/NCM811/LFP/LCO 等级规格）
- 样品类型扩展（正极活性材料/前驱体粉末/锂盐原料）
- 工艺步骤扩展（粉碎/筛分/除磁/包装）
- 工艺路线：当升科技 NCM 正极材料合成路线

数据 only，无 schema 变更。downgrade() 为 no-op。
"""
from alembic import op

revision = "0019_mdm_easpring_seed"
down_revision = "0018_mdm_missing_seed"
branch_labels = None
depends_on = None


# ──────────────────────────────────────────────────────────────────────────────
# 工具
# ──────────────────────────────────────────────────────────────────────────────
def _sql_bool(v: bool) -> str:
    return "TRUE" if v else "FALSE"


def _sql_null(v) -> str:
    """Python None → SQL NULL；其它值加单引号转字符串。"""
    if v is None:
        return "NULL"
    return f"'{v}'"


def _sql_null_num(v) -> str:
    """数值 None → SQL NULL；其它原样输出。"""
    if v is None:
        return "NULL"
    return str(v)


def _insert_values(table: str, columns: list[str], rows: list[tuple], conflict_target: str) -> None:
    """批量 INSERT，列顺序由 columns 决定，NULL 由 _sql_null/_sql_null_num 处理。

    rows 中每个元素已是对应列的 SQL 字面量字符串（NULL / 'xxx' / 数字 / TRUE|FALSE）。
    """
    if not rows:
        return
    col_list = ",".join(columns)
    values = ",".join(f"({','.join(r)})" for r in rows)
    op.execute(
        f"INSERT INTO mdm.{table} ({col_list}) VALUES {values} "
        f"ON CONFLICT ({conflict_target}) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1. 电池行业专用单位
# ──────────────────────────────────────────────────────────────────────────────
def _seed_battery_units() -> None:
    """补充电池行业常用单位（容量/面积/长度/质量分数/摩尔浓度/面密度/面容量等）。

    不与 0011/0013/0014 已存在的单位冲突（unit_code 唯一）。
    """
    rows = [
        # (unit_code, name, symbol, dimension, is_base, is_active)
        ("mAh",    "毫安时",       "mAh",    "capacity",            True),
        ("Ah",     "安时",         "Ah",     "capacity",            False),
        ("cm2",    "平方厘米",     "cm2",    "area",                True),
        ("m2",     "平方米",       "m2",     "area",                False),
        ("nm",     "纳米",         "nm",     "length",              False),
        ("m",      "米",           "m",      "length",              False),
        ("wt%",    "质量百分比",   "wt%",    "mass_fraction",       True),
        ("mol/kg", "摩尔每千克",   "mol/kg", "molality",            True),
        ("g/L",    "克每升",       "g/L",    "mass_concentration",  True),
        ("ppm",    "百万分之一",   "ppm",    "trace_concentration", True),
        ("mg/kg",  "毫克每千克",   "mg/kg",  "trace_concentration", False),
        ("Pa.s",   "帕斯卡秒",     "Pa·s",   "viscosity",           False),
        ("Hz",     "赫兹",         "Hz",     "frequency",           True),
        ("A",      "安培",         "A",      "current",             True),
        ("g/m2",   "克每平方米",   "g/m2",   "area_density",        False),
        ("mAh/cm2","毫安时每平方厘米","mAh/cm2","area_capacity",    True),
        ("Ah/m2",  "安时每平方米", "Ah/m2",  "area_capacity",       False),
        ("m2/g",   "平方米每克",   "m2/g",   "specific_surface",    True),
        ("cycles", "次",           "cycles", "cycle_count",         True),
    ]
    columns = ["unit_code", "name", "symbol", "dimension", "is_base", "is_active"]
    sql_rows = [
        (f"'{r[0]}'", f"'{r[1]}'", f"'{r[2]}'", f"'{r[3]}'", _sql_bool(r[4]), _sql_bool(True))
        for r in rows
    ]
    _insert_values("units", columns, sql_rows, "unit_code")


# ──────────────────────────────────────────────────────────────────────────────
# 2. 电池行业单位换算
# value_in_to = value_in_from * factor + offset_value
# ──────────────────────────────────────────────────────────────────────────────
def _seed_battery_unit_conversions() -> None:
    """补充电池行业单位换算。0011 已有 13 条（质量/体积/温度/压力等），
    这里补充容量、面积、长度、粘度、面密度、面容量、痕量浓度换算。
    """
    rows = [
        # (from_unit, to_unit, factor, offset_value)
        # 容量：mAh 为 base
        ("Ah",   "mAh", 1000.0, 0.0),
        # 面积：cm2 为 base
        ("m2",   "cm2", 10000.0, 0.0),
        # 长度：um 为 base（0013 已存在），补充 nm/m 换算
        ("nm",   "um",  0.001,  0.0),
        ("m",    "um",  1000000.0, 0.0),
        ("um",   "m",   0.000001, 0.0),
        ("m",    "nm",  1000000000.0, 0.0),
        # 粘度：mPa.s 为 base（0013 已存在）
        ("Pa.s", "mPa.s", 1000.0, 0.0),
        # 面容量：mAh/cm2 为 base
        ("Ah/m2", "mAh/cm2", 0.1, 0.0),   # 1 Ah/m2 = 0.1 mAh/cm2
        ("mAh/cm2", "Ah/m2", 10.0, 0.0),   # 1 mAh/cm2 = 10 Ah/m2
        # 面密度：mg/cm2 为 base（0014 已存在）
        ("g/m2", "mg/cm2", 0.1, 0.0),     # 1 g/m2 = 0.1 mg/cm2
        ("mg/cm2", "g/m2", 10.0, 0.0),     # 1 mg/cm2 = 10 g/m2
        # 痕量浓度：ppm 与 mg/kg 等价（质量/质量）
        ("ppm",   "mg/kg", 1.0, 0.0),
        ("mg/kg", "ppm",   1.0, 0.0),
        # 质量百分比与 ppm（1 wt% = 10000 ppm）
        ("wt%",   "ppm",   10000.0, 0.0),
    ]
    columns = ["from_unit", "to_unit", "factor", "offset_value"]
    sql_rows = [(f"'{r[0]}'", f"'{r[1]}'", str(r[2]), str(r[3])) for r in rows]
    col_list = ",".join(columns)
    values = ",".join(f"({','.join(r)})" for r in sql_rows)
    op.execute(
        f"INSERT INTO mdm.unit_conversions ({col_list}) VALUES {values} "
        f"ON CONFLICT (from_unit, to_unit) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 3. 电池材料分类树
# ──────────────────────────────────────────────────────────────────────────────
def _seed_battery_classifications() -> None:
    """扩展 material 域分类树，覆盖正极/负极/锂源/前驱体/导电剂/粘结剂/隔膜/电解液/集流体。

    父子关系：material → 大类 → 子类（按需）。
    """
    rows = [
        # (code, domain, parent_code, label, sort_order)
        # 一级：正极活性材料
        ("material.cathode_active",            "material", "material", "正极活性材料",   100),
        # 二级：三元 NCM 系列
        ("material.cathode_active.ncm",         "material", "material.cathode_active", "三元材料NCM",  110),
        ("material.cathode_active.ncm523",     "material", "material.cathode_active.ncm", "NCM523",  111),
        ("material.cathode_active.ncm622",     "material", "material.cathode_active.ncm", "NCM622",  112),
        ("material.cathode_active.ncm811",     "material", "material.cathode_active.ncm", "NCM811",  113),
        # 二级：NCA
        ("material.cathode_active.nca",         "material", "material.cathode_active", "NCA",         120),
        # 二级：磷酸铁锂及改性
        ("material.cathode_active.lfp",         "material", "material.cathode_active", "磷酸铁锂LFP", 130),
        ("material.cathode_active.lmfp",        "material", "material.cathode_active", "磷酸锰铁锂LMFP", 140),
        # 二级：钴酸锂/锰酸锂
        ("material.cathode_active.lco",         "material", "material.cathode_active", "钴酸锂LCO",   150),
        ("material.cathode_active.lmo",        "material", "material.cathode_active", "锰酸锂LMO",   160),
        # 一级：负极活性材料
        ("material.anode_active",               "material", "material", "负极活性材料",   200),
        ("material.anode_active.graphite",      "material", "material.anode_active", "石墨",        210),
        ("material.anode_active.silicon",       "material", "material.anode_active", "硅基",        220),
        # 一级：锂源
        ("material.lithium_source",             "material", "material", "锂源",         300),
        ("material.lithium_source.li2co3",      "material", "material.lithium_source", "碳酸锂",     310),
        ("material.lithium_source.lioh",        "material", "material.lithium_source", "氢氧化锂",   320),
        # 一级：三元前驱体（扩展 0012 已有的 material.precursor）
        ("material.precursor.ncm_hydroxide",   "material", "material.precursor", "三元前驱体氢氧化物", 25),
        # 一级：导电剂
        ("material.conductive_additive",        "material", "material", "导电剂",       400),
        ("material.conductive_additive.super_p","material", "material.conductive_additive", "Super-P导电炭黑", 410),
        ("material.conductive_additive.cnt",    "material", "material.conductive_additive", "碳纳米管CNT", 420),
        # 一级：粘结剂
        ("material.binder",                     "material", "material", "粘结剂",       500),
        ("material.binder.pvdf",                "material", "material.binder", "PVDF聚偏氟乙烯", 510),
        ("material.binder.sbr",                 "material", "material.binder", "SBR丁苯橡胶",    520),
        # 一级：隔膜
        ("material.separator",                  "material", "material", "隔膜",         600),
        # 一级：电解液
        ("material.electrolyte",                "material", "material", "电解液",       700),
        # 一级：集流体
        ("material.current_collector",          "material", "material", "集流体",       800),
        ("material.current_collector.al_foil",  "material", "material.current_collector", "铝箔", 810),
        ("material.current_collector.cu_foil",  "material", "material.current_collector", "铜箔", 820),
        # process_type 扩展（用于工艺步骤分类）
        ("process_type.grinding",       "process_type", "process_type", "粉碎研磨", 95),
        ("process_type.sieving",        "process_type", "process_type", "筛分",     96),
        ("process_type.magnetic_sep",   "process_type", "process_type", "除磁",     97),
        ("process_type.packaging",      "process_type", "process_type", "包装",     98),
    ]
    columns = ["code", "domain", "parent_code", "label", "sort_order", "is_active", "description"]
    sql_rows = [
        (f"'{r[0]}'", f"'{r[1]}'", _sql_null(r[2]), f"'{r[3]}'", str(r[4]), _sql_bool(True), "''")
        for r in rows
    ]
    _insert_values("classifications", columns, sql_rows, "code")


# ──────────────────────────────────────────────────────────────────────────────
# 4. 物料分类治理（material_categories）
# ──────────────────────────────────────────────────────────────────────────────
def _seed_battery_material_categories() -> None:
    """为每个电池材料叶子分类补充治理属性：默认单位/存储条件/保质期/危险品标识。

    category_code 引用 classifications.code，default_unit 引用 units.unit_code。
    """
    rows = [
        # (category_code, default_unit, default_storage_conditions, default_retention_days, is_hazardous, description)
        # 正极活性材料
        ("material.cathode_active.ncm523", "kg", "常温干燥避光",     180, False, "NCM523 三元正极材料 6 个月保质期"),
        ("material.cathode_active.ncm622", "kg", "常温干燥避光",     180, False, "NCM622 三元正极材料 6 个月保质期"),
        ("material.cathode_active.ncm811", "kg", "常温干燥惰性气氛", 90,  True,  "NCM811 高镍正极 需惰性气氛存储 防吸潮"),
        ("material.cathode_active.nca",    "kg", "常温干燥惰性气氛", 90,  True,  "NCA 高镍正极 需惰性气氛存储"),
        ("material.cathode_active.lfp",    "kg", "常温干燥",         365, False, "磷酸铁锂正极材料 1 年保质期"),
        ("material.cathode_active.lmfp",   "kg", "常温干燥",         180, False, "磷酸锰铁锂正极材料"),
        ("material.cathode_active.lco",    "kg", "常温干燥避光",     365, True,  "钴酸锂正极 钴为有害元素需特殊管理"),
        ("material.cathode_active.lmo",    "kg", "常温干燥",         365, False, "锰酸锂正极材料"),
        # 负极活性材料
        ("material.anode_active.graphite", "kg", "常温干燥",         365, False, "人造/天然石墨负极材料"),
        ("material.anode_active.silicon",  "kg", "常温干燥惰性气氛", 90,  False, "硅基负极材料 需惰性气氛防氧化"),
        # 锂源
        ("material.lithium_source.li2co3", "kg", "常温干燥密封",     365, False, "电池级碳酸锂 主锂源"),
        ("material.lithium_source.lioh",   "kg", "常温干燥密封",     180, True,  "电池级单水氢氧化锂 强碱性 高镍正极用"),
        # 三元前驱体
        ("material.precursor.ncm_hydroxide", "kg", "常温干燥惰性气氛", 180, True, "三元前驱体 Ni-Co-Mn 复合氢氧化物 需惰性气氛"),
        # 导电剂
        ("material.conductive_additive.super_p", "kg", "常温干燥密封", 365, False, "Super-P 导电炭黑 易飞扬"),
        ("material.conductive_additive.cnt",     "kg", "常温干燥密封", 365, False, "碳纳米管导电剂"),
        # 粘结剂
        ("material.binder.pvdf", "kg", "常温干燥避光", 365, False, "PVDF 聚偏氟乙烯正极粘结剂"),
        ("material.binder.sbr",  "kg", "常温阴凉",     180, False, "SBR 丁苯橡胶乳液负极粘结剂"),
        # 隔膜
        ("material.separator", "kg", "常温干燥", 365, False, "聚乙烯/聚丙烯隔膜"),
        # 电解液
        ("material.electrolyte", "L", "常温阴凉密封避光", 180, True, "电解液 含 LiPF6 易燃腐蚀"),
        # 集流体
        ("material.current_collector.al_foil", "kg", "常温干燥", 730, False, "电池正极铝箔"),
        ("material.current_collector.cu_foil", "kg", "常温干燥", 730, False, "电池负极铜箔"),
    ]
    columns = ["category_code", "default_unit", "default_storage_conditions",
               "default_retention_days", "is_hazardous", "description"]
    sql_rows = [
        (f"'{r[0]}'", f"'{r[1]}'", f"'{r[2]}'", str(r[3]), _sql_bool(r[4]), f"'{r[5]}'")
        for r in rows
    ]
    _insert_values("material_categories", columns, sql_rows, "category_code")


# ──────────────────────────────────────────────────────────────────────────────
# 5. 电池相关方法标准
# ──────────────────────────────────────────────────────────────────────────────
def _seed_battery_standards() -> None:
    """补充电池正极材料相关国标/行业标准。0017 已有 GB/T 18287/31485 等，这里聚焦材料标准。"""
    rows = [
        # (standard_code, name, issuer, version, effective_date, description)
        ("GB/T 30835",  "锂离子电池用炭复合磷酸铁锂正极材料",            "国标", "2014", "2014-12-05", "LFP 正极材料产品规范"),
        ("GB/T 33822",  "炭复合磷酸铁锂正极材料中碳含量的测定",        "国标", "2017", "2017-12-29", "LFP 中碳含量测定方法"),
        ("GB/T 37201",  "镍钴锰酸锂",                                  "国标", "2018", "2018-12-28", "NCM 三元正极材料产品规范"),
        ("GB/T 26055",  "镍钴锰三元素复合氢氧化物",                    "国标", "2010", "2011-08-01", "NCM 前驱体产品规范"),
        ("GB/T 11075",  "碳酸锂",                                       "国标", "2003", "2004-04-01", "工业/电池级碳酸锂规范"),
        ("GB/T 5162",   "金属粉末 振实密度的测定",                      "国标", "2006", "2007-02-01", "振实密度测试方法"),
        ("GB/T 20155",  "锂离子电池石墨类负极材料中磁性异物含量的测定", "国标", "2006", "2006-08-01", "电池材料磁性金属异物测定 ICP-MS 法"),
        ("ISO 9277",    "Determination of the specific surface area by gas adsorption", "ISO", "2010", "2010-12-01", "BET 氮吸附法比表面积测定"),
        ("YS/T 799",    "铝合金箔",                                     "有色标", "2012", "2013-03-01", "电池用铝箔行业标准"),
    ]
    columns = ["standard_code", "name", "issuer", "version", "effective_date",
               "is_active", "description"]
    sql_rows = [
        (f"'{r[0]}'", f"'{r[1]}'", f"'{r[2]}'", f"'{r[3]}'", _sql_null(r[4]),
         _sql_bool(True), f"'{r[5]}'")
        for r in rows
    ]
    _insert_values("standards", columns, sql_rows, "standard_code")


# ──────────────────────────────────────────────────────────────────────────────
# 6. 电池正极材料专用物性
# ──────────────────────────────────────────────────────────────────────────────
def _seed_battery_properties() -> None:
    """补充正极材料专用物性。0013 已有 8 项（离子电导率/比容量/粒径/孔隙率/粘度/pH/密度/水分），
    这里补充振实密度、BET 比表面积、磁性异物、首次库伦效率、循环寿命。
    """
    rows = [
        # (property_id, name, property_type, default_unit, description, sort_order)
        ("prop.tap_density",          "振实密度",       "physical",      "g/cm3", "粉末振实后的表观密度", 90),
        ("prop.bet_surface_area",     "BET比表面积",    "morphological", "m2/g",  "氮吸附法测得的比表面积", 100),
        ("prop.magnetic_substance",   "磁性异物",       "chemical",      "ppm",   "铁/铬/镍等磁性金属杂质", 110),
        ("prop.first_cycle_efficiency","首次库伦效率",  "electrochemical","%",    "半电池首圈充放电效率", 120),
        ("prop.cycle_life_80pct",     "80%容量循环寿命","electrochemical","cycles","容量保持率降至80%的循环次数", 130),
    ]
    columns = ["property_id", "name", "property_type", "default_unit",
               "description", "sort_order", "is_active"]
    sql_rows = [
        (f"'{r[0]}'", f"'{r[1]}'", f"'{r[2]}'", _sql_null(r[3]), f"'{r[4]}'", str(r[5]), _sql_bool(True))
        for r in rows
    ]
    _insert_values("properties", columns, sql_rows, "property_id")


# ──────────────────────────────────────────────────────────────────────────────
# 7. 电池检测方法
# ──────────────────────────────────────────────────────────────────────────────
def _seed_battery_test_methods() -> None:
    """补充电池正极材料专用检测方法。0013 已有 EIS/半电/激光衍射/压汞/旋转粘度/卡尔费休。"""
    rows = [
        # (method_id, name, standard_code, sop_version, preparation_req, calculation_formula, description)
        ("method.tap_density_test",  "振实密度测试法",       "GB/T 5162", "v1.0", "5g 样品振实 3000 次", "rho_tap = m/V_tap",     "振实密度测定"),
        ("method.bet_n2_adsorption", "BET氮吸附法",          "ISO 9277",  "v1.0", "样品 200℃ 真空脱气 2h", "SSA = (V_m * N_A * sigma) / (22400 * m)", "比表面积测定"),
        ("method.magnetic_icp_ms",   "ICP-MS磁性异物法",     "GB/T 20155", "v1.0", "样品酸溶后过滤磁性物质", "C = (m_mag / m_sample) * 1e6", "磁性金属异物含量测定"),
        ("method.half_cell_05c",     "0.5C半电池容量法",     None,         "v1.0", "涂布极片装配 CR2032 扣电", "C = I*t/m_active", "0.5C 充放电测比容量"),
    ]
    columns = ["method_id", "name", "standard_code", "sop_version",
               "preparation_req", "calculation_formula", "description", "is_active"]
    sql_rows = [
        (f"'{r[0]}'", f"'{r[1]}'", _sql_null(r[2]), f"'{r[3]}'", f"'{r[4]}'", f"'{r[5]}'", f"'{r[6]}'", _sql_bool(True))
        for r in rows
    ]
    _insert_values("test_methods", columns, sql_rows, "method_id")


# ──────────────────────────────────────────────────────────────────────────────
# 8. 电池检测指标项目
# ──────────────────────────────────────────────────────────────────────────────
def _seed_battery_test_items() -> None:
    """补充电池正极材料检测指标，关联 properties ↔ test_methods。"""
    rows = [
        # (item_id, property_id, name, test_method_id, condition_text, default_unit, sort_order)
        ("item.tap_density_5g",   "prop.tap_density",          "5g振实密度",       "method.tap_density_test",  "5g 样品 3000 次振实", "g/cm3", 10),
        ("item.bet_surface_area", "prop.bet_surface_area",     "BET比表面积",      "method.bet_n2_adsorption", "200℃ 脱气 2h",        "m2/g",  10),
        ("item.magnetic_fe",      "prop.magnetic_substance",   "铁磁性异物",       "method.magnetic_icp_ms",   "酸溶磁选富集",         "ppm",   10),
        ("item.magnetic_cr",      "prop.magnetic_substance",   "铬磁性异物",       "method.magnetic_icp_ms",   "酸溶磁选富集",         "ppm",   20),
        ("item.magnetic_ni",      "prop.magnetic_substance",   "镍磁性异物",       "method.magnetic_icp_ms",   "酸溶磁选富集",         "ppm",   30),
        ("item.spec_cap_05c",     "prop.specific_capacity",    "0.5C比容量",       "method.half_cell_05c",     "0.5C 恒流充放电",      "mAh/g", 30),
        ("item.first_eff_01c",    "prop.first_cycle_efficiency","0.1C首次库伦效率","method.half_cell_05c",     "0.1C 首圈",            "%",     10),
        ("item.cycle_life_1c",    "prop.cycle_life_80pct",     "1C循环至80%容量", "method.half_cell_05c",     "1C 循环至 80% 保持率", "cycles", 10),
    ]
    columns = ["item_id", "property_id", "name", "test_method_id",
               "condition_text", "default_unit", "sort_order", "is_active"]
    sql_rows = [
        (f"'{r[0]}'", f"'{r[1]}'", f"'{r[2]}'", _sql_null(r[3]), f"'{r[4]}'", _sql_null(r[5]), str(r[6]), _sql_bool(True))
        for r in rows
    ]
    _insert_values("test_items", columns, sql_rows, "item_id")


# ──────────────────────────────────────────────────────────────────────────────
# 9. 正极材料等级规格判定
# ──────────────────────────────────────────────────────────────────────────────
def _seed_battery_specifications() -> None:
    """补充 NCM523/NCM622/NCM811/LFP/LCO 等级规格判定规则。

    引用 item.* 已有或新增的指标项目，给出目标值/上下限/判定逻辑。
    """
    rows = [
        # (spec_id, item_id, target_value, min_value, max_value, unit, judgment_logic, description)
        # NCM523 规格
        ("spec.ncm523_d50",          "item.particle_d50",      8.0,  5.0,   12.0, "um",    "RANGE", "NCM523 D50 粒径 5-12 um"),
        ("spec.ncm523_tap_density",  "item.tap_density_5g",     2.3,  2.0,   None,  "g/cm3", "GE",    "NCM523 振实密度 ≥ 2.0 g/cm3"),
        ("spec.ncm523_bet",           "item.bet_surface_area",  0.4,  0.2,   0.6,   "m2/g",  "RANGE", "NCM523 BET 0.2-0.6 m2/g"),
        ("spec.ncm523_magnetic_fe",   "item.magnetic_fe",      None, None,  0.5,   "ppm",   "LE",     "NCM523 磁性铁 ≤ 0.5 ppm"),
        ("spec.ncm523_spec_cap_01c",  "item.spec_cap_01c",     None, 150.0, None,  "mAh/g", "GE",     "NCM523 0.1C 比容量 ≥ 150 mAh/g"),
        # NCM622 规格
        ("spec.ncm622_d50",          "item.particle_d50",      9.0,  6.0,   13.0, "um",    "RANGE", "NCM622 D50 粒径 6-13 um"),
        ("spec.ncm622_tap_density",  "item.tap_density_5g",    2.4,  2.1,   None,  "g/cm3", "GE",    "NCM622 振实密度 ≥ 2.1 g/cm3"),
        ("spec.ncm622_bet",           "item.bet_surface_area",  0.35, 0.2,   0.5,   "m2/g",  "RANGE", "NCM622 BET 0.2-0.5 m2/g"),
        ("spec.ncm622_magnetic_fe",   "item.magnetic_fe",      None, None,  0.3,   "ppm",   "LE",     "NCM622 磁性铁 ≤ 0.3 ppm"),
        ("spec.ncm622_spec_cap_01c",  "item.spec_cap_01c",     None, 165.0, None,  "mAh/g", "GE",     "NCM622 0.1C 比容量 ≥ 165 mAh/g"),
        # NCM811 规格（高镍，更严苛）
        ("spec.ncm811_d50",          "item.particle_d50",      10.0, 7.0,   14.0, "um",    "RANGE", "NCM811 D50 粒径 7-14 um"),
        ("spec.ncm811_tap_density",  "item.tap_density_5g",    2.5,  2.2,   None,  "g/cm3", "GE",    "NCM811 振实密度 ≥ 2.2 g/cm3"),
        ("spec.ncm811_bet",           "item.bet_surface_area",  0.3,  0.15,  0.45,  "m2/g",  "RANGE", "NCM811 BET 0.15-0.45 m2/g"),
        ("spec.ncm811_magnetic_fe",   "item.magnetic_fe",       None, None,  0.2,   "ppm",   "LE",     "NCM811 磁性铁 ≤ 0.2 ppm（高镍材料严控）"),
        ("spec.ncm811_spec_cap_01c",  "item.spec_cap_01c",     None, 180.0, None,  "mAh/g", "GE",     "NCM811 0.1C 比容量 ≥ 180 mAh/g"),
        ("spec.ncm811_first_eff",     "item.first_eff_01c",    None, 88.0,  None,  "%",     "GE",     "NCM811 首次库伦效率 ≥ 88%"),
        # LFP 规格
        ("spec.lfp_d50",             "item.particle_d50",      2.5,  1.5,   3.5,  "um",    "RANGE", "LFP D50 粒径 1.5-3.5 um（小颗粒）"),
        ("spec.lfp_tap_density",     "item.tap_density_5g",    1.4,  1.2,   None,  "g/cm3", "GE",    "LFP 振实密度 ≥ 1.2 g/cm3"),
        ("spec.lfp_bet",              "item.bet_surface_area", 15.0, 12.0,  18.0, "m2/g",  "RANGE", "LFP BET 12-18 m2/g（高比表面积）"),
        ("spec.lfp_magnetic_fe",      "item.magnetic_fe",      None, None,  0.5,   "ppm",   "LE",     "LFP 磁性铁 ≤ 0.5 ppm"),
        ("spec.lfp_spec_cap_01c",     "item.spec_cap_01c",     None, 150.0, None,  "mAh/g", "GE",     "LFP 0.1C 比容量 ≥ 150 mAh/g"),
        # LCO 规格（3C 钴酸锂）
        ("spec.lco_d50",             "item.particle_d50",      7.0,  5.0,   10.0, "um",    "RANGE", "LCO D50 粒径 5-10 um"),
        ("spec.lco_tap_density",     "item.tap_density_5g",    2.4,  2.2,   2.6,  "g/cm3", "RANGE", "LCO 振实密度 2.2-2.6 g/cm3"),
        ("spec.lco_spec_cap_01c",     "item.spec_cap_01c",     None, 140.0, None,  "mAh/g", "GE",     "LCO 0.1C 比容量 ≥ 140 mAh/g"),
    ]
    columns = ["spec_id", "item_id", "target_value", "min_value", "max_value",
               "unit", "judgment_logic", "description", "is_active"]
    sql_rows = [
        (f"'{r[0]}'", f"'{r[1]}'", _sql_null_num(r[2]), _sql_null_num(r[3]),
         _sql_null_num(r[4]), f"'{r[5]}'", f"'{r[6]}'", f"'{r[7]}'", _sql_bool(True))
        for r in rows
    ]
    _insert_values("specifications", columns, sql_rows, "spec_id")


# ──────────────────────────────────────────────────────────────────────────────
# 10. 电池样品类型扩展
# ──────────────────────────────────────────────────────────────────────────────
def _seed_battery_sample_types() -> None:
    """补充电池材料专用样品类型。0012 已有 7 个通用类型，这里加 4 个电池专用。"""
    rows = [
        # (type_code, name, description, default_storage_conditions, default_retention_days, is_hazardous, sort_order)
        ("cathode_active",     "正极活性材料",  "NCM/LFP/LCO 等正极粉末样品", "常温干燥避光",     180, False, 80),
        ("anode_active",       "负极活性材料",  "石墨/硅基负极粉末样品",      "常温干燥",         365, False, 90),
        ("precursor_powder",   "前驱体粉末",    "三元前驱体氢氧化物粉末",     "常温干燥惰性气氛", 180, True,  100),
        ("lithium_salt",       "锂盐原料",      "碳酸锂/氢氧化锂等锂源原料",   "常温干燥密封",     365, False, 110),
    ]
    columns = ["type_code", "name", "description", "default_storage_conditions",
               "default_retention_days", "is_hazardous", "sort_order", "is_active"]
    sql_rows = [
        (f"'{r[0]}'", f"'{r[1]}'", f"'{r[2]}'", f"'{r[3]}'", str(r[4]), _sql_bool(r[5]), str(r[6]), _sql_bool(True))
        for r in rows
    ]
    _insert_values("sample_types", columns, sql_rows, "type_code")


# ──────────────────────────────────────────────────────────────────────────────
# 11. 电池工艺步骤扩展
# ──────────────────────────────────────────────────────────────────────────────
def _seed_battery_process_steps() -> None:
    """补充正极材料合成专用工艺步骤。0014 已有 9 步（mixing/dispersion/coating/drying/rolling/
    sintering/assembly/formation/cycling_test），这里补 4 步：grinding/sieving/magnetic_sep/packaging。
    """
    rows = [
        # (step_id, name, step_type, description, sort_order)
        ("step.grinding",            "粉碎研磨",   "process_type.grinding",    "烧结块料气流/机械粉碎至目标粒径", 95),
        ("step.sieving",             "筛分",       "process_type.sieving",     "过筛获取目标粒度分布",          96),
        ("step.magnetic_separation", "除磁",       "process_type.magnetic_sep", "电磁除铁去除磁性金属异物",       97),
        ("step.packaging",           "包装入库",   "process_type.packaging",   "真空/惰气包装入库",             98),
    ]
    columns = ["step_id", "name", "step_type", "description", "sort_order", "is_active"]
    sql_rows = [
        (f"'{r[0]}'", f"'{r[1]}'", f"'{r[2]}'", f"'{r[3]}'", str(r[4]), _sql_bool(True))
        for r in rows
    ]
    _insert_values("process_steps", columns, sql_rows, "step_id")


# ──────────────────────────────────────────────────────────────────────────────
# 12. 当升科技 NCM 合成工艺路线
# ──────────────────────────────────────────────────────────────────────────────
def _seed_battery_process_routes() -> None:
    """补充当升科技 NCM 正极材料合成工艺路线。

    典型流程：锂源+前驱体配料混合 → 高温烧结 → 粉碎研磨 → 筛分 → 除磁 → 包装入库
    """
    rows = [
        # (route_id, name, route_type, description, version)
        ("PR-ROUTE-NCM-SYNTHESIS", "当升科技NCM正极合成工艺",
         "cathode_synthesis",
         "锂源+三元前驱体→混合→烧结→粉碎→筛分→除磁→包装",
         "v2.0"),
        ("PR-ROUTE-LFP-SYNTHESIS", "LFP正极合成工艺（碳热还原法）",
         "cathode_synthesis",
         "磷酸铁+锂源+碳源→球磨混合→烧结→粉碎→筛分→除磁→包装",
         "v1.0"),
    ]
    columns = ["route_id", "name", "route_type", "description", "version", "is_active"]
    sql_rows = [
        (f"'{r[0]}'", f"'{r[1]}'", f"'{r[2]}'", f"'{r[3]}'", f"'{r[4]}'", _sql_bool(True))
        for r in rows
    ]
    _insert_values("process_routes", columns, sql_rows, "route_id")


def _seed_battery_process_route_steps() -> None:
    """为当升科技 NCM/LFP 合成路线建立步骤映射。"""
    rows = [
        # (route_id, step_id, step_order, notes)
        # NCM 合成 6 步
        ("PR-ROUTE-NCM-SYNTHESIS", "step.mixing",             1, "LiOH+NCM前驱体按 Li/M 摩尔比 1.05 配料混合"),
        ("PR-ROUTE-NCM-SYNTHESIS", "step.sintering",          2, "750-850℃ 氧气气氛烧结 12h"),
        ("PR-ROUTE-NCM-SYNTHESIS", "step.grinding",            3, "对辊/气流粉碎至 D50≈10 um"),
        ("PR-ROUTE-NCM-SYNTHESIS", "step.sieving",             4, "400 目过筛去除大颗粒"),
        ("PR-ROUTE-NCM-SYNTHESIS", "step.magnetic_separation",  5, "电磁除铁 磁场强度 8000 Gs"),
        ("PR-ROUTE-NCM-SYNTHESIS", "step.packaging",            6, "真空铝塑袋包装 入库"),
        # LFP 合成 6 步
        ("PR-ROUTE-LFP-SYNTHESIS", "step.mixing",             1, "磷酸铁+Li2CO3+蔗糖球磨混合"),
        ("PR-ROUTE-LFP-SYNTHESIS", "step.sintering",          2, "700℃ 氮气保护烧结 10h 碳热还原"),
        ("PR-ROUTE-LFP-SYNTHESIS", "step.grinding",            3, "气流粉碎至 D50≈2.5 um"),
        ("PR-ROUTE-LFP-SYNTHESIS", "step.sieving",             4, "500 目过筛"),
        ("PR-ROUTE-LFP-SYNTHESIS", "step.magnetic_separation",  5, "电磁除铁"),
        ("PR-ROUTE-LFP-SYNTHESIS", "step.packaging",            6, "真空包装入库"),
    ]
    columns = ["route_id", "step_id", "step_order", "notes"]
    col_list = ",".join(columns)
    values = ",".join(f"('{r[0]}','{r[1]}',{r[2]},'{r[3]}')" for r in rows)
    # process_route_steps 唯一约束：(route_id, step_id) 与 (route_id, step_order)
    op.execute(
        f"INSERT INTO mdm.process_route_steps ({col_list}) VALUES {values} "
        f"ON CONFLICT (route_id, step_id) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 13. 合成工艺步骤-参数映射
# ──────────────────────────────────────────────────────────────────────────────
def _seed_battery_process_step_parameters() -> None:
    """为合成工艺关键步骤绑定参数与默认值/控制范围。

    引用 0014 已有 process_parameters：temperature/time/rotation_speed/vacuum/
    solid_content/compaction_density/coating_weight/pressure。
    """
    rows = [
        # (step_id, parameter_id, default_value, min_value, max_value, control_level, notes)
        # 烧结步骤
        ("step.sintering", "param.temperature",       800.0,  750.0, 850.0, "critical", "NCM 烧结温度 750-850℃"),
        ("step.sintering", "param.time",              12.0,   8.0,   16.0,  "critical", "烧结时间 8-16 h"),
        # 粉碎研磨
        ("step.grinding",  "param.rotation_speed",    3000.0, 2000.0, 4000.0, "normal", "气流粉碎转速"),
        # 筛分
        ("step.sieving",   "param.time",              0.5,    0.3,   1.0,   "normal", "过筛时间"),
        # 除磁
        ("step.magnetic_separation", "param.time",   2.0,    1.0,   5.0,   "normal", "除磁通过次数"),
    ]
    columns = ["step_id", "parameter_id", "default_value", "min_value",
               "max_value", "control_level", "notes"]
    col_list = ",".join(columns)
    values = ",".join(
        f"('{r[0]}','{r[1]}',{r[2]},{r[3]},{r[4]},'{r[5]}','{r[6]}')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.process_step_parameters ({col_list}) VALUES {values} "
        f"ON CONFLICT (step_id, parameter_id) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────────────────────────────────────
def upgrade() -> None:
    _seed_battery_units()
    _seed_battery_unit_conversions()
    _seed_battery_classifications()
    _seed_battery_material_categories()
    _seed_battery_standards()
    _seed_battery_properties()
    _seed_battery_test_methods()
    _seed_battery_test_items()
    _seed_battery_specifications()
    _seed_battery_sample_types()
    _seed_battery_process_steps()
    _seed_battery_process_routes()
    _seed_battery_process_route_steps()
    _seed_battery_process_step_parameters()


def downgrade() -> None:
    # 数据 only seed，downgrade 不逆向删除（保留前向兼容）
    pass
