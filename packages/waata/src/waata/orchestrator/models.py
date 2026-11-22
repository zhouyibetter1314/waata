"""C2 request, result and error types."""

from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from waata.artifacts import ArtifactRef

Verdict = Literal["passed", "failed", "blocked", "inconclusive"]
RunStatus = Literal["queued", "running", "succeeded", "errored", "cancelled"]
Scalar = str | int | float | bool | None
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def display_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class TestOptions(_ContractModel):
    max_steps_per_case: int | None = Field(default=None, gt=0)


class TestRequest(_ContractModel):
    target_url: NonEmpty
    goal: NonEmpty
    expected_behavior: NonEmpty
    credential_ref: NonEmpty | None = Field(default=None, repr=False)
    options: TestOptions = Field(default_factory=TestOptions)

    @field_validator("target_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parts = urlsplit(value)
        _ = parts.port
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or "\\" in value
            or any(char.isspace() or ord(char) < 32 for char in value)
        ):
            raise ValueError("The target must be an absolute HTTP(S) URL")
        return value


class RunError(_ContractModel):
    code: str
    message: str


class ExecutionContext(_ContractModel):
    target_url: str
    max_steps_per_case: int = Field(gt=0)
    max_browser_actions_per_run: int = Field(gt=0)
    max_test_cases: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)


class ToolCallSummary(_ContractModel):
    tool_call_id: str
    tool: str
    success: bool | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class StepResult(_ContractModel):
    step_id: str
    summary: str | None = None
    tool_calls: list[ToolCallSummary] = Field(default_factory=list)


class AssertionResult(_ContractModel):
    assertion_id: str
    expected: Scalar
    actual: Scalar = None
    passed: bool | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class TestCaseResult(_ContractModel):
    case_id: str
    name: str
    preconditions: list[str]
    expected_behavior: str
    verdict: Verdict | None = None
    reason: str | None = None
    steps: list[StepResult] = Field(default_factory=list)
    assertions: list[AssertionResult] = Field(default_factory=list)


class TestResult(_ContractModel):
    run_id: str
    status: RunStatus
    verdict: Verdict | None
    error: RunError | None = None
    execution: ExecutionContext
    cases: list[TestCaseResult] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    langfuse_trace_id: str | None = None


class WAATAError(Exception):
    def __init__(
        self, error: RunError, partial_result: TestResult | None = None
    ) -> None:
        super().__init__(error.message)
        self.error = error
        self.partial_result = partial_result
