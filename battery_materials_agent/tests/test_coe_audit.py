"""CoE Audit「证据链完整性」审计单元测试。

覆盖场景：
- CoeAuditScorer 对完整证据链打分高，对残缺证据链打分低
- CoeAuditScorer 聚合指标正确
- CoeAuditor.run 从仓库拉取数据并产出报告（含 per_case 核对）
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from battery_materials_agent.committee.enums import (
    CaseStatus,
    CommitteeType,
    Decision,
    EvidenceSource,
)
from battery_materials_agent.committee.models import (
    CommitteeCase,
    CommitteeVerdict,
    EvidenceItem,
)
from battery_materials_agent.evals.coe_audit import CoeAuditor
from battery_materials_agent.evals.scorers.coe_audit_scorers import CoeAuditScorer


class TestCoeAuditScorer(unittest.TestCase):
    def test_complete_chain_scores_high(self):
        """完整证据链（证据落库、success、方法、引用、层级、核验）应得高分。"""
        scorer = CoeAuditScorer()
        case = {
            "case_id": "c1",
            "evidence_count": 2,
            "success_count": 2,
            "method_aligned_count": 2,
            "citation_traceable_count": 2,
            "source_tier_valid_count": 2,
            "verified_count": 2,
        }
        s = scorer.score_case(case)
        self.assertTrue(s["evidence_recorded"])
        self.assertEqual(s["evidence_success_rate"], 1.0)
        self.assertEqual(s["method_alignment_rate"], 1.0)
        self.assertEqual(s["citation_traceability"], 1.0)
        self.assertEqual(s["source_tier_validity"], 1.0)
        self.assertEqual(s["claim_verification_rate"], 1.0)

    def test_incomplete_chain_scores_low(self):
        """残缺证据链（无证据、无方法、无引用）应得低分。"""
        scorer = CoeAuditScorer()
        case = {
            "case_id": "c2",
            "evidence_count": 1,
            "success_count": 0,
            "method_aligned_count": 0,
            "citation_traceable_count": 0,
            "source_tier_valid_count": 0,
            "verified_count": 0,
        }
        s = scorer.score_case(case)
        self.assertEqual(s["evidence_success_rate"], 0.0)
        self.assertEqual(s["method_alignment_rate"], 0.0)
        self.assertEqual(s["citation_traceability"], 0.0)
        self.assertEqual(s["source_tier_validity"], 0.0)
        self.assertEqual(s["claim_verification_rate"], 0.0)

    def test_aggregate_metrics(self):
        """聚合指标综合全部案件。"""
        scorer = CoeAuditScorer()
        cases = [
            {
                "case_id": "c1", "evidence_count": 2, "success_count": 2,
                "method_aligned_count": 2, "citation_traceable_count": 2,
                "source_tier_valid_count": 2, "verified_count": 2,
            },
            {
                "case_id": "c2", "evidence_count": 0, "success_count": 0,
                "method_aligned_count": 0, "citation_traceable_count": 0,
                "source_tier_valid_count": 0, "verified_count": 0,
            },
        ]
        m = scorer.score_all(cases)
        self.assertEqual(m["case_count"], 2)
        self.assertEqual(m["evidence_count"], 2)
        self.assertEqual(m["evidence_coverage"], 0.5)
        self.assertEqual(m["evidence_success_rate"], 1.0)
        self.assertGreater(m["integrity_score"], 0)
        self.assertLess(m["integrity_score"], 1)


class TestCoeAuditor(unittest.TestCase):
    def _make_case(self, case_id: str) -> CommitteeCase:
        return CommitteeCase(
            case_id=case_id,
            committee_type=CommitteeType.CANDIDATE_PRIORITY,
            status=CaseStatus.PASS,
            created_at=datetime.now(timezone.utc),
        )

    def _make_evidence(self, id_: str, case_id: str, **kw) -> EvidenceItem:
        defaults = dict(
            evidence_id=id_,
            case_id=case_id,
            source_type=EvidenceSource.LOCAL_TOOL,
            source_name="dft",
            capability="relaxation",
            status="success",
            value={},
            verification="verified",
            provenance={"run_id": f"run_{id_}"},
            created_at=datetime.now(timezone.utc),
        )
        defaults.update(kw)
        return EvidenceItem(**defaults)

    def test_run_produces_report(self):
        """CoeAuditor.run 从仓库拉取数据并写入报告。"""
        repo = MagicMock()
        repo.list_cases.return_value = [
            self._make_case("c1"),
            self._make_case("c2"),
        ]
        repo.get_evidence_by_case.side_effect = lambda cid: (
            [self._make_evidence("e1", cid), self._make_evidence("e2", cid)]
            if cid == "c1" else []
        )
        repo.get_verdict_by_case.return_value = CommitteeVerdict(
            verdict_id="v1", case_id="c1", decision=Decision.PASS,
        )
        repo.get_scientific_evidence_source_tiers.return_value = [
            "real_engine", "builtin_library", "llm_generated",
        ]

        with tempfile.TemporaryDirectory() as tmp:
            auditor = CoeAuditor(repository=repo, report_dir=tmp)
            report = auditor.run(limit=10)
            # 报告文件真实存在且可解析（在 tempfile 块内检查）
            path = Path(report["report_path"])
            self.assertTrue(path.exists())
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["audit_run_id"], report["audit_run_id"])
            # c1 有证据，c2 无证据
            by_case = {c["case_id"]: c for c in data["per_case"]}
            self.assertEqual(by_case["c1"]["evidence_count"], 2)
            self.assertEqual(by_case["c2"]["evidence_count"], 0)
            # 来源层级审计：scientific_kernel.evidence 三级信任体系
            self.assertEqual(data["source_tier"]["total"], 3)
            self.assertEqual(data["source_tier"]["valid"], 3)
            self.assertEqual(data["source_tier"]["validity"], 1.0)
            self.assertEqual(report["metrics"]["source_tier_validity"], 1.0)

        self.assertEqual(report["audit_type"], "coe_evidence_chain_integrity")
        self.assertEqual(report["metrics"]["case_count"], 2)
        self.assertEqual(report["metrics"]["evidence_count"], 2)
        self.assertTrue(report["report_path"].endswith(".json"))

    def test_run_repo_failure_returns_error_report(self):
        """仓库拉取失败时返回 error 报告（不抛异常）。"""
        repo = MagicMock()
        repo.list_cases.side_effect = RuntimeError("db down")
        with tempfile.TemporaryDirectory() as tmp:
            auditor = CoeAuditor(repository=repo, report_dir=tmp)
            report = auditor.run(limit=10)
        self.assertIn("error", report)
        self.assertIn("list_cases_failed", report["error"])

    def test_unverified_not_citation_traceable(self):
        """核验失败(unverified)的证据不计入引用可查。"""
        ev = self._make_evidence(
            "e-unverified", "c1",
            verification="unverified",
            provenance={"run_id": "run_x"},
        )
        audit = CoeAuditor._audit_evidence([ev])
        self.assertEqual(audit["citation_traceable_count"], 0)

    def test_verified_with_run_is_citation_traceable(self):
        """核验通过且带 run_id 的证据计入引用可查。"""
        ev = self._make_evidence(
            "e-ok", "c1",
            verification="verified",
            provenance={"run_id": "run_x"},
        )
        audit = CoeAuditor._audit_evidence([ev])
        self.assertEqual(audit["citation_traceable_count"], 1)

    def test_scientific_source_tier_invalid_values(self):
        """scientific_kernel.evidence 存在非法层级时 validity 降低。"""
        repo = MagicMock()
        repo.get_scientific_evidence_source_tiers.return_value = [
            "real_engine", "unknown_tier", "llm_generated",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            auditor = CoeAuditor(repository=repo, report_dir=tmp)
            st = auditor._audit_scientific_source_tiers()
        self.assertEqual(st["total"], 3)
        self.assertEqual(st["valid"], 2)
        self.assertAlmostEqual(st["validity"], 2 / 3)


if __name__ == "__main__":
    unittest.main()