"""清理残留的两层流程（T2L-）测试数据，避免外键残留导致后续测试失败。"""
from pathlib import Path  # noqa: F401
from sqlalchemy import text
from battery_materials_agent.db import get_engine


def main() -> None:
    e = get_engine()
    with e.begin() as conn:
        # 先删子表（process_schemes 引用 candidates）
        dp = conn.execute(
            text("DELETE FROM experiment.process_schemes WHERE process_id LIKE 'T2L-%'")
        ).rowcount
        # 实验单：order_id 为 EXP_...，但 candidate_id/process_id 为 T2L-，需按来源关联删除
        do = conn.execute(
            text("DELETE FROM experiment.experiment_orders "
                 "WHERE candidate_id LIKE 'T2L-%' OR process_id LIKE 'T2L-%'")
        ).rowcount
        # 候选
        dc = conn.execute(
            text("DELETE FROM experiment.candidates WHERE candidate_id LIKE 'T2L-%'")
        ).rowcount
    print(f"cleaned: process_schemes={dp}, experiment_orders={do}, candidates={dc}")


if __name__ == "__main__":
    main()