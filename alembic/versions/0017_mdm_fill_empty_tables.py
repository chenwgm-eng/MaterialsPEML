"""P6 MDM 空表填充：为 11 张空的 MDM 主数据表填充电池材料研发基础数据。

填充内容：
- mdm.standards 方法标准（10 条：GB/T、IEC、ASTM、ISO、QC/T）
- mdm.ghs_classes GHS 危害分类（9 条：GHS01-GHS09）
- mdm.locations 位置层级（9 条：研发楼/楼层/实验室/仓库/冷藏室）
- mdm.containers 容器（9 条：试剂瓶/烧瓶/烧杯/包装袋/桶）
- mdm.equipment_templates 设备模板（14 条：反应釜/烘箱/电池测试仪等）
- mdm.equipment_template_capabilities 设备模板-能力映射
- mdm.inspection_capabilities 质检能力（6 条：每个 test_method 一条）
- mdm.process_routes 工艺路线（5 条：LCO/NCM/LFP/石墨/隔膜）
- mdm.process_route_steps 工艺路线-步骤映射
- mdm.process_step_parameters 工艺步骤-参数映射
- mdm.process_step_equipment_templates 工艺步骤-设备模板映射

同时补充 mdm.classifications 中 equipment_templates.category_code 需要的设备子分类
（synthesis/pretreatment/test/electrochemical/analysis，characterization/safety 已存在）。

所有 INSERT 使用 ON CONFLICT (...) DO NOTHING 保证幂等。

Revision ID: 0017_mdm_fill_empty_tables
Revises: 0016_mdm_seed_fix
Create Date: 2026-07-27

详见 .trae/specs/mdm-governance/spec.md
"""
from __future__ import annotations

from alembic import op

revision = "0017_mdm_fill_empty_tables"
down_revision = "0016_mdm_seed_fix"
branch_labels = None
depends_on = None


# ──────────────────────────────────────────────────────────────────────────────
# upgrade
# ──────────────────────────────────────────────────────────────────────────────
def upgrade() -> None:
    # 0. 补充 equipment_templates.category_code 需要的设备子分类（FK 依赖）
    _seed_equipment_classifications()
    # 1-11. 填充 11 张空表
    _seed_standards()
    _seed_ghs_classes()
    _seed_locations()
    _seed_containers()
    _seed_equipment_templates()
    _seed_equipment_template_capabilities()
    _seed_inspection_capabilities()
    _seed_process_routes()
    _seed_process_route_steps()
    _seed_process_step_parameters()
    _seed_process_step_equipment_templates()


# ──────────────────────────────────────────────────────────────────────────────
# downgrade：seed 数据不可逆，仅占位
# ──────────────────────────────────────────────────────────────────────────────
def downgrade() -> None:
    """seed 数据不可逆，不删除。"""
    pass


