"""P0-4 test 垃圾数据隔离 与 P0-1 首页 KPI 统一口径 的单元测试。"""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from battery_materials_agent.ecml.ecml_engine import ECMLState, ECMLStateStore
from battery_materials_agent.auth.user_store import UserRole
from tests.conftest import attach_test_auth


@pytest.fixture
def store(tmp_path):
    s = ECMLStateStore(db_path=str(tmp_path / "ecml_states.db"))
    # 迁移至 PostgreSQL 后所有测试共享同一数据库，需在每条测试前清理 ecml_runs
    with s.engine.begin() as conn:
        conn.execute(text("DELETE FROM ecml.ecml_runs_index"))
        conn.execute(text("DELETE FROM ecml.ecml_runs"))
    return s


@pytest.fixture(autouse=True)
def _cleanup_ecml_runs():
    """每个测试结束后清理 ecml_runs，避免跨测试数据污染。"""
    yield
    from battery_materials_agent.db import get_engine
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM ecml.ecml_runs_index"))
        conn.execute(text("DELETE FROM ecml.ecml_runs"))


def _save_run(store, run_id, target, is_complete=True, status="completed", updated_at=None, project_id=""):
    state = ECMLState(
        run_id=run_id,
        target=target,
        target_property="ionic_conductivity",
        is_complete=is_complete,
        status=status,
        iteration=1,
        project_id=project_id,
    )
    store.save(run_id, target, "ionic_conductivity", state)
    if updated_at is not None:
        with store.engine.begin() as conn:
            conn.execute(
                text("UPDATE ecml.ecml_runs SET updated_at=:updated_at WHERE run_id=:run_id"),
                {"updated_at": updated_at, "run_id": run_id},
            )


class TestRunSourceInference:
    @pytest.mark.parametrize("target", ["test", "Test", "test1", "test_2", "demo", "debug", "tmp", "abc", "123", ""])
    def test_test_targets(self, target):
        assert ECMLStateStore._infer_run_source(target) == "test"

    @pytest.mark.parametrize("target", ["LiCoO2", "Li3PS4", "PEO", "NMC811", "testosterone"])
    def test_production_targets(self, target):
        assert ECMLStateStore._infer_run_source(target) == "production"


class TestRunSourcePersistence:
    def test_save_writes_run_source(self, store):
        _save_run(store, "r1", "test")
        _save_run(store, "r2", "LiCoO2")
        runs = {r["run_id"]: r for r in store.list_runs(10)}
        assert runs["r1"]["run_source"] == "test"
        assert runs["r2"]["run_source"] == "production"

    def test_lazy_migration_backfills_null_source(self, store):
        """历史记录 run_source 为空时，list/get_run_stats 应按 target 推断回填。"""
        _save_run(store, "r1", "test")
        with store.engine.begin() as conn:
            conn.execute(
                text("UPDATE ecml.ecml_runs SET run_source='' WHERE run_id='r1'")
            )
        runs = store.list_runs(10)
        assert runs[0]["run_source"] == "test"
        # 已真正写回数据库
        with store.engine.connect() as conn:
            val = conn.execute(
                text("SELECT run_source FROM ecml.ecml_runs WHERE run_id='r1'")
            ).fetchone()[0]
        assert val == "test"


class TestBulkDelete:
    def test_bulk_delete_removes_records(self, store):
        for i in range(3):
            _save_run(store, f"t{i}", "test")
        _save_run(store, "keep", "LiCoO2")
        deleted = store.bulk_delete(["t0", "t1", "t2"])
        assert deleted == 3
        runs = store.list_runs(10)
        assert len(runs) == 1
        assert runs[0]["run_id"] == "keep"

    def test_bulk_delete_empty(self, store):
        assert store.bulk_delete([]) == 0


class TestRunStats:
    def test_stats_exclude_test_data(self, store):
        _save_run(store, "p1", "LiCoO2")
        _save_run(store, "p2", "Li3PS4", is_complete=False, status="running")
        for i in range(5):
            _save_run(store, f"t{i}", "test")
        stats = store.get_run_stats()
        assert stats["total"] == 2
        assert stats["active"] == 1
        assert stats["completed_30d"] == 1
        assert stats["test_total"] == 5

    def test_completed_30d_window(self, store):
        old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        recent = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        _save_run(store, "old", "LiCoO2", updated_at=old)
        _save_run(store, "recent", "LiCoO2", updated_at=recent)
        stats = store.get_run_stats()
        assert stats["completed_30d"] == 1


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        from battery_materials_agent.api import app
        import battery_materials_agent.api as api_module

        headers = attach_test_auth(app, role=UserRole.ADMIN)
        with TestClient(app) as c:
            # startup 会重建全局 agent 并重置 user_store，必须在 TestClient 启动后
            # 重新挂载测试用户，否则受角色保护端点（如 bulk-delete）将返回 401
            headers = attach_test_auth(app, role=UserRole.ADMIN)
            c.headers.update(headers)
            # startup 会重建全局 agent，必须在 TestClient 启动后再替换为隔离存储
            api_module.agent.ecml.state_store = ECMLStateStore(
                db_path=os.path.join(tmpdir, "ecml_states.db")
            )
            # 迁移至 PostgreSQL 后所有测试共享同一数据库，client fixture 也需清理
            from sqlalchemy import text as _text
            with api_module.agent.ecml.state_store.engine.begin() as conn:
                conn.execute(_text("DELETE FROM ecml.ecml_runs_index"))
                conn.execute(_text("DELETE FROM ecml.ecml_runs"))
            from battery_materials_agent.synthesis.task_store import SynthesisTaskStore
            app.state.synthesis_task_store = SynthesisTaskStore(
                db_path=os.path.join(tmpdir, "synthesis_tasks.db")
            )
            yield c
        app.state.synthesis_task_store = None


