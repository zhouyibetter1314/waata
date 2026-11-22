"""A deterministic model substitute for local and contract checks (NFR-003)."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from waata.core.model import ChatMessage, ChatResponse, ModelError, ModelMetadata
from waata.core.tools import ToolSpec


@dataclass(frozen=True, slots=True)
class ModelRequest:
    messages: tuple[ChatMessage, ...] = field(repr=False)
    tools: tuple[ToolSpec, ...]
    json_mode: bool
    max_output_tokens: int | None


class FakeLLM:
    def __init__(
        self,
        responses: Iterable[ChatResponse | BaseException],
        *,
        metadata: ModelMetadata | None = None,
    ) -> None:
        self._responses = deque(responses)
        self._metadata = metadata or ModelMetadata(supports_json=True)
        self.requests: list[ModelRequest] = []

    @property
    def metadata(self) -> ModelMetadata:
        return self._metadata

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSpec] = (),
        json_mode: bool = False,
        max_output_tokens: int | None = None,
    ) -> ChatResponse:
        self.requests.append(
            ModelRequest(tuple(messages), tuple(tools), json_mode, max_output_tokens)
        )
        if not self._responses:
            raise ModelError("FakeLLM has no scripted response for this request")
        response = self._responses.popleft()
        if isinstance(response, BaseException):
            raise response
        return response
