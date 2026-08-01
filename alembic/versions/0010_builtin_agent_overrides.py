"""内置智能体覆盖表：支持在前端编辑内置 agent 并持久化。

新增 agent_team.builtin_agent_overrides 表，存储对内置 agent 字段的覆盖。
启动时由 AgentRegistry 合并到内置 agent 定义上，实现「内置可编辑、可重置」。

Revision ID: 0010_builtin_agent_overrides
Revises: 0009_business_chain_mdm
Create Date: 2026-07-26
"""
from __future__ import annotations

from alembic import op

revision = "0010_builtin_agent_overrides"
down_revision = "0009_business_chain_mdm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_team.builtin_agent_overrides (
            id           TEXT PRIMARY KEY,
            data         JSONB NOT NULL,
            updated_at   TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_builtin_overrides_id "
        "ON agent_team.builtin_agent_overrides(id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_team.builtin_agent_overrides")
