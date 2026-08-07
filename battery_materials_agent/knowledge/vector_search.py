"""知识资产层语义向量检索（pgvector）。

依赖链（任一不可用即视为"未启用"）：
1. pgvector 扩展（pg_extension.extname='vector'）已安装；
2. knowledge 资产表的 embedding 列为 vector(1024)（非 TEXT 占位）；
3. InternLM 提供 OpenAI 兼容的 /embeddings 接口，可生成查询向量。

当以上任一条件不满足时，向量检索不可用，调用方应退化为一律返回空检索
（不静默回退到关键词检索），避免给出语义上不可靠的结果。
"""
from __future__ import annotations

import logging
import os

import requests
from sqlalchemy import text

from ..config import get_config
from ..db import get_engine

logger = logging.getLogger(__name__)

# 文本向量化模型（InternLM 兼容模型名，可用 EMBEDDING_MODEL 环境变量覆盖）
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intern-xembedding-pro")


def pgvector_enabled(engine=None) -> bool:
    """检测 pgvector 扩展 + embedding 列是否为 vector 类型。"""
    engine = engine or get_engine()
    try:
        with engine.connect() as conn:
            ext = conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname='vector'")
            ).scalar()
            if not ext:
                return False
            # 检查 papers（代表资产表）embedding 列是否为 vector 类型
            row = conn.execute(
                text("""
                    SELECT udt_name FROM information_schema.columns
                    WHERE table_schema='knowledge' AND table_name='papers'
                      AND column_name='embedding'
                """)
            ).scalar()
            return row == "vector"
    except Exception as exc:  # noqa: BLE001
        logger.warning("pgvector 可用性检测失败，视为未启用: %s", exc)
        return False


def embed_query(text: str) -> list[float] | None:
    """通过 InternLM /embeddings 生成查询向量；不可用时返回 None。"""
    if not text or not text.strip():
        return None
    cfg = get_config()
    if not cfg.internlm.enabled or not cfg.internlm.api_key:
        logger.info("InternLM embedding 未配置，向量检索不可用")
        return None
    base_url = cfg.internlm.base_url.rstrip("/")
    endpoint = f"{base_url}/embeddings"
    api_key = cfg.internlm.api_key.get_secret_value()
    try:
        resp = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": EMBEDDING_MODEL, "input": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        embedding = data["data"][0]["embedding"]
        if not isinstance(embedding, list) or not embedding:
            return None
        return [float(x) for x in embedding]
    except Exception as exc:  # noqa: BLE001
        logger.warning("查询向量生成失败，向量检索不可用: %s", exc)
        return None


def semantic_paper_search(
    query: str,
    source: str = "",
    source_tier: str = "",
    limit: int = 20,
    engine=None,
) -> list[dict]:
    """按语义相似度检索文献（cosine）。

    返回结构复用 PaperStore._row_to_dict 的字段。未启用 pgvector 或
    无法生成查询向量时返回空列表（退化空检索）。
    """
    engine = engine or get_engine()
    if not pgvector_enabled(engine):
        logger.info("pgvector 未启用，语义检索退化为空检索")
        return []
    vec = embed_query(query)
    if vec is None:
        logger.info("无法生成查询向量，语义检索退化为空检索")
        return []

    params: dict = {"vec": f"[{','.join(repr(v) for v in vec)}]", "limit": limit}
    where_parts = ["embedding IS NOT NULL"]
    if source:
        where_parts.append("source = :source")
        params["source"] = source
    if source_tier:
        where_parts.append("source_tier = :source_tier")
        params["source_tier"] = source_tier

    sql = f"""SELECT paper_id, doi, title, authors, journal, year, abstract,
                   keywords, source, source_tier, url, citation_count, extra,
                   created_at, updated_at,
                   (embedding <=> CAST(:vec AS vector)) AS similarity_distance
            FROM knowledge.papers
            WHERE {' AND '.join(where_parts)}
            ORDER BY embedding <=> CAST(:vec AS vector) ASC
            LIMIT :limit"""

    from .asset_store import PaperStore
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        results = []
        for r in rows:
            d = PaperStore._row_to_dict(r)
            d["semantic_similarity"] = round(
                max(0.0, 1.0 - float(r["similarity_distance"])), 4
            )
            results.append(d)
        return results
    except Exception as exc:  # noqa: BLE001
        logger.warning("语义检索执行失败，退化为空检索: %s", exc)
        return []