"""P1-2: 统一 Agent 调用事件日志 + 委员会触发规则引擎测试。

覆盖：AgentEventLog CRUD 与聚合统计、ECML 步骤事件埋点、
合成任务连续失败计数、触发条件B（候选质量审核案件）、
触发条件C（系统健康度告警案件）及去重保护。
"""

import asyncio
import os
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from battery_materials_agent.agent import BatteryMaterialsAgent
from battery_materials_agent.agent_team.event_log import AgentEventLog
from battery_materials_agent.committee.enums import (
    CaseStatus,
    CommitteeType,
    TriggerCode,
)
from battery_materials_agent.committee.event_store import CommitteeEventStore
from battery_materials_agent.committee.repository import CommitteeRepository
from tests.conftest import attach_test_auth
from battery_materials_agent.committee.triggers import (
    SYNTHESIS_FAILURE_STREAK_THRESHOLD,
    trigger_candidate_quality_case,
    trigger_synthesis_health_case,
)
from battery_materials_agent.config import AgentConfig
from battery_materials_agent.synthesis.task_store import SynthesisTaskStore


# ── AgentEventLog ─────────────────────────────────────────────

@pytest.fixture
def event_log(tmp_path):
    log = AgentEventLog(db_path=str(tmp_path / "agent_events.db"))
    # 迁移至 PostgreSQL 后所有测试共享同一数据库，需在每条测试前清理 agent_events
    from sqlalchemy import text
    with log.engine.begin() as conn:
        conn.execute(text("DELETE FROM agent_team.agent_events"))
    return log


@pytest.fixture(autouse=True)
def _cleanup_agent_events():
    """每个测试结束后清理 agent_events，避免跨测试数据污染。"""
    yield
    from sqlalchemy import text
    from battery_materials_agent.db import get_engine
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM agent_team.agent_events"))


class TestAgentEventLog:
    def test_log_and_list(self, event_log):
        eid = event_log.log_event(
            agent_id="builtin_material_router",
            agent_name="材料路由调度员",
            related_run_id="run-1",
            step="step1_route",
            input_summary={"target": "LiCoO2"},
            output_summary={"candidates": 3},
            duration_ms=42,
            status="success",
        )
        assert eid
        events = event_log.list_events()
        assert len(events) == 1
        ev = events[0]
        assert ev["event_id"] == eid
        assert ev["agent_id"] == "builtin_material_router"
        assert ev["related_run_id"] == "run-1"
        assert ev["input_summary"] == {"target": "LiCoO2"}
        assert ev["output_summary"] == {"candidates": 3}
        assert ev["duration_ms"] == 42
        assert ev["status"] == "success"

    def test_list_filters(self, event_log):
        event_log.log_event(agent_id="a1", related_run_id="r1", step="s1")
        event_log.log_event(agent_id="a2", related_run_id="r1", step="s2")
        event_log.log_event(agent_id="a1", related_run_id="r2", step="s1")
        assert len(event_log.list_events(run_id="r1")) == 2
        assert len(event_log.list_events(agent_id="a1")) == 2
        assert len(event_log.list_events(run_id="r1", agent_id="a1")) == 1
        assert len(event_log.list_events(run_id="nonexistent")) == 0

    def test_stats_by_agent(self, event_log):
        for _ in range(3):
            event_log.log_event(agent_id="a1", agent_name="Agent1", status="success", duration_ms=100)
        event_log.log_event(agent_id="a1", agent_name="Agent1", status="failed", duration_ms=200)
        event_log.log_event(agent_id="a2", agent_name="Agent2", status="timeout", duration_ms=50)

        stats = event_log.stats_by_agent()
        assert set(stats.keys()) == {"a1", "a2"}
        s1 = stats["a1"]
        assert s1["invocations"] == 4
        assert s1["succeeded"] == 3
        assert s1["failed"] == 1
        assert s1["success_rate"] == 0.75
        assert s1["avg_duration_ms"] == 125
        assert s1["last_invoked_at"]
        assert stats["a2"]["success_rate"] == 0.0

    def test_stats_empty(self, event_log):
        assert event_log.stats_by_agent() == {}


