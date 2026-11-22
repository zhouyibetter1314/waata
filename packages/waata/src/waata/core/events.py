"""C4 event DTO exposed to the caller of TestEngine."""

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

EventType = Literal[
    "plan.created",
    "case.started",
    "agent.step.started",
    "tool.called",
    "tool.completed",
    "case.verified",
]


class TestEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    event_id: str
    run_id: str
    type: EventType
    timestamp: AwareDatetime
    case_id: str | None = None
    step_id: str | None = None
    payload: dict[str, Any]
