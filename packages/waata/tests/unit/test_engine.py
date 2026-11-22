"""C2 Worker substitution, deterministic synchronization, and import isolation."""

import asyncio
import inspect
import os
import subprocess
import sys
import unittest

from _fixtures import (
    ROOT,
    dependencies,
    progress_data,
    request,
    result,
    result_data,
)
from pydantic import ValidationError
from waata.core.events import WORKER_EVENT_TYPES, TestEvent
from waata.orchestrator import (
    EngineConfig,
    FakeTestEngine,
    RunError,
    TestEngine,
    TestOptions,
    TestResult,
    WAATAError,
)


def events() -> list[TestEvent]:
    return [
        TestEvent.model_validate({k: v for k, v in e.items() if k != "sequence"})
        for e in progress_data()
        if e["type"] not in WORKER_EVENT_TYPES
    ]


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_fake_is_a_c2_substitute_with_identical_run_signature(self):
        self.assertEqual(
            inspect.signature(FakeTestEngine.run), inspect.signature(TestEngine.run)
        )
        engine: TestEngine = FakeTestEngine(**dependencies(), result=result())
        self.assertIsInstance(engine, TestEngine)
        self.assertEqual((await engine.run(request())).verdict, "passed")

    async def test_returns_programmed_success_without_altering_fixture(self):
        template = result()
        engine = FakeTestEngine(**dependencies(), result=template)
        actual = await engine.run(request(), run_id=template.run_id)
        self.assertEqual(actual, template)
        actual.cases.clear()
        self.assertEqual(template.model_dump(), result_data())
        self.assertEqual(await engine.run(request(), run_id=template.run_id), template)

    async def test_template_is_snapshotted_at_construction(self):
        template = result()
        engine = FakeTestEngine(**dependencies(), result=template)
        template.cases.clear()
        self.assertEqual(len((await engine.run(request())).cases), 1)

    async def test_failed_test_is_a_normally_completed_run(self):
        data = result_data()
        data["verdict"] = data["cases"][0]["verdict"] = "failed"
        data["cases"][0]["assertions"][0].update(actual=False, passed=False)
        engine = FakeTestEngine(
            **dependencies(), result=TestResult.model_validate(data)
        )
        actual = await engine.run(request(), run_id=data["run_id"])
        self.assertEqual(actual.status, "succeeded")
        self.assertEqual(actual.verdict, "failed")
        self.assertIsNone(actual.error)
        self.assertIs(actual.cases[0].assertions[0].actual, False)

    async def test_blocked_and_inconclusive_are_normal_verdicts(self):
        for verdict in ("blocked", "inconclusive"):
            with self.subTest(verdict=verdict):
                data = result_data()
                data["verdict"] = data["cases"][0]["verdict"] = verdict
                data["cases"][0].update(
                    reason="Scripted missing precondition or evidence",
                    steps=[],
                    assertions=[],
                )
                data["artifacts"] = []
                engine = FakeTestEngine(
                    **dependencies(), result=TestResult.model_validate(data)
                )
                actual = await engine.run(request())
                self.assertEqual(
                    (actual.status, actual.verdict), ("succeeded", verdict)
                )
                self.assertIsNone(actual.error)

    async def test_all_run_error_codes_can_be_programmed(self):
        for code in (
            "CONFIGURATION_ERROR",
            "MODEL_UNAVAILABLE",
            "BROWSER_ERROR",
            "RUN_TIMEOUT",
            "EVENT_DELIVERY_FAILED",
            "CLEANUP_FAILED",
            "INTERNAL_ERROR",
        ):
            with self.subTest(code=code):
                failure = WAATAError(RunError(code=code, message="Fixture failure"))
                engine = FakeTestEngine(**dependencies(), error=failure)
                with self.assertRaises(WAATAError) as caught:
                    await engine.run(request(), run_id="worker-run")
                self.assertEqual(caught.exception.error, failure.error)
                self.assertIsNot(caught.exception, failure)
                self.assertIsNone(caught.exception.partial_result)

    async def test_partial_report_keeps_completed_evidence_and_unfinished_case(self):
        data = result_data()
        error = RunError(code="BROWSER_ERROR", message="Fixture browser stopped")
        data.update(status="errored", verdict=None, error=error.model_dump())
        data["cases"][0]["verdict"] = None
        call = data["cases"][0]["steps"][0]["tool_calls"][0]
        call.update(success=None, duration_ms=None, error_code=None)
        failure = WAATAError(error, partial_result=TestResult.model_validate(data))
        engine = FakeTestEngine(**dependencies(), error=failure)
        with self.assertRaises(WAATAError) as caught:
            await engine.run(request(), run_id="partial-run")
        partial = caught.exception.partial_result
        self.assertEqual(partial.status, "errored")
        self.assertIsNone(partial.verdict)
        self.assertIsNone(partial.cases[0].verdict)
        self.assertTrue(partial.cases[0].assertions[0].passed)
        self.assertIsNone(partial.cases[0].steps[0].tool_calls[0].success)
        self.assertEqual(partial.run_id, "partial-run")
        self.assertTrue(all(a.run_id == "partial-run" for a in partial.artifacts))
        self.assertEqual(failure.partial_result.run_id, data["run_id"])

    async def test_partial_report_with_undecided_assertion_survives_fake_round_trip(
        self,
    ):
        data = result_data()
        error = RunError(code="BROWSER_ERROR", message="Fixture browser stopped")
        data.update(status="errored", verdict=None, error=error.model_dump())
        case = data["cases"][0]
        case["verdict"] = None
        case["assertions"][0].update(actual=None, passed=None)
        case["steps"][0]["tool_calls"][0].update(
            success=None, duration_ms=None, error_code=None
        )
        partial = TestResult.model_validate(data)
        engine = FakeTestEngine(
            **dependencies(), error=WAATAError(error, partial_result=partial)
        )
        with self.assertRaises(WAATAError) as caught:
            await engine.run(request(), run_id="partial-unjudged")
        actual = caught.exception.partial_result
        self.assertEqual(actual.status, "errored")
        self.assertIsNone(actual.verdict)
        self.assertIsNone(actual.cases[0].verdict)
        self.assertIsNone(actual.cases[0].assertions[0].passed)
        self.assertTrue(actual.cases[0].assertions[1].passed)
        self.assertIsNone(actual.cases[0].steps[0].tool_calls[0].success)
        self.assertEqual(len(actual.artifacts), len(partial.artifacts))
        self.assertEqual(actual.run_id, "partial-unjudged")

    async def test_run_id_is_opaque_and_preserved_everywhere(self):
        engine = FakeTestEngine(**dependencies(), result=result(), events=events())
        received = []

        async def callback(event):
            received.append(event)

        opaque_id = "worker:任务 / opaque id"
        actual = await engine.run(request(), run_id=opaque_id, on_event=callback)
        self.assertEqual(actual.run_id, opaque_id)
        self.assertTrue(all(a.run_id == opaque_id for a in actual.artifacts))
        self.assertTrue(all(e.run_id == opaque_id for e in received))

    async def test_generated_ids_are_unique_and_shared_by_report_events_and_artifacts(
        self,
    ):
        received = []

        async def callback(event):
            received.append(event)

        engine = FakeTestEngine(**dependencies(), result=result(), events=events())
        actual = await engine.run(request(), on_event=callback)
        self.assertRegex(actual.run_id, r"^run_[0-9a-f]{32}$")
        self.assertTrue(all(a.run_id == actual.run_id for a in actual.artifacts))
        self.assertTrue(all(e.run_id == actual.run_id for e in received))
        another = await engine.run(request())
        self.assertNotEqual(another.run_id, actual.run_id)

    async def test_invalid_run_ids_are_configuration_errors(self):
        engine = FakeTestEngine(**dependencies())
        for value in ("", "  ", False, 123):
            with self.subTest(value=value):
                with self.assertRaises(WAATAError) as caught:
                    await engine.run(request(), run_id=value)
                self.assertEqual(caught.exception.error.code, "CONFIGURATION_ERROR")

    async def test_requested_budget_obeys_configured_limit_before_callbacks(self):
        calls = []

        async def callback(event):
            calls.append(event)

        engine = FakeTestEngine(
            **dependencies(),
            config=EngineConfig(max_steps_per_case=5, max_steps_per_case_limit=10),
            events=events(),
        )
        for value in (11, 10**30):
            with self.subTest(value=value):
                req = request().model_copy(
                    update={"options": TestOptions(max_steps_per_case=value)}
                )
                with self.assertRaises(WAATAError) as caught:
                    await engine.run(req, on_event=callback)
                self.assertEqual(caught.exception.error.code, "CONFIGURATION_ERROR")
        self.assertEqual(calls, [])
        for value, expected in ((None, 5), (1, 1), (10, 10)):
            req = request().model_copy(
                update={"options": TestOptions(max_steps_per_case=value)}
            )
            self.assertEqual(
                (await engine.run(req)).execution.max_steps_per_case, expected
            )

    async def test_effective_config_is_recorded_and_url_queries_are_removed(self):
        engine = FakeTestEngine(
            **dependencies(),
            config=EngineConfig(
                max_browser_actions_per_run=3, max_test_cases=4, timeout_seconds=2.5
            ),
        )
        req = request().model_copy(
            update={"target_url": "https://example.test/login?token=fixture#secret"}
        )
        execution = (await engine.run(req)).execution
        self.assertEqual(execution.target_url, "https://example.test/login")
        self.assertEqual(execution.max_browser_actions_per_run, 3)
        self.assertEqual(execution.max_test_cases, 4)
        self.assertEqual(execution.timeout_seconds, 2.5)
        self.assertIn("?token=fixture", req.target_url)

    async def test_public_report_and_progress_do_not_echo_request_credential_reference(
        self,
    ):
        received = []

        async def callback(event):
            received.append(event.model_dump_json())

        req = request()
        engine = FakeTestEngine(**dependencies(), result=result(), events=events())
        actual = await engine.run(req, on_event=callback)
        for public in [actual.model_dump_json(), *received]:
            self.assertNotIn(req.credential_ref, public)
            self.assertNotIn('"credential_ref"', public)
            self.assertNotIn('"secret_ref"', public)

    async def test_revalidates_request_and_configuration_at_entry(self):
        engine = FakeTestEngine(**dependencies())
        for options in ({"max_steps_per_case": False}, {"max_steps_per_case": 0}):
            req = request().model_copy(update={"options": options})
            with self.assertRaises(WAATAError):
                await engine.run(req)
        engine.config = engine.config.model_copy(update={"timeout_seconds": False})
        with self.assertRaises(WAATAError):
            await engine.run(request())

    async def test_callbacks_are_awaited_in_order_and_do_not_mutate_templates(self):
        templates = events()
        persisted = []
        entered, release = asyncio.Event(), asyncio.Event()

        async def callback(event):
            if not persisted:
                entered.set()
                await release.wait()
            persisted.append(event.event_id)
            event.payload.clear()

        engine = FakeTestEngine(**dependencies(), events=templates)
        task = asyncio.create_task(engine.run(request(), on_event=callback))
        await asyncio.wait_for(entered.wait(), timeout=2)
        self.assertEqual(persisted, [])
        self.assertFalse(task.done())
        release.set()
        await asyncio.wait_for(task, timeout=2)
        self.assertEqual(persisted, [e.event_id for e in templates])
        self.assertTrue(templates[0].payload)
        replay = []

        async def record(event):
            replay.append(event)

        await engine.run(request(), on_event=record)
        self.assertTrue(replay[0].payload)

    async def test_callback_failure_stops_later_events_and_sanitizes_error(self):
        received = []

        async def failing(event):
            received.append(event)
            raise RuntimeError("fixture-secret /internal/path")

        engine = FakeTestEngine(**dependencies(), result=result(), events=events())
        with self.assertRaises(WAATAError) as caught:
            await engine.run(request(), on_event=failing)
        self.assertEqual(caught.exception.error.code, "EVENT_DELIVERY_FAILED")
        self.assertNotIn("fixture-secret", str(caught.exception))
        self.assertIsNone(caught.exception.partial_result)
        self.assertEqual(len(received), 1)

    async def test_wait_gate_can_release_normal_completion(self):
        started, release = asyncio.Event(), asyncio.Event()
        engine = FakeTestEngine(**dependencies(), started=started, wait_for=release)
        task = asyncio.create_task(engine.run(request()))
        await asyncio.wait_for(started.wait(), timeout=2)
        self.assertFalse(task.done())
        release.set()
        self.assertEqual((await asyncio.wait_for(task, timeout=2)).status, "succeeded")

    async def test_cancellation_propagates_without_a_report_after_saved_progress(self):
        started, release = asyncio.Event(), asyncio.Event()
        persisted = []

        async def callback(event):
            persisted.append(event)

        engine = FakeTestEngine(
            **dependencies(),
            result=result(),
            events=events(),
            started=started,
            wait_for=release,
        )
        task = asyncio.create_task(engine.run(request(), on_event=callback))
        await asyncio.wait_for(started.wait(), timeout=2)
        self.assertEqual(len(persisted), len(events()))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(task.cancelled())
        self.assertEqual(len(persisted), len(events()))
        release.set()
        self.assertEqual((await engine.run(request())).status, "succeeded")

    async def test_cancellation_during_callback_is_not_wrapped_as_technical_error(self):
        entered, release = asyncio.Event(), asyncio.Event()
        received = []

        async def callback(event):
            received.append(event)
            entered.set()
            await release.wait()

        engine = FakeTestEngine(**dependencies(), events=events())
        task = asyncio.create_task(engine.run(request(), on_event=callback))
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(len(received), 1)

    async def test_concurrent_runs_have_independent_reports_and_event_envelopes(self):
        received = []

        async def callback(event):
            received.append(event)
            await asyncio.sleep(0)

        engine = FakeTestEngine(**dependencies(), result=result(), events=events())
        first, second = await asyncio.gather(
            engine.run(request(), run_id="first", on_event=callback),
            engine.run(request(), run_id="second", on_event=callback),
        )
        for actual in (first, second):
            matching = [e.event_id for e in received if e.run_id == actual.run_id]
            self.assertEqual(matching, [e.event_id for e in events()])
            self.assertTrue(all(a.run_id == actual.run_id for a in actual.artifacts))
        first.cases.clear()
        self.assertEqual(len(second.cases), 1)

    async def test_dependencies_are_injected_by_identity_and_remain_untouched(self):
        injected = dependencies()
        engine = FakeTestEngine(**injected)
        for key, value in injected.items():
            self.assertIs(getattr(engine, key), value)
        actual = await engine.run(request())
        self.assertEqual(actual.verdict, "inconclusive")
        self.assertEqual(actual.cases, [])
        self.assertEqual(actual.artifacts, [])
        self.assertIsNone(actual.error)
        self.assertEqual(set(actual.model_dump()), set(result_data()))

    async def test_real_engine_explicitly_reports_unimplemented_execution(self):
        engine = TestEngine(**dependencies())
        with self.assertRaises(WAATAError) as caught:
            await engine.run(request())
        self.assertEqual(caught.exception.error.code, "CONFIGURATION_ERROR")
        self.assertIn("not implemented", caught.exception.error.message)


