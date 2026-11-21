"""Check the shared v0.1 fixtures before integrating Vue, FastAPI, and waata."""

import json
import unittest
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
MEDIA_TYPES = {
    "observation": "application/json",
    "screenshot": "image/png",
    "playwright_trace": "application/zip",
    "test_report": "application/json",
}


def read_json(relative_path):
    return json.loads((CONTRACTS / relative_path).read_text(encoding="utf-8"))


class RunFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http_request = read_json("http/examples/4gaboards-create-run.json")
        cls.accepted = read_json("http/examples/4gaboards-run-created.json")
        cls.detail = read_json("http/examples/4gaboards-run-detail.json")
        cls.report = read_json("http/examples/4gaboards-report.json")
        cls.test_request = read_json("waata/examples/4gaboards-test-request.json")
        cls.test_result = read_json("waata/examples/4gaboards-test-result.json")
        cls.tool_calls = read_json("tools/examples/4gaboards-tool-calls.json")
        cls.artifacts = read_json("artifacts/examples/4gaboards-artifact-views.json")
        cls.stream = (CONTRACTS / "events/examples/4gaboards-events.sse").read_text(
            encoding="utf-8"
        )
        cls.frames = cls.stream.strip().split("\n\n")
        cls.events = [
            json.loads(
                next(
                    line[6:] for line in frame.splitlines() if line.startswith("data: ")
                )
            )
            for frame in cls.frames
        ]
        cls.artifact_by_id = {
            artifact["artifact_id"]: artifact for artifact in cls.artifacts
        }
        cls.report_calls = {
            call["tool_call_id"]: (case["case_id"], step["step_id"], call)
            for case in cls.test_result["cases"]
            for step in case["steps"]
            for call in step["tool_calls"]
        }

    def test_c1_creation_and_detail_share_run_id(self):
        target = urlsplit(self.http_request["target_url"])
        self.assertIn(target.scheme, {"http", "https"})
        self.assertTrue(target.hostname)
        self.assertIsNone(target.username)
        self.assertIsNone(target.password)
        self.assertEqual(self.accepted["status"], "queued")
        self.assertEqual(self.accepted["run_id"], self.detail["run_id"])
        self.assertEqual(self.accepted["created_at"], self.detail["created_at"])
        for field in ("target_url", "goal", "expected_behavior"):
            with self.subTest(field=field):
                self.assertTrue(self.http_request[field].strip())
                self.assertEqual(self.http_request[field], self.detail[field])

    def test_c1_detail_summarizes_report(self):
        for field in ("run_id", "status", "verdict", "error"):
            with self.subTest(field=field):
                self.assertEqual(self.detail[field], self.report[field])
        case_verdicts = Counter(case["verdict"] for case in self.report["cases"])
        self.assertEqual(
            self.detail["summary"],
            {
                verdict: case_verdicts[verdict]
                for verdict in ("passed", "failed", "blocked", "inconclusive")
            },
        )
        self.assertEqual(
            self.detail["progress"]["total_cases"], len(self.report["cases"])
        )
        self.assertEqual(
            self.detail["progress"]["completed_cases"],
            sum(self.detail["summary"].values()),
        )

    def test_c1_login_regression_reports_a_completed_run_with_failed_assertions(self):
        report = read_json("http/examples/test-run-report.json")
        self.assertEqual(report["status"], "succeeded")
        self.assertEqual(report["verdict"], "failed")
        self.assertIsNone(report["error"])
        artifact_ids = {artifact["artifact_id"] for artifact in report["artifacts"]}
        failed_assertions = [
            assertion
            for case in report["cases"]
            for assertion in case["assertions"]
            if assertion["passed"] is False
        ]
        self.assertTrue(failed_assertions)
        for assertion in failed_assertions:
            self.assertNotEqual(assertion["actual"], assertion["expected"])
            self.assertTrue(assertion["evidence_ids"])
            self.assertTrue(set(assertion["evidence_ids"]) <= artifact_ids)

    def test_c2_worker_input_keeps_test_parameters_and_selects_browser_separately(self):
        options = self.http_request["options"]
        self.assertIsInstance(options["headless"], bool)
        expected_request = {
            **self.http_request,
            "options": {
                key: value for key, value in options.items() if key != "headless"
            },
        }
        self.assertEqual(self.test_request, expected_request)
        self.assertEqual(
            self.test_result["execution"]["max_steps_per_case"],
            self.test_request["options"]["max_steps_per_case"],
        )

    def test_c2_portable_result_and_http_report_differ_only_in_artifact_projection(
        self,
    ):
        self.assertEqual(self.report, {**self.test_result, "artifacts": self.artifacts})
        self.assertEqual(
            self.test_result["artifacts"],
            [
                {
                    key: value
                    for key, value in artifact.items()
                    if key not in ("url", "expires_at")
                }
                for artifact in self.artifacts
            ],
        )
        self.assertEqual(self.test_result["run_id"], self.accepted["run_id"])

    def test_c2_fixture_verdict_follows_case_precedence(self):
        precedence = ("failed", "blocked", "inconclusive", "passed")
        for report in (
            self.test_result,
            read_json("http/examples/test-run-report.json"),
        ):
            with self.subTest(run_id=report["run_id"]):
                case_verdicts = {case["verdict"] for case in report["cases"]}
                expected = next(
                    (verdict for verdict in precedence if verdict in case_verdicts),
                    "inconclusive",
                )
                self.assertEqual(report["verdict"], expected)

    def test_c3_call_envelopes_match_recorded_steps(self):
        self.assertEqual(len(self.tool_calls), len(self.report_calls))
        seen = set()
        for example in self.tool_calls:
            context, call, result = (
                example[key] for key in ("context", "call", "result")
            )
            call_id = context["tool_call_id"]
            with self.subTest(tool_call_id=call_id):
                self.assertNotIn(call_id, seen)
                seen.add(call_id)
                case_id, step_id, summary = self.report_calls[call_id]
                self.assertEqual(context["run_id"], self.test_result["run_id"])
                self.assertEqual(
                    (context["case_id"], context["step_id"]), (case_id, step_id)
                )
                self.assertEqual(call["tool"], summary["tool"])
                self.assertEqual(result["success"], summary["success"])
                self.assertIsNone(result["error"])
                self.assertTrue(context.keys().isdisjoint(call["arguments"]))
                if call["tool"] == "browser.fill":
                    self.assertEqual(
                        len({"value", "secret_ref"} & call["arguments"].keys()), 1
                    )
                self.assertEqual(
                    result["data"].get("evidence_ids", []), summary["evidence_ids"]
                )
        self.assertEqual(seen, self.report_calls.keys())

    def test_c4_sse_frames_are_sequenced_and_report_precedes_terminal(self):
        self.assertTrue(self.stream.endswith("\n\n"))
        self.assertEqual(self.events[0]["type"], "run.started")
        seen = set()
        for sequence, (frame, event) in enumerate(
            zip(self.frames, self.events, strict=True), start=1
        ):
            with self.subTest(sequence=sequence):
                self.assertIn(f"id: {sequence}", frame.splitlines())
                self.assertIn(f"event: {event['type']}", frame.splitlines())
                self.assertEqual(event["sequence"], sequence)
                self.assertEqual(event["schema_version"], 1)
                self.assertEqual(event["run_id"], self.test_result["run_id"])
                self.assertNotIn(event["event_id"], seen)
                seen.add(event["event_id"])
        terminal_types = {"run.completed", "run.failed", "run.cancelled"}
        self.assertEqual(
            [event for event in self.events if event["type"] in terminal_types],
            self.events[-1:],
        )
        self.assertEqual(self.events[-2]["type"], "report.generated")
        terminal = self.events[-1]
        self.assertEqual(terminal["type"], "run.completed")
        self.assertEqual(
            terminal["payload"],
            {key: self.report[key] for key in ("status", "verdict", "error")},
        )

    def test_c4_tool_events_pair_and_match_report_summaries(self):
        pending = {}
        completed = set()
        for event in self.events:
            if event["type"] not in {"tool.called", "tool.completed"}:
                continue
            payload = event["payload"]
            call_id = payload["tool_call_id"]
            with self.subTest(tool_call_id=call_id, event=event["type"]):
                case_id, step_id, summary = self.report_calls[call_id]
                self.assertEqual(
                    (event["case_id"], event["step_id"]), (case_id, step_id)
                )
                self.assertEqual(payload["tool"], summary["tool"])
                if event["type"] == "tool.called":
                    self.assertNotIn(call_id, pending.keys() | completed)
                    pending[call_id] = event["sequence"]
                else:
                    self.assertLess(pending.pop(call_id), event["sequence"])
                    self.assertEqual(payload, summary)
                    completed.add(call_id)
        self.assertFalse(pending)
        self.assertEqual(completed, self.report_calls.keys())

    def test_c5_evidence_is_resolvable_and_scoped_to_the_run(self):
        self.assertEqual(len(self.artifact_by_id), len(self.artifacts))
        for artifact in self.artifacts:
            artifact_id = artifact["artifact_id"]
            with self.subTest(artifact_id=artifact_id):
                self.assertEqual(artifact["run_id"], self.report["run_id"])
                self.assertEqual(artifact["mime_type"], MEDIA_TYPES[artifact["kind"]])
                self.assertEqual(artifact["url"], f"/api/v1/artifacts/{artifact_id}")
                self.assertGreaterEqual(artifact["size_bytes"], 0)
        for case in self.report["cases"]:
            for assertion in case["assertions"]:
                if assertion["passed"] is not None:
                    self.assertTrue(assertion["evidence_ids"])
                for artifact_id in assertion["evidence_ids"]:
                    self.assertEqual(
                        self.artifact_by_id[artifact_id]["case_id"], case["case_id"]
                    )
        for call_id, (case_id, step_id, call) in self.report_calls.items():
            for artifact_id in call["evidence_ids"]:
                artifact = self.artifact_by_id[artifact_id]
                self.assertEqual(
                    (
                        artifact["case_id"],
                        artifact["step_id"],
                        artifact["tool_call_id"],
                    ),
                    (case_id, step_id, call_id),
                )

    def test_c5_observations_match_registered_bytes_and_inspect_result(self):
        observations = {
            artifact["tool_call_id"]: artifact
            for artifact in self.artifacts
            if artifact["kind"] == "observation"
        }
        inspect_by_id = {
            example["context"]["tool_call_id"]: example["result"]["data"]
            for example in self.tool_calls
            if example["call"]["tool"] == "browser.inspect"
        }
        evidenced_calls = set()
        for path in (CONTRACTS / "artifacts/examples").glob(
            "4gaboards-*-observation.json"
        ):
            with self.subTest(file=path.name):
                contents = path.read_text(encoding="utf-8")
                data = json.loads(contents)
                call_id = data["tool_call_id"]
                artifact = observations[call_id]
                inspect_result = inspect_by_id[call_id]
                self.assertNotIn("evidence_ids", data)
                self.assertEqual(data["observed_at"], artifact["captured_at"])
                self.assertEqual(data["actual"], inspect_result["actual"])
                self.assertEqual(data["matched"], inspect_result["matched"])
                # Use the canonical LF fixture bytes even in a CRLF checkout.
                self.assertEqual(len(contents.encode("utf-8")), artifact["size_bytes"])
                self.assertIn(artifact["artifact_id"], inspect_result["evidence_ids"])
                evidenced_calls.add(call_id)
        self.assertEqual(evidenced_calls, observations.keys())

    def test_public_fixtures_do_not_echo_the_credential_reference(self):
        reference = self.http_request["credential_ref"]
        self.assertTrue(reference)
        for response in (
            self.accepted,
            self.detail,
            self.report,
            self.test_result,
            self.events,
            self.artifacts,
        ):
            public = json.dumps(response)
            self.assertNotIn(reference, public)
            self.assertNotIn('"credential_ref"', public)
            self.assertNotIn('"secret_ref"', public)
