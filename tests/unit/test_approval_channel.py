"""Task 20 回归测试：审批目标通道（channel）前后端一致化。

验证 create_approval 返回 channel / channel_label，且消息包含目标通道；
审批中心列表（/approvals/pending）能据 notes 区分审批通道（实验审批 / 委员会评审）。
"""

from __future__ import annotations

import asyncio
import types
import uuid

import pytest
from sqlalchemy import text

from battery_materials_agent.experiment.experiment_controller import (
    ExperimentDataStore,
    ExperimentOrder,
)


@pytest.fixture
def api_store_and_agent():
    """注入最小化 agent mock 到 api 模块，直接调用端点函数以绕过 startup 事件。"""
    store = ExperimentDataStore()
    mock_controller = types.SimpleNamespace(_store=store)
    mock_agent = types.SimpleNamespace(experiment_controller=mock_controller)

    import battery_materials_agent.api as api_module
    previous_agent = getattr(api_module, "agent", None)
    api_module.agent = mock_agent
    try:
        yield store
    finally:
        api_module.agent = previous_agent


def _cleanup_order(store, order_id: str):
    with store.engine.begin() as conn:
        conn.execute(
            text("DELETE FROM experiment.experiment_order_status_transitions WHERE order_id = :oid"),
            {"oid": order_id},
        )
        conn.execute(
            text("DELETE FROM experiment.experiment_orders WHERE order_id = :oid"),
            {"oid": order_id},
        )


class TestApprovalChannel:
    def test_create_approval_returns_channel_and_persists(self, api_store_and_agent):
        store = api_store_and_agent
        from battery_materials_agent.api import ApprovalCreateRequest, create_approval

        oid = None
        try:
            req = ApprovalCreateRequest(
                title="候选材料审批：LiFePO4",
                type="material_adoption",
                # project_id/task_id 留空，避免 FK 约束失败（不存在的项目）
                payload={
                    "candidate": {"candidate_id": "C-001", "formula": "LiFePO4"},
                    "project_id": "",
                    "task_id": "",
                },
                requester="tester",
            )
            result = asyncio.run(create_approval(req))
            oid = result["approval_id"]

            assert result["status"] == "PENDING_APPROVAL"
            assert result["channel"] == "experiment"
            assert result["channel_label"] == "实验审批"
            assert "实验审批" in result["message"]

            # 审批中心列表应能查询到该事项并区分审批通道
            from battery_materials_agent.api import list_pending_approvals
            items = asyncio.run(list_pending_approvals())["items"]
            matched = [it for it in items if it["id"] == oid]
            assert matched, "创建审批后，审批中心应能查询到该事项"
            assert matched[0]["channel"] == "实验审批"
            assert matched[0]["details"]["channel"] == "实验审批"
        finally:
            if oid:
                _cleanup_order(store, oid)

    def test_committee_channel_label_detected(self, api_store_and_agent):
        """订单 notes 标记为委员会评审时，审批中心应归入「委员会评审」通道。"""
        store = api_store_and_agent
        from battery_materials_agent.api import list_pending_approvals

        oid = f"T20-CH-{uuid.uuid4().hex[:8]}"
        store.save_order(ExperimentOrder(
            order_id=oid,
            status="PENDING_APPROVAL",
            notes="候选材料 | 审批通道: 委员会评审",
            assignee="tester",
        ))
        try:
            items = asyncio.run(list_pending_approvals())["items"]
            matched = [it for it in items if it["id"] == oid]
            assert matched, "列表应能查询到委员会评审订单"
            assert matched[0]["channel"] == "委员会评审"
        finally:
            _cleanup_order(store, oid)