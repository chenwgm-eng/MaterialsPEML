"""0021_candidate_artifacts_and_process_schemes

新增候选材料产出物的持久化存储与关联：

1. 新建 experiment.process_schemes：独立工艺方案表（与 BomScheme 1:1 关联），
   用于记录从合成路径生成的工艺路线信息。
2. 新建 experiment.candidate_artifacts：候选产出物统一存储表，按 candidate_id +
   artifact_type 唯一约束保留最新一条。覆盖性质预测、合规检查等。
3. 修改 experiment.bom_schemes：放宽候选 1:1 UNIQUE 约束为 1:N，新增 source_route_id /
   source_synthesis_task_id / process_id / name 字段，记录 BOM 来源合成路径与关联工艺方案。
4. 修改 synthesis.synthesis_tasks：新增 candidate_id 列，便于按候选回溯合成历史。
"""
from alembic import op
import sqlalchemy as sa


revision = "0021_cand_artifacts_proc"
down_revision = "0020_battery_role_material_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 新建工艺方案表
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS experiment.process_schemes (
            process_id                 TEXT PRIMARY KEY,
            candidate_id               TEXT NOT NULL,
            bom_id                     TEXT,
            source_route_id            TEXT,
            source_synthesis_task_id   TEXT,
            steps                      JSONB DEFAULT '[]'::jsonb,
            raw_materials              JSONB DEFAULT '[]'::jsonb,
            metadata                   JSONB DEFAULT '{}'::jsonb,
            created_by                 TEXT DEFAULT '',
            created_at                 TIMESTAMPTZ DEFAULT NOW(),
            updated_at                 TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_process_candidate FOREIGN KEY (candidate_id)
                REFERENCES experiment.candidates(candidate_id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_process_candidate_id "
        "ON experiment.process_schemes(candidate_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_process_bom_id "
        "ON experiment.process_schemes(bom_id)"
    )

    # 2. 新建候选产出物表（性质预测 / 合规检查 等，只保留最新一条）
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS experiment.candidate_artifacts (
            artifact_id     TEXT PRIMARY KEY,
            candidate_id    TEXT NOT NULL,
            artifact_type   TEXT NOT NULL,
            artifact_data   JSONB DEFAULT '{}'::jsonb,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_artifact_candidate FOREIGN KEY (candidate_id)
                REFERENCES experiment.candidates(candidate_id) ON DELETE CASCADE,
            CONSTRAINT uq_artifact_candidate_type UNIQUE (candidate_id, artifact_type)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_candidate_id "
        "ON experiment.candidate_artifacts(candidate_id)"
    )

    # 3. 修改 bom_schemes：放宽 UNIQUE(candidate_id)，新增来源字段
    # 3.1 删除原 UNIQUE 约束（若存在）
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_bom_candidate'
                  AND conrelid = 'experiment.bom_schemes'::regclass
            ) THEN
                ALTER TABLE experiment.bom_schemes DROP CONSTRAINT uq_bom_candidate;
            END IF;
        END $$;
        """
    )
    # 3.2 新增字段（IF NOT EXISTS 兼容重复执行）
    op.execute(
        "ALTER TABLE experiment.bom_schemes "
        "ADD COLUMN IF NOT EXISTS source_route_id TEXT DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE experiment.bom_schemes "
        "ADD COLUMN IF NOT EXISTS source_synthesis_task_id TEXT DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE experiment.bom_schemes "
        "ADD COLUMN IF NOT EXISTS process_id TEXT DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE experiment.bom_schemes "
        "ADD COLUMN IF NOT EXISTS name TEXT DEFAULT ''"
    )
    # 3.3 为多 BOM 共存增加索引
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bom_candidate_id "
        "ON experiment.bom_schemes(candidate_id)"
    )

    # 4. 修改 synthesis.synthesis_tasks：新增 candidate_id 列
    op.execute(
        "ALTER TABLE synthesis.synthesis_tasks "
        "ADD COLUMN IF NOT EXISTS candidate_id TEXT DEFAULT ''"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_synthesis_tasks_candidate_id "
        "ON synthesis.synthesis_tasks(candidate_id)"
    )


def downgrade() -> None:
    # 回滚时仅删除新增表与字段，不恢复 UNIQUE 约束（避免破坏 1:N 模式下已有数据）
    op.execute("DROP TABLE IF EXISTS experiment.candidate_artifacts")
    op.execute("DROP TABLE IF EXISTS experiment.process_schemes")

    op.execute(
        "ALTER TABLE experiment.bom_schemes "
        "DROP COLUMN IF EXISTS source_route_id"
    )
    op.execute(
        "ALTER TABLE experiment.bom_schemes "
        "DROP COLUMN IF EXISTS source_synthesis_task_id"
    )
    op.execute(
        "ALTER TABLE experiment.bom_schemes "
        "DROP COLUMN IF EXISTS process_id"
    )
    op.execute(
        "ALTER TABLE experiment.bom_schemes "
        "DROP COLUMN IF EXISTS name"
    )

    op.execute(
        "ALTER TABLE synthesis.synthesis_tasks "
        "DROP COLUMN IF EXISTS candidate_id"
    )
