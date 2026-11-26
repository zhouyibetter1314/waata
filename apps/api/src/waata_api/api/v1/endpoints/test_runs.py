"""C1 test-run and evidence endpoints."""

import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import StreamingResponse
from psycopg import Error as DatabaseError

from waata_api.api.dependencies import Owner, Runtime
from waata_api.api.errors import ApiError, error_responses
from waata_api.infrastructure.config import CredentialNotAllowed, TargetNotAllowed
from waata_api.repositories import RunNotCancellable, RunNotDeletable
from waata_api.schemas.test_runs import (
    CancelRunResponse,
    CreateRunRequest,
    CreateRunResponse,
    RunDetail,
    RunListResponse,
    RunReport,
)
from waata_api.services.run_events import event_cursor, stream_events
from waata_api.services.run_views import (
    TERMINAL_STATUSES,
    require_run,
    run_detail,
    run_report,
    run_summary,
)

router = APIRouter(prefix="/api/v1")
_LOG = logging.getLogger(__name__)


@router.post(
    "/test-runs",
    status_code=202,
    operation_id="createTestRun",
    responses=error_responses(
        "INVALID_REQUEST",
        "TARGET_NOT_ALLOWED",
        "CREDENTIAL_NOT_ALLOWED",
        "VALIDATION_ERROR",
    ),
)
async def create_test_run(
    body: CreateRunRequest, owner: Owner, runtime: Runtime
) -> CreateRunResponse:
    settings = runtime.settings
    options = settings.engine_config
    steps = body.options.max_steps_per_case or options.max_steps_per_case
    if steps > options.max_steps_per_case_limit:
        raise ApiError("VALIDATION_ERROR")
    try:
        settings.policy.authorize(owner, body.target_url, body.credential_ref)
    except TargetNotAllowed:
        raise ApiError("TARGET_NOT_ALLOWED") from None
    except CredentialNotAllowed:
        raise ApiError("CREDENTIAL_NOT_ALLOWED") from None
    fields = (body.target_url, body.goal, body.expected_behavior)
    if any(settings.policy.sanitize(field) != field for field in fields):
        raise ApiError("VALIDATION_ERROR")
    record = body.model_dump(mode="json", exclude={"credential_ref"})
    record["options"]["max_steps_per_case"] = steps
    run_id = f"run_{uuid4().hex}"
    run = await runtime.repository.create_run(
        run_id=run_id,
        owner_id=owner,
        request=record,
        credential_ref=body.credential_ref,
    )
    return CreateRunResponse(
        run_id=run_id, status="queued", created_at=run["created_at"].astimezone(UTC)
    )


