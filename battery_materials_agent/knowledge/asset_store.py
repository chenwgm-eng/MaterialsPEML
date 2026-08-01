"""材料知识资产库存储层。

三层资产模型：
- PaperStore    : 文献资产（含来源追溯 + 双维度可信度）
- MaterialStore : 材料卡片（聚合多篇文献的知识）
- ClaimStore    : 主张/数据点（可验证的最小知识单元）

可信度双维度：
- source_tier    : database / top_journal / journal / preprint / internal / llm_generated
- evidence_level : computation / literature / lab_validated / pilot / production
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import uuid

from sqlalchemy import text

from ..db import get_engine

logger = logging.getLogger(__name__)


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


# ─────────────────────────────────────────────────────────────────────────────
# 文献资产
# ─────────────────────────────────────────────────────────────────────────────

class PaperStore:
    """文献资产存储。"""

    VALID_SOURCE_TIERS = {
        "database", "top_journal", "journal", "preprint", "internal", "llm_generated",
    }

    def __init__(self):
        self.engine = get_engine()

    def upsert(self, paper: dict) -> dict:
        """按 DOI 去重插入或更新文献。返回含 paper_id 的完整记录。"""
        now = datetime.now(timezone.utc).isoformat()
        doi = (paper.get("doi") or "").strip() or None
        source_tier = paper.get("source_tier") or "journal"
        if source_tier not in self.VALID_SOURCE_TIERS:
            source_tier = "journal"

        # 若有 DOI，先查是否已存在
        if doi:
            existing = self.get_by_doi(doi)
            if existing:
                return existing

        paper_id = paper.get("paper_id") or _new_id("P")
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO knowledge.papers
                (paper_id, doi, title, authors, journal, year, abstract, keywords,
                 source, source_tier, url, citation_count, extra, created_at, updated_at)
                VALUES (:paper_id, :doi, :title, CAST(:authors AS JSONB), :journal, :year,
                        :abstract, CAST(:keywords AS JSONB), :source, :source_tier, :url,
                        :citation_count, CAST(:extra AS JSONB), :created_at, :updated_at)
                ON CONFLICT (paper_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    authors = EXCLUDED.authors,
                    journal = EXCLUDED.journal,
                    year = EXCLUDED.year,
                    abstract = EXCLUDED.abstract,
                    keywords = EXCLUDED.keywords,
                    source_tier = EXCLUDED.source_tier,
                    url = EXCLUDED.url,
                    citation_count = EXCLUDED.citation_count,
                    extra = EXCLUDED.extra,
                    updated_at = EXCLUDED.updated_at
                """),
                {
                    "paper_id": paper_id,
                    "doi": doi,
                    "title": paper.get("title", ""),
                    "authors": json.dumps(paper.get("authors", []), ensure_ascii=False),
                    "journal": paper.get("journal", ""),
                    "year": paper.get("year"),
                    "abstract": paper.get("abstract", ""),
                    "keywords": json.dumps(paper.get("keywords", []), ensure_ascii=False),
                    "source": paper.get("source", "unknown"),
                    "source_tier": source_tier,
                    "url": paper.get("url", ""),
                    "citation_count": paper.get("citation_count", 0),
                    "extra": json.dumps(paper.get("extra", {}), ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return self.get(paper_id)

    def get(self, paper_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""SELECT paper_id, doi, title, authors, journal, year, abstract,
                       keywords, source, source_tier, url, citation_count, extra,
                       created_at, updated_at
                FROM knowledge.papers WHERE paper_id=:paper_id"""),
                {"paper_id": paper_id},
            ).mappings().first()
        if row is None:
            return None
        return self._row_to_dict(row)

    def get_by_doi(self, doi: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""SELECT paper_id, doi, title, authors, journal, year, abstract,
                       keywords, source, source_tier, url, citation_count, extra,
                       created_at, updated_at
                FROM knowledge.papers WHERE doi=:doi"""),
                {"doi": doi},
            ).mappings().first()
        if row is None:
            return None
        return self._row_to_dict(row)

    def search(
        self,
        query: str = "",
        source: str = "",
        source_tier: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """关键词 + 来源筛选检索（使用 PostgreSQL 全文索引）。"""
        where_parts = []
        params: dict = {"limit": limit, "offset": offset}
        if query:
            where_parts.append(
                "(to_tsvector('simple', title) @@ plainto_tsquery('simple', :query)"
                " OR abstract ILIKE :like_query)"
            )
            params["query"] = query
            params["like_query"] = f"%{query}%"
        if source:
            where_parts.append("source = :source")
            params["source"] = source
        if source_tier:
            where_parts.append("source_tier = :source_tier")
            params["source_tier"] = source_tier

        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        sql = f"""SELECT paper_id, doi, title, authors, journal, year, abstract,
                   keywords, source, source_tier, url, citation_count, extra,
                   created_at, updated_at
            FROM knowledge.papers
            {where_clause}
            ORDER BY year DESC NULLS LAST, citation_count DESC, created_at DESC
            LIMIT :limit OFFSET :offset"""
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return [self._row_to_dict(r) for r in rows]

    def count(self, query: str = "", source: str = "", source_tier: str = "") -> int:
        where_parts = []
        params: dict = {}
        if query:
            where_parts.append(
                "(to_tsvector('simple', title) @@ plainto_tsquery('simple', :query)"
                " OR abstract ILIKE :like_query)"
            )
            params["query"] = query
            params["like_query"] = f"%{query}%"
        if source:
            where_parts.append("source = :source")
            params["source"] = source
        if source_tier:
            where_parts.append("source_tier = :source_tier")
            params["source_tier"] = source_tier
        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT count(*) AS c FROM knowledge.papers {where_clause}"),
                params,
            ).mappings().first()
        return row["c"] if row else 0

    def delete(self, paper_id: str) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM knowledge.papers WHERE paper_id=:paper_id"),
                {"paper_id": paper_id},
            )
        return result.rowcount > 0

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "paper_id": row["paper_id"],
            "doi": row["doi"] or "",
            "title": row["title"],
            "authors": row["authors"] or [],
            "journal": row["journal"] or "",
            "year": row["year"],
            "abstract": row["abstract"] or "",
            "keywords": row["keywords"] or [],
            "source": row["source"],
            "source_tier": row["source_tier"],
            "url": row["url"] or "",
            "citation_count": row["citation_count"] or 0,
            "extra": row["extra"] or {},
            "created_at": _iso(row["created_at"]),
            "updated_at": _iso(row["updated_at"]),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 材料卡片
