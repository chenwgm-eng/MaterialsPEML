"""0020_battery_role_material_types

补充电池配方角色物料类型到 mdm.classifications 和 mdm.material_categories。

背景：industrialization.raw_materials.category 外键引用 mdm.classifications(code)，
而 formula_agent.py 与前端 DEFAULT_INDUSTRIAL_CATEGORIES 使用 BASE_POLYMER/LITHIUM_SALT
等电池配方角色码（按电池配方角色分类），与已有的 material.* 系列（按化学/业务分类）
不互通，导致插入 raw_materials 时违反外键约束。

本次迁移补充 6 个电池配方角色物料分类码，使外键约束可通过。
数据 only，无 schema 变更。downgrade() 为 no-op。
"""
from alembic import op

revision = "0020_battery_role_material_types"
down_revision = "0019_mdm_easpring_seed"
branch_labels = None
depends_on = None


def _sql_bool(v: bool) -> str:
    return "TRUE" if v else "FALSE"


def upgrade() -> None:
    # 1. 补充到 classifications 表（domain='material'，根节点 parent_code='material'）
    cls_rows = [
        # (code, domain, parent_code, label, sort_order)
        ("BASE_POLYMER", "material", "material", "基材",       800),
        ("LITHIUM_SALT", "material", "material", "锂盐",       810),
        ("FILLER",       "material", "material", "填料",       820),
        ("SOLVENT",      "material", "material", "溶剂(配方)",  830),
        ("ADDITIVE",     "material", "material", "添加剂",     840),
        ("BINDER",       "material", "material", "粘结剂",     850),
    ]
    cls_values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'电池配方角色物料类型')"
        for r in cls_rows
    )
    op.execute(
        "INSERT INTO mdm.classifications "
        "(code, domain, parent_code, label, sort_order, is_active, description) "
        f"VALUES {cls_values} ON CONFLICT (code) DO NOTHING"
    )

    # 2. 补充到 material_categories 表（治理属性：默认单位/存储条件/保质期/危险品）
    mc_rows = [
        # (category_code, default_unit, default_storage_conditions, default_retention_days, is_hazardous, description)
        ("BASE_POLYMER", "kg", "常温干燥",     365, False, "电池配方基材"),
        ("LITHIUM_SALT", "kg", "常温干燥密封", 365, False, "电池配方锂盐"),
        ("FILLER",       "kg", "常温干燥",     365, False, "电池配方填料"),
        ("SOLVENT",      "L",  "常温阴凉通风", 365, False, "电池配方溶剂"),
        ("ADDITIVE",     "kg", "常温干燥",     365, False, "电池配方添加剂"),
        ("BINDER",       "kg", "常温干燥避光", 365, False, "电池配方粘结剂"),
    ]
    mc_values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}',{r[3]},{_sql_bool(r[4])},'{r[5]}')"
        for r in mc_rows
    )
    op.execute(
        "INSERT INTO mdm.material_categories "
        "(category_code, default_unit, default_storage_conditions, "
        "default_retention_days, is_hazardous, description) "
        f"VALUES {mc_values} ON CONFLICT (category_code) DO NOTHING"
    )


def downgrade() -> None:
    # 数据迁移，no-op 回滚（不删除补充的分类码，避免破坏已有 raw_materials 引用）
    pass
