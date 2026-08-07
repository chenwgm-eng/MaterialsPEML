"""声明核验器（ClaimVerifier）单元测试。

覆盖场景：
- 证据非 success → 不适用，不修改
- 证据无 run_id → 不适用，不修改
- run 记录不存在 → 未核验 + 降级 + 记录原因
- run 状态未完成 → 未核验
- 无 artifact 落库 → 未核验
- 全部满足 → 通过，不降级
- kernel 未注入 → 未核验
- CommitteeVerifier 接入核验器 + verdict 记录失败原因
"""

from __future__ import annotations

import unittest

from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.run import Run, RunStatus
from battery_materials_agent.committee.claim_verifier import (
    ClaimVerifier,
    UNVERIFIED_CONFIDENCE,
)
from battery_materials_agent.committee.models import (
    CommitteeCase,
    CommitteeVerdict,
    EvidenceItem,
    Proposal,
)
from battery_materials_agent.committee.enums import (
    CommitteeType,
    EvidenceSource,
    Decision,
)
from battery_materials_agent.committee.verifier import CommitteeVerifier


class _FakeKernel:
    """不依赖数据库的伪 kernel，用于单元测试。"""

    def __init__(self, runs=None, artifacts=None):
        self.runs = runs or {}
        self.artifacts = artifacts or {}

    def get_run(self, run_id: str):
        return self.runs.get(run_id)

    def get_artifacts(self, run_id: str):
        return self.artifacts.get(run_id, [])


def _make_run(run_id: str, status=RunStatus.SUCCEEDED) -> Run:
    return Run(
        run_id=run_id,
        task_id="task-1",
        project_id="proj-1",
        service_id="svc",
        command="x",
        status=status,
    )


def _make_artifact(run_id: str) -> Artifact:
    return Artifact(run_id=run_id, type=ArtifactType.RESULT_TABLE, name="result")


def _make_evidence(
    evidence_id: str,
    *,
    status: str = "success",
    run_id: str | None = None,
    provenance=None,
) -> EvidenceItem:
    prov = dict(provenance or {})
    if run_id:
        prov["run_id"] = run_id
    return EvidenceItem(
        evidence_id=evidence_id,
        case_id="case-1",
        source_type=EvidenceSource.SCP,
        capability="candidate_priority",
        status=status,
        value={"score": 0.8},
        confidence=0.8,
        provenance=prov,
    )


class TestClaimVerifier(unittest.TestCase):
    def test_non_success_evidence_not_applicable(self):
        """非 success 证据不适用核验，不降级、不标记。"""
        item = _make_evidence("ev-non", status="failed", run_id="run-1")
        verifier = ClaimVerifier(_FakeKernel())
        check = verifier.verify_item(item)
        self.assertFalse(check.applicable)
        self.assertTrue(check.verified)
        self.assertEqual(item.verification, "verified")
        self.assertEqual(item.confidence, 0.8)

    def test_missing_run_id_not_applicable(self):
        """无 run_id 的证据不适用核验，原样保留。"""
        item = _make_evidence("ev-norun")
        verifier = ClaimVerifier(_FakeKernel())
        check = verifier.verify_item(item)
        self.assertFalse(check.applicable)
        self.assertEqual(item.verification, "verified")
        self.assertEqual(item.confidence, 0.8)

    def test_run_not_found_unverified(self):
        """run 记录不存在 → 未核验 + 降级 + 原因记录。"""
        item = _make_evidence("ev-missing", run_id="run-nope")
        verifier = ClaimVerifier(_FakeKernel())
        check = verifier.verify_item(item)
        self.assertTrue(check.applicable)
        self.assertFalse(check.verified)
        self.assertIn("run_not_found", check.reason)

        verifier.apply([item])
        self.assertEqual(item.verification, "unverified")
        self.assertEqual(item.confidence, UNVERIFIED_CONFIDENCE)
        self.assertFalse(item.provenance["claim_verifier"]["verified"])

    def test_run_not_completed_unverified(self):
        """run 状态未完成 → 未核验。"""
        item = _make_evidence("ev-pending", run_id="run-pending")
        kernel = _FakeKernel(runs={"run-pending": _make_run("run-pending", RunStatus.RUNNING)})
        verifier = ClaimVerifier(kernel)
        check = verifier.verify_item(item)
        self.assertFalse(check.verified)
        self.assertIn("run_not_completed:running", check.reason)

    def test_artifact_missing_unverified(self):
        """无 artifact 落库 → 未核验。"""
        item = _make_evidence("ev-noartifact", run_id="run-ok")
        kernel = _FakeKernel(runs={"run-ok": _make_run("run-ok")})  # 无 artifacts
        verifier = ClaimVerifier(kernel)
        check = verifier.verify_item(item)
        self.assertFalse(check.verified)
        self.assertEqual(check.reason, "artifact_missing")

    def test_full_verification_passes(self):
        """run 存在 + 完成 + artifact 落库 → 通过，不降级。"""
        item = _make_evidence("ev-ok", run_id="run-ok")
        kernel = _FakeKernel(
            runs={"run-ok": _make_run("run-ok")},
            artifacts={"run-ok": [_make_artifact("run-ok")]},
        )
        verifier = ClaimVerifier(kernel)
        check = verifier.verify_item(item)
        self.assertTrue(check.verified)
        self.assertEqual(item.verification, "verified")
        self.assertEqual(item.confidence, 0.8)

    def test_no_kernel_unverified(self):
        """kernel 未注入且证据携带 run_id → 未核验。"""
        item = _make_evidence("ev-nokernel", run_id="run-1")
        verifier = ClaimVerifier(kernel=None)
        check = verifier.verify_item(item)
        self.assertFalse(check.verified)
        self.assertEqual(check.reason, "no_verifier_kernel")

    def test_run_id_from_task_nested(self):
        """从 provenance.task 内嵌 run_id 提取。"""
        item = _make_evidence("ev-task", provenance={"task": {"run_id": "run-task"}})
        kernel = _FakeKernel(
            runs={"run-task": _make_run("run-task")},
            artifacts={"run-task": [_make_artifact("run-task")]},
        )
        verifier = ClaimVerifier(kernel)
        self.assertEqual(verifier.extract_run_id(item), "run-task")
        self.assertTrue(verifier.verify_item(item).verified)

    def test_apply_mixed(self):
        """混合证据：通过者保留、失败者降级、不适用者不变。"""
        good = _make_evidence("ev-good", run_id="run-good")
        bad = _make_evidence("ev-bad", run_id="run-bad")
        local = _make_evidence("ev-local")  # 无 run_id
        kernel = _FakeKernel(
            runs={"run-good": _make_run("run-good")},
            artifacts={"run-good": [_make_artifact("run-good")]},
        )
        verifier = ClaimVerifier(kernel)
        checks = verifier.apply([good, bad, local])

        self.assertTrue(checks[0].verified)
        self.assertFalse(checks[1].verified)
        self.assertFalse(checks[2].applicable)

        self.assertEqual(good.verification, "verified")
        self.assertEqual(bad.verification, "unverified")
        self.assertEqual(bad.confidence, UNVERIFIED_CONFIDENCE)
        self.assertEqual(local.verification, "verified")


