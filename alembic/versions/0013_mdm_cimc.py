"""P3 CIMC（特性-指标-方法-能力）模型：新建 5 张表。

新建：
- mdm.properties 特性
- mdm.test_items 指标项目
- mdm.test_methods 检测方法
- mdm.specifications 规格与判定
- mdm.inspection_capabilities 检查能力

关系：property 1→N test_items N→1 test_method 1→N inspection_capabilities。

Revision ID: 0013_mdm_cimc
Revises: 0012_mdm_master_data
Create Date: 2026-07-27

详见 .trae/specs/mdm-governance/spec.md
"""
from __future__ import annotations

from alembic import op

revision = "0013_mdm_cimc"
down_revision = "0012_mdm_master_data"
branch_labels = None
depends_on = None


# ──────────────────────────────────────────────────────────────────────────────
# upgrade
# ──────────────────────────────────────────────────────────────────────────────
def upgrade() -> None:
    # 1. 创建 5 张表
    _create_properties()
    _create_test_methods()
    _create_test_items()
    _create_specifications()
    _create_inspection_capabilities()

    # 2. 数据迁移
    _seed_missing_units()
    _seed_properties()
    _seed_test_methods()
    _seed_test_items()
    _seed_specifications()


# ──────────────────────────────────────────────────────────────────────────────
# downgrade
# ──────────────────────────────────────────────────────────────────────────────
def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mdm.inspection_capabilities")
    op.execute("DROP TABLE IF EXISTS mdm.specifications")
    op.execute("DROP TABLE IF EXISTS mdm.test_items")
    op.execute("DROP TABLE IF EXISTS mdm.test_methods")
    op.execute("DROP TABLE IF EXISTS mdm.properties")


# ──────────────────────────────────────────────────────────────────────────────
# 建表
# ──────────────────────────────────────────────────────────────────────────────
def _create_properties() -> None:
    """特性主数据：离子电导率/比容量/粒径/孔隙率等。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.properties (
            property_id      TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            property_type    TEXT DEFAULT '',
            default_unit     TEXT,
            description      TEXT DEFAULT '',
            sort_order       INTEGER DEFAULT 0,
            is_active        BOOLEAN DEFAULT TRUE,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_properties_unit FOREIGN KEY (default_unit)
                REFERENCES mdm.units(unit_code) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_properties_type ON mdm.properties(property_type)"
    )


def _create_test_methods() -> None:
    """检测方法主数据：标准编号/SOP版本/制备要求/计算公式。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.test_methods (
            method_id          TEXT PRIMARY KEY,
            name               TEXT NOT NULL,
            standard_code      TEXT,
            sop_version        TEXT DEFAULT '',
            preparation_req    TEXT DEFAULT '',
            calculation_formula TEXT DEFAULT '',
            description        TEXT DEFAULT '',
            is_active          BOOLEAN DEFAULT TRUE,
            created_at         TIMESTAMPTZ DEFAULT NOW(),
            updated_at         TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_methods_standard FOREIGN KEY (standard_code)
                REFERENCES mdm.standards(standard_code) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_methods_standard ON mdm.test_methods(standard_code)"
    )


def _create_test_items() -> None:
    """指标项目：property 1→N test_items N→1 test_method。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.test_items (
            item_id          TEXT PRIMARY KEY,
            property_id      TEXT NOT NULL,
            name             TEXT NOT NULL,
            test_method_id   TEXT,
            condition_text   TEXT DEFAULT '',
            default_unit     TEXT,
            sort_order       INTEGER DEFAULT 0,
            is_active        BOOLEAN DEFAULT TRUE,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_items_property FOREIGN KEY (property_id)
                REFERENCES mdm.properties(property_id) ON DELETE RESTRICT,
            CONSTRAINT fk_items_method FOREIGN KEY (test_method_id)
                REFERENCES mdm.test_methods(method_id) ON DELETE SET NULL,
            CONSTRAINT fk_items_unit FOREIGN KEY (default_unit)
                REFERENCES mdm.units(unit_code) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_items_property ON mdm.test_items(property_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_items_method ON mdm.test_items(test_method_id)"
    )


def _create_specifications() -> None:
    """规格与判定：目标值/上下限/判定逻辑。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.specifications (
            spec_id          TEXT PRIMARY KEY,
            item_id          TEXT NOT NULL,
            target_value     DOUBLE PRECISION,
            min_value        DOUBLE PRECISION,
            max_value        DOUBLE PRECISION,
            unit             TEXT,
            judgment_logic   TEXT DEFAULT '',
            description      TEXT DEFAULT '',
            is_active        BOOLEAN DEFAULT TRUE,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_specs_item FOREIGN KEY (item_id)
                REFERENCES mdm.test_items(item_id) ON DELETE CASCADE,
            CONSTRAINT fk_specs_unit FOREIGN KEY (unit)
                REFERENCES mdm.units(unit_code) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_specs_item ON mdm.specifications(item_id)"
    )


