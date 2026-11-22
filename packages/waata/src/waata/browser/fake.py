"""Scriptable C3 adapter for tests without a Playwright dependency."""

from collections.abc import Awaitable, Callable, Iterable, Mapping

from pydantic import BaseModel

from waata.artifacts import ArtifactStore
from waata.core.tools import ToolContext, ToolResult, ToolSpec

from .adapter import ACTION_NAMES
from .models import BROWSER_TOOLS, FillArgs
from .policy import Origin, sanitize

FakeToolHandler = Callable[
    [str, BaseModel, ToolContext, ArtifactStore], Awaitable[ToolResult]
]


class FakeBrowserAdapter:
    """Invoke a test's scripted handler through the production input schemas."""

    def __init__(
        self,
        handler: FakeToolHandler,
        *,
        allowed_origins: Iterable[str],
        credential_refs: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        self._handler = handler
        self._origins = frozenset(Origin.from_url(url) for url in allowed_origins)
        self._credential_refs = {
            key: tuple(refs) for key, refs in (credential_refs or {}).items()
        }

    def validate_target(self, url: str) -> None:
        if Origin.from_url(url) not in self._origins:
            raise ValueError("browser target is outside the configured scope")

    def secret_refs(self, credential_ref: str | None) -> tuple[str, ...]:
        if credential_ref is None:
            return ()
        if credential_ref not in self._credential_refs:
            raise ValueError("credential fixture is not available")
        return self._credential_refs[credential_ref]

    def sanitize(self, value: str, credential_ref: str | None = None) -> str:
        return sanitize(value, self.secret_refs(credential_ref))

    async def open_case(
        self,
        target_url: str,
        *,
        credential_ref: str | None,
        artifact_store: ArtifactStore,
    ) -> "FakeBrowserSession":
        self.validate_target(target_url)
        return FakeBrowserSession(
            self._handler,
            artifact_store,
            Origin.from_url(target_url),
            self.secret_refs(credential_ref),
        )


class FakeBrowserSession:
    def __init__(
        self,
        handler: FakeToolHandler,
        store: ArtifactStore,
        origin: Origin,
        secret_refs: tuple[str, ...],
    ) -> None:
        self._script = handler
        self._store = store
        self._origin = origin
        self._url: str | None = None
        self.secret_refs = secret_refs
        self.closed = False
        self.revision = 0
        self.observation_stale = True
        self.latest_observation: dict | None = None
        self.tools = tuple(
            ToolSpec(name, description, model, self._handler(name))
            for name, description, model in BROWSER_TOOLS
        )

    def _handler(self, name: str):
        async def execute(args: BaseModel, context: ToolContext) -> ToolResult:
            if self.closed:
                return ToolResult.failed(
                    "SESSION_NOT_READY", "The fake session is closed."
                )
            if name == "browser.navigate" and not self._origin.permits(args.url):
                return ToolResult.failed(
                    "TARGET_NOT_ALLOWED", "The target is outside the case origin."
                )
            if (
                isinstance(args, FillArgs)
                and args.secret_ref is not None
                and args.secret_ref not in self.secret_refs
            ):
                return ToolResult.failed(
                    "SECRET_NOT_AVAILABLE", "The test secret is unavailable."
                )
            if name in ACTION_NAMES:
                if context.reserve_action is not None and not context.reserve_action():
                    return ToolResult.failed(
                        "BUDGET_EXCEEDED", "The browser action budget is exhausted."
                    )
                self.observation_stale = True
            result = await self._script(name, args, context, self._store)
            if result.success and result.data is not None:
                if name == "browser.observe":
                    self.latest_observation = result.data
                    self.observation_stale = False
                elif name in ACTION_NAMES:
                    url = result.data.get("url", self._url)
                    if name == "browser.navigate" or url != self._url:
                        self.revision += 1
                    self._url = url
            return result

        return execute

    def sanitize(self, value: str) -> str:
        return sanitize(value, self.secret_refs)

    async def close(self) -> None:
        self.closed = True