class TestVerifierIntegration(unittest.TestCase):
    def _case(self) -> CommitteeCase:
        return CommitteeCase(
            case_id="case-ok",
            committee_type=CommitteeType.CANDIDATE_PRIORITY,
        )

    def _proposal(self) -> Proposal:
        return Proposal(
            proposal_id="p-1",
            case_id="case-ok",
            requested_evidence=["target_match", "confidence", "stability", "dft_info_value", "cost"],
        )

    def _candidate_evidence(self, run_id: str | None = None) -> list[EvidenceItem]:
        caps = ["target_match", "confidence", "stability", "dft_info_value", "cost"]
        items = []
        for i, cap in enumerate(caps):
            prov = {}
            if run_id:
                prov["run_id"] = run_id
            items.append(
                EvidenceItem(
                    evidence_id=f"ev-{i}",
                    case_id="case-ok",
                    source_type=EvidenceSource.SCP,
                    capability=cap,
                    status="success",
                    value={"score": 0.8},
                    confidence=0.8,
                    provenance=prov,
                )
            )
        return items

    def test_unverified_evidence_recorded_in_verdict(self):
        """核验失败原因应在 verdict.verifier_provenance 与 warnings 中记录。"""
        case = self._case()
        proposal = self._proposal()
        evidence = self._candidate_evidence(run_id="run-missing")  # run 不存在
        kernel = _FakeKernel()  # 无 run 记录
        verifier = CommitteeVerifier(claim_verifier=ClaimVerifier(kernel))

        verdict = verifier.evaluate(case, proposal, evidence)

        self.assertIsInstance(verdict, CommitteeVerdict)
        self.assertEqual(verdict.decision, Decision.PASS)  # 分数仍通过
        self.assertTrue(verdict.verifier_provenance["claim_verification"]["failures"])
        self.assertEqual(verdict.verifier_provenance["claim_verification"]["count"], 5)
        self.assertTrue(any("claim_unverified" in w for w in verdict.warnings))
        # 所有证据均被降级
        self.assertTrue(all(e.verification == "unverified" for e in evidence))
        self.assertTrue(all(e.confidence == UNVERIFIED_CONFIDENCE for e in evidence))

    def test_verified_evidence_no_failures(self):
        """全部核验通过时 verdict 无失败记录。"""
        case = self._case()
        proposal = self._proposal()
        evidence = self._candidate_evidence(run_id="run-good")
        kernel = _FakeKernel(
            runs={"run-good": _make_run("run-good")},
            artifacts={"run-good": [_make_artifact("run-good")]},
        )
        verifier = CommitteeVerifier(claim_verifier=ClaimVerifier(kernel))

        verdict = verifier.evaluate(case, proposal, evidence)

        self.assertEqual(verdict.verifier_provenance["claim_verification"]["count"], 0)
        self.assertTrue(all(e.verification == "verified" for e in evidence))
        self.assertTrue(all(e.confidence == 0.8 for e in evidence))

    def test_local_evidence_not_downgraded(self):
        """无 run_id 的本地工具证据不被降级。"""
        case = self._case()
        proposal = self._proposal()
        evidence = self._candidate_evidence()  # 无 run_id
        verifier = CommitteeVerifier(claim_verifier=ClaimVerifier(_FakeKernel()))

        verdict = verifier.evaluate(case, proposal, evidence)

        self.assertEqual(verdict.verifier_provenance["claim_verification"]["count"], 0)
        self.assertTrue(all(e.verification == "verified" for e in evidence))
        self.assertTrue(all(e.confidence == 0.8 for e in evidence))

    def test_without_claim_verifier_unchanged(self):
        """未注入核验器时行为与之前一致（无 claim_verification）。"""
        case = self._case()
        proposal = self._proposal()
        evidence = self._candidate_evidence(run_id="run-missing")
        verifier = CommitteeVerifier()  # 无核验器

        verdict = verifier.evaluate(case, proposal, evidence)

        self.assertNotIn("claim_verification", verdict.verifier_provenance)
        self.assertTrue(all(e.verification == "verified" for e in evidence))
        self.assertTrue(all(e.confidence == 0.8 for e in evidence))


if __name__ == "__main__":
    unittest.main()