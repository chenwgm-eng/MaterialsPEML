"""Integration tests for the FastAPI server."""

import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from battery_materials_agent.agent import BatteryMaterialsAgent
from battery_materials_agent.config import AgentConfig
from tests.conftest import attach_test_auth


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(data_dir=os.path.join(tmpdir, "data"))
        os.makedirs(config.data_dir, exist_ok=True)
        agent = BatteryMaterialsAgent(config)

        from battery_materials_agent.api import app
        app.dependency_overrides = {}

        import battery_materials_agent.api as api_module
        api_module.agent = agent

        # 原始 startup() 会初始化并覆盖 app.state.user_store（真实 UserStore），
        # attach_test_auth 在 TestClient 进入前调用会被覆盖。on_event 按注册顺序执行，
        # 此 override 在原始 startup 之后运行，重新挂载测试用户存储。
        @app.on_event("startup")
        async def override_startup():
            attach_test_auth(app)

        headers = attach_test_auth(app)
        with TestClient(app, headers=headers) as c:
            yield c


class TestAPI:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_route_material(self, client):
        resp = client.post("/route", json={"name": "PEO electrolyte"})
        assert resp.status_code == 200
        data = resp.json()
        assert "material_type" in data

    def test_discover(self, client):
        resp = client.post("/discover", json={"target": "test", "max_iterations": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert "iterations" in data

    def test_discover_crystal(self, client):
        resp = client.post("/discover/crystal", json={"elements": ["Li"], "num_candidates": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] > 0

    def test_discover_polymer(self, client):
        resp = client.post("/discover/polymer", json={"num_candidates": 5})
        assert resp.status_code == 200

    def test_synthesis_check(self, client):
        resp = client.post("/synthesis/check", json={"smiles": "CCO"})
        assert resp.status_code == 200
        assert "feasibility_score" in resp.json()

    def test_verify(self, client):
        resp = client.post("/verify", json={"smiles": "CCO", "property_name": "total_energy"})
        assert resp.status_code == 200
        assert "molecule_name" in resp.json()

    def test_query_experiments(self, client):
        resp = client.post("/experiments/query", json={"formula": "LiCoO2"})
        assert resp.status_code == 200
        assert "records" in resp.json()

    def test_mcp_manifest(self, client):
        resp = client.get("/mcp/manifest")
        assert resp.status_code == 200
        assert "tools" in resp.json()

    def test_tools_list(self, client):
        resp = client.get("/tools")
        assert resp.status_code == 200
        assert "tools" in resp.json()
