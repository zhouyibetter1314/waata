"""Submit one prepared B06–B10 fixture to the local WAATA platform."""

import asyncio
import json
import os
import re
import runpy
import sys
from dataclasses import replace
from pathlib import Path

import httpx
from dotenv import dotenv_values
from pydantic import BaseModel, Field
from waata.core.model import ChatMessage, ChatResponse, ModelError, ToolCall, estimate_request_input_tokens
from waata.llm import OpenAILike
from waata_test_support.model import FakeLLM
from waata_api.infrastructure.config import Settings, TargetPolicies, TargetPolicy
from waata_api.infrastructure.database import open_repository
from waata_api.workers.runtime import run_worker

ROOT = Path("/source")
SITE = "http://127.0.0.1:3000/"
GATEWAY = "http://waata-4ga-web:5173"
ACTIONS = {"browser.navigate", "browser.fill", "browser.click", "browser.select_option"}
TEXT = "Confirm pickup at the north desk."
DESCRIPTION_SAVE = 'button[type="submit"][title="Save"]'
DESCRIPTION_EDITOR = 'textarea[placeholder="Enter description..."]'
DESCRIPTION_OPEN = 'button[class*="CardModal_descriptionButton__"]'
BASE = {'input[name="emailOrUsername"]', 'input[name="password"]', 'button[type="submit"]'}

def latest_tool_turn(messages):
    """Keep current state and the last complete assistant/tool exchange."""
    for index in range(len(messages) - 1, 1, -1):
        if messages[index].role == "assistant":
            return (*messages[:2], *messages[index:])
    return messages

def css(value):
    return {"strategy": "css", "value": value}


def normalize_approved_click(call, selectors):
    """Accept shorthand only for an exact fixture-approved CSS selector."""
    arguments = call.arguments or {}
    locator = arguments.get("locator")
    if call.name == "browser.click" and isinstance(locator, str) and locator in selectors:
        return replace(call, arguments={**arguments, "locator": css(locator)})
    return call


class B10Click(BaseModel):
    locators: list[str] = Field(min_length=1, max_length=7)


class B10SourceCheck(BaseModel):
    pass


def compact_b10(messages, tools, selectors):
    state = json.loads(messages[1].content)
    page = state["state"].get("page") or {}
    page["elements"] = [el for el in page.get("elements", [])
                        if el.get("locator", {}).get("value") in selectors
                        or el.get("name") in {"Move Card", "Move"}]
    page["aria"] = (page.get("aria") or "")[-700:]
    tools = tuple(
        replace(t, input_model=B10Click, model_schema=None, description="Click an ordered batch of 1-7 authorized B10 controls. Give all remaining dependent dialog clicks together when their choices are known; stop on the first failure.")
        if t.name == "browser.click" else
        replace(t, input_model=B10SourceCheck, model_schema=None, description="Use empty arguments {} on the source board after moving to verify the card is absent.")
        if t.name == "browser.inspect" else t
        for t in tools if t.name != "browser.fill"
    )
    return (messages[0], replace(messages[1], content=json.dumps(state, ensure_ascii=False)), *messages[2:]), tools


def fixture_setup_calls(page, target):
    """Trusted fixture setup only; the model still performs the business operation."""
    selectors = {item.get("locator", {}).get("value") for item in page.get("elements", [])}
    if BASE <= selectors or page.get("url") == SITE + "login":
        return (
            ToolCall("fixture-user", "browser.fill", {
                "locator": css('input[name="emailOrUsername"]'), "secret_ref": "boards_admin_login_ref",
            }),
            ToolCall("fixture-pass", "browser.fill", {
                "locator": css('input[name="password"]'), "secret_ref": "boards_admin_pass_ref",
            }),
            ToolCall("fixture-login", "browser.click", {"locator": css('button[type="submit"]')}),
        )
    if page.get("url") == SITE:
        return (ToolCall("fixture-board", "browser.navigate", {"url": target}),)
    return ()


def scoped_card(list_name, card):
    return (f'[class*="List_innerWrapper"]:has([class*="List_headerName"][title={json.dumps(list_name)}]) '
            f'[class*="Card_name"][title={json.dumps(card)}]')


def card_edit_option(card):
    return (f'div[class*="Card_card__"]:has([class*="Card_name"][title={json.dumps(card)}]) '
            'button[class*="Card_editCardButton__"][title="Edit Card"]')


