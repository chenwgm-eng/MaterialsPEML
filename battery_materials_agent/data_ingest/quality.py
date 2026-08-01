"""数据质量检查：缺失/非法值/单位问题/异常值/重复/未映射字段。

输入 rows + mapping + entity_type，输出汇总报告与逐行 row_status。
单位归一化：g/克/kg/千克/mg/毫克/mL/毫升/L/升/片/pcs → g/kg/mg/mL/L/片。
异常值用 IQR 法判定，只标记不阻断。
与库内已有数据的重复比对由 store 层负责，此处仅做文件内重复检查。

.. deprecated:: Task 12.5
    本模块为文件级（CSV/Excel）批量质量检查，保留 API 向后兼容。
    单条 ExperimentResultRecord 的 QC 检查已统一到
    ``battery_materials_agent.qc_service`` 模块（基于
    ``middleware/wet_data/quality.py`` 的 QCEngine）。
    新代码请优先使用 ``qc_service.check_record()`` / ``qc_service.check_and_audit()``，
    以获得 rule_id / decision_path / rule_version 等可解释字段。
    调用 ``check_quality()`` 会发出 ``DeprecationWarning``。
"""

from __future__ import annotations

import math
import re
import warnings

from .field_dict import get_field_dict

# Task 12.5 标记：模块标记为 deprecated，由 check_quality() 实际调用时发出告警
__deprecated__ = "Task 12.5：单条记录 QC 请改用 battery_materials_agent.qc_service"

# 单位归一化表：各种写法 → canonical 单位
UNIT_NORMALIZATION: dict[str, str] = {
    "g": "g", "克": "g", "gram": "g", "grams": "g",
    "kg": "kg", "千克": "kg", "公斤": "kg",
    "mg": "mg", "毫克": "mg",
    "ml": "mL", "mL": "mL", "毫升": "mL",
    "l": "L", "L": "L", "升": "L",
    "片": "片", "pcs": "片", "PCS": "片", "个": "片", "件": "片",
}

# 同族单位换算到族内基准单位（质量→g，体积→mL）
_UNIT_FAMILY: dict[str, tuple[str, float]] = {
    "g": ("g", 1.0), "kg": ("g", 1000.0), "mg": ("g", 0.001),
    "mL": ("mL", 1.0), "L": ("mL", 1000.0),
    "片": ("片", 1.0),
}

# 各实体业务键（文件内查重）
_BUSINESS_KEYS: dict[str, list[list[str]]] = {
    "sample": [["sample_code"], ["name", "batch_number"]],
    "equipment": [["equipment_id"], ["name", "serial_number"]],
    "raw_material": [["material_id"], ["name", "batch_number"]],
    "project": [["name"]],
}


def normalize_unit(unit: str) -> str | None:
    """归一化单位字符串，无法识别返回 None。"""
    if unit is None:
        return None
    text = str(unit).strip()
    if not text:
        return ""
    return UNIT_NORMALIZATION.get(text) or UNIT_NORMALIZATION.get(text.lower())


def normalize_quantity(value: float, unit: str) -> tuple[float, str]:
    """把数量换算到单位族基准单位（质量→g，体积→mL），返回 (value, canonical_unit)。"""
    canonical = normalize_unit(unit)
    if canonical is None or canonical not in _UNIT_FAMILY:
        return value, str(unit or "")
    base, factor = _UNIT_FAMILY[canonical]
    return value * factor, base


