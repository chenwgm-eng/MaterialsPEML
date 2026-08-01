"""材料知识资产库：papers / materials / claims / relations

Revision ID: 0028_knowledge_asset_base
Revises: 0027_activity_agent_tool_mappings
Create Date: 2026-07-28

设计目标：
- 从"图谱快照"升级为"材料知识资产库"
- 三层资产：文献（papers）→ 材料卡片（materials）→ 主张/数据点（claims）
- 双维度可信度：source_tier（来源等级）× evidence_level（证据强度）
- pgvector 可选：若扩展可用则启用向量检索；否则降级为 PostgreSQL 全文检索

降级策略：
- embedding 列使用 TEXT 占位（存 JSON 字符串）
- 不创建 HNSW 索引
- 后续切换到 pgvector 镜像后，可用单独的迁移把 TEXT 列改为 vector(1024)
"""
from alembic import op
from sqlalchemy import text

revision = "0028_knowledge_asset_base"
down_revision = "0027_activity_agent_tool_mappings"
branch_labels = None
depends_on = None


def _pgvector_available(conn) -> bool:
    """检测 pgvector 扩展是否可用。"""
    try:
        result = conn.execute(text(
            "SELECT 1 FROM pg_available_extensions WHERE name='vector'"
        )).scalar()
        return result is not None
    except Exception:
        return False


def upgrade():
    conn = op.get_bind()
    has_pgvector = _pgvector_available(conn)
    if has_pgvector:
        op.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        embedding_type = "vector(1024)"
    else:
        # 降级：用 TEXT 存 JSON 字符串，后续可 ALTER COLUMN 切换到 vector
        embedding_type = "TEXT"

    # ──────────────────────────── 文献资产表 ────────────────────────────
    op.execute(text(f"""
        CREATE TABLE IF NOT EXISTS knowledge.papers (
            paper_id        TEXT PRIMARY KEY,
            doi             TEXT,
            title           TEXT NOT NULL,
            authors         JSONB DEFAULT '[]'::JSONB,
            journal         TEXT,
            year            INTEGER,
            abstract        TEXT,
            keywords        JSONB DEFAULT '[]'::JSONB,
            source          TEXT NOT NULL,
            source_tier     TEXT NOT NULL DEFAULT 'journal',
            url             TEXT,
            citation_count  INTEGER DEFAULT 0,
            extra           JSONB DEFAULT '{{}}'::JSONB,
            embedding       {embedding_type},
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    op.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_doi
        ON knowledge.papers(doi) WHERE doi IS NOT NULL AND doi <> ''
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_papers_source
        ON knowledge.papers(source)
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_papers_year
        ON knowledge.papers(year DESC)
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_papers_title_fts
        ON knowledge.papers USING GIN (to_tsvector('simple', title))
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_papers_abstract_fts
        ON knowledge.papers USING GIN (to_tsvector('simple', coalesce(abstract, '')))
    """))

    # ──────────────────────────── 材料卡片表 ────────────────────────────
    op.execute(text(f"""
        CREATE TABLE IF NOT EXISTS knowledge.materials (
            material_id     TEXT PRIMARY KEY,
            canonical_name  TEXT NOT NULL,
            aliases         JSONB DEFAULT '[]'::JSONB,
            category        TEXT,
            description     TEXT,
            properties      JSONB DEFAULT '{{}}'::JSONB,
            paper_count     INTEGER DEFAULT 0,
            claim_count     INTEGER DEFAULT 0,
            source_tier     TEXT DEFAULT 'journal',
            evidence_level  TEXT DEFAULT 'literature',
            embedding       {embedding_type},
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    op.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_materials_name
        ON knowledge.materials(canonical_name)
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_materials_category
        ON knowledge.materials(category)
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_materials_name_fts
        ON knowledge.materials USING GIN (to_tsvector('simple', canonical_name))
    """))

    # ──────────────────────── 主张 / 数据点表 ────────────────────────
    op.execute(text(f"""
        CREATE TABLE IF NOT EXISTS knowledge.claims (
            claim_id        TEXT PRIMARY KEY,
            material_id     TEXT REFERENCES knowledge.materials(material_id) ON DELETE CASCADE,
            claim_type      TEXT NOT NULL,
            subject         TEXT NOT NULL,
            predicate       TEXT NOT NULL,
            value           TEXT,
            unit            TEXT,
            numeric_value   DOUBLE PRECISION,
            claim_text      TEXT NOT NULL,
            source_paper_id TEXT REFERENCES knowledge.papers(paper_id) ON DELETE SET NULL,
            source_tier     TEXT NOT NULL DEFAULT 'journal',
            evidence_level  TEXT NOT NULL DEFAULT 'literature',
            confidence      DOUBLE PRECISION DEFAULT 0.5,
            extra           JSONB DEFAULT '{{}}'::JSONB,
            embedding       {embedding_type},
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_claims_material
        ON knowledge.claims(material_id)
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_claims_paper
        ON knowledge.claims(source_paper_id)
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_claims_type
        ON knowledge.claims(claim_type)
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_claims_text_fts
        ON knowledge.claims USING GIN (to_tsvector('simple', claim_text))
    """))

    # ────────────────────── 文献-材料关联表 ──────────────────────
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS knowledge.paper_materials (
            paper_id        TEXT NOT NULL REFERENCES knowledge.papers(paper_id) ON DELETE CASCADE,
            material_id     TEXT NOT NULL REFERENCES knowledge.materials(material_id) ON DELETE CASCADE,
            mention_context TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (paper_id, material_id)
        )
    """))

    # ────────────────────── 语义检索向量索引（仅 pgvector 可用时创建）──────
    if has_pgvector:
        op.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_papers_embedding
            ON knowledge.papers USING hnsw (embedding vector_cosine_ops)
        """))
        op.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_claims_embedding
            ON knowledge.claims USING hnsw (embedding vector_cosine_ops)
        """))
        op.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_materials_embedding
            ON knowledge.materials USING hnsw (embedding vector_cosine_ops)
        """))


def downgrade():
    op.execute(text("DROP TABLE IF EXISTS knowledge.paper_materials"))
    op.execute(text("DROP TABLE IF EXISTS knowledge.claims"))
    op.execute(text("DROP TABLE IF EXISTS knowledge.materials"))
    op.execute(text("DROP TABLE IF EXISTS knowledge.papers"))
