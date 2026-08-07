"""Phase B：工艺深化编排服务单元测试。

覆盖：
- 工艺深化生成工艺方案（routes / evidence_refs 持久化）
- SCP 优先：SCP 可用时走 SCP，并记录 scp 来源
- 本地回退：SCP 不可用时回退本地，并记录 local 来源
- 无 SMILES 的候选拒绝深化

数据库依赖：PostgreSQL 已就绪且 alembic 已 upgrade 到 0040。
SCP 调用通过注入假 client_pool/catalog 隔离，不触网。
"""
from __future__ import annotations

import uuid

import pytest

from battery_materials_agent.experiment.candidate_store import (
    CandidateRecord,
    CandidateStore,
)
from battery_materials_agent.experiment.process_scheme_store import (
    ProcessScheme,
    ProcessSchemeStore,
)
from battery_materials_agent.experiment.process_deepening_service import (
    ProcessDeepeningService,
)
from battery_materials_agent.synthesis.synthesis_planner import (
    RouteStep,
    SynthesisRoute,
)


def _unique_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class FakeSynthesisPlanner:
    """本地逆合成/DFT 假实现：不触网，返回固定路线。"""

    def __init__(self, routes=None, raise_on_plan=False):
        self._routes = routes or [
            SynthesisRoute(
                target_smiles="CCO",
                steps=[RouteStep(reaction_smiles="CC=O.[H][H]>>CCO", score=0.9,
                                 reaction_type="reduction")],
                overall_score=90.0,
                num_steps=1,
                feasibility_score=0.9,
                is_feasible=True,
                confidence=0.8,
            )
        ]
        self._raise_on_plan = raise_on_plan

    async def plan_synthesis_async(self, smiles, max_depth=3, num_routes=5):
        if self._raise_on_plan:
            raise RuntimeError("fake plan failure")
        return self._routes

    async def verify_with_dft(self, route: dict) -> dict:
        return {
            "route_id": route.get("route_id", ""),
            "step_results": [{"step_idx": 0, "status": "passed", "energy_change": 2.0}],
            "overall_status": "passed",
            "original_confidence": 0.8,
            "adjusted_confidence": 0.84,
            "method": "template-based DFT estimate",
        }


class FakeSCPCatalog:
    def __init__(self, enabled=True):
        self._enabled = enabled

    def get(self, name):
        return FakeBinding(name, self._enabled)


class FakeBinding:
    def __init__(self, name, enabled=True):
        self.name = name
        self.enabled = enabled
        self.server_id = "31" if enabled else ""
        self.remote_tool_name = "retrosynthesis"
        self.server_url = "https://fake.scp"
        self.provider = "FakeProvider"


class FakeSCPClientPool:
    def __init__(self, succeed=True, invalid_data=False):
        self._succeed = succeed
        # invalid_data：返回 status=success 但数据不符合能力语义（如绑定错工具）
        self._invalid_data = invalid_data

    async def call_tool(self, server_id, tool_name, arguments, server_url=None):
        if not self._succeed:
            return {"status": "error", "error": "fake scp failure"}
        if self._invalid_data:
            # 合成路径规划返回了无 routes 的数据；DFT 返回了无 overall_status 的数据
            return {"status": "success", "data": {"weight": 180.2, "cas": "64-17-5"}}
        return {
            "status": "success",
            "data": {"routes": [{
                "route_id": "SCP-R1",
                "steps": [{"reaction_smiles": "A>>B"}],
                "confidence": 0.9,
            }]},
        }


@pytest.fixture
def candidate_store():
    return CandidateStore()


@pytest.fixture
def process_store():
    return ProcessSchemeStore()


@pytest.fixture
def ensure_candidate(candidate_store):
    cid = _unique_id("PDS-CAND")
    candidate_store.save(CandidateRecord(
        candidate_id=cid,
        candidate_type="polymer",
        name=f"PDSC-{cid}",
        smiles="CCO",
        source="process_deepening_test",
        multi_objective_score=0.8,
        data={"formula": f"PDSC-{cid}"},
    ))
    yield cid
    from sqlalchemy import text
    with candidate_store.engine.begin() as conn:
        conn.execute(
            text("DELETE FROM experiment.process_schemes WHERE candidate_id = :cid"),
            {"cid": cid},
        )
        conn.execute(
            text("DELETE FROM experiment.candidates WHERE candidate_id = :cid"),
            {"cid": cid},
        )