# ─────────────────────────────────────────────────────────────────────────────

class MaterialStore:
    """材料卡片存储：聚合多篇文献的材料知识。"""

    VALID_EVIDENCE_LEVELS = {
        "computation", "literature", "lab_validated", "pilot", "production",
    }

    def __init__(self):
        self.engine = get_engine()

    def upsert(self, material: dict) -> dict:
        """按 canonical_name 去重插入或更新材料卡片。"""
        now = datetime.now(timezone.utc).isoformat()
        canonical_name = (material.get("canonical_name") or "").strip()
        if not canonical_name:
            raise ValueError("canonical_name 不能为空")

        evidence_level = material.get("evidence_level") or "literature"
        if evidence_level not in self.VALID_EVIDENCE_LEVELS:
            evidence_level = "literature"

        existing = self.get_by_name(canonical_name)
        if existing:
            # 合并 aliases 和 properties
            merged_aliases = set(existing.get("aliases", []))
            merged_aliases.update(material.get("aliases", []))
            merged_props = dict(existing.get("properties", {}))
            merged_props.update(material.get("properties", {}))

            with self.engine.begin() as conn:
                conn.execute(
                    text("""UPDATE knowledge.materials SET
                        aliases = CAST(:aliases AS JSONB),
                        category = COALESCE(:category, category),
                        description = COALESCE(:description, description),
                        properties = CAST(:properties AS JSONB),
                        source_tier = :source_tier,
                        evidence_level = :evidence_level,
                        updated_at = :updated_at
                    WHERE material_id = :material_id"""),
                    {
                        "material_id": existing["material_id"],
                        "aliases": json.dumps(sorted(merged_aliases), ensure_ascii=False),
                        "category": material.get("category") or None,
                        "description": material.get("description") or None,
                        "properties": json.dumps(merged_props, ensure_ascii=False),
                        "source_tier": material.get("source_tier") or existing["source_tier"],
                        "evidence_level": evidence_level,
                        "updated_at": now,
                    },
                )
            return self.get(existing["material_id"])

        material_id = material.get("material_id") or _new_id("M")
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO knowledge.materials
                (material_id, canonical_name, aliases, category, description, properties,
                 paper_count, claim_count, source_tier, evidence_level, created_at, updated_at)
                VALUES (:material_id, :canonical_name, CAST(:aliases AS JSONB), :category,
                        :description, CAST(:properties AS JSONB), :paper_count, :claim_count,
                        :source_tier, :evidence_level, :created_at, :updated_at)"""),
                {
                    "material_id": material_id,
                    "canonical_name": canonical_name,
                    "aliases": json.dumps(material.get("aliases", []), ensure_ascii=False),
                    "category": material.get("category", ""),
                    "description": material.get("description", ""),
                    "properties": json.dumps(material.get("properties", {}), ensure_ascii=False),
                    "paper_count": material.get("paper_count", 0),
                    "claim_count": material.get("claim_count", 0),
                    "source_tier": material.get("source_tier", "journal"),
                    "evidence_level": evidence_level,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return self.get(material_id)

    def get(self, material_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""SELECT material_id, canonical_name, aliases, category, description,
                       properties, paper_count, claim_count, source_tier, evidence_level,
                       created_at, updated_at
                FROM knowledge.materials WHERE material_id=:material_id"""),
                {"material_id": material_id},
            ).mappings().first()
        if row is None:
            return None
        return self._row_to_dict(row)

    def get_by_name(self, canonical_name: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""SELECT material_id, canonical_name, aliases, category, description,
                       properties, paper_count, claim_count, source_tier, evidence_level,
                       created_at, updated_at
                FROM knowledge.materials WHERE canonical_name=:canonical_name"""),
                {"canonical_name": canonical_name},
            ).mappings().first()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list(
        self,
        query: str = "",
        category: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        where_parts = []
        params: dict = {"limit": limit, "offset": offset}
        if query:
            where_parts.append(
                "(canonical_name ILIKE :q OR EXISTS ("
                "  SELECT 1 FROM jsonb_array_elements_text(aliases) a WHERE a ILIKE :q))"
            )
            params["q"] = f"%{query}%"
        if category:
            where_parts.append("category = :category")
            params["category"] = category
        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        sql = f"""SELECT material_id, canonical_name, aliases, category, description,
                   properties, paper_count, claim_count, source_tier, evidence_level,
                   created_at, updated_at
            FROM knowledge.materials {where_clause}
            ORDER BY paper_count DESC, updated_at DESC
            LIMIT :limit OFFSET :offset"""
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return [self._row_to_dict(r) for r in rows]

    def link_paper(self, material_id: str, paper_id: str, context: str = "") -> None:
        """建立文献-材料关联（幂等）。"""
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO knowledge.paper_materials (paper_id, material_id, mention_context)
                VALUES (:paper_id, :material_id, :context)
                ON CONFLICT (paper_id, material_id) DO NOTHING"""),
                {"paper_id": paper_id, "material_id": material_id, "context": context},
            )
            # 更新计数
            conn.execute(
                text("""UPDATE knowledge.materials SET paper_count = (
                    SELECT count(*) FROM knowledge.paper_materials WHERE material_id=:material_id
                ), updated_at = NOW() WHERE material_id=:material_id"""),
                {"material_id": material_id},
            )

    def list_papers(self, material_id: str, limit: int = 50) -> list[dict]:
        """列出关联的文献。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""SELECT p.paper_id, p.doi, p.title, p.authors, p.journal, p.year,
                       p.abstract, p.keywords, p.source, p.source_tier, p.url,
                       p.citation_count, p.extra, p.created_at, p.updated_at
                FROM knowledge.papers p
                JOIN knowledge.paper_materials pm ON p.paper_id = pm.paper_id
                WHERE pm.material_id = :material_id
                ORDER BY p.year DESC NULLS LAST, p.citation_count DESC
                LIMIT :limit"""),
                {"material_id": material_id, "limit": limit},
            ).mappings().all()
        return [PaperStore._row_to_dict(r) for r in rows]

    def delete(self, material_id: str) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM knowledge.materials WHERE material_id=:material_id"),
                {"material_id": material_id},
            )
        return result.rowcount > 0

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "material_id": row["material_id"],
            "canonical_name": row["canonical_name"],
            "aliases": row["aliases"] or [],
            "category": row["category"] or "",
            "description": row["description"] or "",
            "properties": row["properties"] or {},
            "paper_count": row["paper_count"] or 0,
            "claim_count": row["claim_count"] or 0,
            "source_tier": row["source_tier"] or "journal",
            "evidence_level": row["evidence_level"] or "literature",
            "created_at": _iso(row["created_at"]),
            "updated_at": _iso(row["updated_at"]),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 主张 / 数据点
