"""Exercise C6 transaction boundaries on an isolated PostgreSQL 17 schema."""

import asyncio
import os
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from psycopg import AsyncConnection, sql
from psycopg.errors import CheckViolation
from psycopg_pool import AsyncConnectionPool
from waata_api.repositories import (
    EventConflict,
    InvalidEvidence,
    LeaseLost,
    PostgresRepository,
    RunNotCancellable,
    RunNotDeletable,
)

_DSN = os.environ.get("WAATA_TEST_DATABASE_URL")
_MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"


def progress(run_id, event_id, kind, payload, *, case_id=None, step_id=None):
    return {
        "event_id": event_id,
        "run_id": run_id,
        "type": kind,
        "timestamp": datetime.now(UTC),
        "case_id": case_id,
        "step_id": step_id,
        "payload": payload,
    }


def empty_report(run_id):
    return {
        "run_id": run_id,
        "status": "succeeded",
        "verdict": "inconclusive",
        "execution": {
            "target_url": "http://localhost/",
            "max_steps_per_case": 10,
            "max_browser_actions_per_run": 10,
            "max_test_cases": 1,
            "timeout_seconds": 20.0,
        },
    }


@unittest.skipUnless(
    _DSN, "set WAATA_TEST_DATABASE_URL to an independent PostgreSQL 17 database"
)
class PostgresRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = f"test_c6_{uuid4().hex}"
        self.admin = await AsyncConnection.connect(
            _DSN, autocommit=True, connect_timeout=5
        )
        self.addAsyncCleanup(self.admin.close)
        identifier = sql.Identifier(self.schema)
        await self.admin.execute(sql.SQL("CREATE SCHEMA {}").format(identifier))
        self.addAsyncCleanup(
            self.admin.execute, sql.SQL("DROP SCHEMA {} CASCADE").format(identifier)
        )
        self.pool = AsyncConnectionPool(
            _DSN,
            kwargs={
                "autocommit": True,
                "options": f"-c search_path={self.schema},public",
            },
            min_size=1,
            max_size=4,
            open=False,
        )
        await self.pool.open(wait=True, timeout=5)
        self.addAsyncCleanup(self.pool.close)
        self.repo = PostgresRepository(self.pool)
        await self.apply_migration("0001_platform_persistence.sql")
        legacy = await self.create_run("legacy")
        self.assertEqual(legacy["status"], "queued")
        await self.apply_migration("0002_run_execution_lease.sql")
        await self.apply_migration("0003_run_artifact_cleanup.sql")

    async def apply_migration(self, name):
        async with self.pool.connection() as conn:
            await conn.execute((_MIGRATIONS / name).read_text())

    async def create_run(self, run_id, owner="alice"):
        return await self.repo.create_run(
            run_id=run_id, owner_id=owner, request={"target_url": "http://localhost/"}
        )

    async def test_terminal_deletion_cascades_and_retains_cleanup_job(self):
        with self.assertRaises(RunNotDeletable):
            await self.repo.delete_run("legacy", "alice")
        token = await self.claim("legacy")
        with self.assertRaises(RunNotDeletable):
            await self.repo.delete_run("legacy", "alice")
        artifact = {
            "artifact_id": "art_delete",
            "run_id": "legacy",
            "case_id": None,
            "step_id": None,
            "tool_call_id": None,
            "kind": "observation",
            "mime_type": "application/json",
            "captured_at": datetime.now(UTC),
            "size_bytes": 2,
            "storage_key": "key_delete",
            "expires_at": None,
        }
        await self.repo.register_artifact("legacy", token, artifact)
        await self.repo.finish_run(
            "legacy",
            token,
            status="succeeded",
            verdict="inconclusive",
            report=empty_report("legacy"),
        )
        self.assertFalse(await self.repo.delete_run("legacy", "bob"))
        self.assertTrue(await self.repo.delete_run("legacy", "alice"))
        self.assertFalse(await self.repo.delete_run("legacy", "alice"))
        self.assertIsNone(await self.repo.get_run("legacy", "alice"))
        self.assertIsNone(await self.repo.get_artifact("art_delete", "alice"))
        self.assertEqual(await self.repo.read_events("legacy", after=0), [])
        jobs = await self.repo.deleted_artifacts(run_id="legacy", limit=1)
        self.assertEqual(
            jobs, [{"storage_key": "key_delete", "mime_type": "application/json"}]
        )
        await self.repo.finish_artifact_deletion("key_delete", retry=True)
        self.assertEqual(await self.repo.deleted_artifacts(run_id=None, limit=1), [])
        await self.repo.finish_artifact_deletion("key_delete", retry=False)
        cursor = await self.admin.execute(
            sql.SQL("SELECT count(*) FROM {}.deleted_run_artifacts").format(
                sql.Identifier(self.schema)
            )
        )
        self.assertEqual(await cursor.fetchone(), (0,))

    async def claim(self, run_id):
        run = await self.repo.claim_run(lease_seconds=10)
        self.assertEqual(run["run_id"], run_id)
        return run["execution_token"]

    async def test_upgrade_owner_listing_and_atomic_concurrent_claim(self):
        original = await self.repo.get_run("legacy", "alice")
        self.assertEqual(original["request"], {"target_url": "http://localhost/"})
        self.assertIsNone(original["execution_token"])
        self.assertIsNone(await self.repo.get_run("legacy", "bob"))
        claims = await asyncio.gather(
            self.repo.claim_run(lease_seconds=10), self.repo.claim_run(lease_seconds=10)
        )
        self.assertEqual([claim["run_id"] for claim in claims if claim], ["legacy"])
        self.assertEqual(
            [event["type"] for event in await self.repo.read_events("legacy", after=0)],
            ["run.started"],
        )

        await self.create_run("later")
        await self.create_run("private", "bob")
        rows, count = await self.repo.list_runs("alice", page=1, page_size=1)
        self.assertEqual([row["run_id"] for row in rows], ["later"])
        self.assertEqual(count, 2)
        self.assertEqual(
            await self.repo.list_runs("alice", page=10**30, page_size=100), ([], 2)
        )

    async def test_progress_retry_and_report_commit_order(self):
        token = await self.claim("legacy")
        plan = progress("legacy", "plan", "plan.created", {"total_cases": 0})
        self.assertEqual(await self.repo.append_event("legacy", token, plan), 2)
        self.assertEqual(await self.repo.append_event("legacy", token, plan), 2)
        with self.assertRaises(EventConflict):
            await self.repo.append_event(
                "legacy", token, {**plan, "payload": {"total_cases": 1}}
            )
        with self.assertRaises(CheckViolation):
            await self.repo.append_event(
                "legacy",
                token,
                progress(
                    "legacy",
                    "invalid",
                    "case.verified",
                    {"verdict": "passed"},
                    case_id="too-many",
                ),
            )
        terminal = {
            "status": "succeeded",
            "verdict": "inconclusive",
            "report": empty_report("legacy"),
            "terminal_event_id": "terminal",
            "report_event_id": "report",
        }
        self.assertEqual(
            (await self.repo.finish_run("legacy", token, **terminal))["status"],
            "succeeded",
        )
        self.assertEqual(
            (await self.repo.finish_run("legacy", token, **terminal))["status"],
            "succeeded",
        )
        events = await self.repo.read_events("legacy", after=2)
        self.assertEqual(
            [(evt["sequence"], evt["type"]) for evt in events],
            [(3, "report.generated"), (4, "run.completed")],
        )
        published = await self.repo.get_run("legacy", "alice")
        self.assertEqual(published["last_event_sequence"], 4)
        self.assertEqual(published["completed_cases"], 0)
        self.assertEqual(published["report"]["verdict"], "inconclusive")
        self.assertEqual(await self.repo.append_event("legacy", token, plan), 2)
        with self.assertRaises(RunNotCancellable):
            await self.repo.cancel_run("legacy", "alice")

    async def test_cancel_before_and_after_claim(self):
        queued = await self.repo.cancel_run("legacy", "alice")
        self.assertEqual(queued["status"], "cancelled")
        self.assertIsNone(queued["started_at"])
        self.assertEqual(
            (await self.repo.read_events("legacy", after=0))[0]["type"], "run.cancelled"
        )
        self.assertIsNone(await self.repo.claim_run(lease_seconds=10))

        await self.create_run("running")
        token = await self.claim("running")
        for _ in range(2):
            requested = await self.repo.cancel_run("running", "alice")
            self.assertEqual(requested["status"], "running")
            self.assertTrue(requested["cancellation_requested"])
        active = await self.repo.heartbeat("running", token, lease_seconds=10)
        self.assertTrue(active["cancellation_requested"])
        result = await self.repo.finish_run(
            "running",
            token,
            status="succeeded",
            verdict="inconclusive",
            report=empty_report("running"),
        )
        self.assertEqual(result["status"], "cancelled")
        self.assertIsNone((await self.repo.get_run("running", "alice"))["report"])

    async def test_expired_and_legacy_running_leases_are_fenced(self):
        token = await self.claim("legacy")
        await self.create_run("old-running")
        async with self.pool.connection() as conn:
            await conn.execute(
                "UPDATE test_runs SET lease_expires_at = clock_timestamp() - interval '1 second' WHERE run_id = 'legacy'"
            )
            await conn.execute(
                "UPDATE test_runs SET status = 'running', started_at = clock_timestamp() WHERE run_id = 'old-running'"
            )
        self.assertIsNone(await self.repo.heartbeat("legacy", token, lease_seconds=10))
        self.assertEqual(await self.repo.recover_expired(), 2)
        self.assertEqual(await self.repo.recover_expired(), 0)
        with self.assertRaises(LeaseLost):
            await self.repo.finish_run(
                "legacy",
                token,
                status="errored",
                error={"code": "WORKER_ERROR", "message": "Stale"},
            )
        for run_id in ("legacy", "old-running"):
            current = await self.repo.get_run(run_id, "alice")
            self.assertEqual(current["error"]["code"], "WORKER_ERROR")
            events = await self.repo.read_events(run_id, after=0)
            self.assertEqual(events[-1]["type"], "run.failed")
            self.assertIsNone(current["execution_token"])
        self.assertIsNone(await self.repo.claim_run(lease_seconds=10))

    async def test_case_progress_and_partial_report_survive_cleanup_failure(self):
        token = await self.claim("legacy")
        await self.repo.append_event(
            "legacy",
            token,
            progress("legacy", "plan", "plan.created", {"total_cases": 1}),
        )
        for event_id in ("first", "second"):
            await self.repo.append_event(
                "legacy",
                token,
                progress(
                    "legacy",
                    event_id,
                    "case.verified",
                    {"verdict": "blocked"},
                    case_id="case_01",
                ),
            )
        await self.repo.cancel_run("legacy", "alice")
        error = {"code": "CLEANUP_FAILED", "message": "The session did not close"}
        await self.repo.finish_run(
            "legacy",
            token,
            status="errored",
            error=error,
            report={
                **empty_report("legacy"),
                "status": "errored",
                "verdict": None,
                "error": error,
                "cases": [
                    {
                        "case_id": "case_01",
                        "name": "Check login",
                        "preconditions": [],
                        "expected_behavior": "Login form appears",
                        "verdict": "blocked",
                    }
                ],
            },
        )
        published = await self.repo.get_run("legacy", "alice")
        self.assertEqual(published["completed_cases"], 1)
        self.assertEqual(published["status"], "errored")
        self.assertIsNone(published["verdict"])
        self.assertEqual(published["report"]["cases"][0]["verdict"], "blocked")
        events = await self.repo.read_events("legacy", after=4)
        self.assertEqual(
            [event["type"] for event in events], ["report.generated", "run.failed"]
        )

    async def test_evidence_registration_scope_and_expiration(self):
        token = await self.claim("legacy")
        stamp = datetime.now(UTC)
        artifact = {
            "artifact_id": "art_one",
            "run_id": "legacy",
            "case_id": "case_01",
            "step_id": "step_01",
            "tool_call_id": "call_01",
            "kind": "observation",
            "mime_type": "application/json",
            "captured_at": stamp,
            "size_bytes": 20,
            "storage_key": "key_one",
            "expires_at": stamp - timedelta(seconds=1),
        }
        saved = await self.repo.register_artifact("legacy", token, artifact)
        self.assertEqual(saved["storage_key"], "key_one")
        self.assertIsNone(await self.repo.get_artifact("art_one", "bob"))
        self.assertEqual(
            (await self.repo.get_artifact_by_storage_key("key_one"))["run_id"], "legacy"
        )
        self.assertEqual(
            [row["artifact_id"] for row in await self.repo.expired_artifacts()],
            ["art_one"],
        )
        self.assertTrue(await self.repo.mark_artifact_purged("art_one", "key_one"))
        self.assertTrue(await self.repo.mark_artifact_purged("art_one", "key_one"))
        self.assertEqual(await self.repo.expired_artifacts(), [])
        self.assertIsNone(
            (await self.repo.get_artifact("art_one", "alice"))["storage_key"]
        )

        await self.create_run("second")
        second = await self.claim("second")
        with self.assertRaises(InvalidEvidence):
            await self.repo.append_event(
                "second",
                second,
                progress(
                    "second",
                    "wrong-art",
                    "tool.completed",
                    {
                        "tool_call_id": "call_01",
                        "tool": "browser.inspect",
                        "success": True,
                        "duration_ms": 1,
                        "error_code": None,
                        "evidence_ids": ["art_one"],
                    },
                    case_id="case_01",
                    step_id="step_01",
                ),
            )
        with self.assertRaises(InvalidEvidence):
            await self.repo.finish_run(
                "second",
                second,
                status="succeeded",
                verdict="inconclusive",
                report={
                    **empty_report("second"),
                    "artifacts": [
                        {
                            key: value
                            for key, value in artifact.items()
                            if key not in {"storage_key", "expires_at"}
                        }
                    ],
                },
            )
        self.assertEqual(
            (await self.repo.get_run("second", "alice"))["status"], "running"
        )
        self.assertEqual(len(await self.repo.read_events("second", after=0)), 1)
