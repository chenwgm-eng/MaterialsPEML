"""统一数据库引擎工厂 — SQLAlchemy 2.0 + psycopg3。

替代 27+ 个分散的 SQLite .db 文件 + 原生 sqlite3 调用，
所有 Store 类通过 get_engine() 获取 SQLAlchemy Engine。
"""
from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from functools import lru_cache

from pydantic import BaseModel, Field
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# 默认租户：存量数据与未显式指定租户的上下文均归属该租户
DEFAULT_TENANT = "default"

# 当前请求/任务的租户上下文（ContextVar，随 asyncio task 隔离）。
# 后端中间件解析用户后写入；后台任务（如每日聚合）需显式 set_tenant()。
_tenant_ctx: ContextVar[str] = ContextVar("tenant_id", default=DEFAULT_TENANT)


def set_tenant(tenant_id: str) -> None:
    """在上下文中设置当前租户。后台任务在无请求上下文时必须显式调用。"""
    _tenant_ctx.set(tenant_id or DEFAULT_TENANT)


def get_tenant() -> str:
    """获取当前上下文的租户 ID（默认 default）。"""
    value = _tenant_ctx.get()
    return value or DEFAULT_TENANT


def tenant_filter(column: str = "tenant_id") -> str:
    """返回追加到 SQL WHERE 的租户过滤片段（须与 :param tenant_id 配合）。

    用法：``WHERE {tenant_filter()} AND ...``，并在参数中传入
    ``"tenant_id": get_tenant()``。禁止 store 手写租户过滤，统一走本工具。
    """
    return f"{column} = :tenant_id"


class DatabaseConfig(BaseModel):
    """数据库配置（从环境变量读取）。"""

    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://batteryemcl:batteryemcl_dev@localhost:5433/batteryemcl",
        )
    )
    pool_size: int = Field(default_factory=lambda: int(os.getenv("DB_POOL_SIZE", "5")))
    max_overflow: int = Field(default_factory=lambda: int(os.getenv("DB_MAX_OVERFLOW", "20")))
    pool_pre_ping: bool = Field(
        default_factory=lambda: os.getenv("DB_POOL_PRE_PING", "true").lower() == "true"
    )
    echo: bool = Field(default_factory=lambda: os.getenv("DB_ECHO", "false").lower() == "true")


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """获取 SQLAlchemy Engine 单例（连接池）。

    ``RUN_MODE=production`` 时必须显式配置 ``DATABASE_URL``，
    禁止静默回退到内置开发连接串。

    Returns:
        Engine: 全局唯一的 SQLAlchemy Engine 实例
    """
    if not os.getenv("DATABASE_URL") and os.getenv("RUN_MODE", "demo").lower() == "production":
        raise RuntimeError(
            "RUN_MODE=production 时必须显式配置 DATABASE_URL，禁止使用内置开发连接串。"
        )
    config = DatabaseConfig()
    engine = create_engine(
        config.database_url,
        poolclass=QueuePool,
        pool_size=config.pool_size,
        max_overflow=config.max_overflow,
        pool_pre_ping=config.pool_pre_ping,
        echo=config.echo,
    )
    return engine


def reset_engine() -> None:
    """清空 Engine 单例缓存（测试替换配置或配置热更新后调用）。"""
    get_engine.cache_clear()


def test_connection() -> bool:
    """测试数据库连接是否正常。

    Returns:
        bool: 连接成功返回 True
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning("Database connection test failed: %s", e)
        return False


# 兼容性别名：让 Store 类可以逐步迁移
def get_session():
    """获取 SQLAlchemy Session（用于需要事务的场景）。

    注意：调用方应使用 ``with get_session() as session:`` 上下文管理器，
    确保连接归还连接池，避免泄漏。
    """
    from sqlalchemy.orm import Session
    engine = get_engine()
    return Session(engine)
