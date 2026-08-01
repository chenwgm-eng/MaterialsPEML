"""Task 13 强制合规关联单元测试。

覆盖：
- MaterialSpec 新增合规证据字段（sds_uri / test_report_uri / test_institution / test_date）
- RawMaterialDB._has_evidence 凭证检测（COA/SDS/第三方报告任一即可）
- RawMaterialDB.compute_compliance_status 合规状态判定：
  * non_compliant：声明不合规
  * pending_evidence：声明合规但缺失凭证（不可作为合规依据）
  * compliant：声明合规且关联检测报告
- 合规字段返回结构（status + evidence 嵌套字典）
- field_dict.py raw_material 实体包含 5 个合规证据字段
- compliance_checker.py 对无凭证合规物料输出 pending_evidence 警告
- 向后兼容：旧行（无新列）的物料视为 pending_evidence 而非 compliant
"""

from __future__ import annotations

from unittest.mock import MagicMock

from battery_materials_agent.industrialization.raw_material_db import (
    MaterialSpec,
    RawMaterialDB,
)
from battery_materials_agent.data_ingest.field_dict import get_field_dict


# ───────────────────── MaterialSpec 字段 ─────────────────────

class TestMaterialSpecEvidenceFields:
    """验证 MaterialSpec 模型包含 Task 13 新增的合规证据字段。"""

    def test_spec_has_sds_uri_field(self):
        spec = MaterialSpec(sds_uri="https://example.com/sds.pdf")
        assert spec.sds_uri == "https://example.com/sds.pdf"

    def test_spec_has_test_report_uri_field(self):
        spec = MaterialSpec(test_report_uri="https://example.com/report.pdf")
        assert spec.test_report_uri == "https://example.com/report.pdf"

    def test_spec_has_test_institution_field(self):
        spec = MaterialSpec(test_institution="SGS")
        assert spec.test_institution == "SGS"

    def test_spec_has_test_date_field(self):
        spec = MaterialSpec(test_date="2026-07-26")
        assert spec.test_date == "2026-07-26"

    def test_spec_default_evidence_fields_empty(self):
        """新物料默认无证据，符合 pending_evidence 判定前提。"""
        spec = MaterialSpec(reach_compliant=True)
        assert spec.sds_uri == ""
        assert spec.test_report_uri == ""
        assert spec.test_institution == ""
        assert spec.test_date == ""
        assert spec.coa_uri == ""

    def test_spec_model_dump_includes_evidence_fields(self):
        """model_dump 输出必须包含证据字段，供 API 序列化返回前端。"""
        spec = MaterialSpec()
        dumped = spec.model_dump()
        for key in ("coa_uri", "sds_uri", "test_report_uri", "test_institution", "test_date"):
            assert key in dumped, f"Missing evidence field in model_dump: {key}"


# ───────────────────── 凭证检测 ─────────────────────

class TestHasEvidence:
    """验证 _has_evidence 凭证检测逻辑。"""

    def test_no_evidence_when_all_empty(self):
        spec = MaterialSpec(reach_compliant=True)
        assert RawMaterialDB._has_evidence(spec) is False

    def test_no_evidence_when_all_whitespace(self):
        spec = MaterialSpec(coa_uri="   ", sds_uri="\t", test_report_uri="")
        assert RawMaterialDB._has_evidence(spec) is False

    def test_evidence_from_coa_uri(self):
        spec = MaterialSpec(coa_uri="https://example.com/coa.pdf")
        assert RawMaterialDB._has_evidence(spec) is True

    def test_evidence_from_sds_uri(self):
        spec = MaterialSpec(sds_uri="https://example.com/sds.pdf")
        assert RawMaterialDB._has_evidence(spec) is True

    def test_evidence_from_test_report_uri(self):
        spec = MaterialSpec(test_report_uri="https://example.com/report.pdf")
        assert RawMaterialDB._has_evidence(spec) is True

    def test_evidence_from_any_one_sufficient(self):
        """COA / SDS / 第三方报告任一即可作为凭证。"""
        assert RawMaterialDB._has_evidence(MaterialSpec(coa_uri="x")) is True
        assert RawMaterialDB._has_evidence(MaterialSpec(sds_uri="x")) is True
        assert RawMaterialDB._has_evidence(MaterialSpec(test_report_uri="x")) is True


# ───────────────────── 合规状态判定 ─────────────────────

