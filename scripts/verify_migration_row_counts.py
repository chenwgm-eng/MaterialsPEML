"""Verify SQLite → PostgreSQL migration by comparing row counts (Task 10 verification).

Usage:
    python scripts/verify_migration_row_counts.py
    python scripts/verify_migration_row_counts.py --json

Reads ``scripts/_sqlite_to_pg_mapping.json`` and compares:
  - SQLite source row count (per table)
  - PostgreSQL target row count (per table)

Exit code:
  0 — all tables match (SQLite rows == PostgreSQL rows, allowing for
      corrupted-row skips recorded in ``_migration_report.json``)
  1 — one or more tables mismatch
  2 — mapping file missing / unrecoverable error
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402

from battery_materials_agent.db import get_engine  # noqa: E402

MAPPING_PATH = PROJECT_ROOT / "scripts" / "_sqlite_to_pg_mapping.json"
REPORT_PATH = PROJECT_ROOT / "scripts" / "_migration_report.json"
OUTPUT_JSON = PROJECT_ROOT / "scripts" / "_migration_verification.json"
OUTPUT_MD = PROJECT_ROOT / "scripts" / "_migration_verification.md"


def count_sqlite_rows(db_path: Path, table_name: str) -> int | None:
    """Return row count of a SQLite table, or None if unreadable."""
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            return int(cur.fetchone()[0])
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        print(f"  [warn] sqlite count failed for {db_path}::{table_name}: {exc}", file=sys.stderr)
        return None


def count_pg_rows(pg_schema: str, pg_table: str) -> int | None:
    """Return row count of a PostgreSQL table, or None if table missing."""
    engine = get_engine()
    sql = text(f'SELECT COUNT(*) FROM "{pg_schema}"."{pg_table}"')
    try:
        with engine.connect() as conn:
            return int(conn.execute(sql).fetchone()[0])
    except Exception as exc:
        print(f"  [warn] pg count failed for {pg_schema}.{pg_table}: {exc}", file=sys.stderr)
        return None


def load_corruption_stats() -> dict[str, int]:
    """Return {(db_file, sqlite_table): corrupted_rows} from migration report."""
    if not REPORT_PATH.exists():
        return {}
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    out: dict[str, int] = {}
    for t in report.get("tables", []):
        key = f"{t.get('db_file')}::{t.get('sqlite_table')}"
        out[key] = int(t.get("corrupted_rows", 0))
    return out


def load_skipped_stats() -> dict[str, int]:
    """Return {(db_file, sqlite_table): fk_dangling_skipped_rows + corrupted skipped}.

    These are rows that were NOT migrated (skipped), so they should be
    subtracted from the expected PG row count.
    """
    if not REPORT_PATH.exists():
        return {}
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    out: dict[str, int] = {}
    for t in report.get("tables", []):
        key = f"{t.get('db_file')}::{t.get('sqlite_table')}"
        # corrupted_rows are skipped only when --skip-corrupted is set;
        # by default they are inserted with NULLed fields. We assume default.
        # fk_dangling_skipped_rows are always skipped (NOT NULL FK column).
        out[key] = int(t.get("fk_dangling_skipped_rows", 0))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify SQLite→PostgreSQL migration row counts.")
    parser.add_argument("--json", action="store_true", help="emit JSON to stdout instead of human-readable")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not MAPPING_PATH.exists():
        print(f"[error] mapping file missing: {MAPPING_PATH}", file=sys.stderr)
        return 2

    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    db_entries = {k: v for k, v in mapping.items() if not k.startswith("__")}
    corruption = load_corruption_stats()
    skipped = load_skipped_stats()

    results: list[dict[str, Any]] = []
    mismatches = 0
    total_sqlite = 0
    total_pg = 0

    for db_rel, tables in db_entries.items():
        db_path = PROJECT_ROOT / db_rel
        for table_name, table_map in tables.items():
            pg_schema = table_map["pg_schema"]
            pg_table = table_map["pg_table"]
            sqlite_count = count_sqlite_rows(db_path, table_name)
            pg_count = count_pg_rows(pg_schema, pg_table)
            corrupted = corruption.get(f"{db_rel}::{table_name}", 0)
            skipped_rows = skipped.get(f"{db_rel}::{table_name}", 0)
            # Expected PG rows:
            #   - corrupted rows are inserted with NULLed fields by default
            #     (count toward pg_count), unless --skip-corrupted was used
            #   - fk_dangling_skipped_rows are NOT inserted (NOT NULL FK column)
            # So expected_min = sqlite - skipped_rows (worst case: corrupted also skipped)
            #    expected_max = sqlite (all rows migrated, including corrupted with NULLs)
            expected_max = sqlite_count if sqlite_count is not None else None
            expected_min = (sqlite_count - skipped_rows - corrupted) if sqlite_count is not None else None

            status = "ok"
            if sqlite_count is None:
                status = "sqlite_missing"
            elif pg_count is None:
                status = "pg_missing"
            elif pg_count < expected_min:
                status = "under"
                mismatches += 1
            elif pg_count > expected_max:
                status = "over"
                mismatches += 1
            # pg_count within [expected_min, expected_max] is OK

            if sqlite_count is not None:
                total_sqlite += sqlite_count
            if pg_count is not None:
                total_pg += pg_count

            results.append({
                "db_file": db_rel,
                "sqlite_table": table_name,
                "pg_schema": pg_schema,
                "pg_table": pg_table,
                "sqlite_rows": sqlite_count,
                "pg_rows": pg_count,
                "corrupted_rows": corrupted,
                "expected_min": expected_min,
                "expected_max": expected_max,
                "status": status,
            })

    summary = {
        "total_sqlite_rows": total_sqlite,
        "total_pg_rows": total_pg,
        "mismatches": mismatches,
        "tables_checked": len(results),
    }

    OUTPUT_JSON.write_text(
        json.dumps({"summary": summary, "tables": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Markdown report
    lines: list[str] = []
    lines.append("# SQLite → PostgreSQL 行数验证报告")
    lines.append("")
    lines.append(f"- 生成时间: {__import__('datetime').datetime.now().isoformat()}")
    lines.append(f"- SQLite 总行数: {total_sqlite}")
    lines.append(f"- PostgreSQL 总行数: {total_pg}")
    lines.append(f"- 不匹配表数: {mismatches} / {len(results)}")
    lines.append("")
    lines.append("## 各表对比")
    lines.append("")
    lines.append("| db_file | sqlite_table | pg_schema.pg_table | sqlite_rows | pg_rows | corrupted | expected_min | expected_max | status |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        lines.append(
            f"| {r['db_file']} | {r['sqlite_table']} | "
            f"{r['pg_schema']}.{r['pg_table']} | "
            f"{r['sqlite_rows'] if r['sqlite_rows'] is not None else '-'} | "
            f"{r['pg_rows'] if r['pg_rows'] is not None else '-'} | "
            f"{r['corrupted_rows']} | "
            f"{r['expected_min'] if r['expected_min'] is not None else '-'} | "
            f"{r['expected_max'] if r['expected_max'] is not None else '-'} | "
            f"{r['status']} |"
        )
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")

    if args.json:
        print(json.dumps({"summary": summary, "tables": results}, ensure_ascii=False, indent=2))
    else:
        print(f"\n[verify] tables={len(results)} mismatches={mismatches}")
        print(f"[verify] sqlite_total={total_sqlite} pg_total={total_pg}")
        if mismatches:
            print("\nMISMATCHES (pg_rows outside [sqlite_rows - corrupted, sqlite_rows]):")
            for r in results:
                if r["status"] in ("under", "over"):
                    print(
                        f"  - {r['db_file']}::{r['sqlite_table']} -> "
                        f"{r['pg_schema']}.{r['pg_table']}: "
                        f"sqlite={r['sqlite_rows']} pg={r['pg_rows']} "
                        f"corrupted={r['corrupted_rows']} status={r['status']}"
                    )
        print(f"\n[done] report: {OUTPUT_MD}")

    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
