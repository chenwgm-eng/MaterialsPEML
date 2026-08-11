"""Tests for property prediction modules."""

import pytest
from battery_materials_agent.prediction.crystal_property_predictor import (
    CrystalPropertyPredictor, PredictionResult,
)
from battery_materials_agent.prediction.polymer_property_predictor import (
    PolymerPropertyPredictor, PolymerPredictionResult,
)


class TestCrystalPropertyPredictor:
    def setup_method(self):
        self.predictor = CrystalPropertyPredictor(model_type="cgcnn")

    def test_predict_band_gap(self):
        result = self.predictor.predict({"formula": "LiCoO2"}, "band_gap")
        assert isinstance(result, PredictionResult)
        assert result.property_name == "band_gap"
        assert result.formula == "LiCoO2"
        # v4.0: model 字段反映实际使用的模型（回退时为 heuristic_gnn）
        assert result.model in ("cgcnn", "heuristic_gnn", "m3gnet")

    def test_predict_formation_energy(self):
        result = self.predictor.predict({"formula": "LiFePO4"}, "formation_energy")
        assert result.property_name == "formation_energy"

    def test_predict_unsupported_property(self):
        with pytest.raises(ValueError):
            self.predictor.predict({"formula": "LiCoO2"}, "unsupported_property")

    def test_predict_batch(self):
        features_list = [{"formula": "LiCoO2"}, {"formula": "LiFePO4"}]
        results = self.predictor.predict_batch(features_list, "band_gap")
        assert len(results) == 2

    def test_rank_candidates(self):
        results = [
            PredictionResult(property_name="band_gap", value=3.0),
            PredictionResult(property_name="band_gap", value=1.0),
            PredictionResult(property_name="band_gap", value=2.0),
        ]
        ranked = self.predictor.rank_candidates(results, ascending=True)
        assert ranked[0].value == 1.0
        assert ranked[-1].value == 3.0

    def test_top_k(self):
        results = [
            PredictionResult(property_name="band_gap", value=3.0),
            PredictionResult(property_name="band_gap", value=1.0),
            PredictionResult(property_name="band_gap", value=2.0),
        ]
        top = self.predictor.top_k(results, k=2, ascending=True)
        assert len(top) == 2
        assert top[0].value == 1.0

    def test_mt_cgcnn_model(self):
        predictor = CrystalPropertyPredictor(model_type="mt_cgcnn")
        result = predictor.predict({"formula": "LiCoO2"}, "band_gap")
        # v4.0: 实际模型可能回退到 heuristic_gnn
        assert result.model in ("mt_cgcnn", "heuristic_gnn", "m3gnet")

    def test_m3gnet_model(self):
        predictor = CrystalPropertyPredictor(model_type="m3gnet")
        result = predictor.predict({"formula": "LiCoO2"}, "band_gap")
        # v4.0: m3gnet 不可用时回退到 heuristic_gnn
        assert result.model in ("m3gnet", "heuristic_gnn")

    def test_invalid_model_type(self):
        predictor = CrystalPropertyPredictor(model_type="invalid")
        with pytest.raises(ValueError):
            predictor.predict({"formula": "LiCoO2"}, "band_gap")


class TestPolymerPropertyPredictor:
    def setup_method(self):
        self.predictor = PolymerPropertyPredictor(model_type="polymernn")

    def test_predict_tensile_strength(self):
        result = self.predictor.predict({"psmiles": "Polymer([*]CC(C)[*])"}, "tensile_strength")
        assert isinstance(result, PolymerPredictionResult)
        assert result.property_name == "tensile_strength"
        assert result.unit == "MPa"
        # v4.1（ADR-0001）：启发式路径统一标注 descriptor_heuristic，confidence 有上限
        assert result.model in ("polymernn", "descriptor_heuristic", "mattersim")
        assert result.confidence <= 0.5

    def test_predict_glass_transition(self):
        result = self.predictor.predict({"psmiles": "Polymer([*]CCO[*])"}, "glass_transition_temp")
        assert result.property_name == "glass_transition_temp"

    def test_predict_unsupported(self):
        with pytest.raises(ValueError):
            self.predictor.predict({}, "unsupported_property")
        # v4.1：电池时代属性（离子电导率）已从高分子预测能力移除
        with pytest.raises(ValueError):
            self.predictor.predict({"psmiles": "Polymer([*]CCO[*])"}, "ionic_conductivity")

    def test_predict_batch(self):
        features_list = [{"psmiles": "p1"}, {"psmiles": "p2"}]
        results = self.predictor.predict_batch(features_list, "tensile_strength")
        assert len(results) == 2

    def test_top_k(self):
        results = [
            PolymerPredictionResult(property_name="tensile_strength", value=3.0),
            PolymerPredictionResult(property_name="tensile_strength", value=1.0),
        ]
        top = self.predictor.top_k(results, k=1)
        assert len(top) == 1

    def test_descriptor_model(self):
        predictor = PolymerPropertyPredictor(model_type="descriptor")
        result = predictor.predict({}, "tensile_strength")
        # v4.1（ADR-0001）：描述符路径统一为 descriptor_heuristic
        assert result.model in ("descriptor", "descriptor_heuristic")

    def test_mattersim_model(self):
        predictor = PolymerPropertyPredictor(model_type="mattersim")
        result = predictor.predict({}, "tensile_strength")
        # v4.1（ADR-0001）：mattersim 不可用时回退到 descriptor_heuristic
        assert result.model in ("mattersim", "descriptor_heuristic")

    def test_invalid_model(self):
        predictor = PolymerPropertyPredictor(model_type="invalid")
        with pytest.raises(ValueError):
            predictor.predict({}, "ionic_conductivity")
