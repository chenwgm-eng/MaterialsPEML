"""从委员会 case 生成实验放行卡。

原则：有什么填什么，缺失的类别保持 None/空，绝不编造证据内容。
"""

from __future__ import annotations

import uuid
from pathlib import Path

from ..committee.enums import CaseStatus, EvidenceSource
from ..committee.models import CommitteeCase, CommitteeVerdict, EvidenceItem, Proposal
from ..committee.repository import CommitteeRepository
from .models import EVIDENCE_CATEGORIES, ReleaseCard
from .store import ReleaseCardStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 委员会终态 → 放行卡推荐结论
_RECOMMENDATION_MAP = {
    CaseStatus.PASS: "recommend",
    CaseStatus.REQUEST_EVIDENCE: "need_evidence",
    CaseStatus.HUMAN_REVIEW: "human_review",
    CaseStatus.REJECT: "reject",
    CaseStatus.FAILED: "human_review",
}

# 证据 capability → 放行卡六类证据的映射
_CAPABILITY_CATEGORY_MAP = {
    "prediction": {
        "structure_validity", "chemical_reasonability", "symmetry",
        "relaxation_stability", "target_match", "confidence", "stability",
        "dft_info_value",
    },
    "experiment_history": {"reproducibility", "deviation_magnitude", "methodology_review"},
    "literature": {
        "novelty", "cross_reference", "source_reliability",
        "temporal_validity", "domain_relevance",
    },
    "cost": {"cost"},
    "ehs": {"safety", "compliance"},
    "synthesis_feasibility": {"feasibility"},
}

# capability 未命中时按证据来源兜底
_SOURCE_CATEGORY_MAP = {
    EvidenceSource.MODEL: "prediction",
    EvidenceSource.EXPERIMENT: "experiment_history",
}


def _map_recommendation(status: CaseStatus) -> str:
    """委员会状态 → 推荐结论。非终态（进行中/已取消）保守转人工。"""
    return _RECOMMENDATION_MAP.get(status, "human_review")


def _categorize_evidence(item: EvidenceItem) -> str | None:
    """将一条证据归入六类之一；无法归类返回 None。"""
    capability = (item.capability or "").strip()
    for category, capabilities in _CAPABILITY_CATEGORY_MAP.items():
        if capability in capabilities:
            return category
    return _SOURCE_CATEGORY_MAP.get(item.source_type)


def _build_evidence_summary(evidence: list[EvidenceItem]) -> dict:
    """从委员会证据列表提取六类证据摘要，缺的类别保持 None。"""
    summary: dict = {k: None for k in EVIDENCE_CATEGORIES}
    for item in evidence:
        category = _categorize_evidence(item)
        if category is None:
            continue
        if summary[category] is None:
            summary[category] = {"count": 0, "items": []}
        summary[category]["count"] += 1
        summary[category]["items"].append(
            {
                "evidence_id": item.evidence_id,
                "source_name": item.source_name,
                "capability": item.capability,
                "status": item.status,
                "confidence": item.confidence,
                "value": item.value,
            }
        )
    return summary


def _build_uncertainty(
    evidence: list[EvidenceItem],
    verdict: CommitteeVerdict | None,
    proposal: Proposal | None,
) -> dict:
    """从已有数据提取不确定性，无来源的键保持 None。"""
    applicability = [e.applicability for e in evidence if e.applicability]
    return {
        "applicability_domain": applicability or None,
        "data_gaps": (verdict.blocking_reasons or None) if verdict else None,
        "key_assumptions": (proposal.assumptions or None) if proposal else None,
        "failure_modes": (verdict.warnings or None) if verdict else None,
    }


def generate_from_case(
    case: CommitteeCase,
    evidence: list[EvidenceItem] | None = None,
    verdict: CommitteeVerdict | None = None,
    proposal: Proposal | None = None,
) -> ReleaseCard:
    """纯函数：由委员会 case（及其证据/裁决/提案）生成放行卡，status=pending_review。"""
    evidence = evidence or []

    provenance = {
        "case_id": case.case_id,
        "run_id": case.ecml_run_id,
        "model_versions": proposal.model_provenance if proposal else {},
        "data_versions": (
            {"input_snapshot_hash": case.input_snapshot_hash}
            if case.input_snapshot_hash
            else {}
        ),
        "rule_versions": {"policy_version": case.policy_version},
        "audit_refs": {
            "evidence_ids": [e.evidence_id for e in evidence],
            "verdict_id": verdict.verdict_id if verdict else None,
        },
    }

    return ReleaseCard(
        card_id=f"rc-{uuid.uuid4().hex[:8]}",
        case_id=case.case_id,
        project_id=case.project_id,
        candidate_id=case.candidate_id,
        title=f"实验放行卡 - {case.case_id}",
        recommendation=_map_recommendation(case.status),
        target_window={},
        evidence_summary=_build_evidence_summary(evidence),
        uncertainty=_build_uncertainty(evidence, verdict, proposal),
        suggested_experiments=[],
        stop_conditions=[],
        provenance=provenance,
        status="pending_review",
    )


def generate_and_save(
    case_id: str,
    store: ReleaseCardStore | None = None,
    repository: CommitteeRepository | None = None,
) -> ReleaseCard | None:
    """从委员会 repository 加载 case 及证据/裁决，生成放行卡并保存。

    case 不存在时返回 None。
    """
    store = store or ReleaseCardStore()
    repository = repository or CommitteeRepository(
        db_path=str(PROJECT_ROOT / "data" / "committee.db")
    )

    case = repository.get_case(case_id)
    if case is None:
        return None

    evidence = repository.get_evidence_by_case(case_id)
    # verifier 以 f"verdict-{case_id}" 为键保存裁决；兼容直接以 case_id 为键的旧数据
    verdict = repository.get_verdict(f"verdict-{case_id}") or repository.get_verdict(case_id)

    card = generate_from_case(case, evidence=evidence, verdict=verdict)
    store.create(card)
    return card
