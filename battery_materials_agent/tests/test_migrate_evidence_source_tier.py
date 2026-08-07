"""历史证据来源字段迁移脚本单元测试。

覆盖场景：
- native_service 无内置标记 → real_engine
- native_service 含内置标记 → builtin_library
- scp / skill → real_engine
- 已为新格式（含冒号且 tier 合法）→ 跳过
- metadata 合并保留历史字段
"""

from __future__ import annotations

import unittest

from scripts.migrate_evidence_source_tier import _migrate_row


def _row(
    evidence_id: str,
    source_type: str,
    source_service: str,
    metadata: dict | str,
) -> dict:
    return {
        "evidence_id": evidence_id,
        "source_type": source_type,
        "source_service": source_service,
        "metadata_json": metadata,
    }


class TestMigrateEvidenceSourceTier(unittest.TestCase):
    def test_native_service_no_builtin_maps_to_real_engine(self):
        result = _migrate_row(_row("e1", "native_service", "mpa", {"source": "mpa"}))
        self.assertFalse(result["skipped"])
        self.assertEqual(result["new_source_type"], "real_engine")
        self.assertEqual(result["new_source_service"], "real_engine:mpa")

    def test_native_service_with_builtin_marker_maps_to_builtin_library(self):
        result = _migrate_row(
            _row("e2", "native_service", "DIPPR", {"source": "DIPPR(内置)"})
        )
        self.assertFalse(result["skipped"])
        self.assertEqual(result["new_source_type"], "builtin_library")
        self.assertEqual(result["new_source_service"], "builtin_library:DIPPR")
        self.assertIn("fallback_reason", result["metadata"])

    def test_scp_maps_to_real_engine(self):
        result = _migrate_row(_row("e3", "scp", "gnome", {"source": "gnome"}))
        self.assertFalse(result["skipped"])
        self.assertEqual(result["new_source_type"], "real_engine")
        self.assertEqual(result["new_source_service"], "real_engine:gnome")

    def test_skill_maps_to_real_engine(self):
        result = _migrate_row(_row("e4", "skill", "chem", {"source": "chem"}))
        self.assertFalse(result["skipped"])
        self.assertEqual(result["new_source_type"], "real_engine")
        self.assertEqual(result["new_source_service"], "real_engine:chem")

    def test_already_new_format_skipped(self):
        result = _migrate_row(
            _row("e5", "real_engine", "real_engine:mpa", {"source": "mpa"})
        )
        self.assertTrue(result["skipped"])

    def test_metadata_merged_keeps_original_fields(self):
        result = _migrate_row(
            _row(
                "e6",
                "native_service",
                "DIPPR",
                {"source": "DIPPR(内置)", "mol_id": "C1CCCCC1"},
            )
        )
        # 历史字段保留
        self.assertEqual(result["metadata"]["mol_id"], "C1CCCCC1")
        # 迁移字段补充
        self.assertEqual(result["metadata"]["source_tier"], "builtin_library")
        self.assertEqual(result["metadata"]["provider"], "DIPPR")

    def test_lowercase_builtin_marker(self):
        result = _migrate_row(
            _row("e7", "native_service", "DIPPR", {"source": "dippr builtin"})
        )
        self.assertEqual(result["new_source_type"], "builtin_library")


if __name__ == "__main__":
    unittest.main()