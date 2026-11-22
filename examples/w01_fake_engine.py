"""Run W01 Worker integration scenarios without a server, browser, or model."""

import asyncio
import json
from pathlib import Path

from waata.artifacts import ArtifactInput, ArtifactRef
from waata.core.events import TestEvent
from waata.orchestrator import (
    FakeTestEngine,
    RunError,
    TestRequest,
    TestResult,
    WAATAError,
)

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


class UnusedStore:
    async def save(self, artifact: ArtifactInput) -> ArtifactRef:
        raise AssertionError("The W01 fake does not save evidence")


def make_engine(**scenario) -> FakeTestEngine:
    return FakeTestEngine(
        llm=object(), browser=object(), artifact_store=UnusedStore(), **scenario
    )


def load_result() -> dict:
    return json.loads(
        (CONTRACTS / "waata/examples/4gaboards-test-result.json").read_text(
            encoding="utf-8"
        )
    )


async def main() -> None:
    request = TestRequest.model_validate_json(
        (CONTRACTS / "waata/examples/4gaboards-test-request.json").read_text(
            encoding="utf-8"
        )
    )
    event = TestEvent(
        event_id="evt_fake_plan",
        run_id="template-run",
        type="plan.created",
        timestamp="2026-11-21T02:00:00Z",
        case_id=None,
        step_id=None,
        payload={"total_cases": 1},
    )
    persisted = []

    async def store_progress(event: TestEvent) -> None:
        # A real Worker adds sequence and durably commits before returning.
        persisted.append(event.model_dump(mode="json"))

    engine = make_engine(
        result=TestResult.model_validate(load_result()), events=[event]
    )
    passed = await engine.run(request, run_id="worker_passed", on_event=store_progress)
    assert passed.run_id == persisted[0]["run_id"] == "worker_passed"
    assert passed.status == "succeeded" and passed.verdict == "passed"
    print("passed:", passed.status, passed.verdict)

    data = load_result()
    data["verdict"] = data["cases"][0]["verdict"] = "failed"
    data["cases"][0]["assertions"][0].update(actual=False, passed=False)
    failed = await make_engine(result=TestResult.model_validate(data)).run(
        request, run_id="worker_failed"
    )
    assert failed.status == "succeeded" and failed.verdict == "failed"
    print("failed:", failed.status, failed.verdict)

    error = RunError(code="MODEL_UNAVAILABLE", message="Scripted model outage")
    try:
        await make_engine(error=WAATAError(error)).run(request, run_id="worker_error")
    except WAATAError as exc:
        assert exc.partial_result is None
        print("error:", exc.error.code)
    else:
        raise AssertionError("Expected a technical error")

    data = load_result()
    data.update(status="errored", verdict=None, error=error.model_dump())
    data["cases"][0]["verdict"] = None
    partial = TestResult.model_validate(data)
    try:
        await make_engine(error=WAATAError(error, partial_result=partial)).run(
            request, run_id="worker_partial"
        )
    except WAATAError as exc:
        report = exc.partial_result
        assert report is not None and report.run_id == "worker_partial"
        assert report.verdict is None and report.artifacts
        print("partial:", report.status, report.verdict)
    else:
        raise AssertionError("Expected a technical error with a partial report")

    started, release = asyncio.Event(), asyncio.Event()
    engine = make_engine(started=started, wait_for=release)
    task = asyncio.create_task(engine.run(request, run_id="worker_cancelled"))
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        print("cancelled: CancelledError propagated; no report")
    else:
        raise AssertionError("Expected cancellation")


if __name__ == "__main__":
    asyncio.run(main())
