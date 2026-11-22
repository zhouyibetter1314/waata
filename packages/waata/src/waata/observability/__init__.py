"""Optional run observations for a caller-supplied exporter."""

from dataclasses import dataclass, field
from typing import Protocol

from .langfuse import LangfuseObserver

__all__ = ["LangfuseObserver", "NoOpObserver", "Observation", "Observer", "RunObserver"]


@dataclass(frozen=True, slots=True)
class Observation:
    kind: str
    run_id: str
    case_id: str | None = None
    step_id: str | None = None
    fields: dict[str, str | int | bool | None] = field(default_factory=dict)


class RunObserver(Protocol):
    async def record(self, observation: Observation) -> None: ...

    async def close(self) -> str | None:
        """Close this observation scope and return its optional trace ID."""


class Observer(Protocol):
    async def start_run(self, run_id: str) -> RunObserver: ...


class NoOpObserver:
    async def start_run(self, run_id: str) -> RunObserver:
        return self

    async def record(self, observation: Observation) -> None:
        pass

    async def close(self) -> str | None:
        return None
