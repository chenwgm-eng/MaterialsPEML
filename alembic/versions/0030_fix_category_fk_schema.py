"""修复 equipment.category 和 raw_materials.category 的 FK 约束 schema 指向

Revision ID: 0030_fix_category_fk_schema
Revises: 0029_pgvector_embedding_migration
Create Date: 2026-07-28

背景（P0-EQ-001 / P0-MAT-001）：
- experiment.equipment.category 的 FK 约束 fk_equipment_category
  原指向 classifications(code)，PostgreSQL 在 experiment schema 中查找该表失败
- industrialization.raw_materials.category 的 FK 约束 fk_raw_materials_categ
  同样指向无 schema 前缀的 classifications(code)
- classifications 表实际位于 mdm schema
- 导致设备与物料创建功能完全不可用（HTTP 500 ForeignKeyViolation）

修复方案（方案 A）：DROP 旧约束 → ADD 指向 mdm.classifications(code) 的新约束
"""
from alembic import op

revision = "0030_fix_category_fk_schema"
down_revision = "0029_pgvector_embedding_migration"
branch_labels = None
depends_on = None


# (table, constraint_name, column)
_FK_TO_FIX = [
    ("experiment.equipment", "fk_equipment_category", "category"),
    ("industrialization.raw_materials", "fk_raw_materials_categ", "category"),
]


def upgrade() -> None:
    for table, constraint, column in _FK_TO_FIX:
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}"
        )
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {constraint} "
            f"FOREIGN KEY ({column}) "
            f"REFERENCES mdm.classifications(code) "
            f"ON DELETE RESTRICT"
        )


def downgrade() -> None:
    for table, constraint, column in _FK_TO_FIX:
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}"
        )
        # 回退为无 schema 前缀（还原原始错误状态）
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {constraint} "
            f"FOREIGN KEY ({column}) "
            f"REFERENCES classifications(code)"
        )
