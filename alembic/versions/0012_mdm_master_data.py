"""P2 物料/样品类型/设备模板/位置主数据：新建 9 张表。

新建：
- mdm.sample_types 样品类型模板
- mdm.sample_status_transitions 样品状态迁移规则
- mdm.locations 位置层级
- mdm.containers 容器与包装
- mdm.logistics_types 物流类型
- mdm.equipment_templates 设备模板
- mdm.equipment_capabilities 设备能力
- mdm.equipment_template_capabilities 设备模板↔能力 M:N
- mdm.material_categories 物料分类治理（扩展 classifications）

数据迁移：seed 样品类型/状态迁移/物流类型/设备能力/物料分类扩展。

Revision ID: 0012_mdm_master_data
Revises: 0011_mdm_reference_dict
Create Date: 2026-07-27

详见 .trae/specs/mdm-governance/spec.md
"""
from __future__ import annotations

from alembic import op

revision = "0012_mdm_master_data"
down_revision = "0011_mdm_reference_dict"
branch_labels = None
depends_on = None


# ──────────────────────────────────────────────────────────────────────────────
# upgrade
# ──────────────────────────────────────────────────────────────────────────────
def upgrade() -> None:
    # 1. 创建 9 张表
    _create_sample_types()
    _create_sample_status_transitions()
    _create_locations()
    _create_containers()
    _create_logistics_types()
    _create_equipment_templates()
    _create_equipment_capabilities()
    _create_equipment_template_capabilities()
    _create_material_categories()

    # 2. 数据迁移
    _seed_sample_types()
    _seed_sample_status_transitions()
    _seed_logistics_types()
    _seed_equipment_capabilities()
    _seed_material_categories()


# ──────────────────────────────────────────────────────────────────────────────
# downgrade
# ──────────────────────────────────────────────────────────────────────────────
def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mdm.material_categories")
    op.execute("DROP TABLE IF EXISTS mdm.equipment_template_capabilities")
    op.execute("DROP TABLE IF EXISTS mdm.equipment_capabilities")
    op.execute("DROP TABLE IF EXISTS mdm.equipment_templates")
    op.execute("DROP TABLE IF EXISTS mdm.logistics_types")
    op.execute("DROP TABLE IF EXISTS mdm.containers")
    op.execute("DROP TABLE IF EXISTS mdm.locations")
    op.execute("DROP TABLE IF EXISTS mdm.sample_status_transitions")
    op.execute("DROP TABLE IF EXISTS mdm.sample_types")


# ──────────────────────────────────────────────────────────────────────────────
# 建表
# ──────────────────────────────────────────────────────────────────────────────
def _create_sample_types() -> None:
    """样品类型模板：原料样/配方样/中间体/成品样/留样/对照样/失效样。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.sample_types (
            type_code                TEXT PRIMARY KEY,
            name                     TEXT NOT NULL,
            description              TEXT DEFAULT '',
            default_storage_conditions TEXT DEFAULT '',
            default_retention_days   INTEGER DEFAULT 0,
            is_hazardous             BOOLEAN DEFAULT FALSE,
            sort_order               INTEGER DEFAULT 0,
            is_active                BOOLEAN DEFAULT TRUE,
            created_at               TIMESTAMPTZ DEFAULT NOW(),
            updated_at               TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sample_types_active ON mdm.sample_types(is_active)"
    )


def _create_sample_status_transitions() -> None:
    """样品状态迁移规则：from→to 是否允许，是否需要审批。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.sample_status_transitions (
            id               SERIAL PRIMARY KEY,
            from_status      TEXT NOT NULL,
            to_status        TEXT NOT NULL,
            is_allowed       BOOLEAN DEFAULT TRUE,
            requires_approval BOOLEAN DEFAULT FALSE,
            description      TEXT DEFAULT '',
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (from_status, to_status)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sample_status_trans_from ON mdm.sample_status_transitions(from_status)"
    )


def _create_locations() -> None:
    """位置层级：园区/实验室/库房/货架/库位/冰箱/工位。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.locations (
            location_id      TEXT PRIMARY KEY,
            parent_id        TEXT,
            location_type    TEXT NOT NULL,
            name             TEXT NOT NULL,
            full_path        TEXT DEFAULT '',
            capacity         INTEGER DEFAULT 0,
            description      TEXT DEFAULT '',
            is_active        BOOLEAN DEFAULT TRUE,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_locations_parent FOREIGN KEY (parent_id)
                REFERENCES mdm.locations(location_id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_locations_parent ON mdm.locations(parent_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_locations_type ON mdm.locations(location_type)"
    )


def _create_containers() -> None:
    """容器与包装主数据。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.containers (
            container_code           TEXT PRIMARY KEY,
            name                     TEXT NOT NULL,
            container_type           TEXT DEFAULT '',
            material                 TEXT DEFAULT '',
            capacity_value           DOUBLE PRECISION DEFAULT 0.0,
            capacity_unit            TEXT,
            is_hazardous_compatible  BOOLEAN DEFAULT FALSE,
            description              TEXT DEFAULT '',
            is_active                BOOLEAN DEFAULT TRUE,
            created_at               TIMESTAMPTZ DEFAULT NOW(),
            updated_at               TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_containers_unit FOREIGN KEY (capacity_unit)
                REFERENCES mdm.units(unit_code) ON DELETE RESTRICT
        )
        """
    )


def _create_logistics_types() -> None:
    """物流类型：收货/入库/出库/领用/转移/送检/退回/报废/盘点/外送。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.logistics_types (
            type_code        TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            direction        TEXT DEFAULT '',
            requires_approval BOOLEAN DEFAULT FALSE,
            description      TEXT DEFAULT '',
            sort_order       INTEGER DEFAULT 0,
            is_active        BOOLEAN DEFAULT TRUE,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_logistics_types_direction ON mdm.logistics_types(direction)"
    )


