"""历史证据来源字段迁移 — source_type / source_service 三级信任分级。

将 ``scientific_kernel.evidence`` 表中旧版来源字段迁移为新的
``{tier}:{provider}`` 格式（见 ``contracts/evidence.py`` 的
``LEGACY_SOURCE_TYPE_TO_TIER`` / ``BUILTIN_SOURCE_MARKERS``）。

映射规则:
  - ``native_service`` 依据 ``metadata_json`` 中是否含内置库标记（"(内置)" 等）
    映射为 ``builtin_library`` 或 ``real_engine``
  - ``scp`` / ``skill`` 统一映射为 ``real_engine``（外部服务视为真实来源）
  - 幂等：已为 ``{tier}:{provider}`` 格式（含冒号）或已在目标 tier 集合内的行跳过

用法:
  python scripts/migrate_evidence_source_tier.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# 允许直接以 scripts/ 为工作目录运行时导入项目包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from battery_materials_agent.db import get_engine
from battery_materials_agent.contracts.evidence import (
    BUILTIN_SOURCE_MARKERS,
    LEGACY_SOURCE_TYPE_TO_TIER,
    SourceTier,
)

logger = logging.getLogger(__name__)

# 新格式合法 tier 值（用于幂等判断）
_VALID_TIERS = {t.value for t in SourceTier}
# 需要迁移的旧 source_type 取值
_LEGACY_TYPES = set(LEGACY_SOURCE_TYPE_TO_TIER)


def _is_builtin(metadata: dict) -> bool:
    """判断 metadata 中是否含内置库兜底标记。"""
    source = str(metadata.get("source", "") or "")
    return any(marker in source for marker in BUILTIN_SOURCE_MARKERS)


def _migrate_row(row) -> dict:
    """将单行证据映射为新的 source_type / source_service / metadata。

    Returns:
        dict: 含 evidence_id / old_source_type / old_source_service /
              new_source_type / new_source_service / metadata_patch（如变更）。
    """
    evidence_id = row["evidence_id"]
    old_type = (row["source_type"] or "").strip()
    old_service = (row["source_service"] or "").strip()
    metadata = row.get("metadata_json") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            metadata = {}

    # 幂等：已为 {tier}:{provider} 新格式则跳过
    if ":" in old_service and old_service.split(":", 1)[0] in _VALID_TIERS:
        return {
            "evidence_id": evidence_id,
            "skipped": True,
            "reason": "already-format",
        }

    # 旧 source_service 直接作为 provider（历史存的是提供者名，无 tier 前缀）
    provider = old_service or metadata.get("provider") or metadata.get("source") or "unknown"

    # 映射 tier
    if old_type in _LEGACY_TYPES:
        tier = LEGACY_SOURCE_TYPE_TO_TIER[old_type]
        # native_service 需二次校正：内置库兜底识别
        if old_type == "native_service" and _is_builtin(metadata):
            tier = SourceTier.BUILTIN_LIBRARY
    elif old_type in _VALID_TIERS:
        # 已是新 tier 但 source_service 未带前缀（历史遗留）
        tier = SourceTier(old_type)
    else:
        # 未知旧类型：按 source 字符串推断，默认 real_engine
        tier = SourceTier.BUILTIN_LIBRARY if _is_builtin(metadata) else SourceTier.REAL_ENGINE

    new_type = tier.value
    new_service = f"{new_type}:{provider}"

    metadata_patch: dict = {}
    if new_type == SourceTier.BUILTIN_LIBRARY.value:
        metadata_patch["fallback_reason"] = f"历史数据迁移：真实引擎未命中，回退至 {provider}"
    elif new_type == SourceTier.LLM_GENERATED.value:
        metadata_patch["fallback_reason"] = "LLM 纯记忆生成，未经外部核验"
    metadata_patch["source_tier"] = new_type
    metadata_patch["provider"] = provider

    # 合并原有 metadata，保留历史字段，仅补充迁移相关字段
    merged_metadata = dict(metadata)
    merged_metadata.update(metadata_patch)

    return {
        "evidence_id": evidence_id,
        "skipped": False,
        "old_source_type": old_type,
        "old_source_service": old_service,
        "new_source_type": new_type,
        "new_source_service": new_service,
        "metadata": merged_metadata,
    }


def migrate_evidence_source_tier(dry_run: bool = False) -> dict:
    """执行 source_type / source_service 历史数据迁移。

    Args:
        dry_run: 为 True 时仅统计与打印，不写库。

    Returns:
        dict: {"migrated": int, "skipped": int, "rows": list[dict]}
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT evidence_id, source_type, source_service, metadata_json "
                "FROM scientific_kernel.evidence"
            )
        ).mappings().all()

    migrated: list[dict] = []
    skipped = 0
    for row in rows:
        result = _migrate_row(row)
        if result.get("skipped"):
            skipped += 1
            continue
        migrated.append(result)

    if dry_run:
        logger.info("[dry-run] 待迁移 %d 行，跳过 %d 行", len(migrated), skipped)
        for r in migrated:
            logger.info(
                "  %s: %r -> %r",
                r["evidence_id"],
                r["old_source_service"] or r["old_source_type"],
                r["new_source_service"],
            )
        return {"migrated": len(migrated), "skipped": skipped, "rows": migrated}

    if not migrated:
        logger.info("无历史数据需要迁移")
        return {"migrated": 0, "skipped": skipped, "rows": []}

    with engine.begin() as conn:
        for r in migrated:
            conn.execute(
                text(
                    "UPDATE scientific_kernel.evidence "
                    "SET source_type = :source_type, source_service = :source_service, "
                    "    metadata_json = CAST(:metadata AS JSONB) "
                    "WHERE evidence_id = :evidence_id"
                ),
                {
                    "source_type": r["new_source_type"],
                    "source_service": r["new_source_service"],
                    "metadata": json.dumps(r["metadata"], ensure_ascii=False),
                    "evidence_id": r["evidence_id"],
                },
            )
            logger.info(
                "已迁移 %s: %r -> %r (%s)",
                r["evidence_id"],
                r["old_source_service"] or r["old_source_type"],
                r["new_source_service"],
                r["new_source_type"],
            )

    logger.info("迁移完成：共 %d 行，跳过 %d 行", len(migrated), skipped)
    return {"migrated": len(migrated), "skipped": skipped, "rows": migrated}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="迁移历史证据来源字段为三级信任分级")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览映射结果，不写入数据库",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    migrate_evidence_source_tier(dry_run=args.dry_run)