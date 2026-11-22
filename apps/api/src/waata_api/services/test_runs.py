from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from waata_api.api.errors import ApiError
from waata_api.infrastructure.authorization import AccessPolicy, Principal, display_url
from waata_api.infrastructure.run_queue import QueueUnavailable, RunQueue
from waata_api.repositories.test_runs import RunRecord, RunRepository
from waata_api.schemas.test_runs import (
    CreateRunRequest,
    RunAccepted,
    RunDetail,
    RunPage,
    RunProgress,
    RunSummary,
)


class RunService:
    def __init__(
        self,
        repository: RunRepository,
        queue: RunQueue,
        access: AccessPolicy,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        new_run_id: Callable[[], str] = lambda: f"run_{uuid4().hex}",
    ) -> None:
        self._repository = repository
        self._queue = queue
        self._access = access
        self._clock = clock
        self._new_run_id = new_run_id
        # Coordinates the in-process substitutes. B03 will use a storage transaction.
        self._lock = Lock()

    def create(self, principal: Principal, request: CreateRunRequest) -> RunAccepted:
        self._access.authorize_submission(principal, request)
        with self._lock:
            run_id = self._new_run_id()
            created_at = self._clock().astimezone(UTC)
            detail = RunDetail(
                run_id=run_id,
                target_url=self._access.redact_display(display_url(request.target_url)),
                goal=self._access.redact_display(request.goal),
                expected_behavior=self._access.redact_display(
                    request.expected_behavior
                ),
                status="queued",
                verdict=None,
                created_at=created_at,
                started_at=None,
                finished_at=None,
                progress=RunProgress(total_cases=None, completed_cases=0),
                summary=None,
                error=None,
                cancellation_requested=False,
            )
            self._repository.add(RunRecord(principal.subject, request, detail))
            try:
                self._queue.enqueue(run_id)
            except QueueUnavailable:
                self._repository.remove(run_id)
                raise ApiError(503, "SERVICE_UNAVAILABLE", "任务队列暂不可用") from None
        return RunAccepted(run_id=run_id, created_at=created_at)

    def list(self, principal: Principal, page: int, page_size: int) -> RunPage:
        with self._lock:
            runs = [
                record.detail
                for record in self._repository.list_owned(principal.subject)
            ]
        runs.sort(key=lambda detail: detail.run_id)
        runs.sort(key=lambda detail: detail.created_at, reverse=True)
        start = (page - 1) * page_size
        return RunPage(
            items=[
                RunSummary.model_validate(detail.model_dump())
                for detail in runs[start : start + page_size]
            ],
            page=page,
            page_size=page_size,
            total=len(runs),
        )

    def detail(self, principal: Principal, run_id: str) -> RunDetail:
        with self._lock:
            record = self._repository.get(run_id)
        self._access.require_resource(
            principal, record.owner_id if record is not None else None
        )
        assert record is not None
        return record.detail
