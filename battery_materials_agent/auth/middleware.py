"""权限中间件 — 基于 FastAPI Depends 的角色与项目访问控制。

设计要点：
- ``get_current_user`` 从请求头 ``X-Auth-Token`` 解析当前用户：token 为登录时
  服务端签发的 HMAC 签名串（见 ``auth.tokens``），未携带 / 签名非法 / 已过期 /
  用户存储未就绪 / 用户失效时返回 None（匿名）。该函数永不抛异常，因此可作为
  全局依赖安全注册到 app 上。解析成功时同步写入 ``request.state.current_user``。
- ``require_role(min_role)`` 返回一个依赖函数，校验当前用户角色是否满足最低要求，
  不满足返回 401（未登录/用户失效）或 403（权限不足）。
- ``check_project_access`` 校验用户对指定项目的访问权限（project_ids 为空表示全部可访问）。

UserStore 实例挂载在 ``app.state.user_store``（由 api.py startup 初始化）。
"""

from __future__ import annotations
import logging
from fastapi import Depends, HTTPException, Request
from ..db import set_tenant, DEFAULT_TENANT
from .tokens import verify_token
from .user_store import UserRole, User, UserStore, ROLE_RANK
from .permissions import role_has_permission

logger = logging.getLogger(__name__)


def get_current_user(request: Request) -> User | None:
    """从 X-Auth-Token 解析当前用户。任何异常情况均返回 None（匿名）。"""
    # HTTP 中间件已解析过的话直接复用，避免重复查库
    cached = getattr(request.state, "current_user", None)
    if cached is not None:
        _apply_tenant(request, cached)
        return cached
    store = getattr(request.app.state, "user_store", None)
    if store is None:
        # user_store 未初始化（startup 未完成或配置错误）：记录一次 ERROR 便于排查
        logger.error("user_store not initialized on app.state; authentication disabled")
        return None
    token = request.headers.get("X-Auth-Token", "")
    user_id = verify_token(token)
    if not user_id:
        # 携带了 token 但校验失败（签名错/过期/格式错）：记录 WARNING 便于安全审计；
        # 未携带 token 的匿名访问不记录（流量太大）。
        if token:
            client_ip = request.client.host if request.client else "unknown"
            # 仅记录 user_id 前缀避免泄露完整 token 内容
            token_preview = token[:32] + "..." if len(token) > 32 else token
            logger.warning(
                "Token 校验失败：ip=%s token_preview=%s", client_ip, token_preview
            )
        return None
    user = store.get(user_id)
    if user is None or not user.is_active:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(
            "用户失效或不存在：ip=%s user_id=%s reason=%s",
            client_ip, user_id, "inactive" if user is not None else "not_found"
        )
        return None
    request.state.current_user = user
    _apply_tenant(request, user)
    return user


def _apply_tenant(request: Request, user: User | None) -> None:
    """将当前用户的租户写入请求上下文与 db 上下文。

    匿名用户归属 default 租户；已登录用户归属其 tenant_id。
    后台任务（无 request）需自行调用 db.set_tenant()。
    """
    tenant_id = (user.tenant_id if user else "") or DEFAULT_TENANT
    request.state.tenant_id = tenant_id
    set_tenant(tenant_id)


def require_role(min_role: UserRole):
    """返回 FastAPI 依赖：校验当前用户角色 ≥ min_role。

    用法：``dependencies=[Depends(require_role(UserRole.ADMIN))]``
    或端点签名 ``user: User = Depends(require_role(UserRole.ADMIN))``。

    匿名用户（user is None）仅允许访问 VIEWER 级别资源（保持向后兼容），
    访问更高角色资源时返回 401。
    """

    def _dependency(user: User | None = Depends(get_current_user)) -> User | None:
        if user is None:
            # 匿名访问：仅 VIEWER 级别允许通过，其他角色要求登录
            if min_role is not UserRole.VIEWER:
                raise HTTPException(
                    status_code=401,
                    detail="未登录或用户失效，请先登录",
                )
            return None
        user_rank = ROLE_RANK.get(user.role, 0)
        min_rank = ROLE_RANK.get(min_role, 0)
        if user_rank < min_rank:
            raise HTTPException(
                status_code=403,
                detail=f"权限不足：需要角色 {min_role.value} 或更高",
            )
        return user

    return _dependency


def require_login(request: Request) -> User:
    """FastAPI 依赖：要求请求必须来自已登录用户（不限角色）。

    评测修复 BEMCL-AUTH-P3-001：``require_role(UserRole.VIEWER)`` 为保持向后兼容
    对匿名用户放行，无法保护"登录即可读"的敏感数据端点（如项目列表）。
    本依赖对匿名用户一律返回 401。
    """
    user = get_current_user(request)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="未登录或用户失效，请先登录",
        )
    return user


def require_permission(permission: str):
    """返回 FastAPI 依赖：校验当前用户是否具备指定权限点（A3）。

    用法：``user: User = Depends(require_permission("candidate.update"))``
    或 ``dependencies=[Depends(require_permission("candidate.update"))]``。

    - 匿名用户一律 401；
    - 已登录但缺权限 403，并记录 permission_denied 审计。
    """

    def _dependency(user: User | None = Depends(get_current_user)) -> User:
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="未登录或用户失效，请先登录",
            )
        if not role_has_permission(user.role, permission):
            from ..audit import get_audit_logger, AuditEntry
            try:
                get_audit_logger().log(AuditEntry(
                    event_type="permission_denied", module="auth", action="permission_denied",
                    operator=user.username, user_id=user.user_id,
                    detail={"permission": permission},
                    resource_type="permission", resource_id=permission,
                    tenant_id=user.tenant_id or DEFAULT_TENANT,
                ))
            except Exception:
                logger.debug("权限拒绝审计写入失败", exc_info=True)
            raise HTTPException(
                status_code=403,
                detail=f"权限不足：缺少 {permission}",
            )
        return user

    return _dependency


def check_project_access(user_id: str, project_id: str, store: UserStore) -> bool:
    """校验用户是否可访问指定项目。

    - project_ids 为空：可访问全部项目
    - 否则需 project_id 在用户 project_ids 列表中
    """
    user = store.get(user_id)
    if user is None or not user.is_active:
        return False
    if not user.project_ids:
        return True
    return project_id in user.project_ids


def require_project_access(permission: str):
    """行级访问控制（A3）：要求具备 permission 且能访问指定 project。

    用法：``user: User = Depends(require_project_access("experiment.view"))``，
    同时从 path/query 提取 ``project_id`` 校验行级归属。

    - 匿名 401；
    - 缺权限 403（并记录 permission_denied 审计）；
    - project_ids 非空且不含传入 project_id → 403（行级隔离）。
    """

    def _dependency(
        request: Request,
        user: User = Depends(require_permission(permission)),
    ) -> User:
        project_id = (
            request.path_params.get("project_id")
            or request.query_params.get("project_id")
            or ""
        )
        if project_id and user.project_ids and project_id not in user.project_ids:
            raise HTTPException(
                status_code=403,
                detail=f"无权访问项目 {project_id}",
            )
        return user

    return _dependency
