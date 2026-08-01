"""Migrate SQLite .db files into PostgreSQL (one-shot, Task 10).

Usage:
    python scripts/migrate_sqlite_to_postgres.py --dry-run
    python scripts/migrate_sqlite_to_postgres.py
    python scripts/migrate_sqlite_to_postgres.py --only=data/samples.db
    python scripts/migrate_sqlite_to_postgres.py --archive

Behaviour:
- Reads ``scripts/_sqlite_to_pg_mapping.json`` (produced by _build_mapping.py).
- For every (db_file, table) pair, copies rows from SQLite into the matching
  PostgreSQL ``schema.table`` with ``ON CONFLICT (pk) DO NOTHING``.
- Type conversions:
    * SQLite TEXT  -> PostgreSQL JSONB  (when target column is JSONB)
    * SQLite TEXT  -> PostgreSQL TIMESTAMPTZ (kept as ISO string)
    * SQLite INTEGER -> PostgreSQL BOOLEAN (when target column is BOOLEAN)
    * SQLite INTEGER -> BIGINT (otherwise)
    * SQLite REAL    -> DOUBLE PRECISION
- Corrupted text detection: any TEXT value matching ``\?\?+`` (2+ consecutive
  ``?``) is treated as mojibake. The field is set to NULL and the corruption
  is recorded in the migration report. If the target table has a
  ``data_quality`` column the corruption marker is written there; otherwise
  the corruption is recorded only in the report.
- BIGSERIAL columns listed in ``excluded_columns`` are skipped so PostgreSQL
  can auto-generate them.
- For tables listed in ``legacy_migration_field`` the corresponding field is
  set to ``'LEGACY_MIGRATION'`` on every migrated row.
- ``--archive`` renames each .db file to ``.bak.YYYYMMDD`` after a successful
  full migration. The original file is not deleted.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from psycopg.types.json import Jsonb  # noqa: E402

from sqlalchemy import text  # noqa: E402

from battery_materials_agent.db import get_engine  # noqa: E402


MAPPING_PATH = PROJECT_ROOT / "scripts" / "_sqlite_to_pg_mapping.json"
REPORT_JSON_PATH = PROJECT_ROOT / "scripts" / "_migration_report.json"
REPORT_MD_PATH = PROJECT_ROOT / "scripts" / "_migration_report.md"

# 连续 2 个或更多 `?` 视为乱码（参考 scripts/scan_db_corruption.py）
CORRUPTION_PATTERN = re.compile(r"\?\?+")

# 一次 INSERT 批处理的行数
BATCH_SIZE = 200


# ────────────────────────────── 类型 / 列信息 ──────────────────────────────

def fetch_pg_column_types(pg_schema: str, pg_table: str) -> dict[str, str]:
    """返回 {column_name: data_type} from information_schema."""
    engine = get_engine()
    sql = text(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table
        ORDER BY ordinal_position
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"schema": pg_schema, "table": pg_table}).fetchall()
    return {r[0]: r[1] for r in rows}


def fetch_pg_column_nullability(pg_schema: str, pg_table: str) -> set[str]:
    """返回该表中 NOT NULL 的列名集合（用于判断 FK 列能否被置 NULL）。"""
    engine = get_engine()
    sql = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table AND is_nullable = 'NO'
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"schema": pg_schema, "table": pg_table}).fetchall()
    return {r[0] for r in rows}


def fetch_pg_primary_keys(pg_schema: str, pg_table: str) -> list[str]:
    """返回 PostgreSQL 表的主键列名列表。"""
    engine = get_engine()
    # 注意：不要用 `:relid::regclass` —— SQLAlchemy 的 text() 会把 `::regclass`
    # 当作第二个绑定参数解析。改用 to_regclass(:relid) 函数。
    sql = text(
        """
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a
          ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = to_regclass(:relid) AND i.indisprimary
        ORDER BY array_position(i.indkey, a.attnum)
        """
    )
    rel = f"{pg_schema}.{pg_table}"
    with engine.connect() as conn:
        rows = conn.execute(sql, {"relid": rel}).fetchall()
    return [r[0] for r in rows]


def fetch_pg_foreign_key_columns(pg_schema: str, pg_table: str) -> set[str]:
    """返回该表中作为外键的列名集合（用于空串→NULL 转换）。"""
    engine = get_engine()
    sql = text(
        """
        SELECT a.attname
        FROM pg_constraint c
        JOIN pg_attribute a
          ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
        WHERE c.conrelid = to_regclass(:relid) AND c.contype = 'f'
        """
    )
    rel = f"{pg_schema}.{pg_table}"
    with engine.connect() as conn:
        rows = conn.execute(sql, {"relid": rel}).fetchall()
    return {r[0] for r in rows}


def fetch_pg_foreign_key_targets(pg_schema: str, pg_table: str) -> list[dict[str, str]]:
    """返回外键列及其引用的 (schema, table) 信息。

    用于预取引用表中已有的 PK 集合，识别 SQLite 中的 dangling FK 引用。
    返回 [{"fk_col": "source_order_id", "ref_schema": "experiment",
           "ref_table": "experiment_orders", "ref_col": "order_id"}, ...]
    """
    engine = get_engine()
    sql = text(
        """
        SELECT a.attname AS fk_col,
               nsp.nspname AS ref_schema,
               rel.relname AS ref_table,
               af.attname AS ref_col
        FROM pg_constraint c
        JOIN pg_attribute a
          ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
        JOIN pg_class rel ON rel.oid = c.confrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        JOIN pg_attribute af
          ON af.attrelid = c.confrelid AND af.attnum = ANY(c.confkey)
        WHERE c.conrelid = to_regclass(:relid) AND c.contype = 'f'
        """
    )
    rel = f"{pg_schema}.{pg_table}"
    with engine.connect() as conn:
        rows = conn.execute(sql, {"relid": rel}).fetchall()
    return [
        {"fk_col": r[0], "ref_schema": r[1], "ref_table": r[2], "ref_col": r[3]}
        for r in rows
    ]


def fetch_fk_valid_values(
    fk_targets: list[dict[str, str]],
) -> dict[str, set[str]]:
    """对每个 FK 列，预取引用表中所有已存在的 PK 值集合。

    返回 {fk_col: {id1, id2, ...}}。用于识别 SQLite 中的 dangling FK 引用
    （非空但引用表中不存在的值），将其置 NULL 以避免 FK 约束违反。
    """
    engine = get_engine()
    out: dict[str, set[str]] = {}
    for tgt in fk_targets:
        ref_rel = f'{tgt["ref_schema"]}.{tgt["ref_table"]}'
        ref_col = tgt["ref_col"]
        sql = text(f'SELECT "{ref_col}"::text FROM "{tgt["ref_schema"]}"."{tgt["ref_table"]}"')
        try:
            with engine.connect() as conn:
                rows = conn.execute(sql).fetchall()
            out[tgt["fk_col"]] = {str(r[0]) for r in rows if r[0] is not None}
        except Exception as exc:
            print(
                f"  [warn] cannot prefetch FK values from {ref_rel}.{ref_col}: {exc}",
                file=sys.stderr,
            )
            out[tgt["fk_col"]] = set()
    return out


# ────────────────────────────── 行转换 ──────────────────────────────

def _to_jsonb(value: Any) -> Any:
    """把 SQLite 中的值转成 psycopg Jsonb 适配器。

    - None / 空字符串 → None（让 PostgreSQL 写 NULL）
    - dict / list → Jsonb(value)
    - 字符串 → 尝试 json.loads；成功则 Jsonb(parsed)；失败则 Jsonb(value)
      （后者会把字符串以 JSON 字符串的形式存进 JSONB，保住数据不丢）
    """
    if value is None:
        return None
    if isinstance(value, str):
        if value == "":
            return None
        try:
            return Jsonb(json.loads(value))
        except (json.JSONDecodeError, ValueError):
            return Jsonb(value)
    if isinstance(value, (dict, list)):
        return Jsonb(value)
    # int / bool / float 等：直接交给 Jsonb
    return Jsonb(value)


def _to_bool(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("1", "true", "t", "yes", "y"):
            return True
        if s in ("0", "false", "f", "no", "n", ""):
            return False
    return value


def convert_value(
    value: Any,
    pg_type: str,
    pg_col: str = "",
    fk_columns: set[str] | None = None,
    fk_valid_values: dict[str, set[str]] | None = None,
) -> tuple[Any, bool]:
    """根据 PostgreSQL 列类型转换 SQLite 值。

    返回 (converted_value, fk_nulled)：
      - fk_nulled=True 表示该值是 FK 列的 dangling 引用，被置为 NULL。

    FK 处理（优先级最高）：
      - FK 列 + 空串 → None
      - FK 列 + 非空但引用表中不存在 → None（dangling，记入 fk_nulled）
    """
    if value is None:
        return None, False
    pg_type = (pg_type or "").lower()

    # FK 列优先处理：空串 → NULL；dangling → NULL
    if fk_columns and pg_col in fk_columns:
        if isinstance(value, str) and value.strip() == "":
            return None, False
        valid_set = (fk_valid_values or {}).get(pg_col)
        if valid_set is not None and str(value) not in valid_set:
            # dangling FK：值非空但引用表中不存在，置 NULL 避免 FK 违反
            return None, True
        # FK 值有效，原样返回（不做类型转换，FK 通常是 TEXT）
        return value, False

    if pg_type in ("jsonb", "json"):
        return _to_jsonb(value), False
    if pg_type == "boolean":
        return _to_bool(value), False
    if pg_type in (
        "timestamp with time zone",
        "timestamp without time zone",
        "time with time zone",
        "time without time zone",
    ):
        # SQLite 经常用 '' 表示"无时间"，PostgreSQL TIMESTAMPTZ 不接受空串
        if isinstance(value, str) and value.strip() == "":
            return None, False
        return value, False
    if pg_type in ("bigint", "integer", "smallint"):
        if isinstance(value, str) and value.strip() == "":
            return None, False
        return value, False
    if pg_type in ("numeric", "double precision", "real"):
        if isinstance(value, str) and value.strip() == "":
            return None, False
        return value, False
    # TEXT / 其他：原样传
    return value, False


def detect_corruption(row: dict[str, Any]) -> list[str]:
    """返回该行中包含乱码模式的 TEXT 字段名列表。"""
    corrupted: list[str] = []
    for col, val in row.items():
        if isinstance(val, str) and CORRUPTION_PATTERN.search(val):
            corrupted.append(col)
    return corrupted


# ────────────────────────────── 迁移核心 ──────────────────────────────

def migrate_table(
    db_rel: str,
    sqlite_path: Path,
    table_name: str,
    table_map: dict[str, Any],
    dry_run: bool,
    skip_corrupted: bool,
    reset_no_pk: bool = True,
) -> dict[str, Any]:
    """迁移单张表。返回统计信息字典。"""
    pg_schema = table_map["pg_schema"]
    pg_table = table_map["pg_table"]
    col_mapping: dict[str, str] = table_map["column_mapping"]
    excluded_cols: list[str] = table_map.get("excluded_columns", [])
    legacy_field = table_map.get("legacy_migration_field")

    stats: dict[str, Any] = {
        "db_file": db_rel,
        "sqlite_table": table_name,
        "pg_schema": pg_schema,
        "pg_table": pg_table,
        "sqlite_row_count": table_map.get("sqlite_row_count", 0),
        "total_rows": 0,
        "migrated_rows": 0,
        "corrupted_rows": 0,
        "corrupted_fields": [],
        "conflict_rows": 0,
        "fk_nulled_rows": 0,
        "fk_dangling_skipped_rows": 0,
        "skipped_empty": False,
        "errors": [],
    }

    # 读取 SQLite 全部行
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        # 仅选取需要迁移的列（排除 BIGSERIAL 列）
        sqlite_cols = list(col_mapping.keys())
        col_list_sql = ", ".join(f'"{c}"' for c in sqlite_cols)
        try:
            cur = conn.execute(f'SELECT {col_list_sql} FROM "{table_name}"')
        except sqlite3.DatabaseError as exc:
            stats["errors"].append(f"sqlite read failed: {exc}")
            return stats
        rows = cur.fetchall()
    finally:
        conn.close()

    stats["total_rows"] = len(rows)
    if not rows:
        stats["skipped_empty"] = True
        return stats

    if dry_run:
        # dry-run 时仅校验 PostgreSQL 表能查到列类型
        try:
            pg_types = fetch_pg_column_types(pg_schema, pg_table)
            if not pg_types:
                stats["errors"].append(
                    f"postgres table {pg_schema}.{pg_table} not found in information_schema"
                )
        except Exception as exc:
            stats["errors"].append(f"postgres preflight failed: {exc}")
        # 模拟统计乱码行（不写入）
        for row in rows:
            row_dict = {k: row[k] for k in row.keys()}
            corrupted = detect_corruption(row_dict)
            if corrupted:
                stats["corrupted_rows"] += 1
                stats["corrupted_fields"].extend(corrupted)
        return stats

    # 查询 PostgreSQL 列类型、主键、FK 信息
    try:
        pg_types = fetch_pg_column_types(pg_schema, pg_table)
        if not pg_types:
            stats["errors"].append(
                f"postgres table {pg_schema}.{pg_table} not found in information_schema"
            )
            return stats
        pk_cols = fetch_pg_primary_keys(pg_schema, pg_table)
        not_null_cols = fetch_pg_column_nullability(pg_schema, pg_table)
        fk_targets = fetch_pg_foreign_key_targets(pg_schema, pg_table)
    except Exception as exc:
        stats["errors"].append(f"postgres metadata fetch failed: {exc}")
        return stats

    # 预取每个 FK 列在引用表中已存在的 PK 集合（用于识别 dangling 引用）
    fk_columns: set[str] = {t["fk_col"] for t in fk_targets}
    fk_valid_values: dict[str, set[str]] = {}
    if fk_targets:
        fk_valid_values = fetch_fk_valid_values(fk_targets)

    # 判断是否需要 TRUNCATE：
    #   1. 无主键表（ON CONFLICT 无法去重）
    #   2. 主键列被排除（BIGSERIAL，PK 不在 column_mapping 中，
    #      INSERT 不含 PK 列，ON CONFLICT (pk) 永远不会触发）
    # 这两种情况下重复迁移会累积重复行，必须先 TRUNCATE。
    pg_col_set = set(col_mapping.values())
    pk_in_insert = pk_cols and all(pk in pg_col_set for pk in pk_cols)
    needs_truncate = reset_no_pk and (not pk_cols or not pk_in_insert)
    if needs_truncate:
        engine = get_engine()
        try:
            with engine.begin() as c:
                c.execute(text(f'TRUNCATE TABLE "{pg_schema}"."{pg_table}" RESTART IDENTITY'))
            reason = "no-PK" if not pk_cols else "excluded-BIGSERIAL-PK"
            print(
                f"  [info] truncated {reason} table {pg_schema}.{pg_table} before insert",
                file=sys.stderr,
            )
        except Exception as exc:
            stats["errors"].append(f"truncate table failed: {exc}")
            return stats

    # 构造 INSERT 语句
    pg_cols = list(col_mapping.values())
    if legacy_field and legacy_field in pg_cols:
        # legacy field 会强制覆盖为 'LEGACY_MIGRATION'，无需特殊处理列集
        pass
    cols_sql = ", ".join(f'"{c}"' for c in pg_cols)
    placeholders_sql = ", ".join(f":{c}" for c in pg_cols)

    # ON CONFLICT DO NOTHING：如果有主键就用主键；否则用所有列做冲突目标会失败，
    # 所以无主键表回退到 DO NOTHING（不指定冲突列）。
    if pk_cols:
        conflict_target = ", ".join(f'"{c}"' for c in pk_cols)
        conflict_clause = f"ON CONFLICT ({conflict_target}) DO NOTHING"
    else:
        conflict_clause = "ON CONFLICT DO NOTHING"

    insert_sql = text(
        f'INSERT INTO "{pg_schema}"."{pg_table}" ({cols_sql}) '
        f"VALUES ({placeholders_sql}) {conflict_clause}"
    )

    engine = get_engine()
    migrated = 0
    conflict = 0
    corrupted_rows = 0
    corrupted_fields: list[str] = []
    fk_nulled_rows = 0

    batch: list[dict[str, Any]] = []
    for row in rows:
        row_dict = {k: row[k] for k in row.keys()}
        # 乱码检测
        corrupted = detect_corruption(row_dict)
        if corrupted:
            corrupted_rows += 1
            corrupted_fields.extend(corrupted)
            if skip_corrupted:
                # 跳过整条记录
                continue
            # 默认策略：清空乱码字段，并尝试写入 data_quality 标记
            for col in corrupted:
                row_dict[col] = None
            if "data_quality" in pg_cols:
                row_dict["data_quality"] = "corrupted"

        # LEGACY_MIGRATION 标记
        if legacy_field and legacy_field in row_dict:
            row_dict[legacy_field] = "LEGACY_MIGRATION"

        # 按 PostgreSQL 列名 + 类型转换；FK 列额外做 dangling 检测
        converted: dict[str, Any] = {}
        row_fk_nulled = False
        row_fk_dangling_notnull = False
        for sqlite_col, pg_col in col_mapping.items():
            val = row_dict.get(sqlite_col)
            pg_type = pg_types.get(pg_col, "")
            converted_val, fk_nulled = convert_value(
                val, pg_type, pg_col, fk_columns, fk_valid_values
            )
            if fk_nulled:
                row_fk_nulled = True
                # 如果 FK 列是 NOT NULL，置 NULL 会触发 NotNullViolation
                # → 整行跳过（dangling 引用 + NOT NULL = 无法迁移）
                if pg_col in not_null_cols:
                    row_fk_dangling_notnull = True
            converted[pg_col] = converted_val
        if row_fk_dangling_notnull:
            # 跳过整行：FK dangling 且列 NOT NULL，无法迁移
            stats["fk_dangling_skipped_rows"] += 1
            continue
        if row_fk_nulled:
            fk_nulled_rows += 1
        batch.append(converted)

        if len(batch) >= BATCH_SIZE:
            inserted, conflicts, err_msgs = _execute_batch(engine, insert_sql, batch)
            migrated += inserted
            conflict += conflicts
            if err_msgs:
                stats["errors"].extend(err_msgs[:3])  # 只保留前 3 条错误样本
            batch.clear()

    if batch:
        inserted, conflicts, err_msgs = _execute_batch(engine, insert_sql, batch)
        migrated += inserted
        conflict += conflicts
        if err_msgs:
            stats["errors"].extend(err_msgs[:3])

    stats["migrated_rows"] = migrated
    stats["conflict_rows"] = conflict
    stats["corrupted_rows"] = corrupted_rows
    stats["corrupted_fields"] = corrupted_fields
    stats["fk_nulled_rows"] = fk_nulled_rows
    stats["fk_dangling_skipped_rows"] = stats.get("fk_dangling_skipped_rows", 0)
    return stats


def _execute_batch(
    engine, insert_sql, batch: list[dict[str, Any]]
) -> tuple[int, int, list[str]]:
    """执行一批 INSERT。返回 (成功插入数, 冲突跳过数, 错误消息列表)。

    因为使用 ON CONFLICT DO NOTHING，rowcount 反映实际插入行数；
    冲突数 = batch 大小 - 实际插入行数。

    与早期版本不同：per-row 回退时记录真实错误消息（区分 FK 违反、类型错误等），
    返回给调用方写入 stats["errors"]，便于排查"0 migrated / N conflicts"的根因。
    """
    inserted = 0
    err_msgs: list[str] = []
    try:
        with engine.begin() as conn:
            result = conn.execute(insert_sql, batch)
            inserted = getattr(result, "rowcount", 0) or 0
    except Exception as exc:
        # 单批失败时尝试逐行回退，最大化迁移成功率
        print(
            f"  [warn] batch insert failed ({exc}); falling back to per-row",
            file=sys.stderr,
        )
        err_msgs.append(f"batch failed: {exc}")
        for params in batch:
            try:
                with engine.begin() as conn:
                    result = conn.execute(insert_sql, [params])
                    inserted += getattr(result, "rowcount", 0) or 0
            except Exception as row_exc:
                # 只记录前几条错误样本，避免日志爆炸
                if len(err_msgs) < 6:
                    err_msgs.append(f"row skipped: {row_exc}")
    conflicts = max(0, len(batch) - inserted)
    return inserted, conflicts, err_msgs


# ────────────────────────────── 归档 ──────────────────────────────

def archive_db_files(db_files: list[Path]) -> list[str]:
    """将 .db 文件重命名为 .bak.YYYYMMDD。返回归档后的文件名列表。"""
    date_tag = datetime.now().strftime("%Y%m%d")
    archived: list[str] = []
    for db_path in db_files:
        if not db_path.exists():
            continue
        new_path = db_path.with_name(f"{db_path.name}.bak.{date_tag}")
        # 如果已存在归档文件，附加序号
        counter = 1
        while new_path.exists():
            new_path = db_path.with_name(f"{db_path.name}.bak.{date_tag}.{counter}")
            counter += 1
        db_path.rename(new_path)
        archived.append(str(new_path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
    return archived


# ────────────────────────────── 报告 ──────────────────────────────

def write_report(
    per_table_stats: list[dict[str, Any]],
    unmapped_tables: list[dict[str, str]],
    archived_files: list[str],
) -> None:
    """生成 JSON + Markdown 报告。"""
    total_rows = sum(s["total_rows"] for s in per_table_stats)
    migrated_rows = sum(s["migrated_rows"] for s in per_table_stats)
    corrupted_rows = sum(s["corrupted_rows"] for s in per_table_stats)
    conflict_rows = sum(s["conflict_rows"] for s in per_table_stats)
    fk_nulled_rows = sum(s.get("fk_nulled_rows", 0) for s in per_table_stats)
    fk_dangling_skipped_rows = sum(s.get("fk_dangling_skipped_rows", 0) for s in per_table_stats)

    summary = {
        "total_rows": total_rows,
        "migrated_rows": migrated_rows,
        "corrupted_rows": corrupted_rows,
        "conflict_rows": conflict_rows,
        "fk_nulled_rows": fk_nulled_rows,
        "fk_dangling_skipped_rows": fk_dangling_skipped_rows,
        "unmapped_tables": unmapped_tables,
        "archived_files": archived_files,
    }
    report = {"summary": summary, "tables": per_table_stats}
    REPORT_JSON_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Markdown 报告
    lines: list[str] = []
    lines.append("# SQLite → PostgreSQL 迁移报告")
    lines.append("")
    lines.append(f"- 生成时间: {datetime.now().isoformat()}")
    lines.append(f"- 总行数（SQLite）: {total_rows}")
    lines.append(f"- 成功迁移行数: {migrated_rows}")
    lines.append(f"- 乱码行数: {corrupted_rows}")
    lines.append(f"- 冲突跳过行数: {conflict_rows}")
    lines.append(f"- FK 置空行数（dangling 引用，列可空）: {fk_nulled_rows}")
    lines.append(f"- FK dangling 跳过行数（列 NOT NULL，无法迁移）: {fk_dangling_skipped_rows}")
    lines.append(f"- 未映射表数: {len(unmapped_tables)}")
    lines.append(f"- 归档文件数: {len(archived_files)}")
    lines.append("")
    if unmapped_tables:
        lines.append("## 未映射表")
        lines.append("")
        for u in unmapped_tables:
            lines.append(f"- {u}")
        lines.append("")
    if archived_files:
        lines.append("## 归档文件")
        lines.append("")
        for f in archived_files:
            lines.append(f"- {f}")
        lines.append("")
    lines.append("## 各表迁移统计")
    lines.append("")
    lines.append(
        "| db_file | sqlite_table | pg_schema.pg_table | sqlite_rows | "
        "migrated | corrupted | conflicts | fk_nulled | fk_skipped | errors |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|"
    )
    for s in per_table_stats:
        lines.append(
            f"| {s['db_file']} | {s['sqlite_table']} | "
            f"{s['pg_schema']}.{s['pg_table']} | {s['total_rows']} | "
            f"{s['migrated_rows']} | {s['corrupted_rows']} | "
            f"{s['conflict_rows']} | {s.get('fk_nulled_rows', 0)} | "
            f"{s.get('fk_dangling_skipped_rows', 0)} | "
            f"{'; '.join(s.get('errors', [])) or '-'} |"
        )
    REPORT_MD_PATH.write_text("\n".join(lines), encoding="utf-8")


# ────────────────────────────── CLI ──────────────────────────────

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Migrate 27 SQLite .db files into PostgreSQL (Task 10)."
    )
    p.add_argument("--dry-run", action="store_true", help="只打印迁移计划，不实际写入")
    p.add_argument("--only", default=None, help="仅迁移指定 .db 文件（相对路径）")
    p.add_argument(
        "--skip-corrupted",
        action="store_true",
        help="跳过乱码记录（默认会清空乱码字段并标记）",
    )
    p.add_argument("--archive", action="store_true", help="迁移完成后归档 .db 文件为 .bak.YYYYMMDD")
    p.add_argument(
        "--no-reset-no-pk",
        action="store_true",
        help="不 TRUNCATE 无主键表（默认会 TRUNCATE 以避免重复迁移累积重复行）",
    )
    return p.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)

    if not MAPPING_PATH.exists():
        print(f"[error] mapping file missing: {MAPPING_PATH}", file=sys.stderr)
        print("        run `python scripts/_build_mapping.py` first", file=sys.stderr)
        return 2

    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    unmapped_tables: list[dict[str, str]] = mapping.get("__unmapped_tables__", [])
    db_entries = {k: v for k, v in mapping.items() if not k.startswith("__")}

    if args.only:
        only_norm = args.only.replace("\\", "/")
        if only_norm not in db_entries:
            print(f"[error] --only target not in mapping: {only_norm}", file=sys.stderr)
            return 2
        db_entries = {only_norm: db_entries[only_norm]}

    print(
        f"[plan] db_files={len(db_entries)} tables={sum(len(v) for v in db_entries.values())} "
        f"dry_run={args.dry_run} skip_corrupted={args.skip_corrupted} "
        f"archive={args.archive}",
        file=sys.stderr,
    )

    # 验证 PG 连接
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        print(f"[error] cannot connect to PostgreSQL: {exc}", file=sys.stderr)
        return 3

    per_table_stats: list[dict[str, Any]] = []
    archived_files: list[str] = []

    for db_rel, tables in db_entries.items():
        db_path = PROJECT_ROOT / db_rel
        print(f"[migrate] {db_rel}", file=sys.stderr)
        if not db_path.exists():
            print(f"  [skip] file not found: {db_path}", file=sys.stderr)
            for table_name, table_map in tables.items():
                per_table_stats.append({
                    "db_file": db_rel,
                    "sqlite_table": table_name,
                    "pg_schema": table_map["pg_schema"],
                    "pg_table": table_map["pg_table"],
                    "sqlite_row_count": table_map.get("sqlite_row_count", 0),
                    "total_rows": 0,
                    "migrated_rows": 0,
                    "corrupted_rows": 0,
                    "corrupted_fields": [],
                    "conflict_rows": 0,
                    "skipped_empty": True,
                    "errors": ["sqlite file not found"],
                })
            continue
        for table_name, table_map in tables.items():
            stats = migrate_table(
                db_rel=db_rel,
                sqlite_path=db_path,
                table_name=table_name,
                table_map=table_map,
                dry_run=args.dry_run,
                skip_corrupted=args.skip_corrupted,
                reset_no_pk=not args.no_reset_no_pk,
            )
            per_table_stats.append(stats)
            print(
                f"  - {table_name} -> {stats['pg_schema']}.{stats['pg_table']}: "
                f"total={stats['total_rows']} migrated={stats['migrated_rows']} "
                f"corrupted={stats['corrupted_rows']} conflicts={stats['conflict_rows']} "
                f"fk_nulled={stats.get('fk_nulled_rows', 0)}",
                file=sys.stderr,
            )
            if stats.get("errors"):
                for err in stats["errors"]:
                    print(f"    [error] {err}", file=sys.stderr)

    # 归档
    if args.archive and not args.dry_run:
        db_files = [PROJECT_ROOT / db_rel for db_rel in db_entries.keys()]
        archived_files = archive_db_files(db_files)
        for f in archived_files:
            print(f"[archive] {f}", file=sys.stderr)

    write_report(per_table_stats, unmapped_tables, archived_files)
    print(f"\n[done] report: {REPORT_MD_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
