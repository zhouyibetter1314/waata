"""Isolated Chromium session and the seven registered C3 tools."""

import asyncio
import json
import struct
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin
from uuid import uuid4

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout
from pydantic import BaseModel

from waata.artifacts import ArtifactInput, ArtifactStore
from waata.core.tools import ToolContext, ToolError, ToolResult, ToolSpec

from .adapter import ACTION_NAMES, BrowserLimits
from .models import (
    BROWSER_TOOLS,
    ClickArgs,
    Count,
    CssLocator,
    Exists,
    FillArgs,
    InspectArgs,
    InspectCondition,
    LabelLocator,
    LocatorSpec,
    NavigateArgs,
    ObserveArgs,
    PlaceholderLocator,
    RoleLocator,
    ScreenshotArgs,
    SelectOptionArgs,
    TestIdLocator,
    TextEquals,
    TextLocator,
    TitleEquals,
    ToolArgs,
    UrlEquals,
    Visible,
)
from .observation import COLLECT_CONTROLS, omit_form_values, suggested_locator
from .policy import CredentialField, Origin, safe_url, sanitize

if TYPE_CHECKING:
    from playwright.async_api import (
        BrowserContext,
        Dialog,
        Download,
        ElementHandle,
        Frame,
        Locator,
        Page,
        Route,
        WebSocketRoute,
    )

ERROR_MESSAGES = {
    "INVALID_ARGUMENTS": "The browser arguments are invalid.",
    "TARGET_NOT_ALLOWED": "The browser target is outside the case origin.",
    "ACTION_NOT_ALLOWED": "The operation is outside the configured browser policy.",
    "SECRET_NOT_AVAILABLE": "The test secret is unavailable for this field.",
    "SESSION_NOT_READY": "The case has no navigated browser page.",
    "ELEMENT_NOT_FOUND": "No element matches the locator.",
    "AMBIGUOUS_LOCATOR": "The locator matches multiple elements. Do not retry it unchanged; observe and use a unique test ID or an exact approved CSS locator for the intended control.",
    "ELEMENT_NOT_INTERACTABLE": "The located control is not in the required state.",
    "OPTION_NOT_FOUND": "The requested option is unavailable.",
    "NAVIGATION_FAILED": "The browser could not load the selected page.",
    "OBSERVATION_UNSTABLE": "The page changed while its state was being recorded.",
    "TOOL_TIMEOUT": "The browser tool exceeded its time limit.",
    "BUDGET_EXCEEDED": "The browser action budget is exhausted.",
    "UNSUPPORTED_PAGE_EVENT": "The page opened an unsupported browser interaction.",
    "BROWSER_CLOSED": "The browser page closed unexpectedly.",
    "ARTIFACT_WRITE_FAILED": "The browser evidence could not be registered.",
    "INTERNAL_ERROR": "The browser adapter could not complete the operation.",
}


class BrowserFailure(Exception):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(ERROR_MESSAGES[code])
        self.code = code
        self.retryable = retryable

    def result(self) -> ToolResult:
        return ToolResult(False, error=ToolError(self.code, str(self), self.retryable))


@dataclass(frozen=True)
class Call:
    context: ToolContext
    deadline: float

    def timeout_ms(self) -> float:
        remaining = (self.deadline - asyncio.get_running_loop().time()) * 1000
        if remaining <= 0:
            raise BrowserFailure("TOOL_TIMEOUT")
        return max(1, remaining)


