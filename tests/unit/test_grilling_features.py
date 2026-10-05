"""grilling 会话新增能力的单元测试（v4.1 专业度/审计/易用性）。

覆盖：
- 材料体系/属性推断（/parse-goal 的后端逻辑 _infer_goal_system）
- 工程塑料查表法（reference_properties：来源标注、无派生系数、词边界匹配）
- ECML 闭环验证精度（_compute_validation_metrics：按 formula 对齐、MAPE/命中率）
- 放行卡状态迁移图（非法迁移拒绝）
- demo 模拟测量值围绕估算值（±10% 噪声）
- 描述符启发式术语分层（descriptor_heuristic + confidence 上限）
"""

import asyncio
import json
import sys

import pytest

sys.path.insert(0, r"D:\BattleFish\BatteryEMCL Lab")

from battery_materials_agent.api import _infer_goal_system, _GOAL_SYSTEM_KEYWORDS
from battery_materials_agent.ecml.ecml_engine import ECMLEngine, ECMLState
from battery_materials_agent.experiment.experiment_controller import (
    ExperimentController, ExperimentType,
)
from battery_materials_agent.generation.polymer_candidate_generator import (
    PolymerDesignRules,
)
from battery_materials_agent.hybrid.intent_interpreter import IntentInterpreter
from battery_materials_agent.release_card.store import RELEASE_CARD_TRANSITIONS
from battery_materials_agent.prediction.polymer_property_predictor import (
    PolymerPropertyPredictor,
)


# ── 1. 材料体系推断（智能目标框） ─────────────────────────────

class TestGoalSystemInference:
    def test_chinese_system(self):
        assert _infer_goal_system("开发高冲击强度的玻纤增强 PA6 改性料") == "PA6"

    def test_english_abbr_word_boundary(self):
        # 词边界：PC 不被 spc/process 误命中
        assert _infer_goal_system("设计阻燃等级 V-0 的 PC") == "PC"
        assert _infer_goal_system("开发 ABS 增韧配方") == "ABS"

    def test_modifier_keyword(self):
        assert _infer_goal_system("阻燃改性料开发") == "阻燃改性"

    def test_no_match(self):
        assert _infer_goal_system("任意研发任务描述") == ""

    def test_pa6_not_polypropylene(self):
        # "pa6" 不得命中 PP 分支
        assert _infer_goal_system("PA6 玻纤增强") == "PA6"

    def test_keyword_table_nonempty(self):
        assert len(_GOAL_SYSTEM_KEYWORDS) > 10


# ── 2. 意图解析（高分子属性映射） ─────────────────────────────

class TestIntentParsePolymer:
    async def _interpret(self, goal):
        interp = IntentInterpreter()
        return await interp.interpret(goal)

    def test_parse_tensile_constraint(self):
        intent = asyncio.run(self._interpret("拉伸强度 ≥ 100 MPa 的 PA6"))
        props = intent["target_properties"]
        assert any(p["property"] == "tensile_strength" for p in props)

    def test_polymer_scope(self):
        intent = asyncio.run(self._interpret("开发冲击强度 ≥ 8 kJ/m² 的玻纤增强 PA6"))
        assert intent["material_scope"].material_type == "polymer"

    def test_no_lithium_false_positive(self):
        # "stability" 含 "li" 子串，不得推断 require_elements=["Li"]
        intent = asyncio.run(self._interpret("开发热稳定性好的 PC 材料"))
        assert "Li" not in (intent["require_elements"] or [])


# ── 3. 工程塑料查表法（无派生系数 + 来源标注） ─────────────────

