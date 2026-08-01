"""Policy Engine — testable policy decision point for the Agent Control Plane.

Enforces authorization at API entry, committee triggers, agent dispatch, tool
invocation, state transitions and artifact download points. Decisions are
deterministic functions of (ExecutionContext, action, resource) plus any
registered PolicyRules.
"""
from __future__ import annotations

import fnmatch
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from .context import ExecutionContext

if TYPE_CHECKING:  # avoid runtime cycle; store is injected, not imported
    from .policy_store import PolicyStore

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# Action taxonomy
# ──────────────────────────────────────────────────────────────────────────

ACTION_TAXONOMY: frozenset[str] = frozenset({
    "ecml.run.create",
    "ecml.run.resume",
    "ecml.run.cancel",
    "committee.case.create",
    "committee.case.review",
    "tool.invoke",
    "tool.register",
    "policy.update",
    "budget.update",
    "artifact.download",
    "experiment.start",
    "experiment.submit",
})


# ──────────────────────────────────────────────────────────────────────────
# Role-based permission matrix (admin > pm > researcher > viewer)
# ──────────────────────────────────────────────────────────────────────────

_READ_ACTIONS: frozenset[str] = frozenset({
    "artifact.download",
    "committee.case.review",
})

_RESEARCHER_ACTIONS: frozenset[str] = _READ_ACTIONS | frozenset({
    "ecml.run.create",
    "ecml.run.resume",
    "ecml.run.cancel",
    "committee.case.create",
    "tool.invoke",
    "experiment.start",
    "experiment.submit",
})

_PM_ACTIONS: frozenset[str] = _RESEARCHER_ACTIONS | frozenset({"budget.update"})

_ADMIN_ACTIONS: frozenset[str] = _PM_ACTIONS | frozenset({
    "policy.update",
    "tool.register",
})

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": _ADMIN_ACTIONS,
    "pm": _PM_ACTIONS,
    "researcher": _RESEARCHER_ACTIONS,
    "viewer": _READ_ACTIONS,
}


# Initial tool whitelist — tools not in this set are permanently denied when
# ``tool.invoke`` is evaluated. Extend via ``add_registered_tool``.
DEFAULT_REGISTERED_TOOLS: frozenset[str] = frozenset({
    # SCP standard bindings (see mcp_tools/scp_catalog.py)
    "scp_molecule_descriptors",
    "scp_toxicity_assessment",
    "scp_literature_search",
    "scp_protocol_draft",
    "scp_material_transform",
    # Local / DFT tools
    "dft_vasp",
    "dft_quantum_espresso",
    "pymatgen_validate",
    "m3gnet_relax",
    "m3gnet_predict",
    # LLM generation
    "internlm_generate",
})


# ──────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────

class PolicyDecision(BaseModel):
    """Outcome of a single authorization request."""

    allowed: bool
    reason_code: str
    obligations: list[str] = Field(default_factory=list)
    limits: dict = Field(default_factory=dict)
    policy_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PolicyRule(BaseModel):
    """A single declarative policy rule.

    ``subject_pattern``, ``action`` and ``resource_pattern`` support fnmatch
    glob matching. The first matching rule (highest priority first) wins.
    """

    rule_id: str
    subject_pattern: str
    action: str
    resource_pattern: str
    allowed: bool
    reason_code: str = "policy_rule"
    obligations: list[str] = Field(default_factory=list)
    limits: dict = Field(default_factory=dict)
    priority: int = 0


# ──────────────────────────────────────────────────────────────────────────
# Default rules
# ──────────────────────────────────────────────────────────────────────────

