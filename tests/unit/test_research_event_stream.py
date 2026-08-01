"""P3-1：统一研发事件流水表测试。

覆盖：ResearchEventStream CRUD 与过滤、run_source 数据隔离、stats 聚合、
delete_by_run_id 联动清理、API 端点（/research-events、/research-events/stats）、
业务埋点（材料发现/合成任务/实验任务单写入事件、ECML 运行删除联动清理）。
"""

import os
import tempfile
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from battery_materials_agent.agent import BatteryMaterialsAgent
from battery_materials_agent.agent_team.research_event_stream import (
    EVENT_TYPE_LABELS,
    ResearchEventStream,
)
from battery_materials_agent.config import AgentConfig


# ── ResearchEventStream ─────────────────────────────────────

@pytest.fixture
def stream(tmp_path):
    s = ResearchEventStream(db_path=str(tmp_path / "research_events.db"))
    # 迁移至 PostgreSQL 后所有测试共享同一数据库，需在每条测试前清理 research_events
    from sqlalchemy import text
    with s.engine.begin() as conn:
        conn.execute(text("DELETE FROM agent_team.research_events"))
    return s


@pytest.fixture(autouse=True)
def _cleanup_research_events():
    """每个测试结束后清理 research_events，避免跨测试数据污染。"""
    yield
    from sqlalchemy import text
    from battery_materials_agent.db import get_engine
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM agent_team.research_events"))


class TestResearchEventStream:
    def test_log_and_list(self, stream):
        eid = stream.log_event(
            event_type="discovery",
            title="晶体材料发现：Li,La",
            summary="目标属性 ionic_conductivity，生成候选 5 个",
            payload={"count": 5},
        )
        assert eid
        events = stream.list_events()
        assert len(events) == 1
        ev = events[0]
        assert ev["event_id"] == eid
        assert ev["event_type"] == "discovery"
        assert ev["event_type_label"] == "材料发现"
        assert ev["title"] == "晶体材料发现：Li,La"
        assert ev["payload"] == {"count": 5}
        assert ev["run_source"] == "production"
        assert ev["created_at"]

    def test_list_filters(self, stream):
        stream.log_event(event_type="discovery", run_id="r1", title="发现A")
        stream.log_event(event_type="synthesis", run_id="r1", title="合成A")
        stream.log_event(event_type="discovery", run_id="r2", title="发现B")
        assert len(stream.list_events(event_type="discovery")) == 2
        assert len(stream.list_events(run_id="r1")) == 2
        assert len(stream.list_events(event_type="discovery", run_id="r2")) == 1
        assert len(stream.list_events(event_type="nonexistent")) == 0

    def test_run_source_isolation(self, stream):
        """默认查询仅返回 production；run_source='' 返回全部（治理页口径）。"""
        stream.log_event(event_type="ecml_run", run_id="r1", title="正式运行")
        stream.log_event(event_type="ecml_run", run_id="r2", title="测试运行", run_source="test")
        production = stream.list_events()
        assert len(production) == 1
        assert production[0]["run_id"] == "r1"
        all_events = stream.list_events(run_source="")
        assert len(all_events) == 2

    def test_stats(self, stream):
        stream.log_event(event_type="discovery", status="success")
        stream.log_event(event_type="discovery", status="success")
        stream.log_event(event_type="discovery", status="failed")
        stream.log_event(event_type="synthesis", status="failed")
        stream.log_event(event_type="ecml_run", status="success", run_source="test")

        stats = stream.stats()
        assert stats["by_type"]["discovery"] == {"total": 3, "succeeded": 2, "failed": 1}
        assert stats["by_type"]["synthesis"] == {"total": 1, "succeeded": 0, "failed": 1}
        # test 数据不计入 by_type，单独计数
        assert "ecml_run" not in stats["by_type"]
        assert stats["test_total"] == 1

    def test_stats_empty(self, stream):
        assert stream.stats() == {"by_type": {}, "test_total": 0}

    def test_delete_by_run_id(self, stream):
        stream.log_event(event_type="ecml_run", run_id="r1", title="运行")
        stream.log_event(event_type="synthesis", run_id="t1", title="合成")
        assert stream.delete_by_run_id("r1") == 1
        assert stream.delete_by_run_id("r1") == 0  # 幂等
        remaining = stream.list_events(run_source="")
        assert len(remaining) == 1
        assert remaining[0]["run_id"] == "t1"

    def test_event_type_labels_cover_all_types(self):
        assert set(EVENT_TYPE_LABELS) == {
            "ecml_run", "discovery", "prediction", "synthesis", "experiment",
        }

    def test_limit_respected(self, stream):
        for i in range(10):
            stream.log_event(event_type="discovery", title=f"发现{i}")
        assert len(stream.list_events(limit=3)) == 3


