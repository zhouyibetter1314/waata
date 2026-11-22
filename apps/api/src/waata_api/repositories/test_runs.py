from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from waata_api.schemas.test_runs import CreateRunRequest, RunDetail


@dataclass(frozen=True)
class RunRecord:
    owner_id: str
    request: CreateRunRequest
    detail: RunDetail


class RunRepository(Protocol):
    def add(self, record: RunRecord) -> None: ...
    def remove(self, run_id: str) -> None: ...
    def get(self, run_id: str) -> RunRecord | None: ...
    def list_owned(self, owner_id: str) -> Iterable[RunRecord]: ...


class MemoryRunRepository:
    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}

    def add(self, record: RunRecord) -> None:
        self._runs[record.detail.run_id] = record

    def remove(self, run_id: str) -> None:
        del self._runs[run_id]

    def get(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def list_owned(self, owner_id: str) -> Iterable[RunRecord]:
        return (record for record in self._runs.values() if record.owner_id == owner_id)
