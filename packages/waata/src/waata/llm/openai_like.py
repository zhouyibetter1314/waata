"""OpenAI-compatible asynchronous Chat Completions (FR-002)."""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import Any

import httpx

from waata.core.model import (
    ChatMessage,
    ChatResponse,
    ModelError,
    ModelMetadata,
    ModelRateLimitError,
    ModelResponseError,
    ModelUsage,
    ToolCall,
)
from waata.core.tools import ToolSpec

_FUNCTION_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
_LOG = logging.getLogger(__name__)
_DEFAULT_RATE_LIMIT_WAIT = 30.0
_QUOTA_CODES = {
    "accountoverdue",
    "insufficientbalance",
    "insufficient_quota",
    "quotaexceeded",
}


def _http_failure(response: httpx.Response) -> tuple[str, bool]:
    status = response.status_code
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        message = error.get("message") if isinstance(error, dict) else None
    except (ValueError, RecursionError):
        code = None
        message = None
    if status == 402 or (isinstance(code, str) and code.lower() in _QUOTA_CODES):
        return "quota_or_balance", False
    if status == 429 or (
        isinstance(message, str)
        and "cluster tpm rate limit exceeded" in message.lower()
    ):
        return "rate_limit", True
    if status in {400, 422}:
        return "request_format", False
    if status in {401, 403}:
        return "authentication_or_permission", False
    if status == 408:
        return "timeout", True
    return (
        ("provider_error", True)
        if status == 425 or status >= 500
        else ("http_error", False)
    )


