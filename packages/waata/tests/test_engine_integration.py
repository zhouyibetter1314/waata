"""Independent login checks for FR-001–FR-005 and AC-01–AC-04, AC-06, AC-07."""

import asyncio
import json
from contextlib import contextmanager
from dataclasses import replace
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from secrets import token_urlsafe
from threading import Thread
from unittest import IsolatedAsyncioTestCase
from urllib.parse import parse_qs
from uuid import uuid4

from waata.artifacts import ArtifactInput, ArtifactRef
from waata.browser import CredentialField, PlaywrightAdapter
from waata.browser.observation import COLLECT_CONTROLS
from waata.core.model import ChatMessage, ChatResponse, ToolCall
from waata.core.tools import ToolContext, ToolRegistry, ToolResult
from waata.llm import FakeLLM
from waata.orchestrator import TestEngine, TestRequest, WAATAError
from waata.orchestrator.config import EngineConfig
from waata.orchestrator.planner import parse_plan

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None


LOGIN_ERROR = "Wrong password"
REGRESSION_ERROR = "Service temporarily unavailable"
PASSWORD_FIELD = {"strategy": "label", "value": "Password"}
SIGN_IN_BUTTON = {"strategy": "role", "role": "button", "name": "Sign in"}


class LoginFixture(ThreadingHTTPServer):
    def __init__(self, *, regression=False, redirect_target=None):
        super().__init__(("127.0.0.1", 0), LoginHandler)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.login_url = f"{self.origin}/login"
        self.dashboard_url = f"{self.origin}/dashboard"
        self.password = token_urlsafe(18)
        self.wrong_password = token_urlsafe(18)
        self.session_id = token_urlsafe(18)
        self.error_message = REGRESSION_ERROR if regression else LOGIN_ERROR
        self.redirect_target = redirect_target
        self.login_session_seen = []
        self.submissions = 0
        self.probe_hits = 0
        self.relay_hits = 0


