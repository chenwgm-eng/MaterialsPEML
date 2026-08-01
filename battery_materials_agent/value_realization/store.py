"""研发收益证明层存储：项目基线与成本规则（PostgreSQL）。"""

from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import uuid

from sqlalchemy import text

from ..db import get_engine
from .models import ProjectBaseline, CostRule

# 兼容旧调用方：calculator.py 仍引用 DATA_DIR 作为默认 data_dir。
# 迁移至 PostgreSQL 后 db_path 已被 Store 忽略，此处仅为符号兼容。
DATA_DIR = Path("data")


def _iso(value) -> str:
    """将 datetime 或字符串转换为 ISO 字符串；None 返回空字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


# 幂等预置的默认成本规则（仅在表中不存在同名规则时插入）
DEFAULT_COST_RULES = [
    CostRule(rule_id="CR_WET_LAB", name="单次湿实验综合成本", category="labor",
             unit_price=5000.0, unit="次", notes="默认预置：一次湿实验综合成本"),
    CostRule(rule_id="CR_XRD", name="XRD表征", category="equipment",
             unit_price=300.0, unit="样", notes="默认预置：XRD 表征单样成本"),
    CostRule(rule_id="CR_SEM", name="SEM表征", category="equipment",
             unit_price=500.0, unit="样", notes="默认预置：SEM 表征单样成本"),
    CostRule(rule_id="CR_ECHEM", name="电化学测试", category="equipment",
             unit_price=800.0, unit="样", notes="默认预置：电化学测试单样成本"),
]


class ValueRealizationStore:
    """基线与成本规则存储。"""

    def __init__(self, db_path: str | None = None):
        # db_path 参数保留以兼容旧调用方，迁移至 PostgreSQL 后已忽略，统一使用全局 Engine。
        self.engine = get_engine()
        self._seed_default_rules()

    def _seed_default_rules(self):
        """幂等预置默认成本规则：rule_id 已存在则跳过。"""
        with self.engine.begin() as conn:
            for rule in DEFAULT_COST_RULES:
                conn.execute(
                    text("""INSERT INTO value_realization.cost_rules
                    (rule_id, name, category, unit_price, unit, currency, enabled, notes)
                    VALUES (:rule_id, :name, :category, :unit_price, :unit, :currency, :enabled, :notes)
                    ON CONFLICT (rule_id) DO NOTHING"""),
                    {
                        "rule_id": rule.rule_id, "name": rule.name,
                        "category": rule.category, "unit_price": rule.unit_price,
                        "unit": rule.unit, "currency": rule.currency,
                        "enabled": rule.enabled, "notes": rule.notes,
                    },
                )

    # ---------- 基线 CRUD ----------

    def upsert_baseline(self, baseline: ProjectBaseline) -> ProjectBaseline:
        baseline.updated_at = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO value_realization.baselines
                (project_id, historical_cycle_days, typical_experiment_cost,
                 historical_hit_rate, success_criteria, past_candidate_count,
                 notes, updated_at)
                VALUES (:project_id, :historical_cycle_days, :typical_experiment_cost,
                        :historical_hit_rate, CAST(:success_criteria AS JSONB), :past_candidate_count,
                        :notes, :updated_at)
                ON CONFLICT (project_id) DO UPDATE SET
                    historical_cycle_days=EXCLUDED.historical_cycle_days,
                    typical_experiment_cost=EXCLUDED.typical_experiment_cost,
                    historical_hit_rate=EXCLUDED.historical_hit_rate,
                    success_criteria=EXCLUDED.success_criteria,
                    past_candidate_count=EXCLUDED.past_candidate_count,
                    notes=EXCLUDED.notes,
                    updated_at=EXCLUDED.updated_at"""),
                {
                    "project_id": baseline.project_id,
                    "historical_cycle_days": baseline.historical_cycle_days,
                    "typical_experiment_cost": baseline.typical_experiment_cost,
                    "historical_hit_rate": baseline.historical_hit_rate,
                    "success_criteria": baseline.success_criteria,
                    "past_candidate_count": baseline.past_candidate_count,
                    "notes": baseline.notes,
                    "updated_at": baseline.updated_at,
                },
            )
        return baseline

    def get_baseline(self, project_id: str) -> ProjectBaseline | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM value_realization.baselines WHERE project_id=:project_id"),
                {"project_id": project_id},
            ).fetchone()
        if not row:
            return None
        return ProjectBaseline(
            project_id=row[0], historical_cycle_days=row[1] or 0.0,
            typical_experiment_cost=row[2] or 0.0, historical_hit_rate=row[3] or 0.0,
            success_criteria=row[4] or "", past_candidate_count=row[5] or 0,
            notes=row[6] or "", updated_at=_iso(row[7]),
        )

    # ---------- 成本规则 CRUD ----------

    @staticmethod
    def _row_to_rule(r) -> CostRule:
        valid_categories = ("material", "equipment", "labor", "outsourced", "energy", "waste")
        category = r[2] if r[2] in valid_categories else "labor"
        return CostRule(
            rule_id=r[0] or "", name=r[1] or "未命名规则", category=category,
            unit_price=r[3] if r[3] is not None else 0.0,
            unit=r[4] or "", currency=r[5] or "CNY", enabled=bool(r[6]) if r[6] is not None else True,
            notes=r[7] or "",
        )

    def list_cost_rules(self, enabled_only: bool = False) -> list[CostRule]:
        with self.engine.connect() as conn:
            if enabled_only:
                rows = conn.execute(
                    text("SELECT * FROM value_realization.cost_rules WHERE enabled=TRUE ORDER BY rule_id")
                ).fetchall()
            else:
                rows = conn.execute(
                    text("SELECT * FROM value_realization.cost_rules ORDER BY rule_id")
                ).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def get_cost_rule(self, rule_id: str) -> CostRule | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM value_realization.cost_rules WHERE rule_id=:rule_id"),
                {"rule_id": rule_id},
            ).fetchone()
        return self._row_to_rule(row) if row else None

    def create_cost_rule(self, rule: CostRule) -> CostRule:
        if not rule.rule_id:
            rule.rule_id = f"CR_{uuid.uuid4().hex[:8].upper()}"
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO value_realization.cost_rules
                (rule_id, name, category, unit_price, unit, currency, enabled, notes)
                VALUES (:rule_id, :name, :category, :unit_price, :unit, :currency, :enabled, :notes)"""),
                {
                    "rule_id": rule.rule_id, "name": rule.name,
                    "category": rule.category, "unit_price": rule.unit_price,
                    "unit": rule.unit, "currency": rule.currency,
                    "enabled": rule.enabled, "notes": rule.notes,
                },
            )
        return rule

    def update_cost_rule(self, rule_id: str, rule: CostRule) -> CostRule | None:
        if self.get_cost_rule(rule_id) is None:
            return None
        rule.rule_id = rule_id
        with self.engine.begin() as conn:
            conn.execute(
                text("""UPDATE value_realization.cost_rules SET name=:name, category=:category, unit_price=:unit_price,
                unit=:unit, currency=:currency, enabled=:enabled, notes=:notes WHERE rule_id=:rule_id"""),
                {
                    "name": rule.name, "category": rule.category,
                    "unit_price": rule.unit_price, "unit": rule.unit,
                    "currency": rule.currency, "enabled": rule.enabled,
                    "notes": rule.notes, "rule_id": rule_id,
                },
            )
        return rule

    def delete_cost_rule(self, rule_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM value_realization.cost_rules WHERE rule_id=:rule_id"),
                {"rule_id": rule_id},
            )
        return cur.rowcount > 0
