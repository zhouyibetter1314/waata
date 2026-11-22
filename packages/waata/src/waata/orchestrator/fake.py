"""Programmable C2 substitute for Worker tests; never touches injected resources."""

import asyncio
from collections.abc import Sequence

from waata.artifacts import ArtifactStore
from waata.browser import BrowserAdapter
from waata.core.events import WORKER_EVENT_TYPES, EventCallback, TestEvent
from waata.llm import LLMProvider
from waata.observability import Observer
from waata.orchestrator.config import EngineConfig
from waata.orchestrator.engine import TestEngine
from waata.orchestrator.errors import WAATAError
from waata.orchestrator.models import (
    ExecutionContext,
    RunError,
    TestRequest,
    TestResult,
)


class FakeTestEngine(TestEngine):
    def __init__(
        self,
        *,
        llm: LLMProvider,
        browser: BrowserAdapter,
        artifact_store: ArtifactStore,
        observability: Observer | None = None,
        config: EngineConfig | None = None,
        result: TestResult | None = None,
        error: WAATAError | None = None,
        events: Sequence[TestEvent] = (),
        started: asyncio.Event | None = None,
        wait_for: asyncio.Event | None = None,
    ) -> None:
        super().__init__(
            llm=llm,
            browser=browser,
            artifact_store=artifact_store,
            observability=observability,
            config=config,
        )
        if result is not None and error is not None:
            raise ValueError("configure either result or error, not both")
        if result is not None and result.status != "succeeded":
            raise ValueError("technical results must be supplied through WAATAError")
        self._result = (
            TestResult.model_validate(result.model_dump())
            if result is not None
            else None
        )
        self._error = (
            WAATAError(
                RunError.model_validate(error.error.model_dump()),
                partial_result=(
                    TestResult.model_validate(error.partial_result.model_dump())
                    if error.partial_result is not None
                    else None
                ),
            )
            if error is not None
            else None
        )
        self._events = tuple(TestEvent.model_validate(e.model_dump()) for e in events)
        if any(event.type in WORKER_EVENT_TYPES for event in self._events):
            raise ValueError("FakeTestEngine only emits WAATA-owned progress events")
        ids = [event.event_id for event in self._events]
        if len(ids) != len(set(ids)):
            raise ValueError("scripted event IDs must be unique")
        self._started = started
        self._wait_for = wait_for

    @staticmethod
    def _bind_result(
        template: TestResult, run_id: str, execution: ExecutionContext
    ) -> TestResult:
        data = template.model_dump()
        data["run_id"] = run_id
        data["execution"] = execution.model_dump()
        for artifact in data["artifacts"]:
            artifact["run_id"] = run_id
        return TestResult.model_validate(data)

    async def run(
        self,
        request: TestRequest,
        *,
        run_id: str | None = None,
        on_event: EventCallback | None = None,
    ) -> TestResult:
        effective_id, _, execution = self._prepare(request, run_id)
        if self._started is not None:
            self._started.set()
        if on_event is not None:
            for template in self._events:
                event = TestEvent.model_validate(
                    {**template.model_dump(), "run_id": effective_id}
                )
                try:
                    await on_event(event)
                except Exception:
                    # Cancellation is a BaseException and propagates unchanged.
                    # Do not expose a persistence exception's paths or secrets.
                    raise WAATAError(
                        RunError(
                            code="EVENT_DELIVERY_FAILED",
                            message="Progress callback failed",
                        )
                    ) from None
        if self._wait_for is not None:
            await self._wait_for.wait()
        if self._error is not None:
            partial = self._error.partial_result
            raise WAATAError(
                self._error.error.model_copy(deep=True),
                partial_result=(
                    self._bind_result(partial, effective_id, execution)
                    if partial is not None
                    else None
                ),
            )
        if self._result is not None:
            return self._bind_result(self._result, effective_id, execution)
        # Explicit fake default: an empty plan is inconclusive, never a made-up pass.
        return TestResult(
            run_id=effective_id,
            status="succeeded",
            verdict="inconclusive",
            error=None,
            execution=execution,
            cases=[],
            artifacts=[],
            langfuse_trace_id=None,
        )
