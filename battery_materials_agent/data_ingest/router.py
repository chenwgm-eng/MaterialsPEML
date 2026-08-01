"""数据接入 API：字段字典 / 预览(自动映射+质量报告) / 幂等提交 / 导入历史。

解析在前端完成（xlsx），后端负责映射、校验、质量报告、幂等写入与审计。
APIRouter 不带 prefix，由 api.py 挂载时统一加 /api 前缀。
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..experiment.equipment_store import Equipment, EquipmentStore
from ..experiment.experiment_controller import (
    ExperimentDataStore,
    ExperimentResultRecord,
)
from ..experiment.sample_store import Sample, SampleStore
from ..industrialization.raw_material_db import MaterialSpec, RawMaterialDB
from ..projects import Project, ProjectStore
from .field_dict import ENTITY_TYPES, get_field_dict
from .mapping import auto_map
from .quality import check_quality, normalize_quantity, normalize_unit
from .store import IngestStore

router = APIRouter()

MAX_ROWS = 500

# 模块级单例（惰性初始化，避免 import 时触碰文件系统）
_ingest_store: IngestStore | None = None
_sample_store: SampleStore | None = None
_equipment_store: EquipmentStore | None = None
_raw_material_db: RawMaterialDB | None = None
_project_store: ProjectStore | None = None
_experiment_data_store: ExperimentDataStore | None = None


def _get_ingest_store() -> IngestStore:
    global _ingest_store
    if _ingest_store is None:
        _ingest_store = IngestStore()
    return _ingest_store


def _get_sample_store() -> SampleStore:
    global _sample_store
    if _sample_store is None:
        _sample_store = SampleStore()
    return _sample_store


def _get_equipment_store() -> EquipmentStore:
    global _equipment_store
    if _equipment_store is None:
        _equipment_store = EquipmentStore()
    return _equipment_store


def _get_raw_material_db() -> RawMaterialDB:
    global _raw_material_db
    if _raw_material_db is None:
        _raw_material_db = RawMaterialDB()
    return _raw_material_db


def _get_project_store() -> ProjectStore:
    global _project_store
    if _project_store is None:
        _project_store = ProjectStore()
    return _project_store


def _get_experiment_data_store() -> ExperimentDataStore:
    global _experiment_data_store
    if _experiment_data_store is None:
        _experiment_data_store = ExperimentDataStore()
    return _experiment_data_store


class PreviewRequest(BaseModel):
    entity_type: str
    rows: list[dict[str, Any]] = Field(default_factory=list)
    mapping: dict[str, dict] | None = None  # 前端手工调整后的映射，缺省用自动映射


class CommitRequest(BaseModel):
    entity_type: str
    rows: list[dict[str, Any]] = Field(default_factory=list)
    mapping: dict[str, dict] = Field(default_factory=dict)
    idempotency_key: str
    file_name: str = ""
    operator: str = ""


def _validate_entity(entity_type: str):
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的实体类型: {entity_type}")


def _validate_rows(rows: list[dict]):
    if not rows:
        raise HTTPException(status_code=400, detail="rows 不能为空")
    if len(rows) > MAX_ROWS:
        raise HTTPException(status_code=400, detail=f"单次最多导入 {MAX_ROWS} 行")


def _write_entity(entity_type: str, record: dict) -> str:
    """把 canonical 记录写入对应实体存储，返回业务主键。与库内已有数据比对去重。"""
    if entity_type == "sample":
        store = _get_sample_store()
        existing = store.get_by_code(record.get("sample_code") or "") if record.get("sample_code") else None
        quantity = record.get("quantity") or 0.0
        unit = normalize_unit(record.get("unit") or "") or "g"
        if unit and record.get("quantity") is not None:
            quantity, unit = normalize_quantity(quantity, unit)
        sample = Sample(
            sample_id=(existing.sample_id if existing else f"SMP_{uuid.uuid4().hex[:8]}"),
            name=record.get("name") or "",
            source_type=record.get("source_type") or "",
            batch_number=record.get("batch_number") or "",
            quantity=quantity,
            unit=unit,
            storage_location=record.get("storage_location") or "",
            storage_condition=record.get("storage_condition") or "",
            notes=record.get("notes") or "",
            sample_code=record.get("sample_code") or "",
            chemical_formula=record.get("chemical_formula") or "",
        )
        if existing:
            sample.created_at = existing.created_at
            sample.status = existing.status
        store.save(sample)
        return sample.sample_id

    if entity_type == "equipment":
        store = _get_equipment_store()
        equipment_id = record.get("equipment_id") or f"EQ-{uuid.uuid4().hex[:8].upper()}"
        existing = store.get(equipment_id)
        equipment = Equipment(
            equipment_id=equipment_id,
            name=record.get("name") or "",
            model=record.get("model") or "",
            category=record.get("category") or "",
            serial_number=record.get("serial_number") or "",
            location=record.get("location") or "",
            responsible_person=record.get("responsible_person") or "",
            purchase_date=record.get("purchase_date") or "",
            last_calibration=record.get("last_calibration") or "",
            next_calibration=record.get("next_calibration") or "",
            notes=record.get("notes") or "",
        )
        if existing:
            equipment.status = existing.status
        store.save(equipment)
        return equipment.equipment_id

    if entity_type == "raw_material":
        db = _get_raw_material_db()
        material_id = record.get("material_id") or f"MAT-{uuid.uuid4().hex[:8].upper()}"
        existing = db.get_spec(material_id)
        spec = MaterialSpec(
            material_id=material_id,
            name=record.get("name") or "",
            smiles=record.get("smiles") or "",
            category=record.get("category") or "",
            inventory_quantity=record.get("inventory_quantity") or record.get("inventory_kg") or 0.0,
            unit_cost=record.get("unit_cost") or record.get("cost_per_kg") or 0.0,
            supplier=record.get("supplier") or "",
            batch_number=record.get("batch_number") or "",
            expiry_date=record.get("expiry_date") or "",
            min_order_quantity=record.get("min_order_quantity") or 0.0,
        )
        if existing:
            spec.version = existing.version
            spec.data_source = existing.data_source
        db.upsert_spec(spec)
        return spec.material_id

    if entity_type == "project":
        store = _get_project_store()
        existing = store.get_by_name(record.get("name") or "")
        project = Project(
            project_id=(existing.project_id if existing else ""),
            name=record.get("name") or "",
            target_application=record.get("target_application") or "",
            current_stage=record.get("current_stage") or "立项",
            owner=record.get("owner") or "",
            department=record.get("department") or "",
            start_date=record.get("start_date") or "",
            end_date=record.get("end_date") or "",
            budget=record.get("budget") or 0.0,
            iteration_progress=int(record.get("iteration_progress") or 0),
            notes=record.get("notes") or "",
        )
        if existing:
            project.created_at = existing.created_at
            project.target_properties = existing.target_properties
            project.candidate_ids = existing.candidate_ids
            project.experiment_order_ids = existing.experiment_order_ids
            store.update(project)
        else:
            store.create(project)
        return project.project_id

    if entity_type == "experiment_result":
        # 统一通过 ExperimentDataStore.save_result_record 写入
        # experiment.experiment_result_records，避免双源存储。
        store = _get_experiment_data_store()
        result_id = record.get("result_id") or f"REC_{uuid.uuid4().hex[:12]}"

        # test_conditions 字段允许 dict 或 JSON 字符串
        raw_test_conditions = record.get("test_conditions") or {}
        if isinstance(raw_test_conditions, str):
            import json as _json
            try:
                raw_test_conditions = _json.loads(raw_test_conditions) or {}
            except (ValueError, TypeError):
                raw_test_conditions = {}

        # qc_issues 允许 list 或 JSON 字符串
        raw_qc_issues = record.get("qc_issues") or []
        if isinstance(raw_qc_issues, str):
            import json as _json
            try:
                raw_qc_issues = _json.loads(raw_qc_issues) or []
            except (ValueError, TypeError):
                raw_qc_issues = []

        # learning_eligible 字符串 "true"/"false" → bool
        raw_learning = record.get("learning_eligible")
        if isinstance(raw_learning, str):
            learning_eligible = raw_learning.strip().lower() in {"1", "true", "yes", "y"}
        else:
            learning_eligible = bool(raw_learning or False)

        # value 数值解析
        raw_value = record.get("value") or 0.0
        try:
            value_num = float(raw_value)
        except (TypeError, ValueError):
            value_num = 0.0

        result_record = ExperimentResultRecord(
            result_id=result_id,
            experiment_order_id=record.get("experiment_order_id") or "",
            sample_id=record.get("sample_id") or "",
            sample_batch_id=record.get("sample_batch_id") or "",
            source_type=record.get("source_type") or "MANUAL_ENTRY",
            source_system=record.get("source_system") or "",
            uploaded_by=record.get("uploaded_by") or "",
            uploaded_at=record.get("uploaded_at") or "",
            property_name=record.get("property_name") or "",
            value=value_num,
            unit=record.get("unit") or "",
            test_method=record.get("test_method") or "",
            test_conditions=raw_test_conditions,
            instrument_id=record.get("instrument_id") or "",
            raw_file_uri=record.get("raw_file_uri") or "",
            qc_status=record.get("qc_status") or "PENDING",
            qc_issues=raw_qc_issues,
            reviewed_by=record.get("reviewed_by") or "",
            reviewed_at=record.get("reviewed_at") or None,
            learning_eligible=learning_eligible,
            scenario_id=record.get("scenario_id") or "",
        )
        store.save_result_record(result_record)
        return result_id

    raise HTTPException(status_code=400, detail=f"不支持的实体类型: {entity_type}")


@router.get("/ingest/field-dict/{entity_type}")
async def get_entity_field_dict(entity_type: str):
    """返回字段字典，供前端映射 UI 使用。"""
    _validate_entity(entity_type)
    return {"entity_type": entity_type, "fields": get_field_dict(entity_type)}


@router.post("/ingest/preview")
async def preview_import(req: PreviewRequest):
    """自动映射 + 质量报告 + 前 20 行预览。"""
    _validate_entity(req.entity_type)
    _validate_rows(req.rows)
    if req.mapping:
        map_result = auto_map(req.rows, req.entity_type)
        # 保留前端手工调整（column 被改过的项以请求为准）
        for key, m in req.mapping.items():
            if key in map_result["mapping"]:
                auto_col = map_result["mapping"][key].get("column", "")
                req_col = (m or {}).get("column", "") or ""
                if req_col != auto_col:
                    map_result["mapping"][key] = {
                        "column": req_col,
                        "confidence": (m or {}).get("confidence", "manual") if req_col else "none",
                        "auto": False,
                    }
    else:
        map_result = auto_map(req.rows, req.entity_type)

    quality = check_quality(req.rows, map_result["mapping"], req.entity_type)
    quality.pop("records", None)  # 预览不返回全量转换记录，减小载荷

    rows_preview = []
    for rr in quality["rows"][:20]:
        rows_preview.append({
            "row_index": rr["row_index"],
            "status": rr["status"],
            "issues": rr["issues"],
            "data": req.rows[rr["row_index"]],
        })

    return {
        "mapping": map_result["mapping"],
        "unmapped_columns": map_result["unmapped_columns"],
        "auto_mapped_ratio": map_result["auto_mapped_ratio"],
        "quality": quality,
        "rows_preview": rows_preview,
    }


@router.post("/ingest/commit")
async def commit_import(req: CommitRequest):
    """校验 → 幂等创建批次 → 逐行写入目标存储 → 行级记录 → 审计。

    重复 idempotency_key 直接返回首次结果（duplicated=true），不重复写入。
    """
    _validate_entity(req.entity_type)
    _validate_rows(req.rows)
    if not req.idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency_key 不能为空")

    store = _get_ingest_store()
    imp = store.create_import(
        idempotency_key=req.idempotency_key,
        entity_type=req.entity_type,
        file_name=req.file_name,
        operator=req.operator,
        total_rows=len(req.rows),
    )
    if imp.get("duplicated"):
        rows = store.get_rows(imp["import_id"])
        errors = [
            {"row_index": r["row_index"], "error": r["error"]}
            for r in rows if r["status"] == "failed"
        ][:20]
        return {
            "import_id": imp["import_id"],
            "duplicated": True,
            "success_rows": imp["success_rows"],
            "failed_rows": imp["failed_rows"],
            "status": imp["status"],
            "errors": errors,
        }

    quality = check_quality(req.rows, req.mapping, req.entity_type)
    records = quality["records"]
    row_status = {rr["row_index"]: rr for rr in quality["rows"]}

    success_rows = 0
    failed_rows = 0
    errors: list[dict] = []
    pending_rows: list[dict] = []

    for idx, record in enumerate(records):
        rr = row_status.get(idx, {"status": "ok", "issues": []})
        if rr["status"] == "error":
            failed_rows += 1
            err_msg = "；".join(rr["issues"])
            pending_rows.append({
                "import_id": imp["import_id"], "row_index": idx,
                "status": "failed", "error": err_msg, "payload": record,
            })
            if len(errors) < 20:
                errors.append({"row_index": idx, "error": err_msg})
            continue
        try:
            biz_id = _write_entity(req.entity_type, record)
            success_rows += 1
            pending_rows.append({
                "import_id": imp["import_id"], "row_index": idx,
                "status": "success",
                "error": "" if rr["status"] == "ok" else "；".join(rr["issues"]),
                "payload": {**record, "_biz_id": biz_id},
            })
        except Exception as exc:  # noqa: BLE001 - 单行失败不阻断整批，记录后重试下一行
            failed_rows += 1
            err_msg = f"写入失败: {exc}"
            pending_rows.append({
                "import_id": imp["import_id"], "row_index": idx,
                "status": "failed", "error": err_msg, "payload": record,
            })
            if len(errors) < 20:
                errors.append({"row_index": idx, "error": err_msg})

    # 批量写入行级审计，减少连接开销
    store.save_rows(pending_rows)
    store.finish_import(imp["import_id"], success_rows, failed_rows, quality["summary"])

    return {
        "import_id": imp["import_id"],
        "duplicated": False,
        "success_rows": success_rows,
        "failed_rows": failed_rows,
        "status": "success" if failed_rows == 0 else ("partial" if success_rows > 0 else "failed"),
        "errors": errors,
    }


@router.get("/ingest/imports")
async def list_imports(limit: int = 100):
    """导入历史列表。"""
    return {"items": _get_ingest_store().list_imports(limit)}


@router.get("/ingest/imports/{import_id}")
async def get_import_detail(import_id: str):
    """导入批次详情（含行级明细）。"""
    store = _get_ingest_store()
    imp = store.get_import(import_id)
    if imp is None:
        raise HTTPException(status_code=404, detail=f"导入批次不存在: {import_id}")
    return {**imp, "rows": store.get_rows(import_id)}
