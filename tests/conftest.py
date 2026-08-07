"""测试共享夹具与鉴权助手。

API 端点已启用基于角色的鉴权（``require_role``/``require_login``），
测试客户端需携带有效 token 才能访问受保护端点。本模块提供
``attach_test_auth`` 助手：将测试用户挂载到 ``app.state.user_store``
并签发 token，供各测试文件的 client fixture 复用，避免逐个测试重复造轮子。
"""

from __future__ import annotations

import pytest

from battery_materials_agent.auth.tokens import issue_token
from battery_materials_agent.auth.user_store import User, UserRole


class _TestUserStore:
    """内存版用户存储：仅用于测试短路身份校验，避免依赖 PostgreSQL。"""

    def __init__(self, user: User):
        self._user = user

    def get(self, user_id: str):
        return self._user if user_id == self._user.user_id else None


def attach_test_auth(app, role: UserRole = UserRole.RESEARCHER) -> dict[str, str]:
    """将测试用户挂载到 ``app.state.user_store`` 并返回鉴权头。

    Args:
        app: FastAPI app 实例。
        role: 测试用户角色，默认研究员（覆盖绝大多数端点）。

    Returns:
        应传给 TestClient/请求的 ``X-Auth-Token`` 头。
    """
    user = User(
        user_id="U-TEST-0001",
        username="tester",
        display_name="测试研究员",
        role=role,
        is_active=True,
    )
    app.state.user_store = _TestUserStore(user)
    return {"X-Auth-Token": issue_token(user.user_id)}


__all__ = ["attach_test_auth"]