def parse_number(value) -> float | None:
    """解析数值，失败返回 None。支持 '1,234.5' 与 '123g' 这类简单带单位写法。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    m = re.match(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def get_mapped_value(row: dict, mapping: dict, key: str):
    """按映射取源行中 canonical 字段的原始值。"""
    m = mapping.get(key) or {}
    col = m.get("column") or ""
    if not col:
        return ""
    return row.get(col, "")


def build_record(row: dict, mapping: dict, entity_type: str) -> tuple[dict, list[str]]:
    """把源行转换为 canonical 记录（数值字段解析、单位归一化），返回 (record, errors)。"""
    record: dict = {}
    errors: list[str] = []
    fields = {f["key"]: f for f in get_field_dict(entity_type)}
    for key, field in fields.items():
        raw = get_mapped_value(row, mapping, key)
        if isinstance(raw, str):
            raw = raw.strip()
        if field["type"] == "number":
            if raw == "" or raw is None:
                record[key] = None
            else:
                num = parse_number(raw)
                if num is None:
                    record[key] = None
                    errors.append(f"字段「{field['label']}」数值无法解析: {raw}")
                else:
                    record[key] = num
        else:
            record[key] = "" if raw is None else str(raw)
    # 单位归一化（有 unit 字段的实体）
    if "unit" in fields and record.get("unit"):
        normalized = normalize_unit(record["unit"])
        if normalized is None:
            errors.append(f"单位无法归一化: {record['unit']}")
        else:
            record["unit"] = normalized
    return record, errors


def _business_key(record: dict, entity_type: str) -> str | None:
    """计算业务键，所有候选键全空时返回 None。"""
    for key_fields in _BUSINESS_KEYS.get(entity_type, []):
        parts = [str(record.get(f) or "").strip() for f in key_fields]
        if all(parts):
            return "|".join(parts)
    return None


def _iqr_outliers(values: list[tuple[int, float]], field_key: str) -> list[dict]:
    """IQR 法判定异常值，输入 (row_index, value) 列表。"""
    nums = sorted(v for _, v in values)
    n = len(nums)
    if n < 4:
        return []

    def _quantile(sorted_vals: list[float], q: float) -> float:
        pos = (len(sorted_vals) - 1) * q
        lo = math.floor(pos)
        hi = math.ceil(pos)
        if lo == hi:
            return sorted_vals[lo]
        return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)

    q1 = _quantile(nums, 0.25)
    q3 = _quantile(nums, 0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return []
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return [
        {"row": idx, "field": field_key, "value": v, "range": [round(lower, 6), round(upper, 6)]}
        for idx, v in values if v < lower or v > upper
    ]


def check_quality(rows: list[dict], mapping: dict, entity_type: str) -> dict:
    """质量检查主入口。返回汇总报告 + 逐行 row_status。

    .. deprecated:: Task 12.5
        单条记录 QC 请改用 ``battery_materials_agent.qc_service.check_record()``。
    """
    warnings.warn(
        "data_ingest.quality.check_quality 已 deprecated；"
        "单条记录 QC 请改用 battery_materials_agent.qc_service.check_record()。",
        DeprecationWarning,
        stacklevel=2,
    )
    fields = get_field_dict(entity_type)
    required_fields = [f for f in fields if f["required"]]
    number_fields = [f for f in fields if f["type"] == "number"]

    missing_required: list[dict] = []
    illegal_values: list[dict] = []
    unit_issues: list[dict] = []
    outliers: list[dict] = []
    duplicates: list[dict] = []
    unmapped_fields = [
        {"key": f["key"], "label": f["label"], "required": f["required"]}
        for f in fields
        if not (mapping.get(f["key"]) or {}).get("column")
    ]

    row_results: list[dict] = []
    records: list[dict] = []
    numeric_columns: dict[str, list[tuple[int, float]]] = {f["key"]: [] for f in number_fields}
    seen_keys: dict[str, int] = {}

    for idx, row in enumerate(rows):
        issues: list[str] = []
        has_error = False
        record, parse_errors = build_record(row, mapping, entity_type)
        records.append(record)

        # 必填缺失
        for f in required_fields:
            val = record.get(f["key"])
            if val is None or val == "":
                missing_required.append({"row": idx, "field": f["key"], "label": f["label"]})
                issues.append(f"必填字段「{f['label']}」缺失")
                has_error = True

        # 数值非法（解析错误已在 build_record 收集）
        for err in parse_errors:
            if "数值无法解析" in err:
                illegal_values.append({"row": idx, "issue": err})
                has_error = True
            elif "单位无法归一化" in err:
                unit_issues.append({"row": idx, "issue": err})
            issues.append(err)

        # 收集数值列供 IQR
        for f in number_fields:
            v = record.get(f["key"])
            if isinstance(v, (int, float)):
                numeric_columns[f["key"]].append((idx, v))

        # 文件内业务键查重
        bk = _business_key(record, entity_type)
        if bk is not None:
            if bk in seen_keys:
                first = seen_keys[bk]
                duplicates.append({"rows": [first, idx], "key": bk})
                issues.append(f"与第 {first + 1} 行业务键重复")
            else:
                seen_keys[bk] = idx

        status = "error" if has_error else ("warning" if issues else "ok")
        row_results.append({"row_index": idx, "status": status, "issues": issues})

    # IQR 异常值（只标记为 warning，不阻断）
    outlier_rows: dict[int, list[str]] = {}
    for f in number_fields:
        for item in _iqr_outliers(numeric_columns[f["key"]], f["key"]):
            outliers.append(item)
            outlier_rows.setdefault(item["row"], []).append(
                f"字段「{f['label']}」数值 {item['value']} 超出 IQR 正常范围"
            )
    for r_idx, msgs in outlier_rows.items():
        rr = row_results[r_idx]
        rr["issues"].extend(msgs)
        if rr["status"] == "ok":
            rr["status"] = "warning"

    status_counts = {"ok": 0, "warning": 0, "error": 0}
    for rr in row_results:
        status_counts[rr["status"]] += 1

    return {
        "summary": {
            "total_rows": len(rows),
            "ok": status_counts["ok"],
            "warning": status_counts["warning"],
            "error": status_counts["error"],
            "missing_required": len(missing_required),
            "illegal_values": len(illegal_values),
            "unit_issues": len(unit_issues),
            "outliers": len(outliers),
            "duplicates": len(duplicates),
            "unmapped_fields": len(unmapped_fields),
        },
        "missing_required": missing_required,
        "illegal_values": illegal_values,
        "unit_issues": unit_issues,
        "outliers": outliers,
        "duplicates": duplicates,
        "unmapped_fields": unmapped_fields,
        "rows": row_results,
        "records": records,
    }