def build_default_rules() -> list[PolicyRule]:
    """The built-in policy rules required by the Control Plane spec.

    Rules 1, 2 and 5 are expressed as declarative ``PolicyRule`` entries.
    Rules 3, 4 and 6 are enforced structurally:
      * Rule 3 (viewer read-only) — viewer writes fall through to
        ``_check_role_permission``.
      * Rule 4 (unregistered tools) — rejected before rule evaluation.
      * Rule 6 (expired context) — rejected as a hard gate in ``authorize``.
    """
    return [
        # Rule 1: Thinker agent cannot call DFT tools or start experiments.
        PolicyRule(
            rule_id="deny-thinker-dft",
            subject_pattern="agent:thinker",
            action="tool.invoke",
            resource_pattern="tool:dft_*",
            allowed=False,
            reason_code="role_not_permitted",
            priority=100,
        ),
        PolicyRule(
            rule_id="deny-thinker-experiment-start",
            subject_pattern="agent:thinker",
            action="experiment.start",
            resource_pattern="*",
            allowed=False,
            reason_code="role_not_permitted",
            priority=100,
        ),
        PolicyRule(
            rule_id="deny-thinker-experiment-submit",
            subject_pattern="agent:thinker",
            action="experiment.submit",
            resource_pattern="*",
            allowed=False,
            reason_code="role_not_permitted",
            priority=100,
        ),
        # Rule 2: Committee cannot start real experiments (only DRAFT/SUBMITTED
        # via experiment.submit is permitted).
        PolicyRule(
            rule_id="deny-committee-experiment-start",
            subject_pattern="agent:committee",
            action="experiment.start",
            resource_pattern="*",
            allowed=False,
            reason_code="role_not_permitted",
            priority=100,
        ),
        # Rule 5: Researcher may invoke SCP tools only conditionally — project
        # permission and risk acknowledgement must be verified downstream.
        PolicyRule(
            rule_id="conditional-researcher-scp",
            subject_pattern="role:researcher",
            action="tool.invoke",
            resource_pattern="tool:scp_*",
            allowed=True,
            reason_code="conditional_approval",
            obligations=[
                "verify_project_permission",
                "require_scp_risk_acknowledgement",
            ],
            limits={"max_risk_level": "C"},
            priority=50,
        ),
    ]


# ──────────────────────────────────────────────────────────────────────────
# Policy Engine
# ──────────────────────────────────────────────────────────────────────────

