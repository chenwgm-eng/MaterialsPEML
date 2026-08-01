"""projects.tasks 列：存储 AI 拆解出的项目任务列表。

Revision ID: 0008_project_tasks
Revises: 0007_research_requests_scenario_id
Create Date: 2026-07-26
"""
from alembic import op

revision = "0008_project_tasks"
down_revision = "0007_add_scenario_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 与 projects 表其他 JSON 列保持一致，使用 JSONB 类型
    op.execute(
        "ALTER TABLE projects.projects "
        "ADD COLUMN IF NOT EXISTS tasks JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE projects.projects DROP COLUMN IF EXISTS tasks")
