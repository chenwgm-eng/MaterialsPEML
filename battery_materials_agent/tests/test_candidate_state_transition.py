"""候选材料状态机 —— 合成成功后自动流转 screening→feasible 的回归测试。

锁定修复（api._promote_candidate_to_feasible）的语义：
  1. 系统自动流转应传 actor_role=None，跳过人工角色校验，使 screening→feasible 成功；
  2. 若误传不匹配角色（如 synthesis_planner），将被状态机拒绝 —— 证明 actor_role=None
     是 `_promote_candidate_to_feasible` 得以生效的必要修复；
  3. 非法迁移（feasible→screening）仍被拒绝，确保状态机约束未被修复破坏。

约定：
  - 基于 unittest + 真实 PostgreSQL（与 test_e2e_integration 一致）。
  - 每个测试在 setUp 插入唯一 ID 候选，tearDown 删除，不污染业务库。
"""

from __future__ import annotations

import unittest
import uuid

from sqlalchemy import text

from battery_materials_agent.db import get_engine
from battery_materials_agent.experiment.candidate_store import (
    CandidateRecord,
    CandidateStatus,
    CandidateStore,
    IllegalCandidateTransitionError,
)


class CandidateAutoPromotionTest(unittest.TestCase):
    def setUp(self):
        self.store = CandidateStore()
        self.engine = get_engine()
        self.candidate_id = f"TEST_CAND_{uuid.uuid4().hex[:12]}"
        self.store.save(CandidateRecord(
            candidate_id=self.candidate_id,
            candidate_type="crystal",
            name="LiCoO2",
            smiles="",
            source="test",
            # target_application 唯一，使 content_hash 不撞业务库已有候选，保证 save 真正插入
            data={"formula": "LiCoO2", "target_application": f"test-app-{self.candidate_id}"},
            status=CandidateStatus.SCREENING.value,
        ))

    def tearDown(self):
        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM experiment.candidates WHERE candidate_id = :id"),
                {"id": self.candidate_id},
            )

    def test_system_promotion_with_no_role_succeeds(self):
        """系统自动流转（actor_operation_roles=None）应使 screening→feasible 成功。"""
        self.store.update_status(
            self.candidate_id,
            CandidateStatus.FEASIBLE.value,
            actor_operation_roles=None,
            triggered_by="synthesis_success",
            reason="test synthesis success",
        )
        record = self.store.get(self.candidate_id)
        self.assertEqual(record.status, CandidateStatus.FEASIBLE.value)

    def test_mismatched_role_is_rejected(self):
        """可用操作角色不含目标状态主导角色时应被拒绝 —— 证明 None 是跳过校验的必要信号。"""
        with self.assertRaises(IllegalCandidateTransitionError):
            self.store.update_status(
                self.candidate_id,
                CandidateStatus.FEASIBLE.value,
                actor_operation_roles={"synthesis_planner"},
                triggered_by="synthesis_success",
            )

    def test_illegal_transition_still_rejected(self):
        """非法迁移（feasible→screening）仍被拒绝，状态机约束未被破坏。"""
        self.store.update_status(
            self.candidate_id,
            CandidateStatus.FEASIBLE.value,
            actor_operation_roles=None,
        )
        with self.assertRaises(IllegalCandidateTransitionError):
            self.store.update_status(
                self.candidate_id,
                CandidateStatus.SCREENING.value,
                actor_operation_roles=None,
            )


if __name__ == "__main__":
    unittest.main()