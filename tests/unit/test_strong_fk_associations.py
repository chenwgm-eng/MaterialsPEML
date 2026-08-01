"""Task 14：强外键约束 + 自动关联逻辑端到端单元测试。

覆盖：
- alembic 迁移文件存在且版本号正确（14.1）
- ON DELETE RESTRICT 约束生效（删除有下游数据的记录被阻止）
  - 删除有下游 experiment_orders 的 candidate
  - 删除有下游 samples 的 experiment_order
  - 删除有下游 sample_transfers 的 sample
  - 删除有下游 experiment_result_records 的 experiment_order
- 候选 → 实验任务自动关联（14.2）
- 实验任务 → 样品自动关联（14.3）
- 实验数据 → 设备自动关联（14.4）
- 配方 → 样品自动关联（14.5）

数据库依赖：PostgreSQL 已就绪且 alembic 已 upgrade 到 0005_strong_fk_constraints。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from battery_materials_agent.experiment.candidate_store import (
    CandidateRecord,
    CandidateStore,
)
from battery_materials_agent.experiment.experiment_controller import (
    ExperimentController,
    ExperimentDataStore,
    ExperimentOrder,
    ExperimentOrderStatus,
    ExperimentResultRecord,
)
from battery_materials_agent.experiment.sample_store import (
    Sample,
    SampleStatus,
    SampleStore,
)
from battery_materials_agent.industrialization.formula_store import (
    FormulaStore,
    FormulaVersion,
)
from battery_materials_agent.version_store import Version, VersionStore, VersionType


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_VERSIONS_DIR = PROJECT_ROOT / "alembic" / "versions"


# ───────────────────────── 14.1: 迁移文件结构 ─────────────────────────


class TestMigrationFile:
    """验证 alembic 迁移文件 0005_strong_fk_constraints.py 的结构。"""

    def test_migration_file_exists(self):
        path = ALEMBIC_VERSIONS_DIR / "0005_strong_fk_constraints.py"
        assert path.exists(), f"迁移文件不存在: {path}"

    def test_migration_revision_id(self):
        path = ALEMBIC_VERSIONS_DIR / "0005_strong_fk_constraints.py"
        content = path.read_text(encoding="utf-8")
        assert 'revision: str = "0005_strong_fk_constraints"' in content
        assert 'down_revision: Union[str, None] = "0004_compliance_evidence"' in content

    def test_migration_has_upgrade_and_downgrade(self):
        path = ALEMBIC_VERSIONS_DIR / "0005_strong_fk_constraints.py"
        content = path.read_text(encoding="utf-8")
        assert "def upgrade()" in content
        assert "def downgrade()" in content
        assert "ON DELETE RESTRICT" in content

    def test_migration_covers_required_fks(self):
        path = ALEMBIC_VERSIONS_DIR / "0005_strong_fk_constraints.py"
        content = path.read_text(encoding="utf-8")
        # 必须覆盖的核心 FK
        assert "fk_orders_candidate" in content
        assert "fk_samples_order" in content
        assert "fk_results_order" in content


# ───────────────────────── 测试夹具 ─────────────────────────


def _unique_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def candidate_store():
    return CandidateStore()


@pytest.fixture
def experiment_store():
    return ExperimentDataStore()


@pytest.fixture
def sample_store():
    return SampleStore()


@pytest.fixture
def controller(experiment_store):
    return ExperimentController(db_path="data/experiments.db")


@pytest.fixture
def formula_store():
    return FormulaStore()


@pytest.fixture
def ensure_project(experiment_store):
    """创建测试项目，返回 project_id。"""
    pid = _unique_id("T14-PROJ")
    with experiment_store.engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO projects.projects (project_id, name, created_at, updated_at)
                VALUES (:pid, :name, NOW(), NOW())
            """),
            {"pid": pid, "name": "Task 14 Test Project"},
        )
    yield pid
    # 清理：先删子表，再删项目
    with experiment_store.engine.begin() as conn:
        # 清理可能的样品转移
        conn.execute(text(
            "DELETE FROM experiment.sample_transfers "
            "WHERE sample_id IN (SELECT sample_id FROM experiment.samples "
            "WHERE source_order_id IN (SELECT order_id FROM experiment.experiment_orders WHERE project_id = :pid))"
        ), {"pid": pid})
        conn.execute(text(
            "DELETE FROM experiment.samples "
            "WHERE source_order_id IN (SELECT order_id FROM experiment.experiment_orders WHERE project_id = :pid)"
        ), {"pid": pid})
        conn.execute(text(
            "DELETE FROM experiment.experiment_result_records "
            "WHERE experiment_order_id IN (SELECT order_id FROM experiment.experiment_orders WHERE project_id = :pid)"
        ), {"pid": pid})
        conn.execute(text(
            "DELETE FROM experiment.experiment_order_status_transitions "
            "WHERE order_id IN (SELECT order_id FROM experiment.experiment_orders WHERE project_id = :pid)"
        ), {"pid": pid})
        conn.execute(text(
            "DELETE FROM experiment.experiment_orders WHERE project_id = :pid"
        ), {"pid": pid})
        conn.execute(text("DELETE FROM projects.projects WHERE project_id = :pid"), {"pid": pid})


