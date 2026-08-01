"""Unit tests for ExperimentOrder state machine (Task 11).

覆盖：
- ExperimentOrderStatus 枚举完整性
- ALLOWED_TRANSITIONS 迁移图合法性
- IllegalStateTransitionError 异常
- update_order_status 强制校验（DB 集成）
- 状态迁移事件日志写入（DB 集成）
- API 返回 400 + 错误信息（直接调用端点函数）
"""

from __future__ import annotations

import types
import uuid

import pytest
from sqlalchemy import text

from battery_materials_agent.experiment.experiment_controller import (
    ALLOWED_TRANSITIONS,
    ExperimentDataStore,
    ExperimentOrder,
    ExperimentOrderStatus,
    IllegalStateTransitionError,
    _STATUS_ALIASES,
)


# ───────────────────────── 静态测试（无 DB） ─────────────────────────

class TestStateMachineStatic:
    """纯 Python 测试：枚举、迁移图、异常类。"""

    def test_enum_has_nine_statuses(self):
        assert len(ExperimentOrderStatus) == 9

    def test_enum_values_match_existing_uppercase_strings(self):
        """枚举值必须与现有数据库中存储的大写字符串一致，保持向后兼容。"""
        expected = {
            "DRAFT", "PENDING_APPROVAL", "APPROVED", "SCHEDULED",
            "IN_EXECUTION", "WAITING_FOR_DATA", "COMPLETED",
            "CANCELLED", "VALIDATION_FAILED",
        }
        actual = {s.value for s in ExperimentOrderStatus}
        assert actual == expected

    def test_enum_is_str_subclass(self):
        """str 子类枚举，确保 ExperimentOrderStatus.DRAFT == "DRAFT" 成立。"""
        assert ExperimentOrderStatus.DRAFT == "DRAFT"
        assert ExperimentOrderStatus.COMPLETED == "COMPLETED"

    def test_all_statuses_are_keys_in_transitions(self):
        """每个枚举值都必须在 ALLOWED_TRANSITIONS 中有对应键。"""
        for status in ExperimentOrderStatus:
            assert status in ALLOWED_TRANSITIONS, f"{status} missing from ALLOWED_TRANSITIONS"

    def test_terminal_states_have_empty_transitions(self):
        """COMPLETED 和 CANCELLED 是终态，不能迁出。"""
        assert ALLOWED_TRANSITIONS[ExperimentOrderStatus.COMPLETED] == set()
        assert ALLOWED_TRANSITIONS[ExperimentOrderStatus.CANCELLED] == set()

    def test_completed_cannot_transition_to_any_status(self):
        for status in ExperimentOrderStatus:
            if status == ExperimentOrderStatus.COMPLETED:
                continue
            assert status not in ALLOWED_TRANSITIONS[ExperimentOrderStatus.COMPLETED]

    def test_cancelled_cannot_transition_to_any_status(self):
        for status in ExperimentOrderStatus:
            if status == ExperimentOrderStatus.CANCELLED:
                continue
            assert status not in ALLOWED_TRANSITIONS[ExperimentOrderStatus.CANCELLED]

    def test_waiting_for_data_only_entered_from_in_execution(self):
        """WAITING_FOR_DATA 只能从 IN_EXECUTION 迁入。"""
        for status, targets in ALLOWED_TRANSITIONS.items():
            if status == ExperimentOrderStatus.IN_EXECUTION:
                assert ExperimentOrderStatus.WAITING_FOR_DATA in targets
            else:
                assert ExperimentOrderStatus.WAITING_FOR_DATA not in targets, (
                    f"WAITING_FOR_DATA should not be reachable from {status.value}"
                )

    def test_waiting_for_data_can_only_go_to_in_execution_or_completed(self):
        """WAITING_FOR_DATA 只能迁回 IN_EXECUTION 或推进到 COMPLETED。"""
        targets = ALLOWED_TRANSITIONS[ExperimentOrderStatus.WAITING_FOR_DATA]
        assert targets == {ExperimentOrderStatus.IN_EXECUTION, ExperimentOrderStatus.COMPLETED}

    def test_draft_can_go_to_pending_approval_or_cancelled(self):
        targets = ALLOWED_TRANSITIONS[ExperimentOrderStatus.DRAFT]
        assert targets == {ExperimentOrderStatus.PENDING_APPROVAL, ExperimentOrderStatus.CANCELLED}

    def test_approved_can_go_to_scheduled_in_execution_or_cancelled(self):
        targets = ALLOWED_TRANSITIONS[ExperimentOrderStatus.APPROVED]
        assert targets == {
            ExperimentOrderStatus.SCHEDULED,
            ExperimentOrderStatus.IN_EXECUTION,
            ExperimentOrderStatus.CANCELLED,
        }

    def test_in_execution_can_go_to_waiting_completed_validation_failed_cancelled(self):
        targets = ALLOWED_TRANSITIONS[ExperimentOrderStatus.IN_EXECUTION]
        assert targets == {
            ExperimentOrderStatus.WAITING_FOR_DATA,
            ExperimentOrderStatus.COMPLETED,
            ExperimentOrderStatus.VALIDATION_FAILED,
            ExperimentOrderStatus.CANCELLED,
        }

    def test_validation_failed_can_retry_or_cancel(self):
        """VALIDATION_FAILED 可重试（→ IN_EXECUTION）或取消。"""
        targets = ALLOWED_TRANSITIONS[ExperimentOrderStatus.VALIDATION_FAILED]
        assert targets == {ExperimentOrderStatus.IN_EXECUTION, ExperimentOrderStatus.CANCELLED}

    def test_all_legal_transitions_are_symmetric_to_enum(self):
        """迁移图中的所有目标状态都必须是有效的枚举值。"""
        for status, targets in ALLOWED_TRANSITIONS.items():
            for target in targets:
                assert isinstance(target, ExperimentOrderStatus)

    @pytest.mark.parametrize("from_status", list(ExperimentOrderStatus))
    def test_no_self_transitions_except_none(self, from_status):
        """状态不应允许自转换（DRAFT → DRAFT 等）。"""
        assert from_status not in ALLOWED_TRANSITIONS[from_status]

    def test_illegal_transition_error_attributes(self):
        err = IllegalStateTransitionError("COMPLETED", "APPROVED", "terminal state")
        assert err.from_status == "COMPLETED"
        assert err.to_status == "APPROVED"
        assert err.reason == "terminal state"

    def test_illegal_transition_error_message_contains_statuses(self):
        err = IllegalStateTransitionError("DRAFT", "COMPLETED")
        msg = str(err)
        assert "DRAFT" in msg
        assert "COMPLETED" in msg

    def test_illegal_transition_error_without_reason(self):
        err = IllegalStateTransitionError("DRAFT", "COMPLETED")
        assert err.reason == ""
        assert "DRAFT" in str(err)
        assert "COMPLETED" in str(err)

    def test_illegal_transition_error_is_value_error(self):
        """IllegalStateTransitionError 必须继承 ValueError。"""
        err = IllegalStateTransitionError("A", "B")
        assert isinstance(err, ValueError)

    def test_rejected_alias_maps_to_cancelled(self):
        """旧 API 使用 REJECTED，应映射为 CANCELLED 保持向后兼容。"""
        assert _STATUS_ALIASES["REJECTED"] == "CANCELLED"


