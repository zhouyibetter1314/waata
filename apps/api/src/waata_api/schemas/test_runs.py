import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
)

STEP_LIMIT = 35
RunStatus = Literal["queued", "running", "succeeded", "errored", "cancelled"]
Verdict = Literal["passed", "failed", "blocked", "inconclusive"]
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
NonNegative = Annotated[int, Field(ge=0)]
_http_url = TypeAdapter(AnyHttpUrl)


def validate_target(value: object) -> str:
    # Reject ambiguous authority syntax before the URL parser normalizes it.
    if not isinstance(value, str) or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        raise ValueError("Expected an absolute HTTP(S) URL")
    authority = re.match(r"(?i)^https?://([^/?#]+)", value)
    if not authority or "@" in authority[1]:
        raise ValueError("Expected an absolute HTTP(S) URL without user information")
    url = _http_url.validate_python(value)
    if url.username is not None or url.password is not None:
        raise ValueError("User information is not allowed")
    return value


TargetURL = Annotated[
    str, BeforeValidator(validate_target), Field(json_schema_extra={"format": "uri"})
]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class RunOptions(InputModel):
    headless: bool = True
    max_steps_per_case: int = Field(default=STEP_LIMIT, ge=1, le=STEP_LIMIT)


class CreateRunRequest(InputModel):
    target_url: TargetURL
    goal: NonBlank
    expected_behavior: NonBlank
    credential_ref: NonBlank | None = None
    options: RunOptions = Field(default_factory=RunOptions)


class RunAccepted(BaseModel):
    run_id: str
    status: Literal["queued"] = "queued"
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
    total_cases: NonNegative | None
    completed_cases: NonNegative


class RunCaseSummary(BaseModel):
    passed: NonNegative
    failed: NonNegative
    blocked: NonNegative
    inconclusive: NonNegative


class RunError(BaseModel):
    code: str
    message: str


class RunDetail(RunSummary):
    expected_behavior: str
    progress: RunProgress
    summary: RunCaseSummary | None
    error: RunError | None
    cancellation_requested: bool


class RunPage(BaseModel):
    items: list[RunSummary]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: NonNegative
