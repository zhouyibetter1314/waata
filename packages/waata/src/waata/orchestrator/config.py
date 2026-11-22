"""Trusted W01 configuration; numerical defaults are provisional (Q-005)."""

from typing import Self

from pydantic import model_validator

from waata.core.models import ContractModel, PositiveFloat, PositiveInt


class EngineConfig(ContractModel):
    max_steps_per_case: PositiveInt = 12
    max_steps_per_case_limit: PositiveInt = 100
    max_browser_actions_per_run: PositiveInt = 20
    max_test_cases: PositiveInt = 2
    timeout_seconds: PositiveFloat = 120.0
    cleanup_timeout_seconds: PositiveFloat = 5.0

    @model_validator(mode="after")
    def check_steps(self) -> Self:
        if self.max_steps_per_case > self.max_steps_per_case_limit:
            raise ValueError("default steps exceed the trusted step limit")
        return self
