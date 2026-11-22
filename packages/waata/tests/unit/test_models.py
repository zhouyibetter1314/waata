"""C2/C4/C5 shape validation, JSON preservation, and trusted budget bounds."""

import copy
import json
import unittest

from _fixtures import CONTRACTS, progress_data, request, result, result_data
from pydantic import ValidationError
from waata.artifacts import ArtifactInput, ArtifactRef
from waata.core.events import TestEvent
from waata.orchestrator import (
    EngineConfig,
    TestCaseResult,
    TestOptions,
    TestRequest,
    TestResult,
)


class RequestTests(unittest.TestCase):
    def test_canonical_request_round_trip(self):
        data = json.loads(
            (CONTRACTS / "waata/examples/4gaboards-test-request.json").read_text(
                encoding="utf-8"
            )
        )
        parsed = TestRequest.model_validate(data)
        self.assertEqual(parsed.model_dump(mode="json"), data)
        self.assertEqual(
            TestRequest.model_validate_json(parsed.model_dump_json()), parsed
        )

    def test_missing_null_and_false_are_distinct(self):
        data = request().model_dump(exclude={"credential_ref", "options"})
        omitted = TestRequest(**data)
        explicit = TestRequest(**data, credential_ref=None, options={})
        self.assertIsNone(omitted.credential_ref)
        self.assertNotIn("credential_ref", omitted.model_fields_set)
        self.assertIn("credential_ref", explicit.model_fields_set)
        self.assertEqual(omitted.options, TestOptions(max_steps_per_case=None))
        self.assertEqual(omitted.model_dump()["options"], {"max_steps_per_case": None})
        for field, value in (
            ("options", None),
            ("options", False),
            ("credential_ref", False),
            ("credential_ref", "  "),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValidationError):
                    TestRequest(**{**data, field: value})

    def test_goal_and_expected_behavior_are_required_non_blank_strings(self):
        for field in ("goal", "expected_behavior"):
            for value in ("", " \n\t", None, False, 1):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError):
                        TestRequest(**{**request().model_dump(), field: value})
            data = request().model_dump()
            del data[field]
            with self.assertRaises(ValidationError):
                TestRequest(**data)

    def test_invalid_urls_are_rejected(self):
        for url in (
            "",
            "/login",
            "localhost:3000",
            "file:///tmp/site",
            "javascript:alert(1)",
            "https://",
            "http://user:password@example.test",
            "http://@example.test",
            "https://example.test:65536",
            "https://example.test:0",
            "https://example.test:not-a-port",
            "https://example.test/white space",
            "https://example.test/\n",
            "https://[broken",
            "https://%/",
            "https://example.test\\login",
            False,
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValidationError):
                    TestRequest(**{**request().model_dump(), "target_url": url})

    def test_valid_urls_are_preserved(self):
        for url in (
            "http://localhost:3000/",
            "https://demo-app.test/login?x=false#test",
            "http://[::1]:8000/",
        ):
            with self.subTest(url=url):
                parsed = TestRequest(**{**request().model_dump(), "target_url": url})
                self.assertEqual(parsed.target_url, url)

    def test_step_budget_requires_a_positive_integer_or_null(self):
        for value in (0, -1, False, True, 1.5, "12"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    TestOptions(max_steps_per_case=value)
        self.assertEqual(TestOptions(max_steps_per_case=1).max_steps_per_case, 1)
        self.assertIsNone(TestOptions(max_steps_per_case=None).max_steps_per_case)

    def test_unknown_fields_and_worker_only_options_are_rejected(self):
        for extra in ({"password": "fixture"}, {"options": {"headless": False}}):
            with self.subTest(extra=extra):
                with self.assertRaises(ValidationError):
                    TestRequest(**{**request().model_dump(), **extra})

    def test_configuration_budgets_and_timeouts_are_finite_and_positive(self):
        defaults = EngineConfig().model_dump()
        for field in defaults:
            for value in (0, -1, False, "12", float("inf"), float("nan")):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError):
                        EngineConfig(**{**defaults, field: value})
        with self.assertRaises(ValidationError):
            EngineConfig(max_steps_per_case=11, max_steps_per_case_limit=10)
        self.assertEqual(
            EngineConfig(
                max_steps_per_case=10, max_steps_per_case_limit=10
            ).max_steps_per_case,
            10,
        )


