"""Tests for ECML 7-step scheduling engine."""

import pytest
from battery_materials_agent.ecml.ecml_engine import ECMLEngine, ECMLState, ECMLStep


class TestECMLEngine:
    def setup_method(self):
        self.engine = ECMLEngine()

    def test_run_default(self):
        state = self.engine.run("test_target", max_iterations=1)
        assert state.is_complete is True
        assert state.iteration == 1
        assert state.material_branch == "crystal_branch"

    def test_run_multiple_iterations(self):
        state = self.engine.run("test", max_iterations=3)
        assert state.iteration == 3
        assert state.is_complete is True

    def test_step1_route(self):
        state = ECMLState()
        state = self.engine._step1_route(state, "LiCoO2")
        assert state.current_step == ECMLStep.STEP1_ROUTE
        assert state.material_branch == "crystal_branch"

    def test_step2_generate(self):
        state = ECMLState()
        state = self.engine._step2_generate(state)
        assert state.current_step == ECMLStep.STEP2_GENERATE
        assert len(state.candidates) > 0

    def test_step3_synthesis_check(self):
        state = ECMLState(candidates=[{"formula": "LiCoO2"}])
        state = self.engine._step3_synthesis_check(state)
        assert state.current_step == ECMLStep.STEP3_SYNTHESIS_CHECK
        assert len(state.synthesizable) > 0

    def test_step4_predict(self):
        state = ECMLState(synthesizable=[{"formula": "LiCoO2"}])
        state = self.engine._step4_predict(state)
        assert state.current_step == ECMLStep.STEP4_PREDICT
        assert len(state.predictions) > 0

    def test_step5_verify(self):
        state = ECMLState(predictions=[{"formula": "LiCoO2"}])
        state = self.engine._step5_verify(state)
        assert state.current_step == ECMLStep.STEP5_VERIFY
        assert len(state.verified) > 0

    def test_step6_experiment(self):
        state = ECMLState()
        state = self.engine._step6_experiment(state)
        assert state.current_step == ECMLStep.STEP6_EXPERIMENT

    def test_step7_feedback(self):
        state = ECMLState(iteration=1, max_iterations=1)
        state = self.engine._step7_feedback(state)
        assert state.current_step == ECMLStep.STEP7_FEEDBACK
        assert state.is_complete is True

    def test_get_summary(self):
        state = self.engine.run("test", max_iterations=1)
        summary = self.engine.get_summary(state)
        assert "iterations" in summary
        assert "branch" in summary
        assert "total_candidates" in summary

    def test_run_step(self):
        state = ECMLState()
        state = self.engine.run_step(state, ECMLStep.STEP1_ROUTE)
        assert state.current_step == ECMLStep.STEP1_ROUTE

    def test_history_tracking(self):
        state = self.engine.run("test", max_iterations=1)
        assert len(state.history) > 0

    def test_ecml_step_enum(self):
        # v4.0 6.2: 新增 STEP3_INDUSTRIALIZATION 工业化筛选硬门槛步骤，共 9 步
        steps = list(ECMLStep)
        assert len(steps) == 9
        assert ECMLStep.STEP3_INDUSTRIALIZATION in steps

    def test_ecml_state_defaults(self):
        state = ECMLState()
        assert state.current_step == ECMLStep.STEP1_ROUTE
        assert state.iteration == 0
        assert state.is_complete is False
        # v4.0: 默认 max_iterations 调整为 3（黄金场景单轮验证）
        assert state.max_iterations == 3
