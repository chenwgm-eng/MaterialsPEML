"""合成规划器 Task 18 工艺标签与温度一致性校验测试。

覆盖：
1. _classify_process_by_temperature 温度阈值分类逻辑；
2. RouteStep 新增字段（process_label/label_conflict/process_label_note）经 model_dump 保留；
3. _plan_crystal_with_internlm 构造：低温步骤不会被标注为“高温固相法”，
   且与路线 method 冲突时 label_conflict/校准 note/provenance 正确写入。
全程无需真实 LLM（mock 流式响应）。
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch
from pydantic import SecretStr

from battery_materials_agent.config import AgentConfig, EngineMode, InternLMConfig
from battery_materials_agent.synthesis.synthesis_planner import (
    RouteStep,
    SynthesisPlanner,
)


class TestClassifyProcessByTemperature(unittest.TestCase):
    """温度 -> 工艺标签 分类逻辑测试。"""

    def setUp(self):
        self.planner = SynthesisPlanner()

    def test_high_temperature(self):
        self.assertEqual(self.planner._classify_process_by_temperature(600), "高温固相法")
        self.assertEqual(self.planner._classify_process_by_temperature(800), "高温固相法")
        self.assertEqual(self.planner._classify_process_by_temperature(1200), "高温固相法")

    def test_medium_temperature(self):
        self.assertEqual(self.planner._classify_process_by_temperature(300), "中温煅烧")
        self.assertEqual(self.planner._classify_process_by_temperature(450), "中温煅烧")
        self.assertEqual(self.planner._classify_process_by_temperature(599), "中温煅烧")

    def test_low_temperature(self):
        self.assertTrue(self.planner._classify_process_by_temperature(200).startswith("低温"))
        self.assertEqual(self.planner._classify_process_by_temperature(150), "低温/球磨法")

    def test_room_temperature(self):
        self.assertEqual(self.planner._classify_process_by_temperature(25), "室温球磨法")
        self.assertEqual(self.planner._classify_process_by_temperature(0), "室温球磨法")
        self.assertEqual(self.planner._classify_process_by_temperature(100), "室温球磨法")

    def test_none_and_invalid(self):
        # None/非法温度回退到 fallback
        self.assertEqual(self.planner._classify_process_by_temperature(None), "固相合成")
        self.assertEqual(
            self.planner._classify_process_by_temperature(None, fallback="高温固相法"),
            "高温固相法",
        )
        self.assertEqual(
            self.planner._classify_process_by_temperature(object(), fallback="固相合成"),
            "固相合成",
        )

    def test_string_temperature(self):
        self.assertEqual(self.planner._classify_process_by_temperature("800"), "高温固相法")
        self.assertEqual(self.planner._classify_process_by_temperature("25"), "室温球磨法")


class TestRouteStepNewFields(unittest.TestCase):
    """RouteStep 新增工艺标签字段向后兼容性测试。"""

    def test_defaults_backward_compatible(self):
        step = RouteStep()
        self.assertFalse(step.label_conflict)
        self.assertEqual(step.process_label, "")
        self.assertEqual(step.process_label_note, "")

    def test_fields_survive_model_dump(self):
        step = RouteStep(
            reaction_type="室温球磨法",
            process_label="室温球磨法",
            label_conflict=True,
            process_label_note="工艺标签与温度不符，已按温度自动校准：25°C 归为室温球磨法",
        )
        dumped = step.model_dump()
        self.assertIs(dumped["label_conflict"], True)
        self.assertEqual(dumped["process_label"], "室温球磨法")
        self.assertIn("已按温度自动校准", dumped["process_label_note"])


class TestPlanCrystalLabelCalibration(unittest.TestCase):
    """_plan_crystal_with_internlm 构造测试：低温步骤不被标注为“高温固相法”。"""

    def _run(self, raw_routes):
        config = AgentConfig(
            engine_mode=EngineMode.INTERNLM,
            internlm=InternLMConfig(
                api_key=SecretStr("test-key"),
                base_url="https://example.test/v1",
            ),
        )
        planner = SynthesisPlanner(config=config)
        payload = json.dumps({"routes": raw_routes, "reasoning": "测试推理"})
        with patch.object(
            planner, "_internlm_stream_chat", new_callable=unittest.mock.AsyncMock
        ) as mock_stream:
            mock_stream.return_value = payload
            routes, meta = asyncio.run(
                planner._plan_crystal_with_internlm("LiCoO2", "R-3m", num_routes=1)
            )
            return routes, meta

    def test_room_temp_step_not_high_temp_and_conflict_set(self):
        raw = [{
            "method": "高温固相法",
            "precursors": ["Li2CO3", "Co3O4"],
            "steps": [
                {"action": "球磨混合", "temperature": 25, "duration": 2, "atmosphere": "air"},
                {"action": "煅烧", "temperature": 800, "duration": 12, "atmosphere": "air"},
            ],
            "score": 0.85,
            "key_notes": "Li 挥发补偿",
        }]
        routes, meta = self._run(raw)
        self.assertEqual(len(routes), 1)
        route = routes[0]
        self.assertEqual(len(route.steps), 2)

        # 25°C 步骤：不得标注“高温固相法”，按温度归为室温工艺
        step0 = route.steps[0]
        self.assertNotEqual(step0.reaction_type, "高温固相法")
        self.assertEqual(step0.reaction_type, "室温球磨法")
        self.assertTrue(step0.label_conflict)
        self.assertIn("已按温度自动校准", step0.process_label_note)

        # 800°C 步骤：正常标注“高温固相法”，与路线 method 一致，无冲突
        step1 = route.steps[1]
        self.assertEqual(step1.reaction_type, "高温固相法")
        self.assertFalse(step1.label_conflict)
        self.assertEqual(step1.process_label_note, "")

        # provenance 记录校准说明
        calibration = [p for p in route.provenance if "calibration" in p]
        self.assertEqual(len(calibration), 1)
        self.assertTrue(any("25°C" in d for d in calibration[0]["details"]))

    def test_route_method_consistent_no_conflict(self):
        raw = [{
            "method": "高温固相法",
            "precursors": ["Li2CO3", "Co3O4"],
            "steps": [
                {"action": "煅烧", "temperature": 800, "duration": 12, "atmosphere": "air"}
            ],
            "score": 0.8,
        }]
        routes, _ = self._run(raw)
        step = routes[0].steps[0]
        self.assertEqual(step.reaction_type, "高温固相法")
        self.assertFalse(step.label_conflict)
        self.assertEqual(step.process_label_note, "")


if __name__ == "__main__":
    unittest.main()