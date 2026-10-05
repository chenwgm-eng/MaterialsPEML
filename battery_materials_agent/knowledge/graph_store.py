"""Knowledge graph PostgreSQL storage.

Stores graphs built by LiteratureResearcherAgent.build_knowledge_graph():
- save_graph: persist a graph snapshot with metadata
- get_graph: load a single graph by graph_id
- list_graphs: list saved graphs (most recent first)
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid
import logging

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


class KnowledgeGraphStore:
    """知识图谱 PostgreSQL 持久化存储。"""

    def __init__(self, db_path: str | None = None):
        # db_path 参数保留以兼容旧调用方，迁移至 PostgreSQL 后已忽略，统一使用全局 Engine。
        self.engine = get_engine()

    def save_graph(
        self,
        graph: dict,
        name: str = "",
        query: str = "",
        created_by: str = "",
        paper_count: int = 0,
    ) -> dict:
        """保存知识图谱快照。

        Args:
            graph: {nodes: [...], edges: [...]}
            name: 图谱名称（如 "LLZO solid electrolyte 知识图谱"）
            query: 触发该图谱的检索关键词
            created_by: 创建者标识
            paper_count: 该图谱基于的文献数量

        Returns:
            保存后的图谱元数据（含 graph_id / created_at）
        """
        graph_id = f"KG-{uuid.uuid4().hex[:10].upper()}"
        created_at = datetime.now(timezone.utc).isoformat()
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        display_name = name or f"知识图谱 {created_at[:10]}"

        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO knowledge.knowledge_graphs
                (graph_id, name, query, nodes_json, edges_json,
                 node_count, edge_count, paper_count, created_by, created_at)
                VALUES (:graph_id, :name, :query, CAST(:nodes_json AS JSONB), CAST(:edges_json AS JSONB),
                        :node_count, :edge_count, :paper_count, :created_by, :created_at)"""),
                {
                    "graph_id": graph_id,
                    "name": display_name,
                    "query": query,
                    "nodes_json": json.dumps(nodes, ensure_ascii=False),
                    "edges_json": json.dumps(edges, ensure_ascii=False),
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                    "paper_count": paper_count,
                    "created_by": created_by,
                    "created_at": created_at,
                },
            )

        return {
            "graph_id": graph_id,
            "name": display_name,
            "query": query,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "paper_count": paper_count,
            "created_by": created_by,
            "created_at": created_at,
        }

    def get_graph(self, graph_id: str) -> dict | None:
        """获取单个知识图谱（含完整节点与边）。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT graph_id, name, query, nodes_json, edges_json, "
                     "node_count, edge_count, paper_count, created_by, created_at "
                     "FROM knowledge.knowledge_graphs WHERE graph_id=:graph_id"),
                {"graph_id": graph_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_graph(row, include_data=True)

    def list_graphs(self, limit: int = 50) -> list[dict]:
        """列出知识图谱元数据（不含节点/边数据，按创建时间倒序）。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT graph_id, name, query, nodes_json, edges_json, "
                     "node_count, edge_count, paper_count, created_by, created_at "
                     "FROM knowledge.knowledge_graphs ORDER BY created_at DESC LIMIT :limit"),
                {"limit": limit},
            ).fetchall()
        return [self._row_to_graph(r, include_data=False) for r in rows]

    def update_graph(
        self,
        graph_id: str,
        graph: dict,
        name: str = "",
        query: str = "",
        created_by: str = "",
        paper_count: int = 0,
    ) -> dict | None:
        """增量更新已有知识图谱（合并节点/边而非覆盖）。

        Args:
            graph_id: 要更新的图谱 ID
            graph: 新的节点/边数据 {nodes: [...], edges: [...]}
            name: 图谱名称（为空则保留原名）
            query: 触发更新的检索关键词
            created_by: 更新者标识
            paper_count: 新增文献数量

        Returns:
            更新后的图谱元数据；若图谱不存在则返回 None
        """
        existing = self.get_graph(graph_id)
        if existing is None:
            return None

        merged = self._merge_graph(existing, graph)
        display_name = name or existing.get("name", "")
        now = datetime.now(timezone.utc).isoformat()

        with self.engine.begin() as conn:
            # created_at 保持首次创建时间（此前被覆写为 now，排序失真）
            conn.execute(
                text("""UPDATE knowledge.knowledge_graphs
                SET name=:name, query=:query,
                    nodes_json=CAST(:nodes_json AS JSONB),
                    edges_json=CAST(:edges_json AS JSONB),
                    node_count=:node_count, edge_count=:edge_count,
                    paper_count=paper_count + :paper_count,
                    created_by=:created_by
                WHERE graph_id=:graph_id"""),
                {
                    "graph_id": graph_id,
                    "name": display_name,
                    "query": query or existing.get("query", ""),
                    "nodes_json": json.dumps(merged["nodes"], ensure_ascii=False),
                    "edges_json": json.dumps(merged["edges"], ensure_ascii=False),
                    "node_count": len(merged["nodes"]),
                    "edge_count": len(merged["edges"]),
                    "paper_count": paper_count,
                    "created_by": created_by or existing.get("created_by", ""),
                },
            )

        return {
            "graph_id": graph_id,
            "name": display_name,
            "query": query or existing.get("query", ""),
            "node_count": len(merged["nodes"]),
            "edge_count": len(merged["edges"]),
            "paper_count": existing.get("paper_count", 0) + paper_count,
            "created_by": created_by or existing.get("created_by", ""),
            "created_at": now,
        }

    @staticmethod
    def _merge_graph(existing: dict, new: dict) -> dict:
        """合并已有图谱与新图谱，相同节点/边做增量合并而非覆盖。"""
        nodes: dict[str, dict] = {}
        edges: dict[tuple[str, str, str], dict] = {}

        # 先加载已有图谱
        for node in existing.get("nodes", []):
            node_id = node.get("id", "")
            if node_id:
                nodes[node_id] = node
        for edge in existing.get("edges", []):
            key = (edge.get("source", ""), edge.get("target", ""), edge.get("label", ""))
            edges[key] = edge

        # 合并新节点
        for node in new.get("nodes", []):
            node_id = node.get("id", "")
            if not node_id:
                continue
            if node_id not in nodes:
                nodes[node_id] = node
            else:
                # 合并属性：papers 累加，paper_titles 去重追加
                old_props = nodes[node_id].get("properties", {})
                new_props = node.get("properties", {})
                old_props["papers"] = old_props.get("papers", 0) + new_props.get("papers", 0)
                old_titles = set(old_props.get("paper_titles", []))
                old_titles.update(new_props.get("paper_titles", []))
                old_props["paper_titles"] = sorted(old_titles)
                old_sources = set(old_props.get("sources", []))
                old_sources.update(new_props.get("sources", []))
                old_props["sources"] = sorted(old_sources)
                # 置信度：取较高者
                confidence_order = {"high": 3, "medium": 2, "low": 1}
                old_conf = old_props.get("confidence", "low")
                new_conf = new_props.get("confidence", "low")
                if confidence_order.get(new_conf, 0) > confidence_order.get(old_conf, 0):
                    old_props["confidence"] = new_conf
                nodes[node_id]["properties"] = old_props

        # 合并新边
        for edge in new.get("edges", []):
            key = (edge.get("source", ""), edge.get("target", ""), edge.get("label", ""))
            if key not in edges:
                edges[key] = edge
            else:
                edges[key]["weight"] = edges[key].get("weight", 0) + edge.get("weight", 0)
                old_sources = set(edges[key].get("sources", []))
                old_sources.update(edge.get("sources", []))
                edges[key]["sources"] = sorted(old_sources)

        return {
            "nodes": list(nodes.values()),
            "edges": list(edges.values()),
        }

    def delete_graph(self, graph_id: str) -> bool:
        """删除指定知识图谱。"""
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM knowledge.knowledge_graphs WHERE graph_id=:graph_id"),
                {"graph_id": graph_id},
            )
        return cur.rowcount > 0

    @staticmethod
    def _row_to_graph(row, include_data: bool = False) -> dict:
        """将数据库行转换为图谱字典。include_data=False 时省略 nodes/edges 以节省传输。"""
        data = {
            "graph_id": row[0],
            "name": row[1],
            "query": row[2],
            "node_count": row[5] or 0,
            "edge_count": row[6] or 0,
            "paper_count": row[7] or 0,
            "created_by": row[8] or "",
            "created_at": _iso(row[9]),
        }
        if include_data:
            nodes = row[3] or []
            edges = row[4] or []
            data["nodes"] = nodes if isinstance(nodes, list) else json.loads(nodes or "[]")
            data["edges"] = edges if isinstance(edges, list) else json.loads(edges or "[]")
        return data


# 全局单例
_kg_store: KnowledgeGraphStore | None = None


def get_knowledge_graph_store() -> KnowledgeGraphStore:
    global _kg_store
    if _kg_store is None:
        _kg_store = KnowledgeGraphStore()
    return _kg_store
