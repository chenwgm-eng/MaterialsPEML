"""P1-P5 主数据治理 FK 完整性验证。

验证内容：
1. P1-P5 创建的所有主数据表存在
2. P5 加固的 6 个 FK 约束已生效
3. P1-P5 跨表 FK 关系完整
4. 关键 FK 引用完整性（无孤立记录）

只读操作，安全可重复执行。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让脚本可在未安装包时直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from battery_materials_agent.db import get_engine
from sqlalchemy import text


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "[OK]  " if ok else "[FAIL]"
    print(f"{mark} {name} — {detail}")
    return ok


def _table_exists(conn, schema: str, table: str) -> bool:
    r = conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :s AND table_name = :t"
        ),
        {"s": schema, "t": table},
    ).fetchone()
    return r is not None


def _fk_exists(conn, table_schema: str, table_name: str, constraint_name: str) -> bool:
    r = conn.execute(
        text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_type = 'FOREIGN KEY' "
            "AND table_schema = :s AND table_name = :t "
            "AND constraint_name = :c"
        ),
        {"s": table_schema, "t": table_name, "c": constraint_name},
    ).fetchone()
    return r is not None


def _count_orphans(conn, schema: str, table: str, column: str,
                   ref_schema: str, ref_table: str, ref_column: str) -> int:
    """统计孤立记录数（column 非空但在引用表中找不到）。"""
    r = conn.execute(
        text(
            f"SELECT COUNT(*) FROM {schema}.{table} t "
            f"WHERE t.{column} IS NOT NULL AND t.{column} <> '' "
            f"AND t.{column} NOT IN (SELECT {ref_column} FROM {ref_schema}.{ref_table})"
        )
    ).fetchone()
    return r[0] if r else 0


def main() -> int:
    print("=== P1-P5 主数据治理 FK 完整性验证 ===\n")
    engine = get_engine()
    results: list[bool] = []

    with engine.connect() as conn:
        # ── 1. P1 主数据表存在性 ──────────────────────────────
        print("── P1 参考字典中心表存在性 ──")
        p1_tables = [
            ("mdm", "status_codes"),
            ("mdm", "classifications"),
            ("mdm", "units"),
            ("mdm", "unit_conversions"),
            ("mdm", "standards"),
            ("mdm", "ghs_classes"),
            ("mdm", "dimensions"),
        ]
        for s, t in p1_tables:
            results.append(_check(f"表 {s}.{t}", _table_exists(conn, s, t),
                                  "存在" if _table_exists(conn, s, t) else "缺失"))

        # ── 2. P2 主数据表存在性 ──────────────────────────────
        print("\n── P2 物料/样品/设备/位置表存在性 ──")
        p2_tables = [
            ("mdm", "sample_types"),
            ("mdm", "sample_status_transitions"),
            ("mdm", "locations"),
            ("mdm", "containers"),
            ("mdm", "logistics_types"),
            ("mdm", "equipment_templates"),
            ("mdm", "equipment_capabilities"),
            ("mdm", "equipment_template_capabilities"),
            ("mdm", "material_categories"),
        ]
        for s, t in p2_tables:
            results.append(_check(f"表 {s}.{t}", _table_exists(conn, s, t),
                                  "存在" if _table_exists(conn, s, t) else "缺失"))

        # 域 6（组织/人员/资质）应不存在
        print("\n── 域 6（组织/人员/资质）应不存在 ──")
        for t in ["organizations", "persons", "suppliers"]:
            exists = _table_exists(conn, "mdm", t)
            results.append(_check(f"表 mdm.{t} 不存在", not exists,
                                  "正确移除" if not exists else "错误：表仍存在"))

        # ── 3. P3 CIMC 表存在性 ──────────────────────────────
        print("\n── P3 CIMC 表存在性 ──")
        p3_tables = [
            ("mdm", "properties"),
            ("mdm", "test_items"),
            ("mdm", "test_methods"),
            ("mdm", "specifications"),
            ("mdm", "inspection_capabilities"),
        ]
        for s, t in p3_tables:
            results.append(_check(f"表 {s}.{t}", _table_exists(conn, s, t),
                                  "存在" if _table_exists(conn, s, t) else "缺失"))

        # ── 4. P4 工艺路线表存在性 ──────────────────────────────
        print("\n── P4 工艺路线表存在性 ──")
        p4_tables = [
            ("mdm", "process_routes"),
            ("mdm", "process_steps"),
            ("mdm", "process_parameters"),
            ("mdm", "process_route_steps"),
            ("mdm", "process_step_parameters"),
            ("mdm", "process_step_equipment_templates"),
        ]
        for s, t in p4_tables:
            results.append(_check(f"表 {s}.{t}", _table_exists(conn, s, t),
                                  "存在" if _table_exists(conn, s, t) else "缺失"))

        # ── 5. P5 文档与快照表存在性 ──────────────────────────────
        print("\n── P5 文档与快照表存在性 ──")
        p5_tables = [
            ("mdm", "documents"),
            ("mdm", "document_versions"),
            ("experiment", "order_version_snapshots"),
        ]
        for s, t in p5_tables:
            results.append(_check(f"表 {s}.{t}", _table_exists(conn, s, t),
                                  "存在" if _table_exists(conn, s, t) else "缺失"))

        # ── 6. P5 FK 约束存在性 ──────────────────────────────
        print("\n── P5 FK 加固约束存在性 ──")
        p5_fks = [
            ("experiment", "test_tasks", "fk_test_tasks_method"),
            ("experiment", "experiment_result_records", "fk_results_method"),
            ("experiment", "experiment_result_records", "fk_results_property"),
            ("experiment", "experiment_result_records", "fk_results_unit"),
            ("industrialization", "raw_materials", "fk_raw_materials_category"),
            ("experiment", "equipment", "fk_equipment_category"),
        ]
        for s, t, c in p5_fks:
            exists = _fk_exists(conn, s, t, c)
            results.append(_check(f"FK {c} on {s}.{t}", exists,
                                  "已加固" if exists else "未生效"))

        # ── 7. P5 FK 引用完整性（孤立记录数） ──────────────────────────────
        print("\n── P5 FK 引用完整性（孤立记录应为 0） ──")
        orphan_checks = [
            ("experiment", "test_tasks", "test_method",
             "mdm", "test_methods", "method_id"),
            ("experiment", "experiment_result_records", "test_method",
             "mdm", "test_methods", "method_id"),
            ("experiment", "experiment_result_records", "property_name",
             "mdm", "properties", "property_id"),
            ("experiment", "experiment_result_records", "unit",
             "mdm", "units", "unit_code"),
            ("industrialization", "raw_materials", "category",
             "mdm", "classifications", "code"),
            ("experiment", "equipment", "category",
             "mdm", "classifications", "code"),
        ]
        for schema, table, col, ref_s, ref_t, ref_c in orphan_checks:
            if not _table_exists(conn, schema, table):
                results.append(_check(f"孤立记录 {schema}.{table}.{col}",
                                      False, "源表不存在，跳过"))
                continue
            n = _count_orphans(conn, schema, table, col, ref_s, ref_t, ref_c)
            results.append(_check(f"孤立记录 {schema}.{table}.{col}", n == 0,
                                  f"孤立 {n} 条" if n > 0 else "无孤立"))

        # ── 8. P5 新表 FK 约束存在性 ──────────────────────────────
        print("\n── P5 新表 FK 约束存在性 ──")
        p5_new_fks = [
            ("mdm", "documents", "fk_documents_category"),
            ("mdm", "document_versions", "fk_doc_versions_document"),
            ("experiment", "order_version_snapshots", "fk_order_snap_order"),
        ]
        for s, t, c in p5_new_fks:
            exists = _fk_exists(conn, s, t, c)
            results.append(_check(f"FK {c} on {s}.{t}", exists,
                                  "已生效" if exists else "未生效"))

        # ── 9. P1-P4 内部 FK 约束抽样检查 ──────────────────────────────
        print("\n── P1-P4 内部 FK 约束抽样 ──")
        p1_p4_fks = [
            ("mdm", "classifications", "fk_class_parent"),
            ("mdm", "unit_conversions", "fk_conv_from"),
            ("mdm", "unit_conversions", "fk_conv_to"),
            ("mdm", "locations", "fk_locations_parent"),
            ("mdm", "containers", "fk_containers_unit"),
            ("mdm", "equipment_templates", "fk_eq_templates_category"),
            ("mdm", "equipment_templates", "fk_eq_templates_location"),
            ("mdm", "equipment_capabilities", "fk_eq_caps_unit"),
            ("mdm", "equipment_template_capabilities", "fk_etc_template"),
            ("mdm", "equipment_template_capabilities", "fk_etc_capability"),
            ("mdm", "material_categories", "fk_mat_cat_code"),
            ("mdm", "material_categories", "fk_mat_cat_unit"),
            ("mdm", "test_items", "fk_items_property"),
            ("mdm", "test_items", "fk_items_method"),
            ("mdm", "specifications", "fk_specs_item"),
            ("mdm", "process_parameters", "fk_proc_params_unit"),
            ("mdm", "process_route_steps", "fk_prs_route"),
            ("mdm", "process_route_steps", "fk_prs_step"),
            ("mdm", "process_step_parameters", "fk_psp_step"),
            ("mdm", "process_step_parameters", "fk_psp_param"),
            ("mdm", "process_step_equipment_templates", "fk_pset_step"),
            ("mdm", "process_step_equipment_templates", "fk_pset_template"),
        ]
        for s, t, c in p1_p4_fks:
            exists = _fk_exists(conn, s, t, c)
            results.append(_check(f"FK {c}", exists,
                                  "已生效" if exists else "未生效"))

    # ── 汇总 ──────────────────────────────────────────────
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n=== 汇总：{passed}/{total} 通过 ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
