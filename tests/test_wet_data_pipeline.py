"""测试湿数据管道：录入 -> QC -> 确认。"""

import pytest
from sqlalchemy import text
from battery_materials_agent.experiment.experiment_controller import (
    ExperimentResultRecord,
    ExperimentDataStore,
)
from battery_materials_agent.middleware.wet_data.quality import QCEngine, QCResult
from battery_materials_agent.middleware.wet_data.adapters import (
    ManualEntryAdapter,
    CSVAdapter,
)
from battery_materials_agent.middleware.wet_data.normalization import (
    FieldMapper,
    UnitConverter,
)


@pytest.fixture
def store(tmp_path):
    """临时数据库。"""
    return ExperimentDataStore(str(tmp_path / "test_experiments.db"))


@pytest.fixture(autouse=True)
def _cleanup_experiment_data():
    """每个测试前后清理 experiment_result_records 与 experiment_orders，避免 FK 与跨测试污染。"""
    from battery_materials_agent.db import get_engine
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM experiment.experiment_result_records"))
        conn.execute(text("DELETE FROM experiment.experiment_orders WHERE order_id LIKE 'EXP_%'"))
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM experiment.experiment_result_records"))
        conn.execute(text("DELETE FROM experiment.experiment_orders WHERE order_id LIKE 'EXP_%'"))


@pytest.fixture
def qc_engine():
    return QCEngine()


def test_manual_entry_adapter():
    """人工录入适配器标准化数据。"""
    adapter = ManualEntryAdapter()
    record = adapter.normalize({
        "experiment_order_id": "EXP_001",
        "sample_id": "SMP_001",
        "property_name": "ionic_conductivity",
        "value": "0.005",
        "unit": "S/cm",
        "uploaded_by": "test_user",
    })
    assert record.experiment_order_id == "EXP_001"
    assert record.value == 0.005
    assert record.source_type == "MANUAL_ENTRY"
    assert record.qc_status == "PENDING"


def test_qc_valid_data(qc_engine):
    """完整数据 QC 检查通过。"""
    record = ExperimentResultRecord(
        result_id="RES_001",
        sample_id="SMP_001",
        property_name="ionic_conductivity",
        value=0.005,
        unit="S/cm",
    )
    result = qc_engine.check(record)
    assert result.qc_status == "VALID"
    assert result.learning_eligible is True


def test_qc_missing_field(qc_engine):
    """缺失必填字段 QC 失败。"""
    record = ExperimentResultRecord(
        result_id="RES_002",
        sample_id="",
        property_name="ionic_conductivity",
        value=0.005,
        unit="S/cm",
    )
    result = qc_engine.check(record)
    assert result.qc_status == "INVALID"
    assert any("样品" in issue for issue in result.issues)


def test_qc_out_of_range(qc_engine):
    """数值超出合理范围 QC 失败。"""
    record = ExperimentResultRecord(
        result_id="RES_003",
        sample_id="SMP_001",
        property_name="ionic_conductivity",
        value=999999.0,
        unit="S/cm",
    )
    result = qc_engine.check(record)
    assert result.qc_status == "INVALID"
    assert any("超出" in issue for issue in result.issues)


def test_field_mapper():
    """字段映射器中英文转换。"""
    mapper = FieldMapper()
    assert mapper.map("实验ID") == "experiment_order_id"
    assert mapper.map("样品ID") == "sample_id"


def test_unit_converter():
    """单位换算。"""
    converter = UnitConverter()
    value, unit = converter.convert(5.0, "mS/cm", "S/cm")
    assert abs(value - 0.005) < 1e-6
    assert unit == "S/cm"


def test_full_pipeline(store, qc_engine):
    """完整管道：录入 -> QC -> 确认。"""
    # 0. 先创建 experiment_order，满足 experiment_result_orders.order_id FK 约束
    from battery_materials_agent.db import get_engine
    with get_engine().begin() as conn:
        conn.execute(text(
            "INSERT INTO experiment.experiment_orders (order_id, status) "
            "VALUES (:order_id, 'approved') ON CONFLICT (order_id) DO NOTHING"
        ), {"order_id": "EXP_001"})

    # 1. 录入
    record = ExperimentResultRecord(
        result_id="RES_FULL_001",
        experiment_order_id="EXP_001",
        sample_id="SMP_001",
        property_name="ionic_conductivity",
        value=0.005,
        unit="S/cm",
        uploaded_by="test_user",
    )
    store.save_result_record(record)

    # 2. QC 检查
    qc_result = qc_engine.check(record)
    assert qc_result.qc_status == "VALID"

    store.update_result_qc(
        record.result_id,
        qc_result.qc_status,
        qc_result.issues,
        reviewed_by="qc_user",
        learning_eligible=qc_result.learning_eligible,
    )

    # 3. 确认
    updated = store.get_result_record(record.result_id)
    assert updated.qc_status == "VALID"
    assert updated.learning_eligible is True
    assert updated.reviewed_by == "qc_user"
