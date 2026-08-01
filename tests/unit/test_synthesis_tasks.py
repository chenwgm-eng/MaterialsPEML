"""P0-2: 异步合成规划任务测试。

覆盖：任务存储 CRUD 与统计、异步提交/轮询 API、失败尝试持久化、
手动填写路线兜底、服务健康探测端点。
"""

import asyncio
import os
import tempfile
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from battery_materials_agent.agent import BatteryMaterialsAgent
from battery_materials_agent.config import AgentConfig
from battery_materials_agent.synthesis.task_store import SynthesisTaskStore


@pytest.fixture
def store(tmp_path):
    s = SynthesisTaskStore(db_path=str(tmp_path / "synthesis_tasks.db"))
    # 迁移至 PostgreSQL 后所有测试共享同一数据库，需在每条测试前清理 synthesis_tasks
    with s.engine.begin() as conn:
        conn.execute(text("DELETE FROM synthesis.synthesis_tasks"))
    return s


@pytest.fixture(autouse=True)
def _cleanup_synthesis_tasks():
    """每个测试结束后清理 synthesis_tasks，避免跨测试数据污染。"""
    yield
    from battery_materials_agent.db import get_engine
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM synthesis.synthesis_tasks"))


class TestSynthesisTaskStore:
    def test_create_and_get(self, store):
        tid = store.create_task("CCO", num_routes=3)
        task = store.get_task(tid)
        assert task is not None
        assert task["smiles"] == "CCO"
        assert task["status"] == "pending"
        assert task["source"] == "auto"

    def test_complete_task_and_stats(self, store):
        tid = store.create_task("CCO")
        store.complete_task(tid, {"routes": [{"route_id": "R1"}], "count": 1}, 1234)
        task = store.get_task(tid)
        assert task["status"] == "success"
        assert task["result"]["count"] == 1
        assert task["duration_ms"] == 1234

        stats = store.get_stats()
        assert stats["total_tasks"] == 1
        assert stats["success_tasks"] == 1
        assert stats["routes_generated"] == 1
        assert stats["success_rate"] == 1.0

    def test_fail_task_and_stats(self, store):
        tid = store.create_task("CCO")
        store.fail_task(tid, "服务不可用", 500)
        task = store.get_task(tid)
        assert task["status"] == "failed"
        assert "服务不可用" in task["error"]

        stats = store.get_stats()
        assert stats["failed_tasks"] == 1
        assert stats["success_rate"] == 0.0
        assert stats["routes_generated"] == 0

    def test_failed_attempts_are_recorded(self, store):
        """失败尝试必须被持久化（评审要求：失败也应计入统计而非静默）。"""
        for _ in range(3):
            tid = store.create_task("CCO")
            store.fail_task(tid, "timeout", 15000)
        stats = store.get_stats()
        assert stats["total_tasks"] == 3
        assert stats["failed_tasks"] == 3

    def test_list_tasks_order(self, store):
        t1 = store.create_task("CCO")
        t2 = store.create_task("CCC")
        tasks = store.list_tasks()
        assert len(tasks) == 2
        # 最新创建的在前面
        assert tasks[0]["task_id"] == t2
        assert tasks[1]["task_id"] == t1

    def test_get_missing_returns_none(self, store):
        assert store.get_task("nonexistent") is None

    def test_stats_empty(self, store):
        stats = store.get_stats()
        assert stats["total_tasks"] == 0
        assert stats["success_rate"] is None  # 无任务时不展示告警

    def test_corrupt_result_json_tolerated(self, store):
        tid = store.create_task("CCO")
        store.complete_task(tid, {"count": 2}, 10)
        # 模拟异常 result_json：直接置 NULL（PostgreSQL JSONB 不允许写入损坏 JSON，
        # 但 get_stats 仍需对 None / 非 dict 类型容错，不应崩溃）
        from sqlalchemy import text
        with store.engine.begin() as conn:
            conn.execute(
                text("UPDATE synthesis.synthesis_tasks SET result_json=NULL WHERE task_id=:tid"),
                {"tid": tid},
            )
        stats = store.get_stats()
        assert stats["total_tasks"] >= 1


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(data_dir=os.path.join(tmpdir, "data"))
        os.makedirs(config.data_dir, exist_ok=True)
        agent = BatteryMaterialsAgent(config)

        from battery_materials_agent.api import app
        app.dependency_overrides = {}

        @app.on_event("startup")
        async def override_startup():
            pass

        import battery_materials_agent.api as api_module
        api_module.agent = agent
        # 隔离任务存储到临时目录
        from battery_materials_agent.synthesis.task_store import SynthesisTaskStore
        app.state.synthesis_task_store = SynthesisTaskStore(
            db_path=os.path.join(tmpdir, "synthesis_tasks.db")
        )

        with TestClient(app) as c:
            yield c
        app.state.synthesis_task_store = None


