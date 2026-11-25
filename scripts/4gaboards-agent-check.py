"""Run one local 4gaBoards practice case with WAATA, or replay captured turns."""

import argparse
import asyncio
import json
import re
from dataclasses import asdict
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

from dotenv import dotenv_values
from playwright.async_api import async_playwright
from test_engine_integration import MemoryArtifacts
from waata.browser import CredentialField, PlaywrightAdapter
from waata.core.model import (
    ChatMessage, ChatResponse, ModelError, ModelUsage, ToolCall,
    estimate_request_input_tokens,
)
from waata.llm import OpenAILike
from waata.orchestrator import TestEngine, TestRequest, WAATAError
from waata.orchestrator.config import EngineConfig

ROOT = Path("/source")
HOME = "http://127.0.0.1:3000/"
ACTIONS = {"browser.navigate", "browser.click", "browser.fill", "browser.select_option"}
USER = 'input[name="emailOrUsername"]'
PASSWORD = 'input[name="password"]'
SUBMIT = 'button[type="submit"]'
BOARD_ADD = 'div[class*="Boards_headerButtonGroup"] button[title="Add Board"]'
REFS = {"boards_admin_login_ref": USER, "boards_admin_pass_ref": PASSWORD}


def compact_workbench_tools(tools):
    return tuple(tool for tool in tools if tool.name in ACTIONS - {"browser.select_option"})


def compact_workbench_state(messages):
    """Keep checkpoints and recent tool replies; bound repetitive sidebar text."""
    trimmed = []
    for message in messages:
        if message.role == "user" and message.content:
            data = json.loads(message.content)
            page = data.get("state", {}).get("page")
            if page and len(page.get("aria") or "") > 2500:
                aria = page["aria"]
                page["aria"] = aria[:1200] + "\n…\n" + aria[-1200:]
                page["truncated"] = True
                message = ChatMessage("user", json.dumps(data, ensure_ascii=False))
        trimmed.append(message)
    return tuple(trimmed)


class PreparedBrowser:
    """Reuse an in-memory sign-in fixture, not scenario actions."""

    def __init__(self, browser, storage):
        self.browser = browser
        self.storage = storage

    async def new_context(self, **kwargs):
        return await self.browser.new_context(storage_state=self.storage, **kwargs)


async def prepared_browser(browser, password, url):
    context = await browser.new_context()
    try:
        page = await context.new_page()
        await page.goto(HOME)
        await page.locator(USER).fill("waataadmin")
        await page.locator(PASSWORD).fill(password)
        await page.locator(SUBMIT).click()
        await page.locator('button[class*="Projects_addButton"]').wait_for(timeout=5000)
        storage = await context.storage_state()
    finally:
        await context.close()
    prepared = PreparedBrowser(browser, storage)
    check = await prepared.new_context()
    try:
        page = await check.new_page()
        await page.goto(url)
        await page.locator(
            BOARD_ADD if "/projects/" in url else 'button[class*="Board_addListButton"]'
        ).wait_for(timeout=5000)
    finally:
        await check.close()
    return prepared


