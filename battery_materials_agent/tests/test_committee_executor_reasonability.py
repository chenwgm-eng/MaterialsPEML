"""化学合理性 / 候选数据传递回归测试。

覆盖场景（P0 修复回归）：
1. 空候选（无 formula）→ 化学合理性返回兜底分 _INSUFFICIENT_SCORE（0.4）而非 0 分，
   不再触发 "chemical_reasonability below threshold"。
2. 内联 candidate_data 优先于候选存储查找（方案 1：ECML 闭环真实候选）。
3. 候选存储查找作为回退仍可用。
4. CandidateRecord dataclass 类型候选可通过 _as_dict 归一化。
5. 评分卡 structure_validity 硬约束同时识别 valid / passed 键。
6. 评分卡对无结构证据（数据不足）不硬阻断，而是告警。
"""

from __future__ import annotations

import unittest

from battery_materials_agent.committee.executor import CommitteeExecutor, _INSUFFICIENT_SCORE
from battery_materials_agent.committee.models import EvidenceItem
from battery_materials_agent.committee.scorecards import CrystalConstructionScorecard
from battery_materials_agent.committee.enums import EvidenceSource


class _FakeRecord:
    """模拟 CandidateRecord dataclass。"""

    def __init__(self, formula=""):
        self.formula = formula
        self.chemical_formula = formula
        self.name = "fake"
        self.lattice = None
        self.species = []
        self.coords = []
        self.smiles = ""
        self.candidate_id = "cand-1"
        self.space_group = ""
        self.data = {}


class CommitteeExecutorReasonabilityTest(unittest.TestCase):
    def test_empty_candidate_returns_insufficient_score_not_zero(self):
        """空候选：化学合理性返回兜底分而非 0，避免 below threshold 阻断。"""
        ex = CommitteeExecutor()
        result = ex._chemical_reasonability({"formula": ""})
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(result["score"], _INSUFFICIENT_SCORE)
        self.assertGreaterEqual(result["score"], 0.3)  # 不会触发 below threshold
        self.assertEqual(result["blocking_reasons"], [])

    def test_inline_candidate_data_has_priority_over_lookup(self):
        """内联 candidate_data 优先于候选存储查找。"""
        lookup_used = {"called": False}

        def lookup(_cid):
            lookup_used["called"] = True
            return {"formula": "LiCoO2"}

        ex = CommitteeExecutor(candidate_lookup=lookup)
        task = {
            "tool_name": "chemical_reasonability_check",
            "args": {"candidate_id": "cand-1", "candidate_data": {"formula": "LiNiO2"}},
        }
        result = ex._dispatch(task)
        self.assertFalse(lookup_used["called"], "内联数据存在时不应回退到存储查找")
        self.assertEqual(result["score"], 0.75)

    def test_lookup_fallback_when_no_inline_data(self):
        """无内联数据时回退到候选存储查找。"""
        ex = CommitteeExecutor(candidate_lookup=lambda cid: {"formula": "LiFePO4"})
        task = {
            "tool_name": "chemical_reasonability_check",
            "args": {"candidate_id": "cand-1", "candidate_data": None},
        }
        result = ex._dispatch(task)
        self.assertEqual(result["score"], 0.75)

    def test_dataclass_candidate_normalized(self):
        """CandidateRecord dataclass 类型候选经 _as_dict 归一化为 dict。"""
        ex = CommitteeExecutor()
        d = ex._as_dict(_FakeRecord(formula="LiMn2O4"))
        self.assertEqual(d["formula"], "LiMn2O4")
        self.assertEqual(d["candidate_id"], "cand-1")

    def test_dataclass_candidate_merges_nested_data(self):
        """CandidateRecord 的嵌套 data（结构/属性字段）应展开到顶层供结构校验使用。"""
        record = _FakeRecord(formula="LiCoO2")
        record.data = {
            "formula": "LiCoO2",
            "lattice": [[2.8, 0, 0], [0, 2.8, 0], [0, 0, 2.8]],
            "space_group": "R-3m",
        }
        ex = CommitteeExecutor()
        d = ex._as_dict(record)
        self.assertEqual(d["lattice"], record.data["lattice"])
        self.assertEqual(d["space_group"], "R-3m")
        # 顶层属性优先于嵌套 data（顶层 formula 与 data.formula 一致）
        self.assertEqual(d["formula"], "LiCoO2")

    def test_nonempty_formula_returns_confident_score(self):
        """有化学式时返回稳定高分。"""
        ex = CommitteeExecutor()
        result = ex._chemical_reasonability({"formula": "LiCoO2"})
        self.assertEqual(result["score"], 0.75)


class CrystalConstructionScorecardTest(unittest.TestCase):
    def _evidence(self, capability, value, status="success"):
        return EvidenceItem(
            evidence_id=f"ev-{capability}",
            case_id="case-1",
            source_type=EvidenceSource.LOCAL_TOOL,
            capability=capability,
            status=status,
            value=value,
        )

    def test_structure_validity_recognizes_passed_key(self):
        """structure_validity 返回 passed=False 时应硬阻断（结构非法）。"""
        evidence = [
            self._evidence("structure_validity", {"passed": False, "score": 0.0}),
            self._evidence("chemical_reasonability", {"score": 0.75}),
            self._evidence("symmetry", {"score": 0.8}),
            self._evidence("relaxation_stability", {"score": 0.8}),
            self._evidence("novelty", {"score": 0.8}),
            self._evidence("target_match", {"score": 0.8}),
        ]
        result = CrystalConstructionScorecard().evaluate(evidence)
        self.assertFalse(result["passed"])
        self.assertIn("Structure validity check failed", result["blocking_reasons"])

    def test_structure_validity_recognizes_valid_key(self):
        """structure_validity 返回 valid=False 时同样硬阻断。"""
        evidence = [
            self._evidence("structure_validity", {"valid": False, "score": 0.0}),
            self._evidence("chemical_reasonability", {"score": 0.75}),
            self._evidence("symmetry", {"score": 0.8}),
            self._evidence("relaxation_stability", {"score": 0.8}),
            self._evidence("novelty", {"score": 0.8}),
            self._evidence("target_match", {"score": 0.8}),
        ]
        result = CrystalConstructionScorecard().evaluate(evidence)
        self.assertFalse(result["passed"])

    def test_no_structure_evidence_does_not_hard_block(self):
        """无结构有效性证据（数据不足）不硬阻断，仅告警。"""
        evidence = [
            self._evidence("chemical_reasonability", {"score": _INSUFFICIENT_SCORE}),
            self._evidence("symmetry", {"score": 0.8}),
            self._evidence("relaxation_stability", {"score": 0.8}),
            self._evidence("novelty", {"score": 0.8}),
            self._evidence("target_match", {"score": 0.8}),
        ]
        result = CrystalConstructionScorecard().evaluate(evidence)
        self.assertTrue(any("insufficient data" in w for w in result["warnings"]))
        self.assertNotIn("Structure validity check failed", result["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()