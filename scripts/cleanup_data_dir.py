"""清理 data/ 目录中遗留的 SQLite 数据库文件与备份。

系统已迁移至 PostgreSQL（DATABASE_URL），data/ 下的 *.db / *.db.bak* / *.bak
均为历史 SQLite 残留，删除以保持目录整洁。

用法:
  python scripts/cleanup_data_dir.py [root_dir]
"""
from __future__ import annotations

import logging
import pathlib
import sys

logger = logging.getLogger(__name__)


def cleanup_sqlite_files(root_dir: str = "data", dry_run: bool = False) -> list[pathlib.Path]:
    """递归删除 root_dir 下遗留的 SQLite 文件（*.db、*.db.bak*、*.bak）。

    Args:
        root_dir: 目标根目录。
        dry_run: 为 True 时仅列出不删除。

    Returns:
        被删除（或将被删除）的文件路径列表。
    """
    root = pathlib.Path(root_dir)
    if not root.is_dir():
        logger.warning("目录不存在: %s", root)
        return []

    # *.db.bak.1 / *.db.bak / *.bak / *.db
    targets: list[pathlib.Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if name.endswith(".db") or name.endswith(".bak") or ".db.bak" in name:
            targets.append(path)

    if not targets:
        logger.info("未找到需清理的 SQLite 残留文件")
        return []

    for path in sorted(targets):
        if dry_run:
            logger.info("[dry-run] 待删除: %s", path)
        else:
            try:
                path.unlink()
                logger.info("已删除: %s", path)
            except OSError as exc:
                logger.error("删除失败 %s: %s", path, exc)

    return targets


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root_arg = sys.argv[1] if len(sys.argv) > 1 else "data"
    deleted = cleanup_sqlite_files(root_arg)
    print(f"清理完成，共处理 {len(deleted)} 个文件。")