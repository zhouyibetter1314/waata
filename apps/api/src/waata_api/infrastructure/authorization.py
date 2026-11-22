import re
from dataclasses import dataclass
from hmac import compare_digest
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, TypeAdapter

from waata_api.api.errors import ApiError
from waata_api.schemas.test_runs import CreateRunRequest

COOKIE_NAME = "waata_dev_session"
Origin = tuple[str, str | None, int | None]
_http_url = TypeAdapter(AnyHttpUrl)
_url_in_text = re.compile(r"""https?://[^\s<>"'，。；、]+""", re.IGNORECASE)
_secret_label = re.compile(
    r"(?i)(\b(?:authorization|cookie|password|passwd|api[-_ ]?key|"
    r"credential_ref|secret(?:_ref)?|token)\b|密码|密钥)"
    r"""["']?\s*[:=]"""
)


def origin_of(value: str) -> Origin:
    url = _http_url.validate_python(value)
    return url.scheme, url.host, url.port


def display_url(value: str) -> str:
    url = urlsplit(str(_http_url.validate_python(value)))
    return url._replace(
        netloc=url.netloc.rsplit("@", 1)[-1], query="", fragment=""
    ).geturl()


@dataclass(frozen=True)
class Principal:
    subject: str
    origins: frozenset[Origin]
    credential_refs: frozenset[str] = frozenset()


class AccessPolicy:
    def __init__(self, tokens: dict[str, Principal] | None = None) -> None:
        self._tokens = dict(tokens or {})
        secrets = {*self._tokens}
        for principal in self._tokens.values():
            secrets.update(principal.credential_refs)
        self._redact = tuple(sorted(filter(None, secrets), key=len, reverse=True))

    def authenticate(self, token: str | None) -> Principal:
        if token:
            for configured, principal in self._tokens.items():
                if compare_digest(token.encode(), configured.encode()):
                    return principal
        raise ApiError(401, "UNAUTHENTICATED", "需要有效的平台身份")

    def authorize_submission(
        self, principal: Principal, data: CreateRunRequest
    ) -> None:
        if origin_of(data.target_url) not in principal.origins:
            raise ApiError(403, "TARGET_NOT_ALLOWED", "测试目标未获授权")
        if (
            data.credential_ref is not None
            and data.credential_ref not in principal.credential_refs
        ):
            raise ApiError(403, "CREDENTIAL_NOT_ALLOWED", "测试凭据未获授权")
        if _secret_label.search(data.goal) or _secret_label.search(
            data.expected_behavior
        ):
            raise ApiError(422, "VALIDATION_ERROR", "目标和预期行为不得包含凭据值")

    @staticmethod
    def can_read(principal: Principal, owner_id: str | None) -> bool:
        return owner_id == principal.subject

    def require_resource(
        self, principal: Principal, owner_id: str | None, *, artifact: bool = False
    ) -> None:
        if not self.can_read(principal, owner_id):
            if artifact:
                raise ApiError(404, "ARTIFACT_NOT_FOUND", "证据不存在")
            raise ApiError(404, "RUN_NOT_FOUND", "测试任务不存在")

    def redact_display(self, value: str) -> str:
        def safe_link(match: re.Match[str]) -> str:
            try:
                return display_url(match[0])
            except ValueError:
                return "[REDACTED]"

        value = _url_in_text.sub(safe_link, value)
        for secret in self._redact:
            value = value.replace(secret, "[REDACTED]")
        return value
