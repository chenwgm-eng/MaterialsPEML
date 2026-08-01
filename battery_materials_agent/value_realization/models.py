"""研发收益证明层数据模型。"""

from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
from typing import Literal

COST_CATEGORIES = ("material", "equipment", "labor", "outsourced", "energy", "waste")


class ProjectBaseline(BaseModel):
    """项目历史基线：项目启动时录入，用于收益估算的对照基准。"""
    project_id: str = ""  # 由 router 从路径参数赋值，body 可省略
    historical_cycle_days: float = Field(default=0.0, ge=0)  # 历史原筛选周期（天）
    typical_experiment_cost: float = Field(default=0.0, ge=0)  # 单次实验典型成本（元）
    historical_hit_rate: float = Field(default=0.0, ge=0, le=1)  # 历史命中率（0-1）
    success_criteria: str = ""  # 成功标准（描述）
    past_candidate_count: int = Field(default=0, ge=0)  # 历史典型候选数
    notes: str = ""
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("success_criteria", "notes", mode="before")
    @classmethod
    def _none_to_empty(cls, v):
        return "" if v is None else v


class CostRule(BaseModel):
    """成本规则：可配置的单项成本单价，计算逻辑不硬编码单价。"""
    rule_id: str = ""
    name: str
    category: Literal["material", "equipment", "labor", "outsourced", "energy", "waste"]
    unit_price: float = Field(ge=0)  # 单价（元/unit）
    unit: str = ""  # 计价单位，如 次/样/小时
    currency: str = "CNY"
    enabled: bool = True
    notes: str = ""

    @field_validator("unit", "currency", "notes", mode="before")
    @classmethod
    def _none_to_empty(cls, v):
        return "" if v is None else v


class MetricValue(BaseModel):
    """单项指标输出。verified=实际已验证，estimated=基于假设的预估。

    数据不足时 value=None，kind=verified，assumption 写明缺什么数据。
    """
    label: str = ""
    value: float | int | str | None = None
    unit: str = ""
    kind: Literal["verified", "estimated"] = "verified"
    assumption: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