class TestReferenceProperties:
    def setup_method(self):
        self.rules = PolymerDesignRules()

    def test_pa6_gf_values_and_source(self):
        t, f, i, h, src = self.rules.reference_properties("PA6", "GF30")
        assert t == 160  # 60 + 100（PA 族 GF 加成）
        assert src.startswith("CAMPUS")
        assert "玻纤" in src or "GF" in src

    def test_pp_base_no_filler(self):
        t, f, i, h, src = self.rules.reference_properties("PP", "FR-APP")
        assert t == 32  # 阻燃剂无增强加成 → 基材值
        assert src.startswith("CAMPUS")

    def test_no_derived_coefficients(self):
        # flexural 必须来自查表（非 tensile×28），验证 PA6 弯曲模量与拉伸强度比例
        t_pa, f_pa, *_ = self.rules.reference_properties("PA6", "")
        t_pc, f_pc, *_ = self.rules.reference_properties("PC", "")
        assert abs(f_pa / t_pa - 33.3) < 5  # 2000/60≈33（不可能是单一乘数 28）
        assert abs(f_pc / t_pc - 33.8) < 5  # 2200/65≈34

    def test_unknown_abbr_fallback(self):
        t, f, i, h, src = self.rules.reference_properties("XYZ", "")
        assert t == 50  # 通用兜底
        assert "通用" in src


# ── 4. 放行卡状态迁移图 ────────────────────────────────────────

class TestReleaseCardTransitions:
    def test_valid_transitions(self):
        # 与 mdm.status_codes(release_card) 对齐：draft/pending_review/decided
        assert "decided" in RELEASE_CARD_TRANSITIONS["draft"]
        assert "pending_review" in RELEASE_CARD_TRANSITIONS["draft"]
        assert "decided" in RELEASE_CARD_TRANSITIONS["pending_review"]

    def test_terminal_state(self):
        assert RELEASE_CARD_TRANSITIONS["decided"] == set()

    def test_no_illegal_transition(self):
        # 任何状态不得回退到 draft（历史 pending 兼容键除外）
        for current, allowed in RELEASE_CARD_TRANSITIONS.items():
            if current == "pending":
                continue
            assert "draft" not in allowed or current == "draft"


# ── 4b. 放行卡 decided 补偿回退（CRITICAL 回归） ────────────────

class TestReleaseCardCompensation:
    """审批 agree 后候选回写失败的补偿回退：decided 是终态，
    普通 update 必然被状态机拒绝；必须走 store.rollback_decided 专用通道。
    需要真实 PostgreSQL（连 mdm.status_codes 校验）。"""

    def setup_method(self):
        import uuid
        from datetime import datetime, timezone
        from battery_materials_agent.release_card.models import ReleaseCard
        from battery_materials_agent.release_card.store import ReleaseCardStore
        self.store = ReleaseCardStore()
        self.card_id = f"rc-regress-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)
        card = ReleaseCard(card_id=self.card_id, title="补偿回退回归测试", status="draft")
        self.store.create(card)
        card.status = "decided"
        card.human_responsibility = {
            "reviewer": "tester", "review_opinion": "",
            "final_decision": "agree", "decided_at": now.isoformat(),
        }
        self.store.update(card)

    def teardown_method(self):
        self.store.delete(self.card_id)

    def test_normal_update_cannot_rollback_decided(self):
        # 状态机保证 decided 是终态：普通 update 回退必须拒绝（防止误用绕过补偿通道）
        from battery_materials_agent.release_card.models import ReleaseCard  # noqa: F401
        card = self.store.get(self.card_id)
        card.status = "pending_review"
        with pytest.raises(ValueError):
            self.store.update(card)

    def test_rollback_decided_restores_pending_review_with_trace(self):
        rolled = self.store.rollback_decided(self.card_id, reason="候选回写失败，测试补偿")
        assert rolled.status == "pending_review"
        comps = (rolled.provenance or {}).get("compensations") or []
        assert comps and comps[-1]["reason"] == "候选回写失败，测试补偿"
        # 回退后可重新裁决（pending_review → decided），闭环可恢复
        rolled.status = "decided"
        self.store.update(rolled)

    def test_rollback_rejects_non_decided(self):
        first = self.store.rollback_decided(self.card_id, reason="首次补偿")
        assert first.status == "pending_review"
        with pytest.raises(ValueError):
            self.store.rollback_decided(self.card_id, reason="非 decided 不允许补偿")


# ── 6b. 候选可信度档权威派生（ADR-0001 + 领域决策 2026-08-23） ──