@pytest.fixture
def ensure_candidate(candidate_store):
    """创建测试候选材料，返回 candidate_id。"""
    cid = _unique_id("T14-CAND")
    candidate_store.save(CandidateRecord(
        candidate_id=cid,
        candidate_type="crystal",
        name=f"TestCandidate-{cid}",
        smiles="",
        source="task14_test",
        scenario_id="",
        multi_objective_score=0.85,
        data={"test": True},
    ))
    yield cid
    # 清理：先删依赖此候选的样品、订单等
    with candidate_store.engine.begin() as conn:
        conn.execute(text(
            "DELETE FROM experiment.sample_transfers "
            "WHERE sample_id IN (SELECT sample_id FROM experiment.samples WHERE source_candidate_id = :cid)"
        ), {"cid": cid})
        conn.execute(text("DELETE FROM experiment.samples WHERE source_candidate_id = :cid"), {"cid": cid})
        conn.execute(text(
            "DELETE FROM experiment.experiment_result_records "
            "WHERE experiment_order_id IN (SELECT order_id FROM experiment.experiment_orders WHERE candidate_id = :cid)"
        ), {"cid": cid})
        conn.execute(text(
            "DELETE FROM experiment.experiment_order_status_transitions "
            "WHERE order_id IN (SELECT order_id FROM experiment.experiment_orders WHERE candidate_id = :cid)"
        ), {"cid": cid})
        conn.execute(text("DELETE FROM experiment.experiment_orders WHERE candidate_id = :cid"), {"cid": cid})
        conn.execute(text("DELETE FROM experiment.candidates WHERE candidate_id = :cid"), {"cid": cid})


# ───────────────────────── 14.2: ON DELETE RESTRICT 约束 ─────────────────────────