class PlaywrightSession:
    def __init__(
        self,
        *,
        context: "BrowserContext",
        page: "Page",
        origin: Origin,
        store: ArtifactStore,
        fields: dict[str, CredentialField],
        protected_fields: tuple[CredentialField, ...],
        markers: tuple[str, ...],
        allowed_actions: frozenset[str],
        allowed_css_selectors: frozenset[str],
        allowed_websocket_paths: frozenset[str],
        allow_screenshots: bool,
        screenshot_mask_selectors: tuple[str, ...],
        limits: BrowserLimits,
    ) -> None:
        self._context = context
        self._page = page
        self._origin = origin
        self._store = store
        self._fields = fields
        self._protected_fields = protected_fields
        self._markers = markers
        self._actions = allowed_actions
        self._selectors = allowed_css_selectors
        self._websocket_paths = allowed_websocket_paths
        self._screenshot_allowed = allow_screenshots
        self._masks = screenshot_mask_selectors
        self._limits = limits
        self._lock = asyncio.Lock()
        self._closed = False
        self._blocked_navigation = 0
        self._unsupported_events = 0
        self._reported_events = (0, 0)
        self.secret_refs = tuple(fields)
        self.latest_observation: dict | None = None
        self.observation_stale = True
        self.revision = 0
        operations = {
            "browser.observe": self._observe,
            "browser.navigate": self._navigate,
            "browser.click": self._click,
            "browser.fill": self._fill,
            "browser.select_option": self._select,
            "browser.screenshot": self._screenshot,
            "browser.inspect": self._inspect,
        }
        self.tools = tuple(
            ToolSpec(name, description, model, self._handler(name, operations[name]))
            for name, description, model in BROWSER_TOOLS
        )

    def sanitize(self, value: str) -> str:
        return sanitize(value, self._markers)

    async def install_guards(self) -> None:
        self._page.on("framenavigated", self._navigated)
        self._page.on("dialog", self._dismiss_dialog)
        self._page.on("download", self._cancel_download)
        self._context.on("page", self._close_extra_page)
        await self._context.route("**/*", self._guard_request)
        await self._context.route_web_socket("**/*", self._guard_websocket)
        # Playwright routing pauses only the first request of a redirect chain.
        # Chromium also pauses each response before following its Location.
        self._cdp = await self._context.new_cdp_session(self._page)
        self._cdp.on("Fetch.requestPaused", self._guard_redirect)
        await self._cdp.send(
            "Fetch.enable", {"patterns": [{"requestStage": "Response"}]}
        )

    def _navigated(self, frame: "Frame") -> None:
        if frame == self._page.main_frame:
            self.revision += 1
            self.observation_stale = True

    async def _dismiss_dialog(self, dialog: "Dialog") -> None:
        self._unsupported_events += 1
        with suppress(PlaywrightError):
            await dialog.dismiss()

    async def _cancel_download(self, download: "Download") -> None:
        self._unsupported_events += 1
        with suppress(PlaywrightError):
            await download.cancel()

    async def _close_extra_page(self, page: "Page") -> None:
        self._unsupported_events += 1
        with suppress(PlaywrightError):
            await page.close()

    async def _guard_websocket(self, socket: "WebSocketRoute") -> None:
        if self._origin.permits_websocket(socket.url, self._websocket_paths):
            socket.connect_to_server()
            return
        await socket.close(code=1008, reason="Browser policy")

    async def _guard_request(self, route: "Route") -> None:
        request = route.request
        try:
            is_current_frame = request.frame == self._page.main_frame
        except PlaywrightError:
            is_current_frame = False
        if not is_current_frame or not self._origin.permits(request.url):
            if is_current_frame and request.is_navigation_request():
                self._blocked_navigation += 1
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    async def _guard_redirect(self, event: dict) -> None:
        event_id = {"requestId": event["requestId"]}
        try:
            status = event.get("responseStatusCode", 0)
            if status in {301, 302, 303, 307, 308}:
                locations = [
                    header["value"]
                    for header in event.get("responseHeaders", ())
                    if header["name"].lower() == "location"
                ]
                if locations and (
                    len(locations) != 1
                    or not self._origin.permits(
                        urljoin(event["request"]["url"], locations[0])
                    )
                ):
                    if event.get("resourceType") == "Document":
                        self._blocked_navigation += 1
                    await self._cdp.send(
                        "Fetch.failRequest",
                        {**event_id, "errorReason": "BlockedByClient"},
                    )
                    return
            await self._cdp.send("Fetch.continueResponse", event_id)
        except (PlaywrightError, ValueError):
            if not self._closed:
                try:
                    if event.get("resourceType") == "Document":
                        self._blocked_navigation += 1
                    await self._cdp.send(
                        "Fetch.failRequest",
                        {**event_id, "errorReason": "BlockedByClient"},
                    )
                except PlaywrightError:
                    pass

    def _current_url(self, *, navigating: bool = False) -> str:
        actual = self._page.url
        if self._closed:
            raise BrowserFailure("SESSION_NOT_READY")
        if self._page.is_closed():
            raise BrowserFailure("BROWSER_CLOSED")
        if actual == "about:blank":
            if navigating:
                return actual
            raise BrowserFailure("SESSION_NOT_READY")
        if not self._origin.permits(actual):
            raise BrowserFailure("TARGET_NOT_ALLOWED")
        return actual

    def _public_url(self) -> str:
        return safe_url(self._current_url(), self._markers)

    def _pending_failure(self) -> BrowserFailure | None:
        blocked, unsupported = self._reported_events
        self._reported_events = (self._blocked_navigation, self._unsupported_events)
        if self._blocked_navigation != blocked:
            return BrowserFailure("TARGET_NOT_ALLOWED")
        if self._unsupported_events != unsupported:
            return BrowserFailure("UNSUPPORTED_PAGE_EVENT")
        return None

    def _handler(
        self, name: str, operation: Callable[[Any, Call], Awaitable[dict]]
    ) -> Callable[[BaseModel, ToolContext], Awaitable[ToolResult]]:
        async def invoke(args: BaseModel, context: ToolContext) -> ToolResult:
            params: ToolArgs = args.root if isinstance(args, InspectArgs) else args
            requested = params.timeout_ms or self._limits.default_timeout_ms
            if requested > self._limits.max_timeout_ms:
                return BrowserFailure("INVALID_ARGUMENTS").result()
            if name in ACTION_NAMES and name not in self._actions:
                return BrowserFailure("ACTION_NOT_ALLOWED").result()
            deadline = min(
                context.deadline,
                asyncio.get_running_loop().time()
                + min(requested, self._limits.default_timeout_ms) / 1000,
            )
            call = Call(context, deadline)
            try:
                async with asyncio.timeout_at(deadline), self._lock:
                    pending = self._pending_failure()
                    if pending is not None:
                        return pending.result()
                    self._current_url(navigating=name == "browser.navigate")
                    data = await operation(params, call)
                result = ToolResult(True, data=data)
            except BrowserFailure as exc:
                result = exc.result()
            except (TimeoutError, PlaywrightTimeout):
                result = BrowserFailure("TOOL_TIMEOUT").result()
            except PlaywrightError:
                if self._page.is_closed():
                    code = "BROWSER_CLOSED"
                elif name == "browser.navigate":
                    code = "NAVIGATION_FAILED"
                else:
                    code = "INTERNAL_ERROR"
                result = BrowserFailure(code).result()
            pending = self._pending_failure()
            return pending.result() if pending is not None else result

        return invoke

    def _reserve_action(self, call: Call) -> float:
        timeout_ms = call.timeout_ms()
        reserve = call.context.reserve_action
        if reserve is not None and not reserve():
            raise BrowserFailure("BUDGET_EXCEEDED")
        self.observation_stale = True
        return timeout_ms

    def _locator(self, spec: LocatorSpec) -> "Locator":
        if isinstance(spec, RoleLocator):
            return self._page.get_by_role(spec.role, name=spec.name, exact=spec.exact)
        if isinstance(spec, LabelLocator):
            return self._page.get_by_label(spec.value, exact=spec.exact)
        if isinstance(spec, TextLocator):
            return self._page.get_by_text(spec.value, exact=spec.exact)
        if isinstance(spec, PlaceholderLocator):
            return self._page.get_by_placeholder(spec.value, exact=spec.exact)
        if isinstance(spec, TestIdLocator):
            return self._page.get_by_test_id(spec.value)
        if isinstance(spec, CssLocator) and spec.value in self._selectors:
            return self._page.locator(f"css={spec.value}")
        raise BrowserFailure("INVALID_ARGUMENTS")

    async def _single(
        self, locator: "Locator", call: Call, *, wait: bool = False
    ) -> None:
        count = await locator.count()
        if count == 0 and wait:
            # Observe matching elements without picking one as the action target.
            while count == 0:
                remaining = (call.deadline - asyncio.get_running_loop().time()) * 1000
                if remaining <= 10:
                    break
                await asyncio.sleep(min(0.05, (remaining - 5) / 1000))
                count = await locator.count()
        if count == 0:
            raise BrowserFailure("ELEMENT_NOT_FOUND", retryable=True)
        if count > 1:
            raise BrowserFailure("AMBIGUOUS_LOCATOR", retryable=True)

    async def _navigate(self, args: NavigateArgs, call: Call) -> dict:
        if not self._origin.permits(args.url):
            raise BrowserFailure("TARGET_NOT_ALLOWED")
        await self._page.goto(
            args.url, wait_until="domcontentloaded", timeout=self._reserve_action(call)
        )
        return {"action": "navigate", "url": self._public_url()}

    async def _click(self, args: ClickArgs, call: Call) -> dict:
        locator = self._locator(args.locator)
        await self._single(locator, call, wait=True)
        if not await locator.is_visible() or not await locator.is_enabled():
            raise BrowserFailure("ELEMENT_NOT_INTERACTABLE", retryable=True)
        self._current_url()
        await locator.click(timeout=self._reserve_action(call))
        return {"action": "click", "url": self._public_url()}

    async def _matches_field(
        self, locator: "Locator", handle: "ElementHandle", field: CredentialField
    ) -> bool:
        return await locator.and_(self._locator(field.locator)).evaluate_all(
            "(nodes, target) => nodes.includes(target)", handle
        )

    async def _fill(self, args: FillArgs, call: Call) -> dict:
        locator = self._locator(args.locator)
        await self._single(locator, call, wait=True)
        try:
            editable = await locator.is_editable(timeout=call.timeout_ms())
        except PlaywrightTimeout:
            raise
        except PlaywrightError:
            editable = False
        if not editable or not await locator.is_visible():
            raise BrowserFailure("ELEMENT_NOT_INTERACTABLE", retryable=True)
        handle = await locator.element_handle(timeout=call.timeout_ms())
        try:
            value = args.value
            if args.secret_ref is not None:
                field = self._fields.get(args.secret_ref)
                if field is None or not await self._matches_field(
                    locator, handle, field
                ):
                    raise BrowserFailure("SECRET_NOT_AVAILABLE")
                value = field.value
            else:
                if (
                    self.sanitize(value) != value
                    or (await handle.get_attribute("type") or "").lower() == "password"
                ):
                    raise BrowserFailure("SECRET_NOT_AVAILABLE")
                for field in self._protected_fields:
                    if await self._matches_field(locator, handle, field):
                        raise BrowserFailure("SECRET_NOT_AVAILABLE")
            self._current_url()
            await handle.fill(value, timeout=self._reserve_action(call))
        finally:
            await handle.dispose()
        return {"action": "fill", "url": self._public_url()}

    async def _select(self, args: SelectOptionArgs, call: Call) -> dict:
        locator = self._locator(args.locator)
        await self._single(locator, call, wait=True)
        state = await locator.evaluate(
            """(element, value) => ({
                select: element instanceof HTMLSelectElement && !element.multiple,
                option: element instanceof HTMLSelectElement && Array.from(element.options)
                    .some(option => option.value === value && !option.matches(':disabled'))
            })""",
            args.value,
            timeout=call.timeout_ms(),
        )
        if (
            not state["select"]
            or not await locator.is_visible()
            or not await locator.is_enabled()
        ):
            raise BrowserFailure("ELEMENT_NOT_INTERACTABLE", retryable=True)
        if not state["option"]:
            raise BrowserFailure("OPTION_NOT_FOUND", retryable=True)
        self._current_url()
        await locator.select_option(
            value=args.value, timeout=self._reserve_action(call)
        )
        return {"action": "select_option", "url": self._public_url()}

    async def _save(
        self, kind: str, content: bytes, captured_at: datetime, call: Call
    ) -> str:
        if len(content) > self._limits.max_artifact_bytes:
            raise BrowserFailure("ARTIFACT_WRITE_FAILED")
        context = call.context
        try:
            reference = await self._store.save(
                ArtifactInput(
                    run_id=context.run_id,
                    case_id=context.case_id,
                    step_id=context.step_id,
                    tool_call_id=context.tool_call_id,
                    kind=kind,
                    mime_type="image/png"
                    if kind == "screenshot"
                    else "application/json",
                    captured_at=captured_at,
                    content=content,
                )
            )
            return reference.artifact_id
        except Exception:
            raise BrowserFailure("ARTIFACT_WRITE_FAILED") from None

    @staticmethod
    def _json(data: dict) -> bytes:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()

    async def _capture_screenshot(self, args: ScreenshotArgs, call: Call) -> bytes:
        if not self._screenshot_allowed:
            raise BrowserFailure("ACTION_NOT_ALLOWED")
        body = await self._page.locator("body").inner_text(timeout=call.timeout_ms())
        if self.sanitize(body) != body:
            raise BrowserFailure("ACTION_NOT_ALLOWED")
        masks = [
            self._page.locator("input, textarea, select, [contenteditable]"),
            *(self._page.locator(selector) for selector in self._masks),
        ]
        if args.locator is not None:
            locator = self._locator(args.locator)
            await self._single(locator, call)
            box = await locator.bounding_box(timeout=call.timeout_ms())
            if box is None:
                raise BrowserFailure("ELEMENT_NOT_INTERACTABLE", retryable=True)
            pixels = box["width"] * box["height"]
        elif args.full_page:
            pixels = await self._page.evaluate(
                """() => Math.max(document.documentElement.scrollWidth, innerWidth) *
                     Math.max(document.documentElement.scrollHeight, innerHeight)"""
            )
        else:
            viewport = self._page.viewport_size
            pixels = viewport["width"] * viewport["height"]
        if pixels > self._limits.max_screenshot_pixels:
            raise BrowserFailure("ACTION_NOT_ALLOWED")

        options = {"mask": masks, "scale": "css", "timeout": call.timeout_ms()}
        if args.locator is None:
            content = await self._page.screenshot(full_page=args.full_page, **options)
        else:
            content = await locator.screenshot(**options)
        if len(content) < 24 or content[0:8] != b"\x89PNG\r\n\x1a\n":
            raise BrowserFailure("ARTIFACT_WRITE_FAILED")
        width, height = struct.unpack(">II", content[16:24])
        if width * height > self._limits.max_screenshot_pixels:
            raise BrowserFailure("ARTIFACT_WRITE_FAILED")
        return content

    async def _screenshot(self, args: ScreenshotArgs, call: Call) -> dict:
        starting = (self.revision, self._current_url())
        content = await self._capture_screenshot(args, call)
        if starting != (self.revision, self._current_url()):
            raise BrowserFailure("OBSERVATION_UNSTABLE", retryable=True)
        captured_at = datetime.now(UTC)
        public_url = self._public_url()
        evidence_id = await self._save("screenshot", content, captured_at, call)
        return {
            "artifact_id": evidence_id,
            "kind": "screenshot",
            "page_url": public_url,
            "captured_at": captured_at.isoformat(),
        }

    async def _collect_observation(self, call: Call) -> tuple[dict, bool]:
        raw = await self._page.locator("body").aria_snapshot(timeout=call.timeout_ms())
        aria = self.sanitize(omit_form_values(raw))
        title = self.sanitize(await self._page.title())
        max_chars = self._limits.max_observation_chars
        controls = await self._page.evaluate(
            COLLECT_CONTROLS,
            {
                "limit": self._limits.max_elements,
                "textLimit": 256,
                "approvedSelectors": sorted(self._selectors)[:32],
            },
        )
        elements = []
        for control in controls["elements"]:
            locator = suggested_locator(control)
            if locator is None or any(
                self.sanitize(value) != value for value in locator.values()
            ):
                continue
            elements.append(
                {
                    "locator": locator,
                    "role": self.sanitize(control["role"]) if control["role"] else None,
                    "name": self.sanitize(control["name"]) if control["name"] else None,
                    "text": self.sanitize(control["text"]) if control["text"] else None,
                    "enabled": control["enabled"],
                }
            )
        # Count the control context as well as the two page text fields.
        elements_size = len(self._json({"elements": elements}))
        elements_truncated = False
        while elements and elements_size > max_chars // 2:
            elements.pop()
            elements_truncated = True
            elements_size = len(self._json({"elements": elements}))
        title_limit = min(max_chars // 4, 512)
        aria_limit = max(0, max_chars - min(len(title), title_limit) - elements_size)
        return {
            "title": title[:title_limit],
            "aria": aria[:aria_limit],
            "elements": elements,
        }, (
            controls["truncated"]
            or elements_truncated
            or len(title) > title_limit
            or len(aria) > aria_limit
        )

    async def _observe(self, args: ObserveArgs, call: Call) -> dict:
        for _ in range(2):
            starting = (self.revision, self._current_url())
            try:
                content, truncated = await self._collect_observation(call)
                screenshot = (
                    await self._capture_screenshot(ScreenshotArgs(), call)
                    if args.include_screenshot
                    else None
                )
            except PlaywrightError:
                if starting == (self.revision, self._current_url()):
                    raise
                continue
            if starting == (self.revision, self._current_url()):
                break
        else:
            raise BrowserFailure("OBSERVATION_UNSTABLE", retryable=True)
        captured_at = datetime.now(UTC)
        data = {
            "observation_id": f"obs_{uuid4().hex}",
            "observed_at": captured_at.isoformat(),
            "url": self._public_url(),
            **content,
            "truncated": truncated,
        }
        evidence_ids = []
        if screenshot is not None:
            screenshot_id = await self._save(
                "screenshot", screenshot, captured_at, call
            )
            evidence_ids.append(screenshot_id)
        saved = {**data, "evidence_ids": evidence_ids} if evidence_ids else data
        observation_id = await self._save(
            "observation", self._json(saved), captured_at, call
        )
        result = {**data, "evidence_ids": [observation_id, *evidence_ids]}
        self.latest_observation = result
        self.observation_stale = starting != (self.revision, self._page.url)
        return result

    async def _inspect(self, params: InspectCondition, call: Call) -> dict:
        starting = (self.revision, self._current_url())
        if isinstance(params, UrlEquals | TitleEquals | TextEquals):
            if self.sanitize(params.expected) != params.expected:
                raise BrowserFailure("INVALID_ARGUMENTS")
        if isinstance(params, UrlEquals):
            actual = self._public_url()
            matched = actual == params.expected
        elif isinstance(params, TitleEquals):
            actual = self.sanitize(await self._page.title())
            matched = actual == params.expected
        else:
            locator = self._locator(params.locator)
            if isinstance(params, Exists):
                actual = matched = await locator.count() > 0
            elif isinstance(params, Visible):
                actual = matched = await locator.evaluate_all(
                    """nodes => nodes.some(node => {
                        const rect = node.getBoundingClientRect();
                        return Boolean(rect.width && rect.height) &&
                            getComputedStyle(node).visibility === 'visible';
                    })"""
                )
            elif isinstance(params, Count):
                actual = await locator.count()
                matched = actual == params.expected
            else:
                await self._single(locator, call)
                if not await locator.is_visible():
                    raise BrowserFailure("ELEMENT_NOT_INTERACTABLE", retryable=True)
                actual = self.sanitize(
                    await locator.inner_text(timeout=call.timeout_ms())
                )
                actual = actual.replace("\r\n", "\n").strip()
                matched = actual == params.expected.replace("\r\n", "\n").strip()
        if starting != (self.revision, self._current_url()):
            raise BrowserFailure("OBSERVATION_UNSTABLE", retryable=True)
        captured_at = datetime.now(UTC)
        data = {
            "condition": params.condition,
            "actual": actual,
            "matched": matched,
            "url": self._public_url(),
            "observed_at": captured_at.isoformat(),
        }
        evidence_id = await self._save(
            "observation", self._json(data), captured_at, call
        )
        if starting != (self.revision, self._current_url()):
            raise BrowserFailure("OBSERVATION_UNSTABLE", retryable=True)
        return {**data, "evidence_ids": [evidence_id]}

    async def close(self) -> None:
        self._closed = True
        await self._context.close()
