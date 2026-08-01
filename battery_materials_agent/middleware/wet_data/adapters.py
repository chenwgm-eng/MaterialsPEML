"""湿数据适配器 - 支持人工录入、CSV、Excel、API 推送。"""

from __future__ import annotations
from typing import Any
import csv
import logging
import uuid
from datetime import datetime, timezone

from ...experiment.experiment_controller import ExperimentResultRecord

logger = logging.getLogger(__name__)


class ManualEntryAdapter:
    """人工表单数据标准化。"""

    def normalize(self, raw_data: dict) -> ExperimentResultRecord:
        return ExperimentResultRecord(
            result_id=f"RES_{uuid.uuid4().hex[:8]}",
            experiment_order_id=raw_data.get("experiment_order_id", ""),
            sample_id=raw_data.get("sample_id", ""),
            sample_batch_id=raw_data.get("sample_batch_id", ""),
            source_type="MANUAL_ENTRY",
            uploaded_by=raw_data.get("uploaded_by", ""),
            property_name=raw_data.get("property_name", ""),
            value=float(raw_data.get("value", 0)),
            unit=raw_data.get("unit", ""),
            test_method=raw_data.get("test_method", ""),
            test_conditions=raw_data.get("test_conditions", {}),
            instrument_id=raw_data.get("instrument_id", ""),
            raw_file_uri=raw_data.get("raw_file_uri", ""),
            qc_status="PENDING",
        )


class CSVAdapter:
    """CSV 文件解析器。"""

    # 标准字段映射（CSV 列名 → 系统字段）
    FIELD_MAPPING = {
        "experiment_id": "experiment_order_id",
        "order_id": "experiment_order_id",
        "sample": "sample_id",
        "sample_id": "sample_id",
        "property": "property_name",
        "value": "value",
        "unit": "unit",
        "method": "test_method",
        "test_method": "test_method",
        "instrument": "instrument_id",
        "operator": "uploaded_by",
        "uploaded_by": "uploaded_by",
    }

    def parse_file(self, file_path: str) -> list[ExperimentResultRecord]:
        records = []
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                normalized = {}
                for key, value in row.items():
                    mapped_key = self.FIELD_MAPPING.get(key.strip().lower(), key.strip().lower())
                    normalized[mapped_key] = value.strip() if value else ""

                if not normalized.get("value"):
                    continue

                try:
                    value_float = float(normalized.get("value", 0))
                except ValueError:
                    continue

                record = ExperimentResultRecord(
                    result_id=f"RES_{uuid.uuid4().hex[:8]}",
                    experiment_order_id=normalized.get("experiment_order_id", ""),
                    sample_id=normalized.get("sample_id", ""),
                    sample_batch_id=normalized.get("sample_batch_id", ""),
                    source_type="CSV_IMPORT",
                    uploaded_by=normalized.get("uploaded_by", ""),
                    property_name=normalized.get("property_name", ""),
                    value=value_float,
                    unit=normalized.get("unit", ""),
                    test_method=normalized.get("test_method", ""),
                    test_conditions={k: v for k, v in normalized.items()
                                     if k not in self.FIELD_MAPPING.values() and v},
                    instrument_id=normalized.get("instrument_id", ""),
                    qc_status="PENDING",
                )
                records.append(record)

        logger.info("CSV 导入完成：%d 条记录", len(records))
        return records


class ExcelAdapter:
    """Excel 文件解析器。"""

    def parse_file(self, file_path: str) -> list[ExperimentResultRecord]:
        try:
            import openpyxl
        except ImportError:
            raise ImportError("openpyxl 未安装，无法解析 Excel 文件")

        wb = openpyxl.load_workbook(file_path, read_only=True)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []

        headers = [str(h).strip().lower() if h else "" for h in rows[0]]
        csv_adapter = CSVAdapter()

        records = []
        for row in rows[1:]:
            row_dict = {}
            for i, cell in enumerate(row):
                if i < len(headers) and headers[i]:
                    row_dict[headers[i]] = str(cell).strip() if cell is not None else ""
            normalized = {}
            for key, value in row_dict.items():
                mapped_key = csv_adapter.FIELD_MAPPING.get(key, key)
                normalized[mapped_key] = value

            if not normalized.get("value"):
                continue
            try:
                value_float = float(normalized.get("value", 0))
            except ValueError:
                continue

            record = ExperimentResultRecord(
                result_id=f"RES_{uuid.uuid4().hex[:8]}",
                experiment_order_id=normalized.get("experiment_order_id", ""),
                sample_id=normalized.get("sample_id", ""),
                sample_batch_id=normalized.get("sample_batch_id", ""),
                source_type="EXCEL_IMPORT",
                uploaded_by=normalized.get("uploaded_by", ""),
                property_name=normalized.get("property_name", ""),
                value=value_float,
                unit=normalized.get("unit", ""),
                test_method=normalized.get("test_method", ""),
                test_conditions={k: v for k, v in normalized.items()
                                 if k not in csv_adapter.FIELD_MAPPING.values() and v},
                instrument_id=normalized.get("instrument_id", ""),
                qc_status="PENDING",
            )
            records.append(record)

        wb.close()
        logger.info("Excel 导入完成：%d 条记录", len(records))
        return records
