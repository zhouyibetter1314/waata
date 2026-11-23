"""FastAPI application factory and process lifecycle."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from psycopg import InterfaceError, OperationalError
from starlette.exceptions import HTTPException

from waata_api.api.dependencies import ApiRuntime
from waata_api.api.errors import ApiError, error_response
from waata_api.api.v1.endpoints.test_runs import router
from waata_api.infrastructure.artifacts import FileArtifactStore
from waata_api.infrastructure.config import Settings
from waata_api.infrastructure.database import open_repository
from waata_api.repositories import PostgresRepository

_LOG = logging.getLogger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    repository: PostgresRepository | None = None,
    artifact_store: FileArtifactStore | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        config = settings if settings is not None else Settings.from_env()
        if repository is not None:
            store = artifact_store or FileArtifactStore.from_settings(
                config, repository
            )
            app.state.runtime = ApiRuntime(config, repository, store)
            yield
            return
        async with open_repository(config) as repo:
            store = artifact_store or FileArtifactStore.from_settings(config, repo)
            app.state.runtime = ApiRuntime(config, repo, store)
            yield

    app = FastAPI(title="WAATA", version="0.1.0", lifespan=lifespan)
    app.include_router(router)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = f"req_{uuid4().hex}"
        try:
            response = await call_next(request)
        except (InterfaceError, OperationalError):
            _LOG.warning("Database unavailable request_id=%s", request.state.request_id)
            response = error_response(request, "SERVICE_UNAVAILABLE")
        except Exception as error:
            _LOG.error(
                "HTTP handler failed request_id=%s type=%s",
                request.state.request_id,
                type(error).__name__,
            )
            response = error_response(request, "INTERNAL_ERROR")
        response.headers.setdefault("Cache-Control", "private, no-store")
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, error: ApiError):
        return error_response(request, error.code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, error: RequestValidationError):
        code = "VALIDATION_ERROR"
        if isinstance(error.body, bytes) or any(
            item["type"] == "json_invalid" for item in error.errors()
        ):
            code = "INVALID_REQUEST"
        return error_response(request, code)

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, error: HTTPException):
        response = error_response(
            request, "INVALID_REQUEST", status_code=error.status_code
        )
        if error.headers and (allow := error.headers.get("Allow")):
            response.headers["Allow"] = allow
        return response

    return app


app = create_app()
