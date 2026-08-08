"""0040 两层流程（Phase A）单元测试。

覆盖：
- 候选材料状态机迁移与角色校验（CandidateStore.update_status）
- 工艺方案结构化字段（routes / evidence_refs / status / owner）持久化
- 工艺方案状态机迁移（ProcessSchemeStore.update_status）
- 一键生成实验单：配方来源 + 已确认工艺路径双引用

数据库依赖：PostgreSQL 已就绪且 alembic 已 upgrade 到 0040_two_layer_formulation_process。
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from battery_materials_agent.experiment.candidate_store import (
    CandidateRecord,
    CandidateStatus,
    CandidateStore,
    IllegalCandidateTransitionError,
)
from battery_materials_agent.experiment.process_scheme_store import (
    IllegalProcessSchemeTransitionError,
    ProcessScheme,
    ProcessSchemeStatus,
    ProcessSchemeStore,
)
from battery_materials_agent.experiment.experiment_controller import (
    ExperimentController,
    ExperimentOrder,
    ExperimentOrderStatus,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_VERSIONS_DIR = PROJECT_ROOT / "alembic" / "versions"


def _unique_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# 每个测试候选使用不重复的元素化学式，确保 content_hash（化学式+"|"+应用）唯一，
# 避免 CandidateStore.save() 的 T-020 去重把不同测试候选误判为同一材料而不入库，
# 进而导致 process_schemes.candidate_id 外键违例。
_AUTOGEN_ELEMENTS = [
    "Li", "Na", "K", "Mg", "Ca", "Sr", "Ba", "Al", "Ti", "Zr", "Nb", "Mo",
]
_autogen_counter = 0


def _unique_candidate_formula() -> str:
    global _autogen_counter
    el = _AUTOGEN_ELEMENTS[_autogen_counter % len(_AUTOGEN_ELEMENTS)]
    _autogen_counter += 1
    return f"{el}2O3"


class TestMigration0040:
    """验证 0040 迁移文件结构。"""

    def test_migration_file_exists(self):
        path = ALEMBIC_VERSIONS_DIR / "0040_two_layer_formulation_process.py"
        assert path.exists(), f"迁移文件不存在: {path}"

    def test_migration_covers_all_four_tables(self):
        path = ALEMBIC_VERSIONS_DIR / "0040_two_layer_formulation_process.py"
        content = path.read_text(encoding="utf-8")
        # 候选状态机
        assert 'ADD COLUMN IF NOT EXISTS status' in content
        assert 'ADD COLUMN IF NOT EXISTS owner' in content
        assert 'ADD COLUMN IF NOT EXISTS assigned_role' in content
        # 工艺方案结构化
        assert 'ADD COLUMN IF NOT EXISTS routes' in content
        assert 'ADD COLUMN IF NOT EXISTS evidence_refs' in content
        # 实验单双来源
        assert 'ADD COLUMN IF NOT EXISTS process_id' in content


@pytest.fixture
def candidate_store():
    return CandidateStore()


@pytest.fixture
def process_store():
    return ProcessSchemeStore()


@pytest.fixture
def controller():
    return ExperimentController(db_path="data/experiments.db")


@pytest.fixture
def ensure_candidate(candidate_store):
    cid = _unique_id("T2L-CAND")
    candidate_store.save(CandidateRecord(
        candidate_id=cid,
        candidate_type="crystal",
        name=f"TwoLayer-{cid}",
        smiles="",
        source="two_layer_test",
        scenario_id="",
        multi_objective_score=0.9,
        data={"test": True, "formula": _unique_candidate_formula()},
    ))
    yield cid
    with candidate_store.engine.begin() as conn:
        conn.execute(
            text("DELETE FROM experiment.candidates WHERE candidate_id = :cid"),
            {"cid": cid},
        )


@pytest.fixture
def ensure_process(process_store, ensure_candidate):
    pid = _unique_id("T2L-PROC")
    scheme = ProcessScheme(
        process_id=pid,
        candidate_id=ensure_candidate,
        steps=[{"step": 1, "action": "混合", "equipment": "EQ-MIX-01"}],
        routes=[{"route_id": "R1", "score": 0.9}],
        evidence_refs=[{"step": 1, "provider": "scp_dft", "tier": "real_engine"}],
        raw_materials=[{"material_id": "M1", "name": "LiOH", "required_quantity": 1.0}],
        metadata={"version": "v1"},
        owner="proc_engineer",
    )
    process_store.create(scheme)
    yield pid
    with process_store.engine.begin() as conn:
        conn.execute(
            text("DELETE FROM experiment.process_schemes WHERE process_id = :pid"),
            {"pid": pid},
        )


class TestCandidateStatusMachine:
    def test_default_status_is_screening(self, candidate_store, ensure_candidate):
        rec = candidate_store.get(ensure_candidate)
        assert rec.status == CandidateStatus.SCREENING.value

    def test_legal_transition_screening_to_feasible(self, candidate_store, ensure_candidate):
        updated = candidate_store.update_status(
            ensure_candidate, CandidateStatus.FEASIBLE.value,
            actor_operation_roles={"formulator"}, owner="formulator_a",
        )
        assert updated.status == CandidateStatus.FEASIBLE.value
        assert updated.assigned_role == "formulator"
        assert updated.owner == "formulator_a"

    def test_transition_to_process_planning_requires_process_engineer(
        self, candidate_store, ensure_candidate
    ):
        # 先交棒给工艺阶段
        candidate_store.update_status(
            ensure_candidate, CandidateStatus.FEASIBLE.value, actor_operation_roles={"formulator"},
        )
        # formulator 无权进入 process_planning
        with pytest.raises(IllegalCandidateTransitionError):
            candidate_store.update_status(
                ensure_candidate, CandidateStatus.PROCESS_PLANNING.value,
                actor_operation_roles={"formulator"},
            )
        # process_engineer 可以
        updated = candidate_store.update_status(
            ensure_candidate, CandidateStatus.PROCESS_PLANNING.value,
            actor_operation_roles={"process_engineer"}, owner="proc_b",
        )
        assert updated.assigned_role == "process_engineer"

    def test_illegal_skip_transition(self, candidate_store, ensure_candidate):
        # screening 不能直接跳到 ready_for_experiment
        with pytest.raises(IllegalCandidateTransitionError):
            candidate_store.update_status(
                ensure_candidate, CandidateStatus.READY_FOR_EXPERIMENT.value,
                actor_operation_roles={"formulator"},
            )

    def test_full_chain_to_ready(self, candidate_store, ensure_candidate):
        candidate_store.update_status(ensure_candidate, CandidateStatus.FEASIBLE.value, actor_operation_roles={"formulator"})
        candidate_store.update_status(ensure_candidate, CandidateStatus.PROCESS_PLANNING.value, actor_operation_roles={"process_engineer"})
        candidate_store.update_status(ensure_candidate, CandidateStatus.PROCESS_CONFIRMED.value, actor_operation_roles={"process_engineer"})
        updated = candidate_store.update_status(ensure_candidate, CandidateStatus.READY_FOR_EXPERIMENT.value, actor_operation_roles={"process_engineer"})
        assert updated.status == CandidateStatus.READY_FOR_EXPERIMENT.value

    def test_reject_from_screening(self, candidate_store, ensure_candidate):
        updated = candidate_store.update_status(
            ensure_candidate, CandidateStatus.REJECTED.value, actor_operation_roles={"formulator"},
        )
        assert updated.status == CandidateStatus.REJECTED.value


class TestProcessSchemeStructured:
    def test_create_persists_routes_evidence_status(self, process_store, ensure_process,
                                                     ensure_candidate):
        scheme = process_store.get(ensure_process)
        assert scheme.routes == [{"route_id": "R1", "score": 0.9}]
        assert scheme.evidence_refs == [{"step": 1, "provider": "scp_dft", "tier": "real_engine"}]
        assert scheme.raw_materials == [
            {"material_id": "M1", "name": "LiOH", "required_quantity": 1.0}
        ]
        assert scheme.status == ProcessSchemeStatus.DRAFT.value
        assert scheme.owner == "proc_engineer"

    def test_default_status_draft(self, process_store, ensure_candidate):
        pid = _unique_id("T2L-PROC2")
        scheme = ProcessScheme(process_id=pid, candidate_id=ensure_candidate)
        process_store.create(scheme)
        try:
            assert process_store.get(pid).status == ProcessSchemeStatus.DRAFT.value
        finally:
            process_store.delete(pid)

    def test_status_transition_chain(self, process_store, ensure_process):
        process_store.update_status(ensure_process, ProcessSchemeStatus.REVIEWING.value, owner="proc_c")
        confirmed = process_store.update_status(
            ensure_process, ProcessSchemeStatus.CONFIRMED.value, owner="proc_c",
        )
        assert confirmed.status == ProcessSchemeStatus.CONFIRMED.value
        assert confirmed.owner == "proc_c"

    def test_illegal_transition_from_confirmed(self, process_store, ensure_process):
        process_store.update_status(ensure_process, ProcessSchemeStatus.REVIEWING.value)
        process_store.update_status(ensure_process, ProcessSchemeStatus.CONFIRMED.value)
        # confirmed 是终态，不可再回退
        with pytest.raises(IllegalProcessSchemeTransitionError):
            process_store.update_status(ensure_process, ProcessSchemeStatus.DRAFT.value)

    def test_non_process_engineer_blocked(self, process_store, ensure_process):
        with pytest.raises(IllegalProcessSchemeTransitionError):
            process_store.update_status(
                ensure_process, ProcessSchemeStatus.REVIEWING.value,
                require_role="formulator",
            )


class TestOneClickExperiment:
    def test_create_without_process_links_candidate(self, controller, ensure_candidate):
        order = controller.create_order_for_candidate_and_process(
            candidate_id=ensure_candidate, project_id="",
        )
        try:
            assert order.candidate_id == ensure_candidate
            assert order.process_id == ""
            assert order.status == ExperimentOrderStatus.DRAFT.value
            loaded = controller._store.get_order(order.order_id)
            assert loaded.candidate_id == ensure_candidate
        finally:
            with controller._store.engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM experiment.experiment_orders "
                         "WHERE order_id = :oid"),
                    {"oid": order.order_id},
                )

    def test_create_with_unconfirmed_process_rejected(self, controller, ensure_candidate):
        # 未确认的工艺方案（默认 draft）应被拒绝
        from battery_materials_agent.experiment.process_scheme_store import ProcessSchemeStore
        pid = _unique_id("T2L-NOTCONF")
        ProcessSchemeStore().create(ProcessScheme(
            process_id=pid, candidate_id=ensure_candidate,
            steps=[{"step": 1, "action": "x"}],
        ))
        try:
            with pytest.raises(ValueError):
                controller.create_order_for_candidate_and_process(
                    candidate_id=ensure_candidate, process_id=pid,
                )
        finally:
            ProcessSchemeStore().delete(pid)

    def test_create_with_confirmed_process_backfills(self, controller, ensure_process,
                                                     ensure_candidate):
        # 先确认工艺方案
        ProcessSchemeStore().update_status(ensure_process, "reviewing", owner="proc_c")
        ProcessSchemeStore().update_status(ensure_process, "confirmed", owner="proc_c")

        order = controller.create_order_for_candidate_and_process(
            candidate_id=ensure_candidate, process_id=ensure_process,
        )
        try:
            assert order.candidate_id == ensure_candidate
            assert order.process_id == ensure_process
            # 工艺步骤与原料清单被回填
            assert order.procedure == [{"step": 1, "action": "混合", "equipment": "EQ-MIX-01"}]
            assert order.material_requirements == [
                {"material_id": "M1", "name": "LiOH", "required_quantity": 1.0}
            ]
            assert order.process_version == "v1"
        finally:
            with controller._store.engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM experiment.experiment_orders "
                         "WHERE order_id = :oid"),
                    {"oid": order.order_id},
                )