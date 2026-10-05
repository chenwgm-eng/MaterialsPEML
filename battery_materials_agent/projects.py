"""项目实体管理。"""

from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
import json
import uuid
from sqlalchemy import text
from .db import get_engine, get_tenant, tenant_filter


def _iso(value) -> str:
    """将 datetime 或字符串转换为 ISO 字符串；None 返回空字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class Project(BaseModel):
    """研发项目。"""
    project_id: str = ""
    name: str = ""
    target_application: str = ""  # 动力/储能/消费
    current_stage: str = "立项"  # 立项/筛选/中试/验证/定型
    target_properties: list[dict] = Field(default_factory=list)
    owner: str = ""
    department: str = ""  # 所属部门
    start_date: str = ""  # 计划开始日期
    end_date: str = ""  # 计划结束日期
    budget: float = 0.0  # 预算（万元）
    iteration_progress: int = 0  # 当前迭代进度（%）
    candidate_ids: list[str] = Field(default_factory=list)
    experiment_order_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    # 项目立项时拆解出的任务列表，每项含交付物（材料）与目标属性
    tasks: list[dict] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = ""

    @field_validator("department", "start_date", "end_date", "owner", "name",
                     "target_application", "current_stage", "notes", mode="before")
    @classmethod
    def _none_to_empty(cls, v):
        """前端可能传 null，自动转为空串避免 ValidationError。"""
        return "" if v is None else v


class ProjectTask(BaseModel):
    """项目任务（关系表 projects.tasks）。

    业务链路：项目 1 → N 任务；任务 1 → N 候选材料。
    注：projects.projects.tasks JSONB 字段已 deprecated，统一使用本关系表。
    """
    task_id: str = ""
    project_id: str = ""
    title: str = ""
    deliverable: str = ""  # 交付物（材料名称）
    target_properties: list[dict] = Field(default_factory=list)
    status: str = "draft"  # draft / active / completed / cancelled
    assignee: str = ""
    sort_order: int = 0
    # 甘特图所需字段：研发阶段动作（用于分阶段分组）、计划起止日期
    action: str = ""  # route_material / generate_crystal_candidates / predict_crystal_properties / verify_dft / design_formula / check_synthesis_feasibility / compliance_check
    start_date: str = ""  # 计划开始日期（YYYY-MM-DD）
    end_date: str = ""  # 计划结束日期（YYYY-MM-DD）
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = ""


class ProjectStore:
    """项目数据存储。"""

    def __init__(self, db_path: str | None = None):
        # db_path 参数保留以兼容旧调用方（如 value_realization/calculator.py），
        # 迁移至 PostgreSQL 后已忽略，统一使用全局 Engine。
        self.engine = get_engine()

    def create(self, project: Project) -> Project:
        if not project.project_id:
            project.project_id = f"PROJ-{uuid.uuid4().hex[:8].upper()}"
        # 自动填充时间戳：created_at/updated_at 为空时使用当前 UTC 时间
        now = datetime.now(timezone.utc).isoformat()
        if not project.created_at:
            project.created_at = now
        if not project.updated_at:
            project.updated_at = now
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO projects.projects
                (project_id, name, target_application, current_stage, target_properties,
                 owner, department, start_date, end_date, budget, iteration_progress,
                 candidate_ids, experiment_order_ids, notes, tasks, created_at, updated_at,
                 tenant_id)
                VALUES (:project_id, :name, :target_application, :current_stage,
                        CAST(:target_properties AS JSONB), :owner, :department,
                        :start_date, :end_date, :budget, :iteration_progress,
                        CAST(:candidate_ids AS JSONB),
                        CAST(:experiment_order_ids AS JSONB), :notes,
                        CAST(:tasks AS JSONB), :created_at, :updated_at,
                        :tenant_id)"""),
                {
                    "project_id": project.project_id,
                    "name": project.name,
                    "target_application": project.target_application,
                    "current_stage": project.current_stage,
                    "target_properties": json.dumps(project.target_properties),
                    "owner": project.owner,
                    "department": project.department,
                    "start_date": project.start_date,
                    "end_date": project.end_date,
                    "budget": project.budget,
                    "iteration_progress": project.iteration_progress,
                    "candidate_ids": json.dumps(project.candidate_ids),
                    "experiment_order_ids": json.dumps(project.experiment_order_ids),
                    "notes": project.notes,
                    "tasks": json.dumps(project.tasks),
                    "created_at": project.created_at,
                    "updated_at": project.updated_at,
                    # 多租户隔离（0050）：写入当前上下文租户
                    "tenant_id": get_tenant(),
                },
            )
        # 同步 tasks 到关系表（JSONB 字段保留为只读快照，deprecated）
        if project.tasks:
            self.replace_project_tasks(project.project_id, project.tasks)
        return project

    # ──────────────────────────────────────────────────────────────────
    # 项目任务（projects.tasks 关系表）CRUD
    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _row_to_task(r) -> ProjectTask:
        return ProjectTask(
            task_id=r[0] or "",
            project_id=r[1] or "",
            title=r[2] or "",
            deliverable=r[3] or "",
            target_properties=r[4] or [],
            status=r[5] or "draft",
            assignee=r[6] or "",
            sort_order=r[7] if r[7] is not None else 0,
            created_at=_iso(r[8]),
            updated_at=_iso(r[9]),
        )

    def create_task(self, task: ProjectTask) -> ProjectTask:
        """创建单个项目任务。"""
        if not task.task_id:
            task.task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        if not task.created_at:
            task.created_at = now
        task.updated_at = now
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO projects.tasks
                (task_id, project_id, title, deliverable, target_properties,
                 status, assignee, sort_order, created_at, updated_at)
                VALUES (:task_id, :project_id, :title, :deliverable,
                        CAST(:target_properties AS JSONB), :status, :assignee,
                        :sort_order, :created_at, :updated_at)
                ON CONFLICT (task_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    deliverable = EXCLUDED.deliverable,
                    target_properties = EXCLUDED.target_properties,
                    status = EXCLUDED.status,
                    assignee = EXCLUDED.assignee,
                    sort_order = EXCLUDED.sort_order,
                    updated_at = EXCLUDED.updated_at
                """),
                {
                    "task_id": task.task_id,
                    "project_id": task.project_id,
                    "title": task.title,
                    "deliverable": task.deliverable,
                    "target_properties": json.dumps(task.target_properties),
                    "status": task.status,
                    "assignee": task.assignee,
                    "sort_order": task.sort_order,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                },
            )
        return task

    def get_task(self, task_id: str) -> ProjectTask | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT task_id, project_id, title, deliverable, target_properties, "
                     "status, assignee, sort_order, created_at, updated_at "
                     "FROM projects.tasks WHERE task_id = :task_id"),
                {"task_id": task_id},
            ).fetchone()
        return self._row_to_task(row) if row else None

    def list_tasks(self, project_id: str) -> list[ProjectTask]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT task_id, project_id, title, deliverable, target_properties, "
                     "status, assignee, sort_order, created_at, updated_at "
                     "FROM projects.tasks WHERE project_id = :project_id "
                     "ORDER BY sort_order ASC, created_at ASC"),
                {"project_id": project_id},
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def update_task(self, task: ProjectTask) -> ProjectTask:
        task.updated_at = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text("""UPDATE projects.tasks SET
                title = :title, deliverable = :deliverable,
                target_properties = CAST(:target_properties AS JSONB),
                status = :status, assignee = :assignee, sort_order = :sort_order,
                updated_at = :updated_at
                WHERE task_id = :task_id"""),
                {
                    "title": task.title,
                    "deliverable": task.deliverable,
                    "target_properties": json.dumps(task.target_properties),
                    "status": task.status,
                    "assignee": task.assignee,
                    "sort_order": task.sort_order,
                    "updated_at": task.updated_at,
                    "task_id": task.task_id,
                },
            )
        return task

    def delete_task(self, task_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM projects.tasks WHERE task_id = :task_id"),
                {"task_id": task_id},
            )
        return cur.rowcount > 0

    def replace_project_tasks(self, project_id: str, tasks: list[dict]) -> list[ProjectTask]:
        """全量替换项目的任务列表（先删后插）。

        用于 POST /projects/decompose 和 create/update 同步场景。
        tasks 参数为 list[dict]（兼容 AI 拆解返回的字典格式），自动转换为 ProjectTask。
        """
        # 删除旧任务
        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM projects.tasks WHERE project_id = :project_id"),
                {"project_id": project_id},
            )
        # 插入新任务
        result: list[ProjectTask] = []
        for idx, t in enumerate(tasks):
            task_id = t.get("task_id") or str(uuid.uuid4())
            task = ProjectTask(
                task_id=task_id,
                project_id=project_id,
                title=t.get("title", "未命名任务"),
                deliverable=t.get("deliverable", ""),
                target_properties=t.get("target_properties", []),
                status=t.get("status", "draft"),
                assignee=t.get("assignee", ""),
                sort_order=t.get("sort_order", idx),
            )
            self.create_task(task)
            result.append(task)
        return result

    def _row_to_project(self, r) -> Project:
        return Project(
            project_id=r[0], name=r[1], target_application=r[2],
            current_stage=r[3], target_properties=r[4] or [],
            owner=r[5], candidate_ids=r[6] or [],
            experiment_order_ids=r[7] or [], notes=r[8] or "",
            created_at=_iso(r[9]), updated_at=_iso(r[10]),
            department=r[11] if len(r) > 11 else "",
            start_date=r[12] if len(r) > 12 else "",
            end_date=r[13] if len(r) > 13 else "",
            budget=r[14] if len(r) > 14 else 0.0,
            iteration_progress=r[15] if len(r) > 15 else 0,
            tasks=r[16] if len(r) > 16 and r[16] else [],
        )

    def get(self, project_id: str) -> Project | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT * FROM projects.projects "
                     f"WHERE project_id=:project_id AND {tenant_filter()}"),
                {"project_id": project_id, "tenant_id": get_tenant()},
            ).fetchone()
        if not row:
            return None
        return self._row_to_project(row)

    def get_by_name(self, name: str) -> Project | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT * FROM projects.projects "
                     f"WHERE name=:name AND {tenant_filter()}"),
                {"name": name, "tenant_id": get_tenant()},
            ).fetchone()
        if not row:
            return None
        return self._row_to_project(row)

    def delete(self, project_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text(f"DELETE FROM projects.projects "
                     f"WHERE project_id=:project_id AND {tenant_filter()}"),
                {"project_id": project_id, "tenant_id": get_tenant()},
            )
        return cur.rowcount > 0

    def list_all(self) -> list[Project]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT * FROM projects.projects "
                     f"WHERE {tenant_filter()} ORDER BY created_at DESC"),
                {"tenant_id": get_tenant()},
            ).fetchall()
        return [self._row_to_project(r) for r in rows]

    def update(self, project: Project) -> Project:
        project.updated_at = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(f"""UPDATE projects.projects SET
                name=:name, target_application=:target_application, current_stage=:current_stage,
                target_properties=CAST(:target_properties AS JSONB), owner=:owner,
                department=:department, start_date=:start_date, end_date=:end_date,
                budget=:budget, iteration_progress=:iteration_progress,
                candidate_ids=CAST(:candidate_ids AS JSONB),
                experiment_order_ids=CAST(:experiment_order_ids AS JSONB),
                notes=:notes, tasks=CAST(:tasks AS JSONB), updated_at=:updated_at
                WHERE project_id=:project_id AND {tenant_filter()}"""),
                {
                    "name": project.name,
                    "target_application": project.target_application,
                    "current_stage": project.current_stage,
                    "target_properties": json.dumps(project.target_properties),
                    "owner": project.owner,
                    "department": project.department,
                    "start_date": project.start_date,
                    "end_date": project.end_date,
                    "budget": project.budget,
                    "iteration_progress": project.iteration_progress,
                    "candidate_ids": json.dumps(project.candidate_ids),
                    "experiment_order_ids": json.dumps(project.experiment_order_ids),
                    "notes": project.notes,
                    "tasks": json.dumps(project.tasks),
                    "updated_at": project.updated_at,
                    "project_id": project.project_id,
                    "tenant_id": get_tenant(),
                },
            )
        # 同步 tasks 到关系表（JSONB 字段保留为只读快照，deprecated）
        if project.tasks:
            self.replace_project_tasks(project.project_id, project.tasks)
        return project

    def get_project_tasks(self, project_id: str) -> list[dict]:
        """查询项目任务列表（projects.tasks 关系表）。

        返回 list[dict] 兼容旧 API（前端期望字典数组）。
        动态推断 action / start_date / end_date 供甘特图使用（不修改数据库 schema）。
        """
        tasks = self.list_tasks(project_id)
        result = []
        for t in tasks:
            d = {
                "task_id": t.task_id,
                "title": t.title,
                "deliverable": t.deliverable,
                "target_properties": t.target_properties,
                "status": t.status,
                "assignee": t.assignee,
                "sort_order": t.sort_order,
                "action": getattr(t, "action", "") or "",
                "start_date": getattr(t, "start_date", "") or "",
                "end_date": getattr(t, "end_date", "") or "",
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            # 甘特图兜底：若无 start_date/end_date，用 created_at 推断
            if not d["start_date"] and t.created_at:
                d["start_date"] = t.created_at[:10]  # YYYY-MM-DD
            if not d["end_date"] and t.created_at:
                # 默认 30 天周期
                from datetime import datetime as _dt, timedelta as _td
                try:
                    base = _dt.fromisoformat(t.created_at.replace("Z", "+00:00"))
                    d["end_date"] = (base + _td(days=30)).date().isoformat()
                except Exception:
                    d["end_date"] = ""
            result.append(d)
        return result