def scenario(key, tag, url):
    def css_title(prefix, text):
        return f'[class*="{prefix}"][title={json.dumps(text)}]'

    def link(text):
        return f'a[class*="sidebarItemInner"]:has(:text-is({json.dumps(text)}))'

    if key == "B02":
        before, after = f"B02 Draft Lab {tag}", f"B02 Review Lab {tag}"
        old = [css_title("projectTitle", before), link(before)]
        new = [css_title("projectTitle", after), link(after)]
        href = url.removeprefix(HOME.rstrip("/"))
        edit = (
            f'div[class*="sidebarItemProject"]:has(a[href="{href}"]) '
            'button[title="Edit Project"]'
        )
        return (
            f"Open the fixture project at {url}, rename {before} to {after} using "
            f"the project's edit menu, then reopen {HOME}.",
            "The dashboard tile and sidebar link each show the new name, and the old "
            "name is absent from both regions.",
            [edit, 'textarea[name="name"]', 'form:has(textarea[name="name"]) button[type="submit"]',
             'button[title="Rename Project"]'],
            [(s, 1) for s in new] + [(s, 0) for s in old],
        )
    if key == "B03":
        return (
            f"Open project {url}, create B03 Workflow {tag} with the Kanban template "
            "and open the resulting board. The template starts as Empty; open the "
            "template dropdown (input placeholder Empty), click the exact #kanban option, "
            "and confirm the placeholder has changed to Kanban before submitting the board.",
            "In the resulting board, Open, Todo, In Progress, To Test, and Done each exist once.",
            [BOARD_ADD, 'input[name="name"]',
             'input[placeholder="Empty"]', "#kanban", 'input[placeholder="Kanban"]',
             'form:has(input[name="name"]) button[type="submit"]'],
            [(css_title("List_headerName", name), 1)
             for name in ("Open", "Todo", "In Progress", "To Test", "Done")],
        )
    if key == "B04":
        return (
            f"Open the empty board at {url}, create list B04 Incoming {tag}, and revisit {url}.",
            "The same board contains exactly one heading for the newly created list.",
            ['button[class*="Board_addListButton"]', 'textarea[name="name"]',
             'form:has(textarea[name="name"]) button[type="submit"]'],
            [(css_title("List_headerName", f"B04 Incoming {tag}"), 1)],
        )
    inbox = css_title("List_headerName", f"B05 Inbox {tag}")
    card = css_title("Card_name", f"B05 Confirm delivery {tag}")
    return (
        f"Open {url}, add card B05 Confirm delivery {tag} to list B05 Inbox {tag}, "
        "then open the persisted card to inspect its title.",
        "The saved card is in the Inbox list, and its open details show the exact new title.",
        [f'[class*="List_innerWrapper"]:has({inbox}) button[class*="List_addCardButton"]',
         'textarea[name="name"]', 'form:has(textarea[name="name"]) button[type="submit"]',
         f'div[class*="Card_content__"]:has({card})', '[class*="CardModal_headerTitle__"]'],
        [(f'[class*="List_innerWrapper"]:has({inbox}) {card}', 1)],
    )


def b02_offline_continuation(turns, tag, url, controls, tile):
    """Repair only the recorded edit locator, then supply test-only remaining turns."""
    edit_turn = None
    for index, turn in enumerate(turns):
        for call in turn["calls"]:
            arguments = call.get("arguments") or {}
            locator = arguments.get("locator") or {}
            if call["name"] == "browser.click" and 'button[title="Edit Project"]' in locator.get("value", ""):
                locator["value"] = controls[0]
                edit_turn = index

    def step(tool, *, index=None, **arguments):
        turn = {
            "content": None,
            "finish": "tool_calls",
            "usage": None,
            "calls": [{
                "id": f"offline_{len(turns)}", "name": f"browser.{tool}",
                "arguments": arguments,
            }],
        }
        if index is None:
            turns.append(turn)
        else:
            turns.insert(index, turn)

    if edit_turn is None:
        raise ValueError("The replay has no recorded edit action to repair")
    if not any(
        call["name"] == "browser.navigate" and (call.get("arguments") or {}).get("url") == url
        for turn in turns[:edit_turn] for call in turn["calls"]
    ):
        step("navigate", index=edit_turn, url=url)

    step("click", locator={"strategy": "css", "value": controls[3]})
    step("fill", locator={"strategy": "css", "value": controls[1]}, value=f"B02 Review Lab {tag}")
    step("click", locator={"strategy": "css", "value": controls[2]})
    step("observe")
    step("navigate", url=HOME)
    step("screenshot", locator={"strategy": "css", "value": tile})
    turns.append({"content": "Verify the saved name.", "finish": "stop", "usage": None, "calls": []})


