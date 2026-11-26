"""C2 run orchestration for FR-001 through FR-005 and NFR-001 through NFR-006."""

import asyncio
import json
import logging
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from waata.artifacts import ArtifactInput, ArtifactRef, ArtifactStore
from waata.browser import (
    BrowserAdapter,
    BrowserSession,
    BrowserSetupCleanupError,
    InspectArgs,
)
from waata.core.agent import AgentHistory, ContextLimitError, agent_step
from waata.core.events import EventType, TestEvent
from waata.core.model import (
    ChatMessage,
    ChatResponse,
    LLMProvider,
    ModelError,
    ModelResponseError,
    ToolCall,
    estimate_request_input_tokens,
    input_token_limit,
)
from waata.core.tools import ToolContext, ToolRegistry, ToolResult, ToolSpec
from waata.observability import Observation, Observer, RunObserver

from .config import EngineConfig
from .models import (
    AssertionResult,
    ExecutionContext,
    RunError,
    StepResult,
    TestCaseResult,
    TestRequest,
    TestResult,
    ToolCallSummary,
    Verdict,
    WAATAError,
    display_url,
)
from .planner import RUNNER_PROMPT, CasePlan, parse_plan, planning_messages

EventCallback = Callable[[TestEvent], Awaitable[None]]
_LOG = logging.getLogger(__name__)
_ACTIONS = frozenset(
    {"browser.navigate", "browser.click", "browser.fill", "browser.select_option"}
)
_C3_NAMES = _ACTIONS | {"browser.observe", "browser.inspect", "browser.screenshot"}
_STALE_ACTION = ToolResult.failed(
    "ACTION_NOT_ALLOWED",
    "Page changed since the model observed it. Reobserve before acting.",
)
_BLOCKED = frozenset(
    {"TARGET_NOT_ALLOWED", "ACTION_NOT_ALLOWED", "SECRET_NOT_AVAILABLE"}
)
_BROWSER_FAILURES = frozenset({"BROWSER_CLOSED", "SESSION_NOT_READY", "INTERNAL_ERROR"})
_VERDICT_ORDER: tuple[Verdict, ...] = ("failed", "blocked", "inconclusive", "passed")


def _error(code: str, message: str) -> WAATAError:
    return WAATAError(RunError(code=code, message=message))


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class _ModelBudgetExhausted(Exception):
    pass


class _RunArtifacts:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store
        self.refs: dict[str, ArtifactRef] = {}

    async def save(self, artifact: ArtifactInput) -> ArtifactRef:
        ref = await self.store.save(artifact)
        if (
            ref.model_dump(exclude={"artifact_id", "size_bytes"})
            != artifact.model_dump(exclude={"content"})
            or ref.size_bytes != len(artifact.content)
            or ref.artifact_id in self.refs
        ):
            raise ValueError("The artifact store returned inconsistent metadata")
        self.refs[ref.artifact_id] = ref
        return ref


@dataclass(slots=True)
class _CaseExecution:
    result: TestCaseResult
    session: BrowserSession
    tools: ToolRegistry
    history: AgentHistory = field(default_factory=AgentHistory)
    recent_actions: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=6)
    )
    inspections: dict[str, ToolResult] = field(default_factory=dict)
    inspection_revision: int | None = None
    pending_effect: dict[str, Any] | None = None
    blocked: bool = False
    needs_observation: bool = True
    completion_retry_used: bool = False
    completion_feedback: str | None = None