class ResultTests(unittest.TestCase):
    def test_canonical_result_round_trip_keeps_all_fixed_fields(self):
        parsed = result()
        self.assertEqual(parsed.model_dump(mode="json"), result_data())
        self.assertEqual(
            TestResult.model_validate_json(parsed.model_dump_json()), parsed
        )

    def test_null_and_false_scalar_values_remain_distinct(self):
        for value in (None, False, True, 0, 1, 1.5, "false"):
            with self.subTest(value=value):
                data = result_data()
                data["verdict"] = data["cases"][0]["verdict"] = "failed"
                assertion = data["cases"][0]["assertions"][0]
                assertion.update(expected=value, actual=value, passed=False)
                parsed = TestResult.model_validate_json(json.dumps(data))
                actual = parsed.cases[0].assertions[0].actual
                self.assertIs(type(actual), type(value))
                self.assertEqual(actual, value)
                self.assertIs(parsed.cases[0].assertions[0].passed, False)

    def test_assertions_only_accept_json_scalars_and_strict_boolean(self):
        for field, value in (
            ("actual", {}),
            ("expected", []),
            ("actual", float("nan")),
            ("passed", 0),
            ("passed", "false"),
            ("evidence_ids", []),
        ):
            with self.subTest(field=field, value=value):
                data = result_data()
                data["cases"][0]["assertions"][0][field] = value
                with self.assertRaises(ValidationError):
                    TestResult.model_validate(data)

    def test_nullable_report_fields_are_required_and_serialize_as_null(self):
        data = result_data()
        for field in ("error", "langfuse_trace_id"):
            broken = copy.deepcopy(data)
            del broken[field]
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    TestResult.model_validate(broken)
        self.assertIn('"error":null', result().model_dump_json())
        data["verdict"] = data["cases"][0]["verdict"] = "inconclusive"
        data["cases"][0]["assertions"][0].update(actual=None, passed=None)
        self.assertIsNone(TestResult.model_validate(data).cases[0].assertions[0].passed)

    def test_passed_case_rejects_failed_required_assertion(self):
        data = result_data()
        data["cases"][0]["assertions"][0].update(actual=False, passed=False)
        with self.assertRaisesRegex(ValidationError, "passed cases require"):
            TestCaseResult.model_validate(data["cases"][0])
        with self.assertRaisesRegex(ValidationError, "passed cases require"):
            TestResult.model_validate(data)

    def test_passed_case_rejects_undecided_required_assertion(self):
        data = result_data()
        data["cases"][0]["assertions"][0].update(actual=None, passed=None)
        with self.assertRaisesRegex(ValidationError, "passed cases require"):
            TestCaseResult.model_validate(data["cases"][0])
        with self.assertRaisesRegex(ValidationError, "passed cases require"):
            TestResult.model_validate_json(json.dumps(data))

    def test_passed_case_accepts_all_passed_assertions_without_recomputing_matches(
        self,
    ):
        data = result_data()
        # A valid matching operation need not be scalar equality.
        data["cases"][0]["assertions"][0].update(
            expected="welcome", actual="Welcome, tester", passed=True
        )
        parsed = TestResult.model_validate(data)
        self.assertEqual(parsed.verdict, "passed")
        self.assertEqual(parsed.cases[0].verdict, "passed")
        self.assertTrue(all(a.passed is True for a in parsed.cases[0].assertions))

    def test_failed_assertion_requires_failed_verdict_in_a_decided_case(self):
        data = result_data()
        data["cases"][0]["assertions"][0].update(actual=False, passed=False)
        for verdict in ("blocked", "inconclusive"):
            with self.subTest(verdict=verdict):
                data["cases"][0]["verdict"] = verdict
                with self.assertRaisesRegex(ValidationError, "must be failed"):
                    TestCaseResult.model_validate(data["cases"][0])
        data["verdict"] = data["cases"][0]["verdict"] = "failed"
        # A conclusive failure can coexist with an unfinished assertion.
        data["cases"][0]["assertions"][1].update(actual=None, passed=None)
        self.assertEqual(TestResult.model_validate(data).model_dump(), data)

    def test_partial_report_allows_undecided_assertions_and_case_verdict(self):
        for completed_outcome in (True, False):
            with self.subTest(completed_outcome=completed_outcome):
                data = result_data()
                data.update(
                    status="errored",
                    verdict=None,
                    error={"code": "BROWSER_ERROR", "message": "Browser stopped"},
                )
                case = data["cases"][0]
                case["verdict"] = None
                case["assertions"][0].update(actual=None, passed=None)
                case["assertions"][1].update(
                    actual=completed_outcome, passed=completed_outcome
                )
                call = case["steps"][0]["tool_calls"][0]
                call.update(success=None, duration_ms=None, error_code=None)
                parsed = TestResult.model_validate(data)
                self.assertIsNone(parsed.cases[0].assertions[0].passed)
                self.assertIs(parsed.cases[0].assertions[1].passed, completed_outcome)
                self.assertEqual(parsed.model_dump(), data)

    def test_technical_error_does_not_allow_a_contradictory_passed_case(self):
        for outcome in (False, None):
            with self.subTest(outcome=outcome):
                data = result_data()
                data.update(
                    status="errored",
                    verdict=None,
                    error={"code": "BROWSER_ERROR", "message": "Browser stopped"},
                )
                data["cases"][0]["assertions"][0].update(actual=outcome, passed=outcome)
                with self.assertRaisesRegex(ValidationError, "passed cases require"):
                    TestResult.model_validate(data)

    def test_verdict_precedence_and_empty_plan(self):
        precedence = ("failed", "blocked", "inconclusive", "passed")
        for index, expected in enumerate(precedence):
            data = result_data()
            case = data["cases"][0]
            data["artifacts"] = []
            data["cases"] = [
                {
                    **case,
                    "case_id": f"case_{verdict}",
                    "steps": [],
                    "assertions": [],
                    "verdict": verdict,
                }
                for verdict in reversed(precedence[index:])
            ]
            data["verdict"] = expected
            self.assertEqual(TestResult.model_validate(data).verdict, expected)
        data.update(cases=[], verdict="inconclusive")
        self.assertEqual(TestResult.model_validate(data).cases, [])
        data["verdict"] = "passed"
        with self.assertRaises(ValidationError):
            TestResult.model_validate(data)

    def test_nonempty_plan_rejects_every_incorrect_overall_verdict(self):
        precedence = ("failed", "blocked", "inconclusive", "passed")
        for index, expected in enumerate(precedence):
            data = result_data()
            template = data["cases"][0]
            data["artifacts"] = []
            data["cases"] = [
                {
                    **template,
                    "case_id": f"case_{verdict}",
                    "verdict": verdict,
                    "steps": [],
                    "assertions": [],
                }
                for verdict in reversed(precedence[index:])
            ]
            for overall in precedence:
                with self.subTest(case_verdicts=precedence[index:], overall=overall):
                    data["verdict"] = overall
                    if overall == expected:
                        self.assertEqual(
                            TestResult.model_validate(data).verdict, expected
                        )
                    else:
                        with self.assertRaisesRegex(ValidationError, "case precedence"):
                            TestResult.model_validate(data)

    def test_status_verdict_and_error_are_distinct(self):
        for status, verdict, error in (
            ("succeeded", None, None),
            ("succeeded", "passed", {"code": "INTERNAL_ERROR", "message": "error"}),
            ("errored", "failed", {"code": "BROWSER_ERROR", "message": "error"}),
            ("errored", None, None),
            ("cancelled", None, None),
            ("running", None, None),
        ):
            with self.subTest(status=status, verdict=verdict, error=error):
                data = result_data()
                data.update(status=status, verdict=verdict, error=error)
                with self.assertRaises(ValidationError):
                    TestResult.model_validate(data)

    def test_partial_report_preserves_unfinished_calls_and_unjudged_cases(self):
        data = result_data()
        data.update(
            status="errored",
            verdict=None,
            error={"code": "BROWSER_ERROR", "message": "Browser stopped"},
        )
        data["cases"][0]["verdict"] = None
        call = data["cases"][0]["steps"][0]["tool_calls"][0]
        call.update(success=None, duration_ms=None, error_code=None)
        parsed = TestResult.model_validate(data)
        self.assertIsNone(parsed.cases[0].verdict)
        self.assertIsNone(parsed.cases[0].steps[0].tool_calls[0].success)
        self.assertTrue(parsed.cases[0].assertions[0].passed)
        self.assertEqual(parsed.model_dump(mode="json"), data)

    def test_tool_completion_fields_are_consistent(self):
        for update in (
            {"success": None},
            {"success": 1},
            {"duration_ms": -1},
            {"duration_ms": False},
            {"success": False},
            {"error_code": "TOOL_TIMEOUT"},
        ):
            with self.subTest(update=update):
                data = result_data()
                data["cases"][0]["steps"][0]["tool_calls"][0].update(update)
                with self.assertRaises(ValidationError):
                    TestResult.model_validate(data)
        data = result_data()
        call = data["cases"][0]["steps"][0]["tool_calls"][0]
        call.update(success=False, error_code="TOOL_TIMEOUT")
        self.assertIs(
            TestResult.model_validate(data).cases[0].steps[0].tool_calls[0].success,
            False,
        )

    def test_ids_are_unique_by_type_across_the_run(self):
        for kind in ("case", "step", "assertion", "call", "artifact"):
            with self.subTest(kind=kind):
                data = result_data()
                case = data["cases"][0]
                if kind == "case":
                    data["cases"].append(copy.deepcopy(case))
                elif kind == "step":
                    case["steps"].append(copy.deepcopy(case["steps"][0]))
                elif kind == "assertion":
                    case["assertions"].append(copy.deepcopy(case["assertions"][0]))
                elif kind == "call":
                    case["steps"][1]["tool_calls"].append(
                        copy.deepcopy(case["steps"][0]["tool_calls"][0])
                    )
                else:
                    data["artifacts"].append(copy.deepcopy(data["artifacts"][0]))
                with self.assertRaises(ValidationError):
                    TestResult.model_validate(data)

    def test_evidence_must_resolve_and_match_context(self):
        for field, value in (
            ("run_id", "another-run"),
            ("case_id", "missing-case"),
            ("step_id", "missing-step"),
            ("tool_call_id", "missing-call"),
        ):
            with self.subTest(field=field):
                data = result_data()
                data["artifacts"][0][field] = value
                with self.assertRaises(ValidationError):
                    TestResult.model_validate(data)
        for location in ("assertion", "tool"):
            data = result_data()
            case = data["cases"][0]
            item = (
                case["assertions"][0]
                if location == "assertion"
                else case["steps"][0]["tool_calls"][0]
            )
            item["evidence_ids"] = ["not-registered"]
            with self.assertRaises(ValidationError):
                TestResult.model_validate(data)