@router.get(
    "/test-runs",
    operation_id="listTestRuns",
    responses=error_responses("VALIDATION_ERROR"),
)
async def list_test_runs(
    owner: Owner,
    runtime: Runtime,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RunListResponse:
    runs, total = await runtime.repository.list_runs(
        owner, page=page, page_size=page_size
    )
    return RunListResponse(
        items=[run_summary(runtime, row) for row in runs],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/test-runs/{run_id}",
    operation_id="getTestRun",
    responses=error_responses("RUN_NOT_FOUND", "VALIDATION_ERROR"),
)
async def get_test_run(run_id: str, owner: Owner, runtime: Runtime) -> RunDetail:
    return run_detail(runtime, await require_run(runtime, run_id, owner))


@router.get(
    "/test-runs/{run_id}/events",
    operation_id="getTestRunEvents",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "C4 event replay and live stream",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        204: {"description": "Cursor has already reached the terminal event"},
        **error_responses("INVALID_EVENT_CURSOR", "RUN_NOT_FOUND", "VALIDATION_ERROR"),
    },
)
async def get_test_run_events(
    request: Request,
    run_id: str,
    owner: Owner,
    runtime: Runtime,
    after: Annotated[str | None, Query()] = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> Response:
    run = await require_run(runtime, run_id, owner)
    head = run["last_event_sequence"]
    cursor = event_cursor(last_event_id, after, head=head)
    if run["status"] in TERMINAL_STATUSES and cursor == head:
        return Response(status_code=204)
    return StreamingResponse(
        stream_events(
            runtime, run_id, cursor, owner_id=owner, request_id=request.state.request_id
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/test-runs/{run_id}/report",
    operation_id="getTestRunReport",
    responses=error_responses(
        "RUN_NOT_FOUND", "REPORT_NOT_READY", "REPORT_UNAVAILABLE", "VALIDATION_ERROR"
    ),
)
async def get_test_run_report(run_id: str, owner: Owner, runtime: Runtime) -> RunReport:
    return await run_report(runtime, await require_run(runtime, run_id, owner))


@router.post(
    "/test-runs/{run_id}/cancel",
    status_code=202,
    operation_id="cancelTestRun",
    responses={
        200: {"model": CancelRunResponse, "description": "Queued run cancelled"},
        **error_responses(
            "INVALID_REQUEST",
            "RUN_NOT_FOUND",
            "RUN_NOT_CANCELLABLE",
            "VALIDATION_ERROR",
        ),
    },
)
async def cancel_test_run(
    run_id: str, owner: Owner, runtime: Runtime, response: Response
) -> CancelRunResponse:
    try:
        run = await runtime.repository.cancel_run(run_id, owner)
    except RunNotCancellable:
        raise ApiError("RUN_NOT_CANCELLABLE") from None
    if run is None:
        raise ApiError("RUN_NOT_FOUND")
    if run["status"] == "cancelled":
        response.status_code = 200
    return CancelRunResponse(
        run_id=run_id,
        status=run["status"],
        cancellation_requested=run["cancellation_requested"],
    )


@router.delete(
    "/test-runs/{run_id}",
    status_code=204,
    operation_id="deleteTestRun",
    response_class=Response,
    responses=error_responses("INVALID_REQUEST", "RUN_NOT_FOUND", "RUN_NOT_DELETABLE"),
)
async def delete_test_run(run_id: str, owner: Owner, runtime: Runtime) -> Response:
    try:
        deleted = await runtime.repository.delete_run(run_id, owner)
    except RunNotDeletable:
        raise ApiError("RUN_NOT_DELETABLE") from None
    if not deleted:
        raise ApiError("RUN_NOT_FOUND")
    try:
        await runtime.artifact_store.purge_deleted(run_id=run_id)
    except DatabaseError:
        _LOG.warning("Deferred evidence deletion for a completed run")
    return Response(status_code=204)


_ATTACHMENTS = {"playwright_trace": "trace.zip", "test_report": "report.json"}


@router.get(
    "/artifacts/{artifact_id}",
    operation_id="getTestRunArtifact",
    response_class=Response,
    responses={
        200: {
            "description": "C5 evidence content",
            "content": {
                "application/json": {},
                "image/png": {"schema": {"type": "string", "format": "binary"}},
                "application/zip": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        **error_responses(
            "ARTIFACT_NOT_FOUND",
            "ARTIFACT_EXPIRED",
            "ARTIFACT_UNAVAILABLE",
            "VALIDATION_ERROR",
        ),
    },
)
async def get_test_run_artifact(
    artifact_id: str, owner: Owner, runtime: Runtime
) -> Response:
    artifact = await runtime.repository.get_artifact(artifact_id, owner)
    if artifact is None:
        raise ApiError("ARTIFACT_NOT_FOUND")
    expires = artifact["expires_at"]
    if expires is not None and expires <= datetime.now(UTC):
        raise ApiError("ARTIFACT_EXPIRED")
    storage_key = artifact["storage_key"]
    if storage_key is None:
        raise ApiError("ARTIFACT_UNAVAILABLE")
    try:
        content = await runtime.artifact_store.read(storage_key)
    except (OSError, ValueError):
        if expires is not None and expires <= datetime.now(UTC):
            raise ApiError("ARTIFACT_EXPIRED") from None
        raise ApiError("ARTIFACT_UNAVAILABLE") from None
    if len(content) != artifact["size_bytes"]:
        raise ApiError("ARTIFACT_UNAVAILABLE")
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if filename := _ATTACHMENTS.get(artifact["kind"]):
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return Response(content, media_type=artifact["mime_type"], headers=headers)