class TestEngine:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        browser: BrowserAdapter,
        artifact_store: ArtifactStore,
        observability: Observer | None = None,
        config: EngineConfig | None = None,
    ) -> None:
        self._llm = llm
        self._browser = browser
        self._artifact_store = artifact_store
        self._observability = observability
        self._config = config if config is not None else EngineConfig()
        self._slots = asyncio.Semaphore(self._config.max_concurrent_runs)

    async def run(
        self,
        request: TestRequest,
        *,
        run_id: str | None = None,
        on_event: EventCallback | None = None,
    ) -> TestResult:
        if not isinstance(request, TestRequest):
            raise _error("CONFIGURATION_ERROR", "The run requires a valid TestRequest")
        if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
            raise _error("CONFIGURATION_ERROR", "The run ID must be a nonempty string")
        run = _Run(
            self, request, run_id if run_id is not None else _id("run"), on_event
        )
        try:
            async with asyncio.timeout_at(run.deadline):
                async with self._slots:
                    await run.execute()
        except TimeoutError as exc:
            error = RunError(
                code="RUN_TIMEOUT", message="The run exceeded its deadline"
            )
            await run.finish_observer("errored", error.code)
            raise WAATAError(error, run.report(error)) from exc
        except WAATAError as exc:
            await run.finish_observer("errored", exc.error.code)
            exc.partial_result = run.report(exc.error)
            raise
        except asyncio.CancelledError:
            await run.finish_observer("cancelled")
            raise
        except Exception:
            error = RunError(
                code="INTERNAL_ERROR", message="An internal run error occurred"
            )
            await run.finish_observer("errored", error.code)
            raise WAATAError(error, run.report(error)) from None
        await run.finish_observer("succeeded")
        return run.report()


