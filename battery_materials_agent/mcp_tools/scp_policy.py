"""SCP Policy — authorization and rate limiting for SCP tool calls."""

from __future__ import annotations
from .scp_catalog import SCPCatalog, RiskLevel


class PolicyDeniedError(Exception):
    pass


class SCPPolicy:
    """Authorization and rate limiting for SCP tool calls."""

    def __init__(self, catalog: SCPCatalog):
        self.catalog = catalog

    def authorize(self, internal_name: str, user_role: str, ecml_step: int | None = None) -> bool:
        """Check if user role and step are allowed. Raises on denial."""
        binding = self.catalog.get(internal_name)
        if not binding or not binding.enabled:
            raise PolicyDeniedError(f"Tool '{internal_name}' is not enabled")
        if binding.risk_level == RiskLevel.D:
            raise PolicyDeniedError(f"Tool '{internal_name}' is forbidden (risk level D)")
        if binding.risk_level == RiskLevel.C and user_role != "admin":
            raise PolicyDeniedError(f"Tool '{internal_name}' requires admin approval")
        if user_role not in binding.allowed_roles:
            raise PolicyDeniedError(f"Role '{user_role}' not authorized for '{internal_name}'")
        if ecml_step is not None and binding.ecml_steps and ecml_step not in binding.ecml_steps:
            raise PolicyDeniedError(f"Tool '{internal_name}' not allowed in ECML step {ecml_step}")
        return True