# ── ECML 步骤事件埋点 ─────────────────────────────────────────

class TestECMLStepEventLogging:
    @pytest.fixture
    def engine(self, tmp_path):
        config = AgentConfig(data_dir=os.path.join(str(tmp_path), "data"))
        os.makedirs(config.data_dir, exist_ok=True)
        agent = BatteryMaterialsAgent(config)
        return agent.ecml

    def test_step_success_logged(self, engine, tmp_path):
        log = AgentEventLog(db_path=str(tmp_path / "events.db"))
        engine._agent_event_log = log
        state = engine._create_new_state("", "ionic_conductivity", 1)
        state = engine._run_step_with_event(
            state, "step1_route", {"target": "LiCoO2"}, engine._step1_route, "LiCoO2"
        )
        events = log.list_events(run_id=state.run_id)
        assert len(events) == 1
        assert events[0]["agent_id"] == "builtin_material_router"
        assert events[0]["agent_name"] == "材料路由调度员"
        assert events[0]["step"] == "step1_route"
        assert events[0]["status"] == "success"
        assert events[0]["duration_ms"] >= 0

    def test_step_failure_logged_and_reraised(self, engine, tmp_path):
        log = AgentEventLog(db_path=str(tmp_path / "events.db"))
        engine._agent_event_log = log
        state = engine._create_new_state("", "ionic_conductivity", 1)

        def _boom(state):
            raise RuntimeError("step exploded")

        with pytest.raises(RuntimeError, match="step exploded"):
            engine._run_step_with_event(state, "step2_generate", {}, _boom)
        events = log.list_events()
        assert len(events) == 1
        assert events[0]["status"] == "failed"
        assert events[0]["agent_id"] == "builtin_material_discovery"

    def test_no_log_when_not_injected(self, engine):
        """未注入事件日志时埋点为静默空操作，不影响步骤执行。"""
        engine._agent_event_log = None
        state = engine._create_new_state("", "ionic_conductivity", 1)
        state = engine._run_step_with_event(
            state, "step1_route", {"target": "Li3PS4"}, engine._step1_route, "Li3PS4"
        )
        assert state.target  # 步骤正常执行


# ── 合成任务连续失败计数 ──────────────────────────────────────

class TestConsecutiveFailures:
    @pytest.fixture
    def store(self, tmp_path):
        s = SynthesisTaskStore(db_path=str(tmp_path / "synthesis.db"))
        # 迁移至 PostgreSQL 后所有测试共享同一数据库，需在每条测试前清理 synthesis_tasks
        from sqlalchemy import text
        with s.engine.begin() as conn:
            conn.execute(text("DELETE FROM synthesis.synthesis_tasks"))
        return s

    def teardown_method(self):
        """测试结束清理 synthesis_tasks，避免跨测试数据污染。"""
        from sqlalchemy import text
        from battery_materials_agent.db import get_engine
        with get_engine().begin() as conn:
            conn.execute(text("DELETE FROM synthesis.synthesis_tasks"))

    def test_empty_store(self, store):
        assert store.count_consecutive_failures() == 0

    def test_all_failures(self, store):
        for _ in range(4):
            tid = store.create_task("CCO")
            store.fail_task(tid, "err", 10)
        assert store.count_consecutive_failures() == 4

    def test_streak_broken_by_success(self, store):
        t1 = store.create_task("CCO")
        store.fail_task(t1, "err", 10)
        t2 = store.create_task("CCO")
        store.complete_task(t2, {"count": 1}, 10)
        t3 = store.create_task("CCO")
        store.fail_task(t3, "err", 10)
        t4 = store.create_task("CCO")
        store.fail_task(t4, "err", 10)
        assert store.count_consecutive_failures() == 2

    def test_running_task_skipped(self, store):
        t1 = store.create_task("CCO")
        store.fail_task(t1, "err", 10)
        store.create_task("CCC")  # pending，不计入也不中断
        assert store.count_consecutive_failures() == 1


# ── 委员会触发规则引擎 ────────────────────────────────────────

