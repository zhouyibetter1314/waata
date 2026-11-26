"""Zero-provider TestEngine replay of B03/B04/B06/B10 against new local fixtures."""

import asyncio
import argparse
import json
import runpy
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from playwright.async_api import async_playwright
from test_engine_integration import (
    MemoryArtifacts, assistant_text, case_plan, planning_response, tool_turn, url_check,
)
from waata.browser import PlaywrightAdapter
from waata.core.model import ChatMessage, ChatResponse, ToolCall
from waata.core.tools import ToolResult
from waata.llm import FakeLLM, OpenAILike
from waata.orchestrator import TestEngine, TestRequest, WAATAError
from waata.orchestrator.config import EngineConfig

ROOT = Path("/source")
HOME = "http://127.0.0.1:3000/"


class DelayedPlayback(FakeLLM):
    async def chat(self, *args, **kwargs):
        await asyncio.sleep(0.65)
        return await super().chat(*args, **kwargs)


class OneSaveTurn(DelayedPlayback):
    def __init__(self, turns, provider=None, recorded=None):
        super().__init__(turns)
        self.provider = provider
        self.recorded = recorded
        self.requests_sent = 0
        self.used = 0
        self.save_calls = None
        if provider:
            self._metadata = provider.metadata

    async def chat(self, messages, **kwargs):
        index = len(self.requests)
        fallback = await super().chat(messages, **kwargs)
        if index != 3 or (self.provider is None and self.recorded is None):
            return fallback
        if self.recorded is not None:
            return tool_turn(*(ToolCall(**call) for call in self.recorded))
        tools = [t for t in kwargs.get("tools", ()) if t.name in {"browser.fill", "browser.click"}]
        state = json.loads(messages[1].content)["state"]
        prompt = ChatMessage("user", json.dumps({
            "page": state["page"],
            "task": "The card editor is already open. Fill its description with "
                    "'Confirm pickup at the north desk.' and click Save in the SAME ordered tool turn.",
            "editor": 'textarea[placeholder="Enter description..."]',
        }, ensure_ascii=False))
        self.requests_sent += 1
        response = await self.provider.chat((prompt,), tools=tools, max_output_tokens=400)
        if response.usage:
            self.used = response.usage.total_tokens or response.usage.input_tokens + response.usage.output_tokens
        accepted = []
        for call in response.message.tool_calls:
            args = call.arguments or {}
            if (call.name == "browser.fill" and args.get("value") == "Confirm pickup at the north desk."
                    and args.get("locator") == css('textarea[placeholder="Enter description..."]')) or (
                    call.name == "browser.click" and args.get("locator") in (
                        button("Save"), {"strategy": "role", "role": "button", "name": "Save"},
                    )):
                accepted.append({"id": f"model_save_{len(accepted)}", "name": call.name,
                                 "arguments": {key: args[key] for key in ("locator", "value") if key in args}})
            else:
                accepted = []
                break
        if [call["name"] for call in accepted] != ["browser.fill", "browser.click"]:
            accepted = []
        self.save_calls = accepted
        return ChatResponse(ChatMessage("assistant", tool_calls=tuple(ToolCall(**c) for c in accepted)))


