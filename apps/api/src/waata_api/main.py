import os
from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI, Request, Response

from waata_api.api.errors import install_error_handlers
from waata_api.api.v1.endpoints.test_runs import Bearer, router
from waata_api.infrastructure.authorization import (
    COOKIE_NAME,
    AccessPolicy,
    Principal,
    origin_of,
)
from waata_api.infrastructure.run_queue import MemoryRunQueue, RunQueue
from waata_api.repositories.test_runs import MemoryRunRepository, RunRepository
from waata_api.services.test_runs import RunService


def create_app(
    *,
    access: AccessPolicy | None = None,
    repository: RunRepository | None = None,
    queue: RunQueue | None = None,
    clock: Callable[[], datetime] | None = None,
    new_run_id: Callable[[], str] | None = None,
    dev_session: bool = False,
) -> FastAPI:
    app = FastAPI(title="WAATA Test Runs API", version="0.1.0")
    app.state.access = access if access is not None else AccessPolicy()
    app.state.dev_session = dev_session
    service_options = {}
    if clock is not None:
        service_options["clock"] = clock
    if new_run_id is not None:
        service_options["new_run_id"] = new_run_id
    app.state.runs = RunService(
        repository if repository is not None else MemoryRunRepository(),
        queue if queue is not None else MemoryRunQueue(),
        app.state.access,
        **service_options,
    )
    install_error_handlers(app)
    app.include_router(router, prefix="/api/v1")

    if dev_session:

        @app.post("/api/dev/session", include_in_schema=False, status_code=204)
        def open_dev_session(request: Request, bearer: Bearer) -> Response:
            token = bearer.credentials if bearer else None
            request.app.state.access.authenticate(token)
            response = Response(status_code=204)
            response.set_cookie(
                COOKIE_NAME,
                token,
                httponly=True,
                samesite="strict",
                path="/api",
                max_age=3600,
            )
            return response

    return app


def create_local_app() -> FastAPI:
    """Opt-in local integration identity for Swagger and the same-origin Vue proxy."""
    token = os.environ.get("WAATA_DEV_TOKEN")
    if not token:
        return create_app()
    principal = Principal(
        subject="local-developer",
        origins=frozenset(
            origin_of(url)
            for url in (
                "https://demo-app.test",
                "http://127.0.0.1:3000",
                "http://localhost:3000",
            )
        ),
        credential_refs=frozenset({"demo_login_fixture", "boards_local_fixture"}),
    )
    return create_app(access=AccessPolicy({token: principal}), dev_session=True)


app = create_local_app()
