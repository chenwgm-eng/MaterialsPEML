"""Step A 身份与兼容层 —— 专业画像（discipline）校验逻辑单元测试。

覆盖 P0 不变量：
- 非法枚举值被拒绝；
- primary_discipline 必须 ∈ disciplines；
- 去重去空、排序归一化；
- 空画像读写正常。
（DB CHECK 约束的集成验证见迁移 0057 及真实库 alembic 校验。）
"""

from __future__ import annotations

import pytest

from battery_materials_agent.auth.user_store import normalize_disciplines


class TestNormalizeDisciplines:
    def test_valid_single(self):
        assert normalize_disciplines(["material_research"], "material_research") == (
            ["material_research"], "material_research",
        )

    def test_valid_multiple_sorted_dedup(self):
        # 入参乱序 + 重复 → 去重后的排序结果
        assert normalize_disciplines(
            ["experiment_analysis", "material_research", "experiment_analysis"],
            "experiment_analysis",
        ) == (["experiment_analysis", "material_research"], "experiment_analysis")

    def test_empty_devices_normal(self):
        # 空画像（disciplines=[] 且 primary=''）读写正常
        assert normalize_disciplines([], "") == ([], "")

    def test_none_inputs_normal(self):
        assert normalize_disciplines(None, None) == ([], "")

    def test_invalid_value_rejected(self):
        # 前端自由字符串在 API 层 400（此处抛 ValueError）
        with pytest.raises(ValueError):
            normalize_disciplines(["not_a_discipline"], "")

    def test_primary_not_in_disciplines_rejected(self):
        # disciplines=['material_research'] 而 primary='experiment_analysis'
        with pytest.raises(ValueError):
            normalize_disciplines(["material_research"], "experiment_analysis")

    def test_primary_with_empty_disciplines_rejected(self):
        with pytest.raises(ValueError):
            normalize_disciplines([], "material_research")

    def test_mixed_valid_invalid_rejected(self):
        with pytest.raises(ValueError):
            normalize_disciplines(["material_research", "bogus"], "material_research")