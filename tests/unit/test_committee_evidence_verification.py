"""委员会证据核验结果持久化测试。

覆盖 P1 修复：ClaimVerifier 就地标记的 verification（verified / unverified）
与降级后的 confidence 需经 CommitteeRepository.save_evidence 落库，并能被
get_evidence_by_case 还原，保证 CoE Audit 的声明核验维度可正确读取。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from battery_materials_agent.committee.enums import CommitteeType, EvidenceSource, TriggerCode
from battery_materials_agent.committee.models import CommitteeCase, EvidenceItem
from battery_materials_agent.committee.repository import CommitteeRepository


@pytest.fixture
def repo(tmp_path):
    r = CommitteeRepository(db_path=str(tmp_path / "committee.db"))
    _cleanup_committee_tables(r.engine)
    return r


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    from battery_materials_agent.db import get_engine
    _cleanup_committee_tables(get_engine())


def _cleanup_committee_tables(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM release_card.release_cards"))
        conn.execute(text("DELETE FROM committee.committee_verdicts"))
        conn.execute(text("DELETE FROM committee.committee_evidence"))
        conn.execute(text("DELETE FROM committee.committee_proposals"))
        conn.execute(text("DELETE FROM committee.committee_events"))
        conn.execute(text("DELETE FROM committee.committee_cases"))


def _make_case(case_id: str) -> CommitteeCase:
    return CommitteeCase(
        case_id=case_id,
        committee_type=CommitteeType.CANDIDATE_PRIORITY,
        trigger_code=TriggerCode.CANDIDATE_QUALITY_INVALID.value,
    )


def _make_evidence(evidence_id: str, case_id: str, *, verification: str = "verified", confidence: float | None = None) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        case_id=case_id,
        source_type=EvidenceSource.SCP,
        source_name="scp",
        capability="target_match",
        status="success",
        value={"score": 0.8},
        verification=verification,
        confidence=confidence,
        provenance={"run_id": "run-1"},
    )


def test_save_and_load_verification_roundtrip(repo):
    """验证 verification/confidence 落库并可还原。"""
    case = _make_case("case-v")
    repo.create_case(case)

    ev = _make_evidence("ev-1", "case-v", verification="unverified", confidence=0.3)
    repo.save_evidence(ev)

    loaded = repo.get_evidence_by_case("case-v")
    assert len(loaded) == 1
    assert loaded[0].verification == "unverified"
    assert loaded[0].confidence == 0.3


def test_save_verified_default_roundtrip(repo):
    """默认核验通过 + 高置信度的证据落库还原。"""
    case = _make_case("case-ok")
    repo.create_case(case)

    ev = _make_evidence("ev-2", "case-ok", verification="verified", confidence=0.95)
    repo.save_evidence(ev)

    loaded = repo.get_evidence_by_case("case-ok")
    assert loaded[0].verification == "verified"
    assert loaded[0].confidence == 0.95


def test_upsert_updates_verification(repo):
    """同 evidence_id 再次保存应更新 verification/confidence。"""
    case = _make_case("case-up")
    repo.create_case(case)

    repo.save_evidence(_make_evidence("ev-3", "case-up", verification="verified", confidence=0.9))
    repo.save_evidence(_make_evidence("ev-3", "case-up", verification="unverified", confidence=0.3))

    loaded = repo.get_evidence_by_case("case-up")
    assert len(loaded) == 1
    assert loaded[0].verification == "unverified"
    assert loaded[0].confidence == 0.3