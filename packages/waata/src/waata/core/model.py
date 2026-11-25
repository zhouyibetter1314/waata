"""Provider-neutral messages and limits used by the agent (FR-002, NFR-006)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from waata.core.tools import ToolSpec


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] | None = field(repr=False)
    wire_name: str | None = None


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = field(default=None, repr=False)
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ModelUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ChatResponse:
    message: ChatMessage
    finish_reason: str | None = None
    usage: ModelUsage | None = None


@dataclass(frozen=True, slots=True)
class ModelMetadata:
    context_window: int = 32_768
    max_output_tokens: int = 2_048
    supports_tools: bool = True
    supports_json: bool = False

    def __post_init__(self) -> None:
        if not 0 < self.max_output_tokens < self.context_window:
            raise ValueError("The context window must leave room for input and output")


class ModelError(Exception):
    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ModelResponseError(ModelError):
    """The provider returned a response that cannot be consumed."""


class ModelRateLimitError(ModelError):
    """The provider has temporarily limited request volume."""

    def __init__(self, message: str, *, retry_after: float) -> None:
        super().__init__(message, retryable=True)
        self.retry_after = retry_after


class LLMProvider(Protocol):
    @property
    def metadata(self) -> ModelMetadata: ...

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSpec] = (),
        json_mode: bool = False,
        max_output_tokens: int | None = None,
    ) -> ChatResponse: ...


def input_token_limit(
    metadata: ModelMetadata,
    max_input_tokens: int | None = None,
    safety_margin: int = 128,
) -> int:
    capacity = metadata.context_window - metadata.max_output_tokens - safety_margin
    return capacity if max_input_tokens is None else min(capacity, max_input_tokens)


def estimate_request_input_tokens(
    messages: Sequence[ChatMessage], tools: Sequence[ToolSpec] = ()
) -> int:
    """Use UTF-8 bytes as a conservative estimate for compatible models."""

    def estimate(value: Any) -> int:
        return len(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        )

    tokens = 16
    for message in messages:
        tokens += 16 + estimate(message.role)
        if message.content is not None:
            tokens += estimate(message.content)
        if message.tool_call_id is not None:
            tokens += 16 + estimate(message.tool_call_id)
        for call in message.tool_calls:
            arguments = json.dumps(call.arguments or {}, ensure_ascii=False)
            tokens += 40 + estimate([call.id, call.wire_name or call.name, arguments])
    for tool in tools:
        tokens += 40 + estimate([tool.name, tool.description, tool.model_input_schema])
    return tokens
