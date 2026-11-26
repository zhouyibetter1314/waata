"""Replay the observed B01 action order against the local fixture without a paid model."""

import asyncio
import json
from datetime import UTC, datetime
from itertools import count
from pathlib import Path

from dotenv import dotenv_values
from playwright.async_api import async_playwright
from test_engine_integration import (
    MemoryArtifacts,
    ToolCall,
    assistant_text,
    case_plan,
    planning_response,
    tool_turn,
)
from waata.browser import CredentialField, PlaywrightAdapter
from waata.orchestrator import TestEngine, TestRequest, WAATAError
from waata.orchestrator.config import EngineConfig
from waata_test_support.model import FakeLLM

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:3000/"
ACTIVITY = {
    "browser.navigate",
    "browser.fill",
    "browser.click",
    "browser.select_option",
}


class ReplayModel(FakeLLM):
    async def chat(self, *args, **kwargs):
        # Recorded actions assume the asynchronous login and create responses settle.
        await asyncio.sleep(0.45)
        return await super().chat(*args, **kwargs)


async def replay(browser, password, name, output):
    def css(value):
        return {"strategy": "css", "value": value}

    user = css('input[name="emailOrUsername"]')
    password_input = css('input[name="password"]')
    login = css('button[type="submit"]')
    add = css(
        '[class*="Projects_headerButtonGroup"] button[class*="Projects_addButton"]'
    )
    project_input = css('input[name="name"]')
    submit = css('form:has(input[name="name"]) button[type="submit"]')
    tile = css(f'[class*="projectTitle"][title="{name}"]')
    sidebar = css(f'a[class*="sidebarItemInner"]:has(:text-is("{name}"))')
    sequence = count()

    def action(tool, **arguments):
        return tool_turn(
            ToolCall(f"replay{next(sequence)}", f"browser.{tool}", arguments)
        )

    model = ReplayModel(
        [
            planning_response(
                case_plan(
                    "Create and find both saved project entries",
                    [
                        {"condition": "url_equals", "expected": URL},
                        {"condition": "visible", "locator": tile},
                        {"condition": "visible", "locator": sidebar},
                    ],
                )
            ),
            action("fill", locator=user, secret_ref="fixture_login"),
            action("fill", locator=password_input, secret_ref="fixture_password"),
            action("click", locator=login),
            action("observe"),
            action("click", locator=add),
            action("fill", locator=project_input, value=name),
            action("click", locator=submit),
            action("observe"),
            action("navigate", url=URL),
            action("observe", include_screenshot=True),
            assistant_text("Verify both entries."),
            assistant_text("Verify both entries."),
        ]
    )
    adapter = PlaywrightAdapter(
        browser=browser,
        allowed_origins={URL},
        preferred_css_selectors={
            item["value"]
            for item in (
                user,
                password_input,
                login,
                add,
                project_input,
                submit,
                tile,
                sidebar,
            )
        },
        allowed_websocket_paths={"/socket.io/"},
        allow_screenshots=True,
        credential_sets={
            "fixture": {
                "fixture_login": CredentialField(value="waataadmin", locator=user),
                "fixture_password": CredentialField(
                    value=password, locator=password_input
                ),
            }
        },
    )
    store = MemoryArtifacts()
    events = []

    async def record(event):
        events.append(event.model_dump(mode="json"))

    start = asyncio.get_running_loop().time()
    engine = TestEngine(
        llm=model,
        browser=adapter,
        artifact_store=store,
        # FakeLLM supplies no provider usage. This budget is local to the replay.
        config=EngineConfig(
            max_browser_actions_per_run=35, max_model_tokens_per_run=1_000_000
        ),
    )
    try:
        result = await engine.run(
            TestRequest(
                target_url=URL,
                goal=f"Create and reopen project {name}",
                expected_behavior="Both entries are visible after reopening the dashboard",
                credential_ref="fixture",
            ),
            run_id=name.replace(" ", "-"),
            on_event=record,
        )
    except WAATAError as exc:
        result = exc.partial_result
        if result is None:
            raise
    calls = [
        call for case in result.cases for step in case.steps for call in step.tool_calls
    ]
    report = {
        "run": result.model_dump(mode="json"),
        "events": events,
        "paid_tokens": 0,
        "operation_attempts": sum(call.tool in ACTIVITY for call in calls),
        "seconds": round(asyncio.get_running_loop().time() - start, 2),
    }
    for artifact in result.artifacts:
        if artifact.kind == "screenshot":
            (output / f"{artifact.artifact_id}.png").write_bytes(
                store.saved[artifact.artifact_id].content
            )
    (output / f"{result.run_id}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    checks = [check.passed for case in result.cases for check in case.assertions]
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "verdict": result.verdict,
                "checks": checks,
                "operations": report["operation_attempts"],
                "seconds": report["seconds"],
                "screenshots": sum(a.kind == "screenshot" for a in result.artifacts),
                "errors": [call.error_code for call in calls if not call.success],
                "error": result.error.message if result.error else None,
            }
        ),
        flush=True,
    )
    return (
        result.verdict == "passed"
        and checks == [True] * 3
        and any(a.kind == "screenshot" for a in result.artifacts)
        and report["operation_attempts"] <= 35
    )


async def main():
    password = dotenv_values(ROOT / ".local/4gaboards/.env")["BOARDS_ADMIN_PASSWORD"]
    ticket = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    output = Path("/tmp") / f"waata-b01-replay-{ticket}"
    output.mkdir(parents=True)
    print(f"ARTIFACTS={output}", flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            for index in range(1, 4):
                if not await replay(
                    browser, password, f"B01 Replay {ticket} {index}", output
                ):
                    raise SystemExit("Replay failed; no more scenarios were submitted.")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
