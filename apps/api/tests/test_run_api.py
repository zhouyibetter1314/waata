import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from waata_api.api.errors import ApiError
from waata_api.infrastructure.authorization import AccessPolicy, Principal, origin_of
from waata_api.infrastructure.run_queue import MemoryRunQueue
from waata_api.main import create_app

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = "https://demo-app.test"
RUNS = "/api/v1/test-runs"
CREATED = datetime(2026, 11, 21, tzinfo=UTC)
ALICE = {"Authorization": "Bearer fixture-alice"}
BOB = {"Authorization": "Bearer fixture-bob"}


class RunApiTests(unittest.TestCase):
    def setUp(self):
        allowed = frozenset({origin_of(FIXTURE)})
        self.access = AccessPolicy(
            {
                "fixture-alice": Principal(
                    "alice", allowed, frozenset({"demo_login_fixture"})
                ),
                "fixture-bob": Principal("bob", allowed),
            }
        )
        self.payload = {
            "target_url": f"{FIXTURE}/login",
            "goal": "验证登录流程",
            "expected_behavior": "有效凭据进入控制台",
        }
        self.client = TestClient(create_app(access=self.access))

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(set(response.json()), {"error"})
        error = response.json()["error"]
        self.assertEqual(set(error), {"code", "message", "request_id"})
        self.assertEqual(error["code"], code)
        self.assertTrue(error["request_id"])
        self.assertEqual(response.headers["X-Request-ID"], error["request_id"])

    def submit(self, client=None, headers=ALICE, **changes):
        if client is None:
            client = self.client
        return client.post(RUNS, json=self.payload | changes, headers=headers)

    def test_create_and_query_use_explicit_nulls_and_redacted_values(self):
        response = self.submit(
            credential_ref="demo_login_fixture",
            target_url=f"{FIXTURE}:443/login?session=sensitive-query#sensitive-fragment",
            goal="打开 https://user:example-secret@demo-app.test/login?key=hidden-query",
            expected_behavior="使用 demo_login_fixture 并验证页面",
        )
        self.assertEqual(response.status_code, 202)
        accepted = response.json()
        self.assertEqual(set(accepted), {"run_id", "status", "created_at"})
        self.assertEqual(accepted["status"], "queued")
        self.assertTrue(accepted["created_at"].endswith("Z"))
        detail = self.client.get(f"{RUNS}/{accepted['run_id']}", headers=ALICE)
        self.assertEqual(detail.status_code, 200)
        result = detail.json()
        for field in ("verdict", "started_at", "finished_at", "summary", "error"):
            self.assertIn(field, result)
            self.assertIsNone(result[field])
        self.assertEqual(
            result["progress"], {"total_cases": None, "completed_cases": 0}
        )
        self.assertFalse(result["cancellation_requested"])
        self.assertEqual(result["target_url"], f"{FIXTURE}/login")
        listing = self.client.get(RUNS, headers=ALICE)
        for response in (response, detail, listing):
            for secret in (
                "demo_login_fixture",
                "sensitive-query",
                "sensitive-fragment",
                "example-secret",
                "hidden-query",
            ):
                self.assertNotIn(secret, response.text)

    def test_400_and_422_have_sanitized_errors(self):
        malformed = self.client.post(
            RUNS,
            content='{"goal": "private-marker",',
            headers=ALICE | {"Content-Type": "application/json"},
        )
        self.assert_error(malformed, 400, "INVALID_REQUEST")
        self.assertNotIn("private-marker", malformed.text)
        for change in (
            {"goal": " "},
            {"expected_behavior": ""},
            {"target_url": "/login"},
            {"target_url": "https://user:private-marker@demo-app.test/"},
            {"target_url": "https:///demo-app.test"},
            {"options": {"headless": "false"}},
            {"options": {"max_steps_per_case": 36}},
            {"options": {"max_steps_per_case": 0}},
            {"options": {"max_steps_per_case": True}},
            {"password": "private-marker"},
            {"goal": "password=private-marker"},
        ):
            with self.subTest(change=change):
                response = self.submit(**change)
                self.assert_error(response, 422, "VALIDATION_ERROR")
                self.assertNotIn("private-marker", response.text)
        for data in ("null", "[]"):
            response = self.client.post(
                RUNS, content=data, headers=ALICE | {"Content-Type": "application/json"}
            )
            self.assert_error(response, 422, "VALIDATION_ERROR")

    def test_identity_target_and_credential_authorization(self):
        self.assert_error(self.client.get(RUNS), 401, "UNAUTHENTICATED")
        self.assert_error(self.submit(headers={}), 401, "UNAUTHENTICATED")
        self.assert_error(
            self.submit(target_url="https://demo-app.test.example.org"),
            403,
            "TARGET_NOT_ALLOWED",
        )
        self.assert_error(
            self.submit(target_url=f"{FIXTURE}:9443"), 403, "TARGET_NOT_ALLOWED"
        )
        denied = self.submit(headers=BOB, credential_ref="demo_login_fixture")
        self.assert_error(denied, 403, "CREDENTIAL_NOT_ALLOWED")
        self.assertNotIn("demo_login_fixture", denied.text)
        run_id = self.submit().json()["run_id"]
        foreign = self.client.get(f"{RUNS}/{run_id}", headers=BOB)
        unknown = self.client.get(f"{RUNS}/unknown", headers=BOB)
        for response in (foreign, unknown):
            self.assert_error(response, 404, "RUN_NOT_FOUND")
        self.assertEqual(
            foreign.json()["error"]["message"], unknown.json()["error"]["message"]
        )
        self.assertEqual(self.client.get(RUNS, headers=BOB).json()["total"], 0)

    def test_pagination_filters_owners_and_stably_sorts_equal_timestamps(self):
        identifiers = iter(("run_2", "run_1", "foreign", "newest"))
        dates = iter((CREATED, CREATED, CREATED, CREATED + timedelta(seconds=1)))
        client = TestClient(
            create_app(
                access=self.access,
                clock=lambda: next(dates),
                new_run_id=lambda: next(identifiers),
            )
        )
        for headers in (ALICE, ALICE, BOB, ALICE):
            self.assertEqual(self.submit(client, headers).status_code, 202)
        first = client.get(f"{RUNS}?page_size=2", headers=ALICE).json()
        self.assertEqual(first["total"], 3)
        self.assertEqual([run["run_id"] for run in first["items"]], ["newest", "run_1"])
        self.assertNotIn("expected_behavior", first["items"][0])
        second = client.get(f"{RUNS}?page=2&page_size=2", headers=ALICE).json()
        self.assertEqual([run["run_id"] for run in second["items"]], ["run_2"])
        empty = client.get(f"{RUNS}?page=3&page_size=2", headers=ALICE).json()
        self.assertEqual(empty, {"items": [], "page": 3, "page_size": 2, "total": 3})
        for query in ("page=0", "page=bad", "page_size=0", "page_size=101"):
            self.assert_error(
                client.get(f"{RUNS}?{query}", headers=ALICE), 422, "VALIDATION_ERROR"
            )
        maximum = client.get(f"{RUNS}?page_size=100", headers=ALICE)
        self.assertEqual(maximum.json()["page_size"], 100)

    def test_artifact_authorization_hides_foreign_and_missing_resources(self):
        alice = self.access.authenticate("fixture-alice")
        self.access.require_resource(alice, "alice", artifact=True)
        for owner in ("bob", None):
            with self.subTest(owner=owner), self.assertRaises(ApiError) as result:
                self.access.require_resource(alice, owner, artifact=True)
            self.assertEqual(result.exception.status, 404)
            self.assertEqual(result.exception.code, "ARTIFACT_NOT_FOUND")

    def test_queue_failure_does_not_publish_run(self):
        client = TestClient(
            create_app(
                access=self.access,
                queue=MemoryRunQueue(capacity=0),
                new_run_id=lambda: "rejected",
            )
        )
        self.assert_error(self.submit(client), 503, "SERVICE_UNAVAILABLE")
        self.assertEqual(client.get(RUNS, headers=ALICE).json()["items"], [])
        self.assert_error(
            client.get(f"{RUNS}/rejected", headers=ALICE), 404, "RUN_NOT_FOUND"
        )

    def test_cookie_session_is_opt_in_and_requires_valid_bearer(self):
        self.assertEqual(
            self.client.post("/api/dev/session", headers=ALICE).status_code, 404
        )
        client = TestClient(create_app(access=self.access, dev_session=True))
        self.assert_error(client.post("/api/dev/session"), 401, "UNAUTHENTICATED")
        session = client.post("/api/dev/session", headers=ALICE)
        self.assertEqual(session.status_code, 204)
        self.assertIn("HttpOnly", session.headers["Set-Cookie"])
        self.assertIn("SameSite=strict", session.headers["Set-Cookie"])
        self.assertEqual(client.get(RUNS).status_code, 200)

    def test_openapi_snapshot_matches_served_first_milestone(self):
        snapshot = json.loads(
            (ROOT / "contracts/http/openapi.json").read_text(encoding="utf-8")
        )
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), snapshot)
        self.assertEqual(set(snapshot["paths"]), {RUNS, f"{RUNS}/{{run_id}}"})
        self.assertEqual(set(snapshot["paths"][RUNS]), {"get", "post"})
        for status in ("400", "401", "403", "422", "503"):
            schema = snapshot["paths"][RUNS]["post"]["responses"][status]["content"][
                "application/json"
            ]["schema"]
            self.assertEqual(schema, {"$ref": "#/components/schemas/ErrorEnvelope"})


if __name__ == "__main__":
    unittest.main()