# ── API 端点与业务埋点 ──────────────────────────────────────

@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(data_dir=os.path.join(tmpdir, "data"))
        os.makedirs(config.data_dir, exist_ok=True)
        agent = BatteryMaterialsAgent(config)

        from battery_materials_agent.api import app
        app.dependency_overrides = {}
        # 阻止真实 startup 重初始化事件流到项目真实 DB（会造成测试间相互污染）；
        # 保存并在测试结束后恢复处理器，避免影响同会话其他测试文件
        saved_startup = list(app.router.on_startup)
        app.router.on_startup.clear()

        import battery_materials_agent.api as api_module
        api_module.agent = agent
        api_module._research_event_stream = ResearchEventStream(
            db_path=os.path.join(tmpdir, "research_events.db")
        )
        # 迁移至 PostgreSQL 后所有测试共享同一数据库，client fixture 也需清理
        from sqlalchemy import text
        with api_module._research_event_stream.engine.begin() as conn:
            conn.execute(text("DELETE FROM agent_team.research_events"))
        # ECML state_store 默认指向项目真实 DB，隔离到临时目录避免污染
        from battery_materials_agent.ecml.ecml_engine import ECMLStateStore
        agent.ecml.state_store = ECMLStateStore(
            db_path=os.path.join(tmpdir, "ecml_states.db")
        )
        # 清理 ECML 运行历史，避免 list_runs 污染
        with agent.ecml.state_store.engine.begin() as conn:
            conn.execute(text("DELETE FROM ecml.ecml_runs"))
            conn.execute(text("DELETE FROM ecml.ecml_runs_index"))
        from battery_materials_agent.synthesis.task_store import SynthesisTaskStore
        app.state.synthesis_task_store = SynthesisTaskStore(
            db_path=os.path.join(tmpdir, "synthesis_tasks.db")
        )
        # startup 被跳过后，端点依赖的 candidate_store 需手动挂载
        app.state.candidate_store = agent.candidate_store

        with TestClient(app) as c:
            yield c
        app.router.on_startup[:] = saved_startup
        app.state.synthesis_task_store = None
        api_module._research_event_stream = None


