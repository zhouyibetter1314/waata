import asyncio
import unittest
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from psycopg import OperationalError
from waata.core.events import TestEvent
from waata.orchestrator import TestResult, WAATAError
from waata.orchestrator.models import ExecutionContext, RunError, TestCaseResult
from waata_api.repositories import InvalidReport
from waata_api.workers.events import public_event
from waata_api.workers.runner import Worker


class PublicEventTests(unittest.TestCase):
    def test_filters_and_redacts_optional_tool_detail(self):
        event = TestEvent(
            event_id="evt_tool",
            run_id="run_fixture",
            timestamp=datetime.now(UTC),
            type="tool.completed",
            payload={
                "tool": "browser.navigate",
                "tool_call_id": "call_fixture",
                "success": True,
                "duration_ms": 1,
                "error_code": None,
                "evidence_ids": [],
                "detail": {
                    "phase": "start",
                    "target": "Open fixture-secret",
                    "destination": "http://fixture.test/?auth=fixture-secret#private",
                    "screenshot_id": "art_unregistered",
                    "arguments": {"secret_ref": "fixture-secret"},
                },
            },
        )
        values = public_event(
            event,
            "run_fixture",
            lambda value: value.replace("fixture-secret", "[redacted]"),
        )
        self.assertEqual(
            values["payload"]["detail"],
            {
                "phase": "start",
                "target": "Open [redacted]",
                "destination": "http://fixture.test/",
            },
        )


class FakeRepository:
    def __init__(self):
        self.row = {
            "run_id": "run_fixture",
            "owner_id": "owner_fixture",
            "execution_token": "lease_fixture",
            "credential_ref": "credential_fixture",
            "request": {
                "target_url": "http://fixture.test/login?auth=fixture-secret",
                "goal": "Exercise the login form",
                "expected_behavior": "The expected message is visible",
                "options": {"headless": False, "max_steps_per_case": 7},
            },
        }
        self.claimed = False
        self.cancellation_requested = False
        self.lease_lost = False
        self.reject_report = False
        self.progress_failures = 0
        self.finish_failures = 0
        self.progress = []
        self.finishes = []
        self.finished = asyncio.Event()

    async def claim_run(self, *, lease_seconds):
        if self.claimed:
            return None
        self.claimed = True
        return self.row

    async def heartbeat(self, run_id, execution_token, *, lease_seconds):
        if self.lease_lost:
            return None
        return {"cancellation_requested": self.cancellation_requested}

    async def recover_expired(self, *, limit=100):
        return 0

    async def append_event(self, run_id, execution_token, event):
        self.progress.append((run_id, execution_token, event))
        if self.progress_failures:
            self.progress_failures -= 1
            raise OperationalError()
        return len(self.progress)

    async def finish_run(self, run_id, execution_token, **fields):
        self.finishes.append((run_id, execution_token, fields))
        if self.finish_failures:
            self.finish_failures -= 1
            raise OperationalError()
        if self.reject_report and fields["report"] is not None:
            raise InvalidReport()
        self.finished.set()
        return {}