def _retry_after(response: httpx.Response) -> float:
    value = response.headers.get("Retry-After", "").strip()
    if value.isascii() and value.isdecimal():
        seconds = float(value)
        return max(0.2, seconds)
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=UTC)
        return max(0.2, (date - datetime.now(UTC)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return _DEFAULT_RATE_LIMIT_WAIT


class OpenAILike:
    """Call a compatible provider using an optional caller-owned HTTP client."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        context_window: int = 32_768,
        max_output_tokens: int = 2_048,
        supports_tools: bool = True,
        supports_json: bool | None = None,
        timeout: float = 30,
        thinking: bool | None = None,
    ) -> None:
        try:
            url = httpx.URL(base_url)
        except httpx.InvalidURL:
            raise ValueError("Model base URL must be an absolute HTTP(S) URL") from None
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.userinfo
            or url.query
            or url.fragment
        ):
            raise ValueError("Model base URL must be an absolute HTTP(S) URL")
        if not model.strip() or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("A model name and positive finite timeout are required")
        if thinking is True:
            raise ValueError("Thinking mode requires a dedicated provider adapter")

        path = url.raw_path.partition(b"?")[0].rstrip(b"/")
        if not path.endswith(b"/chat/completions"):
            path += b"/chat/completions"
        self._endpoint = url.copy_with(raw_path=path)
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._retry_at = 0.0
        self._disable_thinking = thinking is False or url.host in {
            "api.deepseek.com",
            "ark.cn-beijing.volces.com",
        }
        self._metadata = ModelMetadata(
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            supports_tools=supports_tools,
            supports_json=(
                url.scheme == "https" and url.host == "api.deepseek.com"
                if supports_json is None
                else supports_json
            ),
        )
        self._owns_client = client is None
        self._client = client if client is not None else httpx.AsyncClient()

    @property
    def metadata(self) -> ModelMetadata:
        return self._metadata

    async def __aenter__(self) -> OpenAILike:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSpec] = (),
        json_mode: bool = False,
        max_output_tokens: int | None = None,
    ) -> ChatResponse:
        output_limit = (
            self.metadata.max_output_tokens
            if max_output_tokens is None
            else max_output_tokens
        )
        if not 0 < output_limit <= self.metadata.max_output_tokens:
            raise ModelError("Requested model output exceeds the configured limit")
        if tools and not self.metadata.supports_tools:
            raise ModelError("The configured model does not support tool calling")
        if json_mode and not self.metadata.supports_json:
            raise ModelError("The configured model does not support JSON mode")
        cooldown = self._retry_at - monotonic()
        if cooldown > 0:
            raise ModelRateLimitError(
                "Model service is rate limited", retry_after=cooldown
            )

        tool_definitions, internal_names = _encode_tools(tools)
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [_encode_message(message) for message in messages],
            "max_tokens": output_limit,
            "stream": False,
        }
        if tool_definitions:
            body["tools"] = tool_definitions
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self._disable_thinking:
            body["thinking"] = {"type": "disabled"}

        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            response = await self._client.post(
                self._endpoint,
                json=body,
                headers=headers,
                timeout=self._timeout,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            _LOG.warning("Model request failed: category=timeout")
            raise ModelError(
                "Model service request timed out", retryable=True
            ) from None
        except (httpx.NetworkError, httpx.RemoteProtocolError):
            _LOG.warning("Model request failed: category=network")
            raise ModelError("Model service request failed", retryable=True) from None
        except httpx.HTTPError:
            _LOG.warning("Model request failed: category=transport")
            raise ModelError("Model service request failed") from None

        if not response.is_success:
            category, retryable = _http_failure(response)
            _LOG.warning(
                "Model service returned HTTP %s: category=%s",
                response.status_code,
                category,
            )
            if category == "rate_limit":
                retry_after = _retry_after(response)
                self._retry_at = max(self._retry_at, monotonic() + retry_after)
                raise ModelRateLimitError(
                    f"Model service returned HTTP {response.status_code}",
                    retry_after=retry_after,
                )
            raise ModelError(
                f"Model service returned HTTP {response.status_code}",
                retryable=retryable,
            )
        try:
            payload = response.json()
        except (ValueError, RecursionError):
            raise ModelResponseError("Model response was not valid JSON") from None
        return _decode_response(payload, internal_names)


def _wire_name(name: str) -> str:
    alias = name.replace(".", "_")
    if not _FUNCTION_NAME.fullmatch(alias):
        raise ModelError("A registered tool has an invalid function name")
    return alias


def _encode_tools(
    tools: Sequence[ToolSpec],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    definitions = []
    names: dict[str, str] = {}
    for tool in tools:
        alias = _wire_name(tool.name)
        if alias in names:
            raise ModelError("Registered tools map to the same function name")
        names[alias] = tool.name
        parameters = tool.model_input_schema
        parameters.setdefault("type", "object")
        definitions.append(
            {
                "type": "function",
                "function": {
                    "name": alias,
                    "description": tool.description,
                    "parameters": parameters,
                },
            }
        )
    return definitions, names


def _encode_message(message: ChatMessage) -> dict[str, Any]:
    data: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_call_id is not None:
        data["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        data["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.wire_name or _wire_name(call.name),
                    "arguments": json.dumps(
                        call.arguments or {}, ensure_ascii=False, allow_nan=False
                    ),
                },
            }
            for call in message.tool_calls
        ]
    return data


def _decode_response(payload: Any, names: dict[str, str]) -> ChatResponse:
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ModelResponseError("Model response did not contain a completion")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise ModelResponseError("Model response did not contain an assistant message")
    content = message.get("content")
    finish_reason = choice.get("finish_reason")
    if (content is not None and not isinstance(content, str)) or (
        finish_reason is not None and not isinstance(finish_reason, str)
    ):
        raise ModelResponseError("Model response contained invalid message fields")
    if content is not None:
        try:
            content.encode()
        except UnicodeEncodeError:
            raise ModelResponseError("Model response contained invalid text") from None

    raw_calls = message.get("tool_calls")
    if raw_calls is None:
        raw_calls = []
    if not isinstance(raw_calls, list):
        raise ModelResponseError("Model response contained invalid tool calls")
    calls = tuple(_decode_call(raw, names) for raw in raw_calls)
    if len({call.id for call in calls}) != len(calls):
        raise ModelResponseError("Model tool calls must have unique IDs")

    return ChatResponse(
        ChatMessage("assistant", content, calls),
        finish_reason=finish_reason,
        usage=_decode_usage(payload.get("usage")),
    )


def _decode_call(raw: Any, names: dict[str, str]) -> ToolCall:
    if not isinstance(raw, dict) or raw.get("type") != "function":
        raise ModelResponseError("Model response contained an invalid tool call")
    call_id = raw.get("id")
    function = raw.get("function")
    if (
        not isinstance(call_id, str)
        or not call_id.strip()
        or not isinstance(function, dict)
    ):
        raise ModelResponseError("Model response contained an invalid tool call")
    alias = function.get("name")
    if not isinstance(alias, str) or not _FUNCTION_NAME.fullmatch(alias):
        raise ModelResponseError("Model response contained an invalid function name")
    return ToolCall(
        call_id,
        names.get(alias, alias),
        _decode_arguments(function.get("arguments")),
        wire_name=alias,
    )


def _decode_arguments(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("Duplicate key")
        return result

    def reject_nonfinite(_: str) -> None:
        raise ValueError("Nonfinite value")

    try:
        value = json.loads(
            raw, object_pairs_hook=unique_object, parse_constant=reject_nonfinite
        )
        # Python can also produce a nonfinite float from a JSON numeric exponent.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _decode_usage(raw: Any) -> ModelUsage | None:
    if not isinstance(raw, dict):
        return None

    input_tokens = raw.get("prompt_tokens")
    output_tokens = raw.get("completion_tokens")
    total_tokens = raw.get("total_tokens")
    if type(total_tokens) is not int or total_tokens < 0:
        if not (
            type(input_tokens) is int
            and input_tokens >= 0
            and type(output_tokens) is int
            and output_tokens >= 0
        ):
            return None
        total_tokens = input_tokens + output_tokens
    input_tokens = (
        input_tokens if type(input_tokens) is int and input_tokens >= 0 else 0
    )
    output_tokens = (
        output_tokens if type(output_tokens) is int and output_tokens >= 0 else 0
    )
    return ModelUsage(
        input_tokens, output_tokens, max(total_tokens, input_tokens + output_tokens)
    )
