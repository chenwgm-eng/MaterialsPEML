"""initial schema: 18 PostgreSQL schemas + 52 tables migrated from SQLite.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-26

将现有 24 个 SQLite .db 文件中的 46 张表 + 源码中定义但未持久化的 6 张表
（auth.users / industrialization.material_requests / knowledge.knowledge_graphs /
control_plane.provenance_nodes / control_plane.provenance_edges /
control_plane.outbox_messages）合计 52 张表，按子包划分到 18 个 PostgreSQL schema。

类型转换规则：
- INTEGER PRIMARY KEY AUTOINCREMENT → BIGSERIAL PRIMARY KEY
- TEXT PRIMARY KEY → TEXT PRIMARY KEY（保持）
- TEXT 存 JSON 的字段 → JSONB（GIN 索引）
- 时间 TEXT 字段 → TIMESTAMPTZ
- INTEGER 布尔字段 → BOOLEAN
- REAL → DOUBLE PRECISION
- BLOB → BYTEA
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCHEMAS = [
    "agent_team",
    "control_plane",
    "experiment",
    "committee",
    "industrialization",
    "hybrid",
    "auth",
    "knowledge",
    "release_card",
    "synthesis",
    "value_realization",
    "data_ingest",
    "audit",
    "ecml",
    "middleware",
    "capability",
    "integrations",
    "projects",
]


def upgrade() -> None:
    # 1. 创建所有 18 个 schema
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    # 2. 按 schema 创建所有表（顺序考虑外键依赖）
    _create_projects()
    _create_hybrid()
    _create_experiment()
    _create_committee()
    _create_ecml()
    _create_industrialization()
    _create_auth()
    _create_knowledge()
    _create_release_card()
    _create_synthesis()
    _create_value_realization()
    _create_data_ingest()
    _create_audit()
    _create_agent_team()
    _create_control_plane()
    _create_middleware()
    _create_capability()
    _create_integrations()


def downgrade() -> None:
    for schema in reversed(SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


# ───────────────────────────── projects ─────────────────────────────
def _create_projects() -> None:
    op.execute(
        """
        CREATE TABLE projects.projects (
            project_id          TEXT PRIMARY KEY,
            name                TEXT NOT NULL,
            target_application  TEXT,
            current_stage       TEXT,
            target_properties   JSONB,
            owner               TEXT,
            candidate_ids       JSONB,
            experiment_order_ids JSONB,
            notes               TEXT,
            created_at          TIMESTAMPTZ,
            updated_at          TIMESTAMPTZ,
            department          TEXT,
            start_date          TEXT,
            end_date            TEXT,
            budget              DOUBLE PRECISION DEFAULT 0,
            iteration_progress  BIGINT DEFAULT 0
        )
        """
    )


# ───────────────────────────── hybrid ──────────────────────────────
def _create_hybrid() -> None:
    op.execute(
        """
        CREATE TABLE hybrid.research_requests (
            request_id          TEXT PRIMARY KEY,
            scenario_id         TEXT,
            goal                TEXT NOT NULL,
            material_scope      TEXT,
            target_properties   JSONB,
            constraints         JSONB,
            preference          TEXT DEFAULT 'balanced',
            user_id             TEXT,
            project_id          TEXT,
            execution_profile   TEXT DEFAULT 'standard',
            status              TEXT DEFAULT 'draft',
            created_at          TIMESTAMPTZ,
            updated_at          TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_requests_status ON hybrid.research_requests(status)"
    )

    op.execute(
        """
        CREATE TABLE hybrid.research_plans (
            plan_id             TEXT PRIMARY KEY,
            request_id          TEXT NOT NULL,
            execution_profile   TEXT,
            steps               JSONB,
            rationale           TEXT,
            estimated_budget    TEXT,
            risk_summary        TEXT,
            capabilities_needed JSONB,
            status              TEXT DEFAULT 'draft',
            created_at          TIMESTAMPTZ,
            updated_at          TIMESTAMPTZ,
            CONSTRAINT fk_plans_request
                FOREIGN KEY (request_id)
                REFERENCES hybrid.research_requests(request_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_plans_request ON hybrid.research_plans(request_id)"
    )

    op.execute(
        """
        CREATE TABLE hybrid.routing_outcomes (
            outcome_id          TEXT PRIMARY KEY,
            request_id          TEXT,
            plan_id             TEXT,
            step_id             TEXT,
            alias               TEXT,
            profile             TEXT,
            selected_binding    JSONB,
            skipped_bindings    JSONB,
            reason_code         TEXT,
            policy_version      TEXT,
            created_at          TIMESTAMPTZ,
            CONSTRAINT fk_outcomes_request
                FOREIGN KEY (request_id)
                REFERENCES hybrid.research_requests(request_id),
            CONSTRAINT fk_outcomes_plan
                FOREIGN KEY (plan_id)
                REFERENCES hybrid.research_plans(plan_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_outcomes_plan ON hybrid.routing_outcomes(plan_id)"
    )
    op.execute(
        "CREATE INDEX idx_outcomes_request ON hybrid.routing_outcomes(request_id)"
    )

    op.execute(
        """
        CREATE TABLE hybrid.routing_policy_versions (
            version_id          TEXT PRIMARY KEY,
            version             TEXT,
            weights             JSONB,
            status              TEXT DEFAULT 'draft',
            created_at          TIMESTAMPTZ,
            promoted_at         TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_policy_status ON hybrid.routing_policy_versions(status)"
    )


# ───────────────────────────── experiment ──────────────────────────
def _create_experiment() -> None:
    op.execute(
        """
        CREATE TABLE experiment.candidates (
            candidate_id        TEXT PRIMARY KEY,
            candidate_type      TEXT,
            name                TEXT,
            smiles              TEXT,
            source              TEXT,
            multi_objective_score DOUBLE PRECISION,
            created_at          TIMESTAMPTZ,
            data                JSONB,
            scenario_id         TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_candidates_scenario ON experiment.candidates(scenario_id)"
    )
    op.execute(
        "CREATE INDEX idx_candidates_name ON experiment.candidates(name)"
    )
    op.execute(
        "CREATE INDEX idx_candidates_type ON experiment.candidates(candidate_type)"
    )

    op.execute(
        """
        CREATE TABLE experiment.experiment_orders (
            order_id                TEXT PRIMARY KEY,
            project_id              TEXT,
            rd_package_id           TEXT,
            candidate_id            TEXT,
            formulation_version     TEXT,
            process_version         TEXT,
            test_protocol_version   TEXT,
            execution_mode          TEXT,
            priority                TEXT,
            assignee                TEXT,
            material_requirements   JSONB,
            procedure               TEXT,
            required_results        JSONB,
            acceptance_criteria     JSONB,
            status                  TEXT,
            created_at              TIMESTAMPTZ,
            approved_by             TEXT,
            approved_at             TIMESTAMPTZ,
            notes                   TEXT,
            protocol_provenance     JSONB,
            ai_draft                BOOLEAN DEFAULT FALSE,
            provenance              JSONB DEFAULT '[]',
            scenario_id             TEXT,
            CONSTRAINT fk_orders_project
                FOREIGN KEY (project_id)
                REFERENCES projects.projects(project_id),
            CONSTRAINT fk_orders_candidate
                FOREIGN KEY (candidate_id)
                REFERENCES experiment.candidates(candidate_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE experiment.experiment_result_records (
            result_id               TEXT PRIMARY KEY,
            experiment_order_id     TEXT,
            sample_id               TEXT,
            sample_batch_id         TEXT,
            source_type             TEXT,
            source_system           TEXT,
            uploaded_by             TEXT,
            uploaded_at             TIMESTAMPTZ,
            property_name           TEXT,
            value                   DOUBLE PRECISION,
            unit                    TEXT,
            test_method             TEXT,
            test_conditions         TEXT,
            instrument_id           TEXT,
            raw_file_uri            TEXT,
            qc_status               TEXT,
            qc_issues               JSONB,
            reviewed_by             TEXT,
            reviewed_at             TIMESTAMPTZ,
            learning_eligible       BOOLEAN,
            scenario_id             TEXT,
            CONSTRAINT fk_results_order
                FOREIGN KEY (experiment_order_id)
                REFERENCES experiment.experiment_orders(order_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE experiment.experiment_results (
            task_id              TEXT PRIMARY KEY,
            experiment_type      TEXT,
            status               TEXT,
            measured_values      JSONB,
            raw_data_path        TEXT,
            metadata             JSONB,
            error_message        TEXT
        )
        """
    )

    op.execute(
        """
        CREATE TABLE experiment.experiment_tasks (
            task_id              TEXT PRIMARY KEY,
            experiment_type      TEXT,
            recipe               JSONB,
            parameters           JSONB,
            status               TEXT,
            created_at           TIMESTAMPTZ,
            started_at           TIMESTAMPTZ,
            completed_at         TIMESTAMPTZ
        )
        """
    )

    op.execute(
        """
        CREATE TABLE experiment.notifications (
            notification_id      TEXT PRIMARY KEY,
            order_id             TEXT,
            assignee             TEXT,
            message              TEXT,
            created_at           TIMESTAMPTZ,
            read                 BOOLEAN DEFAULT FALSE,
            CONSTRAINT fk_notifications_order
                FOREIGN KEY (order_id)
                REFERENCES experiment.experiment_orders(order_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE experiment.analysis_results (
            analysis_id          TEXT PRIMARY KEY,
            order_id             TEXT,
            analysis_json        JSONB,
            created_at           TIMESTAMPTZ,
            CONSTRAINT fk_analysis_order
                FOREIGN KEY (order_id)
                REFERENCES experiment.experiment_orders(order_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE experiment.samples (
            sample_id            TEXT PRIMARY KEY,
            name                 TEXT,
            source_type          TEXT,
            source_order_id      TEXT,
            source_candidate_id  TEXT,
            batch_number         TEXT,
            quantity             DOUBLE PRECISION,
            unit                 TEXT,
            status               TEXT,
            storage_location     TEXT,
            storage_condition    TEXT,
            created_at           TIMESTAMPTZ,
            updated_at           TIMESTAMPTZ,
            notes                TEXT,
            sample_code          TEXT,
            chemical_formula     TEXT,
            scenario_id          TEXT,
            CONSTRAINT fk_samples_order
                FOREIGN KEY (source_order_id)
                REFERENCES experiment.experiment_orders(order_id),
            CONSTRAINT fk_samples_candidate
                FOREIGN KEY (source_candidate_id)
                REFERENCES experiment.candidates(candidate_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE experiment.sample_transfers (
            transfer_id          TEXT PRIMARY KEY,
            sample_id            TEXT,
            from_status          TEXT,
            to_status            TEXT,
            from_location        TEXT,
            to_location          TEXT,
            transferred_by       TEXT,
            transferred_at       TIMESTAMPTZ,
            notes                TEXT,
            CONSTRAINT fk_transfers_sample
                FOREIGN KEY (sample_id)
                REFERENCES experiment.samples(sample_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE experiment.equipment (
            equipment_id          TEXT PRIMARY KEY,
            name                  TEXT,
            model                 TEXT,
            category              TEXT,
            serial_number         TEXT,
            location              TEXT,
            status                TEXT,
            last_calibration      TEXT,
            next_calibration      TEXT,
            responsible_person    TEXT,
            purchase_date         TEXT,
            notes                 TEXT
        )
        """
    )

    op.execute(
        """
        CREATE TABLE experiment.ideas (
            idea_id               TEXT PRIMARY KEY,
            name                  TEXT,
            description           TEXT,
            material_type         TEXT,
            smiles                TEXT,
            formula               TEXT,
            target_properties     JSONB,
            status                TEXT,
            verification_result   TEXT,
            score                 DOUBLE PRECISION,
            created_at            TIMESTAMPTZ,
            updated_at            TIMESTAMPTZ,
            notes                 TEXT,
            provenance            JSONB DEFAULT '[]'
        )
        """
    )


# ───────────────────────────── committee ───────────────────────────
def _create_committee() -> None:
    op.execute(
        """
        CREATE TABLE committee.committee_cases (
            case_id              TEXT PRIMARY KEY,
            committee_type       TEXT NOT NULL,
            project_id           TEXT,
            ecml_run_id          TEXT,
            candidate_id         TEXT,
            trigger_code         TEXT NOT NULL,
            risk_level           TEXT NOT NULL,
            status               TEXT NOT NULL,
            input_snapshot_hash  TEXT NOT NULL,
            policy_version       TEXT NOT NULL,
            created_by           TEXT,
            created_at           TIMESTAMPTZ NOT NULL,
            updated_at           TIMESTAMPTZ NOT NULL
        )
        """
    )

    op.execute(
        """
        CREATE TABLE committee.committee_evidence (
            evidence_id          TEXT PRIMARY KEY,
            case_id              TEXT NOT NULL,
            source_type          TEXT NOT NULL,
            source_name          TEXT NOT NULL,
            capability           TEXT NOT NULL,
            status               TEXT NOT NULL,
            value_summary_json   JSONB,
            raw_artifact_ref     TEXT,
            provenance_json      JSONB NOT NULL,
            created_at           TIMESTAMPTZ NOT NULL,
            CONSTRAINT fk_evidence_case
                FOREIGN KEY (case_id)
                REFERENCES committee.committee_cases(case_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_evidence_case ON committee.committee_evidence(case_id)"
    )

    op.execute(
        """
        CREATE TABLE committee.committee_proposals (
            proposal_id              TEXT PRIMARY KEY,
            case_id                  TEXT NOT NULL,
            content_json             JSONB NOT NULL,
            assumptions_json         JSONB NOT NULL,
            requested_evidence_json  JSONB NOT NULL,
            provenance_json          JSONB NOT NULL,
            created_at               TIMESTAMPTZ NOT NULL,
            CONSTRAINT fk_proposals_case
                FOREIGN KEY (case_id)
                REFERENCES committee.committee_cases(case_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_proposals_case ON committee.committee_proposals(case_id)"
    )

    op.execute(
        """
        CREATE TABLE committee.committee_verdicts (
            verdict_id                TEXT PRIMARY KEY,
            case_id                   TEXT NOT NULL,
            decision                  TEXT NOT NULL,
            scorecard_json            JSONB NOT NULL,
            blocking_reasons_json     JSONB NOT NULL,
            warnings_json             JSONB NOT NULL,
            required_actions_json     JSONB NOT NULL,
            created_at                TIMESTAMPTZ NOT NULL,
            CONSTRAINT fk_verdicts_case
                FOREIGN KEY (case_id)
                REFERENCES committee.committee_cases(case_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_verdicts_case ON committee.committee_verdicts(case_id)"
    )

    op.execute(
        """
        CREATE TABLE committee.committee_events (
            id                   BIGSERIAL PRIMARY KEY,
            case_id              TEXT NOT NULL,
            event_type           TEXT NOT NULL,
            data_json            JSONB NOT NULL,
            timestamp            TIMESTAMPTZ NOT NULL,
            CONSTRAINT fk_events_case
                FOREIGN KEY (case_id)
                REFERENCES committee.committee_cases(case_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_committee_events_case_id ON committee.committee_events(case_id)"
    )
    op.execute(
        "CREATE INDEX idx_committee_events_timestamp ON committee.committee_events(timestamp)"
    )


# ───────────────────────────── ecml ────────────────────────────────
def _create_ecml() -> None:
    op.execute(
        """
        CREATE TABLE ecml.ecml_runs (
            run_id               TEXT PRIMARY KEY,
            target               TEXT,
            target_property      TEXT,
            state_json           JSONB,
            created_at           TIMESTAMPTZ,
            updated_at           TIMESTAMPTZ,
            run_source           TEXT DEFAULT ''
        )
        """
    )

    op.execute(
        """
        CREATE TABLE ecml.ecml_runs_index (
            run_id               TEXT,
            status               TEXT,
            iteration            BIGINT,
            is_complete          BOOLEAN,
            created_at           TIMESTAMPTZ,
            run_status           TEXT DEFAULT 'running',
            iteration_id         BIGINT DEFAULT 1,
            parent_run_id        TEXT DEFAULT '',
            scenario_id          TEXT DEFAULT ''
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_ecml_runs_index_run_id ON ecml.ecml_runs_index(run_id)"
    )
    op.execute(
        "CREATE INDEX idx_ecml_runs_index_scenario ON ecml.ecml_runs_index(scenario_id)"
    )


# ───────────────────────────── industrialization ───────────────────
def _create_industrialization() -> None:
    op.execute(
        """
        CREATE TABLE industrialization.raw_materials (
            material_id          TEXT PRIMARY KEY,
            name                 TEXT,
            smiles               TEXT,
            category             TEXT,
            inventory_kg         DOUBLE PRECISION,
            cost_per_kg          DOUBLE PRECISION,
            supplier             TEXT,
            reach_compliant      BOOLEAN,
            is_toxic             BOOLEAN,
            batch_number         TEXT DEFAULT '',
            expiry_date          TEXT DEFAULT '',
            coa_uri              TEXT DEFAULT '',
            min_order_quantity   DOUBLE PRECISION DEFAULT 0.0,
            version              BIGINT DEFAULT 1,
            updated_by           TEXT DEFAULT '',
            update_reason        TEXT DEFAULT '',
            data_source          TEXT DEFAULT 'measured',
            prediction_meta      JSONB DEFAULT '{}'
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_raw_materials_name ON industrialization.raw_materials(name)"
    )
    op.execute(
        "CREATE INDEX idx_raw_materials_category ON industrialization.raw_materials(category)"
    )
    op.execute(
        "CREATE INDEX idx_raw_materials_prediction_meta "
        "ON industrialization.raw_materials USING GIN (prediction_meta)"
    )

    op.execute(
        """
        CREATE TABLE industrialization.material_requests (
            request_id           TEXT PRIMARY KEY,
            material_data        JSONB,
            request_type         TEXT,
            requester            TEXT,
            status               TEXT,
            submitted_at         TIMESTAMPTZ,
            reviewed_by          TEXT,
            reviewed_at          TIMESTAMPTZ,
            review_comment       TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_mr_status ON industrialization.material_requests(status)"
    )


# ───────────────────────────── auth ────────────────────────────────
def _create_auth() -> None:
    op.execute(
        """
        CREATE TABLE auth.users (
            user_id              TEXT PRIMARY KEY,
            username             TEXT UNIQUE,
            display_name         TEXT,
            email                TEXT,
            role                 TEXT,
            project_ids          JSONB,
            is_active            BOOLEAN,
            created_at           TIMESTAMPTZ,
            last_login           TIMESTAMPTZ,
            password_hash        TEXT
        )
        """
    )


# ───────────────────────────── knowledge ───────────────────────────
def _create_knowledge() -> None:
    op.execute(
        """
        CREATE TABLE knowledge.knowledge_graphs (
            graph_id             TEXT PRIMARY KEY,
            name                 TEXT,
            query                TEXT,
            nodes_json           JSONB,
            edges_json           JSONB,
            node_count           BIGINT,
            edge_count           BIGINT,
            paper_count          BIGINT,
            created_by           TEXT,
            created_at           TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_kg_created ON knowledge.knowledge_graphs(created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_kg_nodes_gin ON knowledge.knowledge_graphs USING GIN (nodes_json)"
    )
    op.execute(
        "CREATE INDEX idx_kg_edges_gin ON knowledge.knowledge_graphs USING GIN (edges_json)"
    )


# ───────────────────────────── release_card ────────────────────────
def _create_release_card() -> None:
    op.execute(
        """
        CREATE TABLE release_card.release_cards (
            card_id              TEXT PRIMARY KEY,
            case_id              TEXT,
            project_id           TEXT,
            candidate_id         TEXT,
            title                TEXT NOT NULL,
            recommendation       TEXT NOT NULL,
            status               TEXT NOT NULL,
            card_json            JSONB NOT NULL,
            created_at           TIMESTAMPTZ NOT NULL,
            updated_at           TIMESTAMPTZ NOT NULL,
            CONSTRAINT fk_release_cards_case
                FOREIGN KEY (case_id)
                REFERENCES committee.committee_cases(case_id),
            CONSTRAINT fk_release_cards_project
                FOREIGN KEY (project_id)
                REFERENCES projects.projects(project_id),
            CONSTRAINT fk_release_cards_candidate
                FOREIGN KEY (candidate_id)
                REFERENCES experiment.candidates(candidate_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_release_cards_case ON release_card.release_cards(case_id)"
    )
    op.execute(
        "CREATE INDEX idx_release_cards_project ON release_card.release_cards(project_id)"
    )
    op.execute(
        "CREATE INDEX idx_release_cards_recommendation ON release_card.release_cards(recommendation)"
    )
    op.execute(
        "CREATE INDEX idx_release_cards_status ON release_card.release_cards(status)"
    )


# ───────────────────────────── synthesis ───────────────────────────
def _create_synthesis() -> None:
    op.execute(
        """
        CREATE TABLE synthesis.synthesis_tasks (
            task_id              TEXT PRIMARY KEY,
            smiles               TEXT NOT NULL,
            num_routes           BIGINT DEFAULT 3,
            status               TEXT NOT NULL DEFAULT 'pending',
            source               TEXT NOT NULL DEFAULT 'auto',
            result_json          JSONB,
            error                TEXT,
            created_at           TIMESTAMPTZ,
            updated_at           TIMESTAMPTZ,
            duration_ms          BIGINT
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_synthesis_status ON synthesis.synthesis_tasks(status)"
    )
    op.execute(
        "CREATE INDEX idx_synthesis_result_gin ON synthesis.synthesis_tasks USING GIN (result_json)"
    )


# ───────────────────────────── value_realization ───────────────────
def _create_value_realization() -> None:
    op.execute(
        """
        CREATE TABLE value_realization.baselines (
            project_id                  TEXT PRIMARY KEY,
            historical_cycle_days       DOUBLE PRECISION,
            typical_experiment_cost     DOUBLE PRECISION,
            historical_hit_rate         DOUBLE PRECISION,
            success_criteria            JSONB,
            past_candidate_count        BIGINT,
            notes                       TEXT,
            updated_at                  TIMESTAMPTZ
        )
        """
    )

    op.execute(
        """
        CREATE TABLE value_realization.cost_rules (
            rule_id              TEXT PRIMARY KEY,
            name                 TEXT NOT NULL,
            category             TEXT,
            unit_price           DOUBLE PRECISION,
            unit                 TEXT,
            currency             TEXT,
            enabled              BOOLEAN,
            notes                TEXT
        )
        """
    )


# ───────────────────────────── data_ingest ─────────────────────────
def _create_data_ingest() -> None:
    op.execute(
        """
        CREATE TABLE data_ingest.imports (
            import_id            TEXT PRIMARY KEY,
            idempotency_key      TEXT UNIQUE,
            entity_type          TEXT,
            file_name            TEXT,
            operator             TEXT,
            total_rows           BIGINT,
            success_rows         BIGINT,
            failed_rows          BIGINT,
            status               TEXT,
            quality_summary      JSONB,
            created_at           TIMESTAMPTZ
        )
        """
    )

    op.execute(
        """
        CREATE TABLE data_ingest.import_rows (
            id                   BIGSERIAL PRIMARY KEY,
            import_id            TEXT,
            row_index            BIGINT,
            status               TEXT,
            error                TEXT,
            payload              JSONB,
            CONSTRAINT fk_import_rows_import
                FOREIGN KEY (import_id)
                REFERENCES data_ingest.imports(import_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_import_rows_import ON data_ingest.import_rows(import_id)"
    )


# ───────────────────────────── audit ───────────────────────────────
def _create_audit() -> None:
    op.execute(
        """
        CREATE TABLE audit.audit_log (
            entry_id             TEXT PRIMARY KEY,
            event_type           TEXT,
            module               TEXT,
            action               TEXT,
            detail               JSONB,
            operator             TEXT,
            confirmed            BOOLEAN,
            created_at           TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_audit_log_module ON audit.audit_log(module)"
    )
    op.execute(
        "CREATE INDEX idx_audit_log_created_at ON audit.audit_log(created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_audit_log_detail_gin ON audit.audit_log USING GIN (detail)"
    )


# ───────────────────────────── agent_team ──────────────────────────
def _create_agent_team() -> None:
    op.execute(
        """
        CREATE TABLE agent_team.custom_agents (
            id                   TEXT PRIMARY KEY,
            data                 JSONB NOT NULL,
            created_at           TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_custom_agents_data_gin ON agent_team.custom_agents USING GIN (data)"
    )

    op.execute(
        """
        CREATE TABLE agent_team.tool_eligibility_rules (
            rule_id              TEXT PRIMARY KEY,
            agent_id             TEXT NOT NULL,
            capability           TEXT NOT NULL,
            data                 JSONB NOT NULL,
            created_at           TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_elig_cap ON agent_team.tool_eligibility_rules(capability)"
    )
    op.execute(
        "CREATE INDEX idx_elig_agent ON agent_team.tool_eligibility_rules(agent_id)"
    )

    op.execute(
        """
        CREATE TABLE agent_team.agent_events (
            event_id             TEXT PRIMARY KEY,
            agent_id             TEXT NOT NULL,
            agent_name           TEXT NOT NULL DEFAULT '',
            related_run_id       TEXT NOT NULL DEFAULT '',
            step                 TEXT NOT NULL DEFAULT '',
            invoked_at           TIMESTAMPTZ NOT NULL,
            input_summary        TEXT,
            output_summary       TEXT,
            duration_ms          BIGINT NOT NULL DEFAULT 0,
            status               TEXT NOT NULL DEFAULT 'success',
            token_cost           DOUBLE PRECISION NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_agent_events_agent ON agent_team.agent_events(agent_id)"
    )
    op.execute(
        "CREATE INDEX idx_agent_events_run ON agent_team.agent_events(related_run_id)"
    )

    op.execute(
        """
        CREATE TABLE agent_team.research_events (
            event_id             TEXT PRIMARY KEY,
            event_type           TEXT NOT NULL,
            run_id               TEXT NOT NULL DEFAULT '',
            title                TEXT NOT NULL DEFAULT '',
            summary              TEXT NOT NULL DEFAULT '',
            status               TEXT NOT NULL DEFAULT 'success',
            run_source           TEXT NOT NULL DEFAULT 'production',
            payload              JSONB,
            created_at           TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_research_events_created ON agent_team.research_events(created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_research_events_run ON agent_team.research_events(run_id)"
    )
    op.execute(
        "CREATE INDEX idx_research_events_type ON agent_team.research_events(event_type)"
    )
    op.execute(
        "CREATE INDEX idx_research_events_payload_gin ON agent_team.research_events USING GIN (payload)"
    )


# ───────────────────────────── control_plane ───────────────────────
def _create_control_plane() -> None:
    op.execute(
        """
        CREATE TABLE control_plane.runs (
            run_id               TEXT PRIMARY KEY,
            run_type             TEXT NOT NULL,
            project_id           TEXT,
            parent_run_id        TEXT,
            status               TEXT NOT NULL,
            input_hash           TEXT NOT NULL,
            plan_version         TEXT,
            policy_version       TEXT NOT NULL,
            idempotency_key      TEXT UNIQUE,
            checkpoint_ref       TEXT,
            metadata_json        JSONB,
            created_at           TIMESTAMPTZ NOT NULL,
            updated_at           TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_runs_parent_run_id ON control_plane.runs(parent_run_id)"
    )
    op.execute(
        "CREATE INDEX idx_runs_status ON control_plane.runs(status)"
    )
    op.execute(
        "CREATE INDEX idx_runs_project_id ON control_plane.runs(project_id)"
    )

    op.execute(
        """
        CREATE TABLE control_plane.checkpoints (
            checkpoint_id        TEXT PRIMARY KEY,
            run_id               TEXT NOT NULL,
            step_name            TEXT NOT NULL,
            step_index           BIGINT NOT NULL,
            status               TEXT NOT NULL,
            input_hash           TEXT NOT NULL,
            output_summary_json  JSONB,
            intent_log_json      JSONB,
            created_at           TIMESTAMPTZ NOT NULL,
            CONSTRAINT fk_checkpoints_run
                FOREIGN KEY (run_id)
                REFERENCES control_plane.runs(run_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_checkpoints_run_step ON control_plane.checkpoints(run_id, step_index)"
    )
    op.execute(
        "CREATE INDEX idx_checkpoints_run_id ON control_plane.checkpoints(run_id)"
    )

    op.execute(
        """
        CREATE TABLE control_plane.budget_envelopes (
            scope                TEXT NOT NULL,
            scope_id             TEXT NOT NULL,
            token_limit          BIGINT,
            external_call_limit  BIGINT,
            dft_cpu_hour_limit   DOUBLE PRECISION,
            cost_limit           DOUBLE PRECISION,
            concurrency_limit    BIGINT,
            action_on_exhaustion TEXT DEFAULT 'pause',
            PRIMARY KEY (scope, scope_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE control_plane.budget_ledger (
            ledger_id            TEXT PRIMARY KEY,
            scope_type           TEXT NOT NULL,
            scope_id             TEXT NOT NULL,
            run_id               TEXT,
            category             TEXT NOT NULL,
            reserved_amount      DOUBLE PRECISION NOT NULL,
            settled_amount       DOUBLE PRECISION,
            status               TEXT NOT NULL,
            created_at           TIMESTAMPTZ NOT NULL,
            CONSTRAINT fk_budget_ledger_run
                FOREIGN KEY (run_id)
                REFERENCES control_plane.runs(run_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_budget_ledger_status ON control_plane.budget_ledger(status)"
    )
    op.execute(
        "CREATE INDEX idx_budget_ledger_run ON control_plane.budget_ledger(run_id)"
    )
    op.execute(
        "CREATE INDEX idx_budget_ledger_scope ON control_plane.budget_ledger(scope_type, scope_id)"
    )

    op.execute(
        """
        CREATE TABLE control_plane.memory_cards (
            card_id              TEXT PRIMARY KEY,
            project_id           TEXT,
            entity_type          TEXT NOT NULL,
            entity_id            TEXT NOT NULL,
            card_type            TEXT NOT NULL,
            content_json         JSONB NOT NULL,
            provenance_json      JSONB NOT NULL,
            access_level         TEXT NOT NULL,
            validity_status      TEXT NOT NULL DEFAULT 'active',
            created_at           TIMESTAMPTZ NOT NULL,
            updated_at           TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_mem_validity ON control_plane.memory_cards(validity_status)"
    )
    op.execute(
        "CREATE INDEX idx_mem_entity ON control_plane.memory_cards(entity_type, entity_id)"
    )
    op.execute(
        "CREATE INDEX idx_mem_type ON control_plane.memory_cards(card_type)"
    )
    op.execute(
        "CREATE INDEX idx_mem_project ON control_plane.memory_cards(project_id)"
    )
    op.execute(
        "CREATE INDEX idx_mem_content_gin ON control_plane.memory_cards USING GIN (content_json)"
    )

    op.execute(
        """
        CREATE TABLE control_plane.providers (
            provider_id                   TEXT PRIMARY KEY,
            provider_type                 TEXT NOT NULL,
            name                          TEXT NOT NULL,
            endpoint                      TEXT NOT NULL,
            auth_secret_ref               TEXT NOT NULL,
            version                       TEXT,
            health_status                 TEXT NOT NULL DEFAULT 'unknown',
            health_check_url              TEXT,
            health_check_interval_seconds BIGINT DEFAULT 300,
            last_health_check             TIMESTAMPTZ,
            quota_limit_json              JSONB,
            quota_used_json               JSONB,
            schema_snapshot_json          JSONB,
            data_processing_level         TEXT DEFAULT 'internal',
            fallback_provider_id          TEXT,
            owner                         TEXT DEFAULT 'system',
            enabled                       BOOLEAN DEFAULT TRUE,
            created_at                    TIMESTAMPTZ NOT NULL,
            updated_at                    TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_providers_type ON control_plane.providers(provider_type)"
    )
    op.execute(
        "CREATE INDEX idx_providers_enabled ON control_plane.providers(enabled)"
    )

    op.execute(
        """
        CREATE TABLE control_plane.trace_events (
            event_id             TEXT PRIMARY KEY,
            correlation_id       TEXT NOT NULL,
            trace_id             TEXT,
            run_id               TEXT,
            event_type           TEXT NOT NULL,
            entity_type          TEXT,
            entity_id            TEXT,
            summary              TEXT,
            details_json         JSONB,
            timestamp            TIMESTAMPTZ NOT NULL,
            CONSTRAINT fk_trace_run
                FOREIGN KEY (run_id)
                REFERENCES control_plane.runs(run_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_trace_type ON control_plane.trace_events(event_type)"
    )
    op.execute(
        "CREATE INDEX idx_trace_run ON control_plane.trace_events(run_id)"
    )
    op.execute(
        "CREATE INDEX idx_trace_correlation ON control_plane.trace_events(correlation_id)"
    )

    op.execute(
        """
        CREATE TABLE control_plane.provenance_nodes (
            record_id            TEXT PRIMARY KEY,
            run_id               TEXT,
            correlation_id       TEXT NOT NULL,
            entity_type          TEXT NOT NULL,
            entity_id            TEXT NOT NULL,
            source               TEXT NOT NULL,
            source_version       TEXT,
            input_hash           TEXT,
            output_artifact_path TEXT,
            metadata_json        JSONB,
            created_at           TIMESTAMPTZ NOT NULL,
            CONSTRAINT fk_prov_node_run
                FOREIGN KEY (run_id)
                REFERENCES control_plane.runs(run_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_prov_node_entity ON control_plane.provenance_nodes(entity_type, entity_id)"
    )
    op.execute(
        "CREATE INDEX idx_prov_node_corr ON control_plane.provenance_nodes(correlation_id)"
    )
    op.execute(
        "CREATE INDEX idx_prov_node_run ON control_plane.provenance_nodes(run_id)"
    )

    op.execute(
        """
        CREATE TABLE control_plane.provenance_edges (
            from_id              TEXT NOT NULL,
            to_id                TEXT NOT NULL,
            relation_type        TEXT NOT NULL,
            created_at           TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (from_id, to_id, relation_type),
            CONSTRAINT fk_prov_edge_from
                FOREIGN KEY (from_id)
                REFERENCES control_plane.provenance_nodes(record_id),
            CONSTRAINT fk_prov_edge_to
                FOREIGN KEY (to_id)
                REFERENCES control_plane.provenance_nodes(record_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_prov_edge_from ON control_plane.provenance_edges(from_id)"
    )
    op.execute(
        "CREATE INDEX idx_prov_edge_to ON control_plane.provenance_edges(to_id)"
    )

    op.execute(
        """
        CREATE TABLE control_plane.outbox_messages (
            message_id           TEXT PRIMARY KEY,
            run_id               TEXT,
            target_type          TEXT NOT NULL,
            target_endpoint      TEXT NOT NULL,
            payload_json         JSONB NOT NULL,
            idempotency_key      TEXT UNIQUE,
            status               TEXT NOT NULL DEFAULT 'pending',
            retry_count          BIGINT NOT NULL DEFAULT 0,
            max_retries          BIGINT NOT NULL DEFAULT 5,
            last_error           TEXT,
            created_at           TIMESTAMPTZ NOT NULL,
            sent_at              TIMESTAMPTZ,
            CONSTRAINT fk_outbox_run
                FOREIGN KEY (run_id)
                REFERENCES control_plane.runs(run_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_outbox_status ON control_plane.outbox_messages(status)"
    )
    op.execute(
        "CREATE INDEX idx_outbox_run_id ON control_plane.outbox_messages(run_id)"
    )
    op.execute(
        "CREATE INDEX idx_outbox_created_at ON control_plane.outbox_messages(created_at)"
    )

    op.execute(
        """
        CREATE TABLE control_plane.versions (
            version_id           TEXT PRIMARY KEY,
            entity_type          TEXT,
            entity_id            TEXT,
            version_number       BIGINT,
            snapshot             JSONB,
            change_summary       TEXT,
            created_by           TEXT,
            created_at           TIMESTAMPTZ,
            is_active            BOOLEAN
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_versions_entity ON control_plane.versions(entity_type, entity_id, version_number)"
    )
    op.execute(
        "CREATE INDEX idx_versions_snapshot_gin ON control_plane.versions USING GIN (snapshot)"
    )


# ───────────────────────────── middleware ──────────────────────────
def _create_middleware() -> None:
    # 兼容只读表：迁移后废弃写入，保留 query_records 兼容只读接口。
    op.execute(
        """
        CREATE TABLE middleware.experiment_records (
            id                   BIGSERIAL PRIMARY KEY,
            sample_id            TEXT NOT NULL,
            formula              TEXT NOT NULL,
            experiment_type      TEXT NOT NULL,
            conditions           JSONB,
            measured_values      JSONB,
            source               TEXT,
            batch_id             TEXT,
            operator             TEXT,
            created_at           TIMESTAMPTZ,
            order_id             TEXT DEFAULT '',
            candidate_id         TEXT DEFAULT '',
            UNIQUE (sample_id, formula, experiment_type)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_middleware_exp_records_sample ON middleware.experiment_records(sample_id)"
    )
    op.execute(
        "CREATE INDEX idx_middleware_exp_records_order ON middleware.experiment_records(order_id)"
    )


# ───────────────────────────── capability ──────────────────────────
def _create_capability() -> None:
    op.execute(
        """
        CREATE TABLE capability.capability_contracts (
            capability_id        TEXT PRIMARY KEY,
            name                 TEXT NOT NULL,
            provider             TEXT,
            risk_level           TEXT,
            status               TEXT,
            payload              JSONB NOT NULL,
            created_at           TIMESTAMPTZ,
            updated_at           TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_capability_name ON capability.capability_contracts(name)"
    )
    op.execute(
        "CREATE INDEX idx_capability_payload_gin ON capability.capability_contracts USING GIN (payload)"
    )


# ───────────────────────────── integrations ────────────────────────
def _create_integrations() -> None:
    op.execute(
        """
        CREATE TABLE integrations.external_invocations (
            invocation_id        TEXT PRIMARY KEY,
            correlation_id       TEXT NOT NULL,
            project_id           TEXT,
            run_id               TEXT,
            actor_id             TEXT,
            provider             TEXT NOT NULL,
            capability           TEXT NOT NULL,
            server_id            TEXT,
            remote_tool_name     TEXT,
            model_name           TEXT,
            status               TEXT NOT NULL,
            input_sha256         TEXT NOT NULL,
            input_redacted_json  JSONB NOT NULL,
            output_summary_json  JSONB,
            raw_output_ref       TEXT,
            error_code           TEXT,
            error_message        TEXT,
            latency_ms           BIGINT NOT NULL,
            retry_count          BIGINT DEFAULT 0,
            created_at           TIMESTAMPTZ NOT NULL,
            CONSTRAINT fk_invocation_project
                FOREIGN KEY (project_id)
                REFERENCES projects.projects(project_id),
            CONSTRAINT fk_invocation_run
                FOREIGN KEY (run_id)
                REFERENCES control_plane.runs(run_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_invocation_project ON integrations.external_invocations(project_id, created_at)"
    )
    op.execute(
        "CREATE INDEX idx_invocation_run ON integrations.external_invocations(run_id, created_at)"
    )
    op.execute(
        "CREATE INDEX idx_invocation_input_gin ON integrations.external_invocations USING GIN (input_redacted_json)"
    )
