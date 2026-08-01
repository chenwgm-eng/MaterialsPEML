"""Workload identities and identity-driven context issuance for the Control Plane.

The :class:`IdentityManager` is the trust root that issues top-level
:class:`ExecutionContext` objects (``sign_context``) and derives child contexts
for agents (``derive_child``). It also validates contexts and answers
permission queries against the role hierarchy:

    admin > pm > researcher > viewer
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .context import DEFAULT_POLICY_VERSION, ExecutionContext, ROLE_RANK, _load_signing_key

logger = logging.getLogger(__name__)

MAX_DELEGATION_DEPTH = 8


class WorkloadIdentity(BaseModel):
    """A workload principal: a user, agent, committee, or tool."""

    identity_id: str
    identity_type: Literal["user", "agent", "committee", "tool"]
    name: str
    role: str
    project_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DelegationChain(BaseModel):
    """A validated view of an ExecutionContext's delegation lineage."""

    chain: list[str] = Field(default_factory=list)
    depth: int = 0
    valid: bool = True


class IdentityManager:
    """Issues and validates ExecutionContexts for the Control Plane.

    Role hierarchy: admin > pm > researcher > viewer. Child contexts (via
    :meth:`derive_child` / :meth:`ExecutionContext.child`) may only keep or
    shrink their role; escalation is rejected at creation time, so contexts
    issued through this manager cannot escalate by construction.
    """

    def __init__(
        self,
        policy_version: str = DEFAULT_POLICY_VERSION,
        default_ttl_seconds: int = 3600,
        max_delegation_depth: int = MAX_DELEGATION_DEPTH,
        user_store=None,
    ) -> None:
        self.policy_version = policy_version
        self.default_ttl_seconds = default_ttl_seconds
        self.max_delegation_depth = max_delegation_depth
        # HMAC signing key for ExecutionContext signatures. Loaded from the
        # ``CONTROL_PLANE_SIGNING_KEY`` env var (dev default fallback).
        self._signing_key: str = _load_signing_key()
        # Optional identity registry. When provided, ``sign_context`` verifies
        # that ``user_id`` exists and ``user_role`` matches the stored identity.
        self._user_store = user_store
        if self._user_store is None:
            logger.warning(
                "IdentityManager initialized without user_store — "
                "sign_context will not verify user identities (dev mode)"
            )

    def sign_context(
        self,
        user_id: str,
        user_role: str,
        project_id: str | None,
        ttl_seconds: int = 3600,
    ) -> ExecutionContext:
        """Create a top-level ExecutionContext for a user.

        Starts a fresh trace and an empty delegation chain. The user's role is
        the ceiling for any subsequently derived child contexts.

        When a ``user_store`` was provided at construction time, ``user_id``
        must exist in the store and ``user_role`` must match the stored
        identity's role; otherwise a ``ValueError`` is raised. Anonymous
        callers (``user_id is None``) bypass the registry check.
        """
        self._verify_identity(user_id, user_role)
        now = datetime.now(timezone.utc)
        context = ExecutionContext(
            correlation_id=str(uuid4()),
            trace_id=str(uuid4()),
            project_id=project_id,
            user_id=user_id,
            user_role=user_role,
            agent_id=None,
            delegation_chain=[],
            policy_version=self.policy_version,
            issued_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        context.signature = context.compute_signature(self._signing_key)
        return context

    def _verify_identity(self, user_id: str | None, user_role: str) -> None:
        """Validate ``user_id`` / ``user_role`` against the user store.

        Skipped (with a logged warning at init time) when no user store is
        configured. Anonymous callers (``user_id is None``) are always allowed
        through this check.
        """
        if self._user_store is None or user_id is None:
            return
        user = self._user_store.get(user_id)
        if user is None:
            raise ValueError(f"Unknown user_id: {user_id!r}")
        stored_role = getattr(user, "role", None)
        # Accept both plain strings and str-Enum role values.
        stored_role_value = getattr(stored_role, "value", stored_role)
        if stored_role_value != user_role:
            raise ValueError(
                f"Role mismatch for user {user_id!r}: "
                f"stored={stored_role_value!r} requested={user_role!r}"
            )

    def derive_child(
        self,
        parent_context: ExecutionContext,
        agent_id: str,
        agent_role: str,
    ) -> ExecutionContext:
        """Derive a child context for an agent with a (possibly reduced) role.

        The child inherits the parent's project and trace; its role may only
        stay the same or shrink. Escalation raises ``ValueError`` (via
        :meth:`ExecutionContext.child`). The child is signed with the same
        signing key as the parent so it can be verified downstream.
        """
        child = parent_context.child(
            actor=parent_context.agent_id or parent_context.user_id or "unknown",
            role=agent_role,
            agent_id=agent_id,
            ttl_seconds=self.default_ttl_seconds,
        )
        child.signature = child.compute_signature(self._signing_key)
        return child

    def validate_context(self, context: ExecutionContext) -> bool:
        """Return True if ``context`` is currently valid.

        Checks:
          - not expired;
          - delegation chain within the depth bound and free of empty entries
            (the depth bound is the practical recursion/cycle safeguard, since
            a chain records identities — not contexts — and the same agent may
            legitimately delegate again for a later step);
          - role is a recognized member of the hierarchy (rejects unknown or
            escalated role values);
          - carries a valid HMAC signature (rejects forged or tampered
            contexts, including those reconstructed via ``from_dict`` without
            a valid signature).

        Parent-vs-child role shrinkage is enforced at derivation time
        (:meth:`ExecutionContext.child`), so contexts issued through this
        manager cannot escalate by construction; this method re-verifies the
        role is legitimate and the signature is intact.
        """
        if context.is_expired():
            return False
        if not self._build_chain(context).valid:
            return False
        if context.user_role not in ROLE_RANK:
            return False
        if not context.verify_signature(self._signing_key):
            return False
        return True

    def check_permission(
        self,
        context: ExecutionContext,
        required_role: str,
    ) -> bool:
        """Return True if ``context`` may act at ``required_role`` or above.

        An expired context never grants permission (fail-closed). Unknown roles
        rank lowest (0), so a context with an unrecognized role cannot satisfy
        any role above viewer.
        """
        if context.is_expired():
            return False
        return ROLE_RANK.get(context.user_role, 0) >= ROLE_RANK.get(required_role, 0)

    def _build_chain(self, context: ExecutionContext) -> DelegationChain:
        """Build a validated DelegationChain view from a context's lineage."""
        chain = list(context.delegation_chain)
        depth = len(chain)
        valid = (
            depth <= self.max_delegation_depth
            and all(isinstance(entry, str) and entry for entry in chain)
        )
        return DelegationChain(chain=chain, depth=depth, valid=valid)
