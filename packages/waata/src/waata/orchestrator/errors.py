"""C2 technical failures, distinct from test verdicts and task cancellation."""

from waata.orchestrator.models import RunError, TestResult


class WAATAError(Exception):
    def __init__(
        self, error: RunError, *, partial_result: TestResult | None = None
    ) -> None:
        if partial_result is not None and (
            partial_result.status != "errored" or partial_result.error != error
        ):
            raise ValueError("partial_result must be errored and carry the same error")
        self.error = error
        self.partial_result = partial_result
        super().__init__(f"{error.code}: {error.message}")
