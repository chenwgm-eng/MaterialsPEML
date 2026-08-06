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
    def __init__(self, succeed=True):
        self._succeed = succeed

    async def call_tool(self, server_id, tool_name, arguments, server_url=None):
        if self._succeed:
            return {
                "status": "success",
                "data": {"routes": [{
                    "route_id": "SCP-R1",
                    "steps": [{"reaction_smiles": "A>>B"}],
                    "confidence": 0.9,
                }]},
            }
        return {"status": "error", "error": "fake scp failure"}


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