def _create_equipment_templates() -> None:
    """设备模板：分类/型号/规格/制造商。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.equipment_templates (
            template_code     TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            category_code     TEXT,
            model             TEXT DEFAULT '',
            manufacturer      TEXT DEFAULT '',
            specification     TEXT DEFAULT '',
            default_location_id TEXT,
            description       TEXT DEFAULT '',
            is_active         BOOLEAN DEFAULT TRUE,
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_eq_templates_category FOREIGN KEY (category_code)
                REFERENCES mdm.classifications(code) ON DELETE RESTRICT,
            CONSTRAINT fk_eq_templates_location FOREIGN KEY (default_location_id)
                REFERENCES mdm.locations(location_id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eq_templates_category ON mdm.equipment_templates(category_code)"
    )


def _create_equipment_capabilities() -> None:
    """设备能力：量程/精度/通量/工艺窗口。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.equipment_capabilities (
            capability_code   TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            capability_type   TEXT DEFAULT '',
            unit              TEXT,
            description       TEXT DEFAULT '',
            is_active         BOOLEAN DEFAULT TRUE,
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_eq_caps_unit FOREIGN KEY (unit)
                REFERENCES mdm.units(unit_code) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eq_caps_type ON mdm.equipment_capabilities(capability_type)"
    )


def _create_equipment_template_capabilities() -> None:
    """设备模板↔能力 M:N 关联，带 min/max/nominal 值。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.equipment_template_capabilities (
            id                SERIAL PRIMARY KEY,
            template_code     TEXT NOT NULL,
            capability_code   TEXT NOT NULL,
            min_value         DOUBLE PRECISION,
            max_value         DOUBLE PRECISION,
            nominal_value     DOUBLE PRECISION,
            notes             TEXT DEFAULT '',
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_etc_template FOREIGN KEY (template_code)
                REFERENCES mdm.equipment_templates(template_code) ON DELETE CASCADE,
            CONSTRAINT fk_etc_capability FOREIGN KEY (capability_code)
                REFERENCES mdm.equipment_capabilities(capability_code) ON DELETE CASCADE,
            UNIQUE (template_code, capability_code)
        )
        """
    )


def _create_material_categories() -> None:
    """物料分类治理：扩展 classifications，补充物料专属字段。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.material_categories (
            category_code              TEXT PRIMARY KEY,
            default_unit               TEXT,
            default_storage_conditions TEXT DEFAULT '',
            default_retention_days     INTEGER DEFAULT 0,
            is_hazardous               BOOLEAN DEFAULT FALSE,
            description                TEXT DEFAULT '',
            created_at                 TIMESTAMPTZ DEFAULT NOW(),
            updated_at                 TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_mat_cat_code FOREIGN KEY (category_code)
                REFERENCES mdm.classifications(code) ON DELETE RESTRICT,
            CONSTRAINT fk_mat_cat_unit FOREIGN KEY (default_unit)
                REFERENCES mdm.units(unit_code) ON DELETE RESTRICT
        )
        """
    )


# ──────────────────────────────────────────────────────────────────────────────
# 数据迁移
# ──────────────────────────────────────────────────────────────────────────────
def _seed_sample_types() -> None:
    """seed 7 种样品类型。"""
    rows = [
        ("raw_material",  "原料样",   "从原料批次取样",        "常温干燥",     365, False, 10),
        ("formulation",   "配方样",   "按配方制备的样品",      "常温干燥",     180, False, 20),
        ("intermediate",  "中间体",   "工艺过程中的中间产物",  "常温干燥",      90, False, 30),
        ("finished",      "成品样",   "最终成品",              "常温干燥",     365, False, 40),
        ("retained",      "留样",     "保留备查样品",          "常温干燥",     730, False, 50),
        ("reference",     "对照样",   "用于对比的对照样品",    "常温干燥",     365, False, 60),
        ("expired",       "失效样",   "已过期或失效的样品",    "常温干燥",     180, False, 70),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},{'TRUE' if r[5] else 'FALSE'},"
        f"{r[6]},TRUE)" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.sample_types (type_code, name, description, default_storage_conditions, "
        f"default_retention_days, is_hazardous, sort_order, is_active) "
        f"VALUES {values} ON CONFLICT (type_code) DO NOTHING"
    )


