"""candidates.content_hash 部分唯一索引（应用层去重的数据库兜底）

Revision ID: 0061_candidate_content_hash_unique
Revises: 0060_kingfa_target_thresholds
Create Date: 2026-08-23

背景：candidate_store.save() 按 content_hash（formula+target_application）去重，
但去重检查（独立连接）与 INSERT 非原子，并发生成同公式候选时无数据库层兜底，
可能产生双胞胎候选（审查 2026-08 MINOR#7 关联项）。

本迁移：
- 建部分唯一索引：仅约束非空 content_hash（dedup=False 路径允许 NULL 并存）

升级前置检查（存量重复会导致本升级失败，属预期防护）：
    SELECT content_hash, COUNT(*) FROM experiment.candidates
    WHERE content_hash IS NOT NULL GROUP BY 1 HAVING COUNT(*) > 1;
处理重复（保留最早 created_at 一条或合并业务字段）后重跑升级。
"""
from __future__ import annotations

from alembic import op

revision = "0061_candidate_content_hash_unique"
down_revision = "0060_kingfa_target_thresholds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_candidates_content_hash "
        "ON experiment.candidates(tenant_id, content_hash) WHERE content_hash IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS experiment.uq_candidates_content_hash")
