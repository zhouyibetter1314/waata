"""C4 callback envelopes; persistence, sequence and lifecycle events are Worker-owned."""

from collections.abc import Awaitable, Callable
from typing import Literal, Self

from pydantic import JsonValue, field_validator, model_validator

from waata.core.models import ContractModel, NonBlank, NonNegativeInt, UTCTimestamp


class _Empty(ContractModel):
    pass


class _Plan(ContractModel):
    total_cases: NonNegativeInt


class _CaseStarted(ContractModel):
    name: str


class _StepStarted(ContractModel):
    summary: str | None


class _ToolCalled(ContractModel):
    tool_call_id: NonBlank
    tool: NonBlank


class _ToolCompleted(_ToolCalled):
    success: bool
    duration_ms: NonNegativeInt
    error_code: NonBlank | None
    evidence_ids: list[NonBlank]

    @model_validator(mode="after")
    def check_error(self) -> Self:
        if (self.error_code is not None) == self.success:
            raise ValueError("error_code must agree with success")
        return self


Verdict = Literal["passed", "failed", "blocked", "inconclusive"]


class _CaseVerified(ContractModel):
    verdict: Verdict


class _ReportGenerated(ContractModel):
    artifact_id: NonBlank | None


class _RunError(ContractModel):
    code: NonBlank
    message: NonBlank


class _Completed(ContractModel):
    status: Literal["succeeded"]
    verdict: Verdict
    error: None


class _Failed(ContractModel):
    status: Literal["errored"]
    verdict: None
    error: _RunError


class _Cancelled(ContractModel):
    status: Literal["cancelled"]
    verdict: None
    error: None


_PAYLOADS = {
    "run.started": _Empty,
    "plan.created": _Plan,
    "case.started": _CaseStarted,
    "agent.step.started": _StepStarted,
    "tool.called": _ToolCalled,
    "tool.completed": _ToolCompleted,
    "case.verified": _CaseVerified,
    "report.generated": _ReportGenerated,
    "run.completed": _Completed,
    "run.failed": _Failed,
    "run.cancelled": _Cancelled,
}
WORKER_EVENT_TYPES = frozenset(
    {"run.started", "report.generated", "run.completed", "run.failed", "run.cancelled"}
)


class TestEvent(ContractModel):
    schema_version: Literal[1] = 1
    event_id: NonBlank
    run_id: NonBlank
    type: str
    timestamp: UTCTimestamp
    case_id: NonBlank | None
    step_id: NonBlank | None
    payload: dict[str, JsonValue]

    @field_validator("schema_version", mode="before")
    @classmethod
    def check_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be integer 1")
        return value

    @model_validator(mode="after")
    def check_event(self) -> Self:
        payload_model = _PAYLOADS.get(self.type)
        if payload_model is None:
            raise ValueError("unknown C4 event type")
        payload_model.model_validate(self.payload)
        if self.step_id is not None and self.case_id is None:
            raise ValueError("step scope requires case_id")
        if self.type in WORKER_EVENT_TYPES or self.type == "plan.created":
            if self.case_id is not None or self.step_id is not None:
                raise ValueError("Run events cannot have case or step scope")
        elif self.type in {"case.started", "case.verified"}:
            if self.case_id is None or self.step_id is not None:
                raise ValueError("Case events require case_id and step_id=null")
        elif self.type == "agent.step.started":
            if self.case_id is None or self.step_id is None:
                raise ValueError("Step events require case_id and step_id")
        return self


EventCallback = Callable[[TestEvent], Awaitable[None]]
