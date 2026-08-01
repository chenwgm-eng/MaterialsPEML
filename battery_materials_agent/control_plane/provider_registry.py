"""Provider Registry — external provider catalog with health, quota, and schema drift.

Stores descriptors for LLMs, external services (SCP, Materials Project, AskCos),
DFT, and local tools. Authentication is referenced by environment variable name
(``auth_secret_ref``) — actual API keys are NEVER stored in the registry.

使用 SQLAlchemy Engine；schema 由 alembic 管理（control_plane.providers）。
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import text

from ..db import get_engine


def _to_datetime(value):
    """兼容 psycopg3 返回的 datetime 对象或 ISO 字符串。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)

logger = logging.getLogger(__name__)


class ProviderType(str, Enum):
    """Categories of providers managed by the control plane."""

    LLM = "llm"
    SCP = "scp"
    MATERIALS_PROJECT = "materials_project"
    ASKCOS = "askcos"
    DFT = "dft"
    LOCAL_TOOL = "local_tool"


class ProviderHealth(str, Enum):
    """Health states for a provider."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ProviderDescriptor(BaseModel):
    """Descriptor for a registered provider.

    ``auth_secret_ref`` holds the *name* of the environment variable that
    contains the API key — the key itself is never persisted.
    """

    provider_id: str
    provider_type: ProviderType
    name: str
    endpoint: str
    auth_secret_ref: str
    version: str
    health_status: ProviderHealth = ProviderHealth.UNKNOWN
    health_check_url: str | None = None
    health_check_interval_seconds: int = 300
    last_health_check: datetime | None = None
    quota_limit: dict | None = None
    quota_used: dict = Field(default_factory=dict)
    schema_snapshot: dict | None = None
    data_processing_level: str = "internal"
    fallback_provider_id: str | None = None
    owner: str = "system"
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _parse_json_field(value, default):
    """解析 JSON 字段，兼容 psycopg3 自动反序列化或字符串两种来源。"""
    if value is None:
        return default
    if isinstance(value, str):
        if not value:
            return default
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
    return value


class ProviderRegistry:
    """PostgreSQL-backed registry of external providers.

    Tracks endpoints, auth references, versions, health, quotas, and schema
    snapshots for drift detection. 使用 SQLAlchemy Engine。
    """

    def __init__(self, db_path: str = "data/control_plane.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.db_path = db_path
        self.engine = get_engine()
        self._init_db()
        self._seed_default_providers()

    def _init_db(self) -> None:  # pragma: no cover - 兼容旧调用
        """No-op：表结构由 alembic 管理。"""
        return

    # ── seeding ────────────────────────────────────────────

    def _seed_default_providers(self) -> None:
        """Pre-register built-in providers if not already present.

        Seeds 6 individual SCP providers (each with its own endpoint) plus
        LLM, Materials Project, AskCos, and local DFT providers. All 6 SCP
        providers share the same ``SCP_HUB_API_KEY`` secret reference.

        Existing descriptors are left untouched so runtime state (health,
        quota, schema snapshots) survives restarts.
        """
        scp_base = os.getenv(
            "SCP_BASE_URL", "https://scp.intern-ai.org.cn/api/v1/mcp"
        )
        defaults = [
            ProviderDescriptor(
                provider_id="internlm",
                provider_type=ProviderType.LLM,
                name="InternLM Chat Completions",
                endpoint=os.getenv(
                    "INTERNLM_BASE_URL", "https://chat.intern-ai.org.cn/api/v1"
                ),
                auth_secret_ref="INTERNLM_API_KEY",
                version="v1",
            ),
            ProviderDescriptor(
                provider_id="scp_scitoolagent_chem_31",
                provider_type=ProviderType.SCP,
                name="SciToolAgent-Chem",
                endpoint=f"{scp_base}/31/SciToolAgent-Chem",
                auth_secret_ref="SCP_HUB_API_KEY",
                version="v1",
            ),
            ProviderDescriptor(
                provider_id="scp_scigraph_material_40",
                provider_type=ProviderType.SCP,
                name="SciGraph-Material",
                endpoint=f"{scp_base}/40/SciGraph-Material",
                auth_secret_ref="SCP_HUB_API_KEY",
                version="v1",
            ),
            ProviderDescriptor(
                provider_id="scp_scitoolagent_mat_30",
                provider_type=ProviderType.SCP,
                name="SciToolAgent-Mat",
                endpoint=f"{scp_base}/30/SciToolAgent-Mat",
                auth_secret_ref="SCP_HUB_API_KEY",
                version="v1",
            ),
            ProviderDescriptor(
                provider_id="scp_chem_reaction_24",
                provider_type=ProviderType.SCP,
                name="Chemistry_and_Reaction_Calculations",
                endpoint=f"{scp_base}/24/Chemistry_and_Reaction_Calculations",
                auth_secret_ref="SCP_HUB_API_KEY",
                version="v1",
            ),
            ProviderDescriptor(
                provider_id="scp_origene_pubchem_8",
                provider_type=ProviderType.SCP,
                name="Origene-PubChem",
                endpoint=f"{scp_base}/8/Origene-PubChem",
                auth_secret_ref="SCP_HUB_API_KEY",
                version="v1",
            ),
            ProviderDescriptor(
                provider_id="scp_origene_chembl_4",
                provider_type=ProviderType.SCP,
                name="Origene-ChEMBL",
                endpoint=f"{scp_base}/4/Origene-ChEMBL",
                auth_secret_ref="SCP_HUB_API_KEY",
                version="v1",
            ),
            ProviderDescriptor(
                provider_id="scp_unit_conversion_27",
                provider_type=ProviderType.SCP,
                name="Physical_Quantities_Conversion",
                endpoint=f"{scp_base}/27/Physical_Quantities_Conversion",
                auth_secret_ref="SCP_HUB_API_KEY",
                version="v1",
            ),
            ProviderDescriptor(
                provider_id="scp_data_analysis_26",
                provider_type=ProviderType.SCP,
                name="Data_processing_and_statistical_analysis",
                endpoint=f"{scp_base}/26/Data_processing_and_statistical_analysis",
                auth_secret_ref="SCP_HUB_API_KEY",
                version="v1",
            ),
            ProviderDescriptor(
                provider_id="scp_intern_agent_28",
                provider_type=ProviderType.SCP,
                name="InternAgent",
                endpoint=f"{scp_base}/28/InternAgent",
                auth_secret_ref="SCP_HUB_API_KEY",
                version="v1",
            ),
            ProviderDescriptor(
                provider_id="scp_scigraph_37",
                provider_type=ProviderType.SCP,
                name="SciGraph",
                endpoint=f"{scp_base}/37/SciGraph",
                auth_secret_ref="SCP_HUB_API_KEY",
                version="v1",
            ),
            ProviderDescriptor(
                provider_id="materials_project",
                provider_type=ProviderType.MATERIALS_PROJECT,
                name="Materials Project API",
                endpoint=os.getenv("MP_BASE_URL", "https://api.materialsproject.org"),
                auth_secret_ref="MP_API_KEY",
                version="v1",
            ),
            ProviderDescriptor(
                provider_id="askcos",
                provider_type=ProviderType.ASKCOS,
                name="AskCos Retrosynthesis",
                endpoint=os.getenv("ASKCOS_BASE_URL", "http://localhost:5000"),
                auth_secret_ref="ASKCOS_API_KEY",
                version="v1",
            ),
            ProviderDescriptor(
                provider_id="local_dft",
                provider_type=ProviderType.DFT,
                name="Local DFT Runner",
                endpoint="local://dft",
                auth_secret_ref="",
                version="v1",
            ),
        ]
        for descriptor in defaults:
            if self.get(descriptor.provider_id) is None:
                self.register(descriptor)
        logger.info(
            "ProviderRegistry seeded with %d default providers", len(defaults)
        )

    # ── CRUD ───────────────────────────────────────────────

    def register(self, descriptor: ProviderDescriptor) -> ProviderDescriptor:
        """Register a new provider or update an existing one."""
        if descriptor.health_check_url:
            self._validate_health_check_url(descriptor.health_check_url)
        descriptor.updated_at = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO control_plane.providers
                       (provider_id, provider_type, name, endpoint, auth_secret_ref,
                        version, health_status, health_check_url,
                        health_check_interval_seconds, last_health_check,
                        quota_limit_json, quota_used_json, schema_snapshot_json,
                        data_processing_level, fallback_provider_id, owner, enabled,
                        created_at, updated_at)
                       VALUES (:provider_id, :provider_type, :name, :endpoint, :auth_secret_ref,
                               :version, :health_status, :health_check_url,
                               :health_check_interval_seconds, :last_health_check,
                               CAST(:quota_limit_json AS JSONB), CAST(:quota_used_json AS JSONB),
                               CAST(:schema_snapshot_json AS JSONB),
                               :data_processing_level, :fallback_provider_id, :owner, :enabled,
                               :created_at, :updated_at)
                       ON CONFLICT(provider_id) DO UPDATE SET
                         provider_type = EXCLUDED.provider_type,
                         name = EXCLUDED.name,
                         endpoint = EXCLUDED.endpoint,
                         auth_secret_ref = EXCLUDED.auth_secret_ref,
                         version = EXCLUDED.version,
                         health_status = EXCLUDED.health_status,
                         health_check_url = EXCLUDED.health_check_url,
                         health_check_interval_seconds = EXCLUDED.health_check_interval_seconds,
                         last_health_check = EXCLUDED.last_health_check,
                         quota_limit_json = EXCLUDED.quota_limit_json,
                         quota_used_json = EXCLUDED.quota_used_json,
                         schema_snapshot_json = EXCLUDED.schema_snapshot_json,
                         data_processing_level = EXCLUDED.data_processing_level,
                         fallback_provider_id = EXCLUDED.fallback_provider_id,
                         owner = EXCLUDED.owner,
                         enabled = EXCLUDED.enabled,
                         updated_at = EXCLUDED.updated_at"""
                ),
                {
                    "provider_id": descriptor.provider_id,
                    "provider_type": descriptor.provider_type.value,
                    "name": descriptor.name,
                    "endpoint": descriptor.endpoint,
                    "auth_secret_ref": descriptor.auth_secret_ref,
                    "version": descriptor.version,
                    "health_status": descriptor.health_status.value,
                    "health_check_url": descriptor.health_check_url,
                    "health_check_interval_seconds": descriptor.health_check_interval_seconds,
                    "last_health_check": descriptor.last_health_check.isoformat()
                    if descriptor.last_health_check
                    else None,
                    "quota_limit_json": json.dumps(descriptor.quota_limit)
                    if descriptor.quota_limit is not None
                    else None,
                    "quota_used_json": json.dumps(descriptor.quota_used),
                    "schema_snapshot_json": json.dumps(descriptor.schema_snapshot)
                    if descriptor.schema_snapshot is not None
                    else None,
                    "data_processing_level": descriptor.data_processing_level,
                    "fallback_provider_id": descriptor.fallback_provider_id,
                    "owner": descriptor.owner,
                    "enabled": descriptor.enabled,
                    "created_at": descriptor.created_at.isoformat(),
                    "updated_at": descriptor.updated_at.isoformat(),
                },
            )
        stored = self.get(descriptor.provider_id)
        logger.info(
            "Registered provider %s (%s)",
            descriptor.provider_id,
            descriptor.provider_type.value,
        )
        return stored if stored is not None else descriptor

    def unregister(self, provider_id: str) -> None:
        """Remove a provider from the registry."""
        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM control_plane.providers WHERE provider_id = :provider_id"),
                {"provider_id": provider_id},
            )
        logger.info("Unregistered provider %s", provider_id)

    def get(self, provider_id: str) -> ProviderDescriptor | None:
        """Get a provider by ID, or ``None`` if not found."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT provider_id, provider_type, name, endpoint, auth_secret_ref,
                              version, health_status, health_check_url,
                              health_check_interval_seconds, last_health_check,
                              quota_limit_json, quota_used_json, schema_snapshot_json,
                              data_processing_level, fallback_provider_id, owner, enabled,
                              created_at, updated_at
                       FROM control_plane.providers WHERE provider_id = :provider_id"""
                ),
                {"provider_id": provider_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_descriptor(row)

    def list_providers(
        self,
        provider_type: ProviderType | None = None,
        health: ProviderHealth | None = None,
    ) -> list[ProviderDescriptor]:
        """List providers, optionally filtered by type and/or health."""
        query = (
            "SELECT provider_id, provider_type, name, endpoint, auth_secret_ref, "
            "version, health_status, health_check_url, health_check_interval_seconds, "
            "last_health_check, quota_limit_json, quota_used_json, schema_snapshot_json, "
            "data_processing_level, fallback_provider_id, owner, enabled, "
            "created_at, updated_at FROM control_plane.providers WHERE 1=1"
        )
        params: dict[str, Any] = {}
        if provider_type is not None:
            query += " AND provider_type = :provider_type"
            params["provider_type"] = provider_type.value
        if health is not None:
            query += " AND health_status = :health_status"
            params["health_status"] = health.value
        query += " ORDER BY provider_id"
        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).fetchall()
        return [self._row_to_descriptor(row) for row in rows]

    # ── health ─────────────────────────────────────────────

    def is_healthy(self, provider_id: str) -> bool:
        """Return ``True`` if the provider is currently healthy."""
        descriptor = self.get(provider_id)
        if descriptor is None:
            return False
        return descriptor.health_status == ProviderHealth.HEALTHY

    def update_health(self, provider_id: str, health: ProviderHealth) -> None:
        """Update a provider's health status and stamp ``last_health_check``."""
        now = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE control_plane.providers
                       SET health_status = :health_status, last_health_check = :last_health_check,
                           updated_at = :updated_at
                       WHERE provider_id = :provider_id"""
                ),
                {
                    "health_status": health.value,
                    "last_health_check": now.isoformat(),
                    "updated_at": now.isoformat(),
                    "provider_id": provider_id,
                },
            )
        logger.info("Provider %s health -> %s", provider_id, health.value)

    def get_fallback(self, provider_id: str) -> str | None:
        """Get the fallback provider ID for a provider, or ``None``."""
        descriptor = self.get(provider_id)
        if descriptor is None:
            return None
        return descriptor.fallback_provider_id

    @staticmethod
    def _validate_health_check_url(url: str) -> None:
        """Validate that ``url`` is safe to probe for health checks."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Invalid URL scheme: {parsed.scheme!r}")
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("Invalid URL: no hostname")
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                raise ValueError(f"Internal/reserved IP not allowed: {hostname}")

    async def check_health(self, provider_id: str) -> ProviderHealth:
        """Perform an HTTP health check against ``health_check_url``."""
        descriptor = self.get(provider_id)
        if descriptor is None:
            logger.warning(
                "Health check requested for unknown provider %s", provider_id
            )
            return ProviderHealth.UNKNOWN
        if not descriptor.health_check_url:
            logger.debug(
                "Provider %s has no health_check_url; skipping", provider_id
            )
            return ProviderHealth.UNKNOWN
        self._validate_health_check_url(descriptor.health_check_url)

        health = ProviderHealth.UNHEALTHY
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(descriptor.health_check_url)
            if 200 <= response.status_code < 300:
                health = ProviderHealth.HEALTHY
            elif 400 <= response.status_code < 500:
                health = ProviderHealth.DEGRADED
            else:
                health = ProviderHealth.UNHEALTHY
        except httpx.HTTPError as exc:
            logger.warning("Health check for %s failed: %s", provider_id, exc)
            health = ProviderHealth.UNHEALTHY
        except Exception as exc:  # noqa: BLE001 — health checks must never crash caller
            logger.exception(
                "Unexpected error during health check for %s: %s",
                provider_id,
                exc,
            )
            health = ProviderHealth.UNHEALTHY

        self.update_health(provider_id, health)
        return health

    # ── handlers ───────────────────────────────────────────

    def get_handler(self, provider_id: str) -> None:
        """Resolve the handler function for a provider (placeholder)."""
        logger.debug("Handler resolution not yet implemented for %s", provider_id)
        return None

    # ── quota ──────────────────────────────────────────────

    def update_quota(self, provider_id: str, category: str, used: float) -> None:
        """Set the used amount for a quota ``category`` on a provider."""
        descriptor = self.get(provider_id)
        if descriptor is None:
            raise ValueError(f"Provider {provider_id!r} not found")
        descriptor.quota_used[category] = used
        now = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE control_plane.providers
                       SET quota_used_json = CAST(:quota_used_json AS JSONB),
                           updated_at = :updated_at
                       WHERE provider_id = :provider_id"""
                ),
                {
                    "quota_used_json": json.dumps(descriptor.quota_used),
                    "updated_at": now.isoformat(),
                    "provider_id": provider_id,
                },
            )

    def check_quota(self, provider_id: str, category: str, amount: float = 1) -> bool:
        """Return ``True`` if ``amount`` fits within the quota for ``category``."""
        descriptor = self.get(provider_id)
        if descriptor is None:
            return False
        if not descriptor.quota_limit:
            return True
        limit = descriptor.quota_limit.get(category)
        if limit is None:
            return True
        used = descriptor.quota_used.get(category, 0.0)
        return used + amount <= limit

    # ── schema drift ───────────────────────────────────────

    def snapshot_schema(self, provider_id: str, schema: dict) -> None:
        """Save a schema snapshot (e.g., ``tools/list`` result) as drift baseline."""
        now = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE control_plane.providers
                       SET schema_snapshot_json = CAST(:schema_snapshot_json AS JSONB),
                           updated_at = :updated_at
                       WHERE provider_id = :provider_id"""
                ),
                {
                    "schema_snapshot_json": json.dumps(schema, sort_keys=True),
                    "updated_at": now.isoformat(),
                    "provider_id": provider_id,
                },
            )
        logger.info("Schema snapshot saved for provider %s", provider_id)

    def check_schema_drift(self, provider_id: str, current_schema: dict) -> bool:
        """Return ``True`` if ``current_schema`` differs from the stored snapshot."""
        descriptor = self.get(provider_id)
        if descriptor is None or descriptor.schema_snapshot is None:
            return False
        baseline = json.dumps(descriptor.schema_snapshot, sort_keys=True)
        current = json.dumps(current_schema, sort_keys=True)
        drifted = baseline != current
        if drifted:
            logger.warning("Schema drift detected for provider %s", provider_id)
        return drifted

    # ── helpers ────────────────────────────────────────────

    @staticmethod
    def _row_to_descriptor(row) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id=row[0],
            provider_type=ProviderType(row[1]),
            name=row[2],
            endpoint=row[3],
            auth_secret_ref=row[4],
            version=row[5],
            health_status=ProviderHealth(row[6]),
            health_check_url=row[7],
            health_check_interval_seconds=row[8],
            last_health_check=_to_datetime(row[9]),
            quota_limit=_parse_json_field(row[10], default=None),
            quota_used=_parse_json_field(row[11], default={}) or {},
            schema_snapshot=_parse_json_field(row[12], default=None),
            data_processing_level=row[13],
            fallback_provider_id=row[14],
            owner=row[15],
            enabled=bool(row[16]),
            created_at=_to_datetime(row[17]),
            updated_at=_to_datetime(row[18]),
        )
