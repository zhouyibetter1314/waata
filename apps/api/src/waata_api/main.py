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
    # lifespan 管理整个 API 进程的资源。FastAPI 在接收请求之前运行到 yield，
    # 服务期间把上下文保持打开，关停时从 yield 继续并退出上下文。
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        config = settings if settings is not None else Settings.from_env()
        if repository is not None:
            # 测试等调用方可以传入已准备好的仓库，由调用方管理它的生命周期。
            store = artifact_store or FileArtifactStore.from_settings(
                config, repository
            )
            app.state.runtime = ApiRuntime(config, repository, store)
            yield
            return
        # 正常启动时，这个上下文打开数据库连接池并检查迁移，退出时关闭连接池。
        async with open_repository(config) as repo:
            store = artifact_store or FileArtifactStore.from_settings(config, repo)
            # 路由通过 get_runtime() 取得这里保存的配置、数据库仓库和证据存储。
            app.state.runtime = ApiRuntime(config, repo, store)
            yield

    app = FastAPI(title="WAATA", version="0.1.0", lifespan=lifespan)
    app.include_router(router)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        # 每个 HTTP 请求分配自己的 req_ ID，响应带上同一个 ID，便于关联日志。
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


# Uvicorn 导入这个 app 时完成路由注册，启动服务时才进入上面的 lifespan。
app = create_app()
