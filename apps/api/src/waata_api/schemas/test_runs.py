"""HTTP request and response models for C1 and C5."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from waata.artifacts import ArtifactRef
from waata.orchestrator import TestOptions, TestRequest, TestResult
from waata.orchestrator.models import (
    AssertionResult,
    RunError,
    RunStatus,
    Scalar,
    StepResult,
    TestCaseResult,
    ToolCallSummary,
    Verdict,
)


class RunOptions(TestOptions):
    headless: bool = True
    max_steps_per_case: Annotated[int, Field(gt=0)] | SkipJsonSchema[None] = Field(
        default_factory=lambda: None
    )

    @field_validator("max_steps_per_case", mode="before")
    @classmethod
    def require_integer_if_present(cls, value: object) -> object:
        if value is None:
            raise ValueError("The maximum step count must be a positive integer")
        return value


class CreateRunRequest(TestRequest):
    options: RunOptions = Field(default_factory=RunOptions)


class CreateRunResponse(BaseModel):
    run_id: str
    status: Literal["queued"]
    created_at: datetime


class RunSummary(BaseModel):
    run_id: str
    target_url: str
    goal: str
    status: RunStatus
    verdict: Verdict | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunProgress(BaseModel):
    total_cases: int | None
    completed_cases: int = Field(ge=0)


class RunCaseSummary(BaseModel):
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    blocked: int = Field(ge=0)
    inconclusive: int = Field(ge=0)


class RunDetail(RunSummary):
    expected_behavior: str
    progress: RunProgress
    summary: RunCaseSummary | None
    error: RunError | None
    cancellation_requested: bool


class RunListResponse(BaseModel):
    items: list[RunSummary]
    page: int
    page_size: int
    total: int = Field(ge=0)


class CancelRunResponse(BaseModel):
    run_id: str
    status: Literal["running", "cancelled"]
    cancellation_requested: Literal[True]


class ArtifactView(ArtifactRef):
    case_id: str | None
    step_id: str | None
    tool_call_id: str | None
    url: str
    expires_at: datetime | None


class ReportToolCall(ToolCallSummary):
    success: bool | None
    duration_ms: int | None = Field(ge=0)
    error_code: str | None
    evidence_ids: list[str]


class ReportStep(StepResult):
    summary: str | None
    tool_calls: list[ReportToolCall]


class ReportAssertion(AssertionResult):
    actual: Scalar
    passed: bool | None
    evidence_ids: list[str]


class ReportCase(TestCaseResult):
    verdict: Verdict | None
    reason: str | None
    steps: list[ReportStep]
    assertions: list[ReportAssertion]


class RunReport(TestResult):
    error: RunError | None
    cases: list[ReportCase]
    artifacts: list[ArtifactView]
    langfuse_trace_id: str | None


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ApiErrorEnvelope(BaseModel):
    error: ApiErrorDetail
