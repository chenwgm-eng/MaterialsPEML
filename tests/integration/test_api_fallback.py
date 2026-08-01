"""P0-3: 技术性报错用户语言转译相关后端测试。

验证未匹配的 API 非 GET 请求返回 404 JSON（中文提示），
而不是向最终用户暴露 405 "Method Not Allowed"。
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from battery_materials_agent.agent import BatteryMaterialsAgent
from battery_materials_agent.config import AgentConfig


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

        with TestClient(app) as c:
            yield c


class TestApiFallbackNoRawMethodNotAllowed:
    """SPA 兜底路由仅支持 GET，未匹配的 API POST/PUT/DELETE 必须返回 404 中文 JSON。"""

    def test_unmatched_api_post_returns_404_not_405(self, client):
        resp = client.post("/api/nonexistent-endpoint-xyz", json={"a": 1})
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert "Method Not Allowed" not in str(detail)
        assert "接口" in detail

    def test_unmatched_api_put_returns_404_not_405(self, client):
        resp = client.put("/api/nonexistent-endpoint-xyz", json={"a": 1})
        assert resp.status_code == 404
        assert "Method Not Allowed" not in str(resp.json()["detail"])

    def test_unmatched_api_delete_returns_404_not_405(self, client):
        resp = client.delete("/api/nonexistent-endpoint-xyz")
        assert resp.status_code == 404
        assert "Method Not Allowed" not in str(resp.json()["detail"])

    def test_unmatched_api_get_returns_404_chinese(self, client):
        resp = client.get("/api/nonexistent-endpoint-xyz")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert "Not Found" not in str(detail)
        assert "接口" in detail
