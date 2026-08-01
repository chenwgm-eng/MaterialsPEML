"""P4 工艺路线-步骤-参数-设备能力模型：新建 6 张表。

新建：
- mdm.process_routes 工艺路线模板
- mdm.process_steps 工艺步骤模板
- mdm.process_parameters 工艺参数字典
- mdm.process_route_steps 路线↔步骤有序关联
- mdm.process_step_parameters 步骤↔参数关联
- mdm.process_step_equipment_templates 步骤↔设备模板 M:N

Revision ID: 0014_mdm_process
Revises: 0013_mdm_cimc
Create Date: 2026-07-27

详见 .trae/specs/mdm-governance/spec.md
"""
from __future__ import annotations

from alembic import op

revision = "0014_mdm_process"
down_revision = "0013_mdm_cimc"
branch_labels = None
depends_on = None


# ──────────────────────────────────────────────────────────────────────────────
# upgrade
# ──────────────────────────────────────────────────────────────────────────────
def upgrade() -> None:
    # 1. 创建 6 张表
    _create_process_routes()
    _create_process_steps()
    _create_process_parameters()
    _create_process_route_steps()
    _create_process_step_parameters()
    _create_process_step_equipment_templates()

    # 2. 数据迁移
    _seed_missing_units()
    _seed_process_steps()
    _seed_process_parameters()


# ──────────────────────────────────────────────────────────────────────────────
# downgrade
# ──────────────────────────────────────────────────────────────────────────────
def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mdm.process_step_equipment_templates")
    op.execute("DROP TABLE IF EXISTS mdm.process_step_parameters")
    op.execute("DROP TABLE IF EXISTS mdm.process_route_steps")
    op.execute("DROP TABLE IF EXISTS mdm.process_parameters")
    op.execute("DROP TABLE IF EXISTS mdm.process_steps")
    op.execute("DROP TABLE IF EXISTS mdm.process_routes")


# ──────────────────────────────────────────────────────────────────────────────
# 建表
# ──────────────────────────────────────────────────────────────────────────────
def _create_process_routes() -> None:
    """工艺路线模板。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.process_routes (
            route_id         TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            route_type       TEXT DEFAULT '',
            description      TEXT DEFAULT '',
            version          TEXT DEFAULT 'v1',
            is_active        BOOLEAN DEFAULT TRUE,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_process_routes_type ON mdm.process_routes(route_type)"
    )


def _create_process_steps() -> None:
    """工艺步骤模板：混料/分散/涂布/干燥/辊压/烧结/装配/化成/循环测试。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.process_steps (
            step_id          TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            step_type        TEXT DEFAULT '',
            description      TEXT DEFAULT '',
            sort_order       INTEGER DEFAULT 0,
            is_active        BOOLEAN DEFAULT TRUE,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_process_steps_type ON mdm.process_steps(step_type)"
    )


def _create_process_parameters() -> None:
    """工艺参数字典：温度/时间/转速/真空度/固含量/压实密度。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.process_parameters (
            parameter_id     TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            parameter_type   TEXT DEFAULT '',
            unit             TEXT,
            description      TEXT DEFAULT '',
            sort_order       INTEGER DEFAULT 0,
            is_active        BOOLEAN DEFAULT TRUE,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_proc_params_unit FOREIGN KEY (unit)
                REFERENCES mdm.units(unit_code) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_proc_params_type ON mdm.process_parameters(parameter_type)"
    )


def _create_process_route_steps() -> None:
    """路线↔步骤有序关联。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.process_route_steps (
            id               SERIAL PRIMARY KEY,
            route_id         TEXT NOT NULL,
            step_id          TEXT NOT NULL,
            step_order       INTEGER NOT NULL DEFAULT 0,
            notes            TEXT DEFAULT '',
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_prs_route FOREIGN KEY (route_id)
                REFERENCES mdm.process_routes(route_id) ON DELETE CASCADE,
            CONSTRAINT fk_prs_step FOREIGN KEY (step_id)
                REFERENCES mdm.process_steps(step_id) ON DELETE RESTRICT,
            UNIQUE (route_id, step_id),
            UNIQUE (route_id, step_order)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_prs_route ON mdm.process_route_steps(route_id)"
    )