# ──────────────────────────────────────────────────────────────────────────────
# 0. 补充 equipment_templates.category_code 需要的设备子分类
# ──────────────────────────────────────────────────────────────────────────────
def _seed_equipment_classifications() -> None:
    """补充 equipment domain 下缺失的子分类（FK 依赖）。

    现有：equipment.preparation/mixing/coating/rolling/sintering/characterization/
          environment_control/safety
    新增：equipment.synthesis/pretreatment/test/electrochemical/analysis
    """
    rows = [
        ("equipment.synthesis",       "equipment", "equipment", "合成设备",       15),
        ("equipment.pretreatment",    "equipment", "equipment", "前处理设备",     25),
        ("equipment.test",            "equipment", "equipment", "测试设备",       35),
        ("equipment.electrochemical", "equipment", "equipment", "电化学测试设备", 45),
        ("equipment.analysis",        "equipment", "equipment", "分析设备",       55),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.classifications (code, domain, parent_code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (code) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# a. mdm.standards 方法标准
# ──────────────────────────────────────────────────────────────────────────────
def _seed_standards() -> None:
    """seed 10 条常见电池/质量/环境方法标准。"""
    rows = [
        # (standard_code, name, issuer, version, effective_date, description)
        ("STD-GBT-18287-2013",  "GB/T 18287-2013 锂离子电池总规范",                  "GB/T",  "2013", "2013-12-31", "锂离子电池总规范"),
        ("STD-GBT-31485-2015",  "GB/T 31485-2015 电动汽车用动力蓄电池安全要求",       "GB/T",  "2015", "2015-05-15", "动力蓄电池安全要求"),
        ("STD-GBT-31486-2015",  "GB/T 31486-2015 电动汽车用动力蓄电池电性能要求",     "GB/T",  "2015", "2015-05-15", "动力蓄电池电性能要求"),
        ("STD-GBT-31467-2015",  "GB/T 31467.1-2015 电动汽车用锂离子动力蓄电池包和系统", "GB/T",  "2015", "2015-05-15", "蓄电池包和系统"),
        ("STD-IEC-62133-2017",  "IEC 62133-2:2017 含碱性或非酸性电解质的蓄电池",      "IEC",   "2017", "2017-01-01", "便携式密封蓄电池安全要求"),
        ("STD-IEC-62660-2018",  "IEC 62660-1:2018 电动汽车用锂离子电池",              "IEC",   "2018", "2018-01-01", "电动汽车用锂离子电池性能"),
        ("STD-ASTM-B214-16",    "ASTM B214-16 粒度分析标准",                          "ASTM",  "2016", "2016-01-01", "金属粉末粒度分析标准"),
        ("STD-ISO-9001-2015",   "ISO 9001:2015 质量管理体系",                          "ISO",   "2015", "2015-09-15", "质量管理体系要求"),
        ("STD-ISO-14001-2015",  "ISO 14001:2015 环境管理体系",                         "ISO",   "2015", "2015-09-15", "环境管理体系要求"),
        ("STD-QCT-743-2006",    "QC/T 743-2006 电动汽车用锂离子蓄电池",                "QC/T",  "2006", "2006-01-01", "电动汽车用锂离子蓄电池"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}','{r[4]}',TRUE,'{r[5]}')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.standards (standard_code, name, issuer, version, effective_date, is_active, description) "
        f"VALUES {values} ON CONFLICT (standard_code) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# b. mdm.ghs_classes GHS 危害分类
# ──────────────────────────────────────────────────────────────────────────────
def _seed_ghs_classes() -> None:
    """seed 9 条 GHS 标准危害分类。"""
    rows = [
        # (ghs_code, label, hazard_level, pictogram)
        ("GHS01", "爆炸物",       "high",   "exploding_bomb"),
        ("GHS02", "易燃物",       "high",   "flame"),
        ("GHS03", "氧化性物质",   "high",   "flame_over_circle"),
        ("GHS04", "高压气体",     "medium", "gas_cylinder"),
        ("GHS05", "腐蚀性物质",   "high",   "corrosion"),
        ("GHS06", "急性毒性",     "high",   "skull_crossbones"),
        ("GHS07", "刺激性",       "medium", "exclamation_mark"),
        ("GHS08", "健康危害",     "high",   "health_hazard"),
        ("GHS09", "环境危害",     "medium", "environment"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',TRUE)" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.ghs_classes (ghs_code, label, hazard_level, pictogram, is_active) "
        f"VALUES {values} ON CONFLICT (ghs_code) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# c. mdm.locations 位置层级（注意：parent_id 必须先于子节点插入）
# ──────────────────────────────────────────────────────────────────────────────
def _seed_locations() -> None:
    """seed 9 条电池研发实验室位置层级，按父→子顺序插入。"""
    rows = [
        # (location_id, parent_id, location_type, name, full_path, capacity, description)
        ("LOC-BUILDING-A",  None,             "building",     "A 栋研发楼",      "/A栋",             0,    "A 栋研发办公楼"),
        ("LOC-FL-A-1",      "LOC-BUILDING-A", "floor",        "A 栋 1 层",       "/A栋/1层",         0,    "A 栋一层公共区域"),
        ("LOC-FL-A-2",      "LOC-BUILDING-A", "floor",        "A 栋 2 层",       "/A栋/2层",         0,    "A 栋二层实验区"),
        ("LOC-LAB-A201",    "LOC-FL-A-2",     "lab",          "A201 合成实验室", "/A栋/2层/A201",    20,   "材料合成与制备"),
        ("LOC-LAB-A202",    "LOC-FL-A-2",     "lab",          "A202 电化学测试室", "/A栋/2层/A202",  15,   "电化学性能测试"),
        ("LOC-LAB-A203",    "LOC-FL-A-2",     "lab",          "A203 表征分析室", "/A栋/2层/A203",    10,   "材料表征分析"),
        ("LOC-WAREHOUSE-1", None,             "warehouse",    "原料仓库",        "/原料仓库",        1000, "常规原料存储"),
        ("LOC-WAREHOUSE-2", None,             "warehouse",    "危化品仓库",      "/危化品仓库",      200,  "危险化学品存储"),
        ("LOC-COLD-1",      None,             "cold_storage", "冷藏室",          "/冷藏室",          100,  "低温冷藏存储"),
    ]
    values = ",".join(
        f"('{r[0]}',{_sql_null(r[1])},'{r[2]}','{r[3]}','{r[4]}',{r[5]},'{r[6]}',TRUE)"
        for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.locations (location_id, parent_id, location_type, name, full_path, "
        f"capacity, description, is_active) "
        f"VALUES {values} ON CONFLICT (location_id) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# d. mdm.containers 容器
# ──────────────────────────────────────────────────────────────────────────────
def _seed_containers() -> None:
    """seed 9 条常见实验容器与包装。"""
    rows = [
        # (container_code, name, container_type, material, capacity_value, capacity_unit, is_hazardous_compatible, description)
        ("CTR-BOTTLE-50",  "50mL 试剂瓶",  "bottle", "glass",  50,  "mL", False, "棕色玻璃试剂瓶"),
        ("CTR-BOTTLE-100", "100mL 试剂瓶", "bottle", "glass",  100, "mL", False, "棕色玻璃试剂瓶"),
        ("CTR-BOTTLE-250", "250mL 试剂瓶", "bottle", "glass",  250, "mL", False, "棕色玻璃试剂瓶"),
        ("CTR-FLASK-250",  "250mL 烧瓶",   "flask",  "glass",  250, "mL", False, "圆底玻璃烧瓶"),
        ("CTR-FLASK-500",  "500mL 烧瓶",   "flask",  "glass",  500, "mL", False, "圆底玻璃烧瓶"),
        ("CTR-BEAKER-100", "100mL 烧杯",   "beaker", "glass",  100, "mL", False, "玻璃烧杯"),
        ("CTR-BEAKER-250", "250mL 烧杯",   "beaker", "glass",  250, "mL", False, "玻璃烧杯"),
        ("CTR-BAG-1",      "1kg 包装袋",   "bag",    "plastic", 1,  "kg",  False, "自封塑料袋"),
        ("CTR-DRUM-25",    "25L 桶",       "drum",   "hdpe",   25,  "L",   True,  "高密度聚乙烯桶，可装危险品"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},'{r[5]}',{_sql_bool(r[6])},'{r[7]}',TRUE)"
        for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.containers (container_code, name, container_type, material, "
        f"capacity_value, capacity_unit, is_hazardous_compatible, description, is_active) "
        f"VALUES {values} ON CONFLICT (container_code) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# e. mdm.equipment_templates 设备模板
# ──────────────────────────────────────────────────────────────────────────────
def _seed_equipment_templates() -> None:
    """seed 14 条电池研发常见设备模板。"""
    rows = [
        # (template_code, name, category_code, model, manufacturer, specification, default_location_id, description)
        ("EQ-TEMPL-REACTOR",       "反应釜",            "equipment.synthesis",       "CF-2L",       "杭州得聚",         "2L PTFE内衬",          "LOC-LAB-A201", "水热合成反应釜"),
        ("EQ-TEMPL-OVEN",          "烘箱",              "equipment.pretreatment",    "DGG-9070A",   "上海森信",         "70L 真空烘箱",         "LOC-LAB-A201", "真空干燥箱"),
        ("EQ-TEMPL-FURNACE",       "马弗炉",            "equipment.pretreatment",    "SX2-12-10",   "上海树立",         "1200度箱式炉",         "LOC-LAB-A201", "高温箱式电阻炉"),
        ("EQ-TEMPL-BALL-MILL",     "球磨机",            "equipment.synthesis",       "QM-3SP4",     "南京大学仪器厂",   "行星式四罐",           "LOC-LAB-A201", "行星式球磨机"),
        ("EQ-TEMPL-COATER",        "涂布机",            "equipment.synthesis",       "MSK-AFA-III", "合肥科晶",         "狭缝涂布",             "LOC-LAB-A202", "自动涂布机"),
        ("EQ-TEMPL-PRESS",         "辊压机",            "equipment.synthesis",       "MSK-2150",    "合肥科晶",         "液压对辊",             "LOC-LAB-A202", "极片辊压机"),
        ("EQ-TEMPL-COIN-CELL",     "扣式电池制备",      "equipment.test",            "MSK-110",     "合肥科晶",         "CR2032",               "LOC-LAB-A202", "扣式电池封口机"),
        ("EQ-TEMPL-BATTERY-TESTER","电池测试仪",        "equipment.test",            "CT2001A",     "蓝电",             "8通道 5V/10mA",        "LOC-LAB-A202", "多通道电池测试系统"),
        ("EQ-TEMPL-EIS",           "电化学工作站",      "equipment.electrochemical", "CHI760E",     "上海辰华",         "频率1e6-1e-3 Hz",      "LOC-LAB-A202", "电化学综合测试仪"),
        ("EQ-TEMPL-XRD",           "X射线衍射仪",       "equipment.characterization", "D8 ADVANCE", "Bruker",           "theta/theta 测角仪",   "LOC-LAB-A203", "X 射线粉末衍射仪"),
        ("EQ-TEMPL-SEM",           "扫描电镜",          "equipment.characterization", "JSM-7800F",  "JEOL",             "场发射 15kV",          "LOC-LAB-A203", "场发射扫描电子显微镜"),
        ("EQ-TEMPL-DSC",           "差示扫描量热仪",    "equipment.analysis",        "Q2000",       "TA Instruments",   "-90~550度",            "LOC-LAB-A203", "差示扫描量热仪"),
        ("EQ-TEMPL-TGA",           "热重分析仪",        "equipment.analysis",        "Q500",        "TA Instruments",   "室温~1000度",          "LOC-LAB-A203", "热重分析仪"),
        ("EQ-TEMPL-GLOVEBOX",      "手套箱",            "equipment.safety",          "MIKROUNA",    "米开罗那",         "H2O/O2 <0.1ppm",       "LOC-LAB-A201", "惰性气氛手套箱"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}','{r[4]}','{r[5]}','{r[6]}','{r[7]}',TRUE)"
        for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.equipment_templates (template_code, name, category_code, model, "
        f"manufacturer, specification, default_location_id, description, is_active) "
        f"VALUES {values} ON CONFLICT (template_code) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# f. mdm.equipment_template_capabilities 设备模板-能力映射
# ──────────────────────────────────────────────────────────────────────────────
def _seed_equipment_template_capabilities() -> None:
    """为 4 个测试/表征设备模板建立能力映射。

    引用的能力（mdm.equipment_capabilities 已有 4 条）：
    range / accuracy / throughput / process_window
    """
    rows = [
        # (template_code, capability_code, min_value, max_value, nominal_value, notes)
        # EQ-TEMPL-BATTERY-TESTER 电池测试仪
        ("EQ-TEMPL-BATTERY-TESTER", "range",          0.0,    5.0,      3.7,    "电压量程 0-5V"),
        ("EQ-TEMPL-BATTERY-TESTER", "accuracy",       None,   0.1,      0.05,   "电流精度 0.1%"),
        ("EQ-TEMPL-BATTERY-TESTER", "throughput",     1.0,    64.0,     32.0,   "1-64 通道"),
        # EQ-TEMPL-EIS 电化学工作站
        ("EQ-TEMPL-EIS",            "range",          0.00001, 10000000.0, 10000.0, "频率 1e-5~1e7 Hz"),
        ("EQ-TEMPL-EIS",            "accuracy",       None,   0.1,      0.05,   "阻抗精度 0.1%"),
        ("EQ-TEMPL-EIS",            "process_window", -10.0,  120.0,    25.0,   "温度窗口 -10~120度"),
        # EQ-TEMPL-XRD X 射线衍射仪
        ("EQ-TEMPL-XRD",            "range",          5.0,    90.0,     30.0,   "2theta 5-90度"),
        ("EQ-TEMPL-XRD",            "accuracy",       None,   0.02,     0.01,   "测角精度 0.02度"),
        ("EQ-TEMPL-XRD",            "process_window", None,   40.0,     40.0,   "最大管压 40kV"),
        # EQ-TEMPL-SEM 扫描电镜
        ("EQ-TEMPL-SEM",            "range",          10.0,   300000.0, 10000.0, "放大倍数 10-300000x"),
        ("EQ-TEMPL-SEM",            "accuracy",       None,   1.0,      0.5,    "分辨率 1nm"),
        ("EQ-TEMPL-SEM",            "process_window", 1.0,    30.0,     15.0,   "加速电压 1-30kV"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}',{_sql_null_num(r[2])},{_sql_null_num(r[3])},{_sql_null_num(r[4])},'{r[5]}')"
        for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.equipment_template_capabilities (template_code, capability_code, "
        f"min_value, max_value, nominal_value, notes) "
        f"VALUES {values} ON CONFLICT (template_code, capability_code) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# g. mdm.inspection_capabilities 质检能力（每个 test_method 一条，共 6 条）
# ──────────────────────────────────────────────────────────────────────────────
def _seed_inspection_capabilities() -> None:
    """seed 6 条质检能力，每个 test_method 一条。

    引用 mdm.test_methods 已有 6 条：
    method.eis / method.half_cell / method.laser_diff /
    method.mercury_poro / method.rotational_vis / method.karl_fischer
    """
    rows = [
        # (capability_id, name, method_id, location_id, template_code, range_min, range_max, accuracy, detection_limit, unit, description)
        ("ICAP-EIS",          "EIS 离子电导率测试能力",   "method.eis",           "LOC-LAB-A202", "EQ-TEMPL-EIS",            0.0000001, 10000000.0, "0.1%", 0.0000001, "S/cm",  "电化学阻抗谱测离子电导率"),
        ("ICAP-HALF-CELL",    "半电池比容量测试能力",     "method.half_cell",     "LOC-LAB-A202", "EQ-TEMPL-BATTERY-TESTER", 0.0,       5000.0,     "0.05%", 0.1,       "mAh/g", "恒流充放电测比容量"),
        ("ICAP-LASER-DIFF",   "激光衍射粒径测试能力",     "method.laser_diff",    "LOC-LAB-A203", None,                      0.01,      2000.0,     "1%",    0.001,     "um",    "激光衍射法测粒径分布"),
        ("ICAP-MERCURY-PORO", "压汞孔隙率测试能力",       "method.mercury_poro",  "LOC-LAB-A203", None,                      0.001,     100.0,      "1%",    0.001,     "%",     "压汞法测孔隙率"),
        ("ICAP-ROT-VIS",      "旋转粘度测试能力",         "method.rotational_vis","LOC-LAB-A201", None,                      1.0,       10000000.0, "1%",    0.1,       "mPa.s", "旋转粘度计测粘度"),
        ("ICAP-KARL-FISCHER", "卡尔费休水分测试能力",     "method.karl_fischer",  "LOC-LAB-A201", None,                      0.0,       100.0,      "1%",    0.0001,    "%",     "卡尔费休法测水分"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}',{_sql_null(r[3])},{_sql_null(r[4])},"
        f"{_sql_null_num(r[5])},{_sql_null_num(r[6])},'{r[7]}',{_sql_null_num(r[8])},"
        f"{_sql_null(r[9])},'{r[10]}',TRUE)"
        for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.inspection_capabilities (capability_id, name, method_id, location_id, "
        f"template_code, range_min, range_max, accuracy, detection_limit, unit, description, is_active) "
        f"VALUES {values} ON CONFLICT (capability_id) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# h. mdm.process_routes 工艺路线
# ──────────────────────────────────────────────────────────────────────────────
def _seed_process_routes() -> None:
    """seed 5 条典型电池材料工艺路线。"""
    rows = [
        # (route_id, name, route_type, description, version)
        ("PR-ROUTE-LCO",      "钴酸锂正极工艺",     "cathode",   "LiCoO2 正极材料合成与电芯制备工艺", "v1"),
        ("PR-ROUTE-NCM",      "三元材料正极工艺",   "cathode",   "NCM 三元正极材料合成与电芯制备工艺", "v1"),
        ("PR-ROUTE-LFP",      "磷酸铁锂正极工艺",   "cathode",   "LiFePO4 正极材料合成与电芯制备工艺", "v1"),
        ("PR-ROUTE-GRAPHITE", "石墨负极工艺",       "anode",     "石墨负极材料处理与电芯制备工艺",     "v1"),
        ("PR-ROUTE-SEPARATOR","隔膜工艺",           "separator", "聚烯烃隔膜制备工艺",                 "v1"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}','{r[4]}',TRUE)" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.process_routes (route_id, name, route_type, description, version, is_active) "
        f"VALUES {values} ON CONFLICT (route_id) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# i. mdm.process_route_steps 工艺路线-步骤映射
# 引用 mdm.process_steps 已有 9 个步骤
# ──────────────────────────────────────────────────────────────────────────────
def _seed_process_route_steps() -> None:
    """为每条工艺路线建立步骤映射，step_order 唯一。"""
    rows = [
        # (route_id, step_id, step_order, notes)
        # PR-ROUTE-LCO 钴酸锂正极（全 9 步）
        ("PR-ROUTE-LCO", "step.mixing",       1, "活性物质/导电剂/粘结剂混料"),
        ("PR-ROUTE-LCO", "step.dispersion",   2, "浆料分散"),
        ("PR-ROUTE-LCO", "step.coating",      3, "涂布到铝箔"),
        ("PR-ROUTE-LCO", "step.drying",       4, "干燥去除溶剂"),
        ("PR-ROUTE-LCO", "step.rolling",      5, "辊压压实"),
        ("PR-ROUTE-LCO", "step.sintering",    6, "材料烧结"),
        ("PR-ROUTE-LCO", "step.assembly",     7, "电芯装配"),
        ("PR-ROUTE-LCO", "step.formation",    8, "化成活化"),
        ("PR-ROUTE-LCO", "step.cycling_test", 9, "循环性能测试"),
        # PR-ROUTE-NCM 三元正极（全 9 步）
        ("PR-ROUTE-NCM", "step.mixing",       1, "三元材料混料"),
        ("PR-ROUTE-NCM", "step.dispersion",   2, "浆料分散"),
        ("PR-ROUTE-NCM", "step.coating",      3, "涂布到铝箔"),
        ("PR-ROUTE-NCM", "step.drying",       4, "干燥"),
        ("PR-ROUTE-NCM", "step.rolling",      5, "辊压"),
        ("PR-ROUTE-NCM", "step.sintering",    6, "三元前驱体烧结"),
        ("PR-ROUTE-NCM", "step.assembly",     7, "电芯装配"),
        ("PR-ROUTE-NCM", "step.formation",    8, "化成"),
        ("PR-ROUTE-NCM", "step.cycling_test", 9, "循环测试"),
        # PR-ROUTE-LFP 磷酸铁锂正极（全 9 步）
        ("PR-ROUTE-LFP", "step.mixing",       1, "磷酸铁锂混料"),
        ("PR-ROUTE-LFP", "step.dispersion",   2, "浆料分散"),
        ("PR-ROUTE-LFP", "step.coating",      3, "涂布到铝箔"),
        ("PR-ROUTE-LFP", "step.drying",       4, "干燥"),
        ("PR-ROUTE-LFP", "step.rolling",      5, "辊压"),
        ("PR-ROUTE-LFP", "step.sintering",    6, "磷酸铁锂烧结"),
        ("PR-ROUTE-LFP", "step.assembly",     7, "电芯装配"),
        ("PR-ROUTE-LFP", "step.formation",    8, "化成"),
        ("PR-ROUTE-LFP", "step.cycling_test", 9, "循环测试"),
        # PR-ROUTE-GRAPHITE 石墨负极（8 步，无烧结）
        ("PR-ROUTE-GRAPHITE", "step.mixing",       1, "石墨负极混料"),
        ("PR-ROUTE-GRAPHITE", "step.dispersion",   2, "浆料分散"),
        ("PR-ROUTE-GRAPHITE", "step.coating",      3, "涂布到铜箔"),
        ("PR-ROUTE-GRAPHITE", "step.drying",       4, "干燥"),
        ("PR-ROUTE-GRAPHITE", "step.rolling",      5, "辊压"),
        ("PR-ROUTE-GRAPHITE", "step.assembly",     6, "电芯装配"),
        ("PR-ROUTE-GRAPHITE", "step.formation",    7, "化成"),
        ("PR-ROUTE-GRAPHITE", "step.cycling_test", 8, "循环测试"),
        # PR-ROUTE-SEPARATOR 隔膜（5 步）
        ("PR-ROUTE-SEPARATOR", "step.mixing",    1, "原料混合熔融"),
        ("PR-ROUTE-SEPARATOR", "step.coating",   2, "流延成膜涂布"),
        ("PR-ROUTE-SEPARATOR", "step.drying",    3, "溶剂干燥"),
        ("PR-ROUTE-SEPARATOR", "step.rolling",   4, "纵向/横向拉伸"),
        ("PR-ROUTE-SEPARATOR", "step.sintering", 5, "热定型"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}',{r[2]},'{r[3]}')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.process_route_steps (route_id, step_id, step_order, notes) "
        f"VALUES {values} ON CONFLICT (route_id, step_id) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# j. mdm.process_step_parameters 工艺步骤-参数映射
# 引用 mdm.process_parameters 已有 8 个参数
# ──────────────────────────────────────────────────────────────────────────────
def _seed_process_step_parameters() -> None:
    """为工艺步骤建立参数映射（默认值/区间/控制级别）。"""
    rows = [
        # (step_id, parameter_id, default_value, min_value, max_value, control_level, notes)
        # step.mixing 混料
        ("step.mixing", "param.temperature",     25.0,  0.0,   80.0,   "normal",   "混料温度"),
        ("step.mixing", "param.time",            2.0,   0.5,   8.0,    "normal",   "混料时间"),
        ("step.mixing", "param.rotation_speed",  300.0, 50.0,  800.0,  "critical", "搅拌转速"),
        ("step.mixing", "param.solid_content",   60.0,  30.0,  80.0,   "critical", "浆料固含量"),
        # step.dispersion 分散
        ("step.dispersion", "param.time",           1.0,   0.5,   4.0,    "normal",   "分散时间"),
        ("step.dispersion", "param.rotation_speed", 500.0, 100.0, 1500.0, "critical", "分散转速"),
        ("step.dispersion", "param.solid_content",  55.0,  30.0,  75.0,   "normal",   "分散固含量"),
        # step.coating 涂布
        ("step.coating", "param.coating_weight", 10.0, 5.0,  30.0,  "critical", "涂布量"),
        ("step.coating", "param.solid_content",  55.0, 40.0, 70.0,  "normal",   "涂布浆料固含量"),
        ("step.coating", "param.temperature",    25.0, 15.0, 40.0,  "normal",   "涂布温度"),
        # step.drying 干燥
        ("step.drying", "param.temperature", 80.0,  40.0,  150.0, "critical", "干燥温度"),
        ("step.drying", "param.time",        4.0,   1.0,   24.0,  "normal",   "干燥时间"),
        ("step.drying", "param.vacuum",      10.0,  0.1,   101.3, "normal",   "真空度（绝对压力）"),
        # step.rolling 辊压
        ("step.rolling", "param.pressure",            50.0, 10.0, 200.0, "critical", "辊压压力"),
        ("step.rolling", "param.compaction_density",  2.5,  1.5,  4.5,   "critical", "压实密度"),
        ("step.rolling", "param.time",                0.5,  0.1,  2.0,   "normal",   "辊压时间"),
        # step.sintering 烧结
        ("step.sintering", "param.temperature", 800.0, 300.0, 1200.0, "critical", "烧结温度"),
        ("step.sintering", "param.time",        8.0,   1.0,   24.0,   "critical", "烧结时间"),
        # step.assembly 装配
        ("step.assembly", "param.pressure", 1.0,   0.1, 5.0, "normal", "装配压力"),
        ("step.assembly", "param.time",     0.5,   0.1, 2.0, "normal", "装配时间"),
        # step.formation 化成
        ("step.formation", "param.time",        24.0, 1.0,  72.0, "critical", "化成时间"),
        ("step.formation", "param.temperature", 30.0, 15.0, 60.0, "normal",   "化成温度"),
        # step.cycling_test 循环测试
        ("step.cycling_test", "param.time",        100.0, 1.0,   1000.0, "normal",   "循环测试时长"),
        ("step.cycling_test", "param.temperature", 25.0,  -20.0, 60.0,   "critical", "测试温度"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}',{_sql_null_num(r[2])},{_sql_null_num(r[3])},{_sql_null_num(r[4])},'{r[5]}','{r[6]}')"
        for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.process_step_parameters (step_id, parameter_id, default_value, "
        f"min_value, max_value, control_level, notes) "
        f"VALUES {values} ON CONFLICT (step_id, parameter_id) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# k. mdm.process_step_equipment_templates 工艺步骤-设备模板映射
# ──────────────────────────────────────────────────────────────────────────────
def _seed_process_step_equipment_templates() -> None:
    """为工艺步骤与设备模板建立映射。"""
    rows = [
        # (step_id, template_code, is_preferred, notes)
        ("step.mixing",       "EQ-TEMPL-BALL-MILL",     True,  "行星球磨机混料"),
        ("step.mixing",       "EQ-TEMPL-REACTOR",       False, "反应釜辅助混料"),
        ("step.dispersion",   "EQ-TEMPL-BALL-MILL",     True,  "球磨分散"),
        ("step.coating",      "EQ-TEMPL-COATER",        True,  "自动涂布机涂布"),
        ("step.drying",       "EQ-TEMPL-OVEN",          True,  "真空烘箱干燥"),
        ("step.drying",       "EQ-TEMPL-FURNACE",       False, "高温炉辅助干燥"),
        ("step.rolling",      "EQ-TEMPL-PRESS",         True,  "液压对辊机辊压"),
        ("step.sintering",    "EQ-TEMPL-FURNACE",       True,  "马弗炉烧结"),
        ("step.assembly",     "EQ-TEMPL-COIN-CELL",     True,  "扣式电池装配"),
        ("step.assembly",     "EQ-TEMPL-GLOVEBOX",      False, "手套箱内装配"),
        ("step.formation",    "EQ-TEMPL-BATTERY-TESTER",True,  "电池测试仪化成"),
        ("step.formation",    "EQ-TEMPL-GLOVEBOX",      False, "惰性气氛化成"),
        ("step.cycling_test", "EQ-TEMPL-BATTERY-TESTER",True,  "电池测试仪循环测试"),
        ("step.cycling_test", "EQ-TEMPL-EIS",           False, "电化学工作站辅助测试"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}',{_sql_bool(r[2])},'{r[3]}')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.process_step_equipment_templates (step_id, template_code, "
        f"is_preferred, notes) "
        f"VALUES {values} ON CONFLICT (step_id, template_code) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 工具
# ──────────────────────────────────────────────────────────────────────────────
def _sql_null(v) -> str:
    """Python None → SQL NULL；字符串值加单引号。"""
    if v is None:
        return "NULL"
    return f"'{v}'"


def _sql_null_num(v) -> str:
    """Python None → SQL NULL；数值转字符串不加引号。"""
    if v is None:
        return "NULL"
    return str(v)


def _sql_bool(v: bool) -> str:
    return "TRUE" if v else "FALSE"