def _wait_task_done(client, task_id, timeout=10.0):
    """轮询任务直到终态。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = client.get(f"/synthesis/tasks/{task_id}").json()
        if task["status"] in ("success", "failed"):
            return task
        time.sleep(0.1)
    raise AssertionError(f"task {task_id} did not finish within {timeout}s")


class TestSynthesisAsyncAPI:
    def test_submit_async_returns_task_id_immediately(self, client):
        with patch(
            "battery_materials_agent.api._probe_askcos", new=AsyncMock(return_value=False)
        ):
            resp = client.post("/synthesis/plan/async", json={"smiles": "CCO"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["task_id"]
            assert data["status"] == "pending"

    def test_task_fails_fast_when_service_down(self, client):
        """服务不可达时任务快速失败，且失败尝试被持久化。"""
        with patch(
            "battery_materials_agent.api._probe_askcos", new=AsyncMock(return_value=False)
        ):
            resp = client.post("/synthesis/plan/async", json={"smiles": "CCO"})
            task_id = resp.json()["task_id"]
            task = _wait_task_done(client, task_id)
            assert task["status"] == "failed"
            assert "无法连接" in task["error"]

            stats = client.get("/synthesis/stats").json()
            # stats 端点会再次探测服务（已被 patch 出上下文，真实探测），仅校验失败计数
            assert stats["failed_tasks"] >= 1
            assert stats["total_tasks"] >= 1

    def test_task_success_path(self, client):
        fake_routes = [{
            "route_id": "R1", "target_smiles": "CCO", "steps": [],
            "feasibility_score": 0.8, "step_count": 1, "confidence": 0.8,
            "reactants": ["CC"], "conditions": [], "is_feasible": True,
            "overall_score": 0.8, "estimated_cost": 1.0,
        }]
        # plan_multiple_routes 真实返回 dict（含 routes/count/best_route），mock 需保持一致
        fake_result = {"routes": fake_routes, "count": 1, "best_route": fake_routes[0]}
        import battery_materials_agent.api as api_module
        with patch(
            "battery_materials_agent.api._probe_askcos", new=AsyncMock(return_value=True)
        ), patch.object(
            api_module.agent.synthesis_planner,
            "plan_multiple_routes",
            new=AsyncMock(return_value=fake_result),
        ):
            resp = client.post("/synthesis/plan/async", json={"smiles": "CCO", "num_routes": 3})
            task_id = resp.json()["task_id"]
            task = _wait_task_done(client, task_id)
            assert task["status"] == "success"
            assert task["result"]["count"] == 1
            assert task["result"]["best_route"]["route_id"] == "R1"

    def test_empty_smiles_rejected(self, client):
        resp = client.post("/synthesis/plan/async", json={"smiles": "  "})
        assert resp.status_code == 400

    def test_get_missing_task_404(self, client):
        resp = client.get("/synthesis/tasks/nonexistent-id")
        assert resp.status_code == 404

    def test_manual_route_fallback(self, client):
        """手动填写路线兜底：校验、持久化、计入统计。"""
        resp = client.post("/synthesis/manual", json={
            "smiles": "CCO",
            "steps": [
                {"reactants": ["CC=O", "[H][H]"], "conditions": "NaBH4, MeOH", "score": 0.7},
            ],
            "note": "服务不可用，手动登记",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        route = data["result"]["best_route"]
        assert route["reaction_type"] if "reaction_type" in route else True
        assert route["steps"][0]["reactants"] == ["CC=O", "[H][H]"]
        assert route["steps"][0]["reaction_smiles"].endswith(">>CCO")

        stats = client.get("/synthesis/stats").json()
        assert stats["success_tasks"] >= 1
        assert stats["routes_generated"] >= 1

    def test_manual_route_validation(self, client):
        # 空步骤
        resp = client.post("/synthesis/manual", json={"smiles": "CCO", "steps": []})
        assert resp.status_code == 400
        # 空反应物
        resp = client.post(
            "/synthesis/manual",
            json={"smiles": "CCO", "steps": [{"reactants": ["  "]}]},
        )
        assert resp.status_code == 400
        # 空 SMILES
        resp = client.post(
            "/synthesis/manual",
            json={"smiles": "", "steps": [{"reactants": ["CC"]}]},
        )
        assert resp.status_code == 400

    def test_health_endpoint_shape(self, client):
        with patch(
            "battery_materials_agent.api._probe_askcos", new=AsyncMock(return_value=False)
        ):
            resp = client.get("/synthesis/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["service"] == "ASKCOS"
            assert data["available"] is False
            assert "base_url" in data
