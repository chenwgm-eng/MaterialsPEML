"""细粒度权限点（A3）。

将原先仅按角色层级（require_role）的粗粒度控制，升级为「权限点 + 角色授权」。
每个涉及敏感操作的 API 端点声明其所需的权限点，由 require_permission 依赖校验。

权限点粒度示例：
- 读类：project.view / candidate.view / experiment.view / audit.view
- 写类：candidate.update / experiment.create / report.export
- 管理类：user.manage / tenant.manage / project.manage

角色与权限映射见 ROLE_PERMISSIONS。ADMIN 默认拥有全部权限，不在此显式列出，
由 require_permission 对 ADMIN 直接放行，便于未来新增权限点无需同步维护 admin。
"""
from __future__ import annotations

from .user_store import User, UserRole, ROLE_RANK


# --- 权限点常量（字符串，便于日志与审计）---
project_view = "project.view"
project_manage = "project.manage"
candidate_view = "candidate.view"
candidate_create = "candidate.create"
candidate_update = "candidate.update"
candidate_delete = "candidate.delete"
experiment_view = "experiment.view"
experiment_create = "experiment.create"
experiment_update = "experiment.update"
experiment_delete = "experiment.delete"
prediction_run = "prediction.run"
report_export = "report.export"
audit_view = "audit.view"
user_manage = "user.manage"
tenant_manage = "tenant.manage"
agent_manage = "agent.manage"


# --- 角色 → 权限点映射 ---
ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.VIEWER: {
        project_view,
        candidate_view,
        experiment_view,
        prediction_run,
        audit_view,
    },
    UserRole.REVIEWER: {
        project_view,
        candidate_view,
        candidate_update,
        experiment_view,
        prediction_run,
        audit_view,
    },
    UserRole.RESEARCHER: {
        project_view,
        candidate_view,
        candidate_create,
        candidate_update,
        experiment_view,
        experiment_create,
        experiment_update,
        prediction_run,
        report_export,
        audit_view,
    },
    UserRole.DATA_ENGINEER: {
        project_view,
        candidate_view,
        candidate_create,
        candidate_update,
        experiment_view,
        experiment_create,
        experiment_update,
        experiment_delete,
        prediction_run,
        report_export,
        audit_view,
    },
    UserRole.PROJECT_MANAGER: {
        project_view,
        project_manage,
        candidate_view,
        candidate_create,
        candidate_update,
        candidate_delete,
        experiment_view,
        experiment_create,
        experiment_update,
        experiment_delete,
        prediction_run,
        report_export,
        audit_view,
        agent_manage,
    },
    # ADMIN 全部权限，由 require_permission 直接放行
}


def role_has_permission(role: UserRole, permission: str) -> bool:
    """判断角色是否具备指定权限点。ADMIN 恒为 True。"""
    if role == UserRole.ADMIN:
        return True
    return permission in ROLE_PERMISSIONS.get(role, set())


def user_has_permission(user: User | None, permission: str) -> bool:
    """判断用户是否具备指定权限点。匿名用户（None）一律无权。"""
    if user is None:
        return False
    return role_has_permission(user.role, permission)