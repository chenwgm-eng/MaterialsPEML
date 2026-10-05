"""测试任务存储。

业务链路层级：
    项目 1 → N 任务
    任务 1 → N 候选材料
    候选材料 1 ↔ 1 BOM 方案
    BOM 方案 1 → N 实验任务（experiment_orders）
    实验任务 1 → N 测试任务（test_tasks）  ← 本模块
    测试任务 1 → N 样品
    样品 1 → N 实验数据（experiment_result_records）

表：experiment.test_tasks（由 0009 迁移创建）。

注：状态迁移规则与取值复用 ExperimentOrderStatus（DRAFT / PENDING_APPROVAL / APPROVED /
SCHEDULED / IN_EXECUTION / WAITING_FOR_DATA / COMPLETED / CANCELLED / VALIDATION_FAILED），
对应 MDM status_codes (domain='test_task')。
"""
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
import uuid
from sqlalchemy import text

from ..db import get_engine
from .experiment_controller import (
    ExperimentOrderStatus,
    IllegalStateTransitionError,
    ALLOWED_TRANSITIONS,
)


def _iso(value) -> str:
    """将 datetime 或字符串转换为 ISO 字符串；None 返回空字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class TestTask(BaseModel):
    """测试任务（experiment_orders 的子层级）。

    通过 order_id FK 关联到 experiment_orders（实验任务 1:N 测试任务）。
    通过 bom_id FK 可选关联到 bom_schemes。
    """
    test_task_id: str = ""
    order_id: str = ""  # 必填，关联 experiment_orders
    bom_id: str = ""  # 可选，关联 bom_schemes
    test_type: str = ""  # 测试类型（如 ionic_conductivity / xrd / sem / dsc / eis / cv）
    test_method: str = ""  # 测试方法（具体测试标准/规程编号）
    priority: str = "P2"  # P0 / P1 / P2 / P3
    assignee: str = ""
    status: str = "DRAFT"  # 见 ExperimentOrderStatus / MDM status_codes (domain='test_task')
    planned_start: str | None = None
    planned_end: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    notes: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = ""

    @field_validator('order_id', 'bom_id', 'test_type', 'test_method', 'priority',
                     'assignee', 'status', 'notes', mode='before')
    @classmethod
    def _coerce_none_to_empty(cls, v):
        """前端或上游可能传入 None，统一转为空字符串。"""
        return "" if v is None else v


class TestTaskStore:
    """测试任务存储。"""

    def __init__(self, db_path: str = ""):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.engine = get_engine()
        # MDM 参考字典 Store 复用，避免每次校验都新建实例
        from ..mdm.reference_dict import ReferenceDictStore
        self._mdm = ReferenceDictStore()
        self._init_db()

    def _init_db(self):
        # 表已由 alembic 迁移创建，这里仅保留 IF NOT EXISTS 兜底
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.test_tasks (
                    test_task_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    bom_id TEXT,
                    test_type TEXT DEFAULT '',
                    test_method TEXT DEFAULT '',
                    priority TEXT DEFAULT 'P2',
                    assignee TEXT DEFAULT '',
                    status TEXT DEFAULT 'DRAFT',
                    planned_start TIMESTAMPTZ,
                    planned_end TIMESTAMPTZ,
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_test_tasks_order_id "
                "ON experiment.test_tasks(order_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_test_tasks_bom_id "
                "ON experiment.test_tasks(bom_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_test_tasks_status "
                "ON experiment.test_tasks(status)"
            ))

    # ──────────────────────────────────────────────────────────────────
    # 行映射
    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _row_to_test_task(r) -> TestTask:
        return TestTask(
            test_task_id=r[0] or "",
            order_id=r[1] or "",
            bom_id=r[2] or "",
            test_type=r[3] or "",
            test_method=r[4] or "",
            priority=r[5] or "P2",
            assignee=r[6] or "",
            status=r[7] or "DRAFT",
            planned_start=_iso(r[8]) or None,
            planned_end=_iso(r[9]) or None,
            started_at=_iso(r[10]) or None,
            completed_at=_iso(r[11]) or None,
            notes=r[12] or "",
            created_at=_iso(r[13]),
            updated_at=_iso(r[14]),
        )

    # ──────────────────────────────────────────────────────────────────
    # CRUD
    # ──────────────────────────────────────────────────────────────────
    def create(self, task: TestTask) -> TestTask:
        """创建测试任务。"""
        if not task.order_id:
            raise ValueError("order_id 不能为空")

        if not task.test_task_id:
            task.test_task_id = f"TT-{uuid.uuid4().hex[:10].upper()}"
        now = datetime.now(timezone.utc).isoformat()
        if not task.created_at:
            task.created_at = now
        task.updated_at = now

        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.test_tasks
                (test_task_id, order_id, bom_id, test_type, test_method, priority,
                 assignee, status, planned_start, planned_end, started_at, completed_at,
                 notes, created_at, updated_at)
                VALUES (:test_task_id, :order_id, :bom_id, :test_type, :test_method, :priority,
                 :assignee, :status, :planned_start, :planned_end, :started_at, :completed_at,
                 :notes, :created_at, :updated_at)
                """),
                {
                    "test_task_id": task.test_task_id,
                    "order_id": task.order_id,
                    # FK 约束：空字符串需转为 NULL
                    "bom_id": task.bom_id or None,
                    "test_type": task.test_type,
                    # fk_test_tasks_method：空字符串需转为 NULL（与 _normalize_test_method 契约一致）
                    "test_method": task.test_method or None,
                    "priority": task.priority,
                    "assignee": task.assignee,
                    "status": task.status,
                    "planned_start": task.planned_start or None,
                    "planned_end": task.planned_end or None,
                    "started_at": task.started_at or None,
                    "completed_at": task.completed_at or None,
                    "notes": task.notes,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                },
            )
        return task

    def get(self, test_task_id: str) -> TestTask | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT test_task_id, order_id, bom_id, test_type, test_method, "
                     "priority, assignee, status, planned_start, planned_end, "
                     "started_at, completed_at, notes, created_at, updated_at "
                     "FROM experiment.test_tasks WHERE test_task_id = :test_task_id"),
                {"test_task_id": test_task_id},
            ).fetchone()
        return self._row_to_test_task(row) if row else None

    def list_by_order(self, order_id: str) -> list[TestTask]:
        """按 order_id 查询测试任务列表。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT test_task_id, order_id, bom_id, test_type, test_method, "
                     "priority, assignee, status, planned_start, planned_end, "
                     "started_at, completed_at, notes, created_at, updated_at "
                     "FROM experiment.test_tasks WHERE order_id = :order_id "
                     "ORDER BY created_at ASC"),
                {"order_id": order_id},
            ).fetchall()
        return [self._row_to_test_task(r) for r in rows]

    def list_by_bom(self, bom_id: str) -> list[TestTask]:
        """按 bom_id 查询测试任务列表。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT test_task_id, order_id, bom_id, test_type, test_method, "
                     "priority, assignee, status, planned_start, planned_end, "
                     "started_at, completed_at, notes, created_at, updated_at "
                     "FROM experiment.test_tasks WHERE bom_id = :bom_id "
                     "ORDER BY created_at ASC"),
                {"bom_id": bom_id},
            ).fetchall()
        return [self._row_to_test_task(r) for r in rows]

    def update(self, task: TestTask) -> TestTask:
        """更新测试任务全字段。"""
        task.updated_at = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text("""UPDATE experiment.test_tasks SET
                bom_id = :bom_id,
                test_type = :test_type,
                test_method = :test_method,
                priority = :priority,
                assignee = :assignee,
                status = :status,
                planned_start = :planned_start,
                planned_end = :planned_end,
                started_at = :started_at,
                completed_at = :completed_at,
                notes = :notes,
                updated_at = :updated_at
                WHERE test_task_id = :test_task_id"""),
                {
                    "bom_id": task.bom_id or None,
                    "test_type": task.test_type,
                    # fk_test_tasks_method：空字符串需转为 NULL（与 _normalize_test_method 契约一致）
                    "test_method": task.test_method or None,
                    "priority": task.priority,
                    "assignee": task.assignee,
                    "status": task.status,
                    "planned_start": task.planned_start or None,
                    "planned_end": task.planned_end or None,
                    "started_at": task.started_at or None,
                    "completed_at": task.completed_at or None,
                    "notes": task.notes,
                    "updated_at": task.updated_at,
                    "test_task_id": task.test_task_id,
                },
            )
        return task

    def update_status(self, test_task_id: str, status: str,
                      started_at: str | None = None,
                      completed_at: str | None = None) -> bool:
        """仅更新测试任务状态及对应时间戳。

        - 状态值必须存在于 MDM status_codes (domain='test_task') 中
        - (current → target) 迁移路径必须在 ALLOWED_TRANSITIONS 中
        非法情况抛 IllegalStateTransitionError；任务不存在返回 False。
        """
        # MDM 校验：目标状态必须在 mdm.status_codes (domain='test_task') 中存在
        if self._mdm.get_status_code("test_task", status) is None:
            raise IllegalStateTransitionError(
                "UNKNOWN", status,
                f"目标状态 {status!r} 不在 MDM 主数据 (domain=test_task) 中",
            )

        # 解析目标状态为枚举
        try:
            to_status_enum = ExperimentOrderStatus(status)
        except ValueError:
            valid = [s.value for s in ExperimentOrderStatus]
            raise IllegalStateTransitionError(
                "UNKNOWN", status,
                f"未知目标状态: {status!r}，合法值: {valid}",
            )

        # 读取当前状态
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT status FROM experiment.test_tasks "
                     "WHERE test_task_id = :test_task_id"),
                {"test_task_id": test_task_id},
            ).fetchone()
        if row is None:
            return False

        current_status_raw = row[0] if row[0] is not None else ""
        try:
            from_status_enum = ExperimentOrderStatus(current_status_raw)
        except ValueError:
            # 数据库中存在未知状态（历史脏数据），记录警告并跳过迁移校验
            from_status_enum = None

        # 校验迁移合法性
        if from_status_enum is not None:
            allowed = ALLOWED_TRANSITIONS.get(from_status_enum, set())
            if to_status_enum not in allowed:
                allowed_str = [s.value for s in allowed] if allowed else "none (terminal state)"
                raise IllegalStateTransitionError(
                    current_status_raw, status,
                    f"合法迁移: {from_status_enum.value} → {allowed_str}",
                )

        now = datetime.now(timezone.utc).isoformat()
        # 根据目标状态决定时间戳
        started = started_at
        completed = completed_at
        if status == ExperimentOrderStatus.IN_EXECUTION.value and not started:
            started = now
        elif status == ExperimentOrderStatus.COMPLETED.value and not completed:
            completed = now

        with self.engine.begin() as conn:
            cur = conn.execute(
                text("""UPDATE experiment.test_tasks SET
                status = :status,
                started_at = COALESCE(:started_at, started_at),
                completed_at = COALESCE(:completed_at, completed_at),
                updated_at = :updated_at
                WHERE test_task_id = :test_task_id"""),
                {
                    "status": status,
                    "started_at": started,
                    "completed_at": completed,
                    "updated_at": now,
                    "test_task_id": test_task_id,
                },
            )
            return cur.rowcount > 0

    def delete(self, test_task_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM experiment.test_tasks WHERE test_task_id = :test_task_id"),
                {"test_task_id": test_task_id},
            )
        return cur.rowcount > 0

    def list_all(self) -> list[TestTask]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT test_task_id, order_id, bom_id, test_type, test_method, "
                     "priority, assignee, status, planned_start, planned_end, "
                     "started_at, completed_at, notes, created_at, updated_at "
                     "FROM experiment.test_tasks ORDER BY created_at DESC")
            ).fetchall()
        return [self._row_to_test_task(r) for r in rows]
