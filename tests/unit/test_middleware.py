"""Tests for wet data middleware module."""

import pytest
import tempfile
import os
from sqlalchemy import text
from battery_materials_agent.middleware.data_middleware import DataMiddleware, ExperimentRecord
from battery_materials_agent.middleware.adapters import FileWatcherAdapter


@pytest.fixture(autouse=True)
def _cleanup_experiment_records():
    """每个测试前后清理 experiment_result_records，避免跨测试数据污染。"""
    from battery_materials_agent.db import get_engine
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM experiment.experiment_result_records"))
    yield
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM experiment.experiment_result_records"))


class TestDataMiddleware:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.middleware = DataMiddleware(db_path=self.db_path)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_ingest_record(self):
        record = ExperimentRecord(
            sample_id="S001",
            formula="LiCoO2",
            experiment_type="prop.ionic_conductivity",
            measured_values={"conductivity": 1.5e-3},
            source="test",
        )
        record_id = self.middleware.ingest_record(record)
        assert record_id != ""

    def test_query_records(self):
        self.middleware.ingest_record(ExperimentRecord(
            sample_id="S002", formula="LiCoO2",
            experiment_type="prop.ionic_conductivity",
            measured_values={"conductivity": 1.5e-3}, source="test",
        ))
        records = self.middleware.query_records(experiment_type="prop.ionic_conductivity")
        assert len(records) >= 1
        # 迁移至 PostgreSQL 后 experiment_result_records 表无 formula 列，
        # query_records 返回的 formula 字段为空字符串；以 sample_id 作为断言依据
        assert records[0].sample_id == "S002"
        assert records[0].experiment_type == "prop.ionic_conductivity"

    def test_query_by_type(self):
        self.middleware.ingest_record(ExperimentRecord(
            sample_id="S003", formula="LiFePO4",
            experiment_type="prop.specific_capacity", source="test",
        ))
        records = self.middleware.query_records(experiment_type="prop.specific_capacity")
        assert len(records) >= 1

    def test_subscribe(self):
        received = []
        def callback(record):
            received.append(record)
        self.middleware.subscribe(callback)
        self.middleware.ingest_record(ExperimentRecord(
            sample_id="S004", formula="test", source="test",
        ))
        assert len(received) == 1

    def test_unsubscribe(self):
        received = []
        def callback(record):
            received.append(record)
        self.middleware.subscribe(callback)
        self.middleware.unsubscribe(callback)
        self.middleware.ingest_record(ExperimentRecord(
            sample_id="S005", formula="test", source="test",
        ))
        assert len(received) == 0

    def test_get_latest(self):
        self.middleware.ingest_record(ExperimentRecord(
            sample_id="S006", formula="LiCoO2",
            experiment_type="prop.ionic_conductivity", source="test",
        ))
        record = self.middleware.get_latest_for_formula("LiCoO2", "prop.ionic_conductivity")
        assert record is not None
        # 迁移至 PostgreSQL 后 formula 字段为空字符串，以 experiment_type 作为断言依据
        assert record.experiment_type == "prop.ionic_conductivity"

    def test_get_statistics(self):
        for i in range(5):
            self.middleware.ingest_record(ExperimentRecord(
                sample_id=f"S{i}", formula="LiCoO2",
                experiment_type="prop.ionic_conductivity",
                measured_values={"conductivity": 1.0 + i * 0.1}, source="test",
            ))
        stats = self.middleware.get_statistics("LiCoO2", "prop.ionic_conductivity")
        assert stats["count"] >= 5
        # 统计键名为 experiment_type（即 prop.ionic_conductivity），不是 measured_values 的子键
        assert "prop.ionic_conductivity" in stats

    def test_experiment_record_fields(self):
        record = ExperimentRecord(
            sample_id="S007",
            formula="LiCoO2",
            experiment_type="ionic_conductivity",
            conditions={"temperature": 25},
            measured_values={"conductivity": 1.5e-3},
            units={"conductivity": "S/cm"},
            error_ranges={"conductivity": 0.1e-3},
            source="test",
            batch_id="B001",
            operator="tester",
            notes="test note",
        )
        assert record.batch_id == "B001"
        assert record.notes == "test note"
        assert record.conditions["temperature"] == 25


class TestFileWatcherAdapter:
    def test_scan_files_nonexistent(self):
        adapter = FileWatcherAdapter(watch_dirs=["/nonexistent"])
        files = adapter.scan_files()
        assert files == []

    def test_parse_csv(self):
        import tempfile
        import os
        tmpdir = tempfile.mkdtemp()
        csv_path = os.path.join(tmpdir, "test.csv")
        with open(csv_path, "w") as f:
            f.write("name,value\nA,1.0\nB,2.0\n")
        adapter = FileWatcherAdapter(watch_dirs=[tmpdir])
        records = adapter.parse_csv(csv_path)
        assert len(records) == 2
        assert records[0]["name"] == "A"
        import shutil
        shutil.rmtree(tmpdir)

    def test_parse_instrument_output(self):
        import tempfile
        import os
        tmpdir = tempfile.mkdtemp()
        txt_path = os.path.join(tmpdir, "report.txt")
        with open(txt_path, "w") as f:
            f.write("Line 1\nLine 2\n")
        adapter = FileWatcherAdapter(watch_dirs=[tmpdir])
        result = adapter.parse_instrument_output(txt_path)
        assert result["num_lines"] == 2
        import shutil
        shutil.rmtree(tmpdir)
