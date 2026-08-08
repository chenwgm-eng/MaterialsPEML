"""PolymerGNN（Tg + 介电常数 试点）适配器与 predictor 集成测试。

- 依赖 torch / torch_geometric 且权重已落盘时，验证真实权重推理路径。
- 依赖缺失 / 权重缺失时，验证优雅降级（返回 None / 回退，不抛异常阻断）。
"""
import sys
import pytest


def _adapter():
    sys.path.insert(0, ".")
    from battery_materials_agent.prediction import polymer_gnn_adapter as m
    return m


class TestPolymerGnnAdapter:
    def test_is_available_returns_bool(self):
        m = _adapter()
        assert isinstance(m.is_available(), bool)

    def test_load_model_never_raises(self):
        """模型缺失 / 依赖缺失 / 加载失败都必须返回 None 或对象，绝不抛出。"""
        m = _adapter()
        model = m.load_model()
        assert model is None or hasattr(model, "eval")

    def test_predict_never_raises(self):
        """任何输入都不应抛异常；不可用时返回 None。"""
        m = _adapter()
        result = m.predict("CC(C([*])=O)O[*]", "glass_transition_temp")
        assert result is None or (len(result) == 3 and isinstance(result[0], float))

    def test_predict_unsupported_property(self):
        m = _adapter()
        assert m.predict("CC(C([*])=O)O[*]", "ionic_conductivity") is None

    def test_predict_invalid_psmiles(self):
        m = _adapter()
        assert m.predict("", "glass_transition_temp") is None
        assert m.predict(None, "glass_transition_temp") is None

    @pytest.mark.skipif(
        not (_adapter().is_available() and _adapter().load_model() is not None),
        reason="torch/torch_geometric 或 polymer_gnn 权重不可用",
    )
    def test_real_weight_inference_tg_and_dielectric(self):
        """权重可用时，Tg 与介电常数都应返回有效数值且标注 polymer_gnn。"""
        m = _adapter()
        tg = m.predict("CC(C([*])=O)O[*]", "glass_transition_temp")
        dielec = m.predict("CC(C([*])=O)O[*]", "dielectric_constant")
        for res in (tg, dielec):
            assert res is not None
            value, confidence, label = res
            assert isinstance(value, float)
            assert 0.0 <= confidence <= 1.0
            assert label == "polymer_gnn"


@pytest.mark.skipif(
    not (_adapter().is_available() and _adapter().load_model() is not None),
    reason="torch/torch_geometric 或 polymer_gnn 权重不可用",
)
class TestPolymerGnnPredictorPriority:
    """通过 PolymerPropertyPredictor 验证 polymernn 路径优先走 PolymerGNN 真实权重。"""

    def setup_method(self):
        from battery_materials_agent.prediction.polymer_property_predictor import PolymerPropertyPredictor
        self.predictor = PolymerPropertyPredictor(model_type="polymernn")

    def test_tg_uses_polymer_gnn(self):
        result = self.predictor.predict({"psmiles": "CC(C([*])=O)O[*]"}, "glass_transition_temp")
        assert result.model == "polymer_gnn"
        assert result.data_quality == "simulated"
        assert result.provenance and result.provenance[0]["model"] == "polymer_gnn"

    def test_dielectric_uses_polymer_gnn(self):
        result = self.predictor.predict({"psmiles": "CC(C([*])=O)O[*]"}, "dielectric_constant")
        assert result.model == "polymer_gnn"
        assert result.data_quality == "simulated"