class TestComputeComplianceStatus:
    """验证 compute_compliance_status 返回结构与状态判定逻辑。"""

    def test_non_compliant_when_reach_false(self):
        """声明不合规 → non_compliant，无论是否有证据。"""
        spec = MaterialSpec(reach_compliant=False, coa_uri="https://x.com/coa.pdf")
        result = RawMaterialDB.compute_compliance_status(spec)
        assert result["status"] == "non_compliant"

    def test_pending_evidence_when_compliant_without_evidence(self):
        """声明合规但无任何检测报告凭证 → pending_evidence（核心场景）。"""
        spec = MaterialSpec(reach_compliant=True)
        result = RawMaterialDB.compute_compliance_status(spec)
        assert result["status"] == "pending_evidence"

    def test_compliant_when_compliant_with_coa(self):
        spec = MaterialSpec(reach_compliant=True, coa_uri="https://x.com/coa.pdf")
        result = RawMaterialDB.compute_compliance_status(spec)
        assert result["status"] == "compliant"

    def test_compliant_when_compliant_with_sds(self):
        spec = MaterialSpec(reach_compliant=True, sds_uri="https://x.com/sds.pdf")
        result = RawMaterialDB.compute_compliance_status(spec)
        assert result["status"] == "compliant"

    def test_compliant_when_compliant_with_test_report(self):
        spec = MaterialSpec(
            reach_compliant=True,
            test_report_uri="https://x.com/report.pdf",
            test_institution="SGS",
            test_date="2026-07-26",
        )
        result = RawMaterialDB.compute_compliance_status(spec)
        assert result["status"] == "compliant"

    def test_status_values_are_constrained(self):
        """status 只能为 compliant / pending_evidence / non_compliant。"""
        valid = {"compliant", "pending_evidence", "non_compliant"}
        for rc in (True, False):
            for ev in (True, False):
                spec = MaterialSpec(reach_compliant=rc)
                if ev:
                    spec.coa_uri = "x"
                assert RawMaterialDB.compute_compliance_status(spec)["status"] in valid

    def test_evidence_dict_keys_match_spec(self):
        """evidence 嵌套字典必须包含 5 个指定键。"""
        spec = MaterialSpec(reach_compliant=True, coa_uri="https://x.com")
        result = RawMaterialDB.compute_compliance_status(spec)
        ev = result["evidence"]
        assert set(ev.keys()) == {
            "coa_uri", "sds_uri", "test_report_uri",
            "test_institution", "test_date",
        }

    def test_evidence_values_none_when_empty(self):
        """未填写的证据字段在返回结构中应为 None（而非空字符串）。"""
        spec = MaterialSpec(reach_compliant=True, coa_uri="https://x.com")
        result = RawMaterialDB.compute_compliance_status(spec)
        ev = result["evidence"]
        assert ev["coa_uri"] == "https://x.com"
        assert ev["sds_uri"] is None
        assert ev["test_report_uri"] is None
        assert ev["test_institution"] is None
        assert ev["test_date"] is None

    def test_evidence_values_populated_when_filled(self):
        spec = MaterialSpec(
            reach_compliant=True,
            coa_uri="https://x.com/coa",
            sds_uri="https://x.com/sds",
            test_report_uri="https://x.com/rpt",
            test_institution="SGS",
            test_date="2026-07-26",
        )
        result = RawMaterialDB.compute_compliance_status(spec)
        ev = result["evidence"]
        assert ev["coa_uri"] == "https://x.com/coa"
        assert ev["sds_uri"] == "https://x.com/sds"
        assert ev["test_report_uri"] == "https://x.com/rpt"
        assert ev["test_institution"] == "SGS"
        assert ev["test_date"] == "2026-07-26"

    def test_return_structure_is_dict_with_status_and_evidence(self):
        """返回结构必须为 {status, evidence} 顶层字典。"""
        spec = MaterialSpec()
        result = RawMaterialDB.compute_compliance_status(spec)
        assert isinstance(result, dict)
        assert set(result.keys()) == {"status", "evidence"}
        assert isinstance(result["evidence"], dict)


# ───────────────────── 向后兼容 ─────────────────────

class TestBackwardCompatibility:
    """旧数据（reach_compliant=True 但无证据）应判定为 pending_evidence。"""

    def test_legacy_compliant_without_evidence_becomes_pending(self):
        """历史数据 reach_compliant=True 但 coa_uri/sds_uri/test_report_uri 均空
        → 不应直接判定为 compliant，应为 pending_evidence。"""
        legacy_spec = MaterialSpec(
            material_id="RM-LEGACY-001",
            name="Legacy PEO",
            reach_compliant=True,
            # 旧数据没有任何证据字段
            coa_uri="",
            sds_uri="",
            test_report_uri="",
        )
        result = RawMaterialDB.compute_compliance_status(legacy_spec)
        assert result["status"] == "pending_evidence"

    def test_legacy_compliant_with_coa_still_compliant(self):
        """旧数据若已有 coa_uri（0001 迁移已含该列），仍判定为 compliant。"""
        legacy_spec = MaterialSpec(
            material_id="RM-LEGACY-002",
            name="Legacy LiTFSI",
            reach_compliant=True,
            coa_uri="https://legacy.com/coa.pdf",
        )
        result = RawMaterialDB.compute_compliance_status(legacy_spec)
        assert result["status"] == "compliant"


# ───────────────────── field_dict 字段定义 ─────────────────────

