"""C2 public request/report models (FR-001, FR-004, FR-005, NFR-005)."""

from typing import Literal, Self

from pydantic import Field, model_validator

from waata.artifacts import ArtifactRef
from waata.core.models import (
    ContractModel,
    HttpURL,
    NonBlank,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
)

RunStatus = Literal["queued", "running", "succeeded", "errored", "cancelled"]
TestVerdict = Literal["passed", "failed", "blocked", "inconclusive"]
JSONScalar = str | bool | int | float | None


class TestOptions(ContractModel):
    max_steps_per_case: PositiveInt | None = None


class TestRequest(ContractModel):
    target_url: HttpURL
    goal: NonBlank
    expected_behavior: NonBlank
    credential_ref: NonBlank | None = Field(default=None, repr=False)
    options: TestOptions = Field(default_factory=TestOptions)


class RunError(ContractModel):
    code: NonBlank
    message: NonBlank


class ExecutionContext(ContractModel):
    target_url: HttpURL
    max_steps_per_case: PositiveInt
    max_browser_actions_per_run: PositiveInt
    max_test_cases: PositiveInt
    timeout_seconds: PositiveFloat


class ToolCallSummary(ContractModel):
    tool_call_id: NonBlank
    tool: NonBlank
    success: bool | None
    duration_ms: NonNegativeInt | None
    error_code: NonBlank | None
    evidence_ids: list[NonBlank]

    @model_validator(mode="after")
    def check_completion(self) -> Self:
        if self.success is None:
            if self.duration_ms is not None or self.error_code is not None:
                raise ValueError("unfinished calls must retain null completion fields")
        elif self.duration_ms is None or (self.error_code is not None) == self.success:
            raise ValueError(
                "completed calls require duration and consistent error_code"
            )
        return self


class StepResult(ContractModel):
    step_id: NonBlank
    summary: str | None
    tool_calls: list[ToolCallSummary]


class AssertionResult(ContractModel):
    assertion_id: NonBlank
    expected: JSONScalar
    actual: JSONScalar
    passed: bool | None
    evidence_ids: list[NonBlank]

    @model_validator(mode="after")
    def check_evidence(self) -> Self:
        if self.passed is not None and not self.evidence_ids:
            raise ValueError("decided assertions require registered evidence")
        return self


class TestCaseResult(ContractModel):
    case_id: NonBlank
    name: NonBlank
    preconditions: list[str]
    expected_behavior: NonBlank
    verdict: TestVerdict | None
    reason: str | None
    steps: list[StepResult]
    assertions: list[AssertionResult]

    @model_validator(mode="after")
    def check_verdict(self) -> Self:
        # C2 has no optional-assertion flag. Check recorded outcomes, without
        # recomputing their matching semantics from expected and actual values.
        if self.verdict == "passed" and any(
            assertion.passed is not True for assertion in self.assertions
        ):
            raise ValueError("passed cases require all assertions to have passed")
        # An interrupted partial report may not yet have a case verdict.
        if self.verdict not in (None, "failed") and any(
            assertion.passed is False for assertion in self.assertions
        ):
            raise ValueError("decided cases with failed assertions must be failed")
        return self


def aggregate_verdict(cases: list[TestCaseResult]) -> TestVerdict:
    verdicts = {case.verdict for case in cases}
    return next(
        (v for v in ("failed", "blocked", "inconclusive", "passed") if v in verdicts),
        "inconclusive",
    )


class TestResult(ContractModel):
    run_id: NonBlank
    status: RunStatus
    verdict: TestVerdict | None
    error: RunError | None
    execution: ExecutionContext
    cases: list[TestCaseResult]
    artifacts: list[ArtifactRef]
    langfuse_trace_id: NonBlank | None

    @model_validator(mode="after")
    def check_report(self) -> Self:
        if self.status == "succeeded":
            if self.error is not None or any(c.verdict is None for c in self.cases):
                raise ValueError("normal reports require decided cases and error=null")
            if self.verdict != aggregate_verdict(self.cases):
                raise ValueError("overall verdict must follow C2 case precedence")
        elif self.status == "errored":
            if self.verdict is not None or self.error is None:
                raise ValueError("technical reports require verdict=null and an error")
        else:
            raise ValueError(
                "C2 reports are succeeded or errored; cancellation has none"
            )

        def unique(values: list[str]) -> None:
            if len(values) != len(set(values)):
                raise ValueError("identifiers must be unique within a Run and type")

        cases = {case.case_id: case for case in self.cases}
        steps = {
            step.step_id: case.case_id for case in self.cases for step in case.steps
        }
        calls = {
            call.tool_call_id: (case.case_id, step.step_id)
            for case in self.cases
            for step in case.steps
            for call in step.tool_calls
        }
        unique([c.case_id for c in self.cases])
        unique([s.step_id for c in self.cases for s in c.steps])
        unique([a.assertion_id for c in self.cases for a in c.assertions])
        unique(
            [t.tool_call_id for c in self.cases for s in c.steps for t in s.tool_calls]
        )
        unique([a.artifact_id for a in self.artifacts])
        artifacts = {artifact.artifact_id: artifact for artifact in self.artifacts}
        for artifact in self.artifacts:
            if artifact.run_id != self.run_id:
                raise ValueError("artifact must belong to the report Run")
            if artifact.case_id is not None and artifact.case_id not in cases:
                raise ValueError("artifact refers to an unknown case")
            if artifact.step_id is not None and (
                steps.get(artifact.step_id) != artifact.case_id
            ):
                raise ValueError("artifact step does not belong to its case")
            if artifact.tool_call_id is not None and calls.get(
                artifact.tool_call_id
            ) != (artifact.case_id, artifact.step_id):
                raise ValueError("artifact tool call does not match report context")

        def check_refs(ids: list[str], case_id: str) -> None:
            for artifact_id in ids:
                artifact = artifacts.get(artifact_id)
                if artifact is None or artifact.case_id not in (None, case_id):
                    raise ValueError(
                        "evidence must resolve in the same report and case"
                    )

        for case in self.cases:
            for assertion in case.assertions:
                check_refs(assertion.evidence_ids, case.case_id)
            for step in case.steps:
                for call in step.tool_calls:
                    check_refs(call.evidence_ids, case.case_id)
        return self