class TestStatsUnifiedAPI:
    def test_stats_excludes_test_runs(self, client):
        import battery_materials_agent.api as api_module
        store = api_module.agent.ecml.state_store
        _save_run(store, "prod1", "LiCoO2")
        for i in range(4):
            _save_run(store, f"t{i}", "test")

        resp = client.get("/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["iterations"] == 1
        assert data["iterations_test_total"] == 4

    def test_stats_has_drilldown_fields(self, client):
        resp = client.get("/stats")
        data = resp.json()
        for key in (
            "candidates", "candidates_new_this_week",
            "experiments", "experiments_active", "experiments_pending_approval",
            "iterations", "iterations_active", "iterations_completed_30d",
            "routes", "synthesis_success_rate",
        ):
            assert key in data, f"missing field: {key}"


class TestBulkDeleteAPI:
    def test_bulk_delete_endpoint(self, client):
        import battery_materials_agent.api as api_module
        store = api_module.agent.ecml.state_store
        for i in range(3):
            _save_run(store, f"t{i}", "test")
        _save_run(store, "keep", "LiCoO2")

        resp = client.post("/api/ecml/runs/bulk-delete", json={"run_ids": ["t0", "t1", "t2"]})
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 3

        runs = client.get("/api/ecml/runs?limit=50").json()["runs"]
        assert len(runs) == 1
        assert runs[0]["run_id"] == "keep"

    def test_bulk_delete_empty_rejected(self, client):
        resp = client.post("/api/ecml/runs/bulk-delete", json={"run_ids": []})
        assert resp.status_code == 400

    def test_bulk_delete_writes_audit_log(self, client):
        import battery_materials_agent.api as api_module
        store = api_module.agent.ecml.state_store
        _save_run(store, "t0", "test")
        client.post("/api/ecml/runs/bulk-delete", json={"run_ids": ["t0"]})

        resp = client.get("/audit/logs?module=ecml&limit=10")
        assert resp.status_code == 200
        logs = resp.json()
        assert any(l["action"] == "bulk_delete_runs" for l in logs)

    def test_list_runs_returns_run_source(self, client):
        import battery_materials_agent.api as api_module
        store = api_module.agent.ecml.state_store
        _save_run(store, "t0", "test")
        _save_run(store, "p0", "LiCoO2")
        runs = {r["run_id"]: r for r in client.get("/api/ecml/runs?limit=50").json()["runs"]}
        assert runs["t0"]["run_source"] == "test"
        assert runs["p0"]["run_source"] == "production"


class TestProjectIdFilter:
    """Step C 4.C1：list_runs 与 /ecml/runs API 按 project_id 过滤。"""

    def test_save_writes_project_id(self, store):
        _save_run(store, "r1", "LiCoO2", project_id="proj-a")
        runs = {r["run_id"]: r for r in store.list_runs(10)}
        assert runs["r1"]["project_id"] == "proj-a"

    def test_list_runs_filters_by_project_id(self, store):
        _save_run(store, "a1", "LiCoO2", project_id="proj-a")
        _save_run(store, "a2", "Li3PS4", project_id="proj-a")
        _save_run(store, "b1", "PEO", project_id="proj-b")
        _save_run(store, "none", "NaCl")  # 无 project_id

        only_a = store.list_runs(50, project_id="proj-a")
        assert {r["run_id"] for r in only_a} == {"a1", "a2"}

        # 空过滤条件返回全部
        all_runs = store.list_runs(50)
        assert {r["run_id"] for r in all_runs} >= {"a1", "a2", "b1", "none"}

    def test_api_filters_by_project_id(self, client):
        import battery_materials_agent.api as api_module
        store = api_module.agent.ecml.state_store
        _save_run(store, "a1", "LiCoO2", project_id="proj-a")
        _save_run(store, "b1", "PEO", project_id="proj-b")

        runs = {r["run_id"]: r for r in client.get("/api/ecml/runs?limit=50&project_id=proj-a").json()["runs"]}
        assert set(runs.keys()) == {"a1"}
        assert runs["a1"]["project_id"] == "proj-a"