class RecordedModel:
    def __init__(self, provider, safe_turn, decisions, limit, replay, offline, lean_budget=None):
        self.provider = provider
        self.metadata = provider.metadata
        self.safe_turn = safe_turn
        self.decisions = decisions
        self.limit = limit
        self.replay = replay
        self.offline = offline
        self.attempts = 0
        self.provider_requests = 0
        self.replay_exhausted = False
        self.actions = 1  # TestEngine opens the target before the first runner turn.
        self.lean_budget = lean_budget
        self.paid = 0
        self.budget_stop = False
        self.usage_missing = False

    async def chat(self, messages, **kwargs):
        if self.attempts >= self.limit:
            raise ModelError("Local request cap reached")
        self.attempts += 1
        item = next(self.replay, None)
        if self.offline:
            await asyncio.sleep(0.4)
        if item is None:
            if self.offline:
                self.replay_exhausted = True
                return ChatResponse(
                    ChatMessage("assistant", "Recorded decisions exhausted.")
                )
            if self.lean_budget is not None:
                # WAATA already refreshes state and verifies checkpoints internally.
                # Keep model turns focused on actions; the engine takes evidence.
                tools = compact_workbench_tools(kwargs.get("tools", ()))
                if tools:
                    messages = compact_workbench_state(messages)
                kwargs["tools"] = tools
                reserve = estimate_request_input_tokens(messages, tools) + self.metadata.max_output_tokens
                if self.usage_missing or self.paid + reserve > self.lean_budget:
                    self.budget_stop = True
                    return ChatResponse(ChatMessage("assistant", "Local token budget reached."))
            self.provider_requests += 1
            response = await self.provider.chat(messages, **kwargs)
            usage = response.usage
            if usage is None:
                self.usage_missing = True
            else:
                self.paid += usage.total_tokens or usage.input_tokens + usage.output_tokens
        else:
            response = ChatResponse(
                ChatMessage("assistant", item["content"], tuple(ToolCall(**c) for c in item["calls"])),
                item["finish"],
                ModelUsage(**item["usage"]) if item["usage"] else None,
            )
        decision = self.safe_turn(response)
        decision["replayed"] = item is not None
        decision["estimated_input"] = estimate_request_input_tokens(
            messages, kwargs.get("tools", ())
        )
        self.decisions.append(decision)
        actions = sum(call.name in ACTIONS for call in response.message.tool_calls)
        if self.actions + actions > 35:
            return ChatResponse(ChatMessage("assistant", "The course operation cap was reached."),
                                usage=response.usage)
        self.actions += actions
        return response


async def verify(browser, password, key, tag, url, checks, output, controls):
    viewport = {"width": 1920, "height": 900} if key == "B03" else None
    context = await browser.new_context(locale="en-US", viewport=viewport)
    try:
        page = await context.new_page()
        page.set_default_timeout(4500)
        await page.goto(HOME)
        await page.locator(USER).fill("waataadmin")
        await page.locator(PASSWORD).fill(password)
        await page.locator(SUBMIT).click()
        await page.locator('button[class*="Projects_addButton"]').wait_for()
        if key != "B02":
            await page.goto(url)
        if key == "B03":
            add_board = page.locator(BOARD_ADD)
            await add_board.wait_for()
            board = page.locator(f'[class*="boardTitle"][title="B03 Workflow {tag}"]')
            if await board.count() == 0:
                await page.screenshot(
                    path=output / "independent.png",
                    mask=[page.locator("input,textarea,[contenteditable]")],
                )
                return {
                    "last_url": page.url, "passed": False,
                    "checks": [{"selector": "expected board tile", "expected": 1, "actual": 0}],
                    "diagnostic": {"scoped_add_board_matches": await add_board.count()},
                }
            await board.first.wait_for()
            await board.first.click()
            await page.wait_for_url("**/boards/*")
        if key == "B02":
            await page.locator('button[class*="Projects_addButton"]').wait_for()
        if key in {"B03", "B04", "B05"}:
            await page.locator('button[class*="Board_addListButton"]').wait_for()
        actual = [{"selector": s, "expected": n, "actual": await page.locator(s).count()}
                  for s, n in checks]
        if key == "B02":
            hrefs = await page.locator(checks[0][0]).evaluate_all(
                "(nodes) => nodes.map(node => node.closest('a')?.getAttribute('href'))"
            )
            sidebar_hrefs = await page.locator(checks[1][0]).evaluate_all(
                "(nodes) => nodes.map(node => node.getAttribute('href'))"
            )
            expected_href = url.removeprefix(HOME.rstrip("/"))
            for name, links in (("dashboard href", hrefs), ("sidebar href", sidebar_hrefs)):
                actual.append({"selector": name, "expected": 1, "actual": links.count(expected_href)})
            if all(item["actual"] == item["expected"] for item in actual):
                # Both panes scroll independently. Frame the actual project in the
                # independent screenshot without changing the Agent's report.
                for selector, _ in checks[:2]:
                    await page.locator(selector).scroll_into_view_if_needed()
        diagnostic = {}
        if key == "B02" and actual[3]["actual"] == 1:
            edit = page.locator(controls[0])
            diagnostic["edit_matches"] = await edit.count()
            row = page.locator(checks[3][0]).locator("..")
            diagnostic["row_controls"] = await row.locator("button").evaluate_all(
                "(nodes) => nodes.map(n => ({title: n.title, "
                "parent: n.parentElement.tagName, className: n.className}))"
            )
            diagnostic["row_class"] = await row.get_attribute("class")
            diagnostic["old_href"] = await page.locator(checks[3][0]).get_attribute("href")
            if diagnostic["edit_matches"] == 1:
                for with_hover in (False, True):
                    try:
                        if with_hover:
                            await edit.locator("..").hover(timeout=1800)
                        await edit.click(trial=True, timeout=1800)
                        diagnostic["trial_after_hover" if with_hover else "trial"] = "ok"
                    except Exception as exc:
                        diagnostic["trial_after_hover" if with_hover else "trial"] = str(exc)[-1400:]
        if key == "B05" and actual[0]["actual"] == 1:
            # The Inbox membership was already verified above; use the persisted
            # card container itself to open details, without an outer-list filter.
            await page.locator(controls[3]).click()
            title = page.locator('[class*="CardModal_headerTitle__"]')
            await title.wait_for()
            actual.append({"selector": "card dialog title", "expected": 1,
                           "actual": int(await title.inner_text() == f"B05 Confirm delivery {tag}")})
        await page.screenshot(path=output / "independent.png",
                              mask=[page.locator("input,textarea,[contenteditable]")])
        return {"last_url": page.url, "checks": actual, "diagnostic": diagnostic,
                "passed": all(i["actual"] == i["expected"] for i in actual)}
    finally:
        await context.close()


