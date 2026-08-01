"""补种表征类检测方法 + experiment_orders 幂等键

Revision ID: 0024_mdm_methods_idem
Revises: 0023_rename_rm_cols
Create Date: 2026-07-27

评测修复（见 doc/BatteryEMCL_全功能实操评测与整改建议书_20260727_v7.md）：

1. P0：数据录入表单选择测试方法必然触发 FK 失败。
   属性模板（api.py PROPERTY_TEMPLATES）的 test_method 选项为 EIS/CV/XRD/SEM/
   DSC/TGA/DC/GA/恒电流滴定 等裸值，而 mdm.test_methods 仅有 method.eis 等
   method.* 主键。0015 迁移为 experiment_result_records.test_method 与
   experiment.test_tasks.test_method 加了 FK（fk_results_method），
   导致用户选择任何测试方法提交数据都会 500。
   本次补种 8 个缺失的表征方法（EIS 已有 method.eis），
   后端在写入边界做别名规范化（裸值 → method_id）。

2. P1：POST /experiments/orders 无幂等保护，双击/重试产生重复任务单。
   本次为 experiment.experiment_orders 增加 idempotency_key 列 +
   部分唯一索引（仅非 NULL 行参与唯一约束，存量数据不受影响）。
"""
from __future__ import annotations

from alembic import op

revision = "0024_mdm_methods_idem"
down_revision = "0023_rename_rm_cols"
branch_labels = None
depends_on = None


def _sql_null(v):
    return f"'{v}'" if v is not None else "NULL"


def _seed_characterization_test_methods() -> None:
    """补种表征/电化学类检测方法（0013 已含 EIS/半电/激光衍射/压汞/旋转粘度/卡尔费休，
    0019 已含振实/BET/ICP-MS/0.5C半电）。"""
    rows = [
        # (method_id, name, standard_code, sop_version, preparation_req, calculation_formula, description)
        # standard_code 统一置 NULL：mdm.standards 未收录这些国标，避免 fk_methods_standard 失败
        ("method.cv",   "循环伏安法",       None, "v1.0", "三电极/扣电体系",      "ipa/ipc, dE_p",            "CV 测氧化还原电位与可逆性"),
        ("method.xrd",  "X射线衍射法",      None, "v1.0", "粉末样品压片",         "2theta = n*lambda/(2d)",   "XRD 物相与晶体结构分析"),
        ("method.sem",  "扫描电镜法",       None, "v1.0", "样品喷金/导电处理",    "-",                        "SEM 形貌与粒径观察"),
        ("method.dsc",  "差示扫描量热法",   None, "v1.0", "5-10mg 样品密封坩埚",  "dH = integral(dQ/dt)",     "DSC 测相变/热稳定性"),
        ("method.tga",  "热重分析法",       None, "v1.0", "5-10mg 样品",          "w% = m/m0 * 100",          "TGA 测热分解与组分含量"),
        ("method.dc",   "直流极化法",       None, "v1.0", "阻塞电极体系",          "sigma = I*L/(V*A)",        "DC 极化测电子/离子电导"),
        ("method.ga",   "恒电流充放电法",   None, "v1.0", "涂布极片装配扣电",      "C = I*t/m",                "恒电流充放电测容量与循环"),
        ("method.gitt", "恒电流间歇滴定法", None, "v1.0", "扣电体系，弛豫充分",    "D = 4/pi * (m*V/(M*A))^2 * (dE_s/dE_t)^2 / t", "GITT 测离子扩散系数"),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}',{_sql_null(r[2])},'{r[3]}','{r[4]}','{r[5]}','{r[6]}',TRUE)" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.test_methods (method_id, name, standard_code, sop_version, "
        f"preparation_req, calculation_formula, description, is_active) "
        f"VALUES {values} ON CONFLICT (method_id) DO NOTHING"
    )


def _add_order_idempotency_key() -> None:
    """experiment.experiment_orders 加 idempotency_key（部分唯一索引）。

    尾部加列：现有 SELECT * 位置索引映射不受影响（新列在 index 25）。
    """
    op.execute(
        "ALTER TABLE experiment.experiment_orders "
        "ADD COLUMN IF NOT EXISTS idempotency_key TEXT"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_idempotency_key "
        "ON experiment.experiment_orders(idempotency_key) "
        "WHERE idempotency_key IS NOT NULL"
    )


def upgrade() -> None:
    _seed_characterization_test_methods()
    _add_order_idempotency_key()


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS experiment.uq_orders_idempotency_key")
    op.execute(
        "ALTER TABLE experiment.experiment_orders "
        "DROP COLUMN IF EXISTS idempotency_key"
    )
    op.execute(
        "DELETE FROM mdm.test_methods WHERE method_id IN "
        "('method.cv','method.xrd','method.sem','method.dsc','method.tga',"
        "'method.dc','method.ga','method.gitt')"
    )
