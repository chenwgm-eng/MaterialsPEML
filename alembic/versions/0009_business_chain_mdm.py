"""业务链路主数据断点补全：新增 projects.tasks / experiment.bom_schemes / experiment.test_tasks 三张表，
现有 6 张表加 task_id/bom_id/test_task_id 字段并补 3 处遗漏 FK 约束，迁移 projects.projects.tasks JSONB 到关系表。

Revision ID: 0009_business_chain_mdm
Revises: 0008_project_tasks
Create Date: 2026-07-26

详见 .trae/specs/business-chain-mdm/spec.md
"""
from __future__ import annotations

from alembic import op

revision = "0009_business_chain_mdm"
down_revision = "0008_project_tasks"
branch_labels = None
depends_on = None


# ──────────────────────────────────────────────────────────────────────────────
# upgrade
# ──────────────────────────────────────────────────────────────────────────────
def upgrade() -> None:
    # 1. 创建 3 张新表
    _create_projects_tasks()
    _create_bom_schemes()
    _create_test_tasks()

    # 2. 现有表加字段 + FK + 索引
    _alter_candidates()
    _alter_experiment_orders()
    _alter_samples()
    _alter_experiment_result_records()
    _alter_research_requests()
    _alter_ecml_runs_index()

    # 3. 数据迁移：projects.projects.tasks JSONB → projects.tasks 关系表
    _migrate_tasks_jsonb_to_relation()


