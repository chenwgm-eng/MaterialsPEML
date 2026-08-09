"""ReactionAdapter 降级标记与化学规则过滤回归测试。

覆盖 Review 发现的三类问题：
1. TS 搜索占位结果不得伪造 ``ts_found=True`` + 硬编码能垒——
   必须显式标记 ``degraded: True`` / ``ts_found: False``，避免被下游当真实证据。
2. 化学规则过滤 ``_filter_by_chemical_rules`` 必须为真实实现——
   按元素/原子守恒 + 平凡反应剔除，而非直通放行。
"""
from __future__ import annotations

import pytest

from battery_materials_agent.infrastructure.executors.reaction_adapter import (
    ReactionAdapter,
    _PlaceholderAdapter,
)
from battery_materials_agent.services.reaction_network.application import (
    _PlaceholderReactionAdapter,
)

rdkit = pytest.importorskip("rdkit")


def _rxn(smiles: str) -> dict:
    return {"reaction_smiles": smiles, "evidence_stage": 0, "confidence": 0.5}


class TestTsSearchPlaceholderMarking:
    """TS 搜索占位必须标记 degraded，且不得给出硬编码能垒。"""

    def _assert_placeholder(self, result: dict):
        assert result["ts_found"] is False
        assert result["degraded"] is True
        assert result["barrier_kcal"] is None
        assert result["frequency"] is None
        assert result["reactions"][0]["metadata"]["ts_found"] is False
        assert result["warnings"], "占位结果必须包含警告"

    def test_infrastructure_placeholder_ts_search(self):
        result = _PlaceholderAdapter()._placeholder_ts_search("CCO>>CCO.C")
        self._assert_placeholder(result)

    def test_infrastructure_rdkit_path_ts_search(self):
        result = ReactionAdapter()._execute_ts_search(
            {"reaction_smiles": "CCO>>CCO.C"}
        )
        self._assert_placeholder(result)

    def test_infrastructure_rdkit_path_requires_rdkit_and_networkx(self, monkeypatch):
        # 缺少 rdkit/networkx 时 execute 走占位，不进入真实实现
        adapter = ReactionAdapter()
        monkeypatch.setattr(adapter, "_rdkit_available", False)
        result = adapter.execute({"command": "ts_search", "reaction_smiles": "CCO>>CCO.C"})
        self._assert_placeholder(result)

    def test_service_placeholder_ts_search(self):
        result = _PlaceholderReactionAdapter()._placeholder_ts_search("CCO>>CCO.C")
        self._assert_placeholder(result)

    @pytest.mark.parametrize(
        "pygsm_ok,xtb_ok,expected",
        [
            (True, True, True),   # 引擎齐全 → 启用真实搜索
            (False, True, False),  # 缺 PyGSM → 探测失败
            (True, False, False),  # 缺 xTB   → 探测失败
            (False, False, False), # 都缺     → 探测失败
        ],
    )
    def test_ts_engines_available_detection(self, monkeypatch, pygsm_ok, xtb_ok, expected):
        """能力探测应真实反映 PyGSM/xTB 可用性（环境无关）。"""
        import builtins
        import types

        def _dummy(name):
            return types.ModuleType(name)

        def fake_import(name, *args, **kwargs):
            if name == "pyGSM":
                if not pygsm_ok:
                    raise ImportError("no pyGSM")
                return _dummy("pyGSM")
            if name == "xtb":
                if not xtb_ok:
                    raise ImportError("no xtb")
                return _dummy("xtb")
            raise ImportError(f"unexpected import: {name}")

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert ReactionAdapter._ts_engines_available() is expected