# ───────────────────────── DB 集成测试 ─────────────────────────

TEST_PROJECT_ID = "T11-TEST-PROJECT"
TEST_CANDIDATE_ID = "T11-TEST-CANDIDATE"


def _make_order(order_id: str, status: str = "DRAFT") -> ExperimentOrder:
    return ExperimentOrder(
        order_id=order_id,
        project_id=TEST_PROJECT_ID,
        candidate_id=TEST_CANDIDATE_ID,
        status=status,
    )


@pytest.fixture
def store():
    return ExperimentDataStore()


@pytest.fixture
def ensure_test_project(store):
    """确保测试项目和候选存在（外键约束要求 project_id / candidate_id 必须在父表中）。"""
    with store.engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO projects.projects (project_id, name, created_at, updated_at)
                VALUES (:pid, :name, NOW(), NOW())
                ON CONFLICT (project_id) DO NOTHING
            """),
            {"pid": TEST_PROJECT_ID, "name": "Task 11 Test Project"},
        )
        conn.execute(
            text("""
                INSERT INTO experiment.candidates (candidate_id, candidate_type, name, created_at)
                VALUES (:cid, :ctype, :name, NOW())
                ON CONFLICT (candidate_id) DO NOTHING
            """),
            {"cid": TEST_CANDIDATE_ID, "ctype": "crystal", "name": "Task 11 Test Candidate"},
        )
    yield store


@pytest.fixture
def cleanup_order_ids():
    """跟踪并清理测试创建的 order_id 和关联的 transition 日志。"""
    order_ids: list[str] = []

    def register(oid: str) -> str:
        order_ids.append(oid)
        return oid

    yield register

    # 清理：先删 transitions，再删 orders
    if order_ids:
        engine = ExperimentDataStore().engine
        with engine.begin() as conn:
            for oid in order_ids:
                conn.execute(
                    text("DELETE FROM experiment.experiment_order_status_transitions WHERE order_id = :oid"),
                    {"oid": oid},
                )
                conn.execute(
                    text("DELETE FROM experiment.experiment_orders WHERE order_id = :oid"),
                    {"oid": oid},
                )


def _get_order_status(store: ExperimentDataStore, order_id: str) -> str:
    """直接通过 SQL 查询订单状态，绕过 get_order() 的 Pydantic datetime 验证问题（预存 bug）。"""
    with store.engine.connect() as conn:
        row = conn.execute(
            text("SELECT status FROM experiment.experiment_orders WHERE order_id = :oid"),
            {"oid": order_id},
        ).fetchone()
    return row[0] if row else ""


class TestUpdateOrderStatusDB:
    """DB 集成测试：update_order_status 的强制校验。"""

    def test_legal_transition_draft_to_pending_approval(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-DRAFT-PA-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "DRAFT"))
        store.update_order_status(oid, "PENDING_APPROVAL", triggered_by="test", reason="submit")
        assert _get_order_status(store, oid) == "PENDING_APPROVAL"

    def test_legal_transition_pending_approval_to_approved(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-PA-AP-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "PENDING_APPROVAL"))
        store.update_order_status(oid, "APPROVED", approved_by="tester", triggered_by="tester")
        assert _get_order_status(store, oid) == "APPROVED"

    def test_legal_transition_approved_to_in_execution(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-AP-IE-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "APPROVED"))
        store.update_order_status(oid, "IN_EXECUTION", triggered_by="system")
        assert _get_order_status(store, oid) == "IN_EXECUTION"

    def test_legal_transition_in_execution_to_waiting_for_data(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-IE-WD-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "IN_EXECUTION"))
        store.update_order_status(oid, "WAITING_FOR_DATA")
        assert _get_order_status(store, oid) == "WAITING_FOR_DATA"

    def test_legal_transition_waiting_for_data_back_to_in_execution(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-WD-IE-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "WAITING_FOR_DATA"))
        store.update_order_status(oid, "IN_EXECUTION")
        assert _get_order_status(store, oid) == "IN_EXECUTION"

    def test_legal_transition_in_execution_to_completed(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-IE-CP-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "IN_EXECUTION"))
        store.update_order_status(oid, "COMPLETED")
        assert _get_order_status(store, oid) == "COMPLETED"

    def test_legal_transition_in_execution_to_validation_failed(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-IE-VF-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "IN_EXECUTION"))
        store.update_order_status(oid, "VALIDATION_FAILED")
        assert _get_order_status(store, oid) == "VALIDATION_FAILED"

    def test_legal_transition_validation_failed_retry_to_in_execution(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-VF-IE-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "VALIDATION_FAILED"))
        store.update_order_status(oid, "IN_EXECUTION", reason="retry")
        assert _get_order_status(store, oid) == "IN_EXECUTION"

    def test_legal_transition_draft_to_cancelled(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-DR-CA-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "DRAFT"))
        store.update_order_status(oid, "CANCELLED")
        assert _get_order_status(store, oid) == "CANCELLED"

    def test_legal_transition_approved_to_scheduled(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-AP-SC-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "APPROVED"))
        store.update_order_status(oid, "SCHEDULED")
        assert _get_order_status(store, oid) == "SCHEDULED"

    # --- 非法迁移 ---

    def test_illegal_transition_completed_to_approved(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-CP-AP-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "COMPLETED"))
        with pytest.raises(IllegalStateTransitionError) as exc_info:
            store.update_order_status(oid, "APPROVED")
        assert exc_info.value.from_status == "COMPLETED"
        assert exc_info.value.to_status == "APPROVED"

    def test_illegal_transition_completed_to_draft(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-CP-DR-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "COMPLETED"))
        with pytest.raises(IllegalStateTransitionError):
            store.update_order_status(oid, "DRAFT")

    def test_illegal_transition_cancelled_to_approved(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-CA-AP-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "CANCELLED"))
        with pytest.raises(IllegalStateTransitionError):
            store.update_order_status(oid, "APPROVED")

    def test_illegal_transition_cancelled_to_in_execution(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-CA-IE-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "CANCELLED"))
        with pytest.raises(IllegalStateTransitionError):
            store.update_order_status(oid, "IN_EXECUTION")

    def test_illegal_transition_draft_to_completed_skipping_steps(self, store, ensure_test_project, cleanup_order_ids):
        """DRAFT 不能直接跳到 COMPLETED。"""
        oid = cleanup_order_ids(f"T11-DR-CP-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "DRAFT"))
        with pytest.raises(IllegalStateTransitionError):
            store.update_order_status(oid, "COMPLETED")

    def test_illegal_transition_draft_to_in_execution(self, store, ensure_test_project, cleanup_order_ids):
        """DRAFT 不能直接跳到 IN_EXECUTION（必须先 PENDING_APPROVAL → APPROVED）。"""
        oid = cleanup_order_ids(f"T11-DR-IE-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "DRAFT"))
        with pytest.raises(IllegalStateTransitionError):
            store.update_order_status(oid, "IN_EXECUTION")

    def test_illegal_transition_waiting_for_data_to_draft(self, store, ensure_test_project, cleanup_order_ids):
        """WAITING_FOR_DATA 只能迁回 IN_EXECUTION 或推进到 COMPLETED。"""
        oid = cleanup_order_ids(f"T11-WD-DR-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "WAITING_FOR_DATA"))
        with pytest.raises(IllegalStateTransitionError):
            store.update_order_status(oid, "DRAFT")

    def test_illegal_transition_waiting_for_data_to_pending_approval(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-WD-PA-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "WAITING_FOR_DATA"))
        with pytest.raises(IllegalStateTransitionError):
            store.update_order_status(oid, "PENDING_APPROVAL")

    def test_illegal_transition_approved_to_waiting_for_data(self, store, ensure_test_project, cleanup_order_ids):
        """APPROVED 不能直接迁到 WAITING_FOR_DATA（必须先 IN_EXECUTION）。"""
        oid = cleanup_order_ids(f"T11-AP-WD-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "APPROVED"))
        with pytest.raises(IllegalStateTransitionError):
            store.update_order_status(oid, "WAITING_FOR_DATA")

    def test_illegal_transition_unknown_target_status(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-DR-XX-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "DRAFT"))
        with pytest.raises(IllegalStateTransitionError) as exc_info:
            store.update_order_status(oid, "UNKNOWN_STATUS")
        assert "Unknown target status" in str(exc_info.value)

    def test_illegal_transition_nonexistent_order(self, store, cleanup_order_ids):
        cleanup_order_ids("T11-NONEXISTENT-ORDER")
        with pytest.raises(IllegalStateTransitionError) as exc_info:
            store.update_order_status("T11-NONEXISTENT-ORDER", "APPROVED")
        assert "not found" in str(exc_info.value).lower()

    # --- 向后兼容 ---

    def test_rejected_alias_normalizes_to_cancelled(self, store, ensure_test_project, cleanup_order_ids):
        """旧 API 传入 REJECTED 应映射为 CANCELLED，且转换合法。"""
        oid = cleanup_order_ids(f"T11-PA-RJ-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "PENDING_APPROVAL"))
        store.update_order_status(oid, "REJECTED", approved_by="manager")
        assert _get_order_status(store, oid) == "CANCELLED"

    def test_rejected_alias_from_draft(self, store, ensure_test_project, cleanup_order_ids):
        """DRAFT 状态下传入 REJECTED 也应映射为 CANCELLED。"""
        oid = cleanup_order_ids(f"T11-DR-RJ-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "DRAFT"))
        store.update_order_status(oid, "REJECTED")
        assert _get_order_status(store, oid) == "CANCELLED"


# ───────────────────────── 事件日志测试 ─────────────────────────

class TestTransitionEventLog:
    """状态迁移事件日志写入测试。"""

    def test_transition_log_recorded(self, store, ensure_test_project, cleanup_order_ids):
        oid = cleanup_order_ids(f"T11-LOG-1-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "DRAFT"))
        store.update_order_status(
            oid, "PENDING_APPROVAL",
            triggered_by="test_user", reason="submit for review",
        )
        with store.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT from_status, to_status, triggered_by, reason "
                     "FROM experiment.experiment_order_status_transitions "
                     "WHERE order_id = :oid ORDER BY transition_id"),
                {"oid": oid},
            ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "DRAFT"
        assert rows[0][1] == "PENDING_APPROVAL"
        assert rows[0][2] == "test_user"
        assert rows[0][3] == "submit for review"

    def test_transition_log_multiple_entries(self, store, ensure_test_project, cleanup_order_ids):
        """多次迁移应产生多条日志，按时间顺序记录。"""
        oid = cleanup_order_ids(f"T11-LOG-2-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "DRAFT"))
        store.update_order_status(oid, "PENDING_APPROVAL")
        store.update_order_status(oid, "APPROVED", approved_by="approver")
        store.update_order_status(oid, "IN_EXECUTION")
        with store.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT from_status, to_status FROM experiment.experiment_order_status_transitions "
                     "WHERE order_id = :oid ORDER BY transition_id"),
                {"oid": oid},
            ).fetchall()
        assert len(rows) == 3
        assert rows[0] == ("DRAFT", "PENDING_APPROVAL")
        assert rows[1] == ("PENDING_APPROVAL", "APPROVED")
        assert rows[2] == ("APPROVED", "IN_EXECUTION")

    def test_transition_log_default_triggered_by(self, store, ensure_test_project, cleanup_order_ids):
        """未传 triggered_by 时默认为 'system'。"""
        oid = cleanup_order_ids(f"T11-LOG-3-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "DRAFT"))
        store.update_order_status(oid, "PENDING_APPROVAL")
        with store.engine.connect() as conn:
            row = conn.execute(
                text("SELECT triggered_by FROM experiment.experiment_order_status_transitions "
                     "WHERE order_id = :oid"),
                {"oid": oid},
            ).fetchone()
        assert row[0] == "system"

    def test_no_log_written_when_transition_fails(self, store, ensure_test_project, cleanup_order_ids):
        """非法迁移失败时不应写入事件日志。"""
        oid = cleanup_order_ids(f"T11-LOG-4-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "COMPLETED"))
        with pytest.raises(IllegalStateTransitionError):
            store.update_order_status(oid, "APPROVED")
        with store.engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM experiment.experiment_order_status_transitions "
                     "WHERE order_id = :oid"),
                {"oid": oid},
            ).fetchone()
        assert count[0] == 0

    def test_rejected_alias_logged_as_cancelled(self, store, ensure_test_project, cleanup_order_ids):
        """旧别名 REJECTED 在日志中记录为 CANCELLED。"""
        oid = cleanup_order_ids(f"T11-LOG-5-{uuid.uuid4().hex[:8]}")
        store.save_order(_make_order(oid, "PENDING_APPROVAL"))
        store.update_order_status(oid, "REJECTED")
        with store.engine.connect() as conn:
            row = conn.execute(
                text("SELECT from_status, to_status FROM experiment.experiment_order_status_transitions "
                     "WHERE order_id = :oid"),
                {"oid": oid},
            ).fetchone()
        assert row[0] == "PENDING_APPROVAL"
        assert row[1] == "CANCELLED"


# ───────────────────────── API 400 测试 ─────────────────────────

@pytest.fixture
def api_store_and_agent(ensure_test_project):
    """注入最小化 agent mock 到 api 模块，避免 BatteryMaterialsAgent 完整初始化。

    直接调用端点函数（而非 TestClient）以绕过 startup 事件中的 User 模型验证问题。
    """
    store = ensure_test_project
    mock_controller = types.SimpleNamespace(_store=store)
    mock_agent = types.SimpleNamespace(experiment_controller=mock_controller)

    import battery_materials_agent.api as api_module
    previous_agent = getattr(api_module, "agent", None)
    api_module.agent = mock_agent
    try:
        yield store
    finally:
        api_module.agent = previous_agent


class TestAPIIllegalTransition:
    """API 端点捕获 IllegalStateTransitionError 返回 400。"""

    def test_approve_completed_order_returns_400(self, api_store_and_agent):
        store = api_store_and_agent
        from battery_materials_agent.api import approve_experiment_order, OrderApprovalRequest
        from fastapi import HTTPException

        oid = f"T11-API-400-{uuid.uuid4().hex[:8]}"
        store.save_order(_make_order(oid, "COMPLETED"))
        try:
            req = OrderApprovalRequest(approved_by="tester", notes="try to re-approve completed")
            with pytest.raises(HTTPException) as exc_info:
                import asyncio
                asyncio.run(approve_experiment_order(oid, req))
            assert exc_info.value.status_code == 400
            detail = str(exc_info.value.detail)
            assert "COMPLETED" in detail
            assert "APPROVED" in detail
        finally:
            with store.engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM experiment.experiment_order_status_transitions WHERE order_id = :oid"),
                    {"oid": oid},
                )
                conn.execute(
                    text("DELETE FROM experiment.experiment_orders WHERE order_id = :oid"),
                    {"oid": oid},
                )

    def test_reject_completed_order_returns_400(self, api_store_and_agent):
        store = api_store_and_agent
        from battery_materials_agent.api import reject_experiment_order, OrderApprovalRequest
        from fastapi import HTTPException

        oid = f"T11-API-REJ-{uuid.uuid4().hex[:8]}"
        store.save_order(_make_order(oid, "COMPLETED"))
        try:
            req = OrderApprovalRequest(approved_by="tester", notes="try to reject completed")
            with pytest.raises(HTTPException) as exc_info:
                import asyncio
                asyncio.run(reject_experiment_order(oid, req))
            assert exc_info.value.status_code == 400
        finally:
            with store.engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM experiment.experiment_order_status_transitions WHERE order_id = :oid"),
                    {"oid": oid},
                )
                conn.execute(
                    text("DELETE FROM experiment.experiment_orders WHERE order_id = :oid"),
                    {"oid": oid},
                )

    def test_approve_pending_approval_order_succeeds(self, api_store_and_agent):
        """合法迁移应返回 200，验证 API 向后兼容。"""
        store = api_store_and_agent
        from battery_materials_agent.api import approve_experiment_order, OrderApprovalRequest

        oid = f"T11-API-OK-{uuid.uuid4().hex[:8]}"
        store.save_order(_make_order(oid, "PENDING_APPROVAL"))
        try:
            req = OrderApprovalRequest(approved_by="tester", notes="valid approval")
            import asyncio
            result = asyncio.run(approve_experiment_order(oid, req))
            assert result["status"] == "approved"
            assert _get_order_status(store, oid) == "APPROVED"
        finally:
            with store.engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM experiment.experiment_order_status_transitions WHERE order_id = :oid"),
                    {"oid": oid},
                )
                conn.execute(
                    text("DELETE FROM experiment.experiment_orders WHERE order_id = :oid"),
                    {"oid": oid},
                )
