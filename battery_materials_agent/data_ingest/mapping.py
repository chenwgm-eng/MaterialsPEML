"""自动字段映射：把源文件列名映射到 canonical 字段。

匹配优先级：完全同名 > 别名(规范化后相同) > 子串包含(fuzzy)。
三轮全局匹配，保证高优先级的字段先占用列。
未匹配的源列进入 unmapped_columns，未映射的 canonical 字段 confidence=none。
"""

from __future__ import annotations

import re

from .field_dict import get_field_dict


def _normalize(text: str) -> str:
    """规范化：小写、去空格/下划线/中划线等分隔符。"""
    return re.sub(r"[\s_\-./\\()（）\[\]【】]+", "", str(text)).lower()


def _targets(field: dict) -> set[str]:
    """字段的所有可匹配名称（key/label/aliases）。"""
    return {field["key"], field["label"]} | set(field.get("aliases", []))


def auto_map(rows: list[dict], entity_type: str) -> dict:
    """输入 rows 与实体类型，输出自动映射结果。

    返回 {
        mapping: {canonical_key: {column, confidence(exact/alias/fuzzy/none), auto(bool)}},
        unmapped_columns: [未匹配到任何 canonical 字段的源列],
        auto_mapped_ratio: 自动映射命中率（已映射字段数 / 字段字典字段数）,
    }
    """
    fields = get_field_dict(entity_type)
    columns: list[str] = []
    for row in rows:
        for col in row.keys():
            if col not in columns:
                columns.append(col)

    norm_col = {col: _normalize(col) for col in columns}
    used_columns: set[str] = set()
    mapping: dict[str, dict] = {
        f["key"]: {"column": "", "confidence": "none", "auto": False} for f in fields
    }

    # 第 1 轮：完全同名（原样匹配 key/label/aliases）
    for field in fields:
        targets = _targets(field)
        for col in columns:
            if col not in used_columns and col in targets:
                used_columns.add(col)
                mapping[field["key"]] = {"column": col, "confidence": "exact", "auto": True}
                break

    # 第 2 轮：别名（规范化后相同）
    for field in fields:
        if mapping[field["key"]]["confidence"] != "none":
            continue
        norm_targets = {_normalize(t) for t in _targets(field)}
        for col in columns:
            if col not in used_columns and norm_col[col] in norm_targets:
                used_columns.add(col)
                mapping[field["key"]] = {"column": col, "confidence": "alias", "auto": True}
                break

    # 第 3 轮：子串包含（fuzzy），规范化后源列与目标互相包含
    for field in fields:
        if mapping[field["key"]]["confidence"] != "none":
            continue
        norm_targets = [t for t in {_normalize(t) for t in _targets(field)} if len(t) >= 2]
        for col in columns:
            if col in used_columns:
                continue
            if any(t in norm_col[col] or norm_col[col] in t for t in norm_targets):
                used_columns.add(col)
                mapping[field["key"]] = {"column": col, "confidence": "fuzzy", "auto": True}
                break

    unmapped_columns = [c for c in columns if c not in used_columns]
    mapped_count = sum(1 for m in mapping.values() if m["confidence"] != "none")
    ratio = round(mapped_count / len(fields), 4) if fields else 0.0

    return {
        "mapping": mapping,
        "unmapped_columns": unmapped_columns,
        "auto_mapped_ratio": ratio,
    }
