"""Step E 治理收尾 —— 测试矩阵 T2/T4/T5/T9 后端授权项集成测试。

覆盖设计文档 §5.2 中可在内存层验证的矩阵项（不写库、不依赖 PostgreSQL 表就绪）：
- T2：``PUT /auth/me/disciplines`` 对非法专业画像返回 400（normalize 在写库前拦截）；
- T4：viewer 直接改 URL 访问 create 端点为 403（require_role RESEARCHER）；
- T5：viewer 直接调管理/写接口为 403（user.manage）；
- T9：非 admin 调 ``PUT /nav-visibility`` 为 403（user.manage）。

403 路径在命中存储前由 require_permission/require_role 判定，无需真实 DB。
T8/其余 DB 相关项由 test_nav_visibility.py / test_user_disciplines.py 单元层覆盖。
"""

from __future__ import annotations

import tempfile
import pytest
from fastapi.testclient import TestClient

from battery_materials_agent.agent import BatteryMaterialsAgent
from battery_materials_agent.config import AgentConfig
from battery_materials_agent.auth.user_store import UserRole
from tests.conftest import attach_test_auth


@pytest.fixture
def client_factory():
    """按角色创建 TestClient 的工厂夹具。"""
    created: list[tuple] = []

    def _make(role: UserRole):
        tmpdir = tempfile.mkdtemp()
        config = AgentConfig(data_dir=tmpdir)
        agent = BatteryMaterialsAgent(config)

        from battery_materials_agent.api import app
        app.dependency_overrides = {}
        import battery_materials_agent.api as api_module
        api_module.agent = agent

        @app.on_event("startup")
        async def override_startup():
            attach_test_auth(app, role=role)

        headers = attach_test_auth(app, role=role)
        c = TestClient(app, headers=headers)
        created.append((c, tmpdir))
        return c

    yield _make
    for c, _t in created:
        c.close()


class TestT2DisciplineAPIValidation:
    """T2：researcher（任一画像）写非法专业画像 → 400；合法写 → 命中 normalize 校验。"""

    def test_invalid_discipline_rejected_400(self, client_factory):
        c = client_factory(UserRole.RESEARCHER)
        resp = c.put("/auth/me/disciplines", json={
            "disciplines": ["material_research", "not_a_discipline"],
            "primary_discipline": "material_research",
        })
        assert resp.status_code == 400

    def test_primary_not_in_disciplines_rejected_400(self, client_factory):
        c = client_factory(UserRole.RESEARCHER)
        resp = c.put("/auth/me/disciplines", json={
            "disciplines": ["material_research"],
            "primary_discipline": "experiment_analysis",
        })
        assert resp.status_code == 400

    def test_anonymous_401(self, client_factory):
        from battery_materials_agent.api import app
        c = TestClient(app)
        resp = c.put("/auth/me/disciplines", json={"disciplines": [], "primary_discipline": ""})
        assert resp.status_code == 401


class TestT4ViewerCreateForbidden:
    """T4：viewer 改 URL 到 create 页 → 后端 403（导航隐藏≠权限，后端仍强制）。"""

    def test_discover_forbidden(self, client_factory):
        c = client_factory(UserRole.VIEWER)
        resp = c.post("/discover", json={"target": "test", "max_iterations": 1})
        assert resp.status_code == 403

    def test_synthesis_check_forbidden(self, client_factory):
        c = client_factory(UserRole.VIEWER)
        resp = c.post("/synthesis/check", json={"smiles": "CCO"})
        assert resp.status_code == 403


class TestT5ViewerManageForbidden:
    """T5：viewer 直接调管理/写接口 → 全 403（user.manage）。"""

    def test_list_users_forbidden(self, client_factory):
        c = client_factory(UserRole.VIEWER)
        resp = c.get("/auth/users")
        assert resp.status_code == 403

    def test_update_user_forbidden(self, client_factory):
        c = client_factory(UserRole.VIEWER)
        resp = c.put("/auth/users/U-OTHER", json={"display_name": "x"})
        assert resp.status_code == 403

    def test_delete_user_forbidden(self, client_factory):
        c = client_factory(UserRole.VIEWER)
        resp = c.delete("/auth/users/U-OTHER")
        assert resp.status_code == 403

    def test_nav_visibility_write_forbidden(self, client_factory):
        c = client_factory(UserRole.VIEWER)
        resp = c.put("/nav-visibility", json={"matrix": {"viewer": {"admin": False}}})
        assert resp.status_code == 403


class TestT9NonAdminNavVisibilityForbidden:
    """T9：非 admin 调 PUT /nav-visibility（无 user.manage）→ 403。"""

    @pytest.mark.parametrize(
        "role",
        [UserRole.PROJECT_MANAGER, UserRole.RESEARCHER, UserRole.REVIEWER, UserRole.DATA_ENGINEER],
    )
    def test_non_admin_put_forbidden(self, client_factory, role):
        c = client_factory(role)
        resp = c.put("/nav-visibility", json={"matrix": {role.value: {"admin": False}}})
        assert resp.status_code == 403