class TestTsSearchCapabilityDispatch:
    """真实 TS 搜索能力探测式派发。"""

    def setup_method(self):
        self.adapter = ReactionAdapter()

    def test_dispatches_to_real_when_engines_available(self, monkeypatch):
        real = {"status": "completed", "ts_found": True, "barrier_kcal": 12.3,
                "frequency": -250.0, "degraded": False}
        monkeypatch.setattr(
            ReactionAdapter, "_ts_engines_available",
            staticmethod(lambda: True),
        )
        monkeypatch.setattr(
            ReactionAdapter, "_execute_real_ts_search",
            lambda self, p: real,
        )
        result = self.adapter._execute_ts_search({"reaction_smiles": "CCO>>C=C"})
        assert result is real
        assert result["degraded"] is False

    def test_falls_back_to_degraded_on_real_failure(self, monkeypatch):
        def _boom(self, p):
            raise RuntimeError("xtb failed")

        monkeypatch.setattr(
            ReactionAdapter, "_ts_engines_available",
            staticmethod(lambda: True),
        )
        monkeypatch.setattr(ReactionAdapter, "_execute_real_ts_search", _boom)
        result = self.adapter._execute_ts_search({"reaction_smiles": "CCO>>C=C"})
        assert result["ts_found"] is False
        assert result["degraded"] is True
        assert any("已降级" in w for w in result["warnings"])

    def test_times_out_and_degrades(self, monkeypatch):
        """超时后应立即降级返回，不阻塞调用方。"""
        import time

        def _slow(self, p):
            time.sleep(0.5)
            return {"ts_found": True, "degraded": False}

        monkeypatch.setattr(
            ReactionAdapter, "_ts_engines_available", staticmethod(lambda: True),
        )
        monkeypatch.setattr(ReactionAdapter, "_execute_real_ts_search", _slow)
        result = self.adapter._execute_ts_search({
            "reaction_smiles": "CCO>>C=C",
            "config": {"timeout_seconds": 0.05},
        })
        assert result["ts_found"] is False
        assert result["degraded"] is True
        assert any("超时" in w for w in result["warnings"])


class TestAtomMapping:
    """产物原子对齐：支持任意原子书写顺序的通用反应。"""

    def setup_method(self):
        self.adapter = ReactionAdapter()

    def test_align_product_atoms_different_order(self):
        from rdkit import Chem
        r_mol = Chem.MolFromSmiles("CC(=O)O")   # 乙酸
        p_mol = Chem.MolFromSmiles("OC(=O)C")   # 乙酸，不同书写顺序
        aligned = self.adapter._align_product_atoms(r_mol, p_mol)
        assert aligned is not None
        r_syms = [a.GetSymbol() for a in r_mol.GetAtoms()]
        p_syms = [a.GetSymbol() for a in aligned.GetAtoms()]
        assert r_syms == p_syms

    def test_align_product_atoms_none_when_unmappable(self):
        from rdkit import Chem
        r_mol = Chem.MolFromSmiles("CC.CC")   # 两个乙烷
        p_mol = Chem.MolFromSmiles("CCCC")    # 丁烷（骨架重排，无法子结构匹配）
        assert self.adapter._align_product_atoms(r_mol, p_mol) is None


class TestChemicalRulesFiltering:
    """化学规则过滤真实实现：元素/原子守恒 + 平凡反应剔除。"""

    def setup_method(self):
        self.adapter = ReactionAdapter()

    def test_passes_valid_conserving_reaction(self):
        reactions = [_rxn("C.C>>CC")]  # 两甲烷偶联合成乙烷，重原子守恒
        kept = self.adapter._filter_by_chemical_rules(reactions)
        assert kept == reactions
        assert reactions[0]["metadata"]["rule_filter_passed"] is True

    def test_rejects_unbalanced_element(self):
        # 产物含 O，而反应物不含 → 元素不守恒
        reactions = [_rxn("C>>CO")]
        kept = self.adapter._filter_by_chemical_rules(reactions)
        assert kept == []
        assert reactions[0]["metadata"]["rule_filter_passed"] is False
        assert reactions[0]["metadata"]["rule_filter_reason"] == "element_not_conserved"

    def test_rejects_atom_count_increase(self):
        # 产物 C 数多于反应物 → 原子不守恒
        reactions = [_rxn("C>>CC")]
        kept = self.adapter._filter_by_chemical_rules(reactions)
        assert kept == []
        assert reactions[0]["metadata"]["rule_filter_reason"] == "atom_count_not_conserved"

    def test_rejects_trivial_reaction(self):
        # 反应物与产物规范相同 → 平凡反应
        reactions = [_rxn("C(C)O>>C(C)O")]
        kept = self.adapter._filter_by_chemical_rules(reactions)
        assert kept == []
        assert reactions[0]["metadata"]["rule_filter_reason"] == "trivial_reaction"

    def test_keeps_unparseable_reaction(self):
        # 无法用 RDKit 解析的反应保留，避免误伤
        reactions = [_rxn("C>>C_product")]  # 伪产物无法解析
        kept = self.adapter._filter_by_chemical_rules(reactions)
        assert kept == reactions
        assert reactions[0]["metadata"]["rule_filter_applied"] is True

    def test_marks_every_reaction_as_applied(self):
        reactions = [_rxn("C>>CO"), _rxn("C.C>>CC")]
        self.adapter._filter_by_chemical_rules(reactions)
        assert all(r["metadata"]["rule_filter_applied"] is True for r in reactions)