def _create_process_step_parameters() -> None:
    """步骤↔参数关联（默认值/区间/控制级别）。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.process_step_parameters (
            id               SERIAL PRIMARY KEY,
            step_id          TEXT NOT NULL,
            parameter_id     TEXT NOT NULL,
            default_value    DOUBLE PRECISION,
            min_value        DOUBLE PRECISION,
            max_value        DOUBLE PRECISION,
            control_level    TEXT DEFAULT 'normal',
            notes            TEXT DEFAULT '',
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_psp_step FOREIGN KEY (step_id)
                REFERENCES mdm.process_steps(step_id) ON DELETE CASCADE,
            CONSTRAINT fk_psp_param FOREIGN KEY (parameter_id)
                REFERENCES mdm.process_parameters(parameter_id) ON DELETE CASCADE,
            UNIQUE (step_id, parameter_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_psp_step ON mdm.process_step_parameters(step_id)"
    )


def _create_process_step_equipment_templates() -> None:
    """步骤↔设备模板 M:N。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.process_step_equipment_templates (
            id               SERIAL PRIMARY KEY,
            step_id          TEXT NOT NULL,
            template_code    TEXT NOT NULL,
            is_preferred     BOOLEAN DEFAULT FALSE,
            notes            TEXT DEFAULT '',
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_pset_step FOREIGN KEY (step_id)
                REFERENCES mdm.process_steps(step_id) ON DELETE CASCADE,
            CONSTRAINT fk_pset_template FOREIGN KEY (template_code)
                REFERENCES mdm.equipment_templates(template_code) ON DELETE CASCADE,
            UNIQUE (step_id, template_code)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pset_step ON mdm.process_step_equipment_templates(step_id)"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 数据迁移
# ──────────────────────────────────────────────────────────────────────────────
def _seed_missing_units() -> None:
    """补充工艺参数用到的缺失单位。"""
    rows = [
        # (unit_code, name, symbol, dimension, is_base)
        ("mg/cm2", "毫克每平方厘米", "mg/cm2", "area_density", True),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',TRUE,TRUE)" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.units (unit_code, name, symbol, dimension, is_base, is_active) "
        f"VALUES {values} ON CONFLICT (unit_code) DO NOTHING"
    )


def _seed_process_steps() -> None:
    """seed 9 种工艺步骤。"""
    rows = [
        # (step_id, name, step_type, description, sort_order)
        ("step.mixing",        "混料",     "mixing",        "活性物质、导电剂、粘结剂混合",  10),
        ("step.dispersion",    "分散",     "dispersion",    "浆料均匀分散",                  20),
        ("step.coating",       "涂布",     "coating",       "浆料涂布到集流体",              30),
        ("step.drying",        "干燥",     "drying",        "去除溶剂",                      40),
        ("step.rolling",       "辊压",     "rolling",       "压实极片",                      50),
        ("step.sintering",     "烧结",     "sintering",     "高温烧结（固态电池）",          60),
        ("step.assembly",      "装配",     "assembly",      "电芯装配",                      70),
        ("step.formation",     "化成",     "formation",     "首次充放电活化",                80),
        ("step.cycling_test",  "循环测试", "cycling_test",  "循环性能测试",                  90),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE)" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.process_steps (step_id, name, step_type, description, "
        f"sort_order, is_active) "
        f"VALUES {values} ON CONFLICT (step_id) DO NOTHING"
    )


def _seed_process_parameters() -> None:
    """seed 8 种工艺参数。"""
    rows = [
        # (parameter_id, name, parameter_type, unit, description, sort_order)
        ("param.temperature",     "温度",     "environment", "C",     "工艺温度",         10),
        ("param.time",            "时间",     "duration",    "h",     "工艺持续时间",     20),
        ("param.rotation_speed",  "转速",     "mechanical",  "rpm",   "搅拌/辊压转速",    30),
        ("param.vacuum",          "真空度",   "environment", "kPa",   "真空度",           40),
        ("param.solid_content",   "固含量",   "composition", "%",     "浆料固含量",       50),
        ("param.compaction_density", "压实密度", "physical",  "g/cm3", "极片压实密度",     60),
        ("param.coating_weight",  "涂布量",   "physical",    "mg/cm2","单位面积涂布量",   70),
        ("param.pressure",        "压力",     "mechanical",  "MPa",   "辊压/装配压力",    80),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}','{r[4]}',{r[5]},TRUE)" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.process_parameters (parameter_id, name, parameter_type, "
        f"unit, description, sort_order, is_active) "
        f"VALUES {values} ON CONFLICT (parameter_id) DO NOTHING"
    )