def _seed_sample_status_transitions() -> None:
    """seed 样品状态迁移规则，基于 SampleStatus 枚举。"""
    rows = [
        # (from_status, to_status, is_allowed, requires_approval, description)
        ("created",    "in_storage", True,  False, "创建后入库"),
        ("in_storage", "in_use",     True,  False, "出库使用"),
        ("in_use",     "in_storage", True,  False, "使用后回库"),
        ("in_use",     "consumed",   True,  False, "使用耗尽"),
        ("in_storage", "discarded",  True,  True,  "丢弃需审批"),
        ("in_use",     "discarded",  True,  True,  "丢弃需审批"),
        ("in_storage", "proposed",   True,  False, "提议复检"),
        ("proposed",   "in_storage", True,  False, "复检后回库"),
        ("proposed",   "discarded",  True,  True,  "复检后丢弃需审批"),
        ("discarded",  "created",    False, False, "不可逆"),
        ("consumed",   "created",    False, False, "不可逆"),
        ("consumed",   "in_storage", False, False, "不可逆"),
        ("discarded",  "in_storage", False, False, "不可逆"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}',{_sql_bool(r[2])},{_sql_bool(r[3])},'{r[4]}')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.sample_status_transitions (from_status, to_status, is_allowed, "
        f"requires_approval, description) "
        f"VALUES {values} ON CONFLICT (from_status, to_status) DO NOTHING"
    )


def _seed_logistics_types() -> None:
    """seed 10 种物流类型。"""
    rows = [
        ("receive",    "收货", "IN",       False, "供应商到货接收"),
        ("stock_in",   "入库", "IN",       False, "物料/样品入库"),
        ("stock_out",  "出库", "OUT",      False, "物料/样品出库"),
        ("issue",      "领用", "OUT",      False, "按需领用"),
        ("transfer",   "转移", "INTERNAL", False, "内部位置转移"),
        ("send_test",  "送检", "OUT",      False, "送外检/内检"),
        ("return",     "退回", "INTERNAL", False, "退回原位置"),
        ("scrap",      "报废", "OUT",      True,  "报废需审批"),
        ("inventory",  "盘点", "INTERNAL", False, "周期性盘点"),
        ("send_out",   "外送", "OUT",      True,  "外送外协需审批"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}',{_sql_bool(r[3])},'{r[4]}',{i*10},TRUE)"
        for i, r in enumerate(rows)
    )
    op.execute(
        f"INSERT INTO mdm.logistics_types (type_code, name, direction, requires_approval, "
        f"description, sort_order, is_active) "
        f"VALUES {values} ON CONFLICT (type_code) DO NOTHING"
    )


def _seed_equipment_capabilities() -> None:
    """seed 4 种设备能力类型。"""
    rows = [
        # (capability_code, name, capability_type, unit, description)
        ("range",            "量程",     "range",            None, "设备可测量的范围"),
        ("accuracy",         "精度",     "accuracy",         None, "设备测量精度"),
        ("throughput",       "通量",     "throughput",       None, "设备单位时间处理能力"),
        ("process_window",   "工艺窗口", "process_window",   None, "设备允许的工艺参数范围"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}',{_sql_null(r[3])},'{r[4]}',TRUE)" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.equipment_capabilities (capability_code, name, capability_type, "
        f"unit, description, is_active) "
        f"VALUES {values} ON CONFLICT (capability_code) DO NOTHING"
    )


def _seed_material_categories() -> None:
    """seed 物料分类扩展数据，关联 classifications 中 domain='material' 的 7 个子分类。"""
    rows = [
        # (category_code, default_unit, default_storage_conditions, default_retention_days, is_hazardous, description)
        ("material.raw_chemical", "kg",   "常温干燥通风",     365, False, "原料化学品默认 1 年保质期"),
        ("material.precursor",    "kg",   "常温干燥避光",     180, False, "前驱体默认 6 个月保质期"),
        ("material.solvent",      "L",    "常温阴凉通风",     365, False, "溶剂默认 1 年保质期"),
        ("material.reagent",      "g",    "常温干燥",         730, False, "试剂默认 2 年保质期"),
        ("material.auxiliary",    "kg",   "常温干燥",         365, False, "辅料默认 1 年保质期"),
        ("material.standard",     "g",    "常温干燥避光",    1825, False, "标准品默认 5 年保质期"),
        ("material.hazardous",    "kg",   "危险品柜内",       365, True,  "危险品需特殊存储"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}',{r[3]},{_sql_bool(r[4])},'{r[5]}')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.material_categories (category_code, default_unit, "
        f"default_storage_conditions, default_retention_days, is_hazardous, description) "
        f"VALUES {values} ON CONFLICT (category_code) DO NOTHING"
    )


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
