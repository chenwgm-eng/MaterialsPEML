"""领域包流水线（Pipeline）与统一阶段执行器（StageExecutor）单元测试。

覆盖：
- PipelineResolver 内置兜底三分支（crystal/polymer/molecule），verify_dft 随 requires_dft 条件出现
- 领域包 pipeline 段覆盖内置流水线（含未知类型、默认 "*"）
- PipelineStage.resolved_capability 能力映射与覆盖
- StageExecutor 统一分派 native/scp/skill/agent 及未注册类型报错
- HybridOrchestrator._generate_steps 从领域包解析流水线（带兜底）
"""

from types import SimpleNamespace

import asyncio

from battery_materials_agent.hybrid.pipeline import (
    PipelineResolver,
    PipelineStage,
)
from battery_materials_agent.hybrid.stage_executor import StageExecutor


def _run(coro):
    """同步测试中驱动 async execute。"""
    try:
        loop = asyncio.get_running_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop).result()
    except RuntimeError:
        return asyncio.run(coro)


def _collect_async_gen(agen):
    """同步测试中驱动并收集 async generator 的全部产出。"""
    async def _drain():
        return [item async for item in agen]

    try:
        loop = asyncio.get_running_loop()
        return asyncio.run_coroutine_threadsafe(_drain(), loop).result()
    except RuntimeError:
        return asyncio.run(_drain())


# ── PipelineResolver ──────────────────────────────────────────────


def test_resolver_builtin_crystal_conditional_dft():
    res = PipelineResolver()
    # requires_dft=True → 含 verify_dft
    stages = res.resolve("crystal", {"requires_dft": True})
    action_names = [s.action for s in stages]
    assert action_names == [
        "route_material",
        "generate_crystal_candidates",
        "predict_crystal_properties",
        "verify_dft",
        "compliance_check",
    ]
    # requires_dft=False → 不含 verify_dft
    stages_no_dft = res.resolve("crystal", {"requires_dft": False})
    assert "verify_dft" not in [s.action for s in stages_no_dft]


def test_resolver_builtin_polymer_and_molecule():
    res = PipelineResolver()
    poly = [s.action for s in res.resolve("polymer")]
    assert poly == [
        "route_material", "generate_polymer_candidates",
        "predict_polymer_properties", "design_formula", "compliance_check",
    ]
    mol = [s.action for s in res.resolve("molecule")]
    assert mol == [
        "route_material", "generate_polymer_candidates",
        "check_synthesis_feasibility", "predict_crystal_properties", "compliance_check",
    ]


