"""将 knowledge 资产库的 embedding 列从 TEXT 占位升级为 vector(1024)

Revision ID: 0029_pgvector_embedding_migration
Revises: 0028_knowledge_asset_base
Create Date: 2026-07-28

背景：
- 0028 在没有 pgvector 扩展时将 embedding 列建为 TEXT 占位
- 现已切换到 pgvector/pgvector:pg16 镜像，扩展可用
- 本迁移把 TEXT 列转为 vector(1024)，并补建 HNSW 向量索引

注意：
- embedding 列当前无应用代码写入（asset_store 未使用），可安全 USING NULL 转换
- 若后续已有 TEXT 形式的 JSON 向量数据，需改写 USING 子句解析后再转换
"""
from alembic import op
from sqlalchemy import text

revision = "0029_pgvector_embedding_migration"
down_revision = "0028_knowledge_asset_base"
branch_labels = None
depends_on = None


EMBEDDING_TABLES = ("papers", "materials", "claims")


def upgrade() -> None:
    # 1. 启用 pgvector 扩展
    op.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # 2. 将 TEXT 占位列转为 vector(1024)
    #    embedding 列当前为空（无应用代码写入），USING NULL 直接转换
    for table in EMBEDDING_TABLES:
        op.execute(
            text(
                f"ALTER TABLE knowledge.{table} "
                f"ALTER COLUMN embedding TYPE vector(1024) USING NULL::vector(1024)"
            )
        )

    # 3. 补建 HNSW 向量索引（余弦相似度）
    for table in EMBEDDING_TABLES:
        index_name = f"idx_{table}_embedding"
        op.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {index_name} "
                f"ON knowledge.{table} USING hnsw (embedding vector_cosine_ops)"
            )
        )


def downgrade() -> None:
    # 删除 HNSW 索引
    for table in EMBEDDING_TABLES:
        index_name = f"idx_{table}_embedding"
        op.execute(text(f"DROP INDEX IF EXISTS knowledge.{index_name}"))

    # 列类型回退为 TEXT
    for table in EMBEDDING_TABLES:
        op.execute(
            text(
                f"ALTER TABLE knowledge.{table} "
                f"ALTER COLUMN embedding TYPE TEXT USING embedding::text"
            )
        )

    # 不卸载 vector 扩展（其他模块可能依赖）
