"""AC-05 with real Vue, FastAPI, PostgreSQL, Worker and Chromium."""

import asyncio
import json
import os
import runpy
import tempfile
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path
from secrets import token_urlsafe
from threading import Thread
from unittest import IsolatedAsyncioTestCase, skipUnless
from uuid import uuid4

import httpx
import uvicorn
from playwright.async_api import async_playwright
from waata.core.model import ChatMessage, ChatResponse, ToolCall
from waata.llm import FakeLLM
from waata_api.infrastructure.config import Settings, TargetPolicies, TargetPolicy
from waata_api.main import create_app
from waata_api.workers.runtime import run_worker

ROOT = Path(__file__).resolve().parents[2]
WEB = "http://127.0.0.1:5173"
API = "http://127.0.0.1:8000"


class ApiServer(uvicorn.Server):
    def capture_signals(self):
        return nullcontext()


@asynccontextmanager
async def api_server(settings):
    server = ApiServer(
        uvicorn.Config(
            create_app(settings=settings),
            host="127.0.0.1",
            port=8000,
            access_log=False,
            log_level="warning",
            timeout_graceful_shutdown=5,
        )
    )
    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(server.serve())
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    await asyncio.sleep(0.05)
            yield
        finally:
            server.should_exit = True


@asynccontextmanager
async def web_server(client):
    process = await asyncio.create_subprocess_exec(
        "node",
        "node_modules/vite/bin/vite.js",
        cwd=ROOT / "apps/web",
        env={**os.environ, "VITE_API_MOCKING": "disabled"},
        stdout=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(10):
            while True:
                if process.returncode is not None:
                    raise RuntimeError("Vite exited before startup")
                try:
                    if (await client.get(WEB)).is_success:
                        break
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(0.05)
        yield
    finally:
        if process.returncode is None:
            process.terminate()
        await process.wait()


def text(value):
    return ChatResponse(ChatMessage("assistant", value))


def script(origin, *, screenshot=False):
    password = {"strategy": "label", "value": "Password"}
    sign_in = {"strategy": "role", "role": "button", "name": "Sign in"}
    scenarios = [
        (
            "Valid password reaches the dashboard",
            "demo.valid",
            "/dashboard",
            {
                "condition": "visible",
                "locator": {"strategy": "test_id", "value": "signed-in"},
            },
        ),
        (
            "Wrong password stays at login",
            "demo.invalid",
            "/login",
            {
                "condition": "text_equals",
                "expected": "Wrong password",
                "locator": {"strategy": "test_id", "value": "login-error"},
            },
        ),
    ]
    plan = {
        "cases": [
            {
                "name": name,
                "preconditions": ["Use a fresh session"],
                "expected_behavior": name,
                "checkpoints": [
                    {"condition": "url_equals", "expected": origin + location},
                    check,
                ],
            }
            for name, _, location, check in scenarios
        ]
    }
    responses = [text(json.dumps(plan))]
    for _, secret_ref, _, _ in scenarios:
        calls = (
            ToolCall(
                "fill", "browser.fill", {"locator": password, "secret_ref": secret_ref}
            ),
            ToolCall("submit", "browser.click", {"locator": sign_in}),
        )
        responses.append(ChatResponse(ChatMessage("assistant", tool_calls=calls)))
        if screenshot and secret_ref == "demo.invalid":
            responses.append(
                ChatResponse(
                    ChatMessage(
                        "assistant",
                        tool_calls=(ToolCall("capture", "browser.screenshot", {}),),
                    )
                )
            )
        responses.append(text("Verify the result."))
    return responses


@skipUnless(
    os.environ.get("WAATA_TEST_DATABASE_URL"),
    "Configure an isolated migrated PostgreSQL 17 database",
)
class PlatformTest(IsolatedAsyncioTestCase):
    async def test_baseline_regression_browser_report_and_restart_replay(self):
        fixture = runpy.run_path(str(ROOT / "testsites/demo-app/server.py"))[
            "DemoServer"
        ]
        password, wrong_password = token_urlsafe(18), token_urlsafe(18)
        baseline = self.enterContext(fixture(0, password))
        regression = self.enterContext(fixture(0, password, regression=True))
        for target in (baseline, regression):
            thread = Thread(target=target.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(thread.join)
            self.addCleanup(target.shutdown)

        owner = uuid4().hex
        template = json.loads(
            (ROOT / "testsites/demo-app/targets.example.json").read_text()
        )[0]
        policy = TargetPolicies(
            tuple(
                TargetPolicy.model_validate(
                    {
                        **template,
                        "origin": site.origin,
                        "owners": [owner],
                        "allow_screenshots": site is baseline,
                    }
                )
                for site in (baseline, regression)
            ),
            {
                "WAATA_DEMO_PASSWORD": password,
                "WAATA_DEMO_WRONG_PASSWORD": wrong_password,
            },
        )
        settings = Settings(
            database_dsn=os.environ["WAATA_TEST_DATABASE_URL"],
            auth_mode="local",
            local_owner_id=owner,
            artifact_root=Path(self.enterContext(tempfile.TemporaryDirectory())),
            worker_concurrency=1,
            policy=policy,
        )
        model = FakeLLM(
            script(baseline.origin, screenshot=True) + script(regression.origin)
        )
        async with httpx.AsyncClient(trust_env=False) as client, web_server(client):
            stop = asyncio.Event()
            async with api_server(settings), asyncio.TaskGroup() as tasks:
                tasks.create_task(run_worker(settings, stop, llm=model))
                try:
                    async with async_playwright() as playwright:
                        browser = await playwright.chromium.launch()
                        try:
                            page = await browser.new_page()
                            base_id = await self.run_in_vue(page, baseline.origin)
                            self.assertEqual(
                                (
                                    await client.get(
                                        f"{API}/api/v1/test-runs/{base_id}/report"
                                    )
                                ).json()["verdict"],
                                "passed",
                            )
                            await (
                                page.locator(".artifact-list button")
                                .filter(has_text="screenshot")
                                .click()
                            )
                            await page.get_by_alt_text("测试证据截图").wait_for()
                            regression_id = await self.run_in_vue(
                                page, regression.origin
                            )
                            self.assertIn(
                                "Service temporarily unavailable",
                                await page.locator(".report-panel").inner_text(),
                            )
                            await page.get_by_role(
                                "button", name="查看证据", exact=False
                            ).first.click()
                            await page.locator(".artifact-preview pre").wait_for()
                        finally:
                            await browser.close()
                finally:
                    stop.set()
                url = f"{API}/api/v1/test-runs/{regression_id}"
                report = (await client.get(f"{url}/report")).json()
                events = (await client.get(f"{url}/events")).text
                self.assertEqual(report["status"], "succeeded")
                self.assertEqual(report["verdict"], "failed")
                public_result = events + json.dumps(report)
                self.assertFalse(
                    password in public_result or wrong_password in public_result
                )
                self.assertIn("event: run.completed", events)
                self.assertIn("event: report.generated", events)
            async with api_server(settings):
                self.assertEqual((await client.get(f"{url}/report")).json(), report)
                result = await client.get(
                    f"{url}/events", headers={"Last-Event-ID": "1"}
                )
                self.assertEqual(result.text, events.split("\n\n", 1)[1])
                last = [
                    line[4:] for line in events.splitlines() if line.startswith("id: ")
                ][-1]
                self.assertEqual(
                    (
                        await client.get(f"{url}/events", params={"after": last})
                    ).status_code,
                    204,
                )
                artifact = report["artifacts"][0]
                evidence = await client.get(API + artifact["url"])
                self.assertEqual(evidence.status_code, 200)
                self.assertEqual(len(evidence.content), artifact["size_bytes"])

    async def run_in_vue(self, page, origin):
        await page.goto(f"{WEB}/runs/new")
        await page.locator('[name="target_url"]').fill(f"{origin}/login")
        await page.locator('[name="goal"]').fill("Verify both login outcomes")
        await page.locator('[name="expected_behavior"]').fill(
            "Valid password enters the dashboard; invalid password displays Wrong password."
        )
        await page.locator('[name="credential_ref"]').fill("demo_login_fixture")
        await page.get_by_role("button", name="提交任务").click()
        await page.wait_for_url("**/runs/run_*")
        await page.locator(".report-case").first.wait_for(timeout=30_000)
        return page.url.rsplit("/", 1)[-1]
