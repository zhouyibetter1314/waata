"""Compose the deployed worker with the public WAATA interfaces."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from langfuse import Langfuse
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Playwright, async_playwright
from waata.browser import PlaywrightAdapter
from waata.llm import LLMProvider, OpenAILike
from waata.observability import LangfuseObserver, Observer
from waata.orchestrator import TestEngine, WAATAError
from waata.orchestrator.models import RunError

from waata_api.infrastructure.artifacts import FileArtifactStore
from waata_api.infrastructure.config import (
    CredentialNotAllowed,
    CredentialUnavailable,
    Settings,
    TargetNotAllowed,
)
from waata_api.infrastructure.database import open_repository

from .runner import ClaimedRun, EngineFactory, Worker

_LOG = logging.getLogger(__name__)


def _failure(code: str, message: str) -> WAATAError:
    return WAATAError(RunError(code=code, message=message))


def make_engine_factory(
    settings: Settings,
    artifacts: FileArtifactStore,
    playwright: Playwright,
    llm: LLMProvider,
    observer: Observer | None,
) -> EngineFactory:
    @asynccontextmanager
    async def engine(claim: ClaimedRun) -> AsyncIterator[TestEngine]:
        request = claim.request
        try:
            target = settings.policy.authorize(
                claim.owner_id, request.target_url, request.credential_ref
            )
            credentials = settings.policy.credential_sets(
                target, request.credential_ref
            )
        except (TargetNotAllowed, CredentialNotAllowed, CredentialUnavailable):
            raise _failure(
                "CONFIGURATION_ERROR",
                "The run no longer has a usable target and credential policy",
            ) from None
        if not claim.headless and not settings.allow_headful:
            raise _failure("CONFIGURATION_ERROR", "Headed Chromium is disabled")

        # The launch command can complete after its caller is cancelled. Keep
        # the launch task until its own bounded startup deadline so a late
        # Browser is still closed by this run.
        startup_timeout = min(5, settings.engine_config.timeout_seconds)
        launch = asyncio.create_task(
            playwright.chromium.launch(
                headless=claim.headless, timeout=startup_timeout * 1_000
            )
        )
        browser = None
        try:
            try:
                browser = await asyncio.shield(launch)
            except asyncio.CancelledError:
                try:
                    browser = await launch
                except PlaywrightError:
                    pass
                raise
            except PlaywrightError:
                raise _failure(
                    "BROWSER_ERROR", "Chromium could not be started"
                ) from None
            try:
                adapter = PlaywrightAdapter(
                    browser=browser,
                    allowed_origins=[target.origin],
                    allowed_actions=target.actions,
                    allowed_css_selectors=target.css_selectors,
                    allowed_websocket_paths=target.websocket_paths,
                    credential_sets=credentials,
                    screenshot_mask_selectors=target.screenshot_mask_selectors,
                    allow_screenshots=target.allow_screenshots,
                )
            except ValueError:
                raise _failure(
                    "CONFIGURATION_ERROR", "The browser target policy is invalid"
                ) from None
            yield TestEngine(
                llm=llm,
                browser=adapter,
                artifact_store=artifacts.for_run(claim.run_id, claim.execution_token),
                observability=observer,
                config=settings.engine_config,
            )
        finally:
            if browser is not None:
                try:
                    async with asyncio.timeout(
                        settings.engine_config.cleanup_timeout_seconds
                    ):
                        await browser.close()
                except (TimeoutError, PlaywrightError):
                    raise _failure(
                        "CLEANUP_FAILED", "Chromium did not close after the run"
                    ) from None

    return engine


async def run_worker(
    settings: Settings,
    stop: asyncio.Event,
    *,
    llm: LLMProvider | None = None,
) -> None:
    async with AsyncExitStack() as resources:
        if llm is None:
            if not settings.model_base_url or not settings.model_name:
                raise ValueError("Configure the WAATA model endpoint and model name")
            llm = await resources.enter_async_context(
                OpenAILike(
                    base_url=settings.model_base_url,
                    model=settings.model_name,
                    api_key=settings.model_api_key,
                )
            )
        observer = None
        if settings.langfuse_public_key or settings.langfuse_secret_key:
            if not settings.langfuse_public_key or not settings.langfuse_secret_key:
                raise ValueError("Configure both Langfuse keys to enable run tracing")
            langfuse = Langfuse(
                base_url=settings.langfuse_base_url,
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                timeout=5,
            )
            resources.push_async_callback(asyncio.to_thread, langfuse.shutdown)
            observer = LangfuseObserver(client=langfuse, model_name=settings.model_name)
        repository = await resources.enter_async_context(open_repository(settings))
        playwright = await resources.enter_async_context(async_playwright())
        artifacts = FileArtifactStore.from_settings(settings, repository)
        worker = Worker(
            repository,
            make_engine_factory(settings, artifacts, playwright, llm, observer),
            public_text=settings.policy.sanitize,
            concurrency=settings.worker_concurrency,
            lease_seconds=settings.worker_lease_seconds,
            heartbeat_seconds=settings.worker_heartbeat_seconds,
            poll_seconds=settings.worker_poll_seconds,
            shutdown_seconds=settings.worker_shutdown_seconds,
            purge_expired=artifacts.purge_expired,
        )
        try:
            await worker.run(stop)
        finally:
            try:
                async with asyncio.timeout(settings.worker_shutdown_seconds):
                    await artifacts.drain()
            except TimeoutError:
                _LOG.warning("Evidence writes will be reconciled after worker shutdown")