# ──────────────────────────────────────────────────────────────────────────────
# 新表创建
# ──────────────────────────────────────────────────────────────────────────────
def _create_projects_tasks() -> None:
    """创建 projects.tasks 关系表（替代 projects.projects.tasks JSONB）。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects.tasks (
            task_id            TEXT PRIMARY KEY,
            project_id         TEXT NOT NULL,
            title              TEXT NOT NULL,
            deliverable        TEXT DEFAULT '',
            target_properties  JSONB DEFAULT '[]'::jsonb,
            status             TEXT DEFAULT 'draft',
            assignee           TEXT DEFAULT '',
            sort_order         INTEGER DEFAULT 0,
            created_at         TIMESTAMPTZ DEFAULT NOW(),
            updated_at         TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_tasks_project FOREIGN KEY (project_id)
                REFERENCES projects.projects(project_id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON projects.tasks(project_id)"
    )


def _create_bom_schemes() -> None:
    """创建 experiment.bom_schemes BOM 方案表（候选材料 1:1）。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS experiment.bom_schemes (
            bom_id             TEXT PRIMARY KEY,
            candidate_id       TEXT NOT NULL,
            task_id            TEXT,
            formulation        JSONB DEFAULT '{}'::jsonb,
            process_route      JSONB DEFAULT '{}'::jsonb,
            test_protocol      JSONB DEFAULT '{}'::jsonb,
            version            TEXT DEFAULT 'v1',
            status             TEXT DEFAULT 'draft',
            created_by         TEXT DEFAULT '',
            created_at         TIMESTAMPTZ DEFAULT NOW(),
            updated_at         TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_bom_candidate FOREIGN KEY (candidate_id)
                REFERENCES experiment.candidates(candidate_id) ON DELETE RESTRICT,
            CONSTRAINT fk_bom_task FOREIGN KEY (task_id)
                REFERENCES projects.tasks(task_id) ON DELETE SET NULL,
            CONSTRAINT uq_bom_candidate UNIQUE (candidate_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bom_task_id ON experiment.bom_schemes(task_id)"
    )


def _create_test_tasks() -> None:
    """创建 experiment.test_tasks 测试任务表（experiment_orders 1:N test_tasks）。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS experiment.test_tasks (
            test_task_id       TEXT PRIMARY KEY,
            order_id           TEXT NOT NULL,
            bom_id             TEXT,
            test_type          TEXT DEFAULT '',
            test_method        TEXT DEFAULT '',
            priority           TEXT DEFAULT 'P2',
            assignee           TEXT DEFAULT '',
            status             TEXT DEFAULT 'DRAFT',
            planned_start      TIMESTAMPTZ,
            planned_end        TIMESTAMPTZ,
            started_at         TIMESTAMPTZ,
            completed_at       TIMESTAMPTZ,
            notes              TEXT DEFAULT '',
            created_at         TIMESTAMPTZ DEFAULT NOW(),
            updated_at         TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_test_task_order FOREIGN KEY (order_id)
                REFERENCES experiment.experiment_orders(order_id) ON DELETE RESTRICT,
            CONSTRAINT fk_test_task_bom FOREIGN KEY (bom_id)
                REFERENCES experiment.bom_schemes(bom_id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_test_tasks_order_id ON experiment.test_tasks(order_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_test_tasks_bom_id ON experiment.test_tasks(bom_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_test_tasks_status ON experiment.test_tasks(status)"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 现有表加字段
# ──────────────────────────────────────────────────────────────────────────────
def _alter_candidates() -> None:
    """experiment.candidates 加 task_id / project_id 字段 + FK + 索引。"""
    op.execute(
        "ALTER TABLE experiment.candidates "
        "ADD COLUMN IF NOT EXISTS task_id TEXT"
    )
    op.execute(
        "ALTER TABLE experiment.candidates "
        "ADD COLUMN IF NOT EXISTS project_id TEXT"
    )
    op.execute(
        "ALTER TABLE experiment.candidates "
        "DROP CONSTRAINT IF EXISTS fk_candidates_task"
    )
    op.execute(
        "ALTER TABLE experiment.candidates "
        "DROP CONSTRAINT IF EXISTS fk_candidates_project"
    )
    op.execute(
        "ALTER TABLE experiment.candidates "
        "ADD CONSTRAINT fk_candidates_task FOREIGN KEY (task_id) "
        "REFERENCES projects.tasks(task_id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE experiment.candidates "
        "ADD CONSTRAINT fk_candidates_project FOREIGN KEY (project_id) "
        "REFERENCES projects.projects(project_id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_candidates_task_id "
        "ON experiment.candidates(task_id)"
    )


def _alter_experiment_orders() -> None:
    """experiment.experiment_orders 加 bom_id / task_id 字段 + FK + 索引。"""
    op.execute(
        "ALTER TABLE experiment.experiment_orders "
        "ADD COLUMN IF NOT EXISTS bom_id TEXT"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_orders "
        "ADD COLUMN IF NOT EXISTS task_id TEXT"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_orders "
        "DROP CONSTRAINT IF EXISTS fk_orders_bom"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_orders "
        "DROP CONSTRAINT IF EXISTS fk_orders_task"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_orders "
        "ADD CONSTRAINT fk_orders_bom FOREIGN KEY (bom_id) "
        "REFERENCES experiment.bom_schemes(bom_id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_orders "
        "ADD CONSTRAINT fk_orders_task FOREIGN KEY (task_id) "
        "REFERENCES projects.tasks(task_id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_orders_task_id "
        "ON experiment.experiment_orders(task_id)"
    )


def _alter_samples() -> None:
    """experiment.samples 加 test_task_id 字段 + FK + 索引。"""
    op.execute(
        "ALTER TABLE experiment.samples "
        "ADD COLUMN IF NOT EXISTS test_task_id TEXT"
    )
    op.execute(
        "ALTER TABLE experiment.samples "
        "DROP CONSTRAINT IF EXISTS fk_samples_test_task"
    )
    op.execute(
        "ALTER TABLE experiment.samples "
        "ADD CONSTRAINT fk_samples_test_task FOREIGN KEY (test_task_id) "
        "REFERENCES experiment.test_tasks(test_task_id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_samples_test_task_id "
        "ON experiment.samples(test_task_id)"
    )


def _alter_experiment_result_records() -> None:
    """experiment.experiment_result_records 加 test_task_id + 补 sample_id/instrument_id FK + 改 test_conditions 类型。

    补 FK 前需先清理孤立记录（sample_id 不存在于 samples 表 / instrument_id 不存在于 equipment 表）。
    """
    # Step 1: 清理孤立 sample_id（含空字符串，凡是不在 samples 表中的都置 NULL）
    op.execute(
        "UPDATE experiment.experiment_result_records SET sample_id = NULL "
        "WHERE sample_id IS NOT NULL "
        "AND sample_id NOT IN (SELECT sample_id FROM experiment.samples)"
    )
    # Step 2: 清理孤立 instrument_id（含空字符串，凡是不在 equipment 表中的都置 NULL）
    op.execute(
        "UPDATE experiment.experiment_result_records SET instrument_id = NULL "
        "WHERE instrument_id IS NOT NULL "
        "AND instrument_id NOT IN (SELECT equipment_id FROM experiment.equipment)"
    )

    # Step 3: 加 test_task_id 字段
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "ADD COLUMN IF NOT EXISTS test_task_id TEXT"
    )

    # Step 4: 补 sample_id FK
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "DROP CONSTRAINT IF EXISTS fk_results_sample"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "ADD CONSTRAINT fk_results_sample FOREIGN KEY (sample_id) "
        "REFERENCES experiment.samples(sample_id) ON DELETE RESTRICT"
    )

    # Step 5: 补 instrument_id FK
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "DROP CONSTRAINT IF EXISTS fk_results_instrument"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "ADD CONSTRAINT fk_results_instrument FOREIGN KEY (instrument_id) "
        "REFERENCES experiment.equipment(equipment_id) ON DELETE SET NULL"
    )

    # Step 6: 加 test_task_id FK
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "DROP CONSTRAINT IF EXISTS fk_results_test_task"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "ADD CONSTRAINT fk_results_test_task FOREIGN KEY (test_task_id) "
        "REFERENCES experiment.test_tasks(test_task_id) ON DELETE SET NULL"
    )

    # Step 7: 改 test_conditions 类型 TEXT → JSONB
    # 注意：NULLIF 兜底空字符串，无法解析的字符串转为 NULL
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "ALTER COLUMN test_conditions TYPE JSONB "
        "USING NULLIF(test_conditions, '')::jsonb"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_results_test_task_id "
        "ON experiment.experiment_result_records(test_task_id)"
    )


def _alter_research_requests() -> None:
    """hybrid.research_requests 加 task_id + 补 project_id FK + 索引。

    补 project_id FK 前需先清理空字符串和孤立 project_id。
    """
    # Step 0: 清理 project_id（空字符串或孤立值都置 NULL）
    op.execute(
        "UPDATE hybrid.research_requests SET project_id = NULL "
        "WHERE project_id IS NOT NULL "
        "AND project_id NOT IN (SELECT project_id FROM projects.projects)"
    )

    # Step 1: 加 task_id 字段
    op.execute(
        "ALTER TABLE hybrid.research_requests "
        "ADD COLUMN IF NOT EXISTS task_id TEXT"
    )
    # Step 2: 补 project_id FK（0005 遗漏，project_id 字段已存在但无 FK）
    op.execute(
        "ALTER TABLE hybrid.research_requests "
        "DROP CONSTRAINT IF EXISTS fk_research_requests_project"
    )
    op.execute(
        "ALTER TABLE hybrid.research_requests "
        "ADD CONSTRAINT fk_research_requests_project FOREIGN KEY (project_id) "
        "REFERENCES projects.projects(project_id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE hybrid.research_requests "
        "DROP CONSTRAINT IF EXISTS fk_research_requests_task"
    )
    op.execute(
        "ALTER TABLE hybrid.research_requests "
        "ADD CONSTRAINT fk_research_requests_task FOREIGN KEY (task_id) "
        "REFERENCES projects.tasks(task_id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_research_requests_task_id "
        "ON hybrid.research_requests(task_id)"
    )


def _alter_ecml_runs_index() -> None:
    """ecml.ecml_runs_index 加 task_id / project_id 字段（无 FK，仅索引）。"""
    op.execute(
        "ALTER TABLE ecml.ecml_runs_index "
        "ADD COLUMN IF NOT EXISTS task_id TEXT DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE ecml.ecml_runs_index "
        "ADD COLUMN IF NOT EXISTS project_id TEXT DEFAULT ''"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ecml_runs_index_task_id "
        "ON ecml.ecml_runs_index(task_id)"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 数据迁移：projects.projects.tasks JSONB → projects.tasks 关系表
# ──────────────────────────────────────────────────────────────────────────────
def _migrate_tasks_jsonb_to_relation() -> None:
    """遍历 projects.projects.tasks JSONB 数组，逐项插入 projects.tasks 关系表。

    - task_id 使用 JSONB 中的 task_id（若存在）或生成新 UUID
    - sort_order 按数组顺序填充
    - ON CONFLICT (task_id) DO NOTHING 跳过重复
    """
    op.execute(
        """
        INSERT INTO projects.tasks (task_id, project_id, title, deliverable,
                                    target_properties, status, assignee, sort_order,
                                    created_at, updated_at)
        SELECT
            CASE
                WHEN t.task->>'task_id' IS NOT NULL AND t.task->>'task_id' <> ''
                    THEN t.task->>'task_id'
                ELSE gen_random_uuid()::text
            END AS task_id,
            p.project_id,
            COALESCE(t.task->>'title', '未命名任务') AS title,
            COALESCE(t.task->>'deliverable', '') AS deliverable,
            COALESCE(t.task->'target_properties', '[]'::jsonb) AS target_properties,
            'draft' AS status,
            '' AS assignee,
            t.idx AS sort_order,
            COALESCE(p.created_at, NOW()) AS created_at,
            COALESCE(p.updated_at, NOW()) AS updated_at
        FROM projects.projects p
        CROSS JOIN LATERAL
            jsonb_array_elements(p.tasks) WITH ORDINALITY AS t(task, idx)
        WHERE jsonb_typeof(p.tasks) = 'array' AND jsonb_array_length(p.tasks) > 0
        ON CONFLICT (task_id) DO NOTHING
        """
    )


# ──────────────────────────────────────────────────────────────────────────────
# downgrade
# ──────────────────────────────────────────────────────────────────────────────
def downgrade() -> None:
    # 注意：downgrade 不还原 projects.tasks JSONB（保留原 JSONB 字段未变）
    # 也不还原 test_conditions 类型（TEXT 转 JSONB 不可逆，原数据可能已损坏）

    # 1. 删除 ecml_runs_index 新增字段
    op.execute("DROP INDEX IF EXISTS ecml.idx_ecml_runs_index_task_id")
    op.execute("ALTER TABLE ecml.ecml_runs_index DROP COLUMN IF EXISTS task_id")
    op.execute("ALTER TABLE ecml.ecml_runs_index DROP COLUMN IF EXISTS project_id")

    # 2. 删除 research_requests 新增字段和 FK
    op.execute("DROP INDEX IF EXISTS hybrid.idx_research_requests_task_id")
    op.execute(
        "ALTER TABLE hybrid.research_requests "
        "DROP CONSTRAINT IF EXISTS fk_research_requests_task"
    )
    op.execute(
        "ALTER TABLE hybrid.research_requests "
        "DROP CONSTRAINT IF EXISTS fk_research_requests_project"
    )
    op.execute("ALTER TABLE hybrid.research_requests DROP COLUMN IF EXISTS task_id")

    # 3. 删除 experiment_result_records 新增字段和 FK，改回 test_conditions 类型
    op.execute("DROP INDEX IF EXISTS experiment.idx_results_test_task_id")
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "DROP CONSTRAINT IF EXISTS fk_results_test_task"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "DROP CONSTRAINT IF EXISTS fk_results_instrument"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "DROP CONSTRAINT IF EXISTS fk_results_sample"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "DROP COLUMN IF EXISTS test_task_id"
    )
    # test_conditions 改回 TEXT（JSONB → TEXT，使用 ::text 转换）
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "ALTER COLUMN test_conditions TYPE TEXT "
        "USING test_conditions::text"
    )

    # 4. 删除 samples 新增字段
    op.execute("DROP INDEX IF EXISTS experiment.idx_samples_test_task_id")
    op.execute(
        "ALTER TABLE experiment.samples "
        "DROP CONSTRAINT IF EXISTS fk_samples_test_task"
    )
    op.execute("ALTER TABLE experiment.samples DROP COLUMN IF EXISTS test_task_id")

    # 5. 删除 experiment_orders 新增字段
    op.execute("DROP INDEX IF EXISTS experiment.idx_orders_task_id")
    op.execute(
        "ALTER TABLE experiment.experiment_orders "
        "DROP CONSTRAINT IF EXISTS fk_orders_task"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_orders "
        "DROP CONSTRAINT IF EXISTS fk_orders_bom"
    )
    op.execute("ALTER TABLE experiment.experiment_orders DROP COLUMN IF EXISTS task_id")
    op.execute("ALTER TABLE experiment.experiment_orders DROP COLUMN IF EXISTS bom_id")

    # 6. 删除 candidates 新增字段
    op.execute("DROP INDEX IF EXISTS experiment.idx_candidates_task_id")
    op.execute(
        "ALTER TABLE experiment.candidates "
        "DROP CONSTRAINT IF EXISTS fk_candidates_project"
    )
    op.execute(
        "ALTER TABLE experiment.candidates "
        "DROP CONSTRAINT IF EXISTS fk_candidates_task"
    )
    op.execute("ALTER TABLE experiment.candidates DROP COLUMN IF EXISTS project_id")
    op.execute("ALTER TABLE experiment.candidates DROP COLUMN IF EXISTS task_id")

    # 7. 删除 3 张新表（顺序：先 test_tasks，再 bom_schemes，最后 tasks）
    op.execute("DROP TABLE IF EXISTS experiment.test_tasks")
    op.execute("DROP TABLE IF EXISTS experiment.bom_schemes")
    op.execute("DROP TABLE IF EXISTS projects.tasks")
