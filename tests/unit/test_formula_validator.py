"""P1-1 候选材料化学式合法性校验引擎 与 下一轮推荐质量门禁 的单元测试。"""

import asyncio

import pytest

from battery_materials_agent.ecml.ecml_engine import (
    ECMLEngine,
    ECMLState,
    ECMLStateStore,
)
from battery_materials_agent.generation.formula_validator import (
    assess_batch_quality,
    assess_candidate_quality,
    parse_formula,
    validate_formula,
    validate_smiles,
)


class TestParseFormula:
    def test_simple_formula(self):
        assert parse_formula("Li3PS4") == {"Li": 3.0, "P": 1.0, "S": 4.0}

    def test_decimal_coefficients(self):
        comp = parse_formula("LiNi0.8Mn0.1Co0.1O2")
        assert comp == {"Li": 1.0, "Ni": 0.8, "Mn": 0.1, "Co": 0.1, "O": 2.0}

    def test_parentheses(self):
        comp = parse_formula("Ca(OH)2")
        assert comp == {"Ca": 1.0, "O": 2.0, "H": 2.0}

    def test_unclosed_parenthesis(self):
        assert parse_formula("Ca(OH2") is None

    def test_unknown_element(self):
        assert parse_formula("Xx3O2") is None

    def test_orphan_number(self):
        assert parse_formula("3Li") is None

    def test_empty(self):
        assert parse_formula("") is None
        assert parse_formula("   ") is None


class TestValidateFormula:
    @pytest.mark.parametrize("formula", ["Li3PS4", "LiCoO2", "LiNi0.8Mn0.1Co0.1O2", "Ca(OH)2", "LLZTO"])
    def test_valid_formulas(self, formula):
        # LLZTO 含未知元素，单独断言
        ok, _ = validate_formula(formula)
        if formula == "LLZTO":
            assert not ok
        else:
            assert ok

    def test_single_element_rejected(self):
        """评审案例：单元素 Ac 不构成电池材料，必须拒绝。"""
        ok, reason = validate_formula("Ac")
        assert not ok
        assert "单一元素" in reason

    def test_bracket_mismatch_rejected(self):
        ok, reason = validate_formula("Ca(H8O5)2")
        assert ok  # 括号配对时合法
        ok2, _ = validate_formula("Ca(H8O5")
        assert not ok2

    def test_empty_rejected(self):
        ok, _ = validate_formula("")
        assert not ok


class TestValidateSmiles:
    @pytest.mark.parametrize("smiles", ["CCO", "c1ccccc1", "[*]CC1O[*]", "O=C(O)C"])
    def test_valid(self, smiles):
        ok, _ = validate_smiles(smiles)
        assert ok

    def test_bracket_mismatch(self):
        ok, reason = validate_smiles("CC(O")
        assert not ok
        assert "括号" in reason

    def test_illegal_chars(self):
        ok, _ = validate_smiles("CCO{}")
        assert not ok

    def test_empty(self):
        ok, _ = validate_smiles("")
        assert not ok


class TestAssessCandidateQuality:
    def test_valid_crystal_candidate(self):
        result = assess_candidate_quality({"formula": "Li3PS4"})
        assert result["flag"] == "valid"
        assert result["issues"] == []

    def test_single_element_flagged(self):
        result = assess_candidate_quality({"formula": "Ac"})
        assert result["flag"] == "invalid"
        assert any("单一元素" in i for i in result["issues"])

    def test_missing_identifier_flagged(self):
        result = assess_candidate_quality({"name": "foo"})
        assert result["flag"] == "invalid"

    def test_polymer_smiles_valid(self):
        result = assess_candidate_quality({"smiles": "[*]CC1O[*]"})
        assert result["flag"] == "valid"


class TestAssessBatchQuality:
    def test_all_zero_predictions_detected(self):
        candidates = [
            {"expected_performance": 0},
            {"expected_performance": 0.0},
        ]
        assert assess_batch_quality(candidates) == "all_zero_predictions"

    def test_normal_predictions(self):
        candidates = [
            {"expected_performance": 0.9},
            {"expected_performance": 0},
        ]
        assert assess_batch_quality(candidates) == "valid"

    def test_no_predictions_is_valid(self):
        assert assess_batch_quality([{"expected_performance": None}]) == "valid"


@pytest.fixture
def engine_with_store(tmp_path):
    store = ECMLStateStore(db_path=str(tmp_path / "ecml_states.db"))
    return ECMLEngine(state_store=store), store


class TestNextRoundQualityGate:
    def test_invalid_candidates_blocked(self, engine_with_store):
        """非法化学式候选（如单元素 Ac）必须被拦截，不进入推荐池。"""
        engine, store = engine_with_store
        state = ECMLState(
            run_id="r1",
            target="LiCoO2",
            target_property="ionic_conductivity",
            material_branch="crystal_branch",
            predictions=[
                {"formula": "Ac", "value": 0.9, "property_name": "ionic_conductivity"},
                {"formula": "Li3PS4", "value": 0.8, "property_name": "ionic_conductivity"},
            ],
        )
        store.save("r1", state.target, state.target_property, state)

        result = asyncio.run(engine.generate_next_round("r1"))
        names = [c["name"] for c in result["next_candidates"]]
        # Ac 变体被拦截，不出现在推荐池
        assert not any(n.startswith("Ac") for n in names)
        assert len(result["blocked_candidates"]) >= 1
        assert all(
            c["data_quality_flag"] == "valid" for c in result["next_candidates"]
        )

    def test_naming_convention_no_debug_traces(self, engine_with_store):
        """命名必须符合规范，禁止 variant_1_from_xxx 调试痕迹。"""
        engine, store = engine_with_store
        state = ECMLState(
            run_id="r2",
            target="LiCoO2",
            target_property="ionic_conductivity",
            material_branch="crystal_branch",
            predictions=[
                {"formula": "Li3PS4", "value": 0.8, "property_name": "ionic_conductivity"},
            ],
        )
        store.save("r2", state.target, state.target_property, state)

        result = asyncio.run(engine.generate_next_round("r2"))
        for c in result["next_candidates"]:
            assert not c["name"].startswith("variant_")
            assert not c["name"].startswith("exploration_")
            assert not c["name"].startswith("fallback_")
        # 利用型变体命名格式：{identifier}-变体A
        variant = next(c for c in result["next_candidates"] if c["strategy"] == "exploitation")
        assert variant["name"] == "Li3PS4-变体A"

    def test_all_zero_batch_warning(self, engine_with_store):
        """全部预测值为 0 时返回批量质量告警（模型推理失效信号）。"""
        engine, store = engine_with_store
        state = ECMLState(
            run_id="r3",
            target="LiCoO2",
            target_property="ionic_conductivity",
            material_branch="crystal_branch",
            predictions=[
                {"formula": "Li3PS4", "value": 0.0, "property_name": "ionic_conductivity"},
                {"formula": "Li7PS6", "value": 0.0, "property_name": "ionic_conductivity"},
            ],
        )
        store.save("r3", state.target, state.target_property, state)

        result = asyncio.run(engine.generate_next_round("r3"))
        assert result["batch_quality_warning"]
        assert "模型推理失效" in result["batch_quality_warning"]
