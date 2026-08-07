"""BO 决策引擎 recommend() 回归测试。

覆盖历史 CRITICAL 崩溃：
1. 单目标路径 is_polymer 生成器引用未定义变量 `c`（NameError）。
2. 多目标判定对 dataclass 实例调用 len()（TypeError），导致 EHVI 不可用。
3. 空训练池回退不抛异常。
"""
import warnings

import pytest

from battery_materials_agent.ecml.bo import (
    BayesianOptimizer,
    ObjectiveMeta,
    PoolResult,
    TrainPoint,
)

# 聚合基线：可被化学式解析的离散候选
_CANDIDATES = [
    {"name": f"c{i}", "formula": f}
    for i, f in enumerate(
        ["Li6PS5Cl", "Li6PS5Br", "Li6PS5Se", "Li6PS4Cl2", "Li7P2S8Cl"]
    )
]
_BASE = ["Li6PS5Cl", "Li6PS5Br", "Li6PS5I", "Li6PS7Cl", "Li7P2S8"]


class _StubBO(BayesianOptimizer):
    """用内存池 stub 掉 build_pool，隔离数据库依赖。"""

    def __init__(self, empty=False):
        super().__init__(engine=object())
        self._empty = empty

    def build_pool(self, family, prop, include_cross_project=False, project_id=""):
        if self._empty:
            return PoolResult(
                points=[], family=family, property_name=prop,
                stats={"total": 0, "project": 0, "cross_project": 0},
            )
        # 不同属性用不同数据分布，验证各目标独立训练
        pts = [
            TrainPoint(
                identifier=_BASE[i % 5],
                value=float(i + 1 if prop == "conductivity" else 10 - i),
                family=family,
            )
            for i in range(10)
        ]
        return PoolResult(
            points=pts, family=family, property_name=prop,
            stats={"total": len(pts), "project": len(pts), "cross_project": 0},
        )


@pytest.mark.parametrize("acq", ["ei", "ucb", "pi"])
def test_single_objective_does_not_crash(acq):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rec = _StubBO().recommend("fam", "conductivity", _CANDIDATES, acquisition=acq, num_candidates=3)
    assert rec.model.get("family")  # 有代理模型
    assert len(rec.candidates) > 0


def test_multi_objective_ehvi_routes_and_independent_pools():
    objectives = [
        ObjectiveMeta(property="conductivity", direction="maximize"),
        ObjectiveMeta(property="stability", direction="minimize"),
    ]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rec = _StubBO().recommend(
            "fam", "conductivity", _CANDIDATES,
            acquisition="ehvi", objectives=objectives, num_candidates=3,
        )
    assert rec.acquisition["name"] == "ehvi"
    models = rec.model.get("models", [])
    assert len(models) == 2
    assert {m["property"] for m in models} == {"conductivity", "stability"}
    assert len(rec.candidates) > 0
    for m in models:
        assert isinstance(m["family"], str)  # family 是字符串而非模型对象
        assert m["n_samples"] > 0
    # 每个候选都有各目标的预测
    for c in rec.candidates:
        assert set(c["predicted_objectives"].keys()) == {"conductivity", "stability"}


def test_empty_pool_falls_back_gracefully():
    rec = _StubBO(empty=True).recommend("fam", "conductivity", _CANDIDATES, acquisition="ei", num_candidates=3)
    assert rec.candidates == []
    assert rec.model.get("family") == "none"