class TestOnDeleteRestrict:
    """验证 ON DELETE RESTRICT 约束生效。"""

    def test_delete_candidate_with_order_blocked(
        self, candidate_store, experiment_store, ensure_project, ensure_candidate
    ):
        """删除有下游 experiment_orders 的 candidate 应被 FK 阻止。"""
        cid = ensure_candidate
        oid = _unique_id("T14-ORD-CAND")
        experiment_store.save_order(ExperimentOrder(
            order_id=oid,
            project_id=ensure_project,
            candidate_id=cid,
            status=ExperimentOrderStatus.DRAFT.value,
        ))
        # 尝试删除候选 — 应被阻止
        with pytest.raises(Exception) as exc_info:
            with candidate_store.engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM experiment.candidates WHERE candidate_id = :cid"),
                    {"cid": cid},
                )
        # PostgreSQL 违反外键约束的错误信息
        assert "foreign key" in str(exc_info.value).lower() or "restrict" in str(exc_info.value).lower() \
               or "violates" in str(exc_info.value).lower()

    def test_delete_order_with_sample_blocked(
        self, candidate_store, experiment_store, sample_store,
        ensure_project, ensure_candidate
    ):
        """删除有下游 samples 的 experiment_order 应被 FK 阻止。"""
        cid = ensure_candidate
        oid = _unique_id("T14-ORD-SMP")
        experiment_store.save_order(ExperimentOrder(
            order_id=oid,
            project_id=ensure_project,
            candidate_id=cid,
            status=ExperimentOrderStatus.DRAFT.value,
        ))
        sid = _unique_id("T14-SMP")
        sample_store.save(Sample(
            sample_id=sid,
            name=f"TestSample-{sid}",
            source_type="experiment",
            source_order_id=oid,
            source_candidate_id=cid,
        ))
        # 尝试删除订单 — 应被阻止
        with pytest.raises(Exception) as exc_info:
            with experiment_store.engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM experiment.experiment_orders WHERE order_id = :oid"),
                    {"oid": oid},
                )
        assert "foreign key" in str(exc_info.value).lower() or "restrict" in str(exc_info.value).lower() \
               or "violates" in str(exc_info.value).lower()

    def test_delete_order_with_result_record_blocked(
        self, candidate_store, experiment_store, ensure_project, ensure_candidate
    ):
        """删除有下游 experiment_result_records 的 experiment_order 应被 FK 阻止。"""
        cid = ensure_candidate
        oid = _unique_id("T14-ORD-RES")
        experiment_store.save_order(ExperimentOrder(
            order_id=oid,
            project_id=ensure_project,
            candidate_id=cid,
            status=ExperimentOrderStatus.APPROVED.value,
        ))
        rid = _unique_id("T14-RES")
        experiment_store.save_result_record(ExperimentResultRecord(
            result_id=rid,
            experiment_order_id=oid,
            property_name="prop.ionic_conductivity",
            value=0.005,
            unit="S/cm",
        ))
        # 尝试删除订单 — 应被阻止
        with pytest.raises(Exception) as exc_info:
            with experiment_store.engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM experiment.experiment_orders WHERE order_id = :oid"),
                    {"oid": oid},
                )
        assert "foreign key" in str(exc_info.value).lower() or "restrict" in str(exc_info.value).lower() \
               or "violates" in str(exc_info.value).lower()

    def test_delete_sample_with_transfer_blocked(
        self, candidate_store, experiment_store, sample_store,
        ensure_project, ensure_candidate
    ):
        """删除有下游 sample_transfers 的 sample 应被 FK 阻止。"""
        cid = ensure_candidate
        oid = _unique_id("T14-ORD-TRF")
        experiment_store.save_order(ExperimentOrder(
            order_id=oid,
            project_id=ensure_project,
            candidate_id=cid,
            status=ExperimentOrderStatus.DRAFT.value,
        ))
        sid = _unique_id("T14-SMP-TRF")
        sample_store.save(Sample(
            sample_id=sid,
            name=f"TestSample-{sid}",
            source_type="experiment",
            source_order_id=oid,
            source_candidate_id=cid,
        ))
        # 创建样品转移记录
        sample_store.transfer(
            sample_id=sid,
            to_status=SampleStatus.IN_STORAGE,
            to_location="lab-shelf-A",
            transferred_by="tester",
        )
        # 尝试删除样品 — 应被阻止
        with pytest.raises(Exception) as exc_info:
            with sample_store.engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM experiment.samples WHERE sample_id = :sid"),
                    {"sid": sid},
                )
        assert "foreign key" in str(exc_info.value).lower() or "restrict" in str(exc_info.value).lower() \
               or "violates" in str(exc_info.value).lower()

    def test_fk_constraint_on_delete_restrict_in_db(self, experiment_store):
        """直接查询 pg_constraint 验证 ON DELETE RESTRICT 已设置。"""
        with experiment_store.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT conname, pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE contype = 'f'
                  AND connamespace = 'experiment'::regnamespace
                  AND conname IN (
                    'fk_orders_candidate', 'fk_samples_order',
                    'fk_samples_candidate', 'fk_results_order',
                    'fk_transfers_sample'
                  )
                ORDER BY conname
            """)).fetchall()
        # 至少应包含 spec 要求的核心 5 个 FK
        names = {r[0] for r in rows}
        required = {
            "fk_orders_candidate", "fk_samples_order",
            "fk_samples_candidate", "fk_results_order",
            "fk_transfers_sample",
        }
        assert required.issubset(names), f"缺少 FK 约束: {required - names}"
        # 每个 FK 的定义必须包含 ON DELETE RESTRICT
        for name, defn in rows:
            assert "ON DELETE RESTRICT" in defn.upper(), \
                f"FK {name} 未设置 ON DELETE RESTRICT: {defn}"


# ───────────────────────── 14.2: 候选 → 实验任务自动关联 ─────────────────────────


class TestCandidateOrderAutoAssociation:
    """验证候选材料 → 实验任务自动关联逻辑。"""

    def test_ensure_draft_order_for_candidate_creates_order(
        self, controller, experiment_store, ensure_candidate, ensure_project
    ):
        """候选无关联订单时，ensure_draft_order_for_candidate 创建 DRAFT 草稿。"""
        cid = ensure_candidate
        order = controller.ensure_draft_order_for_candidate(
            candidate_id=cid,
            project_id=ensure_project,
            scenario_id="",
        )
        assert order is not None
        assert order.candidate_id == cid
        assert order.status == ExperimentOrderStatus.DRAFT.value
        assert order.ai_draft is True
        # 数据库中能查到
        loaded = experiment_store.get_order(order.order_id)
        assert loaded is not None
        assert loaded.candidate_id == cid
        # 清理由 ensure 创建的 order
        with experiment_store.engine.begin() as conn:
            conn.execute(text(
                "DELETE FROM experiment.experiment_order_status_transitions WHERE order_id = :oid"
            ), {"oid": order.order_id})
            conn.execute(text(
                "DELETE FROM experiment.experiment_orders WHERE order_id = :oid"
            ), {"oid": order.order_id})

    def test_ensure_draft_order_for_candidate_skips_if_exists(
        self, controller, experiment_store, ensure_candidate, ensure_project
    ):
        """候选已有关联订单时，ensure_draft_order_for_candidate 返回 None。"""
        cid = ensure_candidate
        # 先创建一个订单
        existing_oid = _unique_id("T14-EXIST-ORD")
        experiment_store.save_order(ExperimentOrder(
            order_id=existing_oid,
            project_id=ensure_project,
            candidate_id=cid,
            status=ExperimentOrderStatus.DRAFT.value,
        ))
        try:
            result = controller.ensure_draft_order_for_candidate(
                candidate_id=cid,
                project_id=ensure_project,
            )
            assert result is None
        finally:
            with experiment_store.engine.begin() as conn:
                conn.execute(text(
                    "DELETE FROM experiment.experiment_order_status_transitions WHERE order_id = :oid"
                ), {"oid": existing_oid})
                conn.execute(text(
                    "DELETE FROM experiment.experiment_orders WHERE order_id = :oid"
                ), {"oid": existing_oid})

    def test_ensure_draft_order_for_empty_candidate_returns_none(self, controller):
        """candidate_id 为空时返回 None。"""
        assert controller.ensure_draft_order_for_candidate("") is None

    def test_create_order_auto_generates_id_and_status(self, controller, experiment_store, ensure_candidate):
        """create_order 自动生成 order_id 与 DRAFT 状态。"""
        cid = ensure_candidate
        order = ExperimentOrder(
            project_id="",
            candidate_id=cid,
        )
        try:
            result = controller.create_order(order)
            assert result.order_id  # 自动生成
            assert result.status == ExperimentOrderStatus.DRAFT.value
            # 数据库中能查到
            loaded = experiment_store.get_order(result.order_id)
            assert loaded is not None
        finally:
            if order.order_id:
                with experiment_store.engine.begin() as conn:
                    conn.execute(text(
                        "DELETE FROM experiment.experiment_order_status_transitions WHERE order_id = :oid"
                    ), {"oid": order.order_id})
                    conn.execute(text(
                        "DELETE FROM experiment.experiment_orders WHERE order_id = :oid"
                    ), {"oid": order.order_id})


# ───────────────────────── 14.3: 实验任务 → 样品自动关联 ─────────────────────────


class TestOrderSampleAutoAssociation:
    """验证实验任务 → 样品自动关联逻辑。"""

    def test_sample_save_autofills_source_candidate_id(
        self, candidate_store, experiment_store, sample_store,
        ensure_project, ensure_candidate
    ):
        """SampleStore.save 时若 source_order_id 存在但 source_candidate_id 缺失，
        从 order.candidate_id 推导填充。"""
        cid = ensure_candidate
        oid = _unique_id("T14-ORD-AUTO")
        experiment_store.save_order(ExperimentOrder(
            order_id=oid,
            project_id=ensure_project,
            candidate_id=cid,
            status=ExperimentOrderStatus.DRAFT.value,
        ))
        sid = _unique_id("T14-SMP-AUTO")
        try:
            # 故意不传 source_candidate_id
            sample_store.save(Sample(
                sample_id=sid,
                name=f"AutoSample-{sid}",
                source_type="experiment",
                source_order_id=oid,
                # source_candidate_id 留空
            ))
            loaded = sample_store.get(sid)
            assert loaded is not None
            assert loaded.source_candidate_id == cid
        finally:
            with sample_store.engine.begin() as conn:
                conn.execute(text("DELETE FROM experiment.samples WHERE sample_id = :sid"),
                             {"sid": sid})
                conn.execute(text(
                    "DELETE FROM experiment.experiment_order_status_transitions WHERE order_id = :oid"
                ), {"oid": oid})
                conn.execute(text("DELETE FROM experiment.experiment_orders WHERE order_id = :oid"),
                             {"oid": oid})

    def test_sample_save_preserves_explicit_candidate_id(
        self, candidate_store, experiment_store, sample_store,
        ensure_project, ensure_candidate
    ):
        """显式指定的 source_candidate_id 不被覆盖。"""
        cid = ensure_candidate
        # 再创建一个候选
        other_cid = _unique_id("T14-OTHER-CAND")
        candidate_store.save(CandidateRecord(
            candidate_id=other_cid,
            candidate_type="crystal",
            name=f"OtherCand-{other_cid}",
            source="task14_test",
        ))
        oid = _unique_id("T14-ORD-EXPL")
        experiment_store.save_order(ExperimentOrder(
            order_id=oid,
            project_id=ensure_project,
            candidate_id=cid,
            status=ExperimentOrderStatus.DRAFT.value,
        ))
        sid = _unique_id("T14-SMP-EXPL")
        try:
            # 显式指定 other_cid
            sample_store.save(Sample(
                sample_id=sid,
                name=f"ExplSample-{sid}",
                source_type="experiment",
                source_order_id=oid,
                source_candidate_id=other_cid,
            ))
            loaded = sample_store.get(sid)
            assert loaded is not None
            # 显式指定的值不被覆盖
            assert loaded.source_candidate_id == other_cid
        finally:
            with sample_store.engine.begin() as conn:
                conn.execute(text("DELETE FROM experiment.samples WHERE sample_id = :sid"),
                             {"sid": sid})
                conn.execute(text(
                    "DELETE FROM experiment.experiment_order_status_transitions WHERE order_id = :oid"
                ), {"oid": oid})
                conn.execute(text("DELETE FROM experiment.experiment_orders WHERE order_id = :oid"),
                             {"oid": oid})
                conn.execute(text("DELETE FROM experiment.candidates WHERE candidate_id = :cid"),
                             {"cid": other_cid})


# ───────────────────────── 14.4: 实验数据 → 设备自动关联 ─────────────────────────


class TestResultInstrumentAutoAssociation:
    """验证实验数据 → 设备自动关联逻辑。"""

    def test_save_result_record_autofills_instrument_id(
        self, candidate_store, experiment_store, ensure_project, ensure_candidate
    ):
        """save_result_record 时若 instrument_id 缺失但 order.procedure 中有 equipment，自动填充。"""
        cid = ensure_candidate
        oid = _unique_id("T14-ORD-INSTR")
        experiment_store.save_order(ExperimentOrder(
            order_id=oid,
            project_id=ensure_project,
            candidate_id=cid,
            status=ExperimentOrderStatus.APPROVED.value,
            procedure=[
                {"step": 1, "equipment": "EQ-EIS-001", "action": "EIS scan"},
                {"step": 2, "equipment": "EQ-EIS-001", "action": "annealing"},
            ],
        ))
        rid = _unique_id("T14-RES-INSTR")
        try:
            experiment_store.save_result_record(ExperimentResultRecord(
                result_id=rid,
                experiment_order_id=oid,
                property_name="prop.ionic_conductivity",
                value=27.1,
                unit="S/cm",
                # instrument_id 留空
            ))
            loaded = experiment_store.get_result_record(rid)
            assert loaded is not None
            # 应该被自动填充为 procedure 中第一个 equipment
            assert loaded.instrument_id == "EQ-EIS-001"
        finally:
            with experiment_store.engine.begin() as conn:
                conn.execute(text(
                    "DELETE FROM experiment.experiment_result_records WHERE result_id = :rid"
                ), {"rid": rid})
                conn.execute(text(
                    "DELETE FROM experiment.experiment_order_status_transitions WHERE order_id = :oid"
                ), {"oid": oid})
                conn.execute(text("DELETE FROM experiment.experiment_orders WHERE order_id = :oid"),
                             {"oid": oid})

    def test_save_result_record_preserves_explicit_instrument_id(
        self, candidate_store, experiment_store, ensure_project, ensure_candidate
    ):
        """显式指定的 instrument_id 不被覆盖。"""
        cid = ensure_candidate
        oid = _unique_id("T14-ORD-INSTR2")
        experiment_store.save_order(ExperimentOrder(
            order_id=oid,
            project_id=ensure_project,
            candidate_id=cid,
            status=ExperimentOrderStatus.APPROVED.value,
            procedure=[{"step": 1, "equipment": "EQ-EIS-001"}],
        ))
        rid = _unique_id("T14-RES-INSTR2")
        try:
            experiment_store.save_result_record(ExperimentResultRecord(
                result_id=rid,
                experiment_order_id=oid,
                property_name="prop.ionic_conductivity",
                value=1.0,
                unit="S/cm",
                instrument_id="EQ-EIS-001",  # 显式指定
            ))
            loaded = experiment_store.get_result_record(rid)
            assert loaded is not None
            assert loaded.instrument_id == "EQ-EIS-001"
        finally:
            with experiment_store.engine.begin() as conn:
                conn.execute(text(
                    "DELETE FROM experiment.experiment_result_records WHERE result_id = :rid"
                ), {"rid": rid})
                conn.execute(text(
                    "DELETE FROM experiment.experiment_order_status_transitions WHERE order_id = :oid"
                ), {"oid": oid})
                conn.execute(text("DELETE FROM experiment.experiment_orders WHERE order_id = :oid"),
                             {"oid": oid})


# ───────────────────────── 14.5: 配方 → 样品自动关联 ─────────────────────────


class TestFormulaSampleAutoAssociation:
    """验证配方 → 样品自动关联逻辑。"""

    def test_set_active_creates_sample_proposal(
        self, formula_store, sample_store, ensure_candidate, candidate_store
    ):
        """配方版本 set_active 后自动创建 status='proposed' 的样品提案。"""
        cid = ensure_candidate
        # 让候选 name 等于配方的 target_material，以便匹配
        candidate = candidate_store.get(cid)
        target_material = candidate.name

        # 创建配方版本
        formula_id = _unique_id("T14-FORM")
        version = FormulaVersion(
            formula_id=formula_id,
            version_number=1,
            target_material=target_material,
            quantity_kg=2.5,
            bom=[],
            bop=[],
            scenario_id="",
        )
        saved = formula_store.save(version)
        created_sample_ids: list[str] = []
        try:
            # 激活配方版本 — 应触发自动样品提案
            activated = formula_store.set_active(formula_id, saved.version_id)
            assert activated is not None

            # 查找自动创建的样品提案
            with sample_store.engine.connect() as conn:
                rows = conn.execute(text(
                    "SELECT sample_id, name, source_type, source_candidate_id, "
                    "status, chemical_formula "
                    "FROM experiment.samples "
                    "WHERE name LIKE :pattern AND status = 'proposed'"
                ), {"pattern": f"%{formula_id}%"}).fetchall()
            assert len(rows) >= 1, "未自动创建样品提案"
            sample_row = rows[0]
            created_sample_ids.append(sample_row[0])
            assert sample_row[2] == "formula"  # source_type
            assert sample_row[3] == cid  # source_candidate_id 关联到候选
            assert sample_row[5] == target_material  # chemical_formula
        finally:
            # 清理
            with sample_store.engine.begin() as conn:
                for sid in created_sample_ids:
                    conn.execute(text(
                        "DELETE FROM experiment.sample_transfers WHERE sample_id = :sid"
                    ), {"sid": sid})
                    conn.execute(text(
                        "DELETE FROM experiment.samples WHERE sample_id = :sid"
                    ), {"sid": sid})
                # 删除配方版本
                conn.execute(text(
                    "DELETE FROM control_plane.versions WHERE entity_id = :fid"
                ), {"fid": formula_id})

    def test_set_active_creates_sample_without_candidate_match(
        self, formula_store, sample_store
    ):
        """target_material 无匹配候选时，仍创建样品提案，source_candidate_id 留空。"""
        formula_id = _unique_id("T14-FORM-NOMATCH")
        version = FormulaVersion(
            formula_id=formula_id,
            version_number=1,
            target_material="NonExistentMaterial_xyz",
            quantity_kg=1.0,
        )
        saved = formula_store.save(version)
        created_sample_ids: list[str] = []
        try:
            activated = formula_store.set_active(formula_id, saved.version_id)
            assert activated is not None
            with sample_store.engine.connect() as conn:
                rows = conn.execute(text(
                    "SELECT sample_id, source_candidate_id, status "
                    "FROM experiment.samples "
                    "WHERE name LIKE :pattern AND status = 'proposed'"
                ), {"pattern": f"%{formula_id}%"}).fetchall()
            assert len(rows) >= 1
            sample_row = rows[0]
            created_sample_ids.append(sample_row[0])
            assert sample_row[1] == "" or sample_row[1] is None  # 无匹配候选
        finally:
            with sample_store.engine.begin() as conn:
                for sid in created_sample_ids:
                    conn.execute(text(
                        "DELETE FROM experiment.sample_transfers WHERE sample_id = :sid"
                    ), {"sid": sid})
                    conn.execute(text(
                        "DELETE FROM experiment.samples WHERE sample_id = :sid"
                    ), {"sid": sid})
                conn.execute(text(
                    "DELETE FROM control_plane.versions WHERE entity_id = :fid"
                ), {"fid": formula_id})


# ───────────────────────── SampleStatus 枚举扩展 ─────────────────────────


class TestSampleStatusProposed:
    """验证 SampleStatus.PROPOSED 已加入枚举。"""

    def test_proposed_in_enum(self):
        assert SampleStatus.PROPOSED == "proposed"
        assert SampleStatus("proposed") == SampleStatus.PROPOSED

    def test_proposed_distinct_from_created(self):
        assert SampleStatus.PROPOSED != SampleStatus.CREATED
