"""Run and finalize C2 work under the C6 execution lease."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager, suppress
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from psycopg import DataError, IntegrityError, InterfaceError, OperationalError
from psycopg_pool import PoolTimeout
from waata.core.events import TestEvent
from waata.orchestrator import (
    EventCallback,
    TestOptions,
    TestRequest,
    TestResult,
    WAATAError,
)
from waata.orchestrator.models import RunError, display_url

from waata_api.repositories import InvalidReport, LeaseLost

from .events import public_event

_LOG = logging.getLogger(__name__)
_TRANSIENT = (OperationalError, InterfaceError, PoolTimeout, TimeoutError)
_WORKER_ERROR = RunError(
    code="WORKER_ERROR", message="The worker could not finish the run"
)
_REPORT_ERROR = RunError(
    code="REPORT_WRITE_FAILED", message="The report could not be saved"
)
_RUN_ERROR_CODES = {
    "CONFIGURATION_ERROR",
    "MODEL_UNAVAILABLE",
    "BROWSER_ERROR",
    "RUN_TIMEOUT",
    "EVENT_DELIVERY_FAILED",
    "CLEANUP_FAILED",
    "INTERNAL_ERROR",
    "WORKER_ERROR",
    "REPORT_WRITE_FAILED",
}


class Engine(Protocol):
    async def run(
        self,
        request: TestRequest,
        *,
        run_id: str | None = None,
        on_event: EventCallback | None = None,
    ) -> TestResult: ...


@dataclass(frozen=True)
class ClaimedRun:
    run_id: str
    owner_id: str
    execution_token: str
    request: TestRequest
    headless: bool


# 工厂按本次 Run 准备引擎。退出 async with 时，它负责清理本次运行占用的资源。
type EngineFactory = Callable[[ClaimedRun], AbstractAsyncContextManager[Engine]]


class WorkerRepository(Protocol):
    async def claim_run(self, *, lease_seconds: float) -> dict | None: ...

    async def heartbeat(
        self, run_id: str, execution_token: str, *, lease_seconds: float
    ) -> dict | None: ...

    async def recover_expired(self, *, limit: int = 100) -> int: ...

    async def append_event(
        self, run_id: str, execution_token: str, event: dict
    ) -> int: ...

    async def finish_run(
        self,
        run_id: str,
        execution_token: str,
        *,
        status: str,
        verdict: str | None = None,
        error: dict | None = None,
        report: dict | None = None,
        terminal_event_id: str | None = None,
        report_event_id: str | None = None,
    ) -> dict: ...


@dataclass
class _Execution:
    run_id: str
    token: str
    deadline: float
    task: asyncio.Task[TestResult] | None = None
    stop_reason: str | None = None
    lost: bool = False

    def stop(self, reason: str) -> None:
        if reason == "lease":
            self.lost = True
        if self.stop_reason is None:
            self.stop_reason = reason
            if self.task is not None and not self.task.done():
                self.task.cancel()


class Worker:
    """An independently runnable queue consumer with isolated execution slots."""

    def __init__(
        self,
        repository: WorkerRepository,
        engine_factory: EngineFactory,
        *,
        public_text: Callable[[str], str] = str,
        concurrency: int = 2,
        lease_seconds: float = 30,
        heartbeat_seconds: float = 1,
        poll_seconds: float = 0.5,
        shutdown_seconds: float = 20,
        purge_expired: Callable[[], Awaitable[object]] | None = None,
    ) -> None:
        if (
            not 0 < heartbeat_seconds < lease_seconds
            or min(concurrency, poll_seconds, shutdown_seconds) <= 0
        ):
            raise ValueError("Worker concurrency and intervals are invalid")
        self.repository = repository
        self.engine_factory = engine_factory
        self.public_text = public_text
        self.concurrency = concurrency
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.poll_seconds = poll_seconds
        self.shutdown_seconds = shutdown_seconds
        self.purge_expired = purge_expired

    async def run(self, stop: asyncio.Event) -> None:
        # active 跟踪外层 _process 任务。领取一条 Run 后，执行和收尾共占用一个并发名额。
        active: dict[asyncio.Task[None], _Execution] = {}
        stopped = asyncio.create_task(stop.wait())
        maintenance = asyncio.create_task(self._maintain())
        try:
            while not stop.is_set():
                for task in list(active):
                    if task.done():
                        task.result()
                        del active[task]
                if maintenance.done():
                    maintenance.result()
                while len(active) < self.concurrency and not stop.is_set():
                    started = asyncio.get_running_loop().time()
                    try:
                        async with asyncio.timeout(self.heartbeat_seconds):
                            # 领取事务把数据库记录改为 running、分配执行令牌，并写入 run.started。
                            row = await self.repository.claim_run(
                                lease_seconds=self.lease_seconds
                            )
                    except _TRANSIENT:
                        _LOG.warning("The worker queue is temporarily unreachable")
                        break
                    if row is None:
                        break
                    execution = _Execution(
                        row["run_id"],
                        row["execution_token"],
                        started + self.lease_seconds,
                    )
                    if stop.is_set():
                        execution.stop("shutdown")
                    task = asyncio.create_task(self._process(row, execution))
                    active[task] = execution
                await asyncio.wait(
                    [*active, stopped],
                    timeout=self.poll_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
        finally:
            await self._drain(active)
            stopped.cancel()
            maintenance.cancel()
            await asyncio.gather(stopped, maintenance, return_exceptions=True)

    async def _maintain(self) -> None:
        next_purge = 0.0
        clock = asyncio.get_running_loop().time
        while True:
            try:
                async with asyncio.timeout(self.heartbeat_seconds):
                    # Worker 未能续租时，数据库把过期的 running 记录收尾为 errored。
                    await self.repository.recover_expired()
            except _TRANSIENT:
                _LOG.warning("The worker could not check expired leases")
            if self.purge_expired is not None and clock() >= next_purge:
                try:
                    async with asyncio.timeout(self.lease_seconds):
                        await self.purge_expired()
                except Exception:
                    _LOG.warning("The worker could not purge expired evidence")
                next_purge = clock() + self.lease_seconds
            await asyncio.sleep(self.heartbeat_seconds)

    async def _drain(self, active: dict[asyncio.Task[None], _Execution]) -> None:
        if not active:
            return
        # 停机时先给已领取的任务时间完成，再通知仍在运行的引擎退出并等待清理。
        grace_period = self.shutdown_seconds / 2
        _, pending = await asyncio.wait(active, timeout=grace_period)
        for task in pending:
            active[task].stop("shutdown")
        if pending:
            _, pending = await asyncio.wait(pending, timeout=grace_period)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def _monitor(self, execution: _Execution, ready: asyncio.Event) -> None:
        clock = asyncio.get_running_loop().time
        while True:
            started = clock()
            if started >= execution.deadline:
                execution.stop("lease")
                return
            try:
                async with asyncio.timeout_at(
                    min(execution.deadline, started + self.heartbeat_seconds)
                ):
                    # 用执行令牌向数据库续租。返回的任务记录也带有用户请求取消的标记。
                    row = await self.repository.heartbeat(
                        execution.run_id,
                        execution.token,
                        lease_seconds=self.lease_seconds,
                    )
            except _TRANSIENT:
                pass
            except Exception:
                _LOG.error(
                    "Could not verify the execution lease for run %s", execution.run_id
                )
                execution.stop("lease")
                return
            else:
                if row is None:
                    execution.stop("lease")
                    return
                execution.deadline = started + self.lease_seconds
                if row["cancellation_requested"]:
                    execution.stop("cancel")
                # 第一次成功续租后发出信号，让等待中的 _run_engine 继续。
                ready.set()
            await asyncio.sleep(
                max(
                    0,
                    min(started + self.heartbeat_seconds, execution.deadline) - clock(),
                )
            )

    # _process 管理一条已领取任务。row 是数据库记录，execution 是本进程的执行状态。
    async def _process(self, row: dict, execution: _Execution) -> None:
        ready = asyncio.Event()
        # 引擎执行测试时，监控协程并行续租并检查是否收到取消请求。
        execution.task = asyncio.create_task(self._run_engine(row, execution, ready))
        monitor = asyncio.create_task(self._monitor(execution, ready))
        try:
            status, error, result = await self._outcome(execution)
            # 写入终态期间保持监控，让收尾操作仍可续租。
            if not execution.lost:
                await self._finish(execution, status, error, result)
        except LeaseLost:
            execution.stop("lease")
        except Exception:
            _LOG.error("Could not finalize run %s", execution.run_id)
        finally:
            monitor.cancel()
            with suppress(asyncio.CancelledError):
                await monitor
            execution.task.add_done_callback(_consume_execution_result)

    async def _run_engine(
        self, row: dict, execution: _Execution, ready: asyncio.Event
    ) -> TestResult:
        await ready.wait()
        # TestRequest 给引擎使用。headless 和执行令牌由平台放在 ClaimedRun 中交给工厂。
        options = row["request"].get("options", {})
        request = TestRequest.model_validate(
            {
                **row["request"],
                "credential_ref": row["credential_ref"],
                "options": TestOptions(
                    max_steps_per_case=options.get("max_steps_per_case")
                ),
            }
        )
        claim = ClaimedRun(
            run_id=execution.run_id,
            owner_id=row["owner_id"],
            execution_token=execution.token,
            request=request,
            headless=options.get("headless", True),
        )

        async def publish(event: TestEvent) -> None:
            # 引擎等待此回调。公开字段通过校验和脱敏后写入数据库，API 再从数据库读取。
            values = public_event(event, execution.run_id, self.public_text)
            for attempt in range(3):
                try:
                    async with self._write_timeout(execution):
                        await self.repository.append_event(
                            execution.run_id, execution.token, values
                        )
                    return
                except _TRANSIENT:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(self.poll_seconds)

        async with self.engine_factory(claim) as engine:
            return await engine.run(request, run_id=execution.run_id, on_event=publish)

    async def _outcome(
        self, execution: _Execution
    ) -> tuple[str, RunError | None, TestResult | None]:
        task = execution.task
        assert task is not None
        if execution.stop_reason == "shutdown":
            task.cancel()
        try:
            # 引擎正常返回时，Run 状态是 succeeded。用例判定另外由 result.verdict 表示。
            return "succeeded", None, await asyncio.shield(task)
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                execution.stop("shutdown")
                raise
            if execution.stop_reason == "cancel":
                return "cancelled", None, None
            return "errored", _WORKER_ERROR, None
        except WAATAError as failure:
            return "errored", failure.error, failure.partial_result
        except Exception:
            _LOG.warning("An execution failed in worker run %s", execution.run_id)
            return "errored", _WORKER_ERROR, None

    async def _finish(
        self,
        execution: _Execution,
        status: str,
        error: RunError | None,
        result: TestResult | None,
    ) -> None:
        report = None
        error = self._public_error(error)
        # 重试沿用同一个终态事件 ID。若上一次已提交，数据库可以识别这是同一次写入。
        terminal_id, report_id = f"evt_{uuid4().hex}", f"evt_{uuid4().hex}"
        clock = asyncio.get_running_loop().time
        retry_until = clock() + self.lease_seconds
        while True:
            try:
                if report is None and result is not None:
                    try:
                        report = self._public_report(result)
                    except ValueError:
                        raise InvalidReport("The report cannot be published") from None
                async with self._write_timeout(execution):
                    # 由数据库仓库在同一个事务内保存报告、终态事件和任务状态。
                    await self.repository.finish_run(
                        execution.run_id,
                        execution.token,
                        status=status,
                        verdict=result.verdict
                        if status == "succeeded" and result
                        else None,
                        error=error,
                        report=report,
                        terminal_event_id=terminal_id,
                        report_event_id=report_id,
                    )
                return
            except (DataError, IntegrityError, InvalidReport):
                if result is None:
                    raise
                _LOG.warning(
                    "Report write failed for run %s after %s",
                    execution.run_id,
                    error["code"] if error else "test completion",
                )
                status, report, result = "errored", None, None
                # A cancellation whose cleanup failed must never become a
                # successful cancellation because its partial report failed.
                if error is None or error["code"] != "CLEANUP_FAILED":
                    error = self._public_error(_REPORT_ERROR)
            except _TRANSIENT:
                if clock() >= retry_until:
                    raise
                await asyncio.sleep(self.poll_seconds)

    def _write_timeout(self, execution: _Execution) -> asyncio.Timeout:
        now = asyncio.get_running_loop().time()
        if execution.lost or now >= execution.deadline:
            raise LeaseLost("Worker execution lease ended")
        return asyncio.timeout_at(min(execution.deadline, now + self.heartbeat_seconds))

    def _public_error(self, error: RunError | None) -> dict | None:
        if error is None:
            return None
        if error.code not in _RUN_ERROR_CODES:
            error = _WORKER_ERROR
        return {
            "code": error.code,
            "message": self.public_text(error.message),
        }

    def _public_report(self, result: TestResult) -> dict:
        # 转成可以写入 PostgreSQL 的 JSON 数据，并对前端可见的内容脱敏。
        report = result.model_dump(mode="json")
        report["error"] = self._public_error(result.error)
        execution = report["execution"]
        execution["target_url"] = self.public_text(display_url(execution["target_url"]))
        trace_id = report["langfuse_trace_id"]
        if trace_id is not None and self.public_text(trace_id) != trace_id:
            report["langfuse_trace_id"] = None
        for case in report["cases"]:
            for key in ("name", "reason", "expected_behavior"):
                if isinstance(case[key], str):
                    case[key] = self.public_text(case[key])
            case["preconditions"] = [
                self.public_text(item) for item in case["preconditions"]
            ]
            for step in case["steps"]:
                if isinstance(step["summary"], str):
                    step["summary"] = self.public_text(step["summary"])
            for assertion in case["assertions"]:
                for key in ("expected", "actual"):
                    if isinstance(assertion[key], str):
                        assertion[key] = self.public_text(assertion[key])
        return report


def _consume_execution_result(task: asyncio.Task[TestResult]) -> None:
    if not task.cancelled():
        task.exception()
