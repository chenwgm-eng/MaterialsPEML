"""SCPClientPool 审计落盘回归测试。

覆盖 Review 发现的 TODO：「SCP_AUDIT 仅打日志，未持久化到 audit 表」。
验证：
- ``_map_audit_status`` 将传输层状态正确映射到 ExternalInvocation.status 枚举；
- ``_persist_audit`` 构造并写入 AuditStore（append-only），且审计失败不抛出。
"""
from __future__ import annotations

from battery_materials_agent.mcp_tools.scp_client import SCPClientPool
from battery_materials_agent.config import SCPConfig


class _FakeAuditStore:
    """内存版 AuditStore，记录每次 append 的调用。"""

    def __init__(self):
        self.appended = []

    def append(self, invocation) -> str:
        self.appended.append(invocation)
        return invocation.invocation_id


class TestMapAuditStatus:
    def test_success(self):
        assert SCPClientPool._map_audit_status("success") == "success"

    def test_blocked(self):
        assert SCPClientPool._map_audit_status("blocked") == "blocked"

    def test_timeout(self):
        assert SCPClientPool._map_audit_status("timeout") == "timeout"

    def test_error_and_failed_default_to_failed(self):
        assert SCPClientPool._map_audit_status("error") == "failed"
        assert SCPClientPool._map_audit_status("failed") == "failed"
        assert SCPClientPool._map_audit_status("unknown") == "failed"


class TestPersistAudit:
    def setup_method(self):
        self.pool = SCPClientPool(SCPConfig())
        self.fake_store = _FakeAuditStore()

    def test_append_success_record(self, monkeypatch):
        monkeypatch.setattr(
            "battery_materials_agent.mcp_tools.scp_client.AuditStore",
            lambda: self.fake_store,
        )
        self.pool._persist_audit(
            request_id="scp_1_foo",
            server_id="srv",
            tool_name="foo",
            arguments={"project_id": "P1", "run_id": "R1", "data": "x"},
            response_status="success",
            error_message=None,
            latency_ms=120,
        )
        assert len(self.fake_store.appended) == 1
        rec = self.fake_store.appended[0]
        assert rec.provider == "scp"
        assert rec.capability == "foo"
        assert rec.status == "success"
        assert rec.project_id == "P1"
        assert rec.run_id == "R1"
        assert rec.latency_ms == 120
        # 输入脱敏：输入元数据仅保留键名，不落完整参数
        assert rec.input_redacted["args_keys"] == ["project_id", "run_id", "data"]

    def test_append_failed_record_with_error(self, monkeypatch):
        monkeypatch.setattr(
            "battery_materials_agent.mcp_tools.scp_client.AuditStore",
            lambda: self.fake_store,
        )
        self.pool._persist_audit(
            request_id="scp_2_bar",
            server_id="srv",
            tool_name="bar",
            arguments={},
            response_status="failed",
            error_message="boom",
            latency_ms=50,
        )
        rec = self.fake_store.appended[0]
        assert rec.status == "failed"
        assert rec.error_code == "boom"

    def test_audit_failure_does_not_raise(self, monkeypatch):
        async def _ok_impl(self, server_id, tool_name, arguments, server_url=None):
            return {"status": "success", "data": {}}

        monkeypatch.setattr(
            "battery_materials_agent.mcp_tools.scp_client.SCPClientPool._call_tool_impl",
            _ok_impl,
        )

        def _boom(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(
            "battery_materials_agent.mcp_tools.scp_client.AuditStore", _boom
        )
        # call_tool 的 finally 应吞掉审计落盘失败，主流程返回正常结果
        import asyncio

        result = asyncio.run(
            self.pool.call_tool("srv", "baz", {"project_id": "P1"})
        )
        assert result["status"] == "success"