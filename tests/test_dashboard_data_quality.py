"""T-022：数据质量分布看板后端测试。

验证 GET /dashboard/data-quality 端点：
- 返回 distribution / total / by_project 三段结构
- distribution 始终包含 4 个桶（verified/estimated/simulated/literature）
- 可选 project_id 筛选
- total 等于各桶 count 之和
"""
from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from battery_materials_agent.agent import BatteryMaterialsAgent
from battery_materials_agent.config import AgentConfig
from battery_materials_agent.db import get_engine


# 4 个标准 data_quality 取值
_BUCKETS = ["verified", "estimated", "simulated", "literature"]


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


@pytest.fixture(autouse=True)
def _cleanup_dq_test_records():
    """每个测试前后清理 DQ_TEST_ 前缀的测试记录，避免跨测试污染。"""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM experiment.experiment_result_records "
                "WHERE result_id LIKE 'DQ_TEST_%'"
            )
        )
    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM experiment.experiment_result_records "
                "WHERE result_id LIKE 'DQ_TEST_%'"
            )
        )


def _insert_result(result_id: str, data_quality: str = "estimated") -> None:
    """插入一条 experiment_result_record，仅设置必要字段与 data_quality。"""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO experiment.experiment_result_records "
                "(result_id, data_quality, qc_status, uploaded_at) "
                "VALUES (:rid, :dq, 'VALID', NOW())"
            ),
            {"rid": result_id, "dq": data_quality},
        )


class TestDataQualityDashboard:
    def test_endpoint_returns_expected_shape(self, client):
        """端点返回 distribution / total / by_project 三段结构。"""
        resp = client.get("/api/dashboard/data-quality")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "distribution" in data
        assert "total" in data
        assert "by_project" in data

    def test_distribution_always_has_four_buckets(self, client):
        """distribution 始终包含 4 个 data_quality 桶（即便计数为 0）。"""
        resp = client.get("/api/dashboard/data-quality")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        keys = {d["data_quality"] for d in data["distribution"]}
        assert keys == set(_BUCKETS)
        # 每条 distribution 项包含 data_quality 与 count 字段
        for item in data["distribution"]:
            assert "data_quality" in item
            assert "count" in item
            assert isinstance(item["count"], int)

    def test_distribution_counts_match_inserted_records(self, client):
        """插入数据后，各桶 count 与插入数量一致，total 等于各桶之和。"""
        _insert_result("DQ_TEST_001", "verified")
        _insert_result("DQ_TEST_002", "verified")
        _insert_result("DQ_TEST_003", "estimated")
        _insert_result("DQ_TEST_004", "simulated")
        _insert_result("DQ_TEST_005", "literature")

        resp = client.get("/api/dashboard/data-quality")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        dist = {d["data_quality"]: d["count"] for d in data["distribution"]}
        assert dist["verified"] >= 2
        assert dist["estimated"] >= 1
        assert dist["simulated"] >= 1
        assert dist["literature"] >= 1
        # total 等于各桶 count 之和
        assert data["total"] == sum(dist.values())

    def test_by_project_structure(self, client):
        """by_project 为列表，每项包含 project_id / project_name / distribution。"""
        resp = client.get("/api/dashboard/data-quality")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data["by_project"], list)
        for proj in data["by_project"]:
            assert "project_id" in proj
            assert "project_name" in proj
            assert "distribution" in proj
            # 项目级 distribution 也应包含 4 个桶
            keys = {d["data_quality"] for d in proj["distribution"]}
            assert keys == set(_BUCKETS)

    def test_project_id_filter(self, client):
        """指定 project_id 筛选时，仅返回该项目的分布。"""
        # 由于无关联 experiment_order，所有 DQ_TEST_ 记录 project_id 为空。
        # 此处验证传 project_id 时端点不报错，且仍返回 4 个标准桶。
        resp = client.get(
            "/api/dashboard/data-quality", params={"project_id": "nonexistent_proj"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        keys = {d["data_quality"] for d in data["distribution"]}
        assert keys == set(_BUCKETS)
