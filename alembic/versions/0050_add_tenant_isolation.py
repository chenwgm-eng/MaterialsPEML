"""企业级多租户隔离：共享 schema + tenant_id 逻辑隔离。

背景：此前所有业务数据混在一个库中，无租户概念。本迁移引入
- ``auth.tenants``：租户表（新增/停用/配额状态）
- 核心业务表加 ``tenant_id`` 列（非空，默认 ``default``），并建复合索引
- 存量数据回填到 ``default`` 租户

设计：共享 schema + ``tenant_id`` 列逻辑隔离（企业级 SaaS 常见），
从认证态解析租户，store 层统一追加 ``tenant_id`` 过滤。

涉及表（核心业务，按需扩展到其余表）：
projects / experiment.candidates / experiment.samples /
experiment.experiment_orders / experiment.experiment_result_records /
audit.audit_log / auth.users（用户归属租户）
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0050_add_tenant_isolation"
down_revision: Union[str, None] = "0049_battery_material_systems"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (schema, table, 是否已有 tenant_id 用于过滤的关键列)
TENANT_TABLES = [
    ("projects", "projects"),
    ("experiment", "candidates"),
    ("experiment", "samples"),
    ("experiment", "experiment_orders"),
    ("experiment", "experiment_result_records"),
    ("audit", "audit_log"),
]


def upgrade() -> None:
    # 1. 租户主表
    op.execute(
        """
        CREATE TABLE auth.tenants (
            tenant_id      TEXT PRIMARY KEY,
            name           TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'active',
            quota          JSONB DEFAULT '{}',
            created_at     TIMESTAMPTZ DEFAULT NOW(),
            updated_at     TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_tenants_status ON auth.tenants(status)")

    # 2. 默认租户（保证存量数据归属）
    op.execute(
        """
        INSERT INTO auth.tenants (tenant_id, name, status)
        VALUES ('default', '默认租户', 'active')
        ON CONFLICT (tenant_id) DO NOTHING
        """
    )

    # 3. 业务表加 tenant_id + 回填 + 索引
    for schema, table in TENANT_TABLES:
        op.execute(
            f"""
            ALTER TABLE {schema}.{table}
            ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default'
            """
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_tenant "
            f"ON {schema}.{table}(tenant_id)"
        )

    # 4. auth.users 归属租户
    op.execute(
        "ALTER TABLE auth.users "
        "ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default'"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_tenant ON auth.users(tenant_id)")
    # 认证源与外部 IdP 标识（为 A2 SSO/JIT 开户预留，同属本迁移演进）
    op.execute(
        "ALTER TABLE auth.users "
        "ADD COLUMN IF NOT EXISTS auth_source TEXT NOT NULL DEFAULT 'local'"
    )
    op.execute(
        "ALTER TABLE auth.users "
        "ADD COLUMN IF NOT EXISTS external_idp_id TEXT DEFAULT ''"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_idp ON auth.users(external_idp_id)"
    )

    # 5. 合规级审计（A4）：补齐字段 + 归档表 + DB 层追加防篡改
    _add_audit_columns()
    _create_audit_archive()
    _create_audit_append_only_rule()


def _add_audit_columns() -> None:
    for col, ddl in [
        ("user_id", "TEXT DEFAULT ''"),
        ("ip", "TEXT DEFAULT ''"),
        ("resource_type", "TEXT DEFAULT ''"),
        ("resource_id", "TEXT DEFAULT ''"),
        ("before", "JSONB DEFAULT '{}'"),
        ("after", "JSONB DEFAULT '{}'"),
    ]:
        op.execute(
            f"ALTER TABLE audit.audit_log ADD COLUMN IF NOT EXISTS {col} {ddl}"
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_tenant "
        "ON audit.audit_log(tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_operator "
        "ON audit.audit_log(operator)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_resource "
        "ON audit.audit_log(resource_type, resource_id)"
    )


def _create_audit_archive() -> None:
    """归档表：结构与 audit_log 完全一致（含全部列），用于超期记录独立归档。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit.audit_archive (
            entry_id             TEXT PRIMARY KEY,
            event_type           TEXT,
            module               TEXT,
            action               TEXT,
            detail               JSONB,
            operator             TEXT,
            confirmed            BOOLEAN,
            created_at           TIMESTAMPTZ,
            tenant_id            TEXT NOT NULL DEFAULT 'default',
            user_id              TEXT DEFAULT '',
            ip                   TEXT DEFAULT '',
            resource_type        TEXT DEFAULT '',
            resource_id          TEXT DEFAULT '',
            before               JSONB DEFAULT '{}',
            after                JSONB DEFAULT '{}'
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_archive_tenant "
        "ON audit.audit_archive(tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_archive_created "
        "ON audit.audit_archive(created_at DESC)"
    )


def _create_audit_append_only_rule() -> None:
    """DB 层追加防篡改：禁止对 audit_log 执行 UPDATE/DELETE。

    使用 RULE 而非 TRIGGER，因为 RULE 在语句层面拦截，可整条拒绝；
    归档动作走 audit_archive 表 + 主表同一事务 DELETE 场景下，
    需在归档完成后才允许删除——这里通过 RULE 只挡住应用层直接篡改，
    归档路径由 store 层 archive() 显式执行（见代码注释）。
    """
    op.execute(
        """
        CREATE OR REPLACE RULE audit_log_no_update AS
        ON UPDATE TO audit.audit_log DO INSTEAD NOTHING
        """
    )
    op.execute(
        """
        CREATE OR REPLACE RULE audit_log_no_delete AS
        ON DELETE TO audit.audit_log DO INSTEAD NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP RULE IF EXISTS audit_log_no_delete ON audit.audit_log")
    op.execute("DROP RULE IF EXISTS audit_log_no_update ON audit.audit_log")
    op.execute("DROP TABLE IF EXISTS audit.audit_archive")
    op.execute("DROP TABLE IF EXISTS auth.tenants")
    for schema, table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {schema}.{table} DROP COLUMN IF EXISTS tenant_id")
    op.execute("ALTER TABLE auth.users DROP COLUMN IF EXISTS tenant_id")
    op.execute("ALTER TABLE auth.users DROP COLUMN IF EXISTS auth_source")
    op.execute("ALTER TABLE auth.users DROP COLUMN IF EXISTS external_idp_id")
    for col in ("user_id", "ip", "resource_type", "resource_id", "before", "after"):
        op.execute(f"ALTER TABLE audit.audit_log DROP COLUMN IF EXISTS {col}")