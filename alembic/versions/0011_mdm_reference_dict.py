"""P1 参考字典中心：统一状态码、分类码、单位、单位换算、方法标准、GHS 分类、通用维度。

新建 mdm schema 与 7 张表，迁移现有散落枚举值与 UnitConverter 硬编码换算因子入库。

Revision ID: 0011_mdm_reference_dict
Revises: 0010_builtin_agent_overrides
Create Date: 2026-07-27

详见 .trae/specs/mdm-governance/spec.md
"""
from __future__ import annotations

from alembic import op

revision = "0011_mdm_reference_dict"
down_revision = "0010_builtin_agent_overrides"
branch_labels = None
depends_on = None


# ──────────────────────────────────────────────────────────────────────────────
# upgrade
# ──────────────────────────────────────────────────────────────────────────────
def upgrade() -> None:
    # 1. 创建 schema
    op.execute("CREATE SCHEMA IF NOT EXISTS mdm")

    # 2. 创建 7 张表
    _create_status_codes()
    _create_classifications()
    _create_units()
    _create_unit_conversions()
    _create_standards()
    _create_ghs_classes()
    _create_dimensions()

    # 3. 数据迁移：现有散落枚举/单位换算入库
    _seed_status_codes()
    _seed_classifications()
    _seed_units_and_conversions()
    _seed_dimensions()


# ──────────────────────────────────────────────────────────────────────────────
# downgrade
# ──────────────────────────────────────────────────────────────────────────────
def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS mdm CASCADE")


# ──────────────────────────────────────────────────────────────────────────────
# 建表
# ──────────────────────────────────────────────────────────────────────────────
def _create_status_codes() -> None:
    """状态码主数据：跨域统一治理样品/设备/订单/任务等状态。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.status_codes (
            code_id          TEXT PRIMARY KEY,
            domain           TEXT NOT NULL,
            code             TEXT NOT NULL,
            label            TEXT NOT NULL,
            sort_order       INTEGER DEFAULT 0,
            is_active        BOOLEAN DEFAULT TRUE,
            description      TEXT DEFAULT '',
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (domain, code)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_status_codes_domain ON mdm.status_codes(domain)"
    )


def _create_classifications() -> None:
    """分类码树形主数据：物料分类/设备分类/实验类型/工艺类型/检测类型/偏差类型。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.classifications (
            code             TEXT PRIMARY KEY,
            domain           TEXT NOT NULL,
            parent_code      TEXT,
            label            TEXT NOT NULL,
            sort_order       INTEGER DEFAULT 0,
            is_active        BOOLEAN DEFAULT TRUE,
            description      TEXT DEFAULT '',
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_class_parent FOREIGN KEY (parent_code)
                REFERENCES mdm.classifications(code) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_class_domain ON mdm.classifications(domain)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_class_parent ON mdm.classifications(parent_code)"
    )


def _create_units() -> None:
    """标准单位主数据：按 dimension 分组（mass/volume/concentration/temperature/pressure/electrochemical）。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.units (
            unit_code        TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            symbol           TEXT NOT NULL,
            dimension        TEXT NOT NULL,
            is_base          BOOLEAN DEFAULT False,
            is_active        BOOLEAN DEFAULT TRUE,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_units_dimension ON mdm.units(dimension)"
    )


def _create_unit_conversions() -> None:
    """单位换算：value_in_to = value_in_from * factor + offset_value。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.unit_conversions (
            id               SERIAL PRIMARY KEY,
            from_unit        TEXT NOT NULL,
            to_unit          TEXT NOT NULL,
            factor           DOUBLE PRECISION DEFAULT 1.0,
            offset_value     DOUBLE PRECISION DEFAULT 0.0,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_conv_from FOREIGN KEY (from_unit)
                REFERENCES mdm.units(unit_code) ON DELETE RESTRICT,
            CONSTRAINT fk_conv_to FOREIGN KEY (to_unit)
                REFERENCES mdm.units(unit_code) ON DELETE RESTRICT,
            UNIQUE (from_unit, to_unit)
        )
        """
    )


def _create_standards() -> None:
    """方法标准主数据：国标/ISO/ASTM/IEC/企业标准/内部 SOP。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.standards (
            standard_code    TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            issuer           TEXT DEFAULT '',
            version          TEXT DEFAULT '',
            effective_date   DATE,
            is_active        BOOLEAN DEFAULT TRUE,
            description      TEXT DEFAULT '',
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_standards_issuer ON mdm.standards(issuer)"
    )