@pytest.fixture
def coordinator(tmp_path):
    """轻量 coordinator stub：triggers 仅依赖 repository 与 event_store。"""
    repo = CommitteeRepository(db_path=str(tmp_path / "committee.db"))
    event_store = CommitteeEventStore(db_path=str(tmp_path / "committee_events.db"))
    # 迁移至 PostgreSQL 后所有测试共享同一数据库，需在每条测试前清理 committee 表
    _cleanup_committee_tables(repo.engine)
    return SimpleNamespace(
        repository=repo,
        event_store=event_store,
    )


@pytest.fixture(autouse=True)
def _cleanup_committee_cases():
    """每个测试结束清理 committee_cases，避免去重保护误命中。"""
    yield
    from battery_materials_agent.db import get_engine
    _cleanup_committee_tables(get_engine())


def _cleanup_committee_tables(engine) -> None:
    """按 FK 依赖顺序清理 committee 相关表。"""
    from sqlalchemy import text
    with engine.begin() as conn:
        # release_cards 引用了 committee_cases.case_id，需先清理
        conn.execute(text("DELETE FROM release_card.release_cards"))
        # 先清理依赖 committee_cases 的子表
        conn.execute(text("DELETE FROM committee.committee_verdicts"))
        conn.execute(text("DELETE FROM committee.committee_evidence"))
        conn.execute(text("DELETE FROM committee.committee_proposals"))
        conn.execute(text("DELETE FROM committee.committee_events"))
        # 最后清理 committee_cases
        conn.execute(text("DELETE FROM committee.committee_cases"))


class TestTriggerCandidateQuality:
    def test_case_created(self, coordinator):
        blocked = [
            {"name": "Ac-变体A", "quality_issues": ["化学式异常：仅含单一元素"]},
            {"name": "Ca(H8O5", "quality_issues": ["化学式异常：括号不匹配"]},
        ]
        case_id = trigger_candidate_quality_case(coordinator, "run-1", blocked)
        assert case_id
        case = coordinator.repository.get_case(case_id)
        assert case.committee_type == CommitteeType.CANDIDATE_QUALITY
        assert case.trigger_code == TriggerCode.CANDIDATE_QUALITY_INVALID.value
        assert case.ecml_run_id == "run-1"
        assert case.status == CaseStatus.PENDING

    def test_dedup_same_run(self, coordinator):
        blocked = [{"name": "Ac", "quality_issues": ["单元素"]}]
        first = trigger_candidate_quality_case(coordinator, "run-1", blocked)
        second = trigger_candidate_quality_case(coordinator, "run-1", blocked)
        assert first is not None
        assert second is None  # 同 run 未结案案件去重

    def test_different_run_not_deduped(self, coordinator):
        blocked = [{"name": "Ac", "quality_issues": ["单元素"]}]
        first = trigger_candidate_quality_case(coordinator, "run-1", blocked)
        second = trigger_candidate_quality_case(coordinator, "run-2", blocked)
        assert first is not None and second is not None

    def test_empty_blocked_no_case(self, coordinator):
        assert trigger_candidate_quality_case(coordinator, "run-1", []) is None

    def test_closed_case_allows_new(self, coordinator):
        blocked = [{"name": "Ac", "quality_issues": ["单元素"]}]
        first = trigger_candidate_quality_case(coordinator, "run-1", blocked)
        coordinator.repository.update_case_status(first, CaseStatus.PASS)
        second = trigger_candidate_quality_case(coordinator, "run-1", blocked)
        assert second is not None  # 已结案后可再次触发


class TestTriggerSynthesisHealth:
    def test_below_threshold_no_case(self, coordinator):
        assert trigger_synthesis_health_case(
            coordinator, SYNTHESIS_FAILURE_STREAK_THRESHOLD - 1, "err"
        ) is None

    def test_case_created_at_threshold(self, coordinator):
        case_id = trigger_synthesis_health_case(
            coordinator, SYNTHESIS_FAILURE_STREAK_THRESHOLD, "服务不可用"
        )
        assert case_id
        case = coordinator.repository.get_case(case_id)
        assert case.committee_type == CommitteeType.SYSTEM_HEALTH
        assert case.trigger_code == TriggerCode.SYNTHESIS_SERVICE_FAILURE.value

    def test_dedup_open_health_case(self, coordinator):
        first = trigger_synthesis_health_case(coordinator, 5, "err")
        second = trigger_synthesis_health_case(coordinator, 6, "err")
        assert first is not None
        assert second is None  # 全局仅一个未结案健康告警