def _create_inspection_capabilities() -> None:
    """检查能力：实验室+设备→方法，量程/精度/检测限。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.inspection_capabilities (
            capability_id    TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            method_id        TEXT NOT NULL,
            location_id      TEXT,
            template_code    TEXT,
            range_min        DOUBLE PRECISION,
            range_max        DOUBLE PRECISION,
            accuracy         TEXT DEFAULT '',
            detection_limit  DOUBLE PRECISION,
            unit             TEXT,
            description      TEXT DEFAULT '',
            is_active        BOOLEAN DEFAULT TRUE,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_ins_caps_method FOREIGN KEY (method_id)
                REFERENCES mdm.test_methods(method_id) ON DELETE RESTRICT,
            CONSTRAINT fk_ins_caps_location FOREIGN KEY (location_id)
                REFERENCES mdm.locations(location_id) ON DELETE SET NULL,
            CONSTRAINT fk_ins_caps_template FOREIGN KEY (template_code)
                REFERENCES mdm.equipment_templates(template_code) ON DELETE SET NULL,
            CONSTRAINT fk_ins_caps_unit FOREIGN KEY (unit)
                REFERENCES mdm.units(unit_code) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ins_caps_method ON mdm.inspection_capabilities(method_id)"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 数据迁移
# ──────────────────────────────────────────────────────────────────────────────
def _seed_missing_units() -> None:
    """补充 CIMC 用到的缺失单位到 mdm.units。"""
    rows = [
        # (unit_code, name, symbol, dimension, is_base)
        ("um",    "微米",       "um",    "length",            False),
        ("%",     "百分比",     "%",     "percentage",        True),
        ("mPa.s", "毫帕秒",     "mPa.s", "viscosity",         True),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{_sql_bool(r[4])},TRUE)" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.units (unit_code, name, symbol, dimension, is_base, is_active) "
        f"VALUES {values} ON CONFLICT (unit_code) DO NOTHING"
    )


def _seed_properties() -> None:
    """seed 8 种特性。"""
    rows = [
        # (property_id, name, property_type, default_unit, description, sort_order)
        ("prop.ionic_conductivity", "离子电导率", "electrochemical", "S/cm",  "电解质离子传导能力", 10),
        ("prop.specific_capacity",  "比容量",     "electrochemical", "mAh/g", "单位质量储电能力",   20),
        ("prop.particle_size",      "粒径",       "morphological",   "um",    "颗粒大小分布",       30),
        ("prop.porosity",           "孔隙率",     "morphological",   "%",     "孔隙体积占比",       40),
        ("prop.viscosity",          "粘度",       "physical",        "mPa.s", "流体流动阻力",       50),
        ("prop.ph",                 "pH值",       "chemical",        None,    "酸碱度",             60),
        ("prop.density",            "密度",       "physical",        "g/cm3", "单位体积质量",       70),
        ("prop.moisture",           "水分含量",   "chemical",        "%",     "含水比例",           80),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}',{_sql_null(r[3])},'{r[4]}',{r[5]},TRUE)" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.properties (property_id, name, property_type, default_unit, "
        f"description, sort_order, is_active) "
        f"VALUES {values} ON CONFLICT (property_id) DO NOTHING"
    )


def _seed_test_methods() -> None:
    """seed 检测方法。"""
    rows = [
        # (method_id, name, standard_code, sop_version, preparation_req, calculation_formula, description)
        ("method.eis",           "电化学阻抗谱法",  None, "v1.0", "样品制备为扣式电池", "sigma = L/(R_b * A)", "EIS 测离子电导率"),
        ("method.half_cell",     "半电池测试法",    None, "v1.0", "涂布极片装配扣电",   "C = I*t/m",            "恒流充放电测比容量"),
        ("method.laser_diff",    "激光衍射法",      None, "v1.0", "样品分散于水/乙醇",  "D50 = median(d)",      "粒径分布测试"),
        ("method.mercury_poro",  "压汞法",          None, "v1.0", "干燥样品",           "P = (4*gamma*cos(theta)/d)", "孔隙率测试"),
        ("method.rotational_vis","旋转粘度计法",    None, "v1.0", "样品恒温",           "eta = tau/gamma",      "粘度测试"),
        ("method.karl_fischer",  "卡尔费休法",      None, "v1.0", "样品密封",           "H2O% = V*F/m",         "水分含量测试"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}',{_sql_null(r[2])},'{r[3]}','{r[4]}','{r[5]}','{r[6]}',TRUE)" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.test_methods (method_id, name, standard_code, sop_version, "
        f"preparation_req, calculation_formula, description, is_active) "
        f"VALUES {values} ON CONFLICT (method_id) DO NOTHING"
    )


def _seed_test_items() -> None:
    """seed 指标项目：property 1→N test_items N→1 test_method。"""
    rows = [
        # (item_id, property_id, name, test_method_id, condition_text, default_unit, sort_order)
        ("item.ionic_cond_25c",    "prop.ionic_conductivity", "25℃离子电导率",     "method.eis",           "25℃恒温",       "S/cm",   10),
        ("item.ionic_cond_60c",    "prop.ionic_conductivity", "60℃离子电导率",     "method.eis",           "60℃恒温",       "S/cm",   20),
        ("item.spec_cap_01c",      "prop.specific_capacity",  "0.1C首圈比容量",    "method.half_cell",     "0.1C充放电",    "mAh/g",  10),
        ("item.spec_cap_1c",       "prop.specific_capacity",  "1C比容量",          "method.half_cell",     "1C充放电",      "mAh/g",  20),
        ("item.particle_d50",      "prop.particle_size",      "D50粒径",           "method.laser_diff",    "超声分散",      "um",     10),
        ("item.particle_d90",      "prop.particle_size",      "D90粒径",           "method.laser_diff",    "超声分散",      "um",     20),
        ("item.porosity_total",    "prop.porosity",           "总孔隙率",          "method.mercury_poro",  "干燥样品",      "%",      10),
        ("item.viscosity_25c",     "prop.viscosity",          "25℃粘度",           "method.rotational_vis","25℃恒温",       "mPa.s",  10),
        ("item.moisture_total",    "prop.moisture",           "总水分含量",        "method.karl_fischer",  "样品密封",      "%",      10),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}',{_sql_null(r[3])},'{r[4]}',{_sql_null(r[5])},{r[6]},TRUE)" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.test_items (item_id, property_id, name, test_method_id, "
        f"condition_text, default_unit, sort_order, is_active) "
        f"VALUES {values} ON CONFLICT (item_id) DO NOTHING"
    )


def _seed_specifications() -> None:
    """seed 规格与判定。"""
    rows = [
        # (spec_id, item_id, target_value, min_value, max_value, unit, judgment_logic, description)
        ("spec.ionic_cond_25c",   "item.ionic_cond_25c",  None, 1e-4,  None,  "S/cm",  "GE",        "离子电导率≥1e-4 S/cm"),
        ("spec.spec_cap_01c",     "item.spec_cap_01c",    None, 150.0, None,  "mAh/g", "GE",        "0.1C首圈比容量≥150 mAh/g"),
        ("spec.particle_d50",     "item.particle_d50",    5.0,  3.0,   8.0,   "um",    "RANGE",     "D50粒径 3-8 um"),
        ("spec.porosity_total",   "item.porosity_total",  None, 30.0,  50.0,  "%",     "RANGE",     "总孔隙率 30-50%"),
        ("spec.viscosity_25c",    "item.viscosity_25c",   None, 100.0, 500.0, "mPa.s", "RANGE",     "25℃粘度 100-500 mPa.s"),
        ("spec.moisture_total",   "item.moisture_total",  None, None,  0.01,  "%",     "LE",        "总水分≤0.01%"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}',{_sql_null_num(r[2])},{_sql_null_num(r[3])},{_sql_null_num(r[4])},"
        f"{_sql_null(r[5])},'{r[6]}','{r[7]}',TRUE)" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.specifications (spec_id, item_id, target_value, min_value, max_value, "
        f"unit, judgment_logic, description, is_active) "
        f"VALUES {values} ON CONFLICT (spec_id) DO NOTHING"
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