class PolicyEngine:
    """Decision point that authorizes control-plane actions."""

    def __init__(self, policy_store: "PolicyStore | None" = None):
        self._policy_store = policy_store
        self._rules: list[PolicyRule] = list(build_default_rules())
        self.registered_tools: set[str] = set(DEFAULT_REGISTERED_TOOLS)
        self._policy_version: str = "cp-v1"
        self._max_chain_depth: int = 8

        if policy_store is not None:
            try:
                active = policy_store.get_active_version()
            except LookupError:
                logger.warning(
                    "No active policy version in store; using built-in defaults only"
                )
                active = None
            if active is not None:
                self._policy_version = active.version
                for rule in active.rules:
                    self._rules.append(rule)
                logger.info(
                    "Loaded active policy version %s with %d additional rules",
                    active.version,
                    len(active.rules),
                )

        logger.info(
            "PolicyEngine initialized (version=%s, rules=%d, registered_tools=%d)",
            self._policy_version,
            len(self._rules),
            len(self.registered_tools),
        )

    # ── public API ───────────────────────────────────────────────────────

    def authorize(
        self,
        context: ExecutionContext,
        action: str,
        resource: str,
        **kwargs,
    ) -> PolicyDecision:
        """Main decision method.

        Evaluation order:
          1. Context validity (expiry / delegation) — hard gates.
          2. Tool registration (``tool.invoke`` only) — hard gate.
          3. Registered rules, highest priority first; first match wins.
          4. Role-based fallback via ``_check_role_permission``.
        """
        policy_version = self.get_policy_version()
        now = datetime.now(timezone.utc)

        # Hard gate: expired context (Rule 6).
        if context.is_expired():
            logger.info(
                "DENY expired_delegation (correlation_id=%s, action=%s, resource=%s)",
                context.correlation_id,
                action,
                resource,
            )
            return self._deny(policy_version, now, "expired_delegation")

        # Hard gate: invalid delegation chain.
        if not self._is_delegation_valid(context.delegation_chain):
            logger.info(
                "DENY invalid_delegation (correlation_id=%s, action=%s)",
                context.correlation_id,
                action,
            )
            return self._deny(policy_version, now, "invalid_delegation")

        # Hard gate: unregistered tools (Rule 4).
        if action == "tool.invoke":
            tool_name = self._extract_tool_name(resource)
            if tool_name is not None and not self._is_tool_registered(tool_name, kwargs):
                logger.info(
                    "DENY unknown_tool (tool=%s, correlation_id=%s)",
                    tool_name,
                    context.correlation_id,
                )
                return self._deny(policy_version, now, "unknown_tool")

        # Rule evaluation: first matching rule (highest priority) wins.
        subjects = self._derive_subjects(context)
        for rule in sorted(self._rules, key=lambda r: r.priority, reverse=True):
            if self._rule_matches(rule, subjects, action, resource):
                decision = PolicyDecision(
                    allowed=rule.allowed,
                    reason_code=rule.reason_code,
                    obligations=list(rule.obligations),
                    limits=dict(rule.limits),
                    policy_version=policy_version,
                    created_at=now,
                )
                logger.info(
                    "rule=%s -> allowed=%s reason=%s (correlation_id=%s, action=%s, resource=%s)",
                    rule.rule_id,
                    decision.allowed,
                    decision.reason_code,
                    context.correlation_id,
                    action,
                    resource,
                )
                return decision

        # Fallback: role-based permission (Rule 3 enforced here — viewer is
        # restricted to read actions).
        if self._check_role_permission(context.user_role, action, resource):
            logger.info(
                "ALLOW role_permitted (role=%s, action=%s, resource=%s)",
                context.user_role,
                action,
                resource,
            )
            return PolicyDecision(
                allowed=True,
                reason_code="role_permitted",
                policy_version=policy_version,
                created_at=now,
            )

        logger.info(
            "DENY role_not_permitted (role=%s, action=%s, resource=%s)",
            context.user_role,
            action,
            resource,
        )
        return self._deny(policy_version, now, "role_not_permitted")

    def add_rule(self, rule: PolicyRule) -> None:
        """Append a policy rule. Higher ``priority`` is evaluated first."""
        self._rules.append(rule)
        logger.info("Added policy rule %s (priority=%d)", rule.rule_id, rule.priority)

    def add_registered_tool(self, name: str) -> None:
        """Register a tool name so ``tool.invoke`` is not permanently denied."""
        self.registered_tools.add(name)
        logger.info("Registered tool %s", name)

    def get_policy_version(self) -> str:
        """Return the policy version stamp applied to every decision."""
        return self._policy_version

    # ── internals ────────────────────────────────────────────────────────

    def _check_role_permission(self, role: str, action: str, resource: str) -> bool:
        """Internal role check against the cumulative role matrix.

        Unknown roles collapse to viewer-level (least privilege).
        """
        allowed_actions = ROLE_PERMISSIONS.get(role, _READ_ACTIONS)
        return action in allowed_actions

    def _is_delegation_valid(self, chain: list[str]) -> bool:
        """Structural delegation-chain check.

        A top-level context may have an empty chain (the user acts directly).
        A non-empty chain is valid when it does not exceed the depth bound and
        every hop is a non-empty string. Cryptographic verification of each hop
        is the responsibility of the identity layer; the engine only rejects
        structurally malformed delegations up front.
        """
        if not chain:
            return True  # top-level context — empty chain is allowed
        if len(chain) > self._max_chain_depth:
            return False
        return all(isinstance(hop, str) and hop.strip() for hop in chain)

    def _derive_subjects(self, context: ExecutionContext) -> list[str]:
        """Build the set of subject tokens a rule's ``subject_pattern`` may match."""
        subjects: list[str] = ["*", f"role:{context.user_role}"]
        if context.agent_id:
            subjects.append(f"agent:{context.agent_id}")
        if context.committee_case_id:
            # Any action performed within a committee case is also scoped by
            # the synthetic ``agent:committee`` subject.
            subjects.append("agent:committee")
        return subjects

    def _rule_matches(
        self,
        rule: PolicyRule,
        subjects: list[str],
        action: str,
        resource: str,
    ) -> bool:
        if not any(fnmatch.fnmatch(s, rule.subject_pattern) for s in subjects):
            return False
        if not fnmatch.fnmatch(action, rule.action):
            return False
        if not fnmatch.fnmatch(resource, rule.resource_pattern):
            return False
        return True

    @staticmethod
    def _extract_tool_name(resource: str) -> str | None:
        """``tool:dft_vasp`` -> ``dft_vasp``; otherwise ``None``."""
        if resource.startswith("tool:"):
            return resource[len("tool:"):]
        return None

    def _is_tool_registered(self, tool_name: str, kwargs: dict) -> bool:
        """True when the tool is known. The registry may be augmented via the
        ``registered_tools`` kwarg (an iterable of tool names).

        Fail-closed: an empty registry (no tools registered at all) denies
        every tool rather than silently allowing it.
        """
        known = set(self.registered_tools)
        extra = kwargs.get("registered_tools")
        if extra:
            known |= set(extra)
        if not known:
            # No registry configured — fail-closed.
            return False
        return tool_name in known

    @staticmethod
    def _deny(
        policy_version: str,
        now: datetime,
        reason_code: str,
    ) -> PolicyDecision:
        return PolicyDecision(
            allowed=False,
            reason_code=reason_code,
            policy_version=policy_version,
            created_at=now,
        )
