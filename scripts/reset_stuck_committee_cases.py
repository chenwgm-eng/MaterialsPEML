"""Reset stuck `external_evidence` committee cases from `pending` to `failed`.

Background (审查意见V5.md P0-2 / Task 2.6):
    39 条 external_evidence 委员会案件长期卡在 `pending` 状态，无法推进也无法重新触发。
    本脚本作为 P0 止血手段，将这些案件标记为 `failed` 并追加 `case_failed` 事件，
    以便用户在前端能看到失败状态并重新触发评估。

Side effects:
    - `data/committee.db`:`committee_cases` 的 `status` 列更新为 `failed`，
      `updated_at` 刷新为当前 UTC 时间。
    - `data/committee_events.db`:`committee_events` 追加 `case_failed` 事件，
      `data_json` 包含 `{"reason": "Manually reset due to stuck pending state (P0-2 fix)"}`。

Usage:
    python scripts/reset_stuck_committee_cases.py
    python scripts/reset_stuck_committee_cases.py --committee-db data/committee.db \\
        --events-db data/committee_events.db --dry-run
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

RESET_REASON = "Manually reset due to stuck pending state (P0-2 fix)"
TARGET_COMMITTEE_TYPE = "external_evidence"
TARGET_STATUS = "pending"
NEW_STATUS = "failed"
EVENT_TYPE = "case_failed"


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset stuck external_evidence committee cases (P0-2 stop-gap).",
    )
    parser.add_argument(
        "--committee-db",
        default="data/committee.db",
        help="Path to committee.db (default: data/committee.db).",
    )
    parser.add_argument(
        "--events-db",
        default="data/committee_events.db",
        help="Path to committee_events.db (default: data/committee_events.db).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would be reset; do not modify any data.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def list_stuck_cases(conn: sqlite3.Connection) -> list[str]:
    """返回所有 external_evidence + pending 案件的 case_id 列表。"""
    cursor = conn.execute(
        "SELECT case_id FROM committee_cases "
        "WHERE committee_type = ? AND status = ? "
        "ORDER BY created_at",
        (TARGET_COMMITTEE_TYPE, TARGET_STATUS),
    )
    return [row[0] for row in cursor.fetchall()]


def reset_case_status(conn: sqlite3.Connection, case_id: str, now_iso: str) -> None:
    """将单个案件的 status 更新为 failed，并刷新 updated_at。"""
    conn.execute(
        "UPDATE committee_cases SET status = ?, updated_at = ? WHERE case_id = ?",
        (NEW_STATUS, now_iso, case_id),
    )


def append_case_failed_event(
    conn: sqlite3.Connection,
    case_id: str,
    now_iso: str,
) -> None:
    """向 committee_events 表追加 case_failed 事件。"""
    conn.execute(
        "INSERT INTO committee_events (case_id, event_type, data_json, timestamp) "
        "VALUES (?, ?, ?, ?)",
        (case_id, EVENT_TYPE, json.dumps({"reason": RESET_REASON}), now_iso),
    )


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    committee_db = Path(args.committee_db)
    events_db = Path(args.events_db)

    if not committee_db.exists():
        print(f"[error] committee db not found: {committee_db}", file=sys.stderr)
        return 2
    if not events_db.exists():
        print(f"[error] events db not found: {events_db}", file=sys.stderr)
        return 2

    # 1. 查询卡死的案件（只读连接）
    committee_conn = sqlite3.connect(str(committee_db))
    try:
        stuck_cases = list_stuck_cases(committee_conn)
    finally:
        committee_conn.close()

    print(f"[scan] found {len(stuck_cases)} stuck {TARGET_COMMITTEE_TYPE} "
          f"case(s) in status='{TARGET_STATUS}'")

    if not stuck_cases:
        print("[done] nothing to reset.")
        return 0

    if args.dry_run:
        print("[dry-run] would reset the following cases:")
        for case_id in stuck_cases:
            print(f"  - {case_id}")
        return 0

    # 2. 重置状态 + 追加事件（事务保护）
    events_conn = sqlite3.connect(str(events_db))
    committee_conn = sqlite3.connect(str(committee_db))
    affected = 0
    try:
        for case_id in stuck_cases:
            now_iso = datetime.now(timezone.utc).isoformat()
            with committee_conn:
                reset_case_status(committee_conn, case_id, now_iso)
            with events_conn:
                append_case_failed_event(events_conn, case_id, now_iso)
            affected += 1
            print(f"  [reset] {case_id} -> {NEW_STATUS} (event: {EVENT_TYPE})")
    finally:
        committee_conn.close()
        events_conn.close()

    print(f"\n[done] reset {affected} case(s).")
    print(f"       reason: {RESET_REASON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
