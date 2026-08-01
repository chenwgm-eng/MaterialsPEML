"""Scan SQLite .db files for text fields containing `?` corruption patterns.

Background (审查意见V5.md P0-3):
    Historical writes to samples.db / equipment.db stored Chinese text fields
    (storage_location, storage_condition, notes, operator, equipment name,
    responsible_person) with inconsistent encodings. The mojibake has been
    baked into `?` characters and cannot be recovered in place. This script
    is the P0 stop-gap: it ONLY scans and reports, leaving the actual repair
    to the PostgreSQL migration phase (Task 10).

Usage:
    python scripts/scan_db_corruption.py --db-dir data \\
        --output scripts/db_corruption_report.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

# 连续 2+ 个 `?` 字符视为乱码模式（参考 Task 3.1 规格说明）
CORRUPTION_PATTERN = re.compile(r"\?{2,}")

# 默认扫描目标（spec 列出的 6 个 .db 文件；materials.db 当前不存在，
# 脚本会以 "file_not_found" 记录并跳过，不视为错误）
DEFAULT_DB_FILES = [
    "samples.db",
    "equipment.db",
    "experiments.db",
    "research.db",
    "committee.db",
    "materials.db",
]

REPORT_COLUMNS = [
    "db_file",
    "table_name",
    "record_id",
    "column_name",
    "corrupted_value",
    "suggested_action",
]


def iter_text_columns(conn: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    """返回 [(col_name, pk_col_name)] 列表，仅包含 TEXT 列。

    pk_col_name 为该表的主键列名（通过 PRAGMA table_info 中 pk=1 获取），
    若表无主键则回退到 'rowid'。
    """
    cursor = conn.execute(f"PRAGMA table_info({table})")
    cols = cursor.fetchall()
    pk_col = next((c[1] for c in cols if c[5] == 1), None) or "rowid"
    text_cols = [c[1] for c in cols if (c[2] or "").upper() == "TEXT"]
    return [(col, pk_col) for col in text_cols]


def scan_table(
    conn: sqlite3.Connection,
    table: str,
    db_file: str,
    writer: csv.writer,
) -> tuple[int, set[str]]:
    """扫描单个表的所有 TEXT 列，写入受影响记录。

    返回 (受影响记录数, 受影响字段名集合)。
    """
    affected = 0
    affected_cols: set[str] = set()
    for col, pk_col in iter_text_columns(conn, table):
        # 使用 rowid 兜底以便无主键表也能定位记录
        select_sql = (
            f"SELECT {pk_col}, {col} FROM {table}"
            if pk_col != "rowid"
            else f"SELECT rowid, {col} FROM {table}"
        )
        try:
            cursor = conn.execute(select_sql)
        except sqlite3.DatabaseError as exc:
            print(f"  [warn] cannot read {db_file}.{table}.{col}: {exc}", file=sys.stderr)
            continue
        col_has_corruption = False
        for row in cursor.fetchall():
            record_id, value = row[0], row[1]
            if not isinstance(value, str):
                continue
            if CORRUPTION_PATTERN.search(value):
                affected += 1
                col_has_corruption = True
                writer.writerow([
                    db_file,
                    table,
                    record_id,
                    col,
                    value,
                    "mark_corrupted_pending_pg_migration",
                ])
        if col_has_corruption:
            affected_cols.add(f"{table}.{col}")
    return affected, affected_cols


def scan_db_file(db_path: Path, writer: csv.writer) -> tuple[int, set[str]]:
    """扫描单个 .db 文件。返回 (受影响记录数, 受影响字段集合)。"""
    db_file = db_path.name
    if not db_path.exists():
        # spec 列出的文件可能尚不存在（如 materials.db），记录占位行便于审计
        writer.writerow([
            db_file,
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "file_not_found_skipped",
        ])
        print(f"[skip] {db_file} not found")
        return 0, set()

    print(f"[scan] {db_path}")
    affected_total = 0
    affected_columns: set[str] = set()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        for table in tables:
            affected, cols = scan_table(conn, table, db_file, writer)
            affected_total += affected
            affected_columns.update(cols)
    finally:
        conn.close()
    print(f"  -> {db_file}: {affected_total} corrupted record(s)")
    return affected_total, affected_columns


def write_summary(summary_path: Path, summaries: list[dict]) -> None:
    """写入汇总 CSV：每个 .db 文件受影响的记录数、字段数。"""
    with summary_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["db_file", "affected_records", "affected_columns"])
        for row in summaries:
            writer.writerow([
                row["db_file"],
                row["affected_records"],
                len(row["affected_columns"]),
            ])


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan SQLite .db files for `?` mojibake corruption (P0-3 stop-gap).",
    )
    parser.add_argument(
        "--db-dir",
        default="data",
        help="Directory containing the .db files to scan (default: data).",
    )
    parser.add_argument(
        "--output",
        default="scripts/db_corruption_report.csv",
        help="Output CSV report path (default: scripts/db_corruption_report.csv).",
    )
    parser.add_argument(
        "--summary",
        default="scripts/db_corruption_summary.csv",
        help="Optional summary CSV path (per-db totals).",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    db_dir = Path(args.db_dir)
    output_path = Path(args.output)
    summary_path = Path(args.summary)

    if not db_dir.is_dir():
        print(f"[error] db-dir does not exist: {db_dir}", file=sys.stderr)
        return 2

    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    summaries: list[dict] = []
    total_records = 0

    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(REPORT_COLUMNS)
        for db_name in DEFAULT_DB_FILES:
            db_path = db_dir / db_name
            affected, cols = scan_db_file(db_path, writer)
            summaries.append({
                "db_file": db_name,
                "affected_records": affected,
                "affected_columns": cols,
            })
            total_records += affected

    write_summary(summary_path, summaries)

    print("\n========== SCAN SUMMARY ==========")
    for row in summaries:
        print(
            f"  {row['db_file']:<20} "
            f"records={row['affected_records']:<6} "
            f"columns={len(row['affected_columns'])}"
        )
    print(f"  {'TOTAL':<20} records={total_records}")
    print(f"\nReport:   {output_path}")
    print(f"Summary:  {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
