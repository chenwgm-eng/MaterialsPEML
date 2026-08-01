"""P5 FK 加固 + 全链血缘 + 文档版本 + 执行快照。

1. 业务表自由文本字段改 FK（清理孤立记录后加约束）：
   - experiment.test_tasks.test_method → mdm.test_methods.method_id
   - experiment.experiment_result_records.test_method → mdm.test_methods.method_id
   - experiment.experiment_result_records.property_name → mdm.properties.property_id
   - experiment.experiment_result_records.unit → mdm.units.unit_code
   - industrialization.raw_materials.category → mdm.classifications.code
   - experiment.equipment.category → mdm.classifications.code
2. 新建 mdm.documents / mdm.document_versions 表（SOP/WI/规范文档）
3. 新建 experiment.order_version_snapshots 表（订单版本快照）
4. control_plane.versions.entity_type 与 provenance_nodes.entity_type 为 TEXT，
   无需 ALTER TYPE，仅文档化新增值 DOCUMENT/SOP/SPECIFICATION/sample/batch/equipment/method_version/raw_file

Revision ID: 0015_mdm_p5_fk_lineage
Revises: 0014_mdm_process
Create Date: 2026-07-27

详见 .trae/specs/mdm-governance/spec.md
"""
from __future__ import annotations

from alembic import op

revision = "0015_mdm_p5_fk_lineage"
down_revision = "0014_mdm_process"
branch_labels = None
depends_on = None


# ──────────────────────────────────────────────────────────────────────────────
# upgrade
# ──────────────────────────────────────────────────────────────────────────────
def upgrade() -> None:
    # 1. 新建表
    _create_documents()
    _create_document_versions()
    _create_order_version_snapshots()

    # 2. FK 加固：清理孤立记录 + 加 FK 约束
    _strengthen_test_tasks_test_method_fk()
    _strengthen_result_records_test_method_fk()
    _strengthen_result_records_property_name_fk()
    _strengthen_result_records_unit_fk()
    _strengthen_raw_materials_category_fk()
    _strengthen_equipment_category_fk()


# ──────────────────────────────────────────────────────────────────────────────
# downgrade
# ──────────────────────────────────────────────────────────────────────────────
def downgrade() -> None:
    # 1. 删 FK 约束
    _drop_fk("experiment.test_tasks", "fk_test_tasks_method")
    _drop_fk("experiment.experiment_result_records", "fk_results_method")
    _drop_fk("experiment.experiment_result_records", "fk_results_property")
    _drop_fk("experiment.experiment_result_records", "fk_results_unit")
    _drop_fk("industrialization.raw_materials", "fk_raw_materials_category")
    _drop_fk("experiment.equipment", "fk_equipment_category")
    # 2. 删表
    op.execute("DROP TABLE IF EXISTS experiment.order_version_snapshots")
    op.execute("DROP TABLE IF EXISTS mdm.document_versions")
    op.execute("DROP TABLE IF EXISTS mdm.documents")


# ──────────────────────────────────────────────────────────────────────────────
# 新表
# ──────────────────────────────────────────────────────────────────────────────
def _create_documents() -> None:
    """文档主数据：SOP/WI/规范文档。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.documents (
            document_id      TEXT PRIMARY KEY,
            title            TEXT NOT NULL,
            document_type    TEXT DEFAULT '',
            category_code    TEXT,
            status           TEXT DEFAULT 'draft',
            owner            TEXT DEFAULT '',
            description      TEXT DEFAULT '',
            is_active        BOOLEAN DEFAULT TRUE,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_documents_category FOREIGN KEY (category_code)
                REFERENCES mdm.classifications(code) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_type ON mdm.documents(document_type)"
    )


def _create_document_versions() -> None:
    """文档版本：承载 SOP/WI/规范的版本化内容。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mdm.document_versions (
            version_id       TEXT PRIMARY KEY,
            document_id      TEXT NOT NULL,
            version_number   TEXT NOT NULL,
            content_uri      TEXT DEFAULT '',
            content_hash     TEXT DEFAULT '',
            effective_date   DATE,
            status           TEXT DEFAULT 'draft',
            change_summary   TEXT DEFAULT '',
            created_by       TEXT DEFAULT '',
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_doc_versions_document FOREIGN KEY (document_id)
                REFERENCES mdm.documents(document_id) ON DELETE CASCADE,
            UNIQUE (document_id, version_number)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_doc_versions_document ON mdm.document_versions(document_id)"
    )


