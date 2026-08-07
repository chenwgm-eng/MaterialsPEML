"""0039: 创建 AI 助手会话与消息表 — scientific_kernel.ai_sessions / ai_messages

为右侧全局 AI 助手（Copilot）提供会话持久化，支持：
- 会话列表（项目隔离 + 用户隔离）
- 消息流转（user / assistant / tool / system）
- 信任机制元数据（来源证据、置信度、行动建议、反馈、耗时）
- 上下文感知（当前页 context_json）与聚焦模式（focus_json）

Revision ID: 0039_ai_assistant_sessions
Revises: 0038_scientific_execution_kernel
Create Date: 2026-08-06
"""
from __future__ import annotations

import logging

from alembic import op

revision = "0039_ai_assistant_sessions"
down_revision = "0038_scientific_execution_kernel"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS scientific_kernel")

    # ── ai_sessions ─────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scientific_kernel.ai_sessions (
            session_id   TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL,
            project_id   TEXT NOT NULL DEFAULT '',
            title        TEXT NOT NULL DEFAULT '新会话',
            mode         TEXT NOT NULL DEFAULT 'global',
            focus_json   JSONB NOT NULL DEFAULT '{}',
            status       TEXT NOT NULL DEFAULT 'active',
            context_json JSONB NOT NULL DEFAULT '{}',
            metadata_json JSONB NOT NULL DEFAULT '{}',
            created_at   TIMESTAMPTZ NOT NULL,
            updated_at   TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_sessions_user ON scientific_kernel.ai_sessions (user_id, updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_sessions_project ON scientific_kernel.ai_sessions (project_id)"
    )

    # ── ai_messages ─────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scientific_kernel.ai_messages (
            message_id   TEXT PRIMARY KEY,
            session_id   TEXT NOT NULL REFERENCES scientific_kernel.ai_sessions (session_id),
            role         TEXT NOT NULL,
            content      TEXT NOT NULL DEFAULT '',
            provider     TEXT NOT NULL DEFAULT '',
            model        TEXT NOT NULL DEFAULT '',
            status       TEXT NOT NULL DEFAULT 'done',
            meta_json    JSONB NOT NULL DEFAULT '{}',
            created_at   TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_messages_session ON scientific_kernel.ai_messages (session_id, created_at)"
    )

    logger.info("0039: 已创建 ai_sessions / ai_messages 表")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scientific_kernel.ai_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS scientific_kernel.ai_sessions CASCADE")
    logger.info("0039: 已删除 ai_sessions / ai_messages 表")