class TestResearchEventsAPI:
    def test_events_empty_initially(self, client):
        resp = client.get("/research-events")
        assert resp.status_code == 200
        assert resp.json() == {"events": [], "count": 0}

    def test_stats_empty_initially(self, client):
        resp = client.get("/research-events/stats")
        assert resp.status_code == 200
        assert resp.json() == {"by_type": {}, "test_total": 0}

    def test_discover_crystal_writes_discovery_event(self, client):
        resp = client.post("/discover/crystal", json={
            "elements": ["Li", "La"], "target_property": "ionic_conductivity",
            "num_candidates": 2,
        })
        assert resp.status_code == 200
        events = client.get("/research-events").json()["events"]
        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"] == "discovery"
        assert "晶体材料发现" in ev["title"]
        assert ev["payload"]["material_kind"] == "crystal"
        assert ev["payload"]["elements"] == ["Li", "La"]

    def test_experiment_order_writes_experiment_event(self, client):
        # PostgreSQL 强外键约束：创建实验任务单前需先确保 project 和 candidate 存在
        from battery_materials_agent.db import get_engine
        from sqlalchemy import text
        with get_engine().begin() as conn:
            existing = conn.execute(
                text("SELECT 1 FROM projects.projects WHERE project_id=:pid"),
                {"pid": "proj-1"},
            ).first()
            if not existing:
                conn.execute(
                    text("""INSERT INTO projects.projects
                        (project_id, name, owner, created_at, updated_at)
                        VALUES (:pid, :name, :owner, NOW(), NOW())"""),
                    {"pid": "proj-1", "name": "Test Project", "owner": "test"},
                )
            existing_cand = conn.execute(
                text("SELECT 1 FROM experiment.candidates WHERE candidate_id=:cid"),
                {"cid": "Li3PS4"},
            ).first()
            if not existing_cand:
                conn.execute(
                    text("""INSERT INTO experiment.candidates
                        (candidate_id, candidate_type, name, created_at)
                        VALUES (:cid, 'crystal', :name, NOW())"""),
                    {"cid": "Li3PS4", "name": "Li3PS4"},
                )
        resp = client.post("/experiments/orders", json={
            "project_id": "proj-1", "candidate_id": "Li3PS4",
        })
        assert resp.status_code == 200
        order_id = resp.json()["order_id"]
        events = client.get("/research-events", params={"event_type": "experiment"}).json()["events"]
        assert len(events) == 1
        ev = events[0]
        assert ev["run_id"] == order_id
        assert ev["status"] == "running"
        assert ev["payload"]["candidate_id"] == "Li3PS4"

    def test_synthesis_task_writes_event(self, client):
        """合成任务结束后必须写入一条 synthesis 研发事件。"""
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
            events = client.get(
                "/research-events", params={"event_type": "synthesis"}
            ).json()["events"]
            assert len(events) >= 1
            ev = events[0]
            assert ev["run_id"] == task_id
            assert ev["status"] == "failed"  # ASKCOS 不可达 → 失败事件
            assert ev["payload"]["smiles"] == "CCO"

    def test_include_test_filter(self, client):
        import battery_materials_agent.api as api_module
        api_module._research_event_stream.log_event(
            event_type="ecml_run", run_id="r-prod", title="正式",
        )
        api_module._research_event_stream.log_event(
            event_type="ecml_run", run_id="r-test", title="测试", run_source="test",
        )
        # 默认排除 test
        events = client.get("/research-events").json()["events"]
        assert {e["run_id"] for e in events} == {"r-prod"}
        # include_test=true 返回全部
        all_events = client.get(
            "/research-events", params={"include_test": True}
        ).json()["events"]
        assert {e["run_id"] for e in all_events} == {"r-prod", "r-test"}

    def test_delete_ecml_run_cleans_events(self, client):
        """删除 ECML 运行必须联动清理研发事件流水中的关联事件。"""
        import battery_materials_agent.api as api_module
        # 先造一个 ECML 运行（直接写 state_store）
        api_module.agent.ecml.run("Li3PS4 固态电解质", "ionic_conductivity", 1)
        runs = api_module.agent.ecml.state_store.list_runs(limit=5)
        assert len(runs) == 1
        run_id = runs[0]["run_id"]
        api_module._research_event_stream.log_event(
            event_type="ecml_run", run_id=run_id, title="闭环迭代",
        )
        assert client.get("/research-events").json()["count"] == 1
        resp = client.delete(f"/ecml/runs/{run_id}")
        assert resp.status_code == 200
        assert client.get("/research-events").json()["count"] == 0

    def test_stats_after_events(self, client):
        import battery_materials_agent.api as api_module
        api_module._research_event_stream.log_event(event_type="discovery")
        api_module._research_event_stream.log_event(event_type="synthesis", status="failed")
        stats = client.get("/research-events/stats").json()
        assert stats["by_type"]["discovery"]["total"] == 1
        assert stats["by_type"]["synthesis"]["failed"] == 1