class ConfigurationAndIsolationTests(unittest.TestCase):
    def test_fake_rejects_contradictory_templates_even_if_model_was_mutated(self):
        for outcome in (False, None):
            with self.subTest(outcome=outcome):
                template = result()
                # Simulate a caller bypassing construction-time validation.
                template.cases[0].assertions[0].passed = outcome
                template.cases[0].assertions[0].actual = outcome
                with self.assertRaisesRegex(ValidationError, "passed cases require"):
                    FakeTestEngine(**dependencies(), result=template)

    def test_ambiguous_fake_outcomes_and_normal_partial_reports_are_rejected(self):
        failure = WAATAError(RunError(code="BROWSER_ERROR", message="Fixture failure"))
        with self.assertRaises(ValueError):
            FakeTestEngine(**dependencies(), result=result(), error=failure)
        with self.assertRaises(ValueError):
            WAATAError(failure.error, partial_result=result())
        data = result_data()
        data.update(status="errored", verdict=None, error=failure.error.model_dump())
        partial = TestResult.model_validate(data)
        with self.assertRaises(ValueError):
            FakeTestEngine(**dependencies(), result=partial)
        with self.assertRaises(ValueError):
            WAATAError(
                RunError(code="INTERNAL_ERROR", message="Different"),
                partial_result=partial,
            )

    def test_fake_rejects_worker_events_and_duplicate_event_ids(self):
        worker = TestEvent.model_validate(
            {k: v for k, v in progress_data()[0].items() if k != "sequence"}
        )
        with self.assertRaises(ValueError):
            FakeTestEngine(**dependencies(), events=[worker])
        event = events()[0]
        with self.assertRaises(ValueError):
            FakeTestEngine(**dependencies(), events=[event, event])

    def test_fresh_process_imports_and_runs_without_platform_browser_or_llm(self):
        script = """
import asyncio
import importlib.abc
import sys

class BlockPlatformImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'fastapi', 'waata_api', 'playwright', 'langfuse', 'httpx', 'openai'
        }:
            raise AssertionError('Unexpected dependency: ' + fullname)

sys.meta_path.insert(0, BlockPlatformImports())
import waata
from waata.orchestrator import FakeTestEngine, TestRequest

async def main():
    engine = FakeTestEngine(llm=object(), browser=object(), artifact_store=object())
    result = await engine.run(TestRequest(
        target_url='https://fixture.test/', goal='test', expected_behavior='expected'
    ))
    assert result.status == 'succeeded' and result.verdict == 'inconclusive'

asyncio.run(main())
print('isolated import and execution passed')
"""
        env = {**os.environ, "PYTHONPATH": str(ROOT / "packages/waata/src")}
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("isolated import and execution passed", completed.stdout)
