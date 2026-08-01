"""Policy Store — versioned policy persistence with publish and rollback.

Policy versions are stored as YAML files (one per version) inside
``policy_dir``. The currently active version is recorded in ``active.txt``.
Rollback only changes which version is active for *future* decisions; it does
not alter already-recorded decision history.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .policy_engine import PolicyRule, build_default_rules

logger = logging.getLogger(__name__)

_ACTIVE_MARKER = "active.txt"


class PolicyVersion(BaseModel):
    """A versioned bundle of policy rules."""

    version: str
    description: str = ""
    rules: list[PolicyRule] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = False


class PolicyStore:
    """Filesystem-backed store of versioned policies."""

    def __init__(self, policy_dir: str = "policies"):
        self.policy_dir = Path(policy_dir)
        self.policy_dir.mkdir(parents=True, exist_ok=True)
        self._active_path = self.policy_dir / _ACTIVE_MARKER
        logger.info("PolicyStore initialized at %s", self.policy_dir)
        # Seed a default v1.0 when the store is empty so the engine has a
        # loadable active version out of the box.
        if not self._list_version_files():
            self._seed_default_version()

    # ── public API ───────────────────────────────────────────────────────

    def load_version(self, version: str) -> PolicyVersion:
        """Load a specific policy version from its YAML/JSON file."""
        self._validate_version(version)
        path = self._find_version_file(version)
        if path is None:
            logger.warning("Policy version %s not found", version)
            raise FileNotFoundError(f"Policy version {version!r} not found in {self.policy_dir}")
        parsed = self._parse_policy_file(path)
        parsed.is_active = version == self._read_active_marker()
        logger.info("Loaded policy version %s from %s (rules=%d)", version, path.name, len(parsed.rules))
        return parsed

    def get_active_version(self) -> PolicyVersion:
        """Get the currently active policy version.

        Raises ``LookupError`` when no version has been published.
        """
        active = self._read_active_marker()
        if active is None:
            logger.warning("No active policy version recorded")
            raise LookupError("No active policy version has been published")
        version = self.load_version(active)
        version.is_active = True
        return version

    def publish_version(self, version: PolicyVersion) -> None:
        """Persist ``version`` and mark it as the active version."""
        self._validate_version(version.version)
        path = self._version_file_path(version.version)
        version.is_active = True
        version.created_at = version.created_at or datetime.now(timezone.utc)
        self._write_version_file(version, path)
        self._write_active_marker(version.version)
        logger.info(
            "Published policy version %s (rules=%d) as active",
            version.version,
            len(version.rules),
        )

    def rollback(self, target_version: str) -> None:
        """Roll back to a previous version.

        Only affects future decisions; already-recorded decisions keep their
        original ``policy_version`` stamp.
        """
        self._validate_version(target_version)
        path = self._find_version_file(target_version)
        if path is None:
            logger.warning("Rollback target %s not found", target_version)
            raise FileNotFoundError(f"Policy version {target_version!r} not found")
        previous = self._read_active_marker()
        self._write_active_marker(target_version)
        logger.info(
            "Rolled back active policy %s -> %s (past decisions unaffected)",
            previous,
            target_version,
        )

    def list_versions(self) -> list[PolicyVersion]:
        """List all available policy versions, active first."""
        versions: list[PolicyVersion] = []
        active = self._read_active_marker()
        for path in self._list_version_files():
            try:
                parsed = self._parse_policy_file(path)
            except Exception:  # noqa: BLE001 — skip corrupt files, log and continue
                logger.exception("Failed to parse policy file %s; skipping", path)
                continue
            parsed.is_active = parsed.version == active
            versions.append(parsed)
        versions.sort(key=lambda v: (not v.is_active, v.version))
        logger.info("Listed %d policy versions (active=%s)", len(versions), active)
        return versions

    # ── internals ────────────────────────────────────────────────────────

    _VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

    def _validate_version(self, version: str) -> None:
        """Reject version strings that could escape ``policy_dir`` via path traversal."""
        if not isinstance(version, str) or not self._VERSION_PATTERN.match(version):
            raise ValueError(f"Invalid version: {version!r}")

    def _parse_policy_file(self, path: Path) -> PolicyVersion:
        """Parse a YAML or JSON policy file into a ``PolicyVersion``."""
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Policy file {path} did not contain a mapping")
        return PolicyVersion(**data)

    def _find_version_file(self, version: str) -> Path | None:
        self._validate_version(version)
        for ext in (".yaml", ".yml", ".json"):
            candidate = self.policy_dir / f"{version}{ext}"
            if candidate.exists():
                return candidate
        return None

    def _version_file_path(self, version: str) -> Path:
        return self.policy_dir / f"{version}.yaml"

    def _list_version_files(self) -> list[Path]:
        return sorted(
            p
            for p in self.policy_dir.iterdir()
            if p.is_file() and p.suffix.lower() in (".yaml", ".yml", ".json")
        )

    def _read_active_marker(self) -> str | None:
        if not self._active_path.exists():
            return None
        content = self._active_path.read_text(encoding="utf-8").strip()
        return content or None

    def _write_active_marker(self, version: str) -> None:
        self._active_path.write_text(version, encoding="utf-8")

    def _write_version_file(self, version: PolicyVersion, path: Path) -> None:
        data = version.model_dump(mode="json")
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def _seed_default_version(self) -> None:
        """Create an initial ``v1.0`` policy from the built-in default rules."""
        default = PolicyVersion(
            version="v1.0",
            description="Built-in default policy (auto-seeded)",
            rules=list(build_default_rules()),
            is_active=True,
        )
        self._write_version_file(default, self._version_file_path("v1.0"))
        self._write_active_marker("v1.0")
        logger.info("Seeded default policy version v1.0 with %d rules", len(default.rules))
