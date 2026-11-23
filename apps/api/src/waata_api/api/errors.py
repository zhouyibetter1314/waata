"""Sanitized C1 errors shared by the HTTP routes and middleware."""

from fastapi import Request
from fastapi.responses import JSONResponse

from waata_api.schemas.test_runs import ApiErrorDetail, ApiErrorEnvelope

ERRORS = {
    "INVALID_REQUEST": (400, "请求格式无效"),
    "INVALID_EVENT_CURSOR": (400, "事件游标无效"),
    "UNAUTHENTICATED": (401, "需要有效的平台身份认证"),
    "TARGET_NOT_ALLOWED": (403, "测试目标未获授权"),
    "CREDENTIAL_NOT_ALLOWED": (403, "测试凭据未获授权"),
    "RUN_NOT_FOUND": (404, "测试任务不存在"),
    "ARTIFACT_NOT_FOUND": (404, "测试证据不存在"),
    "REPORT_NOT_READY": (409, "测试报告尚未生成"),
    "REPORT_UNAVAILABLE": (409, "此任务没有可查询的报告"),
    "RUN_NOT_CANCELLABLE": (409, "此任务已结束，无法取消"),
    "ARTIFACT_EXPIRED": (410, "测试证据已过期"),
    "VALIDATION_ERROR": (422, "请求字段无效或超出允许范围"),
    "TOO_MANY_REQUESTS": (429, "请求超出当前配额"),
    "INTERNAL_ERROR": (500, "服务处理请求时发生错误"),
    "SERVICE_UNAVAILABLE": (503, "服务暂时不可用"),
    "ARTIFACT_UNAVAILABLE": (503, "测试证据暂时不可读取"),
}


class ApiError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def error_response(
    request: Request, code: str, *, status_code: int | None = None
) -> JSONResponse:
    status, message = ERRORS[code]
    envelope = ApiErrorEnvelope(
        error=ApiErrorDetail(
            code=code, message=message, request_id=request.state.request_id
        )
    )
    return JSONResponse(
        envelope.model_dump(mode="json"),
        status_code=status if status_code is None else status_code,
        headers={"Cache-Control": "private, no-store"},
    )


def error_responses(*codes: str) -> dict:
    responses = {}
    for code in ("UNAUTHENTICATED", "INTERNAL_ERROR", "SERVICE_UNAVAILABLE", *codes):
        status, message = ERRORS[code]
        response = responses.setdefault(
            status, {"model": ApiErrorEnvelope, "description": ""}
        )
        detail = f"{code} · {message}"
        response["description"] = ", ".join(
            part for part in (response["description"], detail) if part
        )
    return responses
