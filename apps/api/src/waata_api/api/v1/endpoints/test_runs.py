from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from waata_api.api.errors import error_responses
from waata_api.infrastructure.authorization import COOKIE_NAME, Principal
from waata_api.schemas.test_runs import (
    CreateRunRequest,
    RunAccepted,
    RunDetail,
    RunPage,
)
from waata_api.services.test_runs import RunService

router = APIRouter(prefix="/test-runs", tags=["test-runs"])
bearer_scheme = HTTPBearer(auto_error=False)
session_scheme = APIKeyCookie(name=COOKIE_NAME, auto_error=False)
Bearer = Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)]


def current_principal(
    request: Request,
    bearer: Bearer,
    session: Annotated[str | None, Security(session_scheme)],
) -> Principal:
    from_header = request.headers.get("Authorization") is not None
    token = bearer.credentials if bearer else None
    if not from_header and request.app.state.dev_session:
        token = session
    return request.app.state.access.authenticate(token)


def run_service(request: Request) -> RunService:
    return request.app.state.runs


Actor = Annotated[Principal, Depends(current_principal)]
Runs = Annotated[RunService, Depends(run_service)]


@router.post(
    "",
    status_code=202,
    operation_id="create_test_run",
    responses=error_responses(400, 401, 403, 422, 500, 503),
)
def create_run(data: CreateRunRequest, principal: Actor, runs: Runs) -> RunAccepted:
    return runs.create(principal, data)


@router.get(
    "",
    operation_id="list_test_runs",
    responses=error_responses(401, 422, 500),
)
def list_runs(
    principal: Actor,
    runs: Runs,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RunPage:
    return runs.list(principal, page, page_size)


@router.get(
    "/{run_id}",
    operation_id="get_test_run",
    responses=error_responses(401, 404, 500),
)
def get_run(run_id: str, principal: Actor, runs: Runs) -> RunDetail:
    return runs.detail(principal, run_id)