async def run(args):
    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    key, tag, url = (fixture[name] for name in ("id", "ticket", "url"))
    if key not in {"B02", "B03", "B04", "B05"} or not re.fullmatch(r"\d{14}", tag):
        raise ValueError("Invalid 4gaBoards fixture")
    if not re.fullmatch(re.escape(HOME) + r"(projects|boards)/\d+", url):
        raise ValueError("The fixture must point to the local 4gaBoards instance")
    password = dotenv_values(ROOT / ".local/4gaboards/.env")["BOARDS_ADMIN_PASSWORD"]
    offline = args.replay or args.verify_only or args.preflight or args.assert_persisted_b05
    settings = dotenv_values(ROOT / ".env") if not offline else {}
    if not offline and not all(settings.get(k) for k in (
        "WAATA_MODEL_BASE_URL", "WAATA_MODEL_NAME", "WAATA_MODEL_API_KEY",
    )):
        raise ValueError("Missing model configuration")
    kind = "verify" if args.verify_only else "replay" if args.replay else "agent"
    run_id = f"{key.lower()}-{kind}-{uuid4().hex[:10]}"
    output = Path("/tmp") / run_id
    output.mkdir()
    print(f"ARTIFACTS={output}", flush=True)
    goal, expected, controls, checks = scenario(key, tag, url)
    selectors = {USER, PASSWORD, SUBMIT, *controls, *(s for s, _ in checks)}
    goal += (
        " You start on the fixture page in a signed-in session; do not log in or reopen it to start. "
        if args.prepared else
        " Sign in with the supplied test credential before navigating or editing. "
        "When all login controls are present, fill both fields and submit in one tool-call batch. "
    )
    goal += (
        "After each action state.page is refreshed; use it rather than calling observe again. "
        "Do not repeat successful navigation to the same URL just to wait for rendering. "
        "When an already open form shows both its input and submit button, batch the fill and submit. "
        "Finish after the last required action; WAATA runs the final checks and captures evidence. "
        "The following exact CSS locators are authorized; use them where applicable: "
        + json.dumps(sorted(selectors))
    )
    if key == "B02":
        goal += (
            " Wait until the page URL has left /login before opening the project. "
            "If the project URL is already correct, let it render instead of navigating again. "
            "The renamed dashboard tile is the result to verify."
        )
    if key == "B05":
        expected += f' The dialog title equals "B05 Confirm delivery {tag}".'
    async with async_playwright() as driver, OpenAILike(
        base_url=settings.get("WAATA_MODEL_BASE_URL") or "http://127.0.0.1:1",
        model=args.model or settings.get("WAATA_MODEL_NAME") or "replay",
        api_key=settings.get("WAATA_MODEL_API_KEY"),
        max_output_tokens=1024,
        timeout=25,
    ) as provider:
        browser = await driver.chromium.launch(headless=not args.headed)
        case_browser = await prepared_browser(browser, password, url) if args.prepared else browser
        if args.preflight:
            await browser.close()
            print("Prepared fixture opened successfully without a model.", flush=True)
            return
        adapter = PlaywrightAdapter(
            browser=case_browser, allowed_origins={HOME}, allowed_css_selectors=selectors,
            allowed_websocket_paths={"/socket.io/"}, allow_screenshots=True,
            credential_sets={"boards": {ref: CredentialField(
                value="waataadmin" if locator == USER else password,
                locator={"strategy": "css", "value": locator},
            ) for ref, locator in REFS.items()}},
        )
        def safe(value):
            if isinstance(value, str):
                return adapter.sanitize(value, "boards")
            if isinstance(value, list):
                return [safe(item) for item in value]
            if isinstance(value, dict):
                return {safe(k): v if k == "secret_ref" and isinstance(v, str) and v in REFS
                        else safe(v) for k, v in value.items()}
            return value

        def safe_turn(response):
            return {"content": safe(response.message.content),
                    "calls": [safe(asdict(c)) for c in response.message.tool_calls],
                    "finish": safe(response.finish_reason),
                    "usage": asdict(response.usage) if response.usage else None}

        if args.verify_only:
            try:
                result = safe(await verify(browser, password, key, tag, url, checks, output, controls))
                (output / "independent.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                print(json.dumps(result), flush=True)
            finally:
                await browser.close()
            return

        turns = []
        if args.assert_persisted_b05:
            if key != "B05" or not args.prepared:
                raise ValueError("Persisted B05 check requires a signed-in B05 fixture")
            scope = {"strategy": "css", "value": checks[0][0]}
            title = {"strategy": "css", "value": controls[4]}
            checks_plan = [
                {"condition": "count", "locator": scope, "expected": 1},
                {"condition": "text_equals", "locator": title, "expected": f"B05 Confirm delivery {tag}"},
            ]
            turns = [
                {"content": json.dumps({"cases": [{
                    "name": "Verify the already saved card", "preconditions": [],
                    "expected_behavior": expected, "checkpoints": checks_plan,
                }]}), "finish": "stop", "usage": None, "calls": []},
                {"content": None, "finish": "tool_calls", "usage": None, "calls": [{
                    "id": "open_saved_card", "name": "browser.click",
                    "arguments": {"locator": {"strategy": "css", "value": controls[3]}},
                }]},
                {"content": "Check the saved card.", "finish": "stop", "usage": None, "calls": []},
            ]
        if source_path := args.replay or args.reuse_plan:
            source = json.loads(Path(source_path).read_text(encoding="utf-8"))
            if source["fixture"]["id"] != key:
                raise ValueError("Captured decisions must match the requested scene")
            old = source["fixture"]
            turns = source["decisions"][:1] if args.reuse_plan else source["decisions"]
            raw = json.dumps(turns).replace(old["ticket"], tag).replace(old["url"], url)
            turns = json.loads(raw)
        if args.finish_b02_offline:
            if not args.replay or key != "B02":
                raise ValueError("Offline B02 continuation requires a B02 replay report")
            b02_offline_continuation(turns, tag, url, controls, checks[0][0])
        decisions, events = [], []
        model = RecordedModel(
            provider, safe_turn, decisions, args.requests, iter(turns), bool(offline),
            lean_budget=args.tokens if args.prepared and not offline else None,
        )
        store = MemoryArtifacts()

        async def record(event):
            events.append(event.model_dump(mode="json"))
            if (
                event.type == "tool.completed"
                and event.payload.get("success")
                and event.payload.get("tool") in {"browser.click", "browser.navigate"}
            ):
                # Give the local SPA a moment to settle before the next automatic
                # observation, rather than spending a model turn to wait.
                await asyncio.sleep(0.35)

        engine = TestEngine(llm=model, browser=adapter, artifact_store=store, config=EngineConfig(
            max_test_cases=1, max_steps_per_case=args.requests - 1,
            max_browser_actions_per_run=35, max_model_requests_per_run=args.requests,
            max_model_tokens_per_run=1_000_000 if args.replay or args.prepared else args.tokens,
            max_input_tokens=28_000,
            capture_final_screenshot=True,
            model_retries=0, timeout_seconds=200,
        ))
        started = monotonic()
        try:
            result = await engine.run(TestRequest(target_url=url if args.prepared else HOME, goal=goal,
                expected_behavior=expected, credential_ref="boards"), run_id=run_id, on_event=record)
        except WAATAError as exc:
            result = exc.partial_result
        seconds = round(monotonic() - started, 2)
        try:
            independent = safe(await verify(browser, password, key, tag, url, checks, output, controls))
        except Exception as exc:
            independent = {"passed": None, "error": safe(str(exc))[:1000]}
        finally:
            await browser.close()
        if result:
            for artifact in result.artifacts:
                blob = store.saved[artifact.artifact_id]
                suffix = ".png" if artifact.kind == "screenshot" else ".json"
                (output / (artifact.artifact_id + suffix)).write_bytes(blob.content)
        report = {
            "fixture": fixture, "kind": "replay" if offline else "live",
            "run": result.model_dump(mode="json") if result else None, "events": events,
            "seconds": seconds, "decisions": decisions, "engine_requests": model.attempts,
            "scripted_continuation": args.finish_b02_offline,
            "replay_exhausted": model.replay_exhausted,
            "requests": model.provider_requests,
            "request_limit": args.requests,
            "token_limit": args.tokens if not args.replay else None,
            "prepared_login": args.prepared,
            "automatic_final_screenshot": True,
            "automatic_screenshot_ids": [
                artifact.artifact_id for artifact in (result.artifacts if result else [])
                if args.prepared and not args.replay and artifact.kind == "screenshot"
            ],
            "budget_stop": model.budget_stop,
            "provider_usage_missing": model.usage_missing,
            "paid_tokens": sum(
                (d["usage"]["total_tokens"] or d["usage"]["input_tokens"] + d["usage"]["output_tokens"])
                for d in decisions if d["usage"] and not d["replayed"]
            ),
            "action_attempt_upper_bound": model.actions, "independent": independent,
        }
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({k: report[k] for k in (
            "kind", "seconds", "requests", "paid_tokens", "action_attempt_upper_bound",
        )} | {"run_id": run_id, "verdict": result.verdict if result else None,
              "independent": independent["passed"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--replay", help="Replay a local report without paid calls")
    mode.add_argument("--reuse-plan", help="Reuse the recorded plan; only runner turns call the model")
    mode.add_argument("--verify-only", action="store_true", help="Check persisted results without contacting a model")
    mode.add_argument("--preflight", action="store_true", help="Check signed-in fixture without contacting a model")
    mode.add_argument("--assert-persisted-b05", action="store_true", help="Run engine assertions against the saved card without re-creating it")
    parser.add_argument("--prepared", action="store_true", help="Start with a locally prepared signed-in session")
    parser.add_argument("--headed", action="store_true", help="Show Chromium on the local display")
    parser.add_argument("--model", help="Override the configured model ID for this run only")
    parser.add_argument("--finish-b02-offline", action="store_true")
    parser.add_argument("--requests", type=int, choices=range(3, 17), default=12)
    parser.add_argument("--tokens", type=int, default=85_000)
    args = parser.parse_args()
    if args.preflight and not args.prepared:
        parser.error("--preflight requires --prepared")
    if args.tokens <= 0:
        parser.error("--tokens must be positive")
    asyncio.run(run(args))
