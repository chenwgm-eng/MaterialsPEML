"""统一 Agent 调用事件日志表（P1-2）。

解决产品评审发现的问题：委员会中心/控制平面/Agent 管理页数据完全空转，
用户无法在系统内查证"某个 Agent 在每一次闭环迭代中是否被调用、调用了
多少次、成功率如何"。

设计要点：
- 每次 ECML 步骤执行、合成规划等 Agent 能力调用，均写入一条结构化事件：
  agent_id / invoked_at / related_run_id / step / input_summary /
  output_summary / duration_ms / status / token_cost
- 控制平面"运行队列"与 Agent 管理页统计直接消费本表，不再维护独立空表
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

from ..db import get_engine


# 事件状态
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value) -> str:
    """将 datetime 或字符串转换为 ISO 字符串；None 返回空字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class AgentEventLog:
    """Agent 调用事件的 PostgreSQL 持久化。"""

    def __init__(self, db_path: str = ""):
        # db_path 参数保留以兼容旧调用方，迁移至 PostgreSQL 后已忽略，统一使用全局 Engine。
        self.engine = get_engine()

    def log_event(
        self,
        agent_id: str,
        agent_name: str = "",
        related_run_id: str = "",
        step: str = "",
        input_summary: Optional[dict] = None,
        output_summary: Optional[dict] = None,
        duration_ms: int = 0,
        status: str = STATUS_SUCCESS,
        token_cost: float = 0.0,
    ) -> str:
        """写入一条 Agent 调用事件，返回 event_id。"""
        event_id = uuid.uuid4().hex[:12]
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO agent_team.agent_events
                (event_id, agent_id, agent_name, related_run_id, step, invoked_at,
                 input_summary, output_summary, duration_ms, status, token_cost)
                VALUES (:event_id, :agent_id, :agent_name, :related_run_id, :step, :invoked_at,
                        CAST(:input_summary AS JSONB), CAST(:output_summary AS JSONB),
                        :duration_ms, :status, :token_cost)"""),
                {
                    "event_id": event_id,
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "related_run_id": related_run_id,
                    "step": step,
                    "invoked_at": _now(),
                    "input_summary": json.dumps(input_summary or {}, ensure_ascii=False),
                    "output_summary": json.dumps(output_summary or {}, ensure_ascii=False),
                    "duration_ms": duration_ms,
                    "status": status,
                    "token_cost": token_cost,
                },
            )
        return event_id

    def list_events(
        self,
        run_id: str = "",
        agent_id: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """查询事件（按调用时间倒序），支持按运行 ID / Agent ID 过滤。"""
        query = "SELECT * FROM agent_team.agent_events WHERE 1=1"
        params: dict[str, Any] = {}
        if run_id:
            query += " AND related_run_id = :run_id"
            params["run_id"] = run_id
        if agent_id:
            query += " AND agent_id = :agent_id"
            params["agent_id"] = agent_id
        query += " ORDER BY invoked_at DESC LIMIT :limit"
        params["limit"] = limit
        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def stats_by_agent(self) -> dict[str, dict[str, Any]]:
        """按 Agent 聚合调用统计：次数、成功率、平均耗时、最近调用时间。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""SELECT agent_id, agent_name,
                          COUNT(*) AS invocations,
                          SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS succeeded,
                          SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) AS failed,
                          AVG(duration_ms) AS avg_duration_ms,
                          SUM(token_cost) AS total_token_cost,
                          MAX(invoked_at) AS last_invoked_at
                   FROM agent_team.agent_events GROUP BY agent_id, agent_name""")
            ).fetchall()
        stats: dict[str, dict[str, Any]] = {}
        for agent_id, agent_name, total, succeeded, failed, avg_ms, tokens, last_at in rows:
            stats[agent_id] = {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "invocations": total,
                "succeeded": succeeded,
                "failed": failed,
                "success_rate": round(succeeded / total, 3) if total else None,
                "avg_duration_ms": int(avg_ms or 0),
                "total_token_cost": round(tokens or 0.0, 4),
                "last_invoked_at": _iso(last_at),
            }
        return stats

    @staticmethod
    def _loads(raw) -> dict:
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    def _row_to_dict(self, row) -> dict[str, Any]:
        return {
            "event_id": row[0],
            "agent_id": row[1],
            "agent_name": row[2],
            "related_run_id": row[3],
            "step": row[4],
            "invoked_at": _iso(row[5]),
            "input_summary": self._loads(row[6]),
            "output_summary": self._loads(row[7]),
            "duration_ms": row[8],
            "status": row[9],
            "token_cost": row[10],
        }