def test_resolver_domain_pack_overrides_custom_type():
    """领域包声明的自定义材料类型流水线优先于内置。"""
    domain_pack = {
        "pipeline": {
            "fiber": [
                {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
                {"action": "generate_fiber_candidates", "agent_role": "thinker", "autonomy_level": "L0"},
                {"action": "predict_fiber_properties", "agent_role": "doer", "autonomy_level": "L1"},
                {"action": "compliance_check", "agent_role": "verifier", "autonomy_level": "L2"},
            ]
        }
    }
    stages = PipelineResolver(domain_pack).resolve("fiber")
    assert [s.action for s in stages] == [
        "route_material", "generate_fiber_candidates",
        "predict_fiber_properties", "compliance_check",
    ]


def test_resolver_domain_pack_default_star():
    """领域包 "*" 默认流水线用于未匹配的具体类型。"""
    domain_pack = {
        "pipeline": {
            "*": [
                {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
                {"action": "compliance_check", "agent_role": "verifier", "autonomy_level": "L2"},
            ]
        }
    }
    stages = PipelineResolver(domain_pack).resolve("coating")
    assert [s.action for s in stages] == ["route_material", "compliance_check"]


def test_resolver_unknown_type_falls_back_to_builtin():
    res = PipelineResolver()
    stages = res.resolve("unknown_new_material")
    # 回退到内置 molecule 默认
    assert stages[0].action == "route_material"
    assert stages[-1].action == "compliance_check"


def test_resolver_prefers_specific_over_star():
    """具体类型优先于 "*"，且 per-stage 能力可覆盖默认映射。"""
    domain_pack = {
        "pipeline": {
            "coating": [
                {"action": "adhesion_screen", "capability": "coating_adh_check",
                 "agent_role": "doer", "autonomy_level": "L1"},
            ],
            "*": [{"action": "generic_step", "agent_role": "doer"}],
        }
    }
    stages = PipelineResolver(domain_pack).resolve("coating")
    assert stages[0].resolved_capability == "coating_adh_check"


def test_stage_resolved_capability_map_and_override():
    stage_default = PipelineStage(action="verify_dft")
    assert stage_default.resolved_capability == "dft_verification"
    stage_override = PipelineStage(action="verify_dft", capability="custom_cap")
    assert stage_override.resolved_capability == "custom_cap"


def test_builtin_fallback_includes_pipeline():
    """DomainPackStore 内置兜底应携带 pipeline 段，供 FormulaAgent/编排复用。"""
    from battery_materials_agent.industrialization.domain_pack_store import DomainPackStore

    data = DomainPackStore.builtin_fallback()
    assert "pipeline" in data
    assert "crystal" in data["pipeline"]
    assert "polymer" in data["pipeline"]
    # 内置兜底可直接被 PipelineResolver 消费
    stages = PipelineResolver(data).resolve("crystal", {"requires_dft": True})
    assert "verify_dft" in [s.action for s in stages]


# ── StageExecutor ────────────────────────────────────────────────


def test_stage_executor_dispatches_native_callable():
    def native_fn(stage, context):
        return {"status": "success", "kind": "native", "value": context.get("n", 0) + 1}

    exe = StageExecutor({"native": native_fn})
    result = _run(exe.execute(PipelineStage(action="x", executor_kind="native"), {"n": 1}))
    assert result["value"] == 2


def test_stage_executor_dispatches_object_execute():
    class ScpAdapter:
        def execute(self, stage, context):
            return {"status": "success", "kind": "scp", "stage": stage.action}

    exe = StageExecutor({"scp": ScpAdapter()})
    result = _run(exe.execute(PipelineStage(action="verify_dft", executor_kind="scp")))
    assert result["kind"] == "scp"
    assert result["stage"] == "verify_dft"


def test_stage_executor_unregistered_kind_returns_error():
    exe = StageExecutor()
    result = _run(exe.execute(PipelineStage(action="x", executor_kind="agent")))
    assert result["status"] == "error"
    assert "未注册" in result["error"]


def test_stage_executor_exception_is_caught():
    def bad_fn(stage, context):
        raise RuntimeError("boom")

    exe = StageExecutor({"native": bad_fn})
    result = _run(exe.execute(PipelineStage(action="x", executor_kind="native")))
    assert result["status"] == "error"
    assert "boom" in result["error"]


# ── HybridOrchestrator._generate_steps ────────────────────────────


def _make_orchestrator(domain_pack=None):
    from battery_materials_agent.hybrid.orchestrator import HybridOrchestrator

    return HybridOrchestrator(
        SimpleNamespace(), SimpleNamespace(), domain_pack=domain_pack
    )


def _intent(material_type="crystal", requires_dft=False):
    return {
        "material_scope": SimpleNamespace(material_type=material_type),
        "risk_assessment": SimpleNamespace(requires_dft=requires_dft),
    }


def test_generate_steps_builtin_crystal_sequences_unregressed():
    orc = _make_orchestrator()
    # requires_dft=True → 5 步含 verify_dft
    steps = orc._generate_steps(_intent("crystal", requires_dft=True), object())
    assert [s.action for s in steps] == [
        "route_material", "generate_crystal_candidates",
        "predict_crystal_properties", "verify_dft", "compliance_check",
    ]
    # requires_dft=False → 4 步，无 verify_dft
    steps_no_dft = orc._generate_steps(_intent("crystal", requires_dft=False), object())
    assert "verify_dft" not in [s.action for s in steps_no_dft]
    assert steps[0].agent_id == "planner"
    assert steps[0].autonomy_level == "L1"
    assert steps[0].required_capabilities == ["material_reference_lookup"]


def test_generate_steps_uses_domain_pack_pipeline():
    domain_pack = {
        "pipeline": {
            "biomaterial": [
                {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
                {"action": "generate_sequence_candidates", "agent_role": "thinker",
                 "autonomy_level": "L0", "executor_kind": "skill"},
                {"action": "compliance_check", "agent_role": "verifier", "autonomy_level": "L2"},
            ]
        }
    }
    orc = _make_orchestrator(domain_pack)
    steps = orc._generate_steps(_intent("biomaterial"), object())
    assert [s.action for s in steps] == [
        "route_material", "generate_sequence_candidates", "compliance_check",
    ]
    # executor_kind 随领域包阶段透传到计划步骤
    assert steps[1].executor_kind == "skill"
    assert steps[0].executor_kind == "native"


# ── 金发科技（kingfa）领域包解析 ───────────────────────────────────


def test_kingfa_domain_pack_pipeline_resolves_polymer():
    """金发科技领域包 polymer 流水线：route→候选→配方→预测→合规。"""
    from battery_materials_agent.hybrid.pipeline import PipelineResolver

    pack = {
        "pipeline": {
            "polymer": [
                {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
                {"action": "generate_polymer_candidates", "agent_role": "thinker", "autonomy_level": "L0"},
                {"action": "design_formula", "agent_role": "doer", "autonomy_level": "L1"},
                {"action": "predict_polymer_properties", "agent_role": "doer", "autonomy_level": "L1"},
                {"action": "compliance_check", "agent_role": "verifier", "autonomy_level": "L2"},
            ]
        }
    }
    stages = PipelineResolver(pack).resolve("polymer")
    assert [s.action for s in stages] == [
        "route_material", "generate_polymer_candidates",
        "design_formula", "predict_polymer_properties", "compliance_check",
    ]
    # 金发场景下配方设计在性能预测之前（先配方后验证）
    formula_idx = [s.action for s in stages].index("design_formula")
    predict_idx = [s.action for s in stages].index("predict_polymer_properties")
    assert formula_idx < predict_idx


def test_generate_steps_selects_domain_pack_by_domain_key():
    """按 request.domain_key 动态选择领域包（battery vs kingfa）。"""
    from battery_materials_agent.hybrid.orchestrator import HybridOrchestrator

    battery_pack = {
        "pipeline": {
            "crystal": [
                {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
                {"action": "generate_crystal_candidates", "agent_role": "thinker", "autonomy_level": "L0"},
                {"action": "compliance_check", "agent_role": "verifier", "autonomy_level": "L2"},
            ]
        }
    }
    kingfa_pack = {
        "pipeline": {
            "polymer": [
                {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
                {"action": "generate_polymer_candidates", "agent_role": "thinker", "autonomy_level": "L0"},
                {"action": "design_formula", "agent_role": "doer", "autonomy_level": "L1"},
                {"action": "compliance_check", "agent_role": "verifier", "autonomy_level": "L2"},
            ]
        }
    }

    def provider(key):
        return {"battery": battery_pack, "kingfa": kingfa_pack}.get(key)

    orc = HybridOrchestrator(
        SimpleNamespace(), SimpleNamespace(),
        domain_pack=battery_pack, domain_pack_provider=provider,
    )
    # 未指定 domain_key → 默认领域包（battery）解析 crystal
    crystal_steps = orc._generate_steps(_intent("crystal"), SimpleNamespace(domain_key=""))
    assert "generate_crystal_candidates" in [s.action for s in crystal_steps]
    # 指定 kingfa → 用金发领域包解析 polymer
    kingfa_steps = orc._generate_steps(_intent("polymer"), SimpleNamespace(domain_key="kingfa"))
    assert [s.action for s in kingfa_steps] == [
        "route_material", "generate_polymer_candidates",
        "design_formula", "compliance_check",
    ]
    # 指定 battery → 用电池领域包解析
    battery_steps = orc._generate_steps(_intent("crystal"), SimpleNamespace(domain_key="battery"))
    assert "generate_crystal_candidates" in [s.action for s in battery_steps]


def test_domain_pack_store_resolves_active_pack_by_key():
    """DomainPackStore.resolve_active_pack 支持按 domain_key 精确解析。"""
    from battery_materials_agent.industrialization.domain_pack_store import DomainPackStore

    store = DomainPackStore()
    # 显式指定不存在的 key → None（不抛错）
    assert store.resolve_active_pack(domain_key="no_such_domain") is None
    # 显式指定 battery → 返回该包（若库中存在）
    battery = store.resolve_active_pack(domain_key="battery")
    if battery is not None:
        assert battery.domain_key == "battery"


# ── StageExecutor 接入 orchestrator 执行路径 ───────────────────────


def test_orchestrator_default_native_executor_resolves_capability():
    """未显式注入执行器时，orchestrator 注册默认 native 执行器解析能力路由。"""
    from battery_materials_agent.hybrid.orchestrator import HybridOrchestrator

    class MockRouter:
        def __init__(self, aliases):
            self._aliases = aliases

        async def resolve(self, capability, profile):
            return [SimpleNamespace(binding_id=a) for a in self._aliases]

    class MockModelRouter:
        def route(self, capability, profile):
            return SimpleNamespace(route_id="route-1")

    orc = HybridOrchestrator(
        MockRouter(["tb_formula"]), MockModelRouter(),
        domain_pack={"pipeline": {"polymer": [
            {"action": "design_formula", "agent_role": "doer", "autonomy_level": "L1"},
        ]}},
    )
    step = orc._generate_steps(_intent("polymer"), SimpleNamespace(domain_key=""))[0]
    result = _run(orc._stage_executor.execute(step, {"scope": "native"}))
    assert result["status"] == "success"
    assert result.get("capability") == "reaction_engineering_check"
    assert result.get("aliases") == ["tb_formula"]
    assert result.get("model_route") == "route-1"


def test_orchestrator_execute_dispatches_and_yields_events():
    """execute() 经 StageExecutor 分派并产出含 executor_kind 的事件。"""
    from battery_materials_agent.hybrid.orchestrator import (
        HybridOrchestrator, ResearchPlan, TaskStepV3,
    )

    class MockRouter:
        async def resolve(self, capability, profile):
            return []

    class MockModelRouter:
        def route(self, capability, profile):
            return None

    orc = HybridOrchestrator(MockRouter(), MockModelRouter())
    plan = ResearchPlan(
        plan_id="plan-1", request_id="req-1", status="draft",
        steps=[TaskStepV3(
            step_id="step_0", agent_id="doer", action="design_formula",
            required_capabilities=["reaction_engineering_check"],
            executor_kind="native", status="pending",
        )],
    )
    events = _collect_async_gen(orc.execute(plan, SimpleNamespace(request_id="req-1")))
    assert events[0]["event_type"] == "plan_start"
    step_start = next(e for e in events if e["event_type"] == "step_start")
    assert step_start["executor_kind"] == "native"
    step_progress = next(e for e in events if e["event_type"] == "step_progress")
    assert "executor_kind" in step_progress
    plan_complete = next(e for e in events if e["event_type"] == "plan_complete")
    assert plan_complete["status"] == "completed"