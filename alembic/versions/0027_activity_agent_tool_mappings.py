"""业务活动-智能体-工具 三层映射表

Revision ID: 0027_activity_agent_tool_mappings
Revises: 0026_scp_async_tasks
Create Date: 2026-07-28

决策 1-13 的持久化层：
- agent_team.activity_agent_bindings: 业务活动→智能体绑定（决策 1-C）
- agent_team.agent_tool_bindings: 智能体→主工具绑定（决策 2-C/6-C/9-C）
- agent_team.tool_registrations: 工具注册元数据（决策 8-C/11-C）
"""
from alembic import op
from sqlalchemy import text

revision = "0027_activity_agent_tool_mappings"
down_revision = "0026_scp_async_tasks"
branch_labels = None
depends_on = None


def upgrade():
    # 1. 业务活动 → 智能体绑定
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS agent_team.activity_agent_bindings (
            binding_id TEXT PRIMARY KEY,
            activity_id TEXT NOT NULL,
            data JSONB NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_activity_bindings_activity
        ON agent_team.activity_agent_bindings(activity_id)
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_activity_bindings_agent
        ON agent_team.activity_agent_bindings((data->>'agent_id'))
    """))

    # 2. 智能体 → 工具绑定
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS agent_team.agent_tool_bindings (
            binding_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            capability TEXT NOT NULL,
            data JSONB NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_agent_tool_bindings_agent
        ON agent_team.agent_tool_bindings(agent_id)
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_agent_tool_bindings_cap
        ON agent_team.agent_tool_bindings(capability)
    """))

    # 3. 工具注册元数据
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS agent_team.tool_registrations (
            tool_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            data JSONB NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_tool_registrations_source
        ON agent_team.tool_registrations(source)
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_tool_registrations_cap_gin
        ON agent_team.tool_registrations USING GIN ((data->'capability_refs'))
    """))


def downgrade():
    op.execute(text("DROP TABLE IF EXISTS agent_team.tool_registrations"))
    op.execute(text("DROP TABLE IF EXISTS agent_team.agent_tool_bindings"))
    op.execute(text("DROP TABLE IF EXISTS agent_team.activity_agent_bindings"))
