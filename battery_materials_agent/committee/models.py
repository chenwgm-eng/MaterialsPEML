from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .enums import CaseStatus, CommitteeType, Decision, EvidenceSource, RiskLevel


class CommitteeCase(BaseModel):
    case_id: str
    committee_type: CommitteeType
    project_id: str | None = None
    ecml_run_id: str | None = None
    candidate_id: str | None = None
    trigger_code: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    status: CaseStatus = CaseStatus.PENDING
    input_snapshot_hash: str = ""
    policy_version: str = "committee-v1"
    created_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Proposal(BaseModel):
    proposal_id: str
    case_id: str
    role: Literal["thinker"] = "thinker"
    content: dict = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    requested_evidence: list[str] = Field(default_factory=list)
    model_provenance: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvidenceItem(BaseModel):
    evidence_id: str
    case_id: str
    source_type: EvidenceSource
    source_name: str = ""
    capability: str = ""
    status: Literal["success", "failed", "unknown"] = "unknown"
    value: dict = Field(default_factory=dict)
    verification: str = "verified"  # verified | unverified（ClaimVerifier 就地标记，落库）
    confidence: float | None = None
    applicability: str | None = None
    provenance: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CommitteeVerdict(BaseModel):
    verdict_id: str
    case_id: str
    decision: Decision
    scorecard: dict = Field(default_factory=dict)
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    verifier_provenance: dict | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))