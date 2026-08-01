"""一次性清理 ECML 运行历史中的脏数据。

清理规则：
1. 删除同 target + 同时间戳(精确到秒)的重复记录，保留最新一条；
2. 对超过 1 小时未更新且未完成的运行，自动标记为 timeout；
3. 对迭代次数 >= max_iterations 但 is_complete=0 的运行补终态 completed。

用法：
    python scripts/cleanup_ecml_runs.py            # 预览（dry-run）
    python scripts/cleanup_ecml_runs.py --apply    # 实际执行
"""

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "ecml_states.db"
STALE_TIMEOUT_SECONDS = 3600  # 1 小时


def main():
    parser = argparse.ArgumentParser(description="清理 ECML 运行历史脏数据")
    parser.add_argument("--apply", action="store_true", help="实际执行清理，否则仅预览")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"数据库不存在: {DB_PATH}")
        return

    print(f"数据库: {DB_PATH}")
    print(f"模式: {'应用' if args.apply else '预览(dry-run)'}\n")

    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")

        # 统计清理前状态
        total = conn.execute("SELECT COUNT(*) FROM ecml_runs").fetchone()[0]
        index_total = conn.execute("SELECT COUNT(*) FROM ecml_runs_index").fetchone()[0]
        running = conn.execute(
            "SELECT COUNT(DISTINCT run_id) FROM ecml_runs_index WHERE is_complete=0 AND (run_status='running' OR run_status IS NULL)"
        ).fetchone()[0]
        print(f"清理前: ecml_runs {total} 条, ecml_runs_index {index_total} 条, 其中 {running} 个 run_id 进行中\n")

        # 0. 清理 ecml_runs_index 中的重复 run_id（保留每个 run_id 最新一条）
        print("=== ecml_runs_index 重复 run_id 清理 ===")
        dup_index = conn.execute(
            """SELECT run_id, COUNT(*) AS cnt FROM ecml_runs_index
               GROUP BY run_id HAVING cnt > 1 ORDER BY cnt DESC"""
        ).fetchall()
        if not dup_index:
            print("无重复 run_id\n")
        else:
            total_dup = sum(c - 1 for _, c in dup_index)
            print(f"  发现 {len(dup_index)} 个 run_id 有重复，共 {total_dup} 条冗余记录")
            if args.apply:
                # 保留每个 run_id created_at 最大的一条
                conn.execute(
                    """DELETE FROM ecml_runs_index WHERE rowid NOT IN (
                           SELECT MAX(rowid) FROM ecml_runs_index GROUP BY run_id
                       )"""
                )
                # 同时清理 ecml_runs_index 中不存在于 ecml_runs 的孤儿记录
                conn.execute(
                    """DELETE FROM ecml_runs_index
                       WHERE run_id NOT IN (SELECT run_id FROM ecml_runs)"""
                )
                remaining = conn.execute("SELECT COUNT(*) FROM ecml_runs_index").fetchone()[0]
                print(f"  已清理，剩余 {remaining} 条\n")
            else:
                print("  (预览模式，未执行清理)\n")

        # 1. 删除重复记录（同 target + 同 updated_at 精确到秒）
        print("=== 重复记录检测（同 target + 同 updated_at 秒级）===")
        duplicates = conn.execute(
            """SELECT target, substr(updated_at, 1, 19) AS ts, COUNT(*) AS cnt
               FROM ecml_runs
               GROUP BY target, ts
               HAVING cnt > 1
               ORDER BY cnt DESC"""
        ).fetchall()
        if not duplicates:
            print("无重复记录\n")
        else:
            for target, ts, cnt in duplicates:
                print(f"  target={target}  时间戳={ts}  重复 {cnt} 条")
                if args.apply:
                    # 保留最新(updated_at 最大)的一条，删除其余
                    keep_ids = conn.execute(
                        """SELECT run_id FROM ecml_runs
                           WHERE target=? AND substr(updated_at, 1, 19)=?
                           ORDER BY updated_at DESC LIMIT 1""",
                        (target, ts),
                    ).fetchall()
                    keep_id = keep_ids[0][0] if keep_ids else ""
                    cur = conn.execute(
                        """DELETE FROM ecml_runs
                           WHERE target=? AND substr(updated_at, 1, 19)=? AND run_id<>?""",
                        (target, ts, keep_id),
                    )
                    print(f"    已删除 {cur.rowcount} 条，保留 {keep_id}\n")
                else:
                    print("    (预览模式，未执行删除)\n")

        # 2. 标记僵尸运行（未完成 + 超过 1 小时未更新）
        print("=== 僵尸运行检测（未完成 + 超过 1 小时未更新）===")
        now_dt = datetime.now(timezone.utc)
        rows = conn.execute(
            """SELECT r.run_id, r.target, r.updated_at
               FROM ecml_runs r
               LEFT JOIN ecml_runs_index i ON r.run_id = i.run_id
               WHERE i.is_complete=0 AND (i.run_status='running' OR i.run_status IS NULL)"""
        ).fetchall()
        stale_count = 0
        for run_id, target, updated_at in rows:
            try:
                updated_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                age = (now_dt - updated_dt).total_seconds()
            except (ValueError, AttributeError):
                continue
            if age > STALE_TIMEOUT_SECONDS:
                stale_count += 1
                print(f"  {run_id}  target={target}  更新于 {updated_at}  超时 {int(age/3600)}h")
                if args.apply:
                    conn.execute(
                        "UPDATE ecml_runs_index SET run_status='timeout' WHERE run_id=?",
                        (run_id,),
                    )
        print(f"共 {stale_count} 条僵尸运行{' 已标记为 timeout' if args.apply and stale_count else ''}\n")

        # 3. 补全已跑完迭代但未置完成的运行
        print("=== 终态补全（迭代已用尽但 is_complete=0）===")
        pending = conn.execute(
            """SELECT i.run_id, i.iteration, r.target, MAX(s.max_iterations) AS max_iter
               FROM ecml_runs_index i
               JOIN ecml_runs r ON i.run_id = r.run_id
               LEFT JOIN (
                   SELECT run_id,
                          COALESCE(json_extract(state_json, '$.max_iterations'), 3) AS max_iterations
                   FROM ecml_runs
               ) s ON s.run_id = i.run_id
               WHERE i.is_complete=0 AND i.iteration >= COALESCE(s.max_iterations, 3)
               GROUP BY i.run_id"""
        ).fetchall()
        if not pending:
            print("无需补全\n")
        else:
            for run_id, iteration, target, max_iter in pending:
                print(f"  {run_id}  target={target}  迭代 {iteration}/{max_iter}  补全为 completed")
                if args.apply:
                    conn.execute(
                        "UPDATE ecml_runs_index SET is_complete=1, run_status='completed' WHERE run_id=?",
                        (run_id,),
                    )
            print()

        # 统计清理后状态
        total_after = conn.execute("SELECT COUNT(*) FROM ecml_runs").fetchone()[0]
        running_after = conn.execute(
            "SELECT COUNT(*) FROM ecml_runs_index WHERE is_complete=0 AND (run_status='running' OR run_status IS NULL)"
        ).fetchone()[0]
        print(f"清理后: 共 {total_after} 条运行，其中 {running_after} 条进行中")

        if not args.apply:
            print("\n(预览完成，如需实际执行请追加 --apply)")


if __name__ == "__main__":
    main()