# ── API 端点 ─────────────────────────────────────────────────

@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(data_dir=os.path.join(tmpdir, "data"))
        os.makedirs(config.data_dir, exist_ok=True)
        agent = BatteryMaterialsAgent(config)

        from battery_materials_agent.api import app
        app.dependency_overrides = {}
        # 阻止真实 startup 重初始化事件日志到项目真实 DB（会造成测试间相互污染）；
        # 保存并在测试结束后恢复处理器，避免影响同会话其他测试文件
        saved_startup = list(app.router.on_startup)
        app.router.on_startup.clear()

        import battery_materials_agent.api as api_module
        api_module.agent = agent
        # 隔离事件日志到临时目录
        from battery_materials_agent.agent_team.event_log import AgentEventLog
        api_module._agent_event_log = AgentEventLog(
            db_path=os.path.join(tmpdir, "agent_events.db")
        )
        # 迁移至 PostgreSQL 后所有测试共享同一数据库，client fixture 也需清理
        from sqlalchemy import text
        with api_module._agent_event_log.engine.begin() as conn:
            conn.execute(text("DELETE FROM agent_team.agent_events"))
        # ECML state_store 默认指向项目真实 DB，一并隔离
        from battery_materials_agent.ecml.ecml_engine import ECMLStateStore
        agent.ecml.state_store = ECMLStateStore(
            db_path=os.path.join(tmpdir, "ecml_states.db")
        )
        with agent.ecml.state_store.engine.begin() as conn:
            conn.execute(text("DELETE FROM ecml.ecml_runs_index"))
            conn.execute(text("DELETE FROM ecml.ecml_runs"))
        from battery_materials_agent.synthesis.task_store import SynthesisTaskStore
        app.state.synthesis_task_store = SynthesisTaskStore(
            db_path=os.path.join(tmpdir, "synthesis_tasks.db")
        )

        headers = attach_test_auth(app)
        with TestClient(app, headers=headers) as c:
            yield c
        app.router.on_startup[:] = saved_startup
        app.state.synthesis_task_store = None
        api_module._agent_event_log = None


class TestAgentEventsAPI:
    def test_events_empty_initially(self, client):
        resp = client.get("/agent-events")
        assert resp.status_code == 200
        assert resp.json() == {"events": [], "count": 0}

    def test_stats_empty_initially(self, client):
        resp = client.get("/agent-events/stats")
        assert resp.status_code == 200
        assert resp.json() == {"stats": {}}

    def test_synthesis_task_writes_agent_event(self, client):
        """合成规划任务结束后必须写入一条合成路线规划师的调用事件。"""
        with patch(
            "battery_materials_agent.api._probe_askcos", new=AsyncMock(return_value=False)
        ):
            resp = client.post("/synthesis/plan/async", json={"smiles": "CCO"})
            task_id = resp.json()["task_id"]
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                task = client.get(f"/synthesis/tasks/{task_id}").json()
                if task["status"] in ("success", "failed"):
                    break
                time.sleep(0.1)
            events = client.get("/agent-events").json()["events"]
            assert len(events) >= 1
            ev = events[0]
            assert ev["agent_id"] == "builtin_synthesis_planner"
            assert ev["step"] == "synthesis_plan"
            assert ev["status"] == "failed"  # ASKCOS 不可达 → 失败事件
            assert ev["input_summary"]["smiles"] == "CCO"

    def test_stats_after_events(self, client):
        import battery_materials_agent.api as api_module
        api_module._agent_event_log.log_event(
            agent_id="builtin_dft_verifier", agent_name="DFT 计算专家", status="success",
        )
        stats = client.get("/agent-events/stats").json()["stats"]
        assert "builtin_dft_verifier" in stats
        assert stats["builtin_dft_verifier"]["invocations"] == 1
