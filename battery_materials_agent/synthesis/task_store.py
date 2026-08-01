"""合成路径规划任务的异步持久化层。

解决产品评审 P0 问题：ASKCOS 逆合成服务响应慢导致前端 15s 超时。
改造为异步任务模式：提交后立即返回 task_id，后台执行，前端轮询结果。
每一次规划尝试（成功/失败）均持久化，作为首页"合成路线"KPI 与
服务健康度统计的统一数据源。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

from ..db import get_engine
from ..mdm.reference_dict import ReferenceDictStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value) -> str:
    """将 datetime 或字符串转换为 ISO 字符串；None 返回空字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class SynthesisTaskStore:
    """合成规划任务的 PostgreSQL 持久化。"""

    def __init__(self, db_path: str = ""):
        # db_path 参数保留以兼容旧调用方，迁移至 PostgreSQL 后已忽略，统一使用全局 Engine。
        self.engine = get_engine()
        self._mdm = ReferenceDictStore()

    def _validate_status(self, status: str) -> None:
        """校验状态码必须存在于 MDM 主数据 (domain='synthesis_task') 中。"""
        if self._mdm.get_status_code("synthesis_task", status) is None:
            raise ValueError(f"无效状态 {status!r}，不在 MDM 主数据 (domain='synthesis_task') 中")

    def create_task(self, smiles: str, num_routes: int = 3, source: str = "auto",
                    scenario_id: str = "", candidate_id: str = "") -> str:
        # scenario_id 参数保留以兼容旧调用方签名，alembic 中 synthesis.synthesis_tasks 表无此列。
        # candidate_id 由 0021 迁移新增，便于按候选回溯合成历史。
        self._validate_status("pending")
        task_id = uuid.uuid4().hex[:12]
        now = _now()
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO synthesis.synthesis_tasks
                (task_id, smiles, num_routes, status, source, created_at, updated_at, candidate_id)
                VALUES (:task_id, :smiles, :num_routes, 'pending', :source, :created_at, :updated_at, :candidate_id)"""),
                {
                    "task_id": task_id, "smiles": smiles,
                    "num_routes": num_routes, "source": source,
                    "created_at": now, "updated_at": now,
                    "candidate_id": candidate_id,
                },
            )
        return task_id

    def complete_task(self, task_id: str, result: dict, duration_ms: int):
        self._validate_status("success")
        with self.engine.begin() as conn:
            conn.execute(
                text("""UPDATE synthesis.synthesis_tasks
                SET status='success', result_json=CAST(:result_json AS JSONB), updated_at=:updated_at, duration_ms=:duration_ms
                WHERE task_id=:task_id"""),
                {
                    "result_json": json.dumps(result, ensure_ascii=False),
                    "updated_at": _now(), "duration_ms": duration_ms,
                    "task_id": task_id,
                },
            )

    def fail_task(self, task_id: str, error: str, duration_ms: int):
        self._validate_status("failed")
        with self.engine.begin() as conn:
            conn.execute(
                text("""UPDATE synthesis.synthesis_tasks
                SET status='failed', error=:error, updated_at=:updated_at, duration_ms=:duration_ms
                WHERE task_id=:task_id"""),
                {
                    "error": error[:2000], "updated_at": _now(),
                    "duration_ms": duration_ms, "task_id": task_id,
                },
            )

    def mark_running(self, task_id: str):
        self._validate_status("running")
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE synthesis.synthesis_tasks SET status='running', updated_at=:updated_at WHERE task_id=:task_id"),
                {"updated_at": _now(), "task_id": task_id},
            )

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""SELECT task_id, smiles, num_routes, status, source, result_json,
                          error, created_at, updated_at, duration_ms, candidate_id
                   FROM synthesis.synthesis_tasks WHERE task_id=:task_id"""),
                {"task_id": task_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""SELECT task_id, smiles, num_routes, status, source, result_json,
                          error, created_at, updated_at, duration_ms, candidate_id
                   FROM synthesis.synthesis_tasks ORDER BY created_at DESC LIMIT :limit"""),
                {"limit": limit},
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def list_by_candidate(self, candidate_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """按 candidate_id 查询合成任务历史（0021 新增）。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""SELECT task_id, smiles, num_routes, status, source, result_json,
                          error, created_at, updated_at, duration_ms, candidate_id
                   FROM synthesis.synthesis_tasks
                   WHERE candidate_id = :candidate_id
                   ORDER BY created_at DESC LIMIT :limit"""),
                {"candidate_id": candidate_id, "limit": limit},
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_latest_success_by_candidate(self, candidate_id: str) -> Optional[dict[str, Any]]:
        """获取候选下最新一条成功的合成任务结果（含 routes）。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""SELECT task_id, smiles, num_routes, status, source, result_json,
                          error, created_at, updated_at, duration_ms, candidate_id
                   FROM synthesis.synthesis_tasks
                   WHERE candidate_id = :candidate_id AND status = 'success'
                   ORDER BY created_at DESC LIMIT 1"""),
                {"candidate_id": candidate_id},
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_stats(self) -> dict[str, Any]:
        """统计：总任务数、成功/失败数、累计生成路线数、近24h失败率。"""
        with self.engine.connect() as conn:
            total = conn.execute(
                text("SELECT COUNT(*) FROM synthesis.synthesis_tasks")
            ).fetchone()[0]
            by_status = {
                r[0]: r[1]
                for r in conn.execute(
                    text("SELECT status, COUNT(*) FROM synthesis.synthesis_tasks GROUP BY status")
                ).fetchall()
            }
            routes_generated = 0
            for (result_json,) in conn.execute(
                text("SELECT result_json FROM synthesis.synthesis_tasks WHERE status='success'")
            ).fetchall():
                try:
                    if isinstance(result_json, dict):
                        routes_generated += int(result_json.get("count", 0))
                    else:
                        routes_generated += int(json.loads(result_json or "{}").get("count", 0))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        success = by_status.get("success", 0)
        failed = by_status.get("failed", 0)
        finished = success + failed
        return {
            "total_tasks": total,
            "success_tasks": success,
            "failed_tasks": failed,
            "routes_generated": routes_generated,
            # 服务可用率：已完成任务中的成功占比（无任务时为 None，前端不展示告警）
            "success_rate": round(success / finished, 3) if finished else None,
        }

    def count_consecutive_failures(self) -> int:
        """统计最近连续失败次数（P1-2 触发条件C）。

        按创建时间倒序扫描，跳过尚未完结的 pending/running 任务，
        遇到第一个 success 即停止。
        """
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT status FROM synthesis.synthesis_tasks ORDER BY created_at DESC LIMIT 50")
            ).fetchall()
        streak = 0
        for (status,) in rows:
            if status in ("pending", "running"):
                continue
            if status == "failed":
                streak += 1
            else:
                break
        return streak

    @staticmethod
    def _row_to_dict(row) -> dict[str, Any]:
        result = None
        if row[5]:
            try:
                result = row[5] if isinstance(row[5], dict) else json.loads(row[5])
            except (json.JSONDecodeError, TypeError):
                result = None
        return {
            "task_id": row[0],
            "smiles": row[1],
            "num_routes": row[2],
            "scenario_id": "",  # alembic schema 无此列，保留 key 以兼容旧调用方
            "status": row[3],
            "source": row[4],
            "result": result,
            "error": row[6],
            "created_at": _iso(row[7]),
            "updated_at": _iso(row[8]),
            "duration_ms": row[9],
            # 0021 新增字段（旧查询结果可能不存在，使用安全取值）
            "candidate_id": (row[10] or "") if len(row) > 10 else "",
        }