def _create_order_version_snapshots() -> None:
    """订单版本快照：experiment_order 下单时冻结主数据版本。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS experiment.order_version_snapshots (
            snapshot_id      TEXT PRIMARY KEY,
            order_id         TEXT NOT NULL,
            snapshot_type    TEXT DEFAULT 'order_creation',
            snapshot_data    JSONB NOT NULL DEFAULT '{}'::jsonb,
            master_data_refs JSONB DEFAULT '{}'::jsonb,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_order_snap_order FOREIGN KEY (order_id)
                REFERENCES experiment.experiment_orders(order_id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_order_snap_order ON experiment.order_version_snapshots(order_id)"
    )


# ──────────────────────────────────────────────────────────────────────────────
# FK 加固
# ──────────────────────────────────────────────────────────────────────────────
def _strengthen_test_tasks_test_method_fk() -> None:
    """test_tasks.test_method → mdm.test_methods.method_id（ON DELETE SET NULL）。"""
    # 清理孤立记录和空字符串
    op.execute(
        "UPDATE experiment.test_tasks SET test_method = NULL "
        "WHERE test_method IS NOT NULL "
        "AND (test_method = '' OR test_method NOT IN (SELECT method_id FROM mdm.test_methods))"
    )
    op.execute(
        "ALTER TABLE experiment.test_tasks "
        "DROP CONSTRAINT IF EXISTS fk_test_tasks_method"
    )
    op.execute(
        "ALTER TABLE experiment.test_tasks "
        "ADD CONSTRAINT fk_test_tasks_method FOREIGN KEY (test_method) "
        "REFERENCES mdm.test_methods(method_id) ON DELETE SET NULL"
    )


def _strengthen_result_records_test_method_fk() -> None:
    """experiment_result_records.test_method → mdm.test_methods.method_id。"""
    op.execute(
        "UPDATE experiment.experiment_result_records SET test_method = NULL "
        "WHERE test_method IS NOT NULL "
        "AND (test_method = '' OR test_method NOT IN (SELECT method_id FROM mdm.test_methods))"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "DROP CONSTRAINT IF EXISTS fk_results_method"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "ADD CONSTRAINT fk_results_method FOREIGN KEY (test_method) "
        "REFERENCES mdm.test_methods(method_id) ON DELETE SET NULL"
    )


def _strengthen_result_records_property_name_fk() -> None:
    """experiment_result_records.property_name → mdm.properties.property_id。"""
    op.execute(
        "UPDATE experiment.experiment_result_records SET property_name = NULL "
        "WHERE property_name IS NOT NULL "
        "AND (property_name = '' OR property_name NOT IN (SELECT property_id FROM mdm.properties))"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "DROP CONSTRAINT IF EXISTS fk_results_property"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "ADD CONSTRAINT fk_results_property FOREIGN KEY (property_name) "
        "REFERENCES mdm.properties(property_id) ON DELETE SET NULL"
    )


def _strengthen_result_records_unit_fk() -> None:
    """experiment_result_records.unit → mdm.units.unit_code。"""
    op.execute(
        "UPDATE experiment.experiment_result_records SET unit = NULL "
        "WHERE unit IS NOT NULL "
        "AND (unit = '' OR unit NOT IN (SELECT unit_code FROM mdm.units))"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "DROP CONSTRAINT IF EXISTS fk_results_unit"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "ADD CONSTRAINT fk_results_unit FOREIGN KEY (unit) "
        "REFERENCES mdm.units(unit_code) ON DELETE SET NULL"
    )


def _strengthen_raw_materials_category_fk() -> None:
    """raw_materials.category → mdm.classifications.code。"""
    op.execute(
        "UPDATE industrialization.raw_materials SET category = NULL "
        "WHERE category IS NOT NULL "
        "AND (category = '' OR category NOT IN (SELECT code FROM mdm.classifications))"
    )
    op.execute(
        "ALTER TABLE industrialization.raw_materials "
        "DROP CONSTRAINT IF EXISTS fk_raw_materials_category"
    )
    op.execute(
        "ALTER TABLE industrialization.raw_materials "
        "ADD CONSTRAINT fk_raw_materials_category FOREIGN KEY (category) "
        "REFERENCES mdm.classifications(code) ON DELETE SET NULL"
    )


def _strengthen_equipment_category_fk() -> None:
    """equipment.category → mdm.classifications.code。"""
    op.execute(
        "UPDATE experiment.equipment SET category = NULL "
        "WHERE category IS NOT NULL "
        "AND (category = '' OR category NOT IN (SELECT code FROM mdm.classifications))"
    )
    op.execute(
        "ALTER TABLE experiment.equipment "
        "DROP CONSTRAINT IF EXISTS fk_equipment_category"
    )
    op.execute(
        "ALTER TABLE experiment.equipment "
        "ADD CONSTRAINT fk_equipment_category FOREIGN KEY (category) "
        "REFERENCES mdm.classifications(code) ON DELETE SET NULL"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 工具
# ──────────────────────────────────────────────────────────────────────────────
def _drop_fk(table: str, constraint: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
