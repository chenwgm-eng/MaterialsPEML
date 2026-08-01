"""Alembic 迁移环境配置。"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 从项目配置获取 DATABASE_URL
config = context.config

# 如果 alembic.ini 没有 sqlalchemy.url，从环境变量读取
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option(
        "sqlalchemy.url",
        os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://batteryemcl:batteryemcl_dev@localhost:5433/batteryemcl",
        ),
    )

# 配置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# target_metadata 用于 autogenerate（暂为 None，后续 Task 8 会填充）
target_metadata = None


def run_migrations_offline() -> None:
    """离线模式运行迁移。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式运行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
