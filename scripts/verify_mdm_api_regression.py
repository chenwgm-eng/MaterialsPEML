"""P1-P5 主数据治理 API 回归验证。

直接调用 Store 层验证所有 P1-P5 查询功能，无需启动 HTTP 服务。
覆盖：
- P1 参考字典中心：状态码/分类码/单位/换算/标准/GHS/维度
- P2 物料/样品/设备/位置：9 张表
- P3 CIMC：5 张表
- P4 工艺路线：6 张表
- P5 文档版本与执行快照：3 张表

只读操作，安全可重复执行。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from battery_materials_agent.mdm.reference_dict import ReferenceDictStore
from battery_materials_agent.mdm.master_data import MasterDataStore
from battery_materials_agent.mdm.cimc import CimcStore
from battery_materials_agent.mdm.process import ProcessStore
from battery_materials_agent.mdm.documents import DocumentStore


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "[OK]  " if ok else "[FAIL]"
    print(f"{mark} {name} — {detail}")
    return ok


def main() -> int:
    print("=== P1-P5 主数据治理 API 回归验证 ===\n")
    results: list[bool] = []

    # ── P1 参考字典中心 ──────────────────────────────────
    print("── P1 参考字典中心 ──")
    p1 = ReferenceDictStore()
    items = p1.list_status_codes()
    results.append(_check("list_status_codes", len(items) > 0, f"返回 {len(items)} 条"))

    items = p1.list_status_codes(domain="sample")
    results.append(_check("list_status_codes(domain=sample)", len(items) > 0,
                          f"返回 {len(items)} 条"))

    sc = p1.get_status_code("sample", "created")
    results.append(_check("get_status_code(sample, created)", sc is not None,
                          sc.label if sc else "未找到"))

    items = p1.list_classifications()
    results.append(_check("list_classifications", len(items) > 0, f"返回 {len(items)} 条"))

    items = p1.list_classifications(domain="experiment_type")
    results.append(_check("list_classifications(domain=experiment_type)",
                          len(items) >= 8, f"返回 {len(items)} 条（应≥8）"))

    cls = p1.get_classification("experiment_type.xrd")
    results.append(_check("get_classification(experiment_type.xrd)", cls is not None,
                          cls.label if cls else "未找到"))

    items = p1.list_units()
    results.append(_check("list_units", len(items) > 0, f"返回 {len(items)} 条"))

    items = p1.list_units(dimension="mass")
    results.append(_check("list_units(dimension=mass)", len(items) > 0,
                          f"返回 {len(items)} 条"))

    u = p1.get_unit("g")
    results.append(_check("get_unit(g)", u is not None, u.name if u else "未找到"))

    items = p1.list_conversions()
    results.append(_check("list_conversions", len(items) > 0, f"返回 {len(items)} 条"))

    items = p1.list_conversions(from_unit="kg")
    results.append(_check("list_conversions(from_unit=kg)", len(items) > 0,
                          f"返回 {len(items)} 条"))

    # 单位换算工具
    val = p1.convert(1.0, "g", "kg")
    results.append(_check("convert(1.0, g, kg)", abs(val - 0.001) < 1e-9, f"= {val}"))

    items = p1.list_standards()
    results.append(_check("list_standards", isinstance(items, list),
                          f"返回 {len(items)} 条（初始为空属正常）"))

    items = p1.list_ghs_classes()
    results.append(_check("list_ghs_classes", isinstance(items, list),
                          f"返回 {len(items)} 条（初始为空属正常）"))

    items = p1.list_dimensions()
    results.append(_check("list_dimensions", len(items) > 0, f"返回 {len(items)} 条"))

    # ── P2 物料/样品/设备/位置 ──────────────────────────
    print("\n── P2 物料/样品/设备/位置 ──")
    p2 = MasterDataStore()

    items = p2.list_sample_types()
    results.append(_check("list_sample_types", len(items) > 0, f"返回 {len(items)} 条"))

    st = p2.get_sample_type("raw_material")
    results.append(_check("get_sample_type(raw_material)", st is not None,
                          st.name if st else "未找到"))

    items = p2.list_sample_status_transitions()
    results.append(_check("list_sample_status_transitions", len(items) > 0,
                          f"返回 {len(items)} 条"))

    ok = p2.is_transition_allowed("created", "in_storage")
    results.append(_check("is_transition_allowed(created→in_storage)",
                          ok is True, f"allowed={ok}"))

    items = p2.list_locations()
    results.append(_check("list_locations", isinstance(items, list),
                          f"返回 {len(items)} 条（初始为空属正常）"))

    items = p2.list_containers()
    results.append(_check("list_containers", isinstance(items, list),
                          f"返回 {len(items)} 条（初始为空属正常）"))

    items = p2.list_logistics_types()
    results.append(_check("list_logistics_types", len(items) > 0, f"返回 {len(items)} 条"))

    items = p2.list_equipment_templates()
    results.append(_check("list_equipment_templates", isinstance(items, list),
                          f"返回 {len(items)} 条（初始为空属正常）"))

    items = p2.list_equipment_capabilities()
    results.append(_check("list_equipment_capabilities", len(items) > 0,
                          f"返回 {len(items)} 条"))

    items = p2.list_material_categories()
    results.append(_check("list_material_categories", len(items) > 0,
                          f"返回 {len(items)} 条"))

    # ── P3 CIMC ──────────────────────────────────────
    print("\n── P3 CIMC ──")
    p3 = CimcStore()

    items = p3.list_properties()
    results.append(_check("list_properties", len(items) > 0, f"返回 {len(items)} 条"))

    items = p3.list_test_methods()
    results.append(_check("list_test_methods", len(items) > 0, f"返回 {len(items)} 条"))

    items = p3.list_test_items()
    results.append(_check("list_test_items", len(items) > 0, f"返回 {len(items)} 条"))

    items = p3.list_specifications()
    results.append(_check("list_specifications", len(items) > 0, f"返回 {len(items)} 条"))

    items = p3.list_inspection_capabilities()
    results.append(_check("list_inspection_capabilities", isinstance(items, list),
                          f"返回 {len(items)} 条（初始为空属正常）"))

    # ── P4 工艺路线 ──────────────────────────────────
    print("\n── P4 工艺路线 ──")
    p4 = ProcessStore()

    items = p4.list_process_routes()
    results.append(_check("list_process_routes", isinstance(items, list),
                          f"返回 {len(items)} 条（初始为空属正常）"))

    items = p4.list_process_steps()
    results.append(_check("list_process_steps", len(items) > 0, f"返回 {len(items)} 条"))

    items = p4.list_process_parameters()
    results.append(_check("list_process_parameters", len(items) > 0,
                          f"返回 {len(items)} 条"))

    items = p4.list_route_steps()
    results.append(_check("list_route_steps", isinstance(items, list),
                          f"返回 {len(items)} 条（初始为空属正常）"))

    items = p4.list_step_parameters()
    results.append(_check("list_step_parameters", isinstance(items, list),
                          f"返回 {len(items)} 条（初始为空属正常）"))

    items = p4.list_step_equipment_templates()
    results.append(_check("list_step_equipment_templates", isinstance(items, list),
                          f"返回 {len(items)} 条（初始为空属正常）"))

    # ── P5 文档版本与执行快照 ──────────────────────────
    print("\n── P5 文档版本与执行快照 ──")
    p5 = DocumentStore()

    items = p5.list_documents()
    results.append(_check("list_documents", isinstance(items, list),
                          f"返回 {len(items)} 条（初始为空属正常）"))

    items = p5.list_document_versions()
    results.append(_check("list_document_versions", isinstance(items, list),
                          f"返回 {len(items)} 条"))

    items = p5.list_order_snapshots()
    results.append(_check("list_order_snapshots", isinstance(items, list),
                          f"返回 {len(items)} 条"))

    # ── 汇总 ──────────────────────────────────────────
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n=== 汇总：{passed}/{total} 通过 ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