def _create_ghs_classes() -> None:
    """GHS 危害分类主数据。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.ghs_classes (
            ghs_code         TEXT PRIMARY KEY,
            label            TEXT NOT NULL,
            hazard_level     TEXT DEFAULT '',
            pictogram        TEXT DEFAULT '',
            is_active        BOOLEAN DEFAULT TRUE,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )


def _create_dimensions() -> None:
    """通用维度主数据：优先级/地区/项目类型/供应商类型/角色等。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.dimensions (
            dim_code         TEXT PRIMARY KEY,
            domain           TEXT NOT NULL,
            code             TEXT NOT NULL,
            label            TEXT NOT NULL,
            sort_order       INTEGER DEFAULT 0,
            is_active        BOOLEAN DEFAULT TRUE,
            description      TEXT DEFAULT '',
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (domain, code)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dimensions_domain ON mdm.dimensions(domain)"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 数据迁移：把现有散落枚举值入库
# ──────────────────────────────────────────────────────────────────────────────
def _seed_status_codes() -> None:
    """迁移散落在各模块的状态枚举到 mdm.status_codes。"""
    rows = [
        # sample (SampleStatus: CREATED/IN_STORAGE/IN_USE/CONSUMED/DISCARDED/PROPOSED)
        ("sample.created",        "sample",    "created",        "已创建",   10),
        ("sample.in_storage",     "sample",    "in_storage",     "在库",     20),
        ("sample.in_use",         "sample",    "in_use",         "在用",     30),
        ("sample.consumed",       "sample",    "consumed",       "已耗尽",   40),
        ("sample.discarded",      "sample",    "discarded",      "已丢弃",   50),
        ("sample.proposed",       "sample",    "proposed",       "已提议",   60),
        # equipment (EquipmentStatus: IDLE/IN_USE/MAINTENANCE/CALIBRATION/RETIRED)
        ("equipment.idle",        "equipment", "IDLE",           "空闲",     10),
        ("equipment.in_use",      "equipment", "IN_USE",         "在用",     20),
        ("equipment.maintenance", "equipment", "MAINTENANCE",    "维护中",   30),
        ("equipment.calibration", "equipment", "CALIBRATION",    "校准中",   40),
        ("equipment.retired",     "equipment", "RETIRED",        "已退役",   50),
        # order (ExperimentOrderStatus: DRAFT/PENDING_APPROVAL/APPROVED/SCHEDULED/IN_EXECUTION/WAITING_FOR_DATA/COMPLETED/CANCELLED/VALIDATION_FAILED)
        ("order.draft",                 "order", "DRAFT",              "草稿",         10),
        ("order.pending_approval",      "order", "PENDING_APPROVAL",   "待审批",       20),
        ("order.approved",              "order", "APPROVED",           "已审批",       30),
        ("order.scheduled",             "order", "SCHEDULED",          "已排程",       40),
        ("order.in_execution",          "order", "IN_EXECUTION",       "执行中",       50),
        ("order.waiting_for_data",      "order", "WAITING_FOR_DATA",   "等待数据",     60),
        ("order.completed",             "order", "COMPLETED",          "已完成",       70),
        ("order.cancelled",             "order", "CANCELLED",          "已取消",       80),
        ("order.validation_failed",     "order", "VALIDATION_FAILED",  "验证失败",     90),
        # test_task (复用 ExperimentOrderStatus 取值)
        ("test_task.draft",             "test_task", "DRAFT",              "草稿",         10),
        ("test_task.pending_approval",  "test_task", "PENDING_APPROVAL",   "待审批",       20),
        ("test_task.approved",          "test_task", "APPROVED",           "已审批",       30),
        ("test_task.scheduled",         "test_task", "SCHEDULED",          "已排程",       40),
        ("test_task.in_execution",      "test_task", "IN_EXECUTION",       "执行中",       50),
        ("test_task.waiting_for_data",  "test_task", "WAITING_FOR_DATA",   "等待数据",     60),
        ("test_task.completed",         "test_task", "COMPLETED",          "已完成",       70),
        ("test_task.cancelled",         "test_task", "CANCELLED",          "已取消",       80),
        ("test_task.validation_failed", "test_task", "VALIDATION_FAILED",  "验证失败",     90),
        # task (ProjectTask.status: draft/in_progress/completed/cancelled)
        ("task.draft",         "task", "draft",         "草稿",     10),
        ("task.in_progress",   "task", "in_progress",   "进行中",   20),
        ("task.completed",     "task", "completed",     "已完成",   30),
        ("task.cancelled",     "task", "cancelled",     "已取消",   40),
        # idea (IdeaStatus)
        ("idea.proposed",      "idea", "proposed",      "已提议",   10),
        ("idea.reviewing",     "idea", "reviewing",     "评审中",   20),
        ("idea.accepted",      "idea", "accepted",      "已采纳",   30),
        ("idea.rejected",      "idea", "rejected",      "已拒绝",   40),
        ("idea.archived",      "idea", "archived",      "已归档",   50),
        # material_request (RequestStatus: SUBMITTED/APPROVED/REJECTED/WRITTEN)
        ("material_request.submitted",  "material_request", "SUBMITTED",  "已提交",   10),
        ("material_request.approved",   "material_request", "APPROVED",   "已批准",   20),
        ("material_request.rejected",   "material_request", "REJECTED",   "已拒绝",   30),
        ("material_request.written",    "material_request", "WRITTEN",    "已入库",   40),
        # case (CaseStatus)
        ("case.open",          "case", "open",          "待处理",   10),
        ("case.in_review",     "case", "in_review",     "评审中",   20),
        ("case.approved",      "case", "approved",      "已批准",   30),
        ("case.rejected",      "case", "rejected",      "已拒绝",   40),
        ("case.cancelled",     "case", "cancelled",     "已取消",   50),
        # run (RunStatus)
        ("run.pending",        "run",  "pending",       "待执行",   10),
        ("run.running",        "run",  "running",       "运行中",   20),
        ("run.succeeded",      "run",  "succeeded",     "成功",     30),
        ("run.failed",         "run",  "failed",        "失败",     40),
        ("run.cancelled",      "run",  "cancelled",     "已取消",   50),
        # tool_health (ToolHealthStatus)
        ("tool_health.healthy",     "tool_health", "healthy",     "健康",     10),
        ("tool_health.degraded",    "tool_health", "degraded",    "降级",     20),
        ("tool_health.unhealthy",   "tool_health", "unhealthy",   "不健康",   30),
        ("tool_health.unknown",     "tool_health", "unknown",     "未知",     40),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.status_codes (code_id, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (code_id) DO NOTHING"
    )


def _seed_classifications() -> None:
    """迁移分类码：ExperimentType 8 项 + 物料分类 + 设备分类根节点。"""
    rows = [
        # experiment_type (ExperimentType: ionic_conductivity/xrd/sem/dsc/tga/eis/cv/electrochemical)
        ("experiment_type.ionic_conductivity", "experiment_type", None, "离子电导率测试",  10),
        ("experiment_type.xrd",                "experiment_type", None, "X 射线衍射",      20),
        ("experiment_type.sem",                "experiment_type", None, "扫描电镜",        30),
        ("experiment_type.dsc",                "experiment_type", None, "差示扫描量热",    40),
        ("experiment_type.tga",                "experiment_type", None, "热重分析",        50),
        ("experiment_type.eis",                "experiment_type", None, "电化学阻抗",      60),
        ("experiment_type.cv",                 "experiment_type", None, "循环伏安",        70),
        ("experiment_type.electrochemical",    "experiment_type", None, "电化学测试",      80),
        # material 根节点
        ("material",                          "material", None, "物料分类",         0),
        ("material.raw_chemical",             "material", "material", "原料化学品",  10),
        ("material.precursor",                "material", "material", "前驱体",      20),
        ("material.solvent",                  "material", "material", "溶剂",        30),
        ("material.reagent",                  "material", "material", "试剂",        40),
        ("material.auxiliary",                "material", "material", "辅料",        50),
        ("material.standard",                 "material", "material", "标准品",      60),
        ("material.hazardous",                "material", "material", "危险品",      70),
        # equipment 根节点
        ("equipment",                         "equipment", None, "设备分类",         0),
        ("equipment.preparation",             "equipment", "equipment", "制备设备",   10),
        ("equipment.mixing",                  "equipment", "equipment", "混料设备",   20),
        ("equipment.coating",                 "equipment", "equipment", "涂布设备",   30),
        ("equipment.rolling",                 "equipment", "equipment", "辊压设备",   40),
        ("equipment.sintering",               "equipment", "equipment", "烧结设备",   50),
        ("equipment.characterization",        "equipment", "equipment", "表征设备",   60),
        ("equipment.environment_control",     "equipment", "equipment", "环境控制",   70),
        ("equipment.safety",                  "equipment", "equipment", "安全设施",   80),
        # process_type 根节点
        ("process_type",                      "process_type", None, "工艺类型",       0),
        ("process_type.mixing",               "process_type", "process_type", "混料",  10),
        ("process_type.dispersion",           "process_type", "process_type", "分散",  20),
        ("process_type.coating",              "process_type", "process_type", "涂布",  30),
        ("process_type.drying",               "process_type", "process_type", "干燥",  40),
        ("process_type.rolling",              "process_type", "process_type", "辊压",  50),
        ("process_type.sintering",            "process_type", "process_type", "烧结",  60),
        ("process_type.assembly",             "process_type", "process_type", "装配",  70),
        ("process_type.formation",            "process_type", "process_type", "化成",  80),
        ("process_type.cycling_test",         "process_type", "process_type", "循环测试", 90),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}',{_sql_null(r[2])},'{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.classifications (code, domain, parent_code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (code) DO NOTHING"
    )


def _seed_units_and_conversions() -> None:
    """迁移 UnitConverter 硬编码换算到 mdm.units + mdm.unit_conversions。"""
    units = [
        # mass
        ("g",     "克",     "g",     "mass",            True),
        ("kg",    "千克",   "kg",    "mass",            False),
        ("mg",    "毫克",   "mg",    "mass",            False),
        # volume
        ("mL",    "毫升",   "mL",    "volume",          True),
        ("L",     "升",     "L",     "volume",          False),
        ("uL",    "微升",   "uL",    "volume",          False),
        # concentration
        ("mol/L", "摩尔每升", "mol/L", "concentration",  True),
        ("mg/mL", "毫克每毫升", "mg/mL", "concentration", False),
        # temperature
        ("K",     "开尔文", "K",     "temperature",     True),
        ("C",     "摄氏度", "C",     "temperature",     False),
        # pressure
        ("Pa",    "帕斯卡", "Pa",    "pressure",        True),
        ("kPa",   "千帕",   "kPa",   "pressure",        False),
        ("MPa",   "兆帕",   "MPa",   "pressure",        False),
        # electrochemical
        ("S/cm",  "西门子每厘米", "S/cm", "conductivity", True),
        ("mS/cm", "毫西门子每厘米", "mS/cm", "conductivity", False),
        ("V",     "伏特",   "V",     "voltage",         True),
        ("mV",    "毫伏",   "mV",    "voltage",         False),
        ("mAh/g", "毫安时每克", "mAh/g", "specific_capacity", True),
        ("Ah/kg", "安时每千克", "Ah/kg", "specific_capacity", False),
        ("eV",    "电子伏特", "eV",  "energy",          True),
        # density
        ("g/cm3", "克每立方厘米", "g/cm3", "density",    True),
        ("kg/m3", "千克每立方米", "kg/m3", "density",    False),
        # time
        ("s",     "秒",     "s",     "time",            True),
        ("min",   "分钟",   "min",   "time",            False),
        ("h",     "小时",   "h",     "time",            False),
        # rotational speed
        ("rpm",   "转每分钟", "rpm", "rotational_speed", True),
    ]
    values = ",".join(
        f"('{u[0]}','{u[1]}','{u[2]}','{u[3]}',{'TRUE' if u[4] else 'FALSE'},TRUE)" for u in units
    )
    op.execute(
        f"INSERT INTO mdm.units (unit_code, name, symbol, dimension, is_base, is_active) "
        f"VALUES {values} ON CONFLICT (unit_code) DO NOTHING"
    )

    # 单位换算：value_in_to = value_in_from * factor + offset
    conversions = [
        # mass: g 为 base
        ("kg",  "g",   1000.0, 0.0),
        ("mg",  "g",   0.001,  0.0),
        # volume: mL 为 base
        ("L",   "mL",  1000.0, 0.0),
        ("uL",  "mL",  0.001,  0.0),
        # temperature: K 为 base, C = K - 273.15 → value_in_K = (C + 273.15)
        ("C",   "K",   1.0,    273.15),
        # pressure: Pa 为 base
        ("kPa", "Pa",  1000.0, 0.0),
        ("MPa", "Pa",  1000000.0, 0.0),
        # conductivity: S/cm 为 base
        ("mS/cm", "S/cm", 0.001, 0.0),
        # voltage: V 为 base
        ("mV", "V", 0.001, 0.0),
        # specific_capacity: mAh/g 为 base
        ("Ah/kg", "mAh/g", 1.0, 0.0),  # 1 Ah/kg = 1 mAh/g
        # density: g/cm3 为 base
        ("kg/m3", "g/cm3", 0.001, 0.0),  # 1 kg/m3 = 0.001 g/cm3
        # time: s 为 base
        ("min", "s", 60.0, 0.0),
        ("h",   "s", 3600.0, 0.0),
    ]
    if conversions:
        values = ",".join(
            f"('{c[0]}','{c[1]}',{c[2]},{c[3]})" for c in conversions
        )
        op.execute(
            f"INSERT INTO mdm.unit_conversions (from_unit, to_unit, factor, offset_value) "
            f"VALUES {values} ON CONFLICT (from_unit, to_unit) DO NOTHING"
        )


def _seed_dimensions() -> None:
    """迁移通用维度：优先级/项目类型/目标应用等。"""
    rows = [
        # priority (P0/P1/P2/P3)
        ("priority.P0", "priority", "P0", "P0 紧急",  10),
        ("priority.P1", "priority", "P1", "P1 高",    20),
        ("priority.P2", "priority", "P2", "P2 中",    30),
        ("priority.P3", "priority", "P3", "P3 低",    40),
        # project_type
        ("project_type.research",       "project_type", "research",       "研发项目",     10),
        ("project_type.engineering",    "project_type", "engineering",    "工程项目",     20),
        ("project_type.production",     "project_type", "production",     "生产项目",     30),
        ("project_type.collaboration",  "project_type", "collaboration",  "协作项目",     40),
        # target_application (Project.target_application: 动力/储能/消费)
        ("target_application.power",        "target_application", "power",        "动力",     10),
        ("target_application.energy_storage", "target_application", "energy_storage", "储能",  20),
        ("target_application.consumer",     "target_application", "consumer",     "消费",     30),
        # supplier_type
        ("supplier_type.raw_material",  "supplier_type", "raw_material",  "原材料供应商", 10),
        ("supplier_type.equipment",     "supplier_type", "equipment",     "设备供应商",   20),
        ("supplier_type.service",       "supplier_type", "service",       "服务供应商",   30),
        ("supplier_type.external_lab",  "supplier_type", "external_lab",  "外协实验室",   40),
        # system_role (auth.users.role: ADMIN/PROJECT_MANAGER/RESEARCHER/REVIEWER/VIEWER)
        ("role.admin",            "role", "ADMIN",            "管理员",       10),
        ("role.project_manager",  "role", "PROJECT_MANAGER",  "项目经理",     20),
        ("role.researcher",       "role", "RESEARCHER",       "研究员",       30),
        ("role.reviewer",         "role", "REVIEWER",         "审核者",       40),
        ("role.viewer",           "role", "VIEWER",           "查看者",       50),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )


def _sql_null(value):
    """返回 SQL NULL 字面量或带引号字符串。"""
    return "NULL" if value is None else f"'{value}'"