class TestFieldDictComplianceFields:
    """验证 field_dict.py 的 raw_material 实体包含 5 个合规证据字段。"""

    def test_raw_material_has_coa_uri_field(self):
        keys = {f["key"] for f in get_field_dict("raw_material")}
        assert "coa_uri" in keys

    def test_raw_material_has_sds_uri_field(self):
        keys = {f["key"] for f in get_field_dict("raw_material")}
        assert "sds_uri" in keys

    def test_raw_material_has_test_report_uri_field(self):
        keys = {f["key"] for f in get_field_dict("raw_material")}
        assert "test_report_uri" in keys

    def test_raw_material_has_test_institution_field(self):
        keys = {f["key"] for f in get_field_dict("raw_material")}
        assert "test_institution" in keys

    def test_raw_material_has_test_date_field(self):
        keys = {f["key"] for f in get_field_dict("raw_material")}
        assert "test_date" in keys

    def test_evidence_fields_have_aliases(self):
        """证据字段必须配置中文别名，导入时才能识别。"""
        fields = {f["key"]: f for f in get_field_dict("raw_material")}
        assert "COA" in fields["coa_uri"]["aliases"]
        assert "SDS" in fields["sds_uri"]["aliases"]
        assert "检测报告" in fields["test_report_uri"]["aliases"]
        assert "检测机构" in fields["test_institution"]["aliases"]
        assert "检测日期" in fields["test_date"]["aliases"]

    def test_test_date_is_date_type(self):
        fields = {f["key"]: f for f in get_field_dict("raw_material")}
        assert fields["test_date"]["type"] == "date"


# ───────────────────── compliance_checker 凭证校验 ─────────────────────

class TestComplianceCheckerEvidenceWarning:
    """验证 compliance_checker 对无凭证合规物料输出 pending_evidence 警告。"""

    def _make_checker(self, specs: dict[str, MaterialSpec]):
        """构造不依赖 DB 与 SCP 的 ComplianceAndCostNode 实例。"""
        from battery_materials_agent.industrialization.compliance_checker import (
            ComplianceAndCostNode,
        )
        db = MagicMock()
        db.get_spec = MagicMock(side_effect=lambda mid: specs.get(mid))
        db.get_all = MagicMock(return_value=list(specs.values()))
        checker = ComplianceAndCostNode.__new__(ComplianceAndCostNode)
        checker.db = db
        checker.cost_threshold = 500.0
        checker.blacklist_smarts = []
        checker._scp_enabled = False
        checker._mcp_tool_registry = None
        checker._scp_client_pool = None
        return checker

    def test_compliant_without_evidence_emits_warning(self):
        """声明合规但无凭证 → 警告中含'待补充证据'。"""
        spec = MaterialSpec(
            material_id="RM-001", name="PEO",
            reach_compliant=True, cost_per_kg=85.0,
            # 无任何证据
        )
        checker = self._make_checker({"RM-001": spec})
        report = checker._evaluate_sync({"RM-001": 1.0})
        assert any("待补充证据" in w for w in report.warnings)

    def test_compliant_with_evidence_no_pending_warning(self):
        """声明合规且有关联凭证 → 不应出现'待补充证据'警告。"""
        spec = MaterialSpec(
            material_id="RM-001", name="PEO",
            reach_compliant=True, cost_per_kg=85.0,
            coa_uri="https://x.com/coa.pdf",
        )
        checker = self._make_checker({"RM-001": spec})
        report = checker._evaluate_sync({"RM-001": 1.0})
        assert not any("待补充证据" in w for w in report.warnings)

    def test_non_compliant_still_fatal(self):
        """声明不合规仍是 fatal_error，与凭证无关。"""
        spec = MaterialSpec(
            material_id="RM-002", name="Toxic X",
            reach_compliant=False, cost_per_kg=10.0,
            coa_uri="https://x.com/coa.pdf",  # 有证据但声明不合规
        )
        checker = self._make_checker({"RM-002": spec})
        report = checker._evaluate_sync({"RM-002": 1.0})
        assert any("不符合 REACH" in e for e in report.fatal_errors)
        assert not any("待补充证据" in w for w in report.warnings)

    def test_sds_uri_counts_as_evidence(self):
        """SDS 报告链接同样可作为合规凭证。"""
        spec = MaterialSpec(
            material_id="RM-003", name="LiTFSI",
            reach_compliant=True, cost_per_kg=450.0,
            sds_uri="https://x.com/sds.pdf",
        )
        checker = self._make_checker({"RM-003": spec})
        report = checker._evaluate_sync({"RM-003": 1.0})
        assert not any("待补充证据" in w for w in report.warnings)

    def test_pending_evidence_does_not_block_pass(self):
        """无凭证合规物料只产生警告，不应变为 fatal_error 阻断流程
        （向后兼容：旧数据 reach_compliant=True 但无证据不应立即熔断）。"""
        spec = MaterialSpec(
            material_id="RM-004", name="Legacy",
            reach_compliant=True, cost_per_kg=50.0,
        )
        checker = self._make_checker({"RM-004": spec})
        report = checker._evaluate_sync({"RM-004": 1.0})
        assert report.is_passed is True
        assert len(report.warnings) >= 1
