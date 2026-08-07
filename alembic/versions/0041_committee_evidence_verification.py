"""0041: 委员会证据持久化核验结果 — committee_evidence 增加 verification / confidence

对应需求：证据链可信化。ClaimVerifier 在评分前对证据做 run 记录真实性核验并就地
标记 verification（verified / unverified）与降级 confidence，但仓库此前未持久化
这两个字段，导致 CoE 审计的声明核验维度无从还原。本变更补齐仓库字段。

Revision ID: 0041_committee_evidence_verification
Revises: 0040_two_layer_formulation_process
Create Date: 2026-08-06
"""
from __future__ import annotations

import logging

from alembic import op

revision = "0041_committee_evidence_verification"
down_revision = "0040_two_layer_formulation_process"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE committee.committee_evidence "
        "ADD COLUMN IF NOT EXISTS verification TEXT DEFAULT 'verified'"
    )
    op.execute(
        "ALTER TABLE committee.committee_evidence "
        "ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION"
    )
    logger.info("0041: committee_evidence 已增加 verification / confidence 字段")


def downgrade() -> None:
    op.execute("ALTER TABLE committee.committee_evidence DROP COLUMN IF EXISTS verification")
    op.execute("ALTER TABLE committee.committee_evidence DROP COLUMN IF EXISTS confidence")
    logger.info("0041: 已回滚 committee_evidence 核验字段")