"""用户模型与持久化存储。

密码哈希采用 PBKDF2-HMAC-SHA256（20 万次迭代），校验使用常量时间比较；
兼容读取早期 sha256+salt 格式（登录成功后自动升级重哈希）。
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, timezone
import uuid
import hashlib
import hmac
import secrets
import logging
import os
import json
from sqlalchemy import text
from ..db import get_engine

logger = logging.getLogger(__name__)


def _iso(value) -> str:
    """将 datetime 或字符串转换为 ISO 字符串；None 返回空字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


# 角色层级：数值越大权限越高，用于 require_role 最低角色判定
ROLE_RANK: dict["UserRole", int] = {}


class UserRole(str, Enum):
    ADMIN = "admin"           # 系统管理员
    PROJECT_MANAGER = "pm"    # 项目经理
    RESEARCHER = "researcher" # 研究员
    REVIEWER = "reviewer"     # 审核员
    VIEWER = "viewer"         # 只读访客
    DATA_ENGINEER = "data_engineer"  # 数据工程师（RESEARCHER 别名/子角色，同级）


# 填充角色层级（放在类定义之后）
ROLE_RANK = {
    UserRole.VIEWER: 0,
    UserRole.REVIEWER: 1,
    UserRole.RESEARCHER: 2,
    UserRole.DATA_ENGINEER: 2,  # 与 RESEARCHER 同级
    UserRole.PROJECT_MANAGER: 3,
    UserRole.ADMIN: 4,
}


class Discipline(str, Enum):
    """专业画像（只影响默认体验，不影响权限）。"""
    MATERIAL_RESEARCH = "material_research"      # 材料研发
    PROCESS_DESIGN = "process_design"            # 工艺设计
    EXPERIMENT_ANALYSIS = "experiment_analysis"  # 实验分析


_VALID_DISCIPLINES = {d.value for d in Discipline}


def normalize_disciplines(disciplines, primary):
    """归一化专业画像：去重去空、校验枚举、primary 必须 ∈ disciplines。

    非法输入抛 ``ValueError``，由调用方转为 400。
    """
    ds = sorted({d for d in (disciplines or []) if d})  # 去重去空
    bad = [d for d in ds if d not in _VALID_DISCIPLINES]
    if bad:
        raise ValueError(f"非法专业画像: {bad}")
    p = primary or ""
    if p and p not in ds:
        raise ValueError("primary_discipline 必须属于 disciplines")
    return ds, p


class User(BaseModel):
    user_id: str = ""
    username: str = ""
    display_name: str = ""
    email: str = ""
    role: UserRole = UserRole.VIEWER
    project_ids: list[str] = Field(default_factory=list)  # 可访问的项目ID列表，空列表=全部
    is_active: bool = True
    created_at: str = ""
    last_login: str = ""
    password_hash: str = ""  # 格式：pbkdf2${iterations}${salt}${hash}；兼容旧 {salt}${hash}
    tenant_id: str = ""  # 所属租户（多租户隔离）；空=default
    auth_source: str = "local"  # local / oidc / ldap
    external_idp_id: str = ""  # SSO JIT 开户用的外部 IdP 标识
    disciplines: list[str] = Field(default_factory=list)  # 0-3 个 Discipline 值，去重
    primary_discipline: str = ""  # 空串=NULL 语义；非空必须 ∈ disciplines


_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str, salt: str = "") -> str:
    """PBKDF2-HMAC-SHA256 哈希。返回 'pbkdf2${iterations}${salt}${hash}' 格式。"""
    if not salt:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt}${digest}"


def is_legacy_hash(stored: str) -> bool:
    """判断是否为旧 sha256 格式（用于登录成功后升级重哈希）。"""
    return bool(stored) and not stored.startswith("pbkdf2$")


def verify_password(password: str, stored: str) -> bool:
    """校验密码。支持 pbkdf2 新格式与 sha256 旧格式，常量时间比较。"""
    if not stored or "$" not in stored:
        return False
    if stored.startswith("pbkdf2$"):
        try:
            _, iterations, salt, digest = stored.split("$", 3)
            candidate = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations)
            ).hex()
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(candidate, digest)
    # 兼容旧格式 '{salt}${sha256}'
    salt, digest = stored.split("$", 1)
    candidate = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(candidate, digest)


