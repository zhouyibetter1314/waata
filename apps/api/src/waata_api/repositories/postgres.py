"""PostgreSQL transaction boundaries for C6."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg import AsyncCursor
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool
from pydantic import ValidationError
from waata.artifacts import ArtifactRef
from waata.core.events import TestEvent
from waata.orchestrator import TestResult
from waata.orchestrator.models import RunError, Verdict

Row = dict[str, Any]
Cursor = AsyncCursor[Row]

_TERMINAL_EVENTS = {
    "succeeded": "run.completed",
    "errored": "run.failed",
    "cancelled": "run.cancelled",
}
_EVENT_COLUMNS = """
    schema_version, event_id, run_id, sequence, type,
    occurred_at AS timestamp, case_id, step_id, payload
"""


class RunNotCancellable(Exception):
    """The run has already reached a terminal state."""


class LeaseLost(Exception):
    """The Worker may no longer mutate this run."""


class EventConflict(Exception):
    """An existing event ID identifies a different event."""


class InvalidReport(Exception):
    """A report violates the C2 or C6 contract."""


class InvalidEvidence(InvalidReport):
    """Evidence metadata or its use is inconsistent with its registration."""


def _event(run_id: str, kind: str, payload: Row, event_id: str | None = None) -> Row:
    return {
        "schema_version": 1,
        "event_id": event_id if event_id is not None else f"evt_{uuid4().hex}",
        "run_id": run_id,
        "type": kind,
        "timestamp": datetime.now(UTC),
        "case_id": None,
        "step_id": None,
        "payload": payload,
    }


def _artifact_ref(row: Row) -> ArtifactRef:
    values = {name: row[name] for name in ArtifactRef.model_fields}
    values["captured_at"] = values["captured_at"].astimezone(UTC)
    return ArtifactRef.model_validate(values)


class PostgresRepository:
    """Use the same committed run and event records for API and Worker."""

    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool

    async def create_run(
        self,
        *,
        run_id: str,
        owner_id: str,
        request: Row,
        credential_ref: str | None = None,
    ) -> Row:
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(
                """
                INSERT INTO test_runs (run_id, owner_id, request, credential_ref)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (run_id, owner_id, Jsonb(request), credential_ref),
            )
            return await self._required_row(cur)

    async def list_runs(
        self, owner_id: str, *, page: int, page_size: int
    ) -> tuple[list[Row], int]:
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            await cur.execute(
                "SELECT count(*) AS total FROM test_runs WHERE owner_id = %s",
                (owner_id,),
            )
            total = (await self._required_row(cur))["total"]
            offset = (page - 1) * page_size
            if offset >= total:
                return [], total
            await cur.execute(
                """
                SELECT * FROM test_runs WHERE owner_id = %s
                ORDER BY created_at DESC, run_id DESC
                LIMIT %s OFFSET %s
                """,
                (owner_id, page_size, offset),
            )
            return await cur.fetchall(), total

    async def get_run(self, run_id: str, owner_id: str) -> Row | None:
        async with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(
                """
                SELECT r.*, p.result AS report FROM test_runs r
                LEFT JOIN run_reports p USING (run_id)
                WHERE r.run_id = %s AND r.owner_id = %s
                """,
                (run_id, owner_id),
            )
            return await cur.fetchone()

    async def cancel_run(self, run_id: str, owner_id: str) -> Row | None:
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(
                "SELECT * FROM test_runs WHERE run_id = %s AND owner_id = %s FOR UPDATE",
                (run_id, owner_id),
            )
            run = await cur.fetchone()
            if run is None:
                return None
            if run["status"] in _TERMINAL_EVENTS:
                raise RunNotCancellable
            if run["cancellation_requested"]:
                return run
            await cur.execute(
                "UPDATE test_runs SET cancellation_requested = true WHERE run_id = %s RETURNING *",
                (run_id,),
            )
            run = await self._required_row(cur)
            if run["status"] == "queued":
                return await self._finish_locked(
                    cur, run, status="cancelled", verdict=None, error=None, report=None
                )
            return run

    async def claim_run(self, *, lease_seconds: float) -> Row | None:
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(
                """
                SELECT run_id FROM test_runs WHERE status = 'queued'
                ORDER BY created_at, run_id LIMIT 1 FOR UPDATE SKIP LOCKED
                """
            )
            candidate = await cur.fetchone()
            if candidate is None:
                return None
            await cur.execute(
                """
                UPDATE test_runs SET status = 'running', started_at = clock_timestamp(),
                    execution_token = %s,
                    lease_expires_at = clock_timestamp() + make_interval(secs => %s)
                WHERE run_id = %s
                RETURNING *
                """,
                (uuid4().hex, lease_seconds, candidate["run_id"]),
            )
            run = await self._required_row(cur)
            event = _event(run["run_id"], "run.started", {})
            event["timestamp"] = run["started_at"]
            run["last_event_sequence"] = await self._insert_event(cur, run, event)
            return run

    async def heartbeat(
        self, run_id: str, execution_token: str, *, lease_seconds: float
    ) -> Row | None:
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            run = await self._locked_run(cur, run_id)
            if not await self._has_lease(cur, run, execution_token):
                return None
            await cur.execute(
                """
                UPDATE test_runs
                SET lease_expires_at = clock_timestamp() + make_interval(secs => %s)
                WHERE run_id = %s AND lease_expires_at > clock_timestamp()
                RETURNING *
                """,
                (lease_seconds, run_id),
            )
            return await cur.fetchone()

    async def recover_expired(self, *, limit: int = 100) -> int:
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(
                """
                SELECT * FROM test_runs
                WHERE status = 'running'
                    AND (lease_expires_at IS NULL OR lease_expires_at <= clock_timestamp())
                ORDER BY lease_expires_at NULLS FIRST, run_id LIMIT %s FOR UPDATE SKIP LOCKED
                """,
                (limit,),
            )
            runs = await cur.fetchall()
            for run in runs:
                await self._finish_locked(
                    cur,
                    run,
                    status="errored",
                    verdict=None,
                    error={
                        "code": "WORKER_ERROR",
                        "message": "The worker lost its execution lease",
                    },
                    report=None,
                )
            return len(runs)

    async def append_event(self, run_id: str, execution_token: str, event: Row) -> int:
        progress = TestEvent.model_validate(event)
        if progress.run_id != run_id or not progress.event_id.strip():
            raise ValueError("The progress event has invalid identifiers")
        if progress.timestamp.utcoffset() != UTC.utcoffset(None):
            raise ValueError("Progress event timestamps must be in UTC")
        case_scope = bool(progress.case_id)
        step_scope = bool(progress.step_id)
        if (
            (step_scope and not case_scope)
            or (progress.type == "plan.created" and (case_scope or step_scope))
            or (
                progress.type in {"case.started", "case.verified"}
                and (not case_scope or step_scope)
            )
            or (progress.type == "agent.step.started" and not step_scope)
        ):
            raise ValueError("The progress event has an invalid scope")
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            run = await self._locked_run(cur, run_id)
            await cur.execute(
                f"SELECT {_EVENT_COLUMNS} FROM run_events WHERE run_id = %s AND event_id = %s",
                (run_id, progress.event_id),
            )
            existing = await cur.fetchone()
            event = progress.model_dump()
            if existing is not None:
                sequence = existing.pop("sequence")
                if existing != event:
                    raise EventConflict(
                        "The event ID was already used for a different event"
                    )
                return sequence
            if run is None or not await self._has_lease(cur, run, execution_token):
                raise LeaseLost
            await self._update_progress(cur, run, progress)
            if progress.type == "tool.completed":
                await self._check_tool_evidence(cur, progress)
            return await self._insert_event(cur, run, event)

    async def finish_run(
        self,
        run_id: str,
        execution_token: str,
        *,
        status: str,
        verdict: Verdict | None = None,
        error: Row | None = None,
        report: Row | None = None,
        terminal_event_id: str | None = None,
        report_event_id: str | None = None,
    ) -> Row:
        if status not in _TERMINAL_EVENTS:
            raise ValueError("Only terminal statuses can be published")
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            run = await self._locked_run(cur, run_id)
            if run is None:
                raise LeaseLost
            if run["status"] in _TERMINAL_EVENTS and terminal_event_id is not None:
                await cur.execute(
                    "SELECT event_id FROM run_events WHERE run_id = %s AND type = %s",
                    (run_id, _TERMINAL_EVENTS[run["status"]]),
                )
                terminal = await cur.fetchone()
                if terminal and terminal["event_id"] == terminal_event_id:
                    return run
            if not await self._has_lease(cur, run, execution_token):
                raise LeaseLost
            if (
                run["cancellation_requested"]
                and (error or {}).get("code") != "CLEANUP_FAILED"
            ):
                status, verdict, error, report = "cancelled", None, None, None
            if status == "cancelled" and not run["cancellation_requested"]:
                raise ValueError("The run has no committed cancellation request")
            return await self._finish_locked(
                cur,
                run,
                status=status,
                verdict=verdict,
                error=error,
                report=report,
                terminal_event_id=terminal_event_id,
                report_event_id=report_event_id,
            )

    async def read_events(
        self, run_id: str, *, after: int, limit: int = 100
    ) -> list[Row]:
        async with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(
                f"""
                SELECT {_EVENT_COLUMNS} FROM run_events
                WHERE run_id = %s AND sequence > %s ORDER BY sequence LIMIT %s
                """,
                (run_id, after, limit),
            )
            events = await cur.fetchall()
            for event in events:
                event["timestamp"] = event["timestamp"].astimezone(UTC)
            return events

    async def register_artifact(
        self, run_id: str, execution_token: str, artifact: Row
    ) -> Row:
        if artifact["run_id"] != run_id:
            raise InvalidEvidence("The artifact belongs to a different run")
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await self._lock_storage_key(cur, artifact["storage_key"])
            run = await self._locked_run(cur, run_id)
            if not await self._has_lease(cur, run, execution_token):
                raise LeaseLost
            await cur.execute(
                """
                INSERT INTO run_artifacts (
                    artifact_id, run_id, case_id, step_id, tool_call_id, kind,
                    mime_type, captured_at, size_bytes, storage_key, expires_at
                ) VALUES (
                    %(artifact_id)s, %(run_id)s, %(case_id)s, %(step_id)s,
                    %(tool_call_id)s, %(kind)s, %(mime_type)s, %(captured_at)s,
                    %(size_bytes)s, %(storage_key)s, %(expires_at)s
                ) RETURNING *
                """,
                artifact,
            )
            return await self._required_row(cur)

    async def get_artifact(self, artifact_id: str, owner_id: str) -> Row | None:
        async with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(
                """
                SELECT a.* FROM run_artifacts a JOIN test_runs r USING (run_id)
                WHERE a.artifact_id = %s AND r.owner_id = %s
                """,
                (artifact_id, owner_id),
            )
            return await cur.fetchone()

    async def get_artifact_by_storage_key(self, storage_key: str) -> Row | None:
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await self._lock_storage_key(cur, storage_key)
            await cur.execute(
                "SELECT * FROM run_artifacts WHERE storage_key = %s", (storage_key,)
            )
            return await cur.fetchone()

    async def list_artifacts(self, run_id: str) -> list[Row]:
        async with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(
                "SELECT * FROM run_artifacts WHERE run_id = %s ORDER BY captured_at, artifact_id",
                (run_id,),
            )
            return await cur.fetchall()

    async def expired_artifacts(self, *, limit: int = 100) -> list[Row]:
        async with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(
                """
                SELECT * FROM run_artifacts WHERE storage_key IS NOT NULL
                    AND expires_at <= clock_timestamp()
                ORDER BY expires_at, artifact_id LIMIT %s
                """,
                (limit,),
            )
            return await cur.fetchall()

    async def mark_artifact_purged(self, artifact_id: str, storage_key: str) -> bool:
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(
                """
                UPDATE run_artifacts SET storage_key = NULL, purged_at = clock_timestamp()
                WHERE artifact_id = %s AND storage_key = %s AND expires_at <= clock_timestamp()
                """,
                (artifact_id, storage_key),
            )
            if cur.rowcount:
                return True
            await cur.execute(
                "SELECT 1 FROM run_artifacts WHERE artifact_id = %s AND purged_at IS NOT NULL",
                (artifact_id,),
            )
            return await cur.fetchone() is not None

    @staticmethod
    async def _required_row(cur: Cursor) -> Row:
        row = await cur.fetchone()
        if row is None:
            raise RuntimeError("A database mutation did not return its row")
        return row

    @staticmethod
    async def _locked_run(cur: Cursor, run_id: str) -> Row | None:
        await cur.execute(
            "SELECT * FROM test_runs WHERE run_id = %s FOR UPDATE", (run_id,)
        )
        return await cur.fetchone()

    @staticmethod
    async def _lock_storage_key(cur: Cursor, storage_key: str) -> None:
        # Reconciliation must observe the outcome of a previous registration
        # whose commit acknowledgement was lost.
        await cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"waata.artifact:{storage_key}",),
        )

    @staticmethod
    async def _has_lease(cur: Cursor, run: Row | None, execution_token: str) -> bool:
        if (
            run is None
            or run["status"] != "running"
            or run["execution_token"] != execution_token
        ):
            return False
        await cur.execute("SELECT clock_timestamp() AS now")
        return (
            run["lease_expires_at"]
            > (await PostgresRepository._required_row(cur))["now"]
        )

    @staticmethod
    async def _insert_event(cur: Cursor, run: Row, event: Row) -> int:
        sequence = run["last_event_sequence"] + 1
        await cur.execute(
            """
            INSERT INTO run_events (
                schema_version, event_id, run_id, sequence, type, occurred_at, case_id, step_id, payload
            ) VALUES (
                %(schema_version)s, %(event_id)s, %(run_id)s, %(sequence)s, %(type)s,
                %(timestamp)s, %(case_id)s, %(step_id)s, %(payload)s
            )
            """,
            {**event, "sequence": sequence, "payload": Jsonb(event["payload"])},
        )
        await cur.execute(
            "UPDATE test_runs SET last_event_sequence = %s WHERE run_id = %s",
            (sequence, run["run_id"]),
        )
        run["last_event_sequence"] = sequence
        return sequence

    @staticmethod
    async def _update_progress(cur: Cursor, run: Row, event: TestEvent) -> None:
        if event.type == "plan.created":
            total = event.payload["total_cases"]
            if run["total_cases"] is not None and run["total_cases"] != total:
                raise EventConflict("The run already has a different plan size")
            await cur.execute(
                "UPDATE test_runs SET total_cases = %s WHERE run_id = %s",
                (total, run["run_id"]),
            )
        if event.type == "case.verified":
            await cur.execute(
                """
                UPDATE test_runs r SET completed_cases = completed_cases + 1
                WHERE r.run_id = %s AND NOT EXISTS (
                    SELECT 1 FROM run_events WHERE run_id = r.run_id
                        AND type = 'case.verified' AND case_id = %s
                )
                """,
                (run["run_id"], event.case_id),
            )

    @staticmethod
    async def _check_tool_evidence(cur: Cursor, event: TestEvent) -> None:
        ids = event.payload["evidence_ids"]
        if not ids:
            return
        await cur.execute(
            """
            SELECT artifact_id FROM run_artifacts WHERE run_id = %s
                AND case_id IS NOT DISTINCT FROM %s AND step_id IS NOT DISTINCT FROM %s
                AND tool_call_id = %s AND artifact_id = ANY(%s)
            """,
            (
                event.run_id,
                event.case_id,
                event.step_id,
                event.payload["tool_call_id"],
                ids,
            ),
        )
        if {row["artifact_id"] for row in await cur.fetchall()} != set(ids):
            raise InvalidEvidence(
                "The tool event references unregistered or mismatched evidence"
            )

    @staticmethod
    async def _check_report(
        cur: Cursor,
        run_id: str,
        status: str,
        verdict: Verdict | None,
        error: Row | None,
        report: Row,
    ) -> Row:
        try:
            result = TestResult.model_validate(report)
        except ValidationError:
            raise InvalidReport("The report does not satisfy the C2 schema") from None
        report_error = result.error.model_dump() if result.error is not None else None
        if (result.run_id, result.status, result.verdict, report_error) != (
            run_id,
            status,
            verdict,
            error,
        ):
            raise InvalidReport("The report does not match the run's terminal state")
        if status == "succeeded":
            case_verdicts = {case.verdict for case in result.cases}
            if None in case_verdicts:
                raise InvalidReport("A succeeded run must have a verdict for each case")
            expected = next(
                (
                    value
                    for value in ("failed", "blocked", "inconclusive", "passed")
                    if value in case_verdicts
                ),
                "inconclusive",
            )
            if result.verdict != expected:
                raise InvalidReport(
                    "The total verdict does not match the case outcomes"
                )

        refs = {artifact.artifact_id: artifact for artifact in result.artifacts}
        if len(refs) != len(result.artifacts):
            raise InvalidEvidence("The report contains duplicate evidence metadata")
        if refs:
            await cur.execute(
                "SELECT * FROM run_artifacts WHERE run_id = %s AND artifact_id = ANY(%s)",
                (run_id, list(refs)),
            )
            registered = {
                row["artifact_id"]: _artifact_ref(row) for row in await cur.fetchall()
            }
            if registered != refs:
                raise InvalidEvidence(
                    "The report references unregistered or mismatched evidence"
                )

        for case in result.cases:
            for assertion in case.assertions:
                if assertion.passed is not None and not assertion.evidence_ids:
                    raise InvalidEvidence("A decided assertion requires evidence")
                for identifier in assertion.evidence_ids:
                    ref = refs.get(identifier)
                    if ref is None or ref.case_id != case.case_id:
                        raise InvalidEvidence(
                            "Assertion evidence must belong to the same case"
                        )
            for step in case.steps:
                for tool in step.tool_calls:
                    for identifier in tool.evidence_ids:
                        ref = refs.get(identifier)
                        if ref is None or (
                            ref.case_id,
                            ref.step_id,
                            ref.tool_call_id,
                        ) != (case.case_id, step.step_id, tool.tool_call_id):
                            raise InvalidEvidence(
                                "Tool evidence must match the report tool call"
                            )
        return result.model_dump(mode="json")

    async def _finish_locked(
        self,
        cur: Cursor,
        run: Row,
        *,
        status: str,
        verdict: Verdict | None,
        error: Row | None,
        report: Row | None,
        terminal_event_id: str | None = None,
        report_event_id: str | None = None,
    ) -> Row:
        run_id = run["run_id"]
        if status == "succeeded" and report is None:
            raise InvalidReport("A succeeded run must have a report")
        if status == "cancelled" and report is not None:
            raise InvalidReport("A cancelled run cannot have a report")
        if error is not None:
            error = RunError.model_validate(error).model_dump()
        if report is not None:
            report = await self._check_report(
                cur, run_id, status, verdict, error, report
            )
            await cur.execute(
                "INSERT INTO run_reports (run_id, result) VALUES (%s, %s)",
                (run_id, Jsonb(report)),
            )
            await self._insert_event(
                cur,
                run,
                _event(
                    run_id, "report.generated", {"artifact_id": None}, report_event_id
                ),
            )
        terminal = _event(
            run_id,
            _TERMINAL_EVENTS[status],
            {"status": status, "verdict": verdict, "error": error},
            terminal_event_id,
        )
        await self._insert_event(cur, run, terminal)
        await cur.execute(
            """
            UPDATE test_runs SET status = %s, verdict = %s, error = %s,
                finished_at = clock_timestamp(), execution_token = NULL, lease_expires_at = NULL
            WHERE run_id = %s RETURNING *
            """,
            (status, verdict, Jsonb(error) if error is not None else None, run_id),
        )
        return await self._required_row(cur)
