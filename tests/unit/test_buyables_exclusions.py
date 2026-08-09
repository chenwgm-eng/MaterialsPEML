"""企业 buyables 关键修复的回归测试。

覆盖：
  * M5 — 单-NCO 中间体排除（EXCLUDE_SMILES）与 SMILES 规范化语义；
  * M1 — 企业库不可达时的冷却期（enterprise_refresh_due），避免每次 lookup
    都触发连接超时阻塞；
  * 单一来源守卫 — pricer 与 sync_buyables 引用同一份 EXCLUDE_SMILES / 规范化，
    防止两处各自维护导致语义漂移。
"""
from __future__ import annotations

import sys

import pytest

# 共享模块位于 ASKCOS patches 目录，须先加入 sys.path。
_BUYABLE_PATCH_DIR = "askcos-deploy/custom/patches/makeit/utilities/buyable"
if _BUYABLE_PATCH_DIR not in sys.path:
    sys.path.insert(0, _BUYABLE_PATCH_DIR)

import buyables_exclusions as excl  # noqa: E402
from buyables_exclusions import EXCLUDE_SMILES, canonical_smiles, enterprise_refresh_due  # noqa: E402

# M5 目标：两种人工单-NCO 中间体必须被排除，否则 MCTS 会在单-NCO 处停机。
_MDA_NCO_RAW = "Nc1ccc(Cc2ccc(N=C=O)cc2)cc1"
_HMD_NCO_RAW = "NCCCCCCN=C=O"


@pytest.mark.parametrize("nco", [_MDA_NCO_RAW, _HMD_NCO_RAW])
def test_m5_nco_intermediates_excluded(nco):
    """M5：单-NCO 中间体必须出现在排除集合中。"""
    assert nco in EXCLUDE_SMILES


def test_m5_exclude_smiles_are_canonical():
    """M5：排除集合内的 SMILES 必须已是 RDKit 规范形式（与可购字典 key 对齐）。"""
    for smi in EXCLUDE_SMILES:
        assert canonical_smiles(smi) == smi


def test_canonical_smiles_returns_none_on_invalid():
    """M5：不可解析 SMILES 必须返回 None（与 pricer/sync_buyables 一致，避免误去重）。"""
    assert canonical_smiles("not a smiles") is None
    # 空串解析为空分子，规范结果为空串（非 None），但不应被误判为可购。
    assert canonical_smiles("") == ""


def test_canonical_smiles_normalizes():
    """规范化应统一非规范写法为规范形式。"""
    canonical = canonical_smiles("c1ccc(cc1)C(=O)O")
    assert canonical == "O=C(O)c1ccccc1"


def test_m1_enterprise_refresh_due_cooling_period():
    """M1：失败/加载后进入冷却期，TTL 内不再触发刷新。"""
    ttl = 30.0
    now = 1000.0
    # 刚加载过（loaded_at 接近 now）→ 不应刷新
    assert enterprise_refresh_due(now - 1.0, ttl, now) is False
    # 超过 TTL → 应刷新
    assert enterprise_refresh_due(now - ttl - 1.0, ttl, now) is True


def test_m1_failure_also_sets_cooldown_timestamp():
    """M1：企业库不可达时同样更新时间戳走冷却期（回归：不可把 loaded_at 留 0）。"""
    # 初始 loaded_at=0 表示从未加载 → 应立即刷新
    assert enterprise_refresh_due(0.0, 30.0, 1000.0) is True
    # 失败后即使不打时间戳，也应视为“刚尝试过”而进入冷却期
    assert enterprise_refresh_due(999.0, 30.0, 1000.0) is False


def test_single_source_exclude_and_canonical_shared():
    """单一来源守卫：同步脚本与 Pricer 共用同一份常量/规范化，未各自复制。"""
    import importlib.util

    # 加载 sync_buyables 模块，确认其引用的是共享模块而非本地重复定义。
    sync_path = "askcos-deploy/template_build/sync_buyables.py"
    spec = importlib.util.spec_from_file_location("_sync_buyables", sync_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.EXCLUDE_SMILES is EXCLUDE_SMILES
    assert mod.canonical_smiles is canonical_smiles


def test_single_source_pricer_imports_shared():
    """单一来源守卫：Pricer 源码通过包导入共享模块，而非内联集合。"""
    pricer_path = "askcos-deploy/custom/patches/makeit/utilities/buyable/pricer.py"
    with open(pricer_path, encoding="utf-8") as f:
        src = f.read()
    assert "from makeit.utilities.buyable.buyables_exclusions import" in src
    # 不应再存在本地重复定义
    assert "EXCLUDE_SMILES = {" not in src
    assert "def _canonical_smiles" not in src