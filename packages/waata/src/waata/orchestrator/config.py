"""Trusted runtime defaults and resource limits for C2."""

from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

CaseSetup = Callable[[str, str], Awaitable[None]]


class EngineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    max_steps_per_case: int = Field(default=16, gt=0)
    max_steps_per_case_limit: int = Field(default=50, gt=0)
    max_browser_actions_per_run: int = Field(default=35, gt=0)
    max_test_cases: int = Field(default=8, gt=0)
    max_checkpoints_per_case: int = Field(default=8, gt=0)
    timeout_seconds: float = Field(default=120, gt=0)
    cleanup_timeout_seconds: float = Field(default=5, gt=0)
    tool_timeout_seconds: float = Field(default=5, gt=0)
    verification_settle_seconds: float = Field(default=0.25, ge=0)
    capture_final_screenshot: bool = False
    observer_timeout_seconds: float = Field(default=0.25, gt=0)
    max_model_requests_per_run: int = Field(default=48, gt=0)
    max_model_tokens_per_run: int = Field(default=200_000, gt=0)
    max_input_tokens: int | None = Field(default=None, gt=0)
    context_safety_margin: int = Field(default=128, ge=0)
    model_retries: int = Field(default=1, ge=0, le=5)
    max_tool_attempts_per_run: int = Field(default=160, gt=0)
    max_concurrent_runs: int = Field(default=2, gt=0)
    setup_case: CaseSetup | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_step_limit(self):
        if self.max_steps_per_case > self.max_steps_per_case_limit:
            raise ValueError("The default step limit exceeds the trusted maximum")
        return self
