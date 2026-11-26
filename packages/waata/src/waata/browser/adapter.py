"""Run-scoped browser interfaces and Playwright session assembly (FR-003)."""

import asyncio
from collections.abc import Coroutine, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from waata.artifacts import ArtifactStore
from waata.core.tools import ToolSpec

from .models import CssLocator
from .policy import CredentialField, Origin, normalized_host, redactions, sanitize

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext

ACTION_NAMES = frozenset(
    {"browser.navigate", "browser.click", "browser.fill", "browser.select_option"}
)


class BrowserSession(Protocol):
    @property
    def tools(self) -> tuple[ToolSpec, ...]: ...

    @property
    def secret_refs(self) -> tuple[str, ...]: ...

    @property
    def latest_observation(self) -> dict | None: ...

    @property
    def observation_stale(self) -> bool: ...

    @property
    def revision(self) -> int: ...

    def sanitize(self, value: str) -> str: ...

    async def close(self) -> None: ...


class BrowserAdapter(Protocol):
    def validate_target(self, url: str) -> None: ...

    def secret_refs(self, credential_ref: str | None) -> tuple[str, ...]: ...

    def sanitize(self, value: str, credential_ref: str | None = None) -> str: ...

    async def open_case(
        self,
        target_url: str,
        *,
        credential_ref: str | None,
        artifact_store: ArtifactStore,
    ) -> BrowserSession: ...


class BrowserSetupCleanupError(RuntimeError):
    """A partially opened browser session did not clean up within its deadline."""


@dataclass(frozen=True)
class BrowserLimits:
    default_timeout_ms: int = 5_000
    max_timeout_ms: int = 15_000
    max_observation_chars: int = 6_000
    max_elements: int = 40
    max_artifact_bytes: int = 1_000_000
    max_screenshot_pixels: int = 4_000_000
    setup_cleanup_timeout_ms: int = 3_000

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 1 for value in vars(self).values()):
            raise ValueError("browser limits must be positive integers")
        if self.default_timeout_ms > self.max_timeout_ms:
            raise ValueError("browser default timeout exceeds maximum")


class PlaywrightAdapter:
    """Use a caller-owned Chromium browser with one approved origin per case."""

    def __init__(
        self,
        *,
        browser: "Browser",
        allowed_hosts: Iterable[str] = (),
        allowed_origins: Iterable[str] = (),
        allowed_actions: Iterable[str] = ACTION_NAMES,
        allowed_css_selectors: Iterable[str] = (),
        allowed_websocket_paths: Iterable[str] = (),
        credential_sets: Mapping[str, Mapping[str, CredentialField]] | None = None,
        screenshot_mask_selectors: Iterable[str] = (),
        allow_screenshots: bool = False,
        limits: BrowserLimits | None = None,
    ) -> None:
        self._browser = browser
        self._hosts = frozenset(normalized_host(host) for host in allowed_hosts)
        self._origins = frozenset(Origin.from_url(url) for url in allowed_origins)
        self._actions = frozenset(allowed_actions)
        if not self._actions <= ACTION_NAMES:
            raise ValueError("unrecognized browser action in allowlist")
        self._selectors = frozenset(allowed_css_selectors)
        self._websocket_paths = frozenset(allowed_websocket_paths)
        if any(
            not path.startswith("/") or path.startswith("//")
            for path in self._websocket_paths
        ):
            raise ValueError(
                "WebSocket allowlist entries must be absolute application paths"
            )
        self._credential_sets = {
            name: dict(fields) for name, fields in (credential_sets or {}).items()
        }
        self._all_fields = tuple(
            credential
            for fields in self._credential_sets.values()
            for credential in fields.values()
        )
        for fields in self._credential_sets.values():
            if any(not isinstance(ref, str) or not ref.strip() for ref in fields):
                raise ValueError(
                    "credential field references must be non-empty strings"
                )
        self._all_markers = tuple(
            sorted(
                {
                    marker
                    for fields in self._credential_sets.values()
                    for marker in redactions(fields)
                },
                key=len,
                reverse=True,
            )
        )
        for credential in self._all_fields:
            locator = credential.locator
            if isinstance(locator, CssLocator) and locator.value not in self._selectors:
                raise ValueError("credential CSS selector must be allowed explicitly")
        self._mask_selectors = tuple(screenshot_mask_selectors)
        self._allow_screenshots = allow_screenshots
        self._limits = limits or BrowserLimits()
        self._setup_cleanups: set[asyncio.Task[None]] = set()

    @property
    def planning_css_selectors(self) -> tuple[str, ...]:
        """Exact locators already granted to this adapter, not model-supplied CSS."""
        return tuple(sorted(self._selectors)[:32])

    def validate_target(self, url: str) -> None:
        origin = Origin.from_url(url)
        default_port = 443 if origin.scheme == "https" else 80
        named_host = origin.host in self._hosts and origin.port == default_port
        if origin not in self._origins and not named_host:
            raise ValueError("browser target is outside the configured scope")

    def _fields(self, credential_ref: str | None) -> dict[str, CredentialField]:
        if credential_ref is None:
            return {}
        if credential_ref not in self._credential_sets:
            raise ValueError("credential fixture is not available")
        return self._credential_sets[credential_ref]

    def secret_refs(self, credential_ref: str | None) -> tuple[str, ...]:
        return tuple(self._fields(credential_ref))

    def sanitize(self, value: str, credential_ref: str | None = None) -> str:
        return sanitize(value, self._all_markers)

    async def _close_when_created(
        self, opening: asyncio.Task["BrowserContext"]
    ) -> None:
        try:
            context = await opening
        except Exception:
            # The browser did not return a context to clean up.
            return
        await context.close()

    def _forget_cleanup(self, task: asyncio.Task[None]) -> None:
        self._setup_cleanups.discard(task)
        if not task.cancelled():
            task.exception()

    async def _rollback_setup(
        self, cleanup: Coroutine[Any, Any, None], original: BaseException
    ) -> None:
        task = asyncio.create_task(cleanup)
        self._setup_cleanups.add(task)
        task.add_done_callback(self._forget_cleanup)
        try:
            async with asyncio.timeout(self._limits.setup_cleanup_timeout_ms / 1000):
                await asyncio.shield(task)
        except Exception:
            raise BrowserSetupCleanupError("Browser setup cleanup failed") from original

    async def open_case(
        self,
        target_url: str,
        *,
        credential_ref: str | None,
        artifact_store: ArtifactStore,
    ) -> BrowserSession:
        from .session import PlaywrightSession

        self.validate_target(target_url)
        fields = self._fields(credential_ref)
        opening = asyncio.create_task(
            self._browser.new_context(
                accept_downloads=False,
                service_workers="block",
                viewport={"width": 1280, "height": 720},
            )
        )
        try:
            context = await asyncio.shield(opening)
        except asyncio.CancelledError as original:
            # Chromium may allocate the context even when the caller's wait is cancelled.
            await self._rollback_setup(self._close_when_created(opening), original)
            raise
        try:
            page = await context.new_page()
            session = PlaywrightSession(
                context=context,
                page=page,
                origin=Origin.from_url(target_url),
                store=artifact_store,
                fields=fields,
                protected_fields=self._all_fields,
                markers=self._all_markers,
                allowed_actions=self._actions,
                allowed_css_selectors=self._selectors,
                allowed_websocket_paths=self._websocket_paths,
                allow_screenshots=self._allow_screenshots,
                screenshot_mask_selectors=self._mask_selectors,
                limits=self._limits,
            )
            await session.install_guards()
        except BaseException as original:
            await self._rollback_setup(context.close(), original)
            raise
        return session
