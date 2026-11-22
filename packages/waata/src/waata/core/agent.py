"""Tools and bounded working history for a single agent execution."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from waata.core.model import (
    ChatMessage,
    ChatResponse,
    ModelMetadata,
    ModelResponseError,
    ToolCall,
    estimate_request_input_tokens,
    input_token_limit,
)
from waata.core.tools import ToolResult, ToolSpec


class ContextLimitError(Exception):
    """The required state and tool messages exceed the input window."""


class AgentHistory:
    """Keep assistant calls and their complete set of tool responses together."""

    def __init__(
        self,
        *,
        summarize: Callable[[ToolCall, ToolResult], dict[str, Any]] | None = None,
        max_summary_chars: int = 2_048,
        sanitize_message: Callable[[ChatMessage], ChatMessage] | None = None,
    ) -> None:
        self._turns: deque[tuple[tuple[ChatMessage, ...], list[dict[str, Any]]]] = (
            deque()
        )
        self._archived_summaries: deque[str] = deque()
        self._summary_chars = 0
        self._max_summary_chars = max_summary_chars
        self._summarize = summarize
        self._sanitize_message = sanitize_message

    def append(self, assistant: ChatMessage, results: Sequence[ToolResult]) -> None:
        _validate_calls(assistant)
        if not results or len(results) != len(assistant.tool_calls):
            raise ValueError("A completed tool turn requires all its results")

        if self._sanitize_message is not None:
            sanitized = self._sanitize_message(assistant)
            if sanitized.role != "assistant" or tuple(
                call.id for call in sanitized.tool_calls
            ) != tuple(call.id for call in assistant.tool_calls):
                raise ValueError("Sanitized messages must preserve tool call IDs")
            assistant = sanitized

        messages = [assistant]
        summaries = []
        for call, result in zip(assistant.tool_calls, results, strict=True):
            messages.append(
                ChatMessage("tool", _json(result.to_dict()), tool_call_id=call.id)
            )
            summary: dict[str, Any] = {
                "tool": call.name,
                "success": result.success,
                "error_code": result.error.code if result.error else None,
            }
            if self._summarize is not None:
                summary.update(self._summarize(call, result))
            summaries.append(summary)
        self._turns.append((tuple(messages), summaries))

    def build_messages(
        self,
        system: str,
        state: Mapping[str, Any],
        *,
        tools: Sequence[ToolSpec],
        metadata: ModelMetadata,
        max_input_tokens: int | None = None,
        safety_margin: int = 128,
    ) -> tuple[ChatMessage, ...]:
        limit = input_token_limit(metadata, max_input_tokens, safety_margin)
        system_message = ChatMessage("system", system)
        while True:
            data: dict[str, Any] = {"state": dict(state)}
            if self._archived_summaries:
                data["older_tool_results"] = [
                    json.loads(summary) for summary in self._archived_summaries
                ]
            messages = (
                system_message,
                ChatMessage("user", _json(data)),
                *(message for turn, _ in self._turns for message in turn),
            )
            if estimate_request_input_tokens(messages, tools) <= limit:
                return messages
            if len(self._turns) > 1:
                _, summaries = self._turns.popleft()
                self._archive(summaries)
            elif self._archived_summaries:
                self._summary_chars -= len(self._archived_summaries.popleft())
            else:
                raise ContextLimitError(
                    "Required agent context exceeds the model window"
                )

    def _archive(self, summaries: list[dict[str, Any]]) -> None:
        encoded = _json(summaries)
        if len(encoded) > self._max_summary_chars:
            return
        self._archived_summaries.append(encoded)
        self._summary_chars += len(encoded)
        while self._summary_chars > self._max_summary_chars:
            self._summary_chars -= len(self._archived_summaries.popleft())


async def agent_step(
    response: ChatResponse,
    execute: Callable[[ToolCall], Awaitable[ToolResult]],
    history: AgentHistory,
) -> bool:
    """Validate and dispatch one assistant turn in the model's original order."""
    assistant = response.message
    _validate_calls(assistant)
    if response.finish_reason in {"length", "content_filter", "aborted"}:
        raise ModelResponseError("Model stopped before completing its response")
    if not assistant.tool_calls:
        if response.finish_reason == "tool_calls":
            raise ModelResponseError("Model omitted its tool calls")
        return False

    results = []
    for call in assistant.tool_calls:
        results.append(await execute(call))
    history.append(assistant, results)
    return True


def _validate_calls(assistant: ChatMessage) -> None:
    if assistant.role != "assistant":
        raise ModelResponseError("Model response must contain an assistant message")
    ids = {call.id for call in assistant.tool_calls if call.id}
    if len(ids) != len(assistant.tool_calls):
        raise ModelResponseError("Model tool calls must have unique, nonempty IDs")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