class FakeEngine:
    def __init__(self, *, wait=False, cleanup_failure=False):
        self.started = asyncio.Event()
        self.cleaning = asyncio.Event()
        self.release_cleanup = asyncio.Event()
        self.cleaned = asyncio.Event()
        self.wait = wait
        self.cleanup_failure = cleanup_failure
        self.request = None

    async def run(self, request, *, run_id, on_event):
        self.request = request
        self.started.set()
        result = TestResult(
            run_id=run_id,
            status="succeeded",
            verdict="failed",
            execution=ExecutionContext(
                target_url=request.target_url,
                max_steps_per_case=request.options.max_steps_per_case,
                max_browser_actions_per_run=10,
                max_test_cases=1,
                timeout_seconds=120,
            ),
            cases=[
                TestCaseResult(
                    case_id="case_fixture",
                    name="fixture-secret login",
                    preconditions=[],
                    expected_behavior=request.expected_behavior,
                    verdict="failed",
                )
            ],
        )
        try:
            if self.wait:
                await asyncio.Event().wait()
            await on_event(
                TestEvent(
                    event_id="evt_case",
                    run_id=run_id,
                    timestamp=datetime.now(UTC),
                    type="case.started",
                    case_id="case_fixture",
                    payload={
                        "name": "fixture-secret login",
                        "raw_input": "fixture-secret",
                    },
                )
            )
            return result
        except asyncio.CancelledError:
            self.cleaning.set()
            await self.release_cleanup.wait()
            if self.cleanup_failure:
                error = RunError(
                    code="CLEANUP_FAILED", message="Could not close fixture"
                )
                raise WAATAError(
                    error,
                    result.model_copy(
                        update={"status": "errored", "verdict": None, "error": error}
                    ),
                ) from None
            raise
        finally:
            self.cleaned.set()


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repository = FakeRepository()
        self.stop = asyncio.Event()
        self.claim = None

    async def start(self, engine):
        @asynccontextmanager
        async def factory(claim):
            self.claim = claim
            yield engine

        worker = Worker(
            self.repository,
            factory,
            public_text=lambda value: value.replace("fixture-secret", "[redacted]"),
            concurrency=1,
            lease_seconds=1,
            heartbeat_seconds=0.02,
            poll_seconds=0.01,
            shutdown_seconds=0.2,
        )
        task = asyncio.create_task(worker.run(self.stop))
        self.addAsyncCleanup(self.stop_worker, task)

    async def stop_worker(self, task):
        self.stop.set()
        await asyncio.wait_for(task, 2)

    async def test_maps_c1_options_and_retries_with_stable_ids(self):
        self.repository.progress_failures = 1
        self.repository.finish_failures = 1
        engine = FakeEngine()
        await self.start(engine)
        await asyncio.wait_for(self.repository.finished.wait(), 2)

        self.assertFalse(self.claim.headless)
        self.assertEqual(self.claim.owner_id, "owner_fixture")
        self.assertEqual(engine.request.options.model_dump(), {"max_steps_per_case": 7})
        self.assertEqual(engine.request.credential_ref, "credential_fixture")
        first, second = self.repository.progress
        self.assertEqual(first, second)
        self.assertEqual(first[0:2], ("run_fixture", "lease_fixture"))
        self.assertEqual(first[2]["payload"], {"name": "[redacted] login"})
        first_finish, second_finish = self.repository.finishes
        self.assertEqual(first_finish, second_finish)
        fields = first_finish[2]
        self.assertEqual((fields["status"], fields["verdict"]), ("succeeded", "failed"))
        self.assertEqual(
            fields["report"]["execution"]["target_url"], "http://fixture.test/login"
        )
        self.assertEqual(fields["report"]["cases"][0]["name"], "[redacted] login")

    async def test_cancellation_waits_for_engine_cleanup(self):
        engine = FakeEngine(wait=True)
        await self.start(engine)
        await asyncio.wait_for(engine.started.wait(), 2)
        self.repository.cancellation_requested = True
        await asyncio.wait_for(engine.cleaning.wait(), 2)
        self.assertFalse(self.repository.finished.is_set())
        engine.release_cleanup.set()
        await asyncio.wait_for(self.repository.finished.wait(), 2)
        fields = self.repository.finishes[-1][2]
        self.assertEqual(fields["status"], "cancelled")
        self.assertIsNone(fields["report"])
        self.assertTrue(engine.cleaned.is_set())

    async def test_cancel_cleanup_failure_remains_a_technical_error(self):
        self.repository.reject_report = True
        engine = FakeEngine(wait=True, cleanup_failure=True)
        await self.start(engine)
        await asyncio.wait_for(engine.started.wait(), 2)
        self.repository.cancellation_requested = True
        await asyncio.wait_for(engine.cleaning.wait(), 2)
        engine.release_cleanup.set()
        await asyncio.wait_for(self.repository.finished.wait(), 2)
        fields = self.repository.finishes[-1][2]
        self.assertEqual(fields["status"], "errored")
        self.assertEqual(fields["error"]["code"], "CLEANUP_FAILED")
        self.assertIsNone(fields["report"])

    async def test_lease_loss_stops_engine_and_relinquishes_finalization(self):
        engine = FakeEngine(wait=True)
        await self.start(engine)
        await asyncio.wait_for(engine.started.wait(), 2)
        self.repository.lease_lost = True
        await asyncio.wait_for(engine.cleaning.wait(), 2)
        engine.release_cleanup.set()
        await asyncio.wait_for(engine.cleaned.wait(), 2)
        self.assertEqual(self.repository.finishes, [])

    async def test_invalid_report_falls_back_to_stable_technical_error(self):
        self.repository.reject_report = True
        await self.start(FakeEngine())
        await asyncio.wait_for(self.repository.finished.wait(), 2)
        first, fallback = [attempt[2] for attempt in self.repository.finishes]
        self.assertEqual(first["terminal_event_id"], fallback["terminal_event_id"])
        self.assertEqual(fallback["status"], "errored")
        self.assertEqual(fallback["error"]["code"], "REPORT_WRITE_FAILED")
        self.assertIsNone(fallback["report"])
