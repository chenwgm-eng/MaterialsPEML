"""候选存储 save/update 语义回归测试。

锁定修复：
  1. [CRITICAL] update_synthesis_feasibility 走专用 UPDATE 通道，能对已存在候选落库
     —— 修复 save() content-hash 去重短路导致合成可行性回写被静默丢弃的问题；
  2. [MAJOR] save(dedup=False) 为临时预测转正创建独立候选（同公式可并存），
     且返回实际落库对象，避免幽灵 ID；
  3. save(dedup=True) 默认仍按 content-hash 去重（回归守卫）。

约定：基于 unittest + 真实 PostgreSQL；每个测试用唯一 ID/公式，tearDown 清理。
"""

from __future__ import annotations

import unittest
import uuid

from sqlalchemy import text

from battery_materials_agent.db import get_engine
from battery_materials_agent.experiment.candidate_store import CandidateRecord, CandidateStore


class CandidateStorePersistenceTest(unittest.TestCase):
    def setUp(self):
        self.store = CandidateStore()
        self.engine = get_engine()
        self.ids: list[str] = []
        self._seq = 0

    def tearDown(self):
        if self.ids:
            with self.engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM experiment.candidates WHERE candidate_id = ANY(:ids)"),
                    {"ids": self.ids},
                )
        self.ids = []

    def _mk(self, formula: str, target_app: str) -> CandidateRecord:
        self._seq += 1
        candidate_id = f"TESTPERSIST_{uuid.uuid4().hex[:12]}_{self._seq}"
        self.ids.append(candidate_id)
        return CandidateRecord(
            candidate_id=candidate_id,
            candidate_type="crystal",
            name=formula,
            smiles="",
            source="test",
            data={"formula": formula, "target_application": target_app},
        )

    # ── CRITICAL：更新已存在候选的字段必须落库 ──
    def test_update_synthesis_feasibility_persists(self):
        saved = self.store.save(self._mk("FLiP", "app-synth-" + uuid.uuid4().hex[:8]))
        ok = self.store.update_synthesis_feasibility(
            saved.candidate_id, {"feasibility_score": 0.8, "route_id": "r1"}
        )
        self.assertTrue(ok)
        rec = self.store.get(saved.candidate_id)
        self.assertEqual(rec.synthesis_feasibility["feasibility_score"], 0.8)
        self.assertEqual(rec.data["synthesis_feasibility"]["feasibility_score"], 0.8)

    def test_update_synthesis_feasibility_unknown_id_returns_false(self):
        ok = self.store.update_synthesis_feasibility("NO_SUCH_ID", {"feasibility_score": 0.5})
        self.assertFalse(ok)

    # ── MAJOR：转正创建独立候选（dedup=False） ──
    def test_save_dedup_false_creates_independent_candidates(self):
        target_app = "app-indep-" + uuid.uuid4().hex[:8]
        s1 = self.store.save(self._mk("LiCoO2", target_app), dedup=False)
        s2 = self.store.save(self._mk("LiCoO2", target_app), dedup=False)
        self.assertNotEqual(s1.candidate_id, s2.candidate_id)
        self.assertIsNotNone(self.store.get(s1.candidate_id))
        self.assertIsNotNone(self.store.get(s2.candidate_id))

    # ── 回归守卫：默认 save 仍按 content-hash 去重 ──
    def test_save_dedup_true_returns_existing(self):
        target_app = "app-dedup-" + uuid.uuid4().hex[:8]
        s1 = self.store.save(self._mk("LiCoO2", target_app))
        s2 = self.store.save(self._mk("LiCoO2", target_app))
        self.assertEqual(s1.candidate_id, s2.candidate_id)

    # ── 转正幂等：按 origin_temp_id 反查已转正候选 ──
    def test_find_by_origin_temp_id(self):
        origin = "temp-" + uuid.uuid4().hex[:8]
        rec = self._mk("FLiP", "app-idem-" + uuid.uuid4().hex[:8])
        rec.data = {
            **rec.data,
            "provenance": [{"step": "promote_from_temporary", "origin_temp_id": origin}],
        }
        self.store.save(rec, dedup=False)
        found = self.store.find_by_origin_temp_id(origin)
        self.assertIsNotNone(found)
        self.assertEqual(found.candidate_id, rec.candidate_id)

    def test_find_by_origin_temp_id_unknown_returns_none(self):
        found = self.store.find_by_origin_temp_id("no-such-" + uuid.uuid4().hex[:8])
        self.assertIsNone(found)

    # ── MINOR#7：冲突 upsert 不得回卷已推进的候选状态 ──
    def test_upsert_conflict_preserves_workflow_status(self):
        """重复 save 同一 candidate_id（默认 screening 状态）不得把
        已推进到 feasible 的候选状态回卷——状态只能经 update_status 状态机迁移。"""
        from battery_materials_agent.experiment.candidate_store import CandidateStatus
        target_app = "app-status-" + uuid.uuid4().hex[:8]
        s1 = self.store.save(self._mk("LiFePO4", target_app), dedup=False)
        self.assertTrue(self.store.update_status(
            s1.candidate_id, CandidateStatus.FEASIBLE.value, actor_operation_roles=None,
        ))
        # 以全新默认对象重放同一 candidate_id（模拟重复生成/回写路径）
        replay = CandidateRecord(
            candidate_id=s1.candidate_id,
            candidate_type="crystal",
            name="LiFePO4",
            smiles="",
            source="test",
            data={"formula": "LiFePO4", "target_application": target_app},
        )
        self.store.save(replay, dedup=False)
        rec_after = self.store.get(s1.candidate_id)
        self.assertEqual(rec_after.status, CandidateStatus.FEASIBLE.value)

    def test_find_by_origin_temp_id_empty_returns_none(self):
        self.assertIsNone(self.store.find_by_origin_temp_id(""))


if __name__ == "__main__":
    unittest.main()