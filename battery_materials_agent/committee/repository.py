"""SQLAlchemy Engine-backed repository for committee cases, evidence, proposals, and verdicts."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import text

from ..db import get_engine
from ..mdm.reference_dict import ReferenceDictStore
from .enums import CaseStatus, CommitteeType, Decision, EvidenceSource, RiskLevel
from .models import CommitteeCase, CommitteeVerdict, EvidenceItem, Proposal


def _to_datetime(value):
    """兼容 psycopg3 返回的 datetime 对象或 ISO 字符串。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _safe_json(value, default):
    """安全解析 JSON 字段，兼容 psycopg3 对 JSONB 列的自动反序列化。

    psycopg3 读取 JSONB 列时会直接返回 Python dict/list，
    再次调用 ``json.loads`` 会抛 ``TypeError: the JSON object must be str,
    bytes or bytearray, not dict``。此助手统一处理两种来源。
    """
    if not value:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
    return value


class CommitteeRepository:
    """SQLAlchemy Engine CRUD for committee cases, evidence, proposals, and verdicts.

    Schema is managed by alembic（committee.committee_cases / committee_evidence /
    committee_proposals / committee_verdicts）。
    """

    def __init__(self, db_path: str | None = None):
        # db_path 参数已废弃：schema 由 alembic 管理，统一通过 get_engine() 获取 Engine。
        self.engine = get_engine()
        self._mdm = ReferenceDictStore()

    def _require_dimension(self, domain: str, code: str) -> None:
        if self._mdm.get_dimension(domain, code) is None:
            raise ValueError(f"Invalid dimension code '{code}' for domain '{domain}'")

    def _require_status_code(self, domain: str, code: str) -> None:
        if self._mdm.get_status_code(domain, code) is None:
            raise ValueError(f"Invalid status code '{code}' for domain '{domain}'")

    # ── Cases ────────────────────────────────────────────────

    def create_case(self, case: CommitteeCase) -> CommitteeCase:
        self._require_dimension("committee_type", case.committee_type.value)
        self._require_status_code("case", case.status.value)
        self._require_dimension("trigger_code", case.trigger_code)
        self._require_dimension("risk_level", case.risk_level.value)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO committee.committee_cases
                       (case_id, committee_type, project_id, ecml_run_id, candidate_id,
                        trigger_code, risk_level, status, input_snapshot_hash,
                        policy_version, created_by, created_at, updated_at)
                       VALUES (:case_id, :committee_type, :project_id, :ecml_run_id, :candidate_id,
                               :trigger_code, :risk_level, :status, :input_snapshot_hash,
                               :policy_version, :created_by, :created_at, :updated_at)
                       ON CONFLICT (case_id) DO UPDATE SET
                           committee_type = EXCLUDED.committee_type,
                           project_id = EXCLUDED.project_id,
                           ecml_run_id = EXCLUDED.ecml_run_id,
                           candidate_id = EXCLUDED.candidate_id,
                           trigger_code = EXCLUDED.trigger_code,
                           risk_level = EXCLUDED.risk_level,
                           status = EXCLUDED.status,
                           input_snapshot_hash = EXCLUDED.input_snapshot_hash,
                           policy_version = EXCLUDED.policy_version,
                           created_by = EXCLUDED.created_by,
                           updated_at = EXCLUDED.updated_at"""
                ),
                {
                    "case_id": case.case_id,
                    "committee_type": case.committee_type.value,
                    "project_id": case.project_id,
                    "ecml_run_id": case.ecml_run_id,
                    "candidate_id": case.candidate_id,
                    "trigger_code": case.trigger_code,
                    "risk_level": case.risk_level.value,
                    "status": case.status.value,
                    "input_snapshot_hash": case.input_snapshot_hash,
                    "policy_version": case.policy_version,
                    "created_by": case.created_by,
                    "created_at": case.created_at.isoformat(),
                    "updated_at": case.updated_at.isoformat(),
                },
            )
        return case

    def get_case(self, case_id: str) -> CommitteeCase | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM committee.committee_cases WHERE case_id = :case_id"),
                {"case_id": case_id},
            ).mappings().first()
        if row is None:
            return None
        return self._row_to_case(row)

    def update_case_status(self, case_id: str, status: CaseStatus) -> None:
        self._require_status_code("case", status.value)
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE committee.committee_cases SET status = :status, updated_at = :updated_at "
                    "WHERE case_id = :case_id"
                ),
                {"status": status.value, "updated_at": now, "case_id": case_id},
            )

    def list_cases(
        self,
        committee_type: CommitteeType | None = None,
        status: CaseStatus | None = None,
        project_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CommitteeCase]:
        query = "SELECT * FROM committee.committee_cases WHERE 1=1"
        params: dict[str, object] = {}

        if committee_type is not None:
            query += " AND committee_type = :committee_type"
            params["committee_type"] = committee_type.value
        if status is not None:
            query += " AND status = :status"
            params["status"] = status.value
        if project_id is not None:
            query += " AND project_id = :project_id"
            params["project_id"] = project_id

        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).mappings().all()

        return [self._row_to_case(row) for row in rows]

    # ── Proposals ────────────────────────────────────────────

    def save_proposal(self, proposal: Proposal) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO committee.committee_proposals
                       (proposal_id, case_id, content_json, assumptions_json,
                        requested_evidence_json, provenance_json, created_at)
                       VALUES (:proposal_id, :case_id, :content_json, :assumptions_json,
                               :requested_evidence_json, :provenance_json, :created_at)
                       ON CONFLICT (proposal_id) DO UPDATE SET
                           case_id = EXCLUDED.case_id,
                           content_json = EXCLUDED.content_json,
                           assumptions_json = EXCLUDED.assumptions_json,
                           requested_evidence_json = EXCLUDED.requested_evidence_json,
                           provenance_json = EXCLUDED.provenance_json,
                           created_at = EXCLUDED.created_at"""
                ),
                {
                    "proposal_id": proposal.proposal_id,
                    "case_id": proposal.case_id,
                    "content_json": json.dumps(proposal.content),
                    "assumptions_json": json.dumps(proposal.assumptions),
                    "requested_evidence_json": json.dumps(proposal.requested_evidence),
                    "provenance_json": json.dumps(proposal.model_provenance),
                    "created_at": proposal.created_at.isoformat(),
                },
            )

    def get_proposal_by_case(self, case_id: str) -> Proposal | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM committee.committee_proposals WHERE case_id = :case_id "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"case_id": case_id},
            ).mappings().first()
        if row is None:
            return None
        return Proposal(
            proposal_id=row["proposal_id"],
            case_id=row["case_id"],
            content=_safe_json(row["content_json"], {}),
            assumptions=_safe_json(row["assumptions_json"], []),
            requested_evidence=_safe_json(row["requested_evidence_json"], []),
            model_provenance=_safe_json(row["provenance_json"], {}),
            created_at=_to_datetime(row["created_at"]),
        )

    # ── Evidence ─────────────────────────────────────────────

    def save_evidence(self, evidence: EvidenceItem) -> None:
        self._require_dimension("evidence_source", evidence.source_type.value)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO committee.committee_evidence
                       (evidence_id, case_id, source_type, source_name, capability,
                        status, value_summary_json, raw_artifact_ref, provenance_json, created_at)
                       VALUES (:evidence_id, :case_id, :source_type, :source_name, :capability,
                               :status, :value_summary_json, :raw_artifact_ref, :provenance_json, :created_at)
                       ON CONFLICT (evidence_id) DO UPDATE SET
                           case_id = EXCLUDED.case_id,
                           source_type = EXCLUDED.source_type,
                           source_name = EXCLUDED.source_name,
                           capability = EXCLUDED.capability,
                           status = EXCLUDED.status,
                           value_summary_json = EXCLUDED.value_summary_json,
                           raw_artifact_ref = EXCLUDED.raw_artifact_ref,
                           provenance_json = EXCLUDED.provenance_json,
                           created_at = EXCLUDED.created_at"""
                ),
                {
                    "evidence_id": evidence.evidence_id,
                    "case_id": evidence.case_id,
                    "source_type": evidence.source_type.value,
                    "source_name": evidence.source_name,
                    "capability": evidence.capability,
                    "status": evidence.status,
                    "value_summary_json": json.dumps(evidence.value),
                    "raw_artifact_ref": json.dumps(evidence.provenance),
                    "provenance_json": json.dumps(evidence.provenance),
                    "created_at": evidence.created_at.isoformat(),
                },
            )

    def get_evidence_by_case(self, case_id: str) -> list[EvidenceItem]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM committee.committee_evidence WHERE case_id = :case_id "
                    "ORDER BY created_at"
                ),
                {"case_id": case_id},
            ).mappings().all()

        return [
            EvidenceItem(
                evidence_id=row["evidence_id"],
                case_id=row["case_id"],
                source_type=EvidenceSource(row["source_type"]),
                source_name=row["source_name"],
                capability=row["capability"],
                status=row["status"],
                value=_safe_json(row["value_summary_json"], {}),
                provenance=_safe_json(row["provenance_json"], {}),
                created_at=_to_datetime(row["created_at"]),
            )
            for row in rows
        ]

    # ── Verdicts ─────────────────────────────────────────────

    def save_verdict(self, verdict: CommitteeVerdict) -> None:
        self._require_dimension("committee_decision", verdict.decision.value)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO committee.committee_verdicts
                       (verdict_id, case_id, decision, scorecard_json,
                        blocking_reasons_json, warnings_json, required_actions_json, created_at)
                       VALUES (:verdict_id, :case_id, :decision, :scorecard_json,
                               :blocking_reasons_json, :warnings_json, :required_actions_json, :created_at)
                       ON CONFLICT (verdict_id) DO UPDATE SET
                           case_id = EXCLUDED.case_id,
                           decision = EXCLUDED.decision,
                           scorecard_json = EXCLUDED.scorecard_json,
                           blocking_reasons_json = EXCLUDED.blocking_reasons_json,
                           warnings_json = EXCLUDED.warnings_json,
                           required_actions_json = EXCLUDED.required_actions_json,
                           created_at = EXCLUDED.created_at"""
                ),
                {
                    "verdict_id": verdict.verdict_id,
                    "case_id": verdict.case_id,
                    "decision": verdict.decision.value,
                    "scorecard_json": json.dumps(verdict.scorecard),
                    "blocking_reasons_json": json.dumps(verdict.blocking_reasons),
                    "warnings_json": json.dumps(verdict.warnings),
                    "required_actions_json": json.dumps(verdict.required_actions),
                    "created_at": verdict.created_at.isoformat(),
                },
            )

    def get_verdict(self, verdict_id: str) -> CommitteeVerdict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM committee.committee_verdicts WHERE verdict_id = :verdict_id"),
                {"verdict_id": verdict_id},
            ).mappings().first()
        if row is None:
            return None
        return self._row_to_verdict(row)

    def get_verdict_by_case(self, case_id: str) -> CommitteeVerdict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM committee.committee_verdicts WHERE case_id = :case_id "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"case_id": case_id},
            ).mappings().first()
        if row is None:
            return None
        return self._row_to_verdict(row)

    # ── helpers ─────────────────────────────────────────────

    @staticmethod
    def _row_to_case(row) -> CommitteeCase:
        def _safe_enum(enum_cls, v, default):
            try:
                return enum_cls(v) if v else default
            except (ValueError, KeyError):
                return default

        return CommitteeCase(
            case_id=row["case_id"] or "",
            committee_type=_safe_enum(CommitteeType, row["committee_type"], CommitteeType.CANDIDATE_PRIORITY),
            project_id=row["project_id"],
            ecml_run_id=row["ecml_run_id"],
            candidate_id=row["candidate_id"],
            trigger_code=row["trigger_code"] or "",
            risk_level=_safe_enum(RiskLevel, row["risk_level"], RiskLevel.MEDIUM),
            status=_safe_enum(CaseStatus, row["status"], CaseStatus.PENDING),
            input_snapshot_hash=row["input_snapshot_hash"] or "",
            policy_version=row["policy_version"] or "committee-v1",
            created_by=row["created_by"] or "",
            created_at=_to_datetime(row["created_at"]),
            updated_at=_to_datetime(row["updated_at"]),
        )

    @staticmethod
    def _row_to_verdict(row) -> CommitteeVerdict:
        def _safe_json(value, default):
            if not value:
                return default
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return default
            return value

        return CommitteeVerdict(
            verdict_id=row["verdict_id"] or "",
            case_id=row["case_id"] or "",
            decision=Decision(row["decision"]) if row["decision"] in Decision._value2member_map_ else Decision.FAILED,
            scorecard=_safe_json(row["scorecard_json"], {}),
            blocking_reasons=_safe_json(row["blocking_reasons_json"], []),
            warnings=_safe_json(row["warnings_json"], []),
            required_actions=_safe_json(row["required_actions_json"], []),
            created_at=_to_datetime(row["created_at"]),
        )