class UserStore:
    """PostgreSQL 持久化用户存储。"""

    def __init__(self):
        self.engine = get_engine()
        self._ensure_default_admin()

    def _ensure_default_admin(self):
        """首次初始化时创建默认 admin 用户。

        默认密码从环境变量 ``ADMIN_DEFAULT_PASSWORD`` 读取。未设置时：
        - ``RUN_MODE=production``：拒绝启动（禁止弱口令进入生产）；
        - 其他模式：回退到 ``admin123`` 并输出醒目告警，请尽快修改。
        """
        existing = self.get_by_username("admin")
        if existing is not None:
            return
        default_password = os.environ.get("ADMIN_DEFAULT_PASSWORD", "")
        if not default_password:
            if os.environ.get("RUN_MODE", "demo").lower() == "production":
                raise RuntimeError(
                    "RUN_MODE=production 时必须通过环境变量 ADMIN_DEFAULT_PASSWORD "
                    "显式设置初始管理员密码，禁止使用内置弱口令。"
                )
            default_password = "admin123"
            logger.warning(
                "ADMIN_DEFAULT_PASSWORD 未设置：默认 admin 使用弱口令 admin123，"
                "请尽快通过用户管理修改；生产环境必须显式配置该变量。"
            )
        now = datetime.now(timezone.utc).isoformat()
        admin = User(
            user_id=f"U-{uuid.uuid4().hex[:8].upper()}",
            username="admin",
            display_name="系统管理员",
            email="admin@battery-emcl.local",
            role=UserRole.ADMIN,
            project_ids=[],
            is_active=True,
            created_at=now,
            last_login="",
            password_hash=hash_password(default_password),
        )
        self.save(admin)
        # C3: 日志中不记录密码原文，避免敏感信息泄露
        logger.info("已创建默认管理员用户 admin/***（首次部署后请尽快修改密码）")

    def save(self, user: User) -> User:
        """新增或更新用户（按 user_id upsert）。"""
        if not user.user_id:
            user.user_id = f"U-{uuid.uuid4().hex[:8].upper()}"
        if not user.created_at:
            user.created_at = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO auth.users
                (user_id, username, display_name, email, role, project_ids,
                 is_active, created_at, last_login, password_hash,
                 tenant_id, auth_source, external_idp_id,
                 disciplines, primary_discipline)
                VALUES (:user_id, :username, :display_name, :email, :role,
                        CAST(:project_ids AS JSONB), :is_active,
                        :created_at, :last_login, :password_hash,
                        :tenant_id, :auth_source, :external_idp_id,
                        CAST(:disciplines AS JSONB), :primary_discipline)
                ON CONFLICT (user_id) DO UPDATE SET
                    username=EXCLUDED.username,
                    display_name=EXCLUDED.display_name,
                    email=EXCLUDED.email,
                    role=EXCLUDED.role,
                    project_ids=EXCLUDED.project_ids,
                    is_active=EXCLUDED.is_active,
                    created_at=EXCLUDED.created_at,
                    last_login=EXCLUDED.last_login,
                    password_hash=EXCLUDED.password_hash,
                    tenant_id=EXCLUDED.tenant_id,
                    auth_source=EXCLUDED.auth_source,
                    external_idp_id=EXCLUDED.external_idp_id,
                    disciplines=EXCLUDED.disciplines,
                    primary_discipline=EXCLUDED.primary_discipline"""),
                {
                    "user_id": user.user_id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "email": user.email,
                    "role": user.role.value,
                    "project_ids": json.dumps(user.project_ids),
                    "is_active": user.is_active,
                    "created_at": user.created_at,
                    "last_login": user.last_login,
                    "password_hash": user.password_hash,
                    "tenant_id": user.tenant_id or "default",
                    "auth_source": user.auth_source or "local",
                    "external_idp_id": user.external_idp_id or "",
                    "disciplines": json.dumps(sorted(set(user.disciplines))),
                    "primary_discipline": user.primary_discipline or None,
                },
            )
        return user

    def get(self, user_id: str) -> User | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM auth.users WHERE user_id=:user_id"),
                {"user_id": user_id},
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_by_username(self, username: str) -> User | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM auth.users WHERE username=:username"),
                {"username": username},
            ).fetchone()
        return self._row_to_user(row) if row else None

    def list_all(self) -> list[User]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM auth.users ORDER BY created_at ASC")
            ).fetchall()
        return [self._row_to_user(r) for r in rows]

    def delete(self, user_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM auth.users WHERE user_id=:user_id"),
                {"user_id": user_id},
            )
            return cur.rowcount > 0

    def update_last_login(self, user_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE auth.users SET last_login=:now WHERE user_id=:user_id"),
                {"now": now, "user_id": user_id},
            )

    def _row_to_user(self, row) -> User:
        # 用 _mapping 按名读取，避免新增列导致位置索引漂移
        m = row._mapping
        return User(
            user_id=m["user_id"], username=m["username"], display_name=m["display_name"],
            email=m["email"], role=UserRole(m["role"]),
            project_ids=list(m["project_ids"] or []),
            is_active=bool(m["is_active"]),
            created_at=_iso(m["created_at"]),
            last_login=_iso(m["last_login"]),
            password_hash=m["password_hash"] or "",
            tenant_id=m.get("tenant_id") or "default",
            auth_source=m.get("auth_source") or "local",
            external_idp_id=m.get("external_idp_id") or "",
            disciplines=list(m.get("disciplines") or []),
            primary_discipline=m.get("primary_discipline") or "",
        )

    def get_by_external_idp(self, external_idp_id: str) -> User | None:
        """按外部 IdP 标识查询用户（SSO JIT 开户幂等用）。"""
        if not external_idp_id:
            return None
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM auth.users WHERE external_idp_id=:idp"),
                {"idp": external_idp_id},
            ).fetchone()
        return self._row_to_user(row) if row else None
