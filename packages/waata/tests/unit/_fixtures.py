"""Reuse canonical examples; never modify the shared fixture files."""

import json
from pathlib import Path

from waata.orchestrator import TestRequest, TestResult

ROOT = Path(__file__).resolve().parents[4]
CONTRACTS = ROOT / "contracts"


def request() -> TestRequest:
    return TestRequest.model_validate_json(
        (CONTRACTS / "waata/examples/4gaboards-test-request.json").read_text(
            encoding="utf-8"
        )
    )


def result_data() -> dict:
    return json.loads(
        (CONTRACTS / "waata/examples/4gaboards-test-result.json").read_text(
            encoding="utf-8"
        )
    )


def result() -> TestResult:
    return TestResult.model_validate(result_data())


def progress_data() -> list[dict]:
    stream = (CONTRACTS / "events/examples/4gaboards-events.sse").read_text(
        encoding="utf-8"
    )
    return [
        json.loads(line.removeprefix("data: "))
        for line in stream.splitlines()
        if line.startswith("data: ")
    ]


class UntouchedDependency:
    def __getattr__(self, name):
        raise AssertionError(f"W01 must not invoke caller-owned resources: {name}")


def dependencies() -> dict:
    return {
        "llm": UntouchedDependency(),
        "browser": UntouchedDependency(),
        "artifact_store": UntouchedDependency(),
        "observability": UntouchedDependency(),
    }
