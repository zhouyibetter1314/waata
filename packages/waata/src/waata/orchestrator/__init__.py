"""Web test planning, execution, verification, and reporting."""

from waata.artifacts import ArtifactInput, ArtifactRef, ArtifactStore
from waata.core.events import EventCallback, TestEvent
from waata.orchestrator.config import EngineConfig
from waata.orchestrator.engine import TestEngine
from waata.orchestrator.errors import WAATAError
from waata.orchestrator.fake import FakeTestEngine
from waata.orchestrator.models import (
    AssertionResult,
    ExecutionContext,
    RunError,
    RunStatus,
    StepResult,
    TestCaseResult,
    TestOptions,
    TestRequest,
    TestResult,
    TestVerdict,
    ToolCallSummary,
)

__all__ = [
    "ArtifactInput",
    "ArtifactRef",
    "ArtifactStore",
    "AssertionResult",
    "EngineConfig",
    "EventCallback",
    "ExecutionContext",
    "FakeTestEngine",
    "RunError",
    "RunStatus",
    "StepResult",
    "TestCaseResult",
    "TestEngine",
    "TestEvent",
    "TestOptions",
    "TestRequest",
    "TestResult",
    "TestVerdict",
    "ToolCallSummary",
    "WAATAError",
]