class TestCandidateEvidenceLevel:
    """CandidateRecord.evidence_level 是前端徽标唯一数据源，
    前端不得从 property_source 自行推导。纯模型级测试，无需 DB。"""

    def _rec(self, source, data=None):
        from battery_materials_agent.experiment.candidate_store import CandidateRecord
        return CandidateRecord(candidate_id="x", source=source, data=data or {})

    def test_llm_generated_is_predicted(self):
        # 领域决策（2026-08-23）：LLM 生成来源按模型预测展示
        dump = self._rec("llm_generated").model_dump()
        assert dump["evidence_level"] == "predicted"  # 必须出现在序列化输出中
        assert self._rec("internlm_generated").evidence_level == "predicted"

    def test_lookup_and_heuristic_sources_are_estimated(self):
        for src in ("engineering_plastics", "rule_based", "derivative", "known",
                    "gnome_pg", "gnome_local", "materials_project", "local_database"):
            assert self._rec(src).evidence_level == "estimated", src

    def test_explicit_data_level_wins(self):
        # data 显式标注优先于来源映射（逐条逃生通道）
        assert self._rec("engineering_plastics", {"evidence_level": "predicted"}).evidence_level == "predicted"

    def test_unknown_source_defaults_estimated(self):
        # ADR-0001 保守取向：无法证明是真实权重模型的不得称预测
        assert self._rec("").evidence_level == "estimated"


# ── 7. demo 模拟测量值围绕估算值 ───────────────────────────────

class TestSimulationAroundEstimate:
    def setup_method(self):
        self.ec = ExperimentController(run_mode="demo")

    def test_tensile_around_estimate(self):
        res = self.ec.execute_experiment(
            {"formula": "PA6/GF30", "estimated": {"tensile_strength": 160.0}},
            ExperimentType.TENSILE,
        )
        val = res.measured_values["tensile_strength_MPa"]
        # ±10% 噪声 → 144-176
        assert 144.0 <= val <= 176.0
        assert res.metadata.get("mode") == "simulated"

    def test_no_estimate_fallback(self):
        res = self.ec.execute_experiment({"formula": "X"}, ExperimentType.TENSILE)
        val = res.measured_values["tensile_strength_MPa"]
        assert 40.0 <= val <= 180.0

    def test_deterministic(self):
        r1 = self.ec.execute_experiment(
            {"formula": "PA6/GF30", "estimated": {"tensile_strength": 160.0}},
            ExperimentType.TENSILE,
        )
        r2 = self.ec.execute_experiment(
            {"formula": "PA6/GF30", "estimated": {"tensile_strength": 160.0}},
            ExperimentType.TENSILE,
        )
        assert r1.measured_values["tensile_strength_MPa"] == r2.measured_values["tensile_strength_MPa"]


# ── 6. 描述符启发式术语分层（ADR-0001） ────────────────────────

class TestHeuristicTerminology:
    def setup_method(self):
        self.predictor = PolymerPropertyPredictor(model_type="descriptor")

    def test_heuristic_label_and_confidence(self):
        result = self.predictor.predict({"psmiles": "Polymer([*]CC(C)[*])"}, "tensile_strength")
        assert result.model == "descriptor_heuristic"
        assert result.confidence <= 0.5
        assert result.data_quality == "estimated"
        prov = result.provenance or []
        assert prov and prov[0]["evidence_level"] == "estimated"

    def test_ionic_conductivity_unsupported(self):
        with pytest.raises(ValueError):
            self.predictor.predict({"psmiles": "Polymer([*]CCO[*])"}, "ionic_conductivity")


# ── 8. BO 材料分派（v4.1 工程塑料候选正确走聚合物描述符） ─────────

