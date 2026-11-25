"""Local five-case verification of already saved Agent results; one model request."""

import asyncio
import json
import os
import re
import runpy
import sys
from dataclasses import replace
from pathlib import Path

from dotenv import dotenv_values
from test_engine_integration import assistant_text, case_plan, planning_response, tool_turn, url_check
from waata.core.model import ChatMessage, ToolCall
from waata.llm import FakeLLM, OpenAILike
from waata_api.infrastructure.config import Settings, TargetPolicies, TargetPolicy
from waata_api.workers.runtime import run_worker

ROOT = Path("/source")
HOME = "http://127.0.0.1:3000/"
ACCEPTANCE = ROOT / ".local/4gaboards/acceptance"
SOURCES = {
    "B02": "b02-agent-25dbd71dcd",
    "B03": "b03-agent-2571c558d7",
    "B04": "b04-agent-102296c5e6",
    "B05": "b05-agent-7e37dfec12",
}


class Playback(FakeLLM):
    def __init__(self, plan, actions, specs):
        super().__init__([plan])
        self.actions = {key: iter(turns) for key, turns in actions.items()}
        self.specs = specs
        self.waited = set()
        self.navigations = dict.fromkeys(specs, 0)

    async def chat(self, messages, **kwargs):
        if not kwargs.get("tools"):
            return await super().chat(messages, **kwargs)
        state = json.loads(messages[1].content)["state"]
        key = state["name"].split()[0]
        scripted = next(self.actions[key], None)
        if scripted is not None:
            return scripted
        target = self.specs[key][0]
        current = (state.get("page") or {}).get("url")
        if key not in self.waited:
            self.waited.add(key)
            await asyncio.sleep(1.1)
            return tool_turn(ToolCall(f"{key}-settle", "browser.observe", {}))
        if current != target and self.navigations[key] < 2:
            self.navigations[key] += 1
            return tool_turn(ToolCall(f"{key}-target-{self.navigations[key]}",
                                     "browser.navigate", {"url": target}))
        await asyncio.sleep(0.7)
        return assistant_text("Verify the persisted outcome.")


def css(value):
    return {"strategy": "css", "value": value}


def count(selector, value):
    return {"condition": "count", "locator": css(selector), "expected": value}


async def main():
    configs = dotenv_values(ROOT / ".env")
    harness = runpy.run_path(str(ROOT / "scripts/4gaboards-agent-check.py"))
    specs = {"B01": (HOME, [url_check(HOME),
        count('[class*="projectTitle"][title="WAATA B01 Live 20261124 F"]', 1),
        count('a[class*="sidebarItemInner"]:has(:text-is("WAATA B01 Live 20261124 F"))', 1),
    ])}
    for key, source in SOURCES.items():
        data = json.loads((ACCEPTANCE / source / "report.json").read_text())
        fixture = data["fixture"]
        _, _, controls, checks = harness["scenario"](key, fixture["ticket"], fixture["url"])
        target = data["independent"]["last_url"]
        if not target.startswith(HOME):
            raise ValueError("Verification only accepts the local target")
        assertions = [url_check(target), *(count(selector, value) for selector, value in checks)]
        if key == "B05":
            assertions.append({"condition": "text_equals", "locator": css(controls[4]),
                               "expected": f'B05 Confirm delivery {fixture["ticket"]}'})
        specs[key] = target, assertions

    usage = None
    reused = len(sys.argv) == 3 and sys.argv[1] == "--reuse-order"
    if reused:
        order = sys.argv[2].split(",")
    else:
        # The model only orders trusted checks; it cannot change the assertions.
        async with OpenAILike(base_url=configs["WAATA_MODEL_BASE_URL"],
                              api_key=configs["WAATA_MODEL_API_KEY"],
                              model="deepseek-v4-pro-ga-260813",
                              max_output_tokens=128, timeout=20) as provider:
            response = await provider.chat((ChatMessage(
                "user", 'Return JSON only: {"order":["B01","B02","B03","B04","B05"]}. '
                "Order the read-only checks by project create, project rename, board template, "
                "list create, card create. Include each ID exactly once; no prose.",
            ),), max_output_tokens=128)
        content = (response.message.content or "").strip()
        match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content, re.S)
        order = json.loads(match[1] if match else content)["order"]
        usage = response.usage
    if not isinstance(order, list) or sorted(order) != sorted(specs):
        raise ValueError("The single model reply did not identify all five checks")
    print(json.dumps({"requests": int(not reused), "order": order,
                      "reported_tokens": None if usage is None else (
                          usage.total_tokens or usage.input_tokens + usage.output_tokens)}), flush=True)

    plans = [case_plan(f"{key} persisted outcome verification", specs[key][1]) for key in order]
    actions = {}
    user = css('input[name="emailOrUsername"]')
    password = css('input[name="password"]')
    for key in order:
        actions[key] = [
            tool_turn(ToolCall(f"{key}-user", "browser.fill", {"locator": user, "secret_ref": "boards_admin_login_ref"}),
                      ToolCall(f"{key}-pass", "browser.fill", {"locator": password, "secret_ref": "boards_admin_pass_ref"})),
            tool_turn(ToolCall(f"{key}-login", "browser.click", {"locator": css('button[type="submit"]')})),
        ]
    fixture = dotenv_values(ROOT / ".local/4gaboards/.env")
    raw = json.loads((ROOT / ".local/4gaboards/waata-targets.json").read_text())
    selectors = {item["locator"]["value"] for _, checks in specs.values()
                 for item in checks if "locator" in item}
    for target in raw:
        target["css_selectors"] = sorted(set(target["css_selectors"]) | selectors)
    os.environ.update(
        WAATA_ALLOW_HEADFUL="true",
        WAATA_BOARDS_ADMIN_LOGIN="waataadmin",
        WAATA_BOARDS_ADMIN_PASSWORD=fixture["BOARDS_ADMIN_PASSWORD"],
        WAATA_ENGINE_CONFIG='{"max_browser_actions_per_run":35,"capture_final_screenshot":true,"max_model_tokens_per_run":1000000}',
    )
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        os.environ.pop(key, None)
    settings = replace(Settings.from_env(), policy=TargetPolicies(
        [TargetPolicy.model_validate(target) for target in raw],
    ))
    stop = asyncio.Event()
    asyncio.get_running_loop().call_later(55, stop.set)
    await run_worker(settings, stop, llm=Playback(planning_response(*plans), actions, specs))


if __name__ == "__main__":
    asyncio.run(main())