def b10_click_targets(fixture):
    def option(name):
        return css(f'[class*="Dropdown_dropdownItem"][name={json.dumps(name)}]')

    return {
        "Edit Card": css(card_edit_option(fixture["card"])),
        "Open Move Card dialog": {"strategy": "role", "role": "button", "name": "Move Card"},
        "Board picker": css('input[name="boardId"]'),
        fixture["secondBoard"]: option(fixture["secondBoard"]),
        "List picker": css('input[name="listId"]'),
        fixture["destination"]: option(fixture["destination"]),
        "Submit final Move confirmation": {"strategy": "role", "role": "button", "name": "Move"},
    }


def form_batch(fixture):
    card = fixture["card"]
    tile = f'div[class*="Card_content__"]:has([class*="Card_name"][title={json.dumps(card)}])'
    def click(selector):
        return "browser.click", {"locator": css(selector)}
    def fill(selector, value):
        return "browser.fill", {"locator": css(selector), "value": value}
    if fixture["id"] == "B05":
        inbox = json.dumps(fixture["list"])
        add = f'[class*="List_innerWrapper"]:has([class*="List_headerName"][title={inbox}]) button[class*="List_addCardButton"]'
        return {
            "Open Add Card in Inbox": click(add),
            "Enter requested card title": fill('textarea[name="name"]', card),
            "Submit new card": click('form:has(textarea[name="name"]) button[type="submit"]'),
        }, tile
    return {
        "Open existing card": click(tile),
        "Open description editor": click(DESCRIPTION_OPEN),
        "Enter requested description": fill(DESCRIPTION_EDITOR, TEXT),
        "Save description": click(DESCRIPTION_SAVE),
    }, tile


