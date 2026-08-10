"""Execution context for the Agent Control Plane.

An :class:`ExecutionContext` is a signed, delegatable credential that scopes
what an agent (or user) may do within a single request/trace. Permissions only
ever shrink along a delegation chain: a child context inherits the parent's
project, a role that is equal-or-lower, and a deadline no later than the
parent's.

Role hierarchy: admin > pm > researcher > viewer.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

# Default signing key for development ONLY. Override in production via the
# ``CONTROL_PLANE_SIGNING_KEY`` environment variable.
DEFAULT_SIGNING_KEY = "dev-control-plane-signing-key-CHANGE-ME"


def _load_signing_key() -> str:
    """Load the HMAC signing key from the environment.

    生产模式（RUN_MODE=production）必须显式配置 CONTROL_PLANE_SIGNING_KEY，
    拒绝使用内置开发密钥——否则知情者可伪造任意角色/项目的签名上下文
    绕过治理链（与 auth/tokens.py 的 production 守卫策略一致）。
    """
    key = os.environ.get("CONTROL_PLANE_SIGNING_KEY", "")
    if key:
        return key
    run_mode = (os.environ.get("RUN_MODE", "demo") or "").lower()
    if run_mode == "production":
        raise RuntimeError(
            "RUN_MODE=production 时必须显式配置 CONTROL_PLANE_SIGNING_KEY，"
            "禁止使用内置开发签名密钥"
        )
    return DEFAULT_SIGNING_KEY

# Role hierarchy: higher rank == more permissions.
ROLE_RANK: dict[str, int] = {
    "admin": 4,
    "pm": 3,
    "researcher": 2,
    "viewer": 1,
}

DEFAULT_POLICY_VERSION = "cp-v1"
DEFAULT_CHILD_TTL_SECONDS = 1800


def _rank(role: str) -> int:
    """Return the rank for a role; unknown roles get the lowest rank (0)."""
    return ROLE_RANK.get(role, 0)


def _ensure_aware_utc(dt: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ExecutionContext(BaseModel):
    """Signed, delegatable execution scope for a single agent action.

    Fields group into:
      - identity/correlation: ``correlation_id``, ``trace_id``, ``user_id``, ``agent_id``
      - scope: ``project_id``, ``user_role``, ``budget_scope_id``,
        ``ecml_run_id``, ``committee_case_id``
      - lineage: ``parent_action_id``, ``delegation_chain``
      - governance: ``policy_version``, ``issued_at``, ``expires_at``
    """

    correlation_id: str
    trace_id: str
    project_id: str | None = None
    user_id: str | None = None
    user_role: str
    ecml_run_id: str | None = None
    committee_case_id: str | None = None
    agent_id: str | None = None
    parent_action_id: str | None = None
    delegation_chain: list[str] = Field(default_factory=list)
    policy_version: str = DEFAULT_POLICY_VERSION
    budget_scope_id: str | None = None
    issued_at: datetime
    expires_at: datetime
    # HMAC-SHA256 signature over the security-critical fields. Computed by
    # :meth:`IdentityManager.sign_context`; verified by :meth:`verify_signature`.
    # The signing key itself is never stored on the model (only the signature is).
    signature: str = ""

    # ── queries ──────────────────────────────────────────────────────────

    def is_expired(self) -> bool:
        """Return True if the context's deadline has passed (UTC)."""
        return datetime.now(timezone.utc) >= _ensure_aware_utc(self.expires_at)

    # ── signature ────────────────────────────────────────────────────────

    def _signature_payload(self) -> str:
        """Build the canonical message string covered by the HMAC signature.

        Only security-critical fields are signed: ``correlation_id``,
        ``user_id``, ``user_role``, ``expires_at`` and ``delegation_chain``.
        The ``signature`` field itself is excluded (it cannot sign itself).
        """
        expires_str = _ensure_aware_utc(self.expires_at).isoformat()
        parts = [
            self.correlation_id,
            str(self.user_id),
            self.user_role,
            expires_str,
            "|".join(self.delegation_chain),
        ]
        return "\n".join(parts)

    def compute_signature(self, signing_key: str) -> str:
        """Compute the HMAC-SHA256 signature over the security-critical fields."""
        payload = self._signature_payload().encode("utf-8")
        return hmac.new(
            signing_key.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()

    def verify_signature(self, signing_key: str) -> bool:
        """Return True if the stored signature matches the recomputed HMAC.

        An empty signature (unsigned context) always fails verification.
        """
        if not self.signature:
            return False
        expected = self.compute_signature(signing_key)
        return hmac.compare_digest(self.signature, expected)

    # ── delegation ───────────────────────────────────────────────────────

    @classmethod
    def sign(
        cls,
        parent_context: ExecutionContext,
        child_agent_id: str,
        ttl_seconds: int = DEFAULT_CHILD_TTL_SECONDS,
    ) -> ExecutionContext:
        """Create a child context signed from ``parent_context``.

        The child inherits the parent's role (the maximum a child may hold),
        the parent's project, and a deadline no later than both the parent's
        deadline and ``now + ttl_seconds``. The parent's identity
        (``agent_id`` or ``user_id``) is appended to the delegation chain.

        ``parent_action_id`` is set to the parent's ``agent_id`` (the agent
        action that spawned this child, or ``None`` for a top-level parent).
        """
        if parent_context.is_expired():
            raise ValueError("Cannot derive from expired parent context")
        now = datetime.now(timezone.utc)
        parent_expires = _ensure_aware_utc(parent_context.expires_at)
        child_expires = min(parent_expires, now + timedelta(seconds=ttl_seconds))
        signer = parent_context.agent_id or parent_context.user_id or "unknown"
        return cls(
            correlation_id=str(uuid4()),
            trace_id=parent_context.trace_id,
            project_id=parent_context.project_id,
            user_id=parent_context.user_id,
            user_role=parent_context.user_role,
            ecml_run_id=parent_context.ecml_run_id,
            committee_case_id=parent_context.committee_case_id,
            agent_id=child_agent_id,
            parent_action_id=parent_context.agent_id,
            delegation_chain=[*parent_context.delegation_chain, signer],
            policy_version=parent_context.policy_version,
            budget_scope_id=parent_context.budget_scope_id,
            issued_at=now,
            expires_at=child_expires,
        )

    def child(
        self,
        actor: str,
        role: str,
        agent_id: str,
        ttl_seconds: int = DEFAULT_CHILD_TTL_SECONDS,
    ) -> ExecutionContext:
        """Derive a sub-context from ``self`` with an explicit role.

        Permissions only shrink: ``role`` must be equal to or lower than this
        context's role, otherwise a ``ValueError`` is raised. ``actor`` is
        recorded as ``parent_action_id`` (the principal that triggered this
        derivation). The project cannot change; the deadline is the earlier of
        this context's deadline and ``now + ttl_seconds``.
        """
        if self.is_expired():
            raise ValueError("Cannot derive from expired parent context")
        if _rank(role) > _rank(self.user_role):
            raise ValueError(
                f"role escalation forbidden: requested '{role}' > parent '{self.user_role}'"
            )
        now = datetime.now(timezone.utc)
        parent_expires = _ensure_aware_utc(self.expires_at)
        child_expires = min(parent_expires, now + timedelta(seconds=ttl_seconds))
        signer = self.agent_id or self.user_id or "unknown"
        return ExecutionContext(
            correlation_id=str(uuid4()),
            trace_id=self.trace_id,
            project_id=self.project_id,
            user_id=self.user_id,
            user_role=role,
            ecml_run_id=self.ecml_run_id,
            committee_case_id=self.committee_case_id,
            agent_id=agent_id,
            parent_action_id=actor,
            delegation_chain=[*self.delegation_chain, signer],
            policy_version=self.policy_version,
            budget_scope_id=self.budget_scope_id,
            issued_at=now,
            expires_at=child_expires,
        )

    # ── serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict (datetimes as ISO strings).

        The ``signature`` field is included so the context can be re-verified
        on deserialization; the signing key itself is never stored on the
        model and therefore never appears in the output.
        """
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(
        cls,
        data: dict,
        signing_key: str | None = None,
    ) -> ExecutionContext:
        """Reconstruct an ExecutionContext from a serialized dict.

        The HMAC signature is verified against ``signing_key`` (or the
        ``CONTROL_PLANE_SIGNING_KEY`` environment default when ``None``).
        A missing or mismatched signature raises ``ValueError`` so that
        forged or tampered contexts cannot be reintroduced via deserialization.
        """
        obj = cls.model_validate(data)
        key = signing_key if signing_key is not None else _load_signing_key()
        if not obj.verify_signature(key):
            raise ValueError(
                "Invalid or missing ExecutionContext signature — "
                "context may have been tampered with or forged"
            )
        return obj