class TestBOIsPolymer:
    def setup_method(self):
        from battery_materials_agent.ecml.bo import _is_polymer_candidate, classify_family

        self._is_polymer = _is_polymer_candidate
        self._classify = classify_family

    def test_engineering_plastic_without_material_type(self):
        # 历史/无 material_type 字段的工程塑料候选（formula 含 PA6/GF30）→ 聚合物
        cand = {"formula": "PA6/GF30", "name": "PA6/GF30", "data": {"tensile_strength": 160}}
        assert self._is_polymer(cand) is True

    def test_psmiles_marker(self):
        cand = {"psmiles": "Polymer([*]CC(C)[*])"}
        assert self._is_polymer(cand) is True

    def test_crystal_negative(self):
        assert self._is_polymer({"formula": "LiCoO2"}) is False
        assert self._is_polymer({"formula": "NaCl"}) is False

    def test_classify_engineering_plastic_as_polymer(self):
        # 此前 PP/PA6/PC 会被归类成 "P-based"；v4.1 归入 polymer 族
        assert self._classify("PA6/GF30") == "polymer"
        assert self._classify("PP") == "polymer"
        assert self._classify("PC/ABS") == "polymer"

    def test_classify_crystal_unchanged(self):
        assert self._classify("LiCoO2") == "layered_oxide"
        # Li6PS5Cl 含 argyrodite 骨架（Li6PS5），归 argyrodite（硫化物子类）比 sulfide 更精确
        assert self._classify("Li6PS5Cl") in ("argyrodite", "sulfide")


class TestPolymerCandidateMaterialType:
    def test_model_dump_includes_material_type(self):
        from battery_materials_agent.generation.polymer_candidate_generator import PolymerCandidate

        c = PolymerCandidate(name="PA6/GF30", psmiles="Polymer([*]CCCCC(=O)N[*])")
        dumped = c.model_dump()
        assert dumped.get("material_type") == "polymer"


# ── 7. ECML 闭环验证精度（按 formula 对齐） ────────────────────

class TestValidationMetrics:
    def _make_engine(self):
        return ECMLEngine()

    def test_alignment_by_formula(self):
        engine = self._make_engine()
        state = ECMLState(
            run_id="t-run",
            target="PA6",
            target_property="tensile_strength",
        )
        state.candidates = [
            {"formula": "PA6/GF30", "name": "PA6/GF30",
             "data": {"tensile_strength": 160.0, "flexural_modulus": 7000.0}},
            {"formula": "PA6/POE", "name": "PA6/POE",
             "data": {"tensile_strength": 65.0, "flexural_modulus": 2000.0}},
        ]
        state.predictions = [
            {"property_name": "tensile_strength", "value": 160.0, "formula": "PA6/GF30"},
        ]
        # 模拟记录：sample_id 编码 formula，值与估算 ±10% 一致
        validation_data = [
            {"property_name": "prop.tensile_strength", "value": 155.0,
             "sample_id": "smp_PA6/GF30_1", "data_quality": "simulated"},
            {"property_name": "prop.tensile_strength", "value": 70.0,
             "sample_id": "smp_PA6/POE_1", "data_quality": "simulated"},
        ]
        metrics = engine._compute_validation_metrics(state, validation_data)
        assert metrics["n_records"] == 2
        assert metrics["n_compared"] == 2
        # PA6/GF30: |160-155|/155≈3.2%；PA6/POE: |65-70|/70≈7.1% → 平均 ≈5.2%
        assert 3.0 < metrics["overall_mape_pct"] < 8.0
        assert metrics["within_10pct_pct"] == 100.0
        assert metrics["data_quality_distribution"] == {"simulated": 2}

    def test_empty_records(self):
        engine = self._make_engine()
        state = ECMLState(run_id="t-run", target="PA6", target_property="tensile_strength")
        state.predictions = [{"property_name": "tensile_strength", "value": 100.0}]
        metrics = engine._compute_validation_metrics(state, [])
        assert metrics["n_compared"] == 0

    def test_mismatched_formula_skipped(self):
        engine = self._make_engine()
        state = ECMLState(run_id="t-run", target="PA6", target_property="tensile_strength")
        state.candidates = [{"formula": "PA6/GF30", "data": {"tensile_strength": 160.0}}]
        state.predictions = [{"property_name": "tensile_strength", "value": 160.0}]
        # 无匹配 formula 的记录不参与对比
        validation_data = [
            {"property_name": "prop.tensile_strength", "value": 999.0, "sample_id": "other_1", "data_quality": "simulated"},
        ]
        metrics = engine._compute_validation_metrics(state, validation_data)
        assert metrics["n_compared"] == 0