class TestProcessDeepening:
    async def test_deepen_produces_scheme_local_fallback(self, candidate_store,
                                                          process_store, ensure_candidate):
        planner = FakeSynthesisPlanner()
        svc = ProcessDeepeningService(
            process_scheme_store=process_store,
            candidate_store=candidate_store,
            synthesis_planner=planner,
            scp_client_pool=None,  # 无 SCP → 走本地
            scp_catalog=None,
        )
        scheme = await svc.deepen(ensure_candidate, owner="proc_engineer")
        assert scheme.candidate_id == ensure_candidate
        assert scheme.owner == "proc_engineer"
        assert len(scheme.routes) >= 1
        assert scheme.process_id  # 已落库
        # 本地来源记录
        sources = [e.get("source") for e in scheme.evidence_refs]
        assert "local" in sources
        # DFT 回写
        assert any("dft" in r for r in scheme.routes)
        # 持久化可复查
        persisted = process_store.get(scheme.process_id)
        assert persisted is not None
        assert persisted.evidence_refs

    async def test_deepen_scp_priority(self, candidate_store, process_store,
                                       ensure_candidate):
        planner = FakeSynthesisPlanner()
        svc = ProcessDeepeningService(
            process_scheme_store=process_store,
            candidate_store=candidate_store,
            synthesis_planner=planner,
            scp_client_pool=FakeSCPClientPool(succeed=True),
            scp_catalog=FakeSCPCatalog(enabled=True),
        )
        scheme = await svc.deepen(ensure_candidate, owner="proc_engineer")
        sources = [e.get("source") for e in scheme.evidence_refs]
        # SCP 成功时优先使用 SCP 来源
        assert "scp" in sources
        assert scheme.routes

    async def test_scp_failure_falls_back_to_local(self, candidate_store,
                                                   process_store, ensure_candidate):
        planner = FakeSynthesisPlanner()
        svc = ProcessDeepeningService(
            process_scheme_store=process_store,
            candidate_store=candidate_store,
            synthesis_planner=planner,
            scp_client_pool=FakeSCPClientPool(succeed=False),
            scp_catalog=FakeSCPCatalog(enabled=True),
        )
        scheme = await svc.deepen(ensure_candidate, owner="proc_engineer")
        sources = [e.get("source") for e in scheme.evidence_refs]
        # SCP 失败 → 记录 scp failed + 本地成功
        assert "scp" in sources
        assert "local" in sources
        assert len(scheme.routes) >= 1

    async def test_deepen_without_smiles_rejected(self, candidate_store,
                                                  process_store):
        cid = _unique_id("PDS-NOS")
        candidate_store.save(CandidateRecord(
            candidate_id=cid, candidate_type="crystal", name=f"no-smiles-{cid}",
            smiles="", source="test",
        ))
        try:
            svc = ProcessDeepeningService(
                process_scheme_store=process_store,
                candidate_store=candidate_store,
                synthesis_planner=FakeSynthesisPlanner(),
            )
            with pytest.raises(ValueError):
                await svc.deepen(cid)
        finally:
            from sqlalchemy import text
            with candidate_store.engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM experiment.candidates WHERE candidate_id = :cid"),
                    {"cid": cid},
                )

    async def test_scp_invalid_response_falls_back_local(self, candidate_store,
                                                         process_store, ensure_candidate):
        """回归：SCP 返回 status=success 但数据不符合能力语义时应回退本地。

        绑定错工具（如 SMILESToWeight / SMILESToCAS）时，SCP 会返回"成功"但数据
        无合成路径/DFT 语义。此时不得记录虚假的 scp 成功来源，也不得与本地成功
        来源同时出现（AI 透明度要求）。
        """
        svc = ProcessDeepeningService(
            process_scheme_store=process_store,
            candidate_store=candidate_store,
            synthesis_planner=FakeSynthesisPlanner(),
            scp_client_pool=FakeSCPClientPool(succeed=True, invalid_data=True),
            scp_catalog=FakeSCPCatalog(enabled=True),
        )
        scheme = await svc.deepen(ensure_candidate, owner="proc_engineer")

        # 路线来自本地回退
        assert len(scheme.routes) >= 1
        # 合成路径规划：必须记录 scp failed（语义不符），不能有 scp success
        plan_ev = [e for e in scheme.evidence_refs
                   if e.get("capability") == "synthesis_planning"]
        assert not any(e.get("status") == "success" and e.get("source") == "scp"
                       for e in plan_ev)
        assert any(e.get("status") == "failed" and "语义" in e.get("detail", "")
                   for e in plan_ev)
        # 本地成功来源存在
        assert any(e.get("source") == "local" and e.get("status") == "success"
                   for e in plan_ev)

    async def test_dft_scp_attempts_recorded_in_evidence(self, candidate_store,
                                                         process_store, ensure_candidate):
        """回归：DFT 校验的 SCP 尝试（无论成败）必须记录进 evidence_refs。"""
        svc = ProcessDeepeningService(
            process_scheme_store=process_store,
            candidate_store=candidate_store,
            synthesis_planner=FakeSynthesisPlanner(),
            scp_client_pool=FakeSCPClientPool(succeed=True, invalid_data=True),
            scp_catalog=FakeSCPCatalog(enabled=True),
        )
        scheme = await svc.deepen(ensure_candidate, owner="proc_engineer")

        dft_ev = [e for e in scheme.evidence_refs
                  if e.get("capability") == "dft_verification"]
        # 至少存在一条 DFT 来源记录（SCP 尝试或本地成功）
        assert dft_ev
        # SCP 返回的 DFT 数据无 overall_status → 应记录失败的 scp 尝试
        assert any(e.get("source") == "scp" and e.get("status") == "failed"
                   for e in dft_ev)
        # 本地回退成功后记录了 local 成功
        assert any(e.get("source") == "local" and e.get("status") == "success"
                   for e in dft_ev)

    async def test_dft_scp_success_used_and_recorded(self, candidate_store,
                                                     process_store, ensure_candidate):
        """回归：SCP 返回符合 DFT 语义的数据时，采用 SCP 结果并记录 scp 成功来源。"""
        class _DftSCPClientPool(FakeSCPClientPool):
            async def call_tool(self, server_id, tool_name, arguments, server_url=None):
                if arguments.get("route") is not None:
                    # DFT 校验：返回符合 overall_status 语义的数据
                    return {"status": "success", "data": {
                        "route_id": arguments["route"].get("route_id", ""),
                        "overall_status": "passed",
                        "original_confidence": 0.9,
                        "adjusted_confidence": 0.95,
                        "method": "scp-dft",
                    }}
                return {"status": "success", "data": {"routes": [{
                    "route_id": "SCP-R1", "steps": [], "confidence": 0.9}]}}

        svc = ProcessDeepeningService(
            process_scheme_store=process_store,
            candidate_store=candidate_store,
            synthesis_planner=FakeSynthesisPlanner(),
            scp_client_pool=_DftSCPClientPool(succeed=True),
            scp_catalog=FakeSCPCatalog(enabled=True),
        )
        scheme = await svc.deepen(ensure_candidate, owner="proc_engineer")

        dft_ev = [e for e in scheme.evidence_refs
                  if e.get("capability") == "dft_verification"]
        # 存在 scp 成功的 DFT 来源
        assert any(e.get("source") == "scp" and e.get("status") == "success"
                   for e in dft_ev)
        # SCP 成功时不应再回退本地（不出现 local 成功）
        assert not any(e.get("source") == "local" and e.get("status") == "success"
                       for e in dft_ev)

    async def test_deepen_advances_candidate_to_process_planning(self, candidate_store,
                                                                 process_store):
        """回归：工艺深化开始时，候选应从 feasible 交棒到 process_planning。

        否则后续"确认工艺方案"会尝试 feasible → process_confirmed 而非法。
        """
        cid = _unique_id("PDS-HAND")
        candidate_store.save(CandidateRecord(
            candidate_id=cid, candidate_type="polymer", name=f"hand-{cid}",
            smiles="CCO", source="test", status="feasible", owner="formulator",
            assigned_role="formulator",
        ))
        try:
            svc = ProcessDeepeningService(
                process_scheme_store=process_store,
                candidate_store=candidate_store,
                synthesis_planner=FakeSynthesisPlanner(),
            )
            await svc.deepen(cid, owner="proc_engineer")
            rec = candidate_store.get(cid)
            assert rec.status == "process_planning"
            assert rec.assigned_role == "process_engineer"
            assert rec.owner == "proc_engineer"

            # 且此刻可合法执行"确认工艺方案"：process_planning → process_confirmed
            candidate_store.update_status(
                cid, "process_confirmed", actor_role="process_engineer",
                owner="proc_engineer", reason="回归：确认工艺方案",
            )
            assert candidate_store.get(cid).status == "process_confirmed"
        finally:
            from sqlalchemy import text
            with candidate_store.engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM experiment.process_schemes WHERE candidate_id = :cid"),
                    {"cid": cid},
                )
                conn.execute(
                    text("DELETE FROM experiment.candidates WHERE candidate_id = :cid"),
                    {"cid": cid},
                )