"""Evidence 共享契约 — 科学证据包。"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EvidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ASSISTIVE = "assistive"  # 辅助证据，仅作参考


class SourceTier(str, Enum):
    """证据来源信任层级（CoE 信任分级）。

    - REAL_ENGINE: 真实引擎计算 / 真实外部库查询（chemicals/thermo/Crossref/arXiv/PubMed/SCP/Skill 等）
    - BUILTIN_LIBRARY: 内置文献库兜底（真实引擎未命中时的内置常量库）
    - LLM_GENERATED: LLM 纯记忆生成，未经外部核验
    """

    REAL_ENGINE = "real_engine"
    BUILTIN_LIBRARY = "builtin_library"
    LLM_GENERATED = "llm_generated"


# 旧 source_type 取值 → 新 SourceTier 的迁移映射。
# 说明：旧取值无法区分真实引擎与兜底，故 native_service 统一按 real_engine 迁移，
# 历史数据中真正的内置库兜底需结合 metadata.source 字符串（含"(内置)"）二次校正。
LEGACY_SOURCE_TYPE_TO_TIER: dict[str, SourceTier] = {
    "native_service": SourceTier.REAL_ENGINE,
    "scp": SourceTier.REAL_ENGINE,
    "skill": SourceTier.REAL_ENGINE,
}

# 内置库兜底在 source 字符串中的识别标记（各服务兜底分支约定含"(内置)"；
# "template" 对应文献检索的内置模板文献库兜底）。
BUILTIN_SOURCE_MARKERS: tuple[str, ...] = ("(内置)", "（内置）", "内置库", "builtin", "template")


def infer_source_tier(source: str = "", *, degraded: bool = False, llm_generated: bool = False) -> SourceTier:
    """根据来源信息推断信任层级。

    优先级：llm_generated > builtin（source 含内置标记）> degraded > real_engine。

    Args:
        source: 来源字符串（如 "chemicals/DIPPR"、"DIPPR(内置)"）。
        degraded: 是否为降级结果（真实引擎无法计算，回退到简化路径）。
        llm_generated: 是否由 LLM 纯记忆生成。

    Returns:
        SourceTier 枚举值。
    """
    if llm_generated:
        return SourceTier.LLM_GENERATED
    src = (source or "").strip()
    if any(marker in src for marker in BUILTIN_SOURCE_MARKERS):
        return SourceTier.BUILTIN_LIBRARY
    if degraded:
        # 降级路径未命中真实引擎，视为内置/简化兜底，而非真实引擎计算
        return SourceTier.BUILTIN_LIBRARY
    return SourceTier.REAL_ENGINE


def build_source_fields(
    provider: str,
    *,
    source: str = "",
    degraded: bool = False,
    llm_generated: bool = False,
) -> dict[str, Any]:
    """构建 EvidencePackage 的 source_type / source_service 及 metadata 补充字段。

    - source_type: 层级（real_engine / builtin_library / llm_generated）
    - source_service: "{tier}:{provider}" 格式
    - metadata 补充：source_tier、provider，以及兜底时的 fallback_reason

    Args:
        provider: 具体提供者标识（如 "chem_properties"、"DIPPR"、"internlm"）。
        source: 原始来源字符串（用于推断层级）。
        degraded: 是否降级。
        llm_generated: 是否 LLM 生成。

    Returns:
        dict，含 source_type / source_service / metadata_patch。
    """
    tier = infer_source_tier(source, degraded=degraded, llm_generated=llm_generated)
    metadata_patch: dict[str, Any] = {
        "source_tier": tier.value,
        "provider": provider,
    }
    if tier in (SourceTier.BUILTIN_LIBRARY,):
        metadata_patch["fallback_reason"] = f"真实引擎未命中，回退至 {source or provider}"
    elif tier == SourceTier.LLM_GENERATED:
        metadata_patch["fallback_reason"] = "LLM 纯记忆生成，未经外部核验"
    return {
        "source_type": tier.value,
        "source_service": f"{tier.value}:{provider}",
        "metadata_patch": metadata_patch,
    }


class EvidencePackage(BaseModel):
    """科学证据包 — 由原生服务产生，可触发审批。"""

    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    task_id: str
    claim: str
    value: Any = None
    unit: str = ""
    confidence: float = 1.0
    level: EvidenceLevel = EvidenceLevel.MEDIUM
    method: str = ""
    source_type: str = SourceTier.REAL_ENGINE.value  # real_engine | builtin_library | llm_generated
    source_service: str = ""  # "{tier}:{provider}"
    schema_version: str = "1.0.0"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
