from collections import deque
from typing import Protocol


class QueueUnavailable(Exception):
    """Submission failed and the run was not queued."""


class RunQueue(Protocol):
    def enqueue(self, run_id: str) -> None:
        """Raise QueueUnavailable if the queue cannot accept the run."""
        ...


class MemoryRunQueue:
    def __init__(self, capacity: int = 1000) -> None:
        self._pending: deque[str] = deque()
        self._capacity = capacity

    def enqueue(self, run_id: str) -> None:
        if len(self._pending) >= self._capacity:
            raise QueueUnavailable
        self._pending.append(run_id)