class MoveTimeout(PlaywrightAdapter):
    """Inject an uncertain result after a real Chromium dispatch, once."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.move_dispatches = 0

    async def open_case(self, url, **kwargs):
        session = await super().open_case(url, **kwargs)
        click = next(tool for tool in session.tools if tool.name == "browser.click")

        async def handler(args, context):
            result = await click.handler(args, context)
            if getattr(args.locator, "name", None) == "Move" and result.success:
                self.move_dispatches += 1
                return ToolResult.failed("TOOL_TIMEOUT", "Offline injected unknown click outcome")
            return result

        session.tools = tuple(
            replace(tool, handler=handler) if tool is click else tool for tool in session.tools
        )
        return session


def css(value):
    return {"strategy": "css", "value": value}


def button(name):
    return {"strategy": "role", "role": "button", "name": name, "exact": True}


def count(locator, expected):
    return {"condition": "count", "locator": css(locator), "expected": expected}


async def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture")
    parser.add_argument("--headed", action="store_true", help="Show playback on the local live display")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--one-live-save", action="store_true")
    mode.add_argument("--replay-save")
    args = parser.parse_args()
    fixture = json.loads(Path(args.fixture).read_text())
    key, source = (fixture[k] for k in ("id", "url"))
    card = fixture.get("card")
    harness = runpy.run_path(str(ROOT / "scripts/4gaboards-agent-check.py"))
    stage = runpy.run_path(str(ROOT / "scripts/4gaboards-stage2.py"))
    if key in {"B03", "B04"}:
        goal, expected, controls, expected_counts = harness["scenario"](key, fixture["ticket"], source)
        selectors = set(controls) | {selector for selector, _ in expected_counts}
        selectors.discard('input[placeholder="Kanban"]')
    else:
        goal, expected, selectors = stage["instructions"](fixture)
    card_selector = f'div[class*="Card_content__"]:has([class*="Card_name"][title={json.dumps(card)}])'
    calls = 0

    def call(name, **args):
        nonlocal calls
        calls += 1
        return ToolCall(f"offline_{calls}", f"browser.{name}", args)

    def click(locator):
        return call("click", locator=locator)

    preview = 'button[class*="CardModal_descriptionText__"]'
    if key == "B03":
        _, name, picker, option, _, submit = controls
        checks = [count(s, n) for s, n in expected_counts]
        turns = [
            tool_turn(click(css(harness["BOARD_ADD"]))),
            tool_turn(click(css(picker))),
            tool_turn(click(css(option))),
            tool_turn(call("fill", locator=css(name), value=f'B03 Workflow {fixture["ticket"]}'),
                      click(css(submit))),
        ]
    elif key == "B04":
        add, name, submit = controls
        checks = [url_check(source), *[count(s, n) for s, n in expected_counts]]
        turns = [
            tool_turn(click(css(add))),
            tool_turn(call("fill", locator=css(name), value=f'B04 Incoming {fixture["ticket"]}'),
                      click(css(submit))),
            tool_turn(call("navigate", url=source)),
        ]
    elif key == "B06":
        text = stage["TEXT"]
        checks = [
            count(preview, 1),
            {"condition": "text_equals", "locator": css(preview), "expected": text},
            {"condition": "text_equals", "locator": css('[class*="CardModal_headerTitle__"]'), "expected": card},
        ]
        turns = [
            tool_turn(click(css(card_selector))),
            tool_turn(click(css('button[class*="CardModal_descriptionButton__"]'))),
            tool_turn(call("fill", locator=css('textarea[placeholder="Enter description..."]'), value=text),
                      click(css(stage["DESCRIPTION_SAVE"]))),
            tool_turn(call("navigate", url=source)),
            tool_turn(click(css(card_selector))),
        ]
    elif key == "B10":
        destination = fixture["destinationUrl"]
        source_count = count(stage["scoped_card"](fixture["list"], card), 0)
        checks = [url_check(destination), count(stage["scoped_card"](fixture["destination"], card), 1)]
        board_choice = f'[class*="Dropdown_dropdownItem"][name={json.dumps(fixture["secondBoard"])}]'
        list_choice = f'[class*="Dropdown_dropdownItem"][name={json.dumps(fixture["destination"])}]'
        turns = [
            tool_turn(click(css(stage["card_edit_option"](card)))),
            tool_turn(click(button("Move Card"))),
            tool_turn(click(css('input[name="boardId"]'))),
            tool_turn(click(css(board_choice))),
            tool_turn(click(css('input[name="listId"]'))),
            tool_turn(click(css(list_choice))),
            tool_turn(click(button("Move")), click(button("Move"))),
            tool_turn(call("navigate", url=source)),
            tool_turn(call("inspect", **source_count)),
            tool_turn(call("navigate", url=destination)),
        ]
    else:
        raise ValueError("Only B03, B04, B06 and B10 are supported")

    password = dotenv_values(ROOT / ".local/4gaboards/.env")["BOARDS_ADMIN_PASSWORD"]
    store = MemoryArtifacts()
    if key != "B06" and (args.one_live_save or args.replay_save):
        raise ValueError("Save-turn options only apply to B06")
    provider = None
    if args.one_live_save:
        config = dotenv_values(ROOT / ".env")
        provider = OpenAILike(base_url=config["WAATA_MODEL_BASE_URL"],
                              api_key=config["WAATA_MODEL_API_KEY"],
                              model="deepseek-v4-pro-ga-260813", max_output_tokens=400, timeout=20)
    recorded = json.loads(Path(args.replay_save).read_text())["save_calls"] if args.replay_save else None
    models = OneSaveTurn([
        planning_response(case_plan(key, checks)), *turns, assistant_text("Check saved state."),
    ], provider=provider, recorded=recorded)
    async with async_playwright() as driver:
        browser = await driver.chromium.launch(headless=not args.headed, slow_mo=150 if args.headed else 0)
        prepared = await harness["prepared_browser"](browser, password, source)
        adapter_class = MoveTimeout if key == "B10" else PlaywrightAdapter
        adapter = adapter_class(
            browser=prepared, allowed_origins={HOME}, allowed_css_selectors=selectors,
            allowed_websocket_paths={"/socket.io/"}, allow_screenshots=True,
        )
        engine = TestEngine(llm=models, browser=adapter, artifact_store=store, config=EngineConfig(
            max_browser_actions_per_run=35, capture_final_screenshot=True,
            max_model_tokens_per_run=1000000, model_retries=0,
            observation_settle_seconds=0.5 if key in {"B03", "B04"} else 0,
        ))
        run_id = f"{key.lower()}-offline-{uuid4().hex[:10]}"
        events = []

        async def record(event):
            events.append(event.model_dump(mode="json"))

        try:
            result = await engine.run(TestRequest(target_url=source, goal=goal, expected_behavior=expected),
                                      run_id=run_id, on_event=record)
        except WAATAError as exc:
            if exc.partial_result is None:
                raise
            result = exc.partial_result
        finally:
            if provider:
                await provider.aclose()
            await browser.close()

    actions = [c for k in result.cases for s in k.steps for c in s.tool_calls
               if c.tool in {"browser.navigate", "browser.click", "browser.fill", "browser.select_option"}]
    source_proof = []
    target_proof = []
    output = Path("/tmp") / run_id
    output.mkdir()
    for artifact in result.artifacts:
        data = store.saved[artifact.artifact_id].content
        suffix = ".png" if artifact.kind == "screenshot" else ".json"
        (output / (artifact.artifact_id + suffix)).write_bytes(data)
        if artifact.kind == "observation" and key == "B10":
            proof = json.loads(data)
            if proof.get("condition") == "count" and proof.get("matched"):
                if proof["url"] == source and proof["actual"] == 0:
                    source_proof.append((proof["observed_at"], artifact.artifact_id))
                if proof["url"] == destination and proof["actual"] == 1:
                    target_proof.append((proof["observed_at"], artifact.artifact_id))
    metrics = {"run_id": run_id, "verdict": result.verdict, "paid_tokens": models.used,
               "model_requests": models.requests_sent,
               "actions": len(actions), "failures": [c.error_code for c in actions if not c.success],
               "source_proof": source_proof, "target_proof": target_proof}
    (output / "report.json").write_text(json.dumps(
        {"fixture": fixture, "metrics": metrics, "run": result.model_dump(mode="json"),
         "events": events, "save_calls": models.save_calls},
        indent=2,
    ))
    print(json.dumps(metrics), flush=True)
    assert result.verdict == "passed" and len(actions) <= 35
    assert any(artifact.kind == "screenshot" for artifact in result.artifacts)
    if key == "B10":
        assert adapter.move_dispatches == 1
        assert metrics["failures"] == ["TOOL_TIMEOUT"]
        assert source_proof and target_proof and source_proof[0][0] < target_proof[0][0]


if __name__ == "__main__":
    asyncio.run(run())