class _Run:
    def __init__(
        self,
        engine: TestEngine,
        request: TestRequest,
        run_id: str,
        on_event: EventCallback | None,
    ) -> None:
        self.llm = engine._llm
        self.browser = engine._browser
        self.config = engine._config
        self.artifacts = _RunArtifacts(engine._artifact_store)
        self.observer_factory = engine._observability
        self.observer: RunObserver | None = None
        self.trace_id: str | None = None
        self.on_event = on_event
        self.request = request
        self.run_id = run_id
        self.clock = asyncio.get_running_loop().time
        self.started_at = self.clock()
        self.deadline = self.started_at + self.config.timeout_seconds
        self.max_steps = (
            request.options.max_steps_per_case or self.config.max_steps_per_case
        )
        self.cases: list[TestCaseResult] = []
        self.secret_refs: tuple[str, ...] = ()
        self.model_requests = 0
        self.model_tokens = 0
        self.tool_attempts = 0
        self.actions = 0

    def sanitize(self, value: str) -> str:
        try:
            return self.browser.sanitize(value, self.request.credential_ref)
        except Exception:
            return "[redacted]"

    def verdict(self) -> Verdict:
        for verdict in _VERDICT_ORDER:
            if any(case.verdict == verdict for case in self.cases):
                return verdict
        return "inconclusive"

    def report(self, error: RunError | None = None) -> TestResult:
        return TestResult(
            run_id=self.run_id,
            status="errored" if error else "succeeded",
            verdict=None if error else self.verdict(),
            error=error,
            execution=ExecutionContext(
                target_url=self.sanitize(display_url(self.request.target_url)),
                max_steps_per_case=self.max_steps,
                max_browser_actions_per_run=self.config.max_browser_actions_per_run,
                max_test_cases=self.config.max_test_cases,
                timeout_seconds=self.config.timeout_seconds,
            ),
            cases=self.cases,
            artifacts=list(self.artifacts.refs.values()),
            langfuse_trace_id=self.trace_id,
        )

    async def observe(
        self,
        kind: str,
        case_id: str | None = None,
        step_id: str | None = None,
        **fields: str | int | bool | None,
    ) -> None:
        if self.observer is None:
            return
        try:
            async with asyncio.timeout(self.config.observer_timeout_seconds):
                await self.observer.record(
                    Observation(kind, self.run_id, case_id, step_id, fields)
                )
        except Exception:
            _LOG.debug("WAATA observation delivery failed")

    async def finish_observer(self, status: str, code: str | None = None) -> None:
        if self.observer is None:
            return
        await self.observe(
            "run.finished",
            status=status,
            error_code=code,
            verdict=self.verdict() if status == "succeeded" else None,
            duration_ms=self.elapsed_ms(self.started_at),
        )
        try:
            async with asyncio.timeout(self.config.observer_timeout_seconds):
                trace_id = await self.observer.close()
                self.trace_id = (
                    trace_id
                    if trace_id is None or self.sanitize(trace_id) == trace_id
                    else None
                )
        except Exception:
            _LOG.debug("WAATA observation cleanup failed")

    async def event(
        self,
        kind: EventType,
        payload: dict[str, Any],
        *,
        case_id: str | None = None,
        step_id: str | None = None,
    ) -> None:
        if self.on_event is None:
            return
        event = TestEvent(
            event_id=_id("evt"),
            run_id=self.run_id,
            timestamp=datetime.now(UTC),
            type=kind,
            case_id=case_id,
            step_id=step_id,
            payload=payload,
        )
        try:
            await self.on_event(event)
        except Exception:
            raise _error(
                "EVENT_DELIVERY_FAILED", "The progress callback failed"
            ) from None

    def elapsed_ms(self, since: float) -> int:
        return int((self.clock() - since) * 1000)

    async def execute(self) -> None:
        try:
            self.browser.validate_target(self.request.target_url)
            self.secret_refs = self.browser.secret_refs(self.request.credential_ref)
        except ValueError:
            raise _error(
                "CONFIGURATION_ERROR",
                "The target or test data is outside the fixture policy",
            ) from None
        if self.max_steps > self.config.max_steps_per_case_limit:
            raise _error(
                "CONFIGURATION_ERROR", "The requested step limit exceeds the maximum"
            )
        if not self.llm.metadata.supports_tools:
            raise _error("CONFIGURATION_ERROR", "The model must support tool calling")
        if self.observer_factory is not None:
            try:
                async with asyncio.timeout(self.config.observer_timeout_seconds):
                    self.observer = await self.observer_factory.start_run(self.run_id)
            except Exception:
                _LOG.debug("WAATA observation setup failed")
        await self.observe("run.started")
        cases = await self.plan()
        await self.event("plan.created", {"total_cases": len(cases)})
        await self.observe("plan.created", total_cases=len(cases))
        for plan in cases:
            await self.execute_case(plan)

    async def model_request(
        self,
        messages: Sequence[ChatMessage],
        *,
        phase: str,
        tools: Sequence[ToolSpec] = (),
        json_mode: bool = False,
        case_id: str | None = None,
        step_id: str | None = None,
    ) -> ChatResponse:
        metadata = self.llm.metadata
        estimate = estimate_request_input_tokens(messages, tools)
        if estimate > input_token_limit(
            metadata,
            max_input_tokens=self.config.max_input_tokens,
            safety_margin=self.config.context_safety_margin,
        ):
            raise ContextLimitError(
                "The required model input exceeds the context window"
            )
        reserved = estimate + metadata.max_output_tokens
        for attempt in range(self.config.model_retries + 1):
            if (
                self.model_requests >= self.config.max_model_requests_per_run
                or self.model_tokens + reserved > self.config.max_model_tokens_per_run
            ):
                raise _ModelBudgetExhausted
            self.model_requests += 1
            self.model_tokens += reserved
            start = self.clock()
            try:
                response = await self.llm.chat(
                    messages,
                    tools=tools,
                    json_mode=json_mode,
                    max_output_tokens=metadata.max_output_tokens,
                )
            except ModelResponseError:
                await self.observe(
                    "model.completed",
                    case_id,
                    step_id,
                    phase=phase,
                    duration_ms=self.elapsed_ms(start),
                    error_code="INTERNAL_ERROR",
                )
                raise
            except (ModelError, TimeoutError) as exc:
                await self.observe(
                    "model.completed",
                    case_id,
                    step_id,
                    phase=phase,
                    duration_ms=self.elapsed_ms(start),
                    error_code="MODEL_UNAVAILABLE",
                )
                if (isinstance(exc, ModelError) and not exc.retryable) or (
                    attempt == self.config.model_retries
                ):
                    raise _error(
                        "MODEL_UNAVAILABLE", "The model request failed"
                    ) from None
                await asyncio.sleep(
                    min(0.2 * (2**attempt), max(0, self.deadline - self.clock()))
                )
                continue
            usage = response.usage
            total = None
            if usage is not None:
                total = usage.total_tokens
                if total is None:
                    total = usage.input_tokens + usage.output_tokens
                self.model_tokens += total - reserved
            await self.observe(
                "model.completed",
                case_id,
                step_id,
                phase=phase,
                duration_ms=self.elapsed_ms(start),
                total_tokens=total,
                finish_reason=response.finish_reason
                if response.finish_reason
                in {"stop", "length", "tool_calls", "content_filter"}
                else None,
            )
            return response
        raise AssertionError("The model retry loop must return or raise")

    async def plan(self) -> list[CasePlan]:
        data = {
            "target_url": self.sanitize(display_url(self.request.target_url)),
            "goal": self.sanitize(self.request.goal),
            "expected_behavior": self.sanitize(self.request.expected_behavior),
            "secret_refs": self.secret_refs,
            "max_cases": self.config.max_test_cases,
            "max_checkpoints_per_case": self.config.max_checkpoints_per_case,
        }
        approved = [
            selector
            for selector in getattr(self.browser, "planning_css_selectors", ())
            if self.sanitize(selector) == selector
        ]
        if approved:
            data["approved_css_selectors"] = approved
        failure = "The model did not produce a valid test plan"
        for repair in (False, True):
            try:
                response = await self.model_request(
                    planning_messages(data, repair=repair),
                    phase="planner",
                    json_mode=self.llm.metadata.supports_json,
                )
            except ModelResponseError:
                failure = "The model returned an unreadable response while planning"
                continue
            except (ContextLimitError, _ModelBudgetExhausted):
                raise _error(
                    "CONFIGURATION_ERROR",
                    "The planning request exceeds the model budget",
                ) from None
            if response.finish_reason == "length":
                failure = (
                    "The model hit its output limit before finishing the test plan"
                )
                continue
            failure = "The model did not produce a valid test plan"
            if response.message.tool_calls:
                continue
            # `:=` 先把 parse_plan 的返回值赋给 cases，再判断它是否为 None。
            # 空列表表示计划合法但没有用例，也会从这里返回。
            if (
                cases := parse_plan(
                    response.message.content,
                    max_cases=self.config.max_test_cases,
                    max_checkpoints=self.config.max_checkpoints_per_case,
                )
            ) is not None:
                return cases
        raise _error("INTERNAL_ERROR", failure)

    async def execute_case(self, plan: CasePlan) -> None:
        result = TestCaseResult(
            case_id=_id("case"),
            name=self.sanitize(plan.name),
            preconditions=[self.sanitize(item) for item in plan.preconditions],
            expected_behavior=self.sanitize(plan.expected_behavior),
        )
        self.cases.append(result)
        await self.event("case.started", {"name": result.name}, case_id=result.case_id)
        await self.observe("case.started", result.case_id)
        if self.config.setup_case is not None:
            try:
                await self.config.setup_case(self.run_id, result.case_id)
            except Exception:
                result.verdict = "blocked"
                result.reason = "The test fixture could not be prepared"
                await self.case_verified(result)
                return
        try:
            session = await self.browser.open_case(
                self.request.target_url,
                credential_ref=self.request.credential_ref,
                artifact_store=self.artifacts,
            )
        except BrowserSetupCleanupError as exc:
            cause = exc.__cause__
            if not isinstance(cause, asyncio.CancelledError):
                cause = _error(
                    "BROWSER_ERROR", "The browser session could not be opened"
                )
            raise _error(
                "CLEANUP_FAILED", "The partial browser session could not be closed"
            ) from cause
        except Exception:
            raise _error(
                "BROWSER_ERROR", "The browser session could not be opened"
            ) from None
        primary_error: BaseException | None = None
        try:
            case = _CaseExecution(
                result,
                session,
                ToolRegistry(session.tools),
                history=AgentHistory(
                    summarize=self.tool_history_summary,
                    sanitize_message=self.sanitize_history_message,
                ),
            )
            reached_target = False
            for index in range(self.max_steps):
                step = StepResult(
                    step_id=_id("step"), summary="Observe and exercise the test case"
                )
                result.steps.append(step)
                await self.event(
                    "agent.step.started",
                    {"summary": step.summary},
                    case_id=result.case_id,
                    step_id=step.step_id,
                )
                await self.observe("agent.step.started", result.case_id, step.step_id)
                if index == 0:
                    navigation = await self.run_tool(
                        case,
                        step,
                        "browser.navigate",
                        {
                            "url": self.request.target_url,
                        },
                    )
                    if not navigation.success:
                        code = navigation.error.code if navigation.error else None
                        if code in {"NAVIGATION_FAILED", "TOOL_TIMEOUT"}:
                            raise _error(
                                "BROWSER_ERROR", "The test page could not be opened"
                            )
                        result.reason = "The test page could not be reached within the execution policy"
                        break
                    reached_target = True
                try:
                    reason = await self.run_step(
                        case, step, plan, can_continue=index + 1 < self.max_steps
                    )
                except WAATAError as exc:
                    if exc.error.code == "MODEL_UNAVAILABLE" and self.config.capture_final_screenshot:
                        await self.capture_final_evidence(case, step)
                    raise
                if reason is not None:
                    result.reason = reason
                    break
            if result.reason is None:
                result.reason = "The agent step limit was reached"
            await self.verify_case(
                case, plan, result.steps[-1], reached_target=reached_target
            )
            if self.config.capture_final_screenshot and reached_target:
                # Optional evidence uses normal browser policy and budgets, and
                # never changes the independently calculated business verdict.
                await self.capture_final_evidence(case, result.steps[-1])
            await self.case_verified(result)
        except (WAATAError, asyncio.CancelledError) as exc:
            primary_error = exc
            raise
        except Exception:
            primary_error = _error("INTERNAL_ERROR", "An internal case error occurred")
            raise primary_error from None
        finally:
            try:
                await self.close_session(session)
            except WAATAError as cleanup:
                if primary_error is not None:
                    raise cleanup from primary_error
                raise

    async def capture_final_evidence(self, case: _CaseExecution, step: StepResult) -> None:
        try:
            await self.run_tool(case, step, "browser.screenshot", {})
        except Exception:
            # Avoid replacing the primary verdict/error with an evidence failure.
            _LOG.warning("Automatic final screenshot could not be captured")

    async def close_session(self, session: BrowserSession) -> None:
        async def close() -> None:
            async with asyncio.timeout(self.config.cleanup_timeout_seconds):
                await session.close()

        task = asyncio.create_task(close())
        cancellation = None
        try:
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError as exc:
                    if task.cancelled():
                        break
                    cancellation = exc
            task.result()
        except asyncio.CancelledError:
            raise _error(
                "CLEANUP_FAILED", "Browser session cleanup was interrupted"
            ) from cancellation
        except Exception:
            raise _error(
                "CLEANUP_FAILED", "The browser session could not be closed"
            ) from cancellation
        if cancellation is not None:
            raise cancellation

    async def case_verified(self, result: TestCaseResult) -> None:
        await self.event(
            "case.verified", {"verdict": result.verdict}, case_id=result.case_id
        )
        await self.observe("case.verified", result.case_id, verdict=result.verdict)

    @staticmethod
    def checkpoint_key(arguments: dict[str, Any]) -> str:
        return json.dumps(
            {key: value for key, value in arguments.items() if key != "timeout_ms"},
            sort_keys=True,
            ensure_ascii=False,
        )

    def context_state(self, case: _CaseExecution, plan: CasePlan) -> dict[str, Any]:
        checkpoints = []
        self.refresh_checkpoints(case)
        for item in plan.checkpoints:
            arguments = item.model_dump(mode="json", exclude_none=True)
            prior = case.inspections.get(self.checkpoint_key(arguments))
            checkpoints.append(
                {
                    "condition": self.sanitize_model_data(arguments),
                    "last_observed_match": prior.data.get("matched")
                    if prior and prior.data
                    else None,
                }
            )
        remaining = self.config.max_browser_actions_per_run - self.actions
        return {
            "name": case.result.name,
            "goal": self.sanitize(self.request.goal),
            "target_url": self.sanitize(display_url(self.request.target_url)),
            "preconditions": self.preconditions_for_model(
                plan, case.session.secret_refs
            ),
            "expected_behavior": case.result.expected_behavior,
            "checkpoints": checkpoints,
            "allowed_secret_refs": case.session.secret_refs,
            "page": case.session.latest_observation,
            "page_is_current": not (
                case.needs_observation or case.session.observation_stale
            ),
            "recent_actions": list(case.recent_actions),
            "pending_side_effect": case.pending_effect,
            "remaining_browser_actions": remaining,
            "completion_feedback": case.completion_feedback,
        }

    def preconditions_for_model(
        self, plan: CasePlan, refs: tuple[str, ...]
    ) -> list[dict]:
        return [
            {
                "description": self.sanitize(item),
                "fixture_fields_mentioned": [ref for ref in refs if ref in item],
            }
            for item in plan.preconditions
        ]

    def sanitize_model_data(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.sanitize(value)
        if isinstance(value, list):
            return [self.sanitize_model_data(item) for item in value]
        if isinstance(value, dict):
            return {
                self.sanitize(key): item
                if key == "secret_ref" and item in self.secret_refs
                else self.sanitize_model_data(item)
                for key, item in value.items()
            }
        return value

    def sanitize_history_message(self, message: ChatMessage) -> ChatMessage:
        return replace(
            message,
            content=self.sanitize(message.content)
            if message.content
            else message.content,
            tool_calls=tuple(
                replace(call, arguments=self.sanitize_model_data(call.arguments))
                for call in message.tool_calls
            ),
        )

    @staticmethod
    def refresh_checkpoints(case: _CaseExecution) -> None:
        current_revision = case.session.revision
        if case.inspection_revision != current_revision:
            case.inspections.clear()
            case.inspection_revision = current_revision

    async def run_step(
        self,
        case: _CaseExecution,
        step: StepResult,
        plan: CasePlan,
        *,
        can_continue: bool,
    ) -> str | None:
        if case.needs_observation or case.session.observation_stale:
            # Trusted fixture opt-in: allow async navigation/rendering to settle
            # before asking the model to act on a still-transitional page.
            previous = case.recent_actions[-1] if case.recent_actions else None
            settle = min(self.config.observation_settle_seconds, self.deadline - self.clock())
            if settle > 0 and previous and previous["success"] and previous["tool"] in {
                "browser.click", "browser.navigate"
            }:
                await asyncio.sleep(settle)
            for _ in range(2):
                observation = await self.run_tool(case, step, "browser.observe", {})
                if observation.success and not case.session.observation_stale:
                    break
                if observation.error is not None and not observation.error.retryable:
                    return "The current page could not be observed"
            else:
                return "The current page could not be observed"
        if self.actions >= self.config.max_browser_actions_per_run:
            return "The browser action limit was reached"
        model_revision = case.session.revision
        state = self.context_state(case, plan)
        page = state["page"]
        compact_state = None
        if page:
            compact_state = {
                **state,
                "page": {
                    "url": page.get("url"),
                    "title": page.get("title"),
                    "aria": (page.get("aria") or "")[:3000],
                    "elements": [
                        element
                        for element in page.get("elements", [])
                        if element.get("locator", {}).get("strategy") == "css"
                    ][:6],
                    "truncated": True,
                },
            }
        try:
            messages = case.history.build_messages(
                RUNNER_PROMPT,
                state,
                tools=case.tools.specs,
                metadata=self.llm.metadata,
                max_input_tokens=self.config.max_input_tokens,
                safety_margin=self.config.context_safety_margin,
                compact_state=compact_state,
            )
            response = await self.model_request(
                messages,
                phase="runner",
                tools=case.tools.specs,
                case_id=case.result.case_id,
                step_id=step.step_id,
            )
        except ContextLimitError:
            return "The required operation context exceeded the model input limit"
        except _ModelBudgetExhausted:
            return "The model usage limit was reached"
        except ModelResponseError:
            raise _error(
                "INTERNAL_ERROR", "The model returned invalid tool data"
            ) from None
        if any(
            any(
                self.sanitize(value) != value
                for value in (call.id, call.wire_name or call.name)
            )
            for call in response.message.tool_calls
        ):
            raise _error(
                "INTERNAL_ERROR", "The model returned an unsafe tool identifier"
            )

        paused = False

        async def execute(call: ToolCall) -> ToolResult:
            nonlocal paused
            is_action = call.name in _ACTIONS
            if is_action and (paused or case.session.revision != model_revision):
                case.needs_observation = True
                return _STALE_ACTION
            actions_before = self.actions
            result = await self.run_tool(
                case,
                step,
                call.name,
                call.arguments,
                expected_revision=model_revision if is_action else None,
            )
            if is_action and not result.success:
                # Even an error before dispatch invalidates assumptions behind
                # dependent actions in the rest of this turn.
                case.needs_observation = True
                paused = True
            elif self.actions != actions_before and call.name == "browser.navigate":
                paused = True
            if call.name == "browser.observe" and result.success:
                # Keep the tool response paired with the call, but send the full
                # current observation only through context_state on the next turn.
                observation = result.data or {}
                return replace(
                    result,
                    data={
                        key: observation[key]
                        for key in ("observation_id", "url", "title", "evidence_ids")
                        if key in observation
                    },
                )
            return result

        try:
            acted = await agent_step(response, execute, case.history)
        except ModelResponseError:
            raise _error(
                "INTERNAL_ERROR", "The model returned invalid tool data"
            ) from None
        if not acted:
            stop = "The agent returned no tool calls"
            if (
                can_continue
                and not case.blocked
                and not case.completion_retry_used
                and any(
                    action["tool"] == "browser.click" and action["success"]
                    for action in case.recent_actions
                )
            ):
                for checkpoint in plan.checkpoints:
                    arguments = checkpoint.model_dump(mode="json", exclude_none=True)
                    checked = await self.run_tool(
                        case, step, "browser.inspect", arguments
                    )
                    if checked.success and (checked.data or {}).get("matched") is False:
                        case.completion_retry_used = True
                        case.completion_feedback = (
                            "Your previous response had no tool calls, but a required "
                            "checkpoint is unmet. Use the current observation and goal "
                            "to complete the remaining actions before ending."
                        )
                        return None
            if case.completion_retry_used:
                stop += " after one checkpoint-guided continuation"
            return stop
        return None

    def tool_history_summary(
        self, call: ToolCall, result: ToolResult
    ) -> dict[str, Any]:
        data = result.data or {}
        return {
            "tool": call.name if call.name in _C3_NAMES else "unknown_tool",
            "success": result.success,
            "error_code": result.error.code if result.error else None,
            "error_message": self.sanitize(result.error.message)
            if result.error
            else None,
            **{
                key: data[key]
                for key in ("action", "url", "observed_at", "evidence_ids", "matched")
                if key in data
            },
        }

    async def run_tool(
        self,
        case: _CaseExecution,
        step: StepResult,
        name: str,
        arguments: dict[str, Any] | None,
        *,
        expected_revision: int | None = None,
    ) -> ToolResult:
        if self.tool_attempts >= self.config.max_tool_attempts_per_run:
            return ToolResult.failed(
                "BUDGET_EXCEEDED", "The tool attempt limit was reached"
            )
        self.tool_attempts += 1
        case_id, step_id = case.result.case_id, step.step_id
        tool_id = _id("call")
        safe_name = (
            name
            if any(spec.name == name for spec in case.tools.specs)
            else "unknown_tool"
        )
        summary = ToolCallSummary(tool_call_id=tool_id, tool=safe_name)
        step.tool_calls.append(summary)
        await self.event(
            "tool.called",
            {"tool_call_id": tool_id, "tool": safe_name},
            case_id=case_id,
            step_id=step_id,
        )
        stale_page = (
            expected_revision is not None and case.session.revision != expected_revision
        )
        dispatched = False

        def reserve_action() -> bool:
            nonlocal dispatched, stale_page
            if (
                expected_revision is not None
                and case.session.revision != expected_revision
            ):
                stale_page = True
                return False
            if self.actions >= self.config.max_browser_actions_per_run:
                return False
            self.actions += 1
            dispatched = True
            return True

        start = self.clock()
        deadline = min(self.deadline, start + self.config.tool_timeout_seconds)
        context = ToolContext(
            self.run_id, case_id, step_id, tool_id, deadline, reserve_action
        )
        output = (
            _STALE_ACTION
            if stale_page
            else await case.tools.execute(name, arguments, context)
        )
        if stale_page:
            case.needs_observation = True
            output = _STALE_ACTION
        summary.success = output.success
        summary.duration_ms = self.elapsed_ms(start)
        summary.error_code = output.error.code if output.error is not None else None
        data = output.data or {}
        ids = data.get("evidence_ids", [])
        if (artifact_id := data.get("artifact_id")) is not None:
            ids = [*ids, artifact_id]
        summary.evidence_ids = [
            value
            for value in dict.fromkeys(ids)
            if (ref := self.artifacts.refs.get(value)) is not None
            and ref.tool_call_id == tool_id
        ]
        if dispatched:
            case.needs_observation = True
            case.inspections.clear()
            action = {
                "tool": safe_name,
                "success": output.success,
                "error_code": summary.error_code,
            }
            case.recent_actions.append(action)
            if not output.success:
                case.pending_effect = {
                    **action,
                    "outcome": "action dispatched, effect unverified",
                }
        if name == "browser.observe" and output.success:
            case.needs_observation = False
        if name == "browser.inspect" and arguments is not None and output.success:
            self.refresh_checkpoints(case)
            validated = InspectArgs.model_validate(arguments).model_dump(
                mode="json", exclude_none=True
            )
            case.inspections[self.checkpoint_key(validated)] = output
        requested_screenshot = name == "browser.screenshot" or (
            name == "browser.observe"
            and (arguments or {}).get("include_screenshot") is True
        )
        optional_evidence_denied = (
            requested_screenshot and summary.error_code == "ACTION_NOT_ALLOWED"
        )
        if summary.error_code in _BLOCKED and not (
            stale_page or optional_evidence_denied
        ):
            case.blocked = True
        await self.event(
            "tool.completed",
            summary.model_dump(),
            case_id=case_id,
            step_id=step_id,
        )
        await self.observe(
            "tool.completed",
            case_id,
            step_id,
            tool=safe_name,
            tool_call_id=tool_id,
            success=output.success,
            error_code=summary.error_code,
            duration_ms=summary.duration_ms,
            evidence_count=len(summary.evidence_ids),
        )
        if summary.error_code in _BROWSER_FAILURES:
            raise _error("BROWSER_ERROR", "The browser session failed")
        return output

    async def verify_case(
        self,
        case: _CaseExecution,
        plan: CasePlan,
        step: StepResult,
        *,
        reached_target: bool,
    ) -> None:
        for checkpoint in plan.checkpoints:
            arguments = checkpoint.model_dump(mode="json", exclude_none=True)
            expected = arguments.get("expected", True)
            assertion = AssertionResult(
                assertion_id=_id("assert"),
                expected=self.sanitize(expected)
                if isinstance(expected, str)
                else expected,
            )
            case.result.assertions.append(assertion)
            if not reached_target:
                continue
            self.refresh_checkpoints(case)
            prior = case.inspections.get(self.checkpoint_key(arguments))
            latest = await self.run_tool(case, step, "browser.inspect", arguments)
            if (
                latest.error is not None
                and latest.error.code == "BUDGET_EXCEEDED"
                and prior is not None
            ):
                latest = prior
            data = latest.data or {}
            stable_mismatch = False
            if (latest.success and data.get("matched") is False) or (
                latest.error is not None and latest.error.retryable
            ):
                settle = self.config.verification_settle_seconds
                revision = case.session.revision
                if self.clock() + settle < self.deadline:
                    await asyncio.sleep(settle)
                    retry = await self.run_tool(
                        case, step, "browser.inspect", arguments
                    )
                    refreshed = retry.data or {}
                    stable_mismatch = (
                        retry.success
                        and refreshed.get("matched") is False
                        and data.get("matched") is False
                        and refreshed.get("actual") == data.get("actual")
                        and refreshed.get("url") == data.get("url")
                        and revision == case.session.revision
                    )
                    if retry.success:
                        data = refreshed
            evidence_ids = [
                value
                for value in data.get("evidence_ids", [])
                if (ref := self.artifacts.refs.get(value)) is not None
                and ref.case_id == case.result.case_id
                and ref.kind == "observation"
            ]
            if evidence_ids:
                actual = data.get("actual")
                assertion.actual = (
                    self.sanitize(actual) if isinstance(actual, str) else actual
                )
                assertion.evidence_ids = evidence_ids
                if data.get("matched") is True or stable_mismatch:
                    assertion.passed = data["matched"]

        values = [assertion.passed for assertion in case.result.assertions]
        if all(value is True for value in values):
            case.result.verdict = "passed"
            case.result.reason = None
        elif case.blocked:
            case.result.verdict = "blocked"
            case.result.reason = "The test was blocked by the fixture or action policy"
        elif False in values:
            case.result.verdict = "failed"
            failure = "A required checkpoint did not match the expected behavior"
            case.result.reason = f"{failure}. {case.result.reason or ''}".strip()
        else:
            case.result.verdict = "inconclusive"
            case.result.reason = (
                f"Insufficient checkpoint evidence. {case.result.reason or ''}".strip()
            )
