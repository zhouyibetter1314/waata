"""Stable C2 boundary. Real planning/execution is deliberately outside W01."""

from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from pydantic import ValidationError

from waata.artifacts import ArtifactStore
from waata.browser import BrowserAdapter
from waata.core.events import EventCallback
from waata.llm import LLMProvider
from waata.observability import Observer
from waata.orchestrator.config import EngineConfig
from waata.orchestrator.errors import WAATAError
from waata.orchestrator.models import (
    ExecutionContext,
    RunError,
    TestRequest,
    TestResult,
)


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
        self.llm = llm
        self.browser = browser
        self.artifact_store = artifact_store
        self.observability = observability
        self.config = config if config is not None else EngineConfig()

    def _prepare(
        self, request: TestRequest, run_id: str | None
    ) -> tuple[str, TestRequest, ExecutionContext]:
        try:
            # Revalidate copies as Pydantic model_copy and mutable lists can bypass
            # construction-time validation. No caller-owned object is modified.
            request = TestRequest.model_validate(request.model_dump(warnings=False))
            config = EngineConfig.model_validate(self.config.model_dump(warnings=False))
            steps = request.options.max_steps_per_case
            steps = config.max_steps_per_case if steps is None else steps
            if steps > config.max_steps_per_case_limit:
                raise ValueError("requested steps exceed trusted limit")
            effective_id = f"run_{uuid4().hex}" if run_id is None else run_id
            # Query values and fragments have no role in a public execution summary.
            url = urlsplit(request.target_url)
            execution = ExecutionContext(
                target_url=urlunsplit((url.scheme, url.netloc, url.path, "", "")),
                max_steps_per_case=steps,
                max_browser_actions_per_run=config.max_browser_actions_per_run,
                max_test_cases=config.max_test_cases,
                timeout_seconds=config.timeout_seconds,
            )
            if not isinstance(effective_id, str) or not effective_id.strip():
                raise ValueError("run_id must be a non-blank string")
        except (ValidationError, ValueError, AttributeError):
            raise WAATAError(
                RunError(
                    code="CONFIGURATION_ERROR", message="Invalid run configuration"
                )
            ) from None
        return effective_id, request, execution

    async def run(
        self,
        request: TestRequest,
        *,
        run_id: str | None = None,
        on_event: EventCallback | None = None,
    ) -> TestResult:
        self._prepare(request, run_id)
        raise WAATAError(
            RunError(
                code="CONFIGURATION_ERROR",
                message="Real execution is not implemented in W01; use FakeTestEngine",
            )
        )
