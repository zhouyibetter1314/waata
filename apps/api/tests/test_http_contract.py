"""Exercise the public HTTP, report, and SSE contracts with controlled doubles."""

import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
from psycopg import OperationalError
from waata_api.infrastructure.config import Settings, TargetPolicies, TargetPolicy
from waata_api.main import create_app
from waata_api.repositories import RunNotCancellable

_ROOT = Path(__file__).resolve().parents[3]
_NOW = datetime(2026, 11, 21, tzinfo=UTC)
_URL = "/api/v1/test-runs"
_REQUEST = {
    "target_url": "http://localhost:3000/login?token=private-url-value#fragment",
    "goal": " Verify login ",
    "expected_behavior": "Invalid credentials show an error",
    "credential_ref": "test_fixture_ref",
}
_OWNER_HEADERS = {
    "x-waata-gateway-token": "synthetic-gateway-token",
    "x-waata-principal": "owner-a",
    "origin": "https://waata.test",
}


class Repository:
    def __init__(self):
        self.runs = {}
        self.artifacts = {}
        self.events = []
        self.poll_count = 0
        self.live_terminal = None
        self.available = True

    async def create_run(self, *, run_id, owner_id, request, credential_ref):
        if not self.available:
            raise OperationalError("SYNTHETIC_PRIVATE_DIAGNOSTIC")
        row = {
            "run_id": run_id,
            "owner_id": owner_id,
            "request": request,
            "credential_ref": credential_ref,
            "status": "queued",
            "verdict": None,
            "report": None,
            "error": None,
            "total_cases": None,
            "completed_cases": 0,
            "created_at": _NOW,
            "started_at": None,
            "finished_at": None,
            "cancellation_requested": False,
            "last_event_sequence": 0,
        }
        self.runs[run_id] = row
        return row

    async def get_run(self, run_id, owner_id):
        row = self.runs.get(run_id)
        if row is None or row["owner_id"] != owner_id:
            return None
        return row

    async def list_runs(self, owner_id, *, page, page_size):
        rows = [row for row in self.runs.values() if row["owner_id"] == owner_id]
        offset = (page - 1) * page_size
        return rows[offset : offset + page_size], len(rows)

    async def cancel_run(self, run_id, owner_id):
        row = await self.get_run(run_id, owner_id)
        if row is None:
            return None
        if row["status"] not in {"queued", "running"}:
            raise RunNotCancellable
        row["cancellation_requested"] = True
        if row["status"] == "queued":
            row["status"] = "cancelled"
            row["finished_at"] = _NOW
            self.append_event(row, "run.cancelled")
        return row

    def append_event(self, row, event_type):
        seq = row["last_event_sequence"] + 1
        row["last_event_sequence"] = seq
        self.events.append(
            {
                "schema_version": 1,
                "event_id": f"evt_{seq}",
                "run_id": row["run_id"],
                "sequence": seq,
                "type": event_type,
                "timestamp": _NOW,
                "case_id": None,
                "step_id": None,
                "payload": (
                    {"status": "cancelled", "verdict": None, "error": None}
                    if event_type == "run.cancelled"
                    else {}
                ),
            }
        )

    async def read_events(self, run_id, *, after, limit=100):
        self.poll_count += 1
        if self.poll_count >= 5 and self.live_terminal is not None:
            self.append_event(self.live_terminal, "run.cancelled")
            self.live_terminal["status"] = "cancelled"
            self.live_terminal = None
        return [
            event
            for event in self.events
            if event["run_id"] == run_id and event["sequence"] > after
        ][:limit]

    async def list_artifacts(self, run_id):
        return [row for row in self.artifacts.values() if row["run_id"] == run_id]

    async def get_artifact(self, artifact_id, owner_id):
        row = self.artifacts.get(artifact_id)
        if row is None or await self.get_run(row["run_id"], owner_id) is None:
            return None
        return row


class ArtifactStore:
    def __init__(self):
        self.files = {}

    async def read(self, storage_key):
        if storage_key not in self.files:
            raise OSError("SYNTHETIC_PRIVATE_PATH")
        return self.files[storage_key]


