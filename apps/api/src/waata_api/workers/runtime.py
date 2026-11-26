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
    # 返回的 engine 由 Runner 在执行单个 Run 时通过 async with 调用。
    @asynccontextmanager
    async def engine(claim: ClaimedRun) -> AsyncIterator[TestEngine]:
        request = claim.request
        # 入队后仍要用 Worker 启动时加载的策略，重新核对调用者、目标和凭据引用。
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
        # headless 是任务自己的选项，能否显示浏览器窗口由 Worker 的配置决定。
        if not claim.headless and not settings.allow_headful:
            raise _failure("CONFIGURATION_ERROR", "Headed Chromium is disabled")

        # asyncio.shield 保留正在启动的任务。即使外层被取消，也能等到浏览器句柄
        # 或启动超时，再由 finally 关闭实际启动的浏览器。
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
            # 同一个 Run 共用一个 Chromium 实例。适配器会为每个用例新建 BrowserContext，
            # 让不同用例的 Cookie 和登录状态彼此隔离。
            try:
                adapter = PlaywrightAdapter(
                    browser=browser,
                    allowed_origins=[target.origin],
                    allowed_actions=target.actions,
                    allowed_websocket_paths=target.websocket_paths,
                    credential_sets=credentials,
                    screenshot_mask_selectors=target.screenshot_mask_selectors,
                    allow_screenshots=target.allow_screenshots,
                )
            except ValueError:
                raise _failure(
                    "CONFIGURATION_ERROR", "The browser target policy is invalid"
                ) from None
            # yield 将引擎交给 Runner。Runner 的 async with 退出时会进入下面的 finally。
            config = settings.engine_config
            if config.capture_final_screenshot and not target.allow_screenshots:
                config = config.model_copy(update={"capture_final_screenshot": False})
            yield TestEngine(
                llm=llm,
                browser=adapter,
                # 按 Run ID 和执行令牌绑定证据存储，以便登记时检查证据归属与执行权。
                artifact_store=artifacts.for_run(claim.run_id, claim.execution_token),
                observability=observer,
                config=config,
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
    # AsyncExitStack 管理资源清理。启动中途失败或 Worker 停止时，按注册的相反顺序清理。
    async with AsyncExitStack() as resources:
        # 调用方可以注入模型。这里仅创建并清理 Worker 自己持有的模型客户端。
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
        # Langfuse 接收规划、工具执行和判定等观测信息。启用时需要同时提供两把密钥。
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
            # SDK 的 shutdown 是同步函数，退出时在线程里调用它。
            resources.push_async_callback(asyncio.to_thread, langfuse.shutdown)
            observer = LangfuseObserver(client=langfuse, model_name=settings.model_name)
        # repository 封装 PostgreSQL 的操作，例如领任务、登记证据和提交报告。
        repository = await resources.enter_async_context(open_repository(settings))
        # 这里只启动 Playwright 驱动，实际的 Chromium 在单个 Run 开始时才启动。
        playwright = await resources.enter_async_context(async_playwright())
        # FileArtifactStore 将证据字节写入磁盘，通过 repository 在 PostgreSQL 登记存储键、
        # 所属 Run 和有效期。API 端按登记信息读取同一证据目录中的文件。
        artifacts = FileArtifactStore.from_settings(settings, repository)

        async def purge_artifacts() -> None:
            await artifacts.purge_deleted()
            await artifacts.purge_expired()

        worker = Worker(
            repository,
            make_engine_factory(settings, artifacts, playwright, llm, observer),
            public_text=settings.policy.sanitize,
            concurrency=settings.worker_concurrency,
            lease_seconds=settings.worker_lease_seconds,
            heartbeat_seconds=settings.worker_heartbeat_seconds,
            poll_seconds=settings.worker_poll_seconds,
            shutdown_seconds=settings.worker_shutdown_seconds,
            purge_expired=purge_artifacts,
        )
        try:
            await worker.run(stop)
        finally:
            # 先等正在写入的证据收尾，再由 resources 关闭数据库连接池等资源。
            try:
                async with asyncio.timeout(settings.worker_shutdown_seconds):
                    await artifacts.drain()
            except TimeoutError:
                _LOG.warning("Evidence writes will be reconciled after worker shutdown")