class LoginHandler(BaseHTTPRequestHandler):
    server: LoginFixture

    def log_message(self, format, *args):
        pass

    def _html(self, title, body):
        content = (
            f'<!doctype html><html lang="en"><title>{title}</title>'
            f"<body>{body}</body></html>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _redirect(self, location, *, sign_in=False):
        self.send_response(303)
        self.send_header("Location", location)
        if sign_in:
            self.send_header(
                "Set-Cookie",
                f"demo_session={self.server.session_id}; Path=/; HttpOnly",
            )
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _login(self, *, error=None, marker=None):
        alert = (
            f'<p role="alert" data-testid="login-error">{escape(error)}</p>'
            if error
            else ""
        )
        display_marker = f"<p>{escape(marker)}</p>" if marker else ""
        link = (
            '<a href="/leave">Open linked page</a>'
            if self.server.redirect_target
            else ""
        )
        self._html(
            "Demo login",
            "<main><h1>Demo login</h1>"
            '<form method="post" action="/login">'
            '<label for="password">Password</label>'
            '<input type="password" id="password" name="password" required>'
            '<button type="submit">Sign in</button></form>'
            f"{alert}{display_marker}{link}</main>",
        )

    def do_GET(self):
        signed_in = self.headers.get("Cookie") == (
            f"demo_session={self.server.session_id}"
        )
        if self.path == "/login":
            self.server.login_session_seen.append(signed_in)
            self._login()
        elif self.path == "/dashboard" and signed_in:
            self._html("Dashboard", '<h1 data-testid="signed-in">Signed in</h1>')
        elif self.path == "/controls":
            self._html(
                "Demo controls",
                '<label for="role">Role</label><select id="role">'
                '<option value="reader">Reader</option><option value="writer">Writer</option>'
                '<option value="disabled" disabled>Disabled</option></select>'
                '<label for="note">Note</label>'
                '<input id="note" value="temporary form draft">',
            )
        elif self.path == "/leave" and self.server.redirect_target:
            self._redirect("/relay")
        elif self.path == "/relay" and self.server.redirect_target:
            self.server.relay_hits += 1
            self._redirect(self.server.redirect_target)
        elif self.path == "/probe":
            self.server.probe_hits += 1
            self._html("Probe", "<p>Local test probe</p>")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/login":
            self.send_error(404)
            return
        self.server.submissions += 1
        body = self.rfile.read(int(self.headers["Content-Length"]))
        password = parse_qs(body.decode()).get("password", [None])[0]
        if password == self.server.password:
            self._redirect("/dashboard", sign_in=True)
        else:
            # A synthetic marker rendered by the fixture exercises output redaction.
            self._login(error=self.server.error_message, marker=password)


@contextmanager
def login_fixture(**options):
    with LoginFixture(**options) as fixture:
        thread = Thread(target=fixture.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield fixture
        finally:
            fixture.shutdown()
            thread.join()


class MemoryArtifacts:
    def __init__(self):
        self.saved = {}

    async def save(self, artifact: ArtifactInput) -> ArtifactRef:
        artifact_id = f"artifact_{uuid4().hex}"
        self.saved[artifact_id] = artifact
        return ArtifactRef(
            artifact_id=artifact_id,
            run_id=artifact.run_id,
            case_id=artifact.case_id,
            step_id=artifact.step_id,
            tool_call_id=artifact.tool_call_id,
            kind=artifact.kind,
            mime_type=artifact.mime_type,
            captured_at=artifact.captured_at,
            size_bytes=len(artifact.content),
        )


def assistant_text(content):
    return ChatResponse(ChatMessage("assistant", content))


def tool_turn(*calls):
    return ChatResponse(ChatMessage("assistant", tool_calls=calls))


def case_plan(name, checkpoints):
    return {
        "name": name,
        "preconditions": ["Use a fresh browser session"],
        "expected_behavior": name,
        "checkpoints": checkpoints,
    }


def planning_response(*cases):
    return assistant_text(json.dumps({"cases": cases}))


def locator_test_id(value):
    return {"strategy": "test_id", "value": value}


def url_check(value):
    return {"condition": "url_equals", "expected": value}


def message_text(request):
    return "\n".join(message.content or "" for message in request.messages)


def login_plan(fixture):
    return planning_response(
        case_plan(
            "Valid password signs in",
            [
                url_check(fixture.dashboard_url),
                {"condition": "visible", "locator": locator_test_id("signed-in")},
            ],
        ),
        case_plan(
            "Invalid password remains on the login page",
            [
                url_check(fixture.login_url),
                {
                    "condition": "text_equals",
                    "expected": LOGIN_ERROR,
                    "locator": locator_test_id("login-error"),
                },
            ],
        ),
    )


def login_actions(branch):
    return (
        tool_turn(
            ToolCall(
                f"fill-{branch}",
                "browser.fill",
                {"locator": PASSWORD_FIELD, "secret_ref": f"demo.{branch}"},
            ),
            ToolCall(f"click-{branch}", "browser.click", {"locator": SIGN_IN_BUTTON}),
        ),
        assistant_text("Verify the observed outcome."),
    )


class BrowserEngineIntegrationTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if async_playwright is None:
            self.skipTest("Install the browser extra to run Chromium integration tests")
        playwright = await self.enterAsyncContext(async_playwright())
        self.browser = await playwright.chromium.launch()
        self.addAsyncCleanup(self.browser.close)

    async def test_planner_accepts_one_fenced_json_object_not_surrounding_prose(self):
        raw = '{"cases":[]}'
        fenced = "```json\n" + raw + "\n```"
        self.assertEqual(parse_plan(fenced, max_cases=1, max_checkpoints=1), [])
        self.assertIsNone(
            parse_plan("Here's the plan:\n" + fenced, max_cases=1, max_checkpoints=1)
        )

    async def test_automatic_final_screenshot_without_model_tool_call(self):
        with login_fixture() as fixture:
            url = f"{fixture.origin}/controls"
            model = FakeLLM(
                [planning_response(case_plan("Controls page", [url_check(url)])),
                 assistant_text("Done")]
            )
            store = MemoryArtifacts()
            engine = TestEngine(
                llm=model,
                browser=PlaywrightAdapter(
                    browser=self.browser,
                    allowed_origins={fixture.origin},
                    allow_screenshots=True,
                ),
                artifact_store=store,
                config=EngineConfig(capture_final_screenshot=True),
            )
            result = await engine.run(
                TestRequest(target_url=url, goal="Open controls", expected_behavior="Controls load")
            )
            self.assertEqual(result.verdict, "passed")
            screenshots = [item for item in result.artifacts if item.kind == "screenshot"]
            self.assertEqual(len(screenshots), 1)
            self.assertTrue(store.saved[screenshots[0].artifact_id].content.startswith(b"\x89PNG"))

    async def test_observation_keeps_approved_control_after_long_sidebar(self):
        page = await self.browser.new_page()
        self.addAsyncCleanup(page.close)
        await page.set_content(
            "<button>Old item</button>" * 250
            + '<button id="hidden" hidden>Hidden action</button>'
            + '<button id="rename">Rename Project</button>'
        )
        observed = await page.evaluate(
            COLLECT_CONTROLS,
            {"limit": 2, "textLimit": 100, "approvedSelectors": ["#hidden", "#rename"]},
        )
        self.assertTrue(observed["truncated"])
        self.assertEqual(observed["elements"][0]["approved_css"], "#rename")
        self.assertEqual(observed["elements"][0]["name"], "Rename Project")
        self.assertEqual(observed["elements"][1]["name"], "Old item")

    async def test_native_select_zero_count_and_browser_evidence_registration(self):
        class ArtifactStoreWithFailure(MemoryArtifacts):
            reject = False

            async def save(self, artifact):
                if self.reject:
                    raise OSError("simulated storage failure")
                return await super().save(artifact)

        with login_fixture() as fixture:
            url = f"{fixture.origin}/controls"
            artifacts = ArtifactStoreWithFailure()
            adapter = PlaywrightAdapter(
                browser=self.browser,
                allowed_origins={fixture.origin},
                allow_screenshots=True,
                allowed_css_selectors={"input#note", "input"},
            )
            session = await adapter.open_case(
                url, credential_ref=None, artifact_store=artifacts
            )
            self.addAsyncCleanup(session.close)
            registry = ToolRegistry(session.tools)
            actions = 0

            def reserve_action():
                nonlocal actions
                actions += 1
                return True

            async def tool(name, arguments):
                return await registry.execute(
                    f"browser.{name}",
                    arguments,
                    ToolContext(
                        "run",
                        "case",
                        "step",
                        uuid4().hex,
                        asyncio.get_running_loop().time() + 3,
                        reserve_action,
                    ),
                )

            result = await tool("navigate", {"url": url})
            self.assertTrue(result.success, result.error)
            self.assertEqual(len(registry.specs), 7)
            locator = {"strategy": "label", "value": "Role"}
            result = await tool(
                "select_option", {"locator": locator, "value": "disabled"}
            )
            self.assertEqual(result.error.code, "OPTION_NOT_FOUND")
            result = await tool(
                "select_option", {"locator": locator, "value": "writer"}
            )
            self.assertTrue(result.success, result.error)
            self.assertEqual(actions, 2)

            result = await tool(
                "inspect",
                {
                    "condition": "count",
                    "locator": locator_test_id("absent"),
                    "expected": 0,
                },
            )
            self.assertTrue(result.data["matched"])
            self.assertEqual(result.data["actual"], 0)

            observation = await tool("observe", {"include_screenshot": True})
            self.assertTrue(observation.success, observation.error)
            observation_id, screenshot_id = observation.data["evidence_ids"]
            screenshot = artifacts.saved[screenshot_id]
            self.assertEqual(screenshot.kind, "screenshot")
            self.assertTrue(screenshot.content.startswith(b"\x89PNG\r\n\x1a\n"))
            stored_observation = json.loads(artifacts.saved[observation_id].content)
            self.assertEqual(stored_observation["evidence_ids"], [screenshot_id])
            self.assertNotIn("temporary form draft", json.dumps(observation.data))
            locators = [item["locator"] for item in observation.data["elements"]]
            self.assertIn({"strategy": "css", "value": "input#note"}, locators)

            artifacts.reject = True
            count_before = len(artifacts.saved)
            result = await tool(
                "inspect", {"condition": "title_equals", "expected": "Demo controls"}
            )
            self.assertEqual(result.error.code, "ARTIFACT_WRITE_FAILED")
            self.assertIsNone(result.data)
            self.assertEqual(len(artifacts.saved), count_before)

    async def test_cancel_during_context_allocation_closes_late_context(self):
        allocated = asyncio.Event()
        release = asyncio.Event()
        browser = self.browser

        class DelayedBrowser:
            async def new_context(self, **options):
                context = await browser.new_context(**options)
                allocated.set()
                await release.wait()
                return context

        adapter = PlaywrightAdapter(
            browser=DelayedBrowser(), allowed_origins={"http://127.0.0.1"}
        )
        opening = asyncio.create_task(
            adapter.open_case(
                "http://127.0.0.1",
                credential_ref=None,
                artifact_store=MemoryArtifacts(),
            )
        )
        try:
            await asyncio.wait_for(allocated.wait(), timeout=3)
            opening.cancel()
            await asyncio.sleep(0)
        finally:
            release.set()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(opening, timeout=3)
        self.assertEqual(browser.contexts, [])
        self.assertTrue(browser.is_connected())

    def _engine(
        self, fixture, llm, artifacts=None, *, adapter=PlaywrightAdapter, **config
    ):
        return TestEngine(
            llm=llm,
            browser=adapter(
                browser=self.browser,
                allowed_origins={fixture.origin},
                credential_sets={
                    "demo": {
                        "demo.valid": CredentialField(
                            value=fixture.password, locator=PASSWORD_FIELD
                        ),
                        "demo.invalid": CredentialField(
                            value=fixture.wrong_password, locator=PASSWORD_FIELD
                        ),
                    }
                },
            ),
            artifact_store=artifacts if artifacts is not None else MemoryArtifacts(),
            config=EngineConfig(**config),
        )

    def _request(self, fixture):
        return TestRequest(
            target_url=fixture.login_url,
            goal="Check valid and invalid passwords",
            expected_behavior="Sign in with valid credentials and reject a wrong password",
            credential_ref="demo",
        )

    async def test_screenshot_policy_denial_preserves_checkpoint_failure(self):
        with login_fixture() as fixture:
            llm = FakeLLM(
                [
                    planning_response(
                        case_plan(
                            "Check login destination",
                            [url_check(fixture.dashboard_url)],
                        )
                    ),
                    tool_turn(
                        ToolCall("screenshot", "browser.screenshot", {}),
                        ToolCall(
                            "observe-screenshot",
                            "browser.observe",
                            {"include_screenshot": True},
                        ),
                    ),
                    assistant_text("Verify the login destination."),
                ]
            )
            request = TestRequest(
                target_url=fixture.login_url,
                goal="Check the login destination",
                expected_behavior=f"The final address is {fixture.dashboard_url}",
            )
            result = await self._engine(fixture, llm).run(request)

        self.assertEqual((result.status, result.verdict), ("succeeded", "failed"))
        case = result.cases[0]
        self.assertIs(case.assertions[0].passed, False)
        self.assertEqual(case.assertions[0].actual, fixture.login_url)
        self.assertTrue(case.assertions[0].evidence_ids)
        self.assertEqual(
            [
                (call.tool, call.error_code)
                for step in case.steps
                for call in step.tool_calls
                if not call.success
            ],
            [
                ("browser.screenshot", "ACTION_NOT_ALLOWED"),
                ("browser.observe", "ACTION_NOT_ALLOWED"),
            ],
        )

    async def test_premature_stop_continues_once_when_checkpoint_is_unmet(self):
        with login_fixture() as fixture:
            llm = FakeLLM(
                [
                    planning_response(
                        case_plan("Sign in then return", [url_check(fixture.login_url)])
                    ),
                    login_actions("valid")[0],
                    tool_turn(ToolCall("observe", "browser.observe", {})),
                    assistant_text("Stop before returning."),
                    tool_turn(
                        ToolCall(
                            "return", "browser.navigate", {"url": fixture.login_url}
                        )
                    ),
                    assistant_text("Returned to the login page."),
                ]
            )
            result = await self._engine(fixture, llm).run(self._request(fixture))

        self.assertEqual(result.verdict, "passed")
        observed = llm.requests[3]
        self.assertIn("Signed in", observed.messages[1].content)
        self.assertNotIn("aria", json.loads(observed.messages[-1].content)["data"])
        self.assertIn("checkpoint is unmet", message_text(llm.requests[4]))
        self.assertEqual(len(llm.requests), 6)

    async def test_login_baseline_and_same_url_regression_preserve_evidence(self):
        for regression in (False, True):
            with (
                self.subTest(regression=regression),
                login_fixture(regression=regression) as fixture,
            ):
                llm = FakeLLM(
                    [
                        login_plan(fixture),
                        *login_actions("valid"),
                        *login_actions("invalid"),
                        *(
                            [assistant_text("The regression remains.")]
                            if regression
                            else []
                        ),
                    ]
                )
                artifacts = MemoryArtifacts()
                events = []

                async def record_event(event):
                    events.append(event.model_dump(mode="json"))
                    if event.type == "tool.completed":
                        self.assertLessEqual(
                            set(events[-1]["payload"]["evidence_ids"]),
                            artifacts.saved.keys(),
                        )

                result = await self._engine(fixture, llm, artifacts).run(
                    self._request(fixture), run_id="fixture-run", on_event=record_event
                )

                verdict = "failed" if regression else "passed"
                self.assertEqual(
                    (result.status, result.verdict), ("succeeded", verdict)
                )
                self.assertEqual(result.run_id, "fixture-run")
                self.assertIsNone(result.langfuse_trace_id)
                self.assertEqual(
                    [case.verdict for case in result.cases], ["passed", verdict]
                )
                self.assertEqual(fixture.submissions, 2)
                self.assertEqual(fixture.login_session_seen, [False, False])
                self.assertEqual(self.browser.contexts, [])
                wrong_password_assertion = result.cases[1].assertions[-1]
                self.assertEqual(wrong_password_assertion.expected, LOGIN_ERROR)
                self.assertEqual(wrong_password_assertion.actual, fixture.error_message)
                self.assertIs(wrong_password_assertion.passed, not regression)
                artifact_ids = {artifact.artifact_id for artifact in result.artifacts}
                for case in result.cases:
                    for assertion in case.assertions:
                        self.assertTrue(assertion.evidence_ids)
                        for artifact_id in assertion.evidence_ids:
                            self.assertIn(artifact_id, artifact_ids)
                            saved = artifacts.saved[artifact_id]
                            self.assertEqual(
                                (saved.run_id, saved.case_id),
                                (result.run_id, case.case_id),
                            )

                self._assert_event_pairs(events)
                self._assert_model_turns(llm, fixture)
                published = result.model_dump_json() + json.dumps(events)
                published += "".join(
                    artifact.content.decode()
                    for artifact in artifacts.saved.values()
                    if artifact.mime_type == "application/json"
                )
                model_context = "\n".join(
                    message_text(request) for request in llm.requests
                )
                for forbidden in (
                    fixture.password,
                    fixture.wrong_password,
                    fixture.session_id,
                ):
                    self.assertFalse(
                        forbidden in published,
                        "A synthetic secret appeared in exported test data",
                    )
                    self.assertFalse(
                        forbidden in model_context,
                        "A synthetic secret appeared in model context",
                    )
                self.assertNotIn("demo.invalid", published)
                self.assertNotIn("demo.valid", published)

    def _assert_model_turns(self, llm, fixture):
        _, valid_first, valid_finished, invalid_first, invalid_finished, *extra = (
            llm.requests
        )
        if extra:
            self.assertEqual(len(extra), 1)
            self.assertIn("checkpoint is unmet", message_text(extra[0]))
        self.assertEqual(valid_first.messages[0].role, "system")
        self.assertIn("Demo login", valid_first.messages[1].content)
        self.assertIn("Signed in", valid_finished.messages[1].content)
        self.assertEqual(
            [message.role for message in invalid_first.messages], ["system", "user"]
        )
        self.assertIn(fixture.error_message, invalid_finished.messages[1].content)
        for request, branch in (
            (valid_finished, "valid"),
            (invalid_finished, "invalid"),
        ):
            batch = request.messages[-3:]
            self.assertEqual(
                [message.role for message in batch], ["assistant", "tool", "tool"]
            )
            request_ids = [call.id for call in batch[0].tool_calls]
            reply_ids = [message.tool_call_id for message in batch[1:]]
            self.assertEqual(request_ids, [f"fill-{branch}", f"click-{branch}"])
            self.assertEqual(reply_ids, request_ids)

    def _assert_event_pairs(self, events):
        self.assertEqual(events[0]["type"], "plan.created")
        self.assertEqual(events[-1]["type"], "case.verified")
        self.assertEqual(len({event["event_id"] for event in events}), len(events))
        calls = {}
        for event in events:
            self.assertNotIn("sequence", event)
            if event["type"] == "tool.called":
                calls[event["payload"]["tool_call_id"]] = event
            if event["type"] == "tool.completed":
                called = calls.pop(event["payload"]["tool_call_id"])
                for scope in ("run_id", "case_id", "step_id"):
                    self.assertEqual(event[scope], called[scope])
        self.assertFalse(calls)

    async def test_shared_action_budget_can_end_before_next_case_opens_its_page(self):
        with login_fixture() as fixture:
            llm = FakeLLM([login_plan(fixture), *login_actions("valid")])
            result = await self._engine(
                fixture, llm, max_browser_actions_per_run=3
            ).run(self._request(fixture))

            self.assertEqual(
                (result.status, result.verdict), ("succeeded", "inconclusive")
            )
            self.assertEqual(
                [case.verdict for case in result.cases], ["passed", "inconclusive"]
            )
            self.assertEqual(fixture.submissions, 1)
            self.assertEqual(fixture.login_session_seen, [False])
            self.assertEqual(self.browser.contexts, [])

    async def test_submit_timeout_refreshes_observation_without_replaying_click(self):
        class SubmitTimeoutAdapter(PlaywrightAdapter):
            async def open_case(self, target_url, **options):
                session = await super().open_case(target_url, **options)
                original = next(
                    spec for spec in session.tools if spec.name == "browser.click"
                )

                async def timeout_after_dispatch(args, context):
                    result = await original.handler(args, context)
                    if result.success:
                        return ToolResult.failed(
                            "TOOL_TIMEOUT", "Submit outcome not yet known"
                        )
                    return result

                wrapped = replace(original, handler=timeout_after_dispatch)
                session.tools = tuple(
                    wrapped if spec is original else spec for spec in session.tools
                )
                return session

        with login_fixture() as fixture:
            login_actions_turn, finish = login_actions("valid")
            calls = login_actions_turn.message.tool_calls
            llm = FakeLLM(
                [
                    planning_response(
                        case_plan(
                            "Submit the login form", [url_check(fixture.dashboard_url)]
                        )
                    ),
                    tool_turn(*calls, replace(calls[-1], id="second-click")),
                    finish,
                ]
            )
            result = await self._engine(fixture, llm, adapter=SubmitTimeoutAdapter).run(
                self._request(fixture)
            )

            self.assertEqual(result.verdict, "passed")
            self.assertEqual(fixture.submissions, 1)
            context = json.loads(llm.requests[-1].messages[1].content)["state"]
            self.assertEqual(context["page"]["url"], fixture.dashboard_url)
            self.assertTrue(context["page_is_current"])
            self.assertIsNotNone(context["pending_side_effect"])
            first_click, skipped_click = llm.requests[-1].messages[-2:]
            self.assertEqual(
                json.loads(first_click.content)["error"]["code"], "TOOL_TIMEOUT"
            )
            self.assertEqual(skipped_click.tool_call_id, "second-click")
            self.assertFalse(json.loads(skipped_click.content)["success"])

    async def test_callback_failure_stops_pending_browser_action_and_cleans_up(self):
        with login_fixture() as fixture:
            llm = FakeLLM([login_plan(fixture), *login_actions("valid")])

            async def failing_callback(event):
                if (
                    event.type == "tool.called"
                    and event.model_dump()["payload"]["tool"] == "browser.click"
                ):
                    raise RuntimeError("event storage unavailable")

            with self.assertRaises(WAATAError) as captured:
                await self._engine(fixture, llm).run(
                    self._request(fixture), on_event=failing_callback
                )

            self.assertEqual(captured.exception.error.code, "EVENT_DELIVERY_FAILED")
            self.assertEqual(captured.exception.partial_result.status, "errored")
            self.assertIsNone(captured.exception.partial_result.verdict)
            self.assertEqual(fixture.submissions, 0)
            self.assertEqual(self.browser.contexts, [])
            self.assertTrue(self.browser.is_connected())

    async def test_cancellation_closes_owned_context_and_leaves_browser_usable(self):
        with login_fixture() as fixture:
            entered_model = asyncio.Event()
            external_context = await self.browser.new_context()
            self.addAsyncCleanup(external_context.close)

            class BlockingAgentModel(FakeLLM):
                async def chat(self, messages, *, tools=(), **options):
                    if tools:
                        entered_model.set()
                        await asyncio.Event().wait()
                    return await super().chat(messages, tools=tools, **options)

            task = asyncio.create_task(
                self._engine(fixture, BlockingAgentModel([login_plan(fixture)])).run(
                    self._request(fixture)
                )
            )
            try:
                await asyncio.wait_for(entered_model.wait(), timeout=12)
                self.assertEqual(len(self.browser.contexts), 2)
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

            self.assertEqual(self.browser.contexts, [external_context])
            external_page = await external_context.new_page()
            await external_page.goto(fixture.login_url)
            self.assertEqual(await external_page.title(), "Demo login")

    async def test_click_redirect_is_blocked_before_other_origin_receives_request(self):
        with (
            login_fixture() as target,
            login_fixture(redirect_target=f"{target.origin}/probe") as fixture,
        ):
            # Verify the second server can receive a request before checking the block.
            control_context = await self.browser.new_context()
            try:
                page = await control_context.new_page()
                await page.goto(f"{target.origin}/probe")
                self.assertEqual(target.probe_hits, 1)
            finally:
                await control_context.close()

            llm = FakeLLM(
                [
                    planning_response(
                        case_plan(
                            "Inspect the source page", [url_check(fixture.login_url)]
                        )
                    ),
                    tool_turn(
                        ToolCall(
                            "attempt-redirect",
                            "browser.click",
                            {
                                "locator": {
                                    "strategy": "role",
                                    "role": "link",
                                    "name": "Open linked page",
                                }
                            },
                        )
                    ),
                    assistant_text("Verify current page."),
                ]
            )
            reports = []

            async def record_progress(event):
                reports.append(event.model_dump(mode="json"))

            await self._engine(fixture, llm).run(
                self._request(fixture), on_event=record_progress
            )
            self.assertEqual(fixture.relay_hits, 1)
            self.assertEqual(target.probe_hits, 1)
            completed = [
                event["payload"]
                for event in reports
                if event["type"] == "tool.completed"
            ]
            self.assertTrue(
                any(
                    item["tool"] == "browser.click"
                    and item["error_code"] == "TARGET_NOT_ALLOWED"
                    for item in completed
                ),
                completed,
            )
            self.assertEqual(self.browser.contexts, [])


class UnusedBrowser:
    opened = False

    def validate_target(self, url):
        pass

    def secret_refs(self, credential_ref):
        return ()

    def sanitize(self, value, credential_ref=None):
        return value

    async def open_case(self, target_url, **options):
        self.opened = True


class EngineLifecycleTests(IsolatedAsyncioTestCase):
    async def test_run_deadline_interrupts_model_planning_before_browser_opens(self):
        class BlockingModel(FakeLLM):
            async def chat(self, messages, **options):
                await asyncio.Event().wait()

        browser = UnusedBrowser()
        engine = TestEngine(
            llm=BlockingModel([]),
            browser=browser,
            artifact_store=MemoryArtifacts(),
            config=EngineConfig(timeout_seconds=0.05),
        )
        request = TestRequest(
            target_url="http://127.0.0.1/",
            goal="Check the login page",
            expected_behavior="The login page renders",
        )

        with self.assertRaises(WAATAError) as captured:
            await asyncio.wait_for(engine.run(request), timeout=2)

        self.assertEqual(captured.exception.error.code, "RUN_TIMEOUT")
        self.assertFalse(browser.opened)

    async def test_observer_trace_and_failure_are_independent_of_progress(self):
        class RecordingObserver:
            def __init__(self, failing_stage):
                self.failing_stage = failing_stage
                self.records = []
                self.run_id = None

            async def start_run(self, run_id):
                self.run_id = run_id
                return self

            async def record(self, observation):
                self.records.append(observation)
                if self.failing_stage == observation.kind:
                    raise RuntimeError("Synthetic observer record failure")

            async def close(self):
                if self.failing_stage == "close":
                    raise RuntimeError("Synthetic observer close failure")
                return "fake-trace"

        request_marker = token_urlsafe(18)
        request = TestRequest(
            target_url="http://127.0.0.1/",
            goal=f"Check login for test marker {request_marker}",
            expected_behavior="The login page renders",
        )
        for failing_stage in (None, "model.completed", "close"):
            with self.subTest(failing_stage=failing_stage):
                observer = RecordingObserver(failing_stage)
                events = []

                async def record_event(event):
                    events.append(event)

                result = await TestEngine(
                    llm=FakeLLM([planning_response()]),
                    browser=UnusedBrowser(),
                    artifact_store=MemoryArtifacts(),
                    observability=observer,
                ).run(request, run_id="observer-run", on_event=record_event)

                self.assertEqual(
                    (result.status, result.verdict), ("succeeded", "inconclusive")
                )
                self.assertEqual(
                    result.langfuse_trace_id,
                    None if failing_stage == "close" else "fake-trace",
                )
                self.assertEqual(observer.run_id, result.run_id)
                self.assertEqual([event.type for event in events], ["plan.created"])
                self.assertEqual(
                    [record.kind for record in observer.records],
                    [
                        "run.started",
                        "model.completed",
                        "plan.created",
                        "run.finished",
                    ],
                )
                for record in observer.records:
                    self.assertEqual(record.run_id, result.run_id)
                    self.assertNotIn(request_marker, json.dumps(record.fields))
