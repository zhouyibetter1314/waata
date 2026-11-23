"""Project PostgreSQL records into public HTTP models."""

from datetime import UTC
from urllib.parse import quote

from waata_api.api.dependencies import ApiRuntime
from waata_api.api.errors import ApiError
from waata_api.schemas.test_runs import (
    ArtifactView,
    RunCaseSummary,
    RunDetail,
    RunProgress,
    RunReport,
    RunSummary,
)

TERMINAL_STATUSES = frozenset({"succeeded", "errored", "cancelled"})


async def require_run(runtime: ApiRuntime, run_id: str, owner: str) -> dict:
    run = await runtime.repository.get_run(run_id, owner)
    if run is None:
        raise ApiError("RUN_NOT_FOUND")
    return run


def _utc(value):
    return value.astimezone(UTC) if value is not None else None


def run_summary(runtime: ApiRuntime, run: dict) -> RunSummary:
    policy = runtime.settings.policy
    return RunSummary(
        run_id=run["run_id"],
        target_url=policy.public_url(run["request"]["target_url"]),
        goal=policy.sanitize(run["request"]["goal"]),
        status=run["status"],
        verdict=run["verdict"],
        created_at=_utc(run["created_at"]),
        started_at=_utc(run["started_at"]),
        finished_at=_utc(run["finished_at"]),
    )


def run_detail(runtime: ApiRuntime, run: dict) -> RunDetail:
    summary = None
    if run["report"] is not None:
        counts = dict.fromkeys(("passed", "failed", "blocked", "inconclusive"), 0)
        for case in run["report"]["cases"]:
            if case["verdict"] is not None:
                counts[case["verdict"]] += 1
        summary = RunCaseSummary(**counts)
    return RunDetail(
        **run_summary(runtime, run).model_dump(),
        expected_behavior=runtime.settings.policy.sanitize(
            run["request"]["expected_behavior"]
        ),
        error=run["error"],
        summary=summary,
        progress=RunProgress(
            total_cases=run["total_cases"], completed_cases=run["completed_cases"]
        ),
        cancellation_requested=run["cancellation_requested"],
    )


def artifact_view(record: dict) -> ArtifactView:
    artifact_id = record["artifact_id"]
    return ArtifactView(
        artifact_id=artifact_id,
        run_id=record["run_id"],
        case_id=record["case_id"],
        step_id=record["step_id"],
        tool_call_id=record["tool_call_id"],
        kind=record["kind"],
        mime_type=record["mime_type"],
        captured_at=_utc(record["captured_at"]),
        size_bytes=record["size_bytes"],
        url=f"/api/v1/artifacts/{quote(artifact_id, safe='')}",
        expires_at=_utc(record["expires_at"]),
    )


async def run_report(runtime: ApiRuntime, run: dict) -> RunReport:
    if run["status"] not in TERMINAL_STATUSES:
        raise ApiError("REPORT_NOT_READY")
    result = run["report"]
    if result is None:
        raise ApiError("REPORT_UNAVAILABLE")
    records = await runtime.repository.list_artifacts(run["run_id"])
    records_by_id = {record["artifact_id"]: record for record in records}
    return RunReport.model_validate(
        {
            **result,
            "artifacts": [
                artifact_view(records_by_id[reference["artifact_id"]])
                for reference in result["artifacts"]
            ],
        }
    )
