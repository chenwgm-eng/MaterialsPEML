"""Research Store — 研发请求与计划持久化（SQLAlchemy Engine）。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from ..db import get_engine
from .orchestrator import ResearchPlan, ResearchRequest


def _parse_json_field(value, default):
    """解析 JSON 字段，兼容 psycopg3 自动反序列化或返回原始字符串两种情况。"""
    if value is None:
        return default
    if isinstance(value, str):
        if not value:
            return default
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


class ResearchStore:
    """研发请求和计划的 SQLAlchemy 持久化。

    Schema 由 alembic 管理（hybrid.research_requests / research_plans /
    routing_outcomes / routing_policy_versions）。
    """

    def __init__(self, db_path: str | None = None):
        # db_path 参数已废弃：统一通过 get_engine() 获取 Engine。
        self.engine = get_engine()

    # ── ResearchRequest CRUD ────────────────────────────────

    def create_request(self, request: ResearchRequest) -> str:
        """创建研发请求，返回 request_id。"""
        if not request.request_id:
            request.request_id = str(uuid.uuid4())
        if not request.scenario_id:
            request.scenario_id = request.request_id
        now = datetime.now(timezone.utc).isoformat()
        created_at = request.created_at or now
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO hybrid.research_requests
                       (request_id, scenario_id, goal, material_scope, target_properties,
                        constraints, preference, user_id, project_id, task_id, execution_profile,
                        status, created_at, updated_at)
                       VALUES (:request_id, :scenario_id, :goal, :material_scope,
                               :target_properties, :constraints, :preference, :user_id,
                               :project_id, :task_id, :execution_profile, :status, :created_at, :updated_at)
                       ON CONFLICT (request_id) DO UPDATE SET
                           scenario_id = EXCLUDED.scenario_id,
                           goal = EXCLUDED.goal,
                           material_scope = EXCLUDED.material_scope,
                           target_properties = EXCLUDED.target_properties,
                           constraints = EXCLUDED.constraints,
                           preference = EXCLUDED.preference,
                           user_id = EXCLUDED.user_id,
                           project_id = EXCLUDED.project_id,
                           task_id = EXCLUDED.task_id,
                           execution_profile = EXCLUDED.execution_profile,
                           status = EXCLUDED.status,
                           updated_at = EXCLUDED.updated_at"""
                ),
                {
                    "request_id": request.request_id,
                    "scenario_id": request.scenario_id,
                    "goal": request.goal,
                    "material_scope": request.material_scope,
                    "target_properties": json.dumps(request.target_properties),
                    "constraints": json.dumps(request.constraints),
                    "preference": request.preference,
                    "user_id": request.user_id,
                    # FK 约束：空字符串需转为 NULL
                    "project_id": request.project_id or None,
                    "task_id": request.task_id or None,
                    "execution_profile": "standard",
                    "status": "draft",
                    "created_at": created_at,
                    "updated_at": now,
                },
            )
        return request.request_id

    def get_request(self, request_id: str) -> dict | None:
        """查询研发请求，返回字典。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM hybrid.research_requests WHERE request_id = :request_id"),
                {"request_id": request_id},
            ).mappings().first()
        if row is None:
            return None
        return self._row_to_request(row)

    def list_requests(self, limit: int = 50, status: str = None) -> list[dict]:
        """查询请求列表，支持 status 过滤。"""
        query = "SELECT * FROM hybrid.research_requests"
        params: dict[str, Any] = {}
        if status is not None:
            query += " WHERE status = :status"
            params["status"] = status
        query += " ORDER BY created_at DESC LIMIT :limit"
        params["limit"] = limit
        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).mappings().all()
        return [self._row_to_request(row) for row in rows]

    def update_request_status(self, request_id: str, status: str) -> None:
        """更新请求状态。"""
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE hybrid.research_requests SET status = :status, updated_at = :updated_at "
                    "WHERE request_id = :request_id"
                ),
                {"status": status, "updated_at": now, "request_id": request_id},
            )

    # ── ResearchPlan CRUD ───────────────────────────────────

    def create_plan(self, plan: ResearchPlan) -> str:
        """创建研发计划，返回 plan_id。"""
        if not plan.plan_id:
            plan.plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO hybrid.research_plans
                       (plan_id, request_id, execution_profile, steps, rationale,
                        estimated_budget, risk_summary, capabilities_needed, status,
                        created_at, updated_at)
                       VALUES (:plan_id, :request_id, :execution_profile, :steps, :rationale,
                               :estimated_budget, :risk_summary, :capabilities_needed, :status,
                               :created_at, :updated_at)
                       ON CONFLICT (plan_id) DO UPDATE SET
                           request_id = EXCLUDED.request_id,
                           execution_profile = EXCLUDED.execution_profile,
                           steps = EXCLUDED.steps,
                           rationale = EXCLUDED.rationale,
                           estimated_budget = EXCLUDED.estimated_budget,
                           risk_summary = EXCLUDED.risk_summary,
                           capabilities_needed = EXCLUDED.capabilities_needed,
                           status = EXCLUDED.status,
                           updated_at = EXCLUDED.updated_at"""
                ),
                {
                    "plan_id": plan.plan_id,
                    "request_id": plan.request_id,
                    "execution_profile": plan.execution_profile,
                    "steps": json.dumps([s.model_dump() for s in plan.steps]),
                    "rationale": plan.rationale,
                    "estimated_budget": json.dumps(plan.estimated_budget),
                    "risk_summary": plan.risk_summary,
                    "capabilities_needed": json.dumps(plan.capabilities_needed),
                    "status": plan.status,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return plan.plan_id

    def get_plan(self, plan_id: str) -> dict | None:
        """查询研发计划，返回字典。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM hybrid.research_plans WHERE plan_id = :plan_id"),
                {"plan_id": plan_id},
            ).mappings().first()
        if row is None:
            return None
        return self._row_to_plan(row)

    def get_plans_by_request(self, request_id: str) -> list[dict]:
        """查询指定请求的所有计划。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM hybrid.research_plans WHERE request_id = :request_id "
                    "ORDER BY created_at ASC"
                ),
                {"request_id": request_id},
            ).mappings().all()
        return [self._row_to_plan(row) for row in rows]

    def update_plan_status(self, plan_id: str, status: str) -> None:
        """更新计划状态。"""
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE hybrid.research_plans SET status = :status, updated_at = :updated_at "
                    "WHERE plan_id = :plan_id"
                ),
                {"status": status, "updated_at": now, "plan_id": plan_id},
            )

    # ── RoutingOutcome CRUD ─────────────────────────────────

    def create_outcome(self, outcome: dict) -> str:
        """在每次工具调用后写入路由决策记录。"""
        outcome_id = outcome.get("outcome_id") or str(uuid.uuid4())
        outcome["outcome_id"] = outcome_id
        now = datetime.now(timezone.utc).isoformat()
        skipped = outcome.get("skipped_bindings")
        if isinstance(skipped, (list, dict)):
            skipped = json.dumps(skipped)
        selected_binding = outcome.get("selected_binding")
        if isinstance(selected_binding, (list, dict)):
            selected_binding = json.dumps(selected_binding)
        elif selected_binding is not None and not isinstance(selected_binding, str):
            selected_binding = json.dumps(selected_binding)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO hybrid.routing_outcomes
                       (outcome_id, request_id, plan_id, step_id, alias, profile,
                        selected_binding, skipped_bindings, reason_code, policy_version,
                        created_at)
                       VALUES (:outcome_id, :request_id, :plan_id, :step_id, :alias, :profile,
                               :selected_binding, :skipped_bindings, :reason_code, :policy_version,
                               :created_at)"""
                ),
                {
                    "outcome_id": outcome_id,
                    "request_id": outcome.get("request_id"),
                    "plan_id": outcome.get("plan_id"),
                    "step_id": outcome.get("step_id"),
                    "alias": outcome.get("alias"),
                    "profile": outcome.get("profile"),
                    "selected_binding": selected_binding,
                    "skipped_bindings": skipped,
                    "reason_code": outcome.get("reason_code"),
                    "policy_version": outcome.get("policy_version"),
                    "created_at": outcome.get("created_at") or now,
                },
            )
        return outcome_id

    def get_outcomes_by_request(self, request_id: str) -> list[dict]:
        """查询指定请求的所有路由决策。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM hybrid.routing_outcomes WHERE request_id = :request_id "
                    "ORDER BY created_at ASC"
                ),
                {"request_id": request_id},
            ).mappings().all()
        return [self._row_to_outcome(row) for row in rows]

    def get_outcomes_by_plan(self, plan_id: str) -> list[dict]:
        """查询指定计划的所有路由决策。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM hybrid.routing_outcomes WHERE plan_id = :plan_id "
                    "ORDER BY created_at ASC"
                ),
                {"plan_id": plan_id},
            ).mappings().all()
        return [self._row_to_outcome(row) for row in rows]

    # ── RoutingPolicyVersion CRUD ───────────────────────────

    def create_policy_version(self, version: str, weights: dict) -> str:
        """创建路由策略版本，返回 version_id。"""
        version_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO hybrid.routing_policy_versions
                       (version_id, version, weights, status, created_at, promoted_at)
                       VALUES (:version_id, :version, :weights, :status, :created_at, NULL)"""
                ),
                {
                    "version_id": version_id,
                    "version": version,
                    "weights": json.dumps(weights),
                    "status": "draft",
                    "created_at": now,
                },
            )
        return version_id

    def get_active_policy_version(self) -> dict | None:
        """查询当前激活的路由策略版本。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM hybrid.routing_policy_versions WHERE status = 'active' "
                    "ORDER BY promoted_at DESC LIMIT 1"
                ),
            ).mappings().first()
        if row is None:
            return None
        return self._row_to_policy_version(row)

    def promote_policy_version(self, version_id: str) -> None:
        """将指定版本提升为激活版本（其余激活版本归档）。"""
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE hybrid.routing_policy_versions SET status = 'archived' "
                    "WHERE status = 'active'"
                ),
            )
            conn.execute(
                text(
                    "UPDATE hybrid.routing_policy_versions SET status = 'active', promoted_at = :promoted_at "
                    "WHERE version_id = :version_id"
                ),
                {"promoted_at": now, "version_id": version_id},
            )

    # ── helpers ─────────────────────────────────────────────

    @staticmethod
    def _row_to_request(row) -> dict:
        return {
            "request_id": row["request_id"],
            "scenario_id": row["scenario_id"] or "",
            "goal": row["goal"],
            "material_scope": row["material_scope"],
            "target_properties": _parse_json_field(row["target_properties"], []) or [],
            "constraints": _parse_json_field(row["constraints"], {}) or {},
            "preference": row["preference"],
            "user_id": row["user_id"],
            "project_id": row["project_id"] or "",
            "task_id": (row["task_id"] if "task_id" in row.keys() else "") or "",
            "execution_profile": row["execution_profile"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _row_to_plan(row) -> dict:
        return {
            "plan_id": row["plan_id"],
            "request_id": row["request_id"],
            "execution_profile": row["execution_profile"],
            "steps": _parse_json_field(row["steps"], []) or [],
            "rationale": row["rationale"],
            "estimated_budget": _parse_json_field(row["estimated_budget"], {}) or {},
            "risk_summary": row["risk_summary"],
            "capabilities_needed": _parse_json_field(row["capabilities_needed"], []) or [],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _row_to_outcome(row) -> dict:
        return {
            "outcome_id": row["outcome_id"],
            "request_id": row["request_id"],
            "plan_id": row["plan_id"],
            "step_id": row["step_id"],
            "alias": row["alias"],
            "profile": row["profile"],
            "selected_binding": row["selected_binding"],
            "skipped_bindings": _parse_json_field(row["skipped_bindings"], []) or [],
            "reason_code": row["reason_code"],
            "policy_version": row["policy_version"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _row_to_policy_version(row) -> dict:
        return {
            "version_id": row["version_id"],
            "version": row["version"],
            "weights": _parse_json_field(row["weights"], {}) or {},
            "status": row["status"],
            "created_at": row["created_at"],
            "promoted_at": row["promoted_at"],
        }