class EventAndArtifactTests(unittest.TestCase):
    def test_all_c4_sse_examples_validate_after_worker_sequence_is_removed(self):
        for envelope in progress_data():
            data = {k: v for k, v in envelope.items() if k != "sequence"}
            with self.subTest(type=data["type"]):
                event = TestEvent.model_validate(data)
                self.assertEqual(event.model_dump(mode="json"), data)
                self.assertEqual(
                    TestEvent.model_validate_json(event.model_dump_json()), event
                )
        with self.assertRaises(ValidationError):
            TestEvent.model_validate(progress_data()[0])

    def test_c4_rejects_invalid_payload_scope_version_and_timestamp(self):
        base = next(e for e in progress_data() if e["type"] == "plan.created")
        base = {k: v for k, v in base.items() if k != "sequence"}
        for update in (
            {"payload": {"total_cases": -1}},
            {"payload": {"total_cases": True}},
            {"payload": {"total_cases": 1, "credential_ref": "fixture"}},
            {"case_id": "case-1"},
            {"step_id": "step-1"},
            {"schema_version": True},
            {"schema_version": 2},
            {"type": "unknown"},
            {"timestamp": "2026-11-21T02:00:00"},
            {"timestamp": "2026-11-21T02:00:00+08:00"},
        ):
            with self.subTest(update=update):
                with self.assertRaises(ValidationError):
                    TestEvent.model_validate({**base, **update})

    def test_artifact_metadata_validates_kind_mime_and_utc(self):
        data = result_data()["artifacts"][0]
        for update in (
            {"mime_type": "image/png"},
            {"kind": "unknown"},
            {"size_bytes": -1},
            {"size_bytes": False},
            {"case_id": None},
            {"captured_at": "2026-11-21"},
            {"url": "/private-path"},
        ):
            with self.subTest(update=update):
                with self.assertRaises(ValidationError):
                    ArtifactRef.model_validate({**data, **update})
        input_data = {
            k: v for k, v in data.items() if k not in {"artifact_id", "size_bytes"}
        }
        artifact = ArtifactInput(**input_data, content=b"{}")
        self.assertEqual(artifact.content, b"{}")