class HttpContractTests(unittest.TestCase):
    def setUp(self):
        self.repository = Repository()
        self.storage = ArtifactStore()
        self.settings = Settings(
            auth_mode="gateway",
            gateway_token=_OWNER_HEADERS["x-waata-gateway-token"],
            allowed_hosts=("waata.test",),
            web_origins=("https://waata.test",),
            sse_poll_seconds=0.005,
            sse_keepalive_seconds=0.005,
            policy=TargetPolicies(
                (
                    TargetPolicy(
                        origin="http://localhost:3000",
                        owners=["owner-a", "owner-b"],
                        credentials={
                            "test_fixture_ref": {
                                "test_password_field_ref": {
                                    "env": "TEST_FIXTURE_SECRET",
                                    "locator": {
                                        "strategy": "label",
                                        "value": "Password",
                                    },
                                },
                            },
                        },
                    ),
                ),
                {"TEST_FIXTURE_SECRET": "SYNTHETIC_PRIVATE_PASSWORD"},
            ),
        )
        self.app = create_app(
            settings=self.settings,
            repository=self.repository,
            artifact_store=self.storage,
        )
        self.client = self.enterContext(
            TestClient(self.app, base_url="https://waata.test")
        )

    def post_run(self, body=None):
        return self.client.post(
            _URL, json=_REQUEST if body is None else body, headers=_OWNER_HEADERS
        )

    def create_run(self):
        response = self.post_run()
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()["run_id"]

    def headers_for(self, owner_id):
        return {**_OWNER_HEADERS, "x-waata-principal": owner_id}

    def check_error(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code, response.text)
        error = response.json()["error"]
        self.assertEqual(error["code"], code)
        self.assertEqual(error["request_id"], response.headers["x-request-id"])
        return error

    def test_auth_input_validation_and_public_projection(self):
        self.check_error(self.client.get(_URL), 401, "UNAUTHENTICATED")
        self.check_error(
            self.client.post(
                _URL,
                json=_REQUEST,
                headers={**_OWNER_HEADERS, "origin": "https://elsewhere.test"},
            ),
            400,
            "INVALID_REQUEST",
        )
        for body, status, code in (
            ({**_REQUEST, "password": "synthetic"}, 422, "VALIDATION_ERROR"),
            ({**_REQUEST, "options": {"headless": "true"}}, 422, "VALIDATION_ERROR"),
            (
                {**_REQUEST, "options": {"max_steps_per_case": None}},
                422,
                "VALIDATION_ERROR",
            ),
            (
                {**_REQUEST, "options": {"max_steps_per_case": 1000}},
                422,
                "VALIDATION_ERROR",
            ),
            ({**_REQUEST, "target_url": "file:///tmp"}, 422, "VALIDATION_ERROR"),
            (
                {**_REQUEST, "target_url": "http://localhost:3001/login"},
                403,
                "TARGET_NOT_ALLOWED",
            ),
            (
                {**_REQUEST, "credential_ref": "unknown"},
                403,
                "CREDENTIAL_NOT_ALLOWED",
            ),
            (
                {**_REQUEST, "goal": "SYNTHETIC_PRIVATE_PASSWORD"},
                422,
                "VALIDATION_ERROR",
            ),
        ):
            with self.subTest(code=code, request=body):
                self.check_error(self.post_run(body), status, code)
        invalid = self.client.post(
            _URL,
            content="{bad]",
            headers={**_OWNER_HEADERS, "content-type": "application/json"},
        )
        self.check_error(invalid, 400, "INVALID_REQUEST")

        run_id = self.create_run()
        record = self.repository.runs[run_id]["request"]
        self.assertNotIn("credential_ref", record)
        self.assertEqual(
            record["options"], {"headless": True, "max_steps_per_case": 16}
        )
        row = self.client.get(f"{_URL}/{run_id}", headers=_OWNER_HEADERS)
        self.assertEqual(row.status_code, 200)
        self.assertEqual(row.json()["target_url"], "http://localhost:3000/login")
        self.assertEqual(row.json()["goal"], "Verify login")
        self.assertEqual(
            row.json()["progress"], {"total_cases": None, "completed_cases": 0}
        )
        self.assertNotIn("test_fixture_ref", row.text)
        other = self.headers_for("owner-b")
        self.check_error(
            self.client.get(f"{_URL}/{run_id}", headers=other), 404, "RUN_NOT_FOUND"
        )
        self.assertEqual(self.client.get(_URL, headers=other).json()["total"], 0)

    def test_local_auth_requires_configured_host_and_loopback_peer(self):
        settings = replace(
            self.settings,
            auth_mode="local",
            local_owner_id="owner-a",
            gateway_token=None,
            allowed_hosts=("localhost:5173",),
            web_origins=("http://localhost:5173",),
        )
        app = create_app(
            settings=settings, repository=self.repository, artifact_store=self.storage
        )
        with TestClient(
            app, base_url="http://localhost:5173", client=("127.0.0.1", 4321)
        ) as local:
            self.assertEqual(local.post(_URL, json=_REQUEST).status_code, 202)
            self.check_error(
                local.get(_URL, headers={"host": "elsewhere.test"}),
                401,
                "UNAUTHENTICATED",
            )
        with TestClient(
            app, base_url="http://localhost:5173", client=("192.0.2.1", 4321)
        ) as remote:
            self.check_error(remote.get(_URL), 401, "UNAUTHENTICATED")

    def test_reports_cancel_status_and_errors(self):
        run_id = self.create_run()
        self.check_error(
            self.client.get(f"{_URL}/{run_id}/report", headers=_OWNER_HEADERS),
            409,
            "REPORT_NOT_READY",
        )
        cancelled = self.client.post(f"{_URL}/{run_id}/cancel", headers=_OWNER_HEADERS)
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(
            cancelled.json(),
            {"run_id": run_id, "status": "cancelled", "cancellation_requested": True},
        )
        self.check_error(
            self.client.get(f"{_URL}/{run_id}/report", headers=_OWNER_HEADERS),
            409,
            "REPORT_UNAVAILABLE",
        )
        self.check_error(
            self.client.post(f"{_URL}/{run_id}/cancel", headers=_OWNER_HEADERS),
            409,
            "RUN_NOT_CANCELLABLE",
        )
        run_id = self.create_run()
        self.repository.runs[run_id]["status"] = "running"
        for _ in range(2):
            response = self.client.post(
                f"{_URL}/{run_id}/cancel", headers=_OWNER_HEADERS
            )
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["status"], "running")
        self.repository.available = False
        with self.assertLogs("waata_api.main", level="WARNING") as events:
            unavailable = self.post_run()
        self.check_error(unavailable, 503, "SERVICE_UNAVAILABLE")
        self.assertNotIn("SYNTHETIC_PRIVATE_DIAGNOSTIC", unavailable.text)
        self.assertNotIn("SYNTHETIC_PRIVATE_DIAGNOSTIC", str(events.output))

    def test_sse_resumes_from_header_and_follows_live_commits(self):
        run_id = self.create_run()
        row = self.repository.runs[run_id]
        row["status"] = "running"
        self.repository.append_event(row, "run.started")
        self.repository.live_terminal = row
        events = f"{_URL}/{run_id}/events"
        for cursor in ("-1", "2", " ", "", "unknown", "9" * 100):
            self.check_error(
                self.client.get(
                    events, params={"after": cursor}, headers=_OWNER_HEADERS
                ),
                400,
                "INVALID_EVENT_CURSOR",
            )
        response = self.client.get(
            events,
            params={"after": "junk"},
            headers={**_OWNER_HEADERS, "Last-Event-ID": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(": keep-alive\n\n", response.text)
        self.assertNotIn("run.started", response.text)
        data = next(
            line[6:] for line in response.text.splitlines() if line.startswith("data: ")
        )
        self.assertEqual(
            (json.loads(data)["sequence"], json.loads(data)["type"]),
            (2, "run.cancelled"),
        )
        done = self.client.get(events, params={"after": 2}, headers=_OWNER_HEADERS)
        self.assertEqual((done.status_code, done.content), (204, b""))

    def test_project_reports_and_authorize_artifacts_before_expiration(self):
        run_id = self.create_run()
        example = _ROOT / "contracts/waata/examples/4gaboards-test-result.json"
        result = json.loads(example.read_text(encoding="utf-8"))
        result["run_id"] = run_id
        error = {"code": "MODEL_UNAVAILABLE", "message": "Model unavailable"}
        result.update(status="errored", verdict=None, error=error)
        calls = result["cases"][0]["steps"][0]["tool_calls"]
        calls[-1].update(success=None, duration_ms=None)
        self.repository.runs[run_id].update(
            status="errored", error=error, report=result, finished_at=_NOW
        )
        buffer = BytesIO()
        with ZipFile(buffer, "w") as synthetic_trace:
            synthetic_trace.writestr("trace.txt", "Synthetic C5 fixture")
        trace_content = buffer.getvalue()
        trace_id = "art_http_contract_trace"
        result["artifacts"].append(
            {
                "artifact_id": trace_id,
                "run_id": run_id,
                "case_id": None,
                "step_id": None,
                "tool_call_id": None,
                "kind": "playwright_trace",
                "mime_type": "application/zip",
                "captured_at": _NOW.isoformat(),
                "size_bytes": len(trace_content),
            }
        )
        for reference in result["artifacts"]:
            reference["run_id"] = run_id
            artifact_id = reference["artifact_id"]
            self.repository.artifacts[artifact_id] = {
                **reference,
                "captured_at": datetime.fromisoformat(reference["captured_at"]),
                "expires_at": datetime.now(UTC) + timedelta(days=1),
                "storage_key": f"private_{artifact_id}",
            }
        summary = self.client.get(f"{_URL}/{run_id}", headers=_OWNER_HEADERS)
        self.assertIsNone(summary.json()["verdict"])
        self.assertEqual(summary.json()["summary"]["passed"], 1)
        report = self.client.get(f"{_URL}/{run_id}/report", headers=_OWNER_HEADERS)
        self.assertEqual(report.status_code, 200, report.text)
        self.assertEqual(report.json()["error"]["code"], "MODEL_UNAVAILABLE")
        report_calls = report.json()["cases"][0]["steps"][0]["tool_calls"]
        self.assertIsNone(report_calls[-1]["success"])
        self.assertIsNone(report_calls[-1]["duration_ms"])
        trace = next(
            item
            for item in report.json()["artifacts"]
            if item["artifact_id"] == trace_id
        )
        self.assertNotIn("storage_key", trace)
        url = trace["url"]
        self.check_error(
            self.client.get(url, headers=_OWNER_HEADERS), 503, "ARTIFACT_UNAVAILABLE"
        )
        trace_row = self.repository.artifacts[trace["artifact_id"]]
        self.storage.files[trace_row["storage_key"]] = trace_content
        attachment = self.client.get(url, headers=_OWNER_HEADERS)
        self.assertEqual(attachment.status_code, 200)
        self.assertEqual(attachment.content, trace_content)
        self.assertEqual(attachment.headers["cache-control"], "private, no-store")
        self.assertEqual(attachment.headers["content-type"], "application/zip")
        self.assertIn("attachment", attachment.headers["content-disposition"])
        trace_row["expires_at"] = datetime.now(UTC) - timedelta(days=1)
        self.check_error(
            self.client.get(url, headers=_OWNER_HEADERS), 410, "ARTIFACT_EXPIRED"
        )
        self.check_error(
            self.client.get(url, headers=self.headers_for("owner-b")),
            404,
            "ARTIFACT_NOT_FOUND",
        )

    def test_openapi_snapshot(self):
        path = _ROOT / "contracts/http/openapi.json"
        self.assertEqual(json.loads(path.read_text()), self.app.openapi())
