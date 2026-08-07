"""0038: 创建 scientific_kernel schema — 科学执行内核数据表

为原生科学服务架构创建独立 schema，包含：
- scientific_kernel.tasks — 科学任务
- scientific_kernel.runs — 执行记录
- scientific_kernel.artifacts — 工件
- scientific_kernel.evidence — 证据包
- scientific_kernel.approvals — 审批请求
- scientific_kernel.outbox — 事务 Outbox

新架构无历史数据负担，使用新表、新契约、新 API。

Revision ID: 0038_scientific_execution_kernel
Revises: 0037_normalize_qc_issues_history
Create Date: 2026-08-01
"""
from __future__ import annotations

import logging

from alembic import op

revision = "0038_scientific_execution_kernel"
down_revision = "0037_normalize_qc_issues_history"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    # 创建 schema
    op.execute("CREATE SCHEMA IF NOT EXISTS scientific_kernel")

    # ── tasks ───────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE scientific_kernel.tasks (
            task_id              TEXT PRIMARY KEY,
            project_id           TEXT NOT NULL,
            capability_id        TEXT NOT NULL,
            title                TEXT NOT NULL,
            description          TEXT NOT NULL DEFAULT '',
            status               TEXT NOT NULL DEFAULT 'pending',
            priority             INTEGER NOT NULL DEFAULT 1,
            input_schema_version TEXT NOT NULL DEFAULT '1.0.0',
            metadata_json        JSONB NOT NULL DEFAULT '{}',
            created_at           TIMESTAMPTZ NOT NULL,
            updated_at           TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_tasks_project_id ON scientific_kernel.tasks (project_id)"
    )
    op.execute(
        "CREATE INDEX idx_tasks_status ON scientific_kernel.tasks (status)"
    )

    # ── runs ────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE scientific_kernel.runs (
            run_id          TEXT PRIMARY KEY,
            task_id         TEXT NOT NULL REFERENCES scientific_kernel.tasks (task_id),
            project_id      TEXT NOT NULL,
            service_id      TEXT NOT NULL,
            command         TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'queued',
            input_json      JSONB NOT NULL DEFAULT '{}',
            output_json     JSONB,
            error_message   TEXT,
            started_at      TIMESTAMPTZ,
            completed_at    TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL,
            updated_at      TIMESTAMPTZ NOT NULL,
            metadata_json   JSONB NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_runs_task_id ON scientific_kernel.runs (task_id)"
    )
    op.execute(
        "CREATE INDEX idx_runs_project_id ON scientific_kernel.runs (project_id)"
    )
    op.execute(
        "CREATE INDEX idx_runs_status ON scientific_kernel.runs (status)"
    )

    # ── artifacts ───────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE scientific_kernel.artifacts (
            artifact_id  TEXT PRIMARY KEY,
            run_id       TEXT NOT NULL REFERENCES scientific_kernel.runs (run_id),
            type         TEXT NOT NULL,
            name         TEXT NOT NULL,
            description  TEXT NOT NULL DEFAULT '',
            content_type TEXT NOT NULL DEFAULT 'application/json',
            data_json    JSONB,
            file_path    TEXT,
            checksum     TEXT,
            created_at   TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_artifacts_run_id ON scientific_kernel.artifacts (run_id)"
    )

    # ── evidence ────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE scientific_kernel.evidence (
            evidence_id    TEXT PRIMARY KEY,
            run_id         TEXT NOT NULL REFERENCES scientific_kernel.runs (run_id),
            task_id        TEXT NOT NULL,
            claim          TEXT NOT NULL,
            value          TEXT,
            unit           TEXT NOT NULL DEFAULT '',
            confidence     REAL NOT NULL DEFAULT 1.0,
            level          TEXT NOT NULL DEFAULT 'medium',
            method         TEXT NOT NULL DEFAULT '',
            source_type    TEXT NOT NULL DEFAULT 'native_service',
            source_service TEXT NOT NULL DEFAULT '',
            schema_version TEXT NOT NULL DEFAULT '1.0.0',
            metadata_json  JSONB NOT NULL DEFAULT '{}',
            created_at     TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_evidence_run_id ON scientific_kernel.evidence (run_id)"
    )
    op.execute(
        "CREATE INDEX idx_evidence_task_id ON scientific_kernel.evidence (task_id)"
    )

    # ── approvals ───────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE scientific_kernel.approvals (
            approval_id  TEXT PRIMARY KEY,
            run_id       TEXT NOT NULL DEFAULT '',
            evidence_id  TEXT NOT NULL REFERENCES scientific_kernel.evidence (evidence_id),
            status       TEXT NOT NULL DEFAULT 'pending',
            requested_by TEXT NOT NULL DEFAULT '',
            reviewed_by  TEXT,
            comment      TEXT,
            reviewed_at  TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL,
            metadata_json JSONB NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_approvals_run_id ON scientific_kernel.approvals (run_id)"
    )
    op.execute(
        "CREATE INDEX idx_approvals_status ON scientific_kernel.approvals (status)"
    )

    # ── outbox ──────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE scientific_kernel.outbox (
            message_id   TEXT PRIMARY KEY,
            event_type   TEXT NOT NULL,
            subject_id   TEXT NOT NULL,
            payload_json JSONB NOT NULL DEFAULT '{}',
            status       TEXT NOT NULL DEFAULT 'pending',
            retry_count  INTEGER NOT NULL DEFAULT 0,
            max_retries  INTEGER NOT NULL DEFAULT 5,
            last_error   TEXT,
            created_at   TIMESTAMPTZ NOT NULL,
            sent_at      TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_outbox_status ON scientific_kernel.outbox (status)"
    )
    op.execute(
        "CREATE INDEX idx_outbox_subject ON scientific_kernel.outbox (subject_id)"
    )

    logger.info("0038: 已创建 scientific_kernel schema（6 张表）")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scientific_kernel.outbox CASCADE")
    op.execute("DROP TABLE IF EXISTS scientific_kernel.approvals CASCADE")
    op.execute("DROP TABLE IF EXISTS scientific_kernel.evidence CASCADE")
    op.execute("DROP TABLE IF EXISTS scientific_kernel.artifacts CASCADE")
    op.execute("DROP TABLE IF EXISTS scientific_kernel.runs CASCADE")
    op.execute("DROP TABLE IF EXISTS scientific_kernel.tasks CASCADE")
    op.execute("DROP SCHEMA IF EXISTS scientific_kernel")
    logger.info("0038: 已删除 scientific_kernel schema")