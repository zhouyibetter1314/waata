"""Trusted deployment configuration for C1/C2 authorization and NFR-004."""

import json
import os
import re
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from waata.browser import CredentialField, LocatorSpec
from waata.browser.policy import Origin, redaction_variants, safe_url, sanitize
from waata.llm.openai_like import validate_thinking_configuration
from waata.orchestrator.config import EngineConfig

LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")
LOCAL_WEB_ORIGINS = tuple(
    f"http://{host}:{port}" for host in LOCAL_HOSTS for port in (5173, 8000)
)
DEFAULT_ARTIFACT_LIMITS = {
    "observation": 512 * 1024,
    "screenshot": 8 * 1024 * 1024,
    "playwright_trace": 32 * 1024 * 1024,
    "test_report": 4 * 1024 * 1024,
}
Action = Literal[
    "browser.navigate", "browser.click", "browser.fill", "browser.select_option"
]


class TargetNotAllowed(ValueError):
    pass


class CredentialNotAllowed(ValueError):
    pass


class CredentialUnavailable(ValueError):
    pass


class CredentialSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    env: str
    locator: LocatorSpec

    @field_validator("env")
    @classmethod
    def validate_env(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", value):
            raise ValueError("Expected the name of a trusted environment variable")
        return value


class TargetPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    origin: str
    owners: list[str]
    actions: list[Action] = []
    credentials: dict[str, dict[str, CredentialSource]] = {}
    css_selectors: list[str] = []
    websocket_paths: list[str] = []
    screenshot_mask_selectors: list[str] = []
    allow_screenshots: bool = False

    @field_validator("origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        origin = Origin.from_url(value)
        parts = urlsplit(value)
        if parts.path not in {"", "/"} or parts.query or parts.fragment:
            raise ValueError("A target policy requires an origin")
        host = f"[{origin.host}]" if ":" in origin.host else origin.host
        return f"{origin.scheme}://{host}:{origin.port}"

    @field_validator("owners")
    @classmethod
    def validate_owners(cls, owners: list[str]) -> list[str]:
        if not owners or any(not owner.strip() for owner in owners):
            raise ValueError("A target policy requires explicit owners")
        return owners


class TargetPolicies:
    def __init__(
        self,
        policies: tuple[TargetPolicy, ...] = (),
        values: dict[str, str] | None = None,
    ) -> None:
        self._targets = {Origin.from_url(policy.origin): policy for policy in policies}
        if len(self._targets) != len(policies):
            raise ValueError("Duplicate target origin")
        values = os.environ if values is None else values
        self._values = {}
        markers = set()
        for policy in policies:
            for ref, sources in policy.credentials.items():
                if (
                    not ref.strip()
                    or not sources
                    or any(not k.strip() for k in sources)
                ):
                    raise ValueError("Credential sets need nonempty references")
                markers.add(ref)
                markers.update(sources)
                for source in sources.values():
                    if source.env in values and values[source.env]:
                        self._values[source.env] = values[source.env]
                        markers.add(values[source.env])
        self._markers = redaction_variants(markers)

    def authorize(
        self, owner_id: str, target_url: str, credential_ref: str | None
    ) -> TargetPolicy:
        try:
            target = self._targets[Origin.from_url(target_url)]
        except (KeyError, ValueError):
            raise TargetNotAllowed(
                "This target is outside the allowed origins"
            ) from None
        if owner_id not in target.owners:
            raise TargetNotAllowed("This target is outside the allowed origins")
        if credential_ref is not None and credential_ref not in target.credentials:
            raise CredentialNotAllowed(
                "This credential set is outside the target policy"
            )
        return target

    def credential_sets(
        self, target: TargetPolicy, credential_ref: str | None
    ) -> dict[str, dict[str, CredentialField]]:
        if credential_ref is None:
            return {}
        try:
            fields = {
                name: CredentialField(self._values[source.env], source.locator)
                for name, source in target.credentials[credential_ref].items()
            }
        except KeyError:
            raise CredentialUnavailable(
                "The authorized credentials are unavailable"
            ) from None
        return {credential_ref: fields}

    def sanitize(self, value: str) -> str:
        return sanitize(value, self._markers)

    def public_url(self, value: str) -> str:
        return safe_url(value, self._markers)


@dataclass(frozen=True)
class Settings:
    database_dsn: str = field(default="", repr=False)
    artifact_root: Path = Path("artifacts/platform")
    artifact_retention_seconds: int = 7 * 24 * 60 * 60
    artifact_max_bytes: dict[str, int] = field(
        default_factory=lambda: DEFAULT_ARTIFACT_LIMITS.copy()
    )
    auth_mode: Literal["disabled", "local", "gateway"] = "disabled"
    local_owner_id: str = "local"
    allowed_hosts: tuple[str, ...] = tuple(
        f"{host}:{port}" for host in LOCAL_HOSTS for port in (5173, 8000)
    )
    web_origins: tuple[str, ...] = LOCAL_WEB_ORIGINS
    gateway_token: str | None = field(default=None, repr=False)
    policy: TargetPolicies = field(default_factory=TargetPolicies)
    engine_config: EngineConfig = field(default_factory=EngineConfig)
    sse_poll_seconds: float = 0.25
    sse_keepalive_seconds: float = 15
    worker_poll_seconds: float = 0.25
    worker_heartbeat_seconds: float = 2
    worker_lease_seconds: float = 15
    worker_shutdown_seconds: float = 15
    worker_concurrency: int = 2
    allow_headful: bool = False
    model_base_url: str | None = None
    model_name: str | None = None
    model_enable_thinking: bool | None = None
    model_api_key: str | None = field(default=None, repr=False)
    langfuse_base_url: str | None = None
    langfuse_public_key: str | None = field(default=None, repr=False)
    langfuse_secret_key: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        try:
            validate_thinking_configuration(
                self.model_base_url, self.model_enable_thinking
            )
        except ValueError as exc:
            raise ValueError(f"Invalid WAATA_MODEL_ENABLE_THINKING: {exc}") from None
        if self.auth_mode not in {"disabled", "local", "gateway"}:
            raise ValueError("Invalid WAATA_AUTH_MODE")
        if self.auth_mode == "gateway" and not self.gateway_token:
            raise ValueError("Gateway mode requires WAATA_GATEWAY_TOKEN")
        if not self.local_owner_id.strip() or not self.allowed_hosts:
            raise ValueError("An owner and an explicit Host allowlist are required")
        timing = (
            self.sse_poll_seconds,
            self.sse_keepalive_seconds,
            self.worker_poll_seconds,
            self.worker_heartbeat_seconds,
            self.worker_lease_seconds,
            self.worker_shutdown_seconds,
        )
        if any(not isfinite(value) or value <= 0 for value in timing):
            raise ValueError("Polling, heartbeat and timeout values must be positive")
        if self.worker_heartbeat_seconds * 2 >= self.worker_lease_seconds:
            raise ValueError("The lease must exceed two heartbeat intervals")
        if self.worker_concurrency <= 0 or self.artifact_retention_seconds <= 0:
            raise ValueError("Concurrency and artifact retention must be positive")
        if not self.artifact_max_bytes.keys() <= DEFAULT_ARTIFACT_LIMITS.keys() or any(
            type(limit) is not int or limit <= 0
            for limit in self.artifact_max_bytes.values()
        ):
            raise ValueError(
                "Artifact limits require contract kinds and positive integers"
            )

    @classmethod
    def from_env(cls) -> "Settings":
        values = {k: v for k, v in dotenv_values(".env").items() if v is not None}
        values.update(os.environ)
        defaults = cls()

        def csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
            return (
                tuple(item.strip() for item in values[name].split(",") if item.strip())
                if name in values
                else default
            )

        policy_path = values.get("WAATA_TARGET_POLICY")
        try:
            raw = json.loads(Path(policy_path).read_text()) if policy_path else []
            if not isinstance(raw, list):
                raise ValueError
            policy = TargetPolicies(
                tuple(TargetPolicy.model_validate(item) for item in raw), values
            )
            engine_config = EngineConfig.model_validate_json(
                values.get("WAATA_ENGINE_CONFIG", "{}"), strict=True
            )
            limits = DEFAULT_ARTIFACT_LIMITS | json.loads(
                values.get("WAATA_ARTIFACT_MAX_BYTES", "{}")
            )
        except (OSError, ValueError, TypeError, ValidationError):
            raise ValueError(
                "Invalid WAATA target policy, engine or artifact configuration"
            ) from None

        def number(name: str, default: int | float, parse):
            try:
                return parse(values.get(name, default))
            except ValueError:
                raise ValueError(f"Invalid numeric configuration for {name}") from None

        thinking = values.get("WAATA_MODEL_ENABLE_THINKING", "").strip().lower()
        if thinking not in {"", "false"}:
            raise ValueError(
                "WAATA_MODEL_ENABLE_THINKING must be false or unset; enabling thinking is unsupported"
            )
        allow_headful = values.get("WAATA_ALLOW_HEADFUL", "false").lower()
        if allow_headful not in {"true", "false"}:
            raise ValueError("WAATA_ALLOW_HEADFUL must be true or false")
        return cls(
            database_dsn=values.get("WAATA_DATABASE_DSN", ""),
            artifact_root=Path(
                values.get("WAATA_ARTIFACT_ROOT", defaults.artifact_root)
            ),
            artifact_retention_seconds=number(
                "WAATA_ARTIFACT_RETENTION_SECONDS",
                defaults.artifact_retention_seconds,
                int,
            ),
            artifact_max_bytes=limits,
            auth_mode=values.get("WAATA_AUTH_MODE", defaults.auth_mode),
            local_owner_id=values.get("WAATA_LOCAL_OWNER_ID", defaults.local_owner_id),
            allowed_hosts=csv("WAATA_ALLOWED_HOSTS", defaults.allowed_hosts),
            web_origins=csv("WAATA_WEB_ORIGINS", defaults.web_origins),
            gateway_token=values.get("WAATA_GATEWAY_TOKEN") or None,
            policy=policy,
            engine_config=engine_config,
            sse_poll_seconds=number(
                "WAATA_SSE_POLL_SECONDS", defaults.sse_poll_seconds, float
            ),
            sse_keepalive_seconds=number(
                "WAATA_SSE_KEEPALIVE_SECONDS", defaults.sse_keepalive_seconds, float
            ),
            worker_poll_seconds=number(
                "WAATA_WORKER_POLL_SECONDS", defaults.worker_poll_seconds, float
            ),
            worker_heartbeat_seconds=number(
                "WAATA_WORKER_HEARTBEAT_SECONDS",
                defaults.worker_heartbeat_seconds,
                float,
            ),
            worker_lease_seconds=number(
                "WAATA_WORKER_LEASE_SECONDS", defaults.worker_lease_seconds, float
            ),
            worker_shutdown_seconds=number(
                "WAATA_WORKER_SHUTDOWN_SECONDS", defaults.worker_shutdown_seconds, float
            ),
            worker_concurrency=number(
                "WAATA_WORKER_CONCURRENCY", engine_config.max_concurrent_runs, int
            ),
            allow_headful=allow_headful == "true",
            model_base_url=values.get("WAATA_MODEL_BASE_URL")
            or values.get("DEEPSEEK_BASE_URL")
            or None,
            model_name=values.get("WAATA_MODEL_NAME")
            or values.get("DEEPSEEK_MODEL")
            or None,
            model_enable_thinking=False if thinking == "false" else None,
            model_api_key=values.get("WAATA_MODEL_API_KEY")
            or values.get("DEEPSEEK_API_KEY")
            or None,
            langfuse_base_url=values.get("LANGFUSE_BASE_URL") or None,
            langfuse_public_key=values.get("LANGFUSE_PUBLIC_KEY") or None,
            langfuse_secret_key=values.get("LANGFUSE_SECRET_KEY") or None,
        )
