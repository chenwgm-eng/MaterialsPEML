"""统一研发事件流水表（P3-1）。

解决产品评审提出的长期架构建议：建立统一的研发事件流水表，作为
首页看板"最近活动"、各模块历史记录、控制平面运行队列、委员会中心
案件触发的唯一数据源，替代各页面分头查询异构表（ecml_runs /
synthesis_tasks / experiment_orders）再合并的模式。

与 agent_events（Agent 调用粒度）的关系：
- agent_events 记录"某个 Agent 被调用了多少次、成功与否"（治理视角）
- research_events 记录"研发业务发生了什么"（业务视角）：一次材料发现、
  一次 ECML 闭环、一次合成规划、一张实验任务单，均为一条业务事件

设计要点：
- 五类业务事件：ecml_run / discovery / prediction / synthesis / experiment
- run_source 沿用 P0-4 数据隔离口径（production / test），默认查询排除 test
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

from ..db import get_engine


# 业务事件类型
EVENT_ECML_RUN = "ecml_run"          # ECML 闭环迭代运行
EVENT_DISCOVERY = "discovery"        # 材料发现（晶体/聚合物候选生成）
EVENT_PREDICTION = "prediction"      # 性质预测
EVENT_SYNTHESIS = "synthesis"        # 合成路径规划
EVENT_EXPERIMENT = "experiment"      # 实验任务单

# 事件状态
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_RUNNING = "running"

# 事件类型中文名（前端展示兜底，payload 中 title 优先）
EVENT_TYPE_LABELS = {
    EVENT_ECML_RUN: "闭环迭代",
    EVENT_DISCOVERY: "材料发现",
    EVENT_PREDICTION: "性质预测",
    EVENT_SYNTHESIS: "合成规划",
    EVENT_EXPERIMENT: "实验任务",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value) -> str:
    """将 datetime 或字符串转换为 ISO 字符串；None 返回空字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class ResearchEventStream:
    """统一研发事件流水的 PostgreSQL 持久化。"""

    def __init__(self, db_path: str = ""):
        # db_path 参数保留以兼容旧调用方，迁移至 PostgreSQL 后已忽略，统一使用全局 Engine。
        self.engine = get_engine()

    def log_event(
        self,
        event_type: str,
        run_id: str = "",
        title: str = "",
        summary: str = "",
        status: str = STATUS_SUCCESS,
        run_source: str = "production",
        payload: Optional[dict] = None,
    ) -> str:
        """写入一条研发业务事件，返回 event_id。"""
        event_id = uuid.uuid4().hex[:12]
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO agent_team.research_events
                (event_id, event_type, run_id, title, summary, status,
                 run_source, payload, created_at)
                VALUES (:event_id, :event_type, :run_id, :title, :summary, :status,
                        :run_source, CAST(:payload AS JSONB), :created_at)"""),
                {
                    "event_id": event_id,
                    "event_type": event_type,
                    "run_id": run_id,
                    "title": title,
                    "summary": summary,
                    "status": status,
                    "run_source": run_source,
                    "payload": json.dumps(payload or {}, ensure_ascii=False),
                    "created_at": _now(),
                },
            )
        return event_id

    def list_events(
        self,
        event_type: str = "",
        run_id: str = "",
        run_source: str = "production",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """查询事件（按时间倒序）。默认仅返回 production 数据，与首页/历史口径一致；
        run_source 传空串可返回全部（含 test），供数据治理页使用。"""
        query = "SELECT * FROM agent_team.research_events WHERE 1=1"
        params: dict[str, Any] = {}
        if event_type:
            query += " AND event_type = :event_type"
            params["event_type"] = event_type
        if run_id:
            query += " AND run_id = :run_id"
            params["run_id"] = run_id
        if run_source:
            query += " AND run_source = :run_source"
            params["run_source"] = run_source
        query += " ORDER BY created_at DESC LIMIT :limit"
        params["limit"] = limit
        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        """按事件类型聚合计数（production 口径），供首页看板/治理页使用。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""SELECT event_type,
                          COUNT(*) AS total,
                          SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS succeeded,
                          SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) AS failed
                   FROM agent_team.research_events WHERE run_source != 'test'
                   GROUP BY event_type""")
            ).fetchall()
            test_total = conn.execute(
                text("SELECT COUNT(*) FROM agent_team.research_events WHERE run_source = 'test'")
            ).fetchone()[0]
        by_type: dict[str, dict[str, int]] = {}
        for event_type, total, succeeded, failed in rows:
            by_type[event_type] = {
                "total": total,
                "succeeded": succeeded,
                "failed": failed,
            }
        return {"by_type": by_type, "test_total": test_total}

    def delete_by_run_id(self, run_id: str) -> int:
        """删除某运行关联的全部事件（跟随 ECML 运行删除/批量清理）。"""
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM agent_team.research_events WHERE run_id = :run_id"),
                {"run_id": run_id},
            )
        return cur.rowcount

    @staticmethod
    def _loads_payload(raw) -> dict:
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    def _row_to_dict(self, row) -> dict[str, Any]:
        payload_raw = row[7]
        payload = self._loads_payload(payload_raw)
        event_type = row[1]
        return {
            "event_id": row[0],
            "event_type": event_type,
            "event_type_label": EVENT_TYPE_LABELS.get(event_type, event_type),
            "run_id": row[2],
            "title": row[3],
            "summary": row[4],
            "status": row[5],
            "run_source": row[6],
            "payload": payload,
            "created_at": _iso(row[8]),
        }
