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
        resp = client.post("/discover/crystal", json={"elements": ["Li", "P", "S", "Cl"], "num_candidates": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] > 0
        # D3(P2-003)：临时性质预测溯源——model_version/confidence/input_snapshot 非空
        first = data["candidates"][0]
        ai_meta = first.get("ai_meta") or {}
        assert ai_meta.get("model_version")
        assert ai_meta.get("input_snapshot_hash")
        assert ai_meta.get("generated_at")

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

    def test_dashboard_material_alerts_have_context_and_dedup(self, client):
        """D4(P2-004)：物料预警附带上下文解释与建议动作，且按 material_id 去重。"""
        import battery_materials_agent.api as api_module
        from battery_materials_agent.industrialization.raw_material_db import MaterialSpec
        db = api_module.agent.raw_material_db
        # 同一 material_id 重复写入多次，验证看板去重后只保留一条
        for _ in range(3):
            db.upsert_spec(MaterialSpec(
                material_id="M-ALERT-001",
                name="低库存测试物料",
                category="",
                inventory_quantity=2.0,  # 低于阈值
                inventory_unit="kg",
                supplier="测试供应商",
            ))
        resp = client.get("/dashboard/resources")
        assert resp.status_code == 200
        alerts = resp.json()["material_alerts"]["items"]
        ids = [a["material_id"] for a in alerts if a["material_id"] in ("M-ALERT-001",)]
        assert len(ids) == 1, "同一物料不应在预警中出现重复条目"
        target = next(a for a in alerts if a["material_id"] == "M-ALERT-001")
        assert target.get("context"), "预警应附上下文解释"
        assert target.get("action"), "预警应附建议动作"

    def test_control_plane_providers_report_configured(self):
        """D5(P2-005)：Provider 报告 configured 状态，未配置服务前端可显示"未配置"。"""
        import tempfile
        from fastapi.testclient import TestClient
        from battery_materials_agent.agent import BatteryMaterialsAgent
        from battery_materials_agent.config import AgentConfig
        from tests.conftest import attach_test_auth
        from battery_materials_agent.auth.user_store import UserRole
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(data_dir=os.path.join(tmpdir, "data"))
            os.makedirs(config.data_dir, exist_ok=True)
            agent = BatteryMaterialsAgent(config)
            from battery_materials_agent.api import app
            app.dependency_overrides = {}
            import battery_materials_agent.api as api_module
            api_module.agent = agent

            @app.on_event("startup")
            async def override_startup():
                attach_test_auth(app, role=UserRole.ADMIN)

            headers = attach_test_auth(app, role=UserRole.ADMIN)
            with TestClient(app, headers=headers) as c:
                resp = c.get("/control-plane/providers")
                assert resp.status_code == 200
                providers = resp.json()["providers"]
                assert providers, "应至少返回内置 Provider"
                for p in providers:
                    assert "configured" in p, "每个 Provider 都应报告 configured 状态"
                    assert p["configured"] in (True, False)
