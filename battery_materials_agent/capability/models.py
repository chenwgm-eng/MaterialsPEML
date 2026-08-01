"""能力契约（Capability Contract）数据模型。"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

RiskLevel = Literal["low", "medium", "high"]
ContractStatus = Literal["active", "pending_approval", "deprecated"]
ContractSource = Literal["auto", "manual"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Semver 正则：可选 "v" 前缀 + MAJOR.MINOR.PATCH
_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def validate_semver(version: str) -> str:
    """校验版本号符合 semver 格式（如 "1.0.0"、"2.1.3"）。

    接受 "v" 前缀（如 "v1.0.0"），校验时去除前缀并返回不带前缀的形式。
    不符合格式时抛出 ValueError。
    """
    if not isinstance(version, str):
        raise ValueError(
            f"version must be a string, got {type(version).__name__}"
        )
    match = _SEMVER_RE.match(version)
    if not match:
        raise ValueError(
            f"version '{version}' is not a valid semver. "
            "Expected format: MAJOR.MINOR.PATCH (e.g. '1.0.0'), "
            "optional 'v' prefix."
        )
    major, minor, patch = match.groups()
    return f"{major}.{minor}.{patch}"


class CapabilityContract(BaseModel):
    """AI 模型/工具能力契约。

    任何 AI 输出都应能回溯到对应契约：模型版本、适用域与回退路径。
    """

    capability_id: str
    name: str = ""
    provider: str = ""  # 提供方，如 local/m3gnet、askcos
    version: str = "1.0.0"
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    supported_domains: list[str] = Field(default_factory=list)  # 适用域
    limitations: list[str] = Field(default_factory=list)  # 已知局限
    uncertainty_method: str = ""  # 不确定性量化方法
    ood_method: str = ""  # 分布外（OOD）处理方法
    cost_model: dict = Field(default_factory=dict)  # 成本模型
    latency_sla: str = ""  # 时延 SLA，如 "P95 < 2s"
    risk_level: RiskLevel = "medium"
    fallback_chain: list[str] = Field(default_factory=list)  # 其他 capability_id
    validation_dataset: str = ""  # 验证数据集
    owner: str = ""  # 负责人
    license: str = ""
    status: ContractStatus = "pending_approval"
    source: ContractSource = "manual"
    created_at: str = Field(default_factory=_utc_now)
    updated_at: str = Field(default_factory=_utc_now)

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        return validate_semver(v)
