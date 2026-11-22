from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message


def install_error_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = f"req_{uuid4().hex}"
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def render(request: Request, error: ApiError, headers=None) -> JSONResponse:
        identifier = request.state.request_id
        safe_headers = {"X-Request-ID": identifier}
        if headers is not None and "Allow" in headers:
            safe_headers["Allow"] = headers["Allow"]
        if error.status == 401:
            safe_headers["WWW-Authenticate"] = "Bearer"
        content = ErrorEnvelope(
            error=ErrorBody(
                code=error.code, message=error.message, request_id=identifier
            )
        )
        return JSONResponse(content.model_dump(), error.status, headers=safe_headers)

    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError) -> JSONResponse:
        return render(request, error)

    @app.exception_handler(RequestValidationError)
    async def validation(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        if any(item["type"] == "json_invalid" for item in error.errors()):
            return render(
                request, ApiError(400, "INVALID_REQUEST", "无法解析请求 JSON")
            )
        return render(request, ApiError(422, "VALIDATION_ERROR", "请求字段无效"))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(
        request: Request, error: StarletteHTTPException
    ) -> JSONResponse:
        code, message = {
            400: ("INVALID_REQUEST", "无法解析请求"),
            404: ("NOT_FOUND", "资源不存在"),
            405: ("METHOD_NOT_ALLOWED", "请求方法不受支持"),
        }.get(error.status_code, ("INTERNAL_ERROR", "请求处理失败"))
        return render(
            request, ApiError(error.status_code, code, message), error.headers
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, _error: Exception) -> JSONResponse:
        return render(request, ApiError(500, "INTERNAL_ERROR", "请求处理失败"))


def error_responses(*statuses: int) -> dict[int, dict]:
    descriptions = {
        400: "请求格式无法解析",
        401: "未认证",
        403: "测试目标或凭据引用未获授权",
        404: "任务不存在或对调用方不可见",
        422: "请求字段无效",
        500: "请求处理失败",
        503: "队列暂不可用",
    }
    return {
        status: {"model": ErrorEnvelope, "description": descriptions[status]}
        for status in statuses
    }
