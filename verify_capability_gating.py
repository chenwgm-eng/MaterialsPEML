"""能力契约门禁改造验证脚本。

验证目标：
1. CapabilityRegistry.is_callable() 对 deprecated/pending_high_risk 返回 False
2. CapabilityRegistry.find_callable_fallback() 能找到 fallback 链中的可调用契约
3. CapabilityRouter.resolve() 在契约 deprecated 时：
   - 有可调用 fallback → 返回 degraded=True 的候选
   - 整条链不可调用 → 返回空列表
4. @require_capability 装饰器在契约不可调用时抛 403

不连接真实数据库，使用 mock 对象隔离测试。
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

# ── 测试 1: CapabilityRegistry.is_callable() 逻辑（不连 DB，mock get_status） ──

print("=" * 70)
print("测试 1: CapabilityRegistry.is_callable() 门禁规则")
print("=" * 70)

from battery_materials_agent.capability.registry import CapabilityRegistry

reg = CapabilityRegistry.__new__(CapabilityRegistry)  # 跳过 __init__（避免连 DB）
reg._status_cache = {}

# Mock get_status 返回不同状态
test_cases = [
    # (capability_id, mock_status_risk, expected_callable, expected_reason)
    ("active_cap", ("active", "medium"), True, "active"),
    ("deprecated_cap", ("deprecated", "low"), False, "deprecated"),
    ("pending_high", ("pending_approval", "high"), False, "pending_high_risk"),
    ("pending_low", ("pending_approval", "medium"), True, "pending_approval"),
    ("pending_medium", ("pending_approval", "medium"), True, "pending_approval"),
    ("unknown_cap", None, True, "no_contract"),
]

passed = 0
failed = 0
for cap_id, status_risk, expected_ok, expected_reason in test_cases:
    reg.get_status = MagicMock(return_value=status_risk)
    ok, reason = reg.is_callable(cap_id)
    status = "PASS" if (ok == expected_ok and reason == expected_reason) else "FAIL"
    if status == "PASS":
        passed += 1
    else:
        failed += 1
    print(f"  [{status}] {cap_id}: is_callable={ok} (reason={reason}), "
          f"expected={expected_ok} ({expected_reason})")

print(f"\n  结果: {passed} passed, {failed} failed\n")

# ── 测试 2: find_callable_fallback() 自动走 fallback 链 ──

print("=" * 70)
print("测试 2: find_callable_fallback() 自动走 fallback 链")
print("=" * 70)

from battery_materials_agent.capability.models import CapabilityContract

# Mock: 主能力 deprecated，fallback 链中 heuristic_baseline_v1 可调用
reg.get_status = MagicMock(side_effect=lambda cid: {
    "crystal_property_prediction_v1": ("deprecated", "medium"),
    "heuristic_baseline_v1": ("active", "low"),
}.get(cid))

# Mock get_fallback_chain 返回主能力 + fallback
main_contract = CapabilityContract(
    capability_id="crystal_property_prediction_v1",
    fallback_chain=["heuristic_baseline_v1"],
)
fb_contract = CapabilityContract(
    capability_id="heuristic_baseline_v1",
    fallback_chain=[],
)
reg.get_fallback_chain = MagicMock(return_value=[main_contract, fb_contract])

fallback_id, reason = reg.find_callable_fallback("crystal_property_prediction_v1")
if fallback_id == "heuristic_baseline_v1" and reason == "fallback:crystal_property_prediction_v1":
    print(f"  [PASS] 主能力 deprecated → fallback 到 {fallback_id} (reason={reason})")
    passed += 1
else:
    print(f"  [FAIL] expected heuristic_baseline_v1, got {fallback_id} ({reason})")
    failed += 1

# 测试整条链都不可调用
reg.get_status = MagicMock(side_effect=lambda cid: {
    "crystal_property_prediction_v1": ("deprecated", "medium"),
    "heuristic_baseline_v1": ("deprecated", "low"),
}.get(cid))
fallback_id, reason = reg.find_callable_fallback("crystal_property_prediction_v1")
if fallback_id is None and reason == "no_callable_fallback":
    print(f"  [PASS] 整条链 deprecated → {fallback_id} (reason={reason})")
    passed += 1
else:
    print(f"  [FAIL] expected None, got {fallback_id} ({reason})")
    failed += 1

# 测试主能力本身可调用
reg.get_status = MagicMock(return_value=("active", "medium"))
fallback_id, reason = reg.find_callable_fallback("crystal_property_prediction_v1")
if fallback_id == "crystal_property_prediction_v1" and reason == "primary_callable":
    print(f"  [PASS] 主能力可调用 → {fallback_id} (reason={reason})")
    passed += 1
else:
    print(f"  [FAIL] expected primary, got {fallback_id} ({reason})")
    failed += 1

print(f"\n  结果: 3 tests, {passed - 6} passed in this section\n")

# ── 测试 3: CapabilityRouter.resolve() 集成门禁 ──

print("=" * 70)
print("测试 3: CapabilityRouter.resolve() 契约门禁生效")
print("=" * 70)

from battery_materials_agent.control_plane.capability_router import CapabilityRouter
from battery_materials_agent.mcp_tools.alias_registry import AliasRegistry
from battery_materials_agent.agent_team.eligibility_store import EligibilityStore

alias_reg = AliasRegistry()
elig_store = EligibilityStore()

# 场景 A: 契约 active → 正常返回候选
mock_cap_reg = MagicMock()
mock_cap_reg.is_callable = MagicMock(return_value=(True, "active"))
mock_cap_reg.get_status = MagicMock(return_value=("active", "medium"))
router = CapabilityRouter(alias_reg, elig_store, capability_registry=mock_cap_reg)

async def test_active():
    candidates = await router.resolve("property_prediction", "standard")
    return candidates

candidates = asyncio.run(test_active())
if candidates and candidates[0].capability_id == "crystal_property_prediction_v1" and not candidates[0].degraded:
    print(f"  [PASS] 契约 active → 返回 {len(candidates)} 个候选，degraded=False")
    passed += 1
else:
    print(f"  [FAIL] 契约 active 场景: candidates={len(candidates)}, "
          f"degraded={candidates[0].degraded if candidates else 'N/A'}")
    failed += 1

# 场景 B: 契约 deprecated + 有 fallback → 返回 degraded=True 候选
mock_cap_reg = MagicMock()
mock_cap_reg.is_callable = MagicMock(side_effect=lambda cid: {
    "crystal_property_prediction_v1": (False, "deprecated"),
    "heuristic_baseline_v1": (True, "active"),
}.get(cid, (True, "no_contract")))
mock_cap_reg.get_status = MagicMock(side_effect=lambda cid: {
    "crystal_property_prediction_v1": ("deprecated", "medium"),
    "heuristic_baseline_v1": ("active", "low"),
}.get(cid))
mock_cap_reg.find_callable_fallback = MagicMock(
    return_value=("heuristic_baseline_v1", "fallback:crystal_property_prediction_v1")
)
router = CapabilityRouter(alias_reg, elig_store, capability_registry=mock_cap_reg)

async def test_degraded():
    candidates = await router.resolve("property_prediction", "standard")
    return candidates

candidates = asyncio.run(test_degraded())
if candidates and candidates[0].degraded and candidates[0].fallback_from == "crystal_property_prediction_v1":
    print(f"  [PASS] 契约 deprecated + 有 fallback → 返回 degraded 候选 "
          f"(fallback_from={candidates[0].fallback_from})")
    passed += 1
else:
    print(f"  [FAIL] degraded 场景: candidates={len(candidates)}, "
          f"degraded={candidates[0].degraded if candidates else 'N/A'}")
    failed += 1

# 场景 C: 契约 deprecated + 无可用 fallback → 返回空列表
mock_cap_reg = MagicMock()
mock_cap_reg.is_callable = MagicMock(return_value=(False, "deprecated"))
mock_cap_reg.find_callable_fallback = MagicMock(return_value=(None, "no_callable_fallback"))
router = CapabilityRouter(alias_reg, elig_store, capability_registry=mock_cap_reg)

async def test_blocked():
    candidates = await router.resolve("property_prediction", "standard")
    return candidates

candidates = asyncio.run(test_blocked())
if not candidates:
    print(f"  [PASS] 契约 deprecated + 无 fallback → 返回空列表（调用方应拒绝）")
    passed += 1
else:
    print(f"  [FAIL] blocked 场景: expected empty, got {len(candidates)} candidates")
    failed += 1

# 场景 D: 无 capability_registry 注入 → 向后兼容，正常返回
router_no_reg = CapabilityRouter(alias_reg, elig_store, capability_registry=None)

async def test_no_reg():
    candidates = await router_no_reg.resolve("property_prediction", "standard")
    return candidates

candidates = asyncio.run(test_no_reg())
if candidates:
    print(f"  [PASS] 未注入 capability_registry → 向后兼容，返回 {len(candidates)} 个候选")
    passed += 1
else:
    print(f"  [FAIL] 未注入 capability_registry 场景: expected candidates, got empty")
    failed += 1

# ── 测试 4: @require_capability 装饰器 ──

print()
print("=" * 70)
print("测试 4: @require_capability 装饰器门禁")
print("=" * 70)

from battery_materials_agent.api import require_capability, _get_capability_registry
from fastapi import HTTPException

# Mock 全局 capability registry 单例
import battery_materials_agent.api as api_module

mock_singleton = MagicMock()
mock_singleton.is_callable = MagicMock(return_value=(False, "deprecated"))
mock_singleton.find_callable_fallback = MagicMock(return_value=(None, "no_callable_fallback"))
api_module._capability_registry_singleton = mock_singleton

@require_capability("crystal_property_prediction_v1")
async def mock_handler():
    return {"result": "ok"}

# 契约不可调用 + 无 fallback → 应抛 403
try:
    asyncio.run(mock_handler())
    print(f"  [FAIL] 预期抛 403，但未抛出")
    failed += 1
except HTTPException as e:
    if e.status_code == 403 and e.detail.get("error") == "capability_blocked":
        print(f"  [PASS] 契约 deprecated + 无 fallback → 抛 403 (capability_blocked)")
        passed += 1
    else:
        print(f"  [FAIL] 抛了 HTTPException 但状态码或 detail 不对: {e.status_code} {e.detail}")
        failed += 1

# 契约不可调用 + 有 fallback → 降级执行，不抛异常
mock_singleton.is_callable = MagicMock(return_value=(False, "deprecated"))
mock_singleton.find_callable_fallback = MagicMock(
    return_value=("heuristic_baseline_v1", "fallback:crystal_property_prediction_v1")
)

try:
    result = asyncio.run(mock_handler())
    if result == {"result": "ok"}:
        print(f"  [PASS] 契约 deprecated + 有 fallback → 降级执行，返回正常结果")
        passed += 1
    else:
        print(f"  [FAIL] 降级执行结果不对: {result}")
        failed += 1
except HTTPException as e:
    print(f"  [FAIL] 预期降级执行，但抛了 {e.status_code}")
    failed += 1

# 契约可调用 → 正常执行
mock_singleton.is_callable = MagicMock(return_value=(True, "active"))

try:
    result = asyncio.run(mock_handler())
    if result == {"result": "ok"}:
        print(f"  [PASS] 契约 active → 正常执行")
        passed += 1
    else:
        print(f"  [FAIL] 正常执行结果不对: {result}")
        failed += 1
except HTTPException as e:
    print(f"  [FAIL] 预期正常执行，但抛了 {e.status_code}")
    failed += 1

# ── 总结 ──

print()
print("=" * 70)
print(f"总结: {passed} passed, {failed} failed")
print("=" * 70)

if failed > 0:
    exit(1)
else:
    print("\n所有门禁逻辑验证通过 ✅")
