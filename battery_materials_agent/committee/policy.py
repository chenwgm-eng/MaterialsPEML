"""Committee policy engine — trigger rules, authorization, and risk assessment."""

from ..config import CommitteeConfig
from .enums import CommitteeType, RiskLevel, TriggerCode
from .models import CommitteeCase


# Maps trigger codes to (committee_type, kind) where kind is "mandatory" or "conditional"
TRIGGER_COMMITTEE_MAP = {
    TriggerCode.CRYSTAL_GENERATED: (CommitteeType.CRYSTAL_CONSTRUCTION, "mandatory"),
    TriggerCode.CRYSTAL_CONFLICT: (CommitteeType.CRYSTAL_CONSTRUCTION, "mandatory"),
    TriggerCode.EXPERIMENT_NEW: (CommitteeType.EXPERIMENTAL_READINESS, "mandatory"),
    TriggerCode.DFT_RESOURCE_SCARCE: (CommitteeType.CANDIDATE_PRIORITY, "conditional"),
    TriggerCode.PREDICTION_CONFLICT: (CommitteeType.CANDIDATE_PRIORITY, "conditional"),
    TriggerCode.EXTERNAL_CONFLICT: (CommitteeType.EXTERNAL_EVIDENCE, "conditional"),
    TriggerCode.EXPERIMENT_DEVIATION: (CommitteeType.DEVIATION_REVIEW, "conditional"),
}


class PolicyDeniedError(Exception):
    """Raised when a policy check denies access."""
    pass


class CommitteePolicy:
    """Central policy for committee triggering, authorization, and risk levels."""

    def __init__(self, config: CommitteeConfig):
        self.config = config

    def should_trigger(self, trigger_code: str, committee_type: CommitteeType, context: dict) -> bool:
        """Check if a committee should be triggered based on policy."""
        if not self.config.enabled:
            return False

        # Per-committee enable flags
        if committee_type == CommitteeType.CRYSTAL_CONSTRUCTION and not self.config.crystal_enabled:
            return False
        if committee_type == CommitteeType.EXPERIMENTAL_READINESS and not self.config.experiment_enabled:
            return False
        if committee_type == CommitteeType.CANDIDATE_PRIORITY and not self.config.candidate_priority_enabled:
            return False
        if committee_type == CommitteeType.DEVIATION_REVIEW and not self.config.deviation_review_enabled:
            return False
        if committee_type == CommitteeType.EXTERNAL_EVIDENCE and not self.config.external_evidence_enabled:
            return False

        # Validate trigger_code against committee type
        mapping = TRIGGER_COMMITTEE_MAP.get(trigger_code)
        if mapping is None:
            return False
        mapped_committee, trigger_kind = mapping
        if mapped_committee != committee_type:
            return False

        # For conditional triggers, check context thresholds
        if trigger_kind == "conditional":
            if trigger_code == TriggerCode.DFT_RESOURCE_SCARCE.value:
                if context.get("estimated_cost", 0) <= self.config.dft_cost_trigger:
                    return False
            elif trigger_code == TriggerCode.PREDICTION_CONFLICT.value:
                if context.get("disagreement_ratio", 1.0) <= self.config.prediction_disagreement_ratio:
                    return False
            elif trigger_code == TriggerCode.EXTERNAL_CONFLICT.value:
                pass  # always True if enabled (hard rule)
            elif trigger_code == TriggerCode.EXPERIMENT_DEVIATION.value:
                if context.get("relative_deviation", 0) <= self.config.experiment_relative_deviation_trigger:
                    return False

        return True

    def assert_authorized(self, case: CommitteeCase, user_role: str = "viewer") -> None:
        """Check permissions. Raises PolicyDeniedError."""
        if not self.config.enabled:
            raise PolicyDeniedError("Committee system is disabled")
        # 系统自动触发跳过人工角色校验（ECML 自动触发使用 user_role="system"）
        if user_role == "system":
            return
        if case.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) and self.config.require_human_for_high_risk:
            if user_role not in ("admin", "pi", "reviewer"):
                raise PolicyDeniedError(
                    f"HIGH/CRITICAL risk cases require admin/pi/reviewer role, got {user_role}"
                )

    def get_risk_level(self, trigger_code: str, context: dict) -> RiskLevel:
        """Determine risk level based on trigger code and context."""
        high_risk_triggers = {
            TriggerCode.CRYSTAL_CONFLICT,
            TriggerCode.EXPERIMENT_DEVIATION,
            TriggerCode.EXTERNAL_CONFLICT,
        }
        critical_triggers = {
            TriggerCode.DFT_RESOURCE_SCARCE,
        }

        if trigger_code in critical_triggers:
            return RiskLevel.CRITICAL
        if trigger_code in high_risk_triggers:
            return RiskLevel.HIGH

        # Context-based escalation
        if context.get("cost_impact", 0) > self.config.dft_cost_trigger:
            return RiskLevel.HIGH
        if context.get("disagreement_ratio", 0) > self.config.prediction_disagreement_ratio:
            return RiskLevel.HIGH

        return RiskLevel.MEDIUM