def instructions(fixture):
    key = fixture["id"]
    if key == "B01":
        name = f'B01 Release Lab {fixture["ticket"]}'
        tile = f'[class*="projectTitle"][title={json.dumps(name)}]'
        sidebar = f'a[class*="sidebarItemInner"]:has(:text-is({json.dumps(name)}))'
        selectors = BASE | {tile, sidebar, 'button[class*="Projects_addButton"]',
                            'input[name="name"]', 'form:has(input[name="name"]) button[type="submit"]'}
        return (
            f'B01: Sign in using supplied refs. Create project {name} using the dashboard Add Project. '
            f'When the name and submit control are visible, batch fill and submit. Revisit {SITE}. '
            'Use the current observed page and stop after the work is complete. Authorized CSS: '
            + json.dumps(sorted(selectors)),
            f'Final URL is {SITE}. Dashboard tile {tile} and distinct sidebar link {sidebar} each have count 1.',
            selectors,
        )
    url, card = fixture["url"], fixture["card"]
    if not re.fullmatch(re.escape(SITE) + r"boards/\d+", url):
        raise ValueError("Expected a local board fixture")
    card_name = f'[class*="Card_name"][title={json.dumps(card)}]'
    contents = f'div[class*="Card_content__"]:has({card_name})'
    scope = lambda name: scoped_card(name, card)
    selectors = BASE | {card_name, contents, '[class*="CardModal_headerTitle__"]'}
    if key == "B05":
        inbox = fixture["list"]
        option = f'[class*="List_innerWrapper"]:has([class*="List_headerName"][title={json.dumps(inbox)}]) button[class*="List_addCardButton"]'
        selectors |= {option, scope(inbox), 'textarea[name="name"]',
                      'form:has(textarea[name="name"]) button[type="submit"]'}
        goal = (f'Add exactly one card {card} to {inbox} using its Add Card button. '
                'Batch filling and clicking submit when both controls are shown. Then open the persisted card.')
        expected = (f'{scope(inbox)} has count 1. The open card title '
                    f'[class*="CardModal_headerTitle__"] is exactly {card}.')
    elif key == "B06":
        preview = 'button[class*="CardModal_descriptionText__"]'
        selectors |= {DESCRIPTION_EDITOR, DESCRIPTION_OPEN, DESCRIPTION_SAVE, preview}
        goal = (f'Open {card} and click the large Add description button, not its toolbar icon. '
                f'Confirm the editor is open in Edit mode, fill "{TEXT}", click Save, '
                'then reopen the card. When the editor and Save are both visible, batch the fill '
                f'and Save ({DESCRIPTION_SAVE}) in the same tool turn. Do not navigate away until '
                'description preview is visible. If the editor is absent, open it before retrying fill.')
        expected = (f'The open card title is exactly {card}; the description preview {preview} '
                    f'exists (count 1) and has text exactly "{TEXT}". '
                    'Include the count so a missing preview is an evidenced failure.')
    elif key in {"B07", "B08"}:
        other = f'[class*="Card_name"][title={json.dumps(fixture["other"])}]'
        selectors |= {other, 'input[placeholder="Filter cards..."]',
                      'button[title="Filter By Labels"]', '[class*="Filters_filterItem"]'}
        goal = ('Fill the board card search with Quartz.' if key == "B07" else
                f'Open Filter By Labels, select "{fixture["label"]}", and close the picker with the filter active.')
        expected = f'{card_name} has count 1 and {other} has count 0 on the board.'
        if key == "B08":
            name = json.dumps(fixture["label"])
            picker = f'span[class*="Item_name__"][title={name}]'
            chip = f'[class*="Filters_filterItem"]:has(:text-is({name}))'
            selectors |= {picker, chip}
            goal = (f'Open Filter By Labels and click the exact picker option {picker} once. '
                    'Close the picker without clicking the label on a card or the active-chip remove button.')
            expected += f' The active chip {chip} has count 1.'
    elif key == "B09":
        target = fixture["destination"]
        field = '[class*="CardModal_headerListField__"]'
        option = f'[class*="Dropdown_dropdownItem"][name={json.dumps(target)}]'
        selectors |= {field, option, scope(fixture["list"]), scope(target)}
        goal = (f'Open {card}, click the current list field {field}, then choose {option}. '
                'Confirm the selected list has changed before revisiting the board and reopening the card.')
        expected = f'The modal selected list is exactly "{target}". {scope(fixture["list"])} has count 0 and {scope(target)} has count 1.'
    elif key == "B10":
        target, destination_url = fixture["destination"], fixture["destinationUrl"]
        if not re.fullmatch(re.escape(SITE) + r"boards/\d+", destination_url):
            raise ValueError("Expected a local destination")
        board_option = f'[class*="Dropdown_dropdownItem"][name={json.dumps(fixture["secondBoard"])}]'
        list_option = f'[class*="Dropdown_dropdownItem"][name={json.dumps(target)}]'
        edit_option = card_edit_option(card)
        selectors |= {edit_option, 'input[name="boardId"]',
                      'input[name="listId"]', board_option, list_option,
                      scope(fixture["list"]), scope(target)}
        goal = (f'On the source board, use the scoped card menu {edit_option} > Move Card '
                f'to move {card} to {fixture["secondBoard"]} / {target}. Do not open card details first. '
                f'Choose the board and list in the move popup; submit Move before any checks. '
                f'Revisit source {url}, wait for the source list to be visible, '
                f'use browser.inspect on {scope(fixture["list"])} to record count 0, '
                f'then open destination {destination_url}. '
                f'Use one browser.click batch for consecutive dialog steps. Authorized labels: '
                f'{json.dumps(list(b10_click_targets(fixture)))}. Return arguments as '
                '{"locators":["first label","next label"]}; decide the order yourself. '
                'Use browser.inspect with empty arguments {} on the source board after Move.')
        expected = f'Final URL is {destination_url}; {scope(target)} has count 1.'
    else:
        raise ValueError("Unsupported fixture")
    setup = (f'The trusted fixture signs in and opens {url}. Do not fill login fields. '
             if key in {"B05", "B06", "B10"} else
             f'Sign in using supplied refs; wait for the redirect, then open {url}. ')
    if key == "B06":
        example = {"locator": css(DESCRIPTION_EDITOR), "value": TEXT}
        goal += f' Fill takes an object: {json.dumps(example)}. Click takes only a locator object.'
    return (
        f'{key}: {setup}{goal} '
        'Use automatically refreshed page state; stop when done. Engine takes the screenshot. '
        'Do not repeat a navigation to the same URL if it has already loaded. '
        f'Exact authorized CSS selectors: {json.dumps(sorted(selectors))}',
        expected, selectors,
    )


class LimitedModel:
    def __init__(self, provider, harness, fixture, sanitize, *, one_shot=False):
        self.provider = provider
        self.metadata = provider.metadata
        self.harness = harness
        self.key = key = fixture["id"]
        self.source = fixture["url"]
        self.source_card = scoped_card(fixture["list"], fixture["card"]) if key == "B10" else None
        self.click_selectors = instructions(fixture)[2] if key == "B10" else set()
        self.click_targets = b10_click_targets(fixture) if key == "B10" else {}
        self.form_targets = form_batch(fixture)[0] if one_shot and key in {"B05", "B06"} else {}
        self.requests = self.tokens = 0
        self.actions = 1
        self.unknown = False
        self.stop_reason = None
        self.request_limit = 13 if key == "B10" else 10
        self.token_limit = 70000 if key == "B10" else 55000
        self.last_idle_page = None
        self.idle_turns = 0
        self.invalid_locator_turns = 0
        self.turns = []
        self.sanitize = sanitize
        self.setup = set()
        self.one_shot = one_shot
        self.authored_batch = False
        self.deferred_form_calls = ()
        self.verification = (form_replay(fixture) if self.form_targets else b10_replay(fixture, include_batch=False)) if one_shot else None

    async def chat(self, messages, **kwargs):
        if self.invalid_locator_turns >= 2:
            self.stop_reason = "repeated_invalid_locator_arguments"
            return ChatResponse(ChatMessage("assistant", "Stopped after two tool turns with missing locator objects."))
        tools = kwargs.get("tools", ())
        page_key = None
        if tools:
            tools = tuple(t for t in tools if t.name in ACTIONS - {"browser.select_option"}
                          or (self.key == "B10" and t.name == "browser.inspect"))
            messages = latest_tool_turn(self.harness["compact_workbench_state"](messages))
            kwargs["tools"] = tools
            page = (json.loads(messages[1].content)["state"].get("page") or {})
            page_key = (page.get("url"), page.get("title"), page.get("aria"))
            if self.key in {"B05", "B06", "B10"}:
                setup = fixture_setup_calls(page, self.source)
                if setup and setup[0].id not in self.setup:
                    self.setup.add(setup[0].id)
                    self.actions += len(setup)
                    self.turns.append({"phase": "fixture_setup", "tools": [call.name for call in setup]})
                    return ChatResponse(ChatMessage("assistant", None, setup))
            if self.idle_turns >= 2 and page_key == self.last_idle_page:
                self.stop_reason = "repeated_read_only_turns"
                return ChatResponse(ChatMessage("assistant", "No progress on the same page."))
            if self.key == "B10":
                messages, tools = compact_b10(messages, tools, self.click_selectors)
                kwargs["tools"] = tools
            if self.deferred_form_calls:
                calls, self.deferred_form_calls = self.deferred_form_calls, ()
                if not re.fullmatch(re.escape(SITE) + r"(?:boards/\d+/)?cards/\d+", page_key[0] or ""):
                    self.stop_reason = "expected_card_page_not_observed"
                    return ChatResponse(ChatMessage("assistant", "Card navigation did not reach a card page."))
                self.actions += len(calls)
                self.turns.append({"phase": "model_authored_batch_continued", "tools": [call.name for call in calls]})
                return ChatResponse(ChatMessage("assistant", None, calls))
        verification = self.verification if not page_key or self.authored_batch else None
        author = self.one_shot and page_key is not None and not self.authored_batch
        if author:
            if page_key[0] != self.source:
                self.stop_reason = "fixture_source_not_ready"
                return ChatResponse(ChatMessage("assistant", "The source board fixture is not ready."))
            tools = tuple(replace(t, input_model=B10Click, model_schema=None, description="Execute the ordered authorized action labels.")
                          for t in tools if t.name == "browser.click")
            kwargs["tools"] = tools
            labels = sorted(self.form_targets or self.click_targets)
            goal = ('Create and save the requested card in Inbox. The add form is closed.' if self.key == "B05" else
                    'Save the requested description on the existing card. The card and editor are closed.')
            messages = (ChatMessage("user", (
                f'{goal} Call browser.click once with locators containing each exact action label in the correct execution order. '
                f'Unordered labels: {json.dumps(labels)}. The engine will open the saved card and verify separately. No prose.'
            ) if self.form_targets else (
                'Design one complete UI action batch to move the fixture card to board '
                f'{next(label for label in labels if label.startswith("B10 Fulfilment"))} and list '
                f'{next(label for label in labels if label.startswith("B10 Received"))}. '
                'On the source board the card menu is not open. Use the UI to open that menu, '
                'open the move dialog, choose the destination board and list, and submit. '
                'Call browser.click just once with a locators array containing each of the seven exact '
                f'labels in the right execution order. These labels are listed alphabetically: {json.dumps(labels)}. '
                'Open Move Card dialog opens the dialog; Submit final Move confirmation is a different '
                'button and MUST be last, after both destination choices. '
                'The engine will verify the result separately. No prose.'
            )),)
        reserve = estimate_request_input_tokens(messages, tools) + self.metadata.max_output_tokens
        if verification is None and (self.unknown or self.requests >= self.request_limit or self.tokens + reserve > self.token_limit):
            self.stop_reason = "missing_usage" if self.unknown else "local_model_budget"
            return ChatResponse(ChatMessage("assistant", "Local model budget reached."))
        replay = verification is not None or isinstance(self.provider, FakeLLM)
        if not replay:
            self.requests += 1
        try:
            response = await (verification or self.provider).chat(messages, **kwargs)
        except ModelError:
            if verification is not None:
                self.stop_reason = "engine_verification_sequence_exhausted"
                return ChatResponse(ChatMessage("assistant", "No further engine verification actions."))
            self.unknown = True
            self.stop_reason = "provider_error_no_usage_receipt"
            raise
        usage = response.usage
        self.unknown = usage is None and not replay
        if usage is not None:
            self.tokens += usage.total_tokens or usage.input_tokens + usage.output_tokens
        if author:
            self.authored_batch = True
            calls = response.message.tool_calls
            labels = (calls[0].arguments or {}).get("locators") if len(calls) == 1 and calls[0].name == "browser.click" else None
            allowed = self.form_targets or self.click_targets
            if (not isinstance(labels, list) or not all(isinstance(label, str) for label in labels)
                    or len(labels) != len(allowed) or set(labels) != set(allowed)
                    or (self.key == "B06" and labels[0] != "Open existing card")
                    or (not self.form_targets and labels[-1] != "Submit final Move confirmation")):
                self.stop_reason = "model_did_not_author_complete_move_batch"
                return ChatResponse(ChatMessage("assistant", "The model did not return the required complete action batch."))
        raw_types = [type((call.arguments or {}).get("locator")).__name__ for call in response.message.tool_calls]
        batches = [len(args["locators"]) for call in response.message.tool_calls
                   if isinstance((args := call.arguments or {}).get("locators"), list)]
        if self.click_selectors or self.form_targets:
            def bind(call):
                args = call.arguments or {}
                value = args.get("locator")
                if call.name == "browser.click" and isinstance(value, str) and value in {"Move Card", "Move"}:
                    return replace(call, arguments={**args, "locator": {"strategy": "role", "role": "button", "name": value}})
                if call.name == "browser.inspect" and call.arguments == {} and page_key and page_key[0] == self.source:
                    return replace(call, arguments={"locator": css(self.source_card), "condition": "count", "expected": 0})
                return normalize_approved_click(call, self.click_selectors)
            def expand(call):
                args = call.arguments or {}
                labels = args.get("locators")
                if (call.name == "browser.click" and set(args) == {"locators"}
                        and isinstance(labels, list) and 1 <= len(labels) <= 7
                        and len({label for label in labels if isinstance(label, str)}) == len(labels)
                        and all(label in (self.form_targets or self.click_targets) for label in labels)):
                    if self.form_targets:
                        return tuple(ToolCall(f"{call.id}-{index}", *self.form_targets[label])
                                     for index, label in enumerate(labels))
                    return tuple(replace(call, id=f"{call.id}-{index}", arguments={"locator": self.click_targets[label]})
                                 for index, label in enumerate(labels))
                return (bind(call),)

            calls = tuple(item for call in response.message.tool_calls for item in expand(call))
            if author and self.key == "B06":
                calls, self.deferred_form_calls = calls[:1], calls[1:]
            response = replace(response, message=replace(response.message, tool_calls=calls))
        first_call = next(iter(response.message.tool_calls), None)
        if (first_call and first_call.name in {"browser.click", "browser.fill", "browser.select_option"}
                and not isinstance((first_call.arguments or {}).get("locator"), dict)):
            self.invalid_locator_turns += 1
        else:
            self.invalid_locator_turns = 0
        self.turns.append({
            "phase": "model_authored_batch" if author else "engine_verification" if verification else
            "runner" if page_key is not None else "planner",
            "tools": [call.name for call in response.message.tool_calls],
            "argument_keys": [sorted((call.arguments or {}).keys()) for call in response.message.tool_calls],
            "raw_locator_types": raw_types,
            "batch_sizes": batches,
            "finish_reason": response.finish_reason,
            # Preserve only the locator, never form values or credentials.
            "targets": [
                {
                    "tool": call.name,
                    "locator": {
                        key: self.sanitize(value)[:512]
                        for key, value in locator.items()
                        if key in {"strategy", "role", "value", "name"} and isinstance(value, str)
                    },
                }
                for call in response.message.tool_calls
                if isinstance((locator := (call.arguments or {}).get("locator")), dict)
            ],
            "requested_source_count_zero": self.key == "B10"
            and page_key is not None and page_key[0] == self.source
            and any(
                call.name == "browser.inspect"
                and (call.arguments or {}).get("condition") == "count"
                and (call.arguments or {}).get("expected") == 0
                and (call.arguments or {}).get("locator") == {"strategy": "css", "value": self.source_card}
                for call in response.message.tool_calls
            ),
        })
        actions = sum(call.name in ACTIONS for call in response.message.tool_calls)
        if page_key is not None and not actions and response.message.tool_calls:
            self.idle_turns = self.idle_turns + 1 if self.last_idle_page == page_key else 1
            self.last_idle_page = page_key
        else:
            self.idle_turns = 0
        if self.actions + actions > 35:
            self.stop_reason = "course_operation_limit"
            return ChatResponse(ChatMessage("assistant", "Course operation limit reached."))
        self.actions += actions
        return response


def b06_replay(fixture):
    from test_engine_integration import assistant_text, case_plan, planning_response, tool_turn

    card = fixture["card"]
    tile = f'div[class*="Card_content__"]:has([class*="Card_name"][title={json.dumps(card)}])'
    preview = css('button[class*="CardModal_descriptionText__"]')
    checks = [
        {"condition": "text_equals", "locator": preview, "expected": TEXT},
        {"condition": "text_equals", "locator": css('[class*="CardModal_headerTitle__"]'), "expected": card},
    ]
    return FakeLLM([
        planning_response(case_plan("B06 saved description", checks)),
        tool_turn(ToolCall("open-card", "browser.click", {"locator": css(tile)})),
        tool_turn(ToolCall("open-editor", "browser.click", {"locator": css(DESCRIPTION_OPEN)})),
        tool_turn(ToolCall("fill-editor", "browser.fill", {"locator": css(DESCRIPTION_EDITOR), "value": TEXT}),
                  ToolCall("save-description", "browser.click", {"locator": css(DESCRIPTION_SAVE)})),
        tool_turn(ToolCall("reopen-board", "browser.navigate", {"url": fixture["url"]})),
        tool_turn(ToolCall("reopen-card", "browser.click", {"locator": css(tile)})),
        assistant_text("Verify the persisted description."),
    ])


def b10_replay(fixture, *, include_batch=True, batch_only=False):
    from test_engine_integration import assistant_text, case_plan, planning_response, tool_turn, url_check

    def turn(action, key, **arguments):
        return tool_turn(ToolCall(f"b10-{key}", f"browser.{action}", arguments))

    def count(list_name, expected):
        return {"condition": "count", "locator": css(scoped_card(list_name, fixture["card"])),
                "expected": expected}

    source, destination = fixture["url"], fixture["destinationUrl"]
    batch = turn("click", "move-batch", locators=list(b10_click_targets(fixture)))
    if batch_only:
        return FakeLLM([batch])
    return FakeLLM([
        planning_response(case_plan("B10 cross-board move", [url_check(destination), count(fixture["destination"], 1)])),
        *([batch] if include_batch else []),
        turn("navigate", "return-source", url=source),
        turn("inspect", "confirm-source"),
        turn("navigate", "open-destination", url=destination),
        assistant_text("Verify the persisted destination."),
    ])


def form_replay(fixture, *, batch_only=False):
    from test_engine_integration import assistant_text, case_plan, planning_response, tool_turn

    actions, tile = form_batch(fixture)
    if batch_only:
        return FakeLLM([tool_turn(ToolCall("form-batch", "browser.click", {"locators": list(actions)}))])
    checks = [{"condition": "text_equals", "locator": css('[class*="CardModal_headerTitle__"]'), "expected": fixture["card"]}]
    if fixture["id"] == "B05":
        checks.append({"condition": "count", "locator": css(scoped_card(fixture["list"], fixture["card"])), "expected": 1})
    else:
        checks.append({"condition": "text_equals", "locator": css('button[class*="CardModal_descriptionText__"]'), "expected": TEXT})
    return FakeLLM([
        planning_response(case_plan(f'{fixture["id"]} persisted card', checks)),
        tool_turn(ToolCall("reload-board", "browser.navigate", {"url": fixture["url"]})),
        tool_turn(ToolCall("verify-card", "browser.click", {"locator": css(tile)})),
        assistant_text("Verify persisted card."),
    ])


async def main():
    fixture = json.loads(Path(sys.argv[1]).read_text())
    replays = {"B06": b06_replay, "B10": b10_replay}
    offline = "--offline" in sys.argv[2:] or "--offline-b06" in sys.argv[2:]
    one_shot = "--one-shot" in sys.argv[2:] or "--b10-one-shot" in sys.argv[2:]
    if one_shot and fixture["id"] not in {"B05", "B06", "B10"}:
        raise ValueError("Single-request mode supports only B05, B06 and B10")
    if offline and fixture["id"] not in replays and not one_shot:
        raise ValueError("Offline platform replay supports only B06 and B10")
    harness = runpy.run_path(str(ROOT / "scripts/4gaboards-agent-check.py"))
    short_input = "--short" in sys.argv[2:]
    token_cap = int(os.environ.get("WAATA_ACCEPTANCE_TOKEN_CAP", "0"))
    if token_cap < 0:
        raise ValueError("Token cap cannot be negative")
    target_url = SITE
    if fixture["id"] == "B05":
        fixture.update(list=f'B05 Inbox {fixture["ticket"]}',
                       card=f'B05 Confirm delivery {fixture["ticket"]}')
    if short_input:
        key, ticket, target_url = (fixture[k] for k in ("id", "ticket", "url"))
        if key not in {"B02", "B03", "B04", "B05"} or not re.fullmatch(r"\d{14}", ticket):
            raise ValueError("Short-input smoke requires a B02–B05 fixture")
        if not re.fullmatch(re.escape(SITE) + r"(projects|boards)/\d+", target_url):
            raise ValueError("Invalid local fixture URL")
        _, _, controls, checks = harness["scenario"](key, ticket, target_url)
        selectors = BASE | set(controls) | {s for s, _ in checks}
        if key == "B03":
            # The selected-template placeholder is not a board name field or
            # a valid way to select the option; do not offer it as an action.
            selectors.discard('input[placeholder="Kanban"]')
        goal, expected = {
            "B02": (f"把「B02 Draft Lab {ticket}」改名为「B02 Review Lab {ticket}」。",
                    f"最终回到仪表盘 {SITE}，刷新后两处各显示一个新名称，旧名称消失。"),
            "B03": (f"在这个项目用 Kanban 模板创建看板「B03 Workflow {ticket}」。",
                    "新看板内 Open、Todo、In Progress、To Test、Done 各有一列。"),
            "B04": (f"给这个看板添加列表「B04 Incoming {ticket}」。",
                    "重开同一看板后，同名列表恰好一个。"),
            "B05": (f"在「B05 Inbox {ticket}」新建卡片「B05 Confirm delivery {ticket}」。",
                    "目标列表恰好一张同名卡，打开详情时标题一致。"),
        }[key]
    else:
        goal, expected, selectors = instructions(fixture)
    fixture_env = dotenv_values(ROOT / ".local/4gaboards/.env")
    config = dotenv_values(ROOT / ".env")
    model_id = os.environ.get("WAATA_RUN_MODEL_OVERRIDE") or config["WAATA_MODEL_NAME"]
    raw = json.loads((ROOT / ".local/4gaboards/waata-targets.json").read_text())
    os.environ.update(
        WAATA_ALLOW_HEADFUL="true", WAATA_BOARDS_ADMIN_LOGIN="waataadmin",
        WAATA_BOARDS_ADMIN_PASSWORD=fixture_env["BOARDS_ADMIN_PASSWORD"],
        WAATA_ENGINE_CONFIG=json.dumps({
            "max_browser_actions_per_run": 35, "capture_final_screenshot": True,
            "max_test_cases": 1, "max_model_requests_per_run": 16,
            # TestEngine estimates the untrimmed message history; the wrapper
            # independently caps paid B10 requests on the compacted payload.
            "max_model_tokens_per_run": 1000000 if fixture["id"] == "B10" else 300000,
            "model_retries": 0, "timeout_seconds": 150,
            "observation_settle_seconds": 0.5 if short_input or fixture["id"] in {"B05", "B06", "B10"} else 0,
        }),
    )
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        os.environ.pop(key, None)
    settings = replace(Settings.from_env(), policy=TargetPolicies(
        [TargetPolicy.model_validate(target) for target in raw],
    ), worker_concurrency=1)
    async with httpx.AsyncClient(base_url=GATEWAY, headers={
        "Host": "127.0.0.1:5173", "Origin": "http://127.0.0.1:5173",
    }) as web, OpenAILike(
        base_url=config["WAATA_MODEL_BASE_URL"], api_key=config["WAATA_MODEL_API_KEY"],
        model=model_id, max_output_tokens=1024, timeout=25,
    ) as provider:
        pending = await web.get("/api/v1/test-runs", params={"status": "queued"})
        pending.raise_for_status()
        if any(item["status"] == "queued" for item in pending.json()["items"]):
            raise RuntimeError("Existing queued run; did not start stage 2")
        created = await web.post("/api/v1/test-runs", json={
            "target_url": target_url, "credential_ref": "boards_admin", "goal": goal,
            "expected_behavior": expected, "options": {"headless": False, "max_steps_per_case": 15},
        })
        if created.is_error:
            raise RuntimeError(f"Platform refused stage 2 request: HTTP {created.status_code}")
        run_id = created.json()["run_id"]
        print(f'{fixture["id"]} RUN {run_id}', flush=True)
        stop = asyncio.Event()
        batch_replay = b10_replay if fixture["id"] == "B10" else form_replay
        playback = (batch_replay(fixture, batch_only=True) if one_shot else replays[fixture["id"]](fixture)) if offline else provider
        model = LimitedModel(playback, harness, fixture, settings.policy.sanitize, one_shot=one_shot)
        if short_input:
            model.token_limit = 58000
        if token_cap:
            model.token_limit = min(model.token_limit, token_cap)
        async with open_repository(settings) as repo:
            async def await_terminal():
                try:
                    async with asyncio.timeout(175):
                        while True:
                            row = await repo.get_run(run_id, "local")
                            if row and row["status"] in {"succeeded", "errored", "cancelled"}:
                                return row
                            await asyncio.sleep(0.35)
                finally:
                    stop.set()

            async with asyncio.TaskGroup() as group:
                result = group.create_task(await_terminal())
                group.create_task(run_worker(settings, stop, llm=model))
        row = result.result()
        output = await web.get(f"/api/v1/test-runs/{run_id}/report")
        output.raise_for_status()
        report = output.json()
        summary = {
            "id": fixture["id"], "run_id": run_id, "status": row["status"],
            "model": "FakeLLM" if offline else model_id,
            "short_input": short_input,
            "business_mode": "single_model_authored_batch_with_engine_verification" if one_shot else "agent_loop",
            "verdict": row["verdict"], "requests": model.requests,
            "reported_tokens": model.tokens, "usage_missing": model.unknown,
            "local_stop_reason": model.stop_reason,
            "request_limit": model.request_limit, "token_limit": model.token_limit,
            "elapsed_seconds": (row["finished_at"] - row["started_at"]).total_seconds(),
            "operation_upper_bound": model.actions,
            "screenshots": [a["artifact_id"] for a in report["artifacts"] if a["kind"] == "screenshot"],
        }
        print(json.dumps(summary), flush=True)
        Path(f"/tmp/{run_id}-stage2.json").write_text(json.dumps({
            "fixture": fixture, "metrics": summary, "report": report, "model_turns": model.turns,
        }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
