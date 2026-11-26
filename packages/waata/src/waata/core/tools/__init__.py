"""Tool registration and strict dispatch at the agent boundary (FR-003)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError


@dataclass(frozen=True, slots=True)
class ToolError:
    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class ToolResult:
    success: bool
    data: dict[str, Any] | None = field(default=None, repr=False)
    error: ToolError | None = None

    @classmethod
    def failed(cls, code: str, message: str, retryable: bool = False) -> ToolResult:
        return cls(success=False, error=ToolError(code, message, retryable))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ToolContext:
    run_id: str
    case_id: str | None
    step_id: str | None
    tool_call_id: str
    deadline: float
    reserve_action: Callable[[], bool] | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[Any, ToolContext], Awaitable[ToolResult]] = field(repr=False)
    model_schema: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    @property
    def model_input_schema(self) -> dict[str, Any]:
        """Omit non-validation metadata from the schema repeated on each model turn."""
        return _compact_schema(
            self.input_schema if self.model_schema is None else self.model_schema
        )


def _compact_schema(schema: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in schema.items():
        if key in {"title", "discriminator"}:
            continue
        if key in {"properties", "$defs", "patternProperties"}:
            value = {name: _compact_schema(item) for name, item in value.items()}
        elif key in {"anyOf", "allOf", "oneOf", "prefixItems"}:
            value = [_compact_schema(item) for item in value]
        elif key in {"items", "additionalProperties", "not"} and isinstance(
            value, dict
        ):
            value = _compact_schema(value)
        result[key] = value
    return result


class ToolRegistry:
    def __init__(self, specs: Iterable[ToolSpec]) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._properties: dict[str, frozenset[str]] = {}
        for spec in specs:
            if not spec.name or spec.name in self._specs:
                raise ValueError("Tool names must be nonempty and unique")
            self._specs[spec.name] = spec
            properties = spec.input_schema.get("properties")
            if isinstance(properties, dict):
                self._properties[spec.name] = frozenset(properties)

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._specs.values())

    async def execute(
        self, name: str, arguments: dict[str, Any] | None, context: ToolContext
    ) -> ToolResult:
        spec = self._specs.get(name)
        if spec is None:
            return ToolResult.failed("UNKNOWN_TOOL", "Tool is unavailable in this run")
        properties = self._properties.get(name)
        if not isinstance(arguments, dict) or (
            properties is not None and arguments.keys() - properties
        ):
            return ToolResult.failed("INVALID_ARGUMENTS", "Invalid tool arguments")
        try:
            params = spec.input_model.model_validate(arguments, strict=True)
        except ValidationError:
            return ToolResult.failed("INVALID_ARGUMENTS", "Invalid tool arguments")

        if asyncio.get_running_loop().time() >= context.deadline:
            return ToolResult.failed("TOOL_TIMEOUT", "Tool deadline expired")
        try:
            async with asyncio.timeout_at(context.deadline):
                return await spec.handler(params, context)
        except TimeoutError:
            return ToolResult.failed("TOOL_TIMEOUT", "Tool deadline expired")
        except Exception:
            return ToolResult.failed("INTERNAL_ERROR", "Tool execution failed")
