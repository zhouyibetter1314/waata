"""Export WAATA run observations through a caller-owned Langfuse SDK client."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langfuse import Langfuse, LangfuseSpan

    from . import Observation, RunObserver


_FIELDS = {
    "plan.created": {"total_cases"},
    "case.started": set(),
    "agent.step.started": set(),
    "model.completed": {
        "phase",
        "duration_ms",
        "total_tokens",
        "finish_reason",
        "error_code",
    },
    "tool.completed": {
        "tool",
        "tool_call_id",
        "success",
        "duration_ms",
        "evidence_count",
        "error_code",
    },
    "case.verified": {"verdict"},
    "run.finished": {"status", "verdict", "duration_ms", "error_code"},
}


class LangfuseObserver:
    """Keep WAATA tracing optional and leave flushing to the client owner."""

    def __init__(self, *, client: Langfuse, model_name: str | None = None) -> None:
        self._client = client
        self._model_name = model_name

    async def start_run(self, run_id: str) -> RunObserver:
        root = self._client.start_observation(
            name="waata.run",
            as_type="span",
            metadata={"run_id": run_id},
            trace_context={"trace_id": self._client.create_trace_id()},
        )
        return _LangfuseRun(root, self._model_name)


class _LangfuseRun:
    def __init__(self, root: LangfuseSpan, model_name: str | None) -> None:
        self._root = root
        self._model_name = model_name

    async def record(self, observation: Observation) -> None:
        if observation.kind not in _FIELDS:
            return
        fields = {
            key: value
            for key, value in observation.fields.items()
            if key in _FIELDS[observation.kind] and value is not None
        }
        metadata = {"run_id": observation.run_id, **fields}
        if observation.case_id is not None:
            metadata["case_id"] = observation.case_id
        if observation.step_id is not None:
            metadata["step_id"] = observation.step_id
        level = "ERROR" if fields.get("error_code") else "DEFAULT"
        if observation.kind == "run.finished":
            self._root.update(metadata=metadata, level=level)
            return
        if observation.kind == "model.completed":
            total = fields.get("total_tokens")
            child = self._root.start_observation(
                name="waata.model",
                as_type="generation",
                metadata=metadata,
                level=level,
                model=self._model_name,
                usage_details={"total": total} if type(total) is int else None,
            )
        else:
            child = self._root.start_observation(
                name=f"waata.{observation.kind}",
                as_type="tool" if observation.kind == "tool.completed" else "span",
                metadata=metadata,
                level=level,
            )
        child.end()

    async def close(self) -> str | None:
        self._root.end()
        return self._root.trace_id