# ─────────────────────────────────────────────────────────────────────────────

class ClaimStore:
    """主张/数据点存储：材料的可验证知识单元。"""

    VALID_CLAIM_TYPES = {
        "property",      # 性能主张（如离子电导率 1.5e-4 S/cm）
        "synthesis",     # 合成方法主张
        "application",   # 应用场景主张
        "comparison",    # 对比结论
        "mechanism",     # 机制解释
        "general",       # 其他
    }

    def __init__(self):
        self.engine = get_engine()

    def upsert(self, claim: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        claim_type = claim.get("claim_type") or "general"
        if claim_type not in self.VALID_CLAIM_TYPES:
            claim_type = "general"

        source_tier = claim.get("source_tier") or "journal"
        evidence_level = claim.get("evidence_level") or "literature"

        claim_id = claim.get("claim_id") or _new_id("C")
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO knowledge.claims
                (claim_id, material_id, claim_type, subject, predicate, value, unit,
                 numeric_value, claim_text, source_paper_id, source_tier, evidence_level,
                 confidence, extra, created_at, updated_at)
                VALUES (:claim_id, :material_id, :claim_type, :subject, :predicate, :value,
                        :unit, :numeric_value, :claim_text, :source_paper_id, :source_tier,
                        :evidence_level, :confidence, CAST(:extra AS JSONB), :created_at, :updated_at)
                ON CONFLICT (claim_id) DO UPDATE SET
                    claim_text = EXCLUDED.claim_text,
                    value = EXCLUDED.value,
                    unit = EXCLUDED.unit,
                    numeric_value = EXCLUDED.numeric_value,
                    source_tier = EXCLUDED.source_tier,
                    evidence_level = EXCLUDED.evidence_level,
                    confidence = EXCLUDED.confidence,
                    extra = EXCLUDED.extra,
                    updated_at = EXCLUDED.updated_at
                """),
                {
                    "claim_id": claim_id,
                    "material_id": claim.get("material_id"),
                    "claim_type": claim_type,
                    "subject": claim.get("subject", ""),
                    "predicate": claim.get("predicate", ""),
                    "value": claim.get("value", ""),
                    "unit": claim.get("unit", ""),
                    "numeric_value": claim.get("numeric_value"),
                    "claim_text": claim.get("claim_text", ""),
                    "source_paper_id": claim.get("source_paper_id"),
                    "source_tier": source_tier,
                    "evidence_level": evidence_level,
                    "confidence": claim.get("confidence", 0.5),
                    "extra": json.dumps(claim.get("extra", {}), ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            # 更新材料卡片的 claim 计数
            if claim.get("material_id"):
                conn.execute(
                    text("""UPDATE knowledge.materials SET claim_count = (
                        SELECT count(*) FROM knowledge.claims WHERE material_id=:material_id
                    ), updated_at = NOW() WHERE material_id=:material_id"""),
                    {"material_id": claim["material_id"]},
                )
        return self.get(claim_id)

    def get(self, claim_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""SELECT claim_id, material_id, claim_type, subject, predicate, value,
                       unit, numeric_value, claim_text, source_paper_id, source_tier,
                       evidence_level, confidence, extra, created_at, updated_at
                FROM knowledge.claims WHERE claim_id=:claim_id"""),
                {"claim_id": claim_id},
            ).mappings().first()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_by_material(
        self,
        material_id: str,
        claim_type: str = "",
        limit: int = 100,
    ) -> list[dict]:
        where_parts = ["material_id = :material_id"]
        params: dict = {"material_id": material_id, "limit": limit}
        if claim_type:
            where_parts.append("claim_type = :claim_type")
            params["claim_type"] = claim_type
        sql = f"""SELECT claim_id, material_id, claim_type, subject, predicate, value,
                   unit, numeric_value, claim_text, source_paper_id, source_tier,
                   evidence_level, confidence, extra, created_at, updated_at
            FROM knowledge.claims
            WHERE {' AND '.join(where_parts)}
            ORDER BY confidence DESC, created_at DESC
            LIMIT :limit"""
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return [self._row_to_dict(r) for r in rows]

    def delete(self, claim_id: str) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM knowledge.claims WHERE claim_id=:claim_id"),
                {"claim_id": claim_id},
            )
        return result.rowcount > 0

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "claim_id": row["claim_id"],
            "material_id": row["material_id"] or "",
            "claim_type": row["claim_type"],
            "subject": row["subject"],
            "predicate": row["predicate"],
            "value": row["value"] or "",
            "unit": row["unit"] or "",
            "numeric_value": row["numeric_value"],
            "claim_text": row["claim_text"],
            "source_paper_id": row["source_paper_id"] or "",
            "source_tier": row["source_tier"],
            "evidence_level": row["evidence_level"],
            "confidence": row["confidence"] or 0.5,
            "extra": row["extra"] or {},
            "created_at": _iso(row["created_at"]),
            "updated_at": _iso(row["updated_at"]),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 单例
# ─────────────────────────────────────────────────────────────────────────────

_paper_store: PaperStore | None = None
_material_store: MaterialStore | None = None
_claim_store: ClaimStore | None = None


def get_paper_store() -> PaperStore:
    global _paper_store
    if _paper_store is None:
        _paper_store = PaperStore()
    return _paper_store


def get_material_store() -> MaterialStore:
    global _material_store
    if _material_store is None:
        _material_store = MaterialStore()
    return _material_store


def get_claim_store() -> ClaimStore:
    global _claim_store
    if _claim_store is None:
        _claim_store = ClaimStore()
    return _claim_store
