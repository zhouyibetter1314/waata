"""Check existing short-input B02/B05 outcomes with WAATA, without a provider."""

import asyncio
import json
import runpy
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from playwright.async_api import async_playwright
from test_engine_integration import (
    MemoryArtifacts, assistant_text, case_plan, planning_response, url_check,
)
from waata.browser import PlaywrightAdapter
from waata_test_support.model import FakeLLM
from waata.orchestrator import TestEngine, TestRequest
from waata.orchestrator.config import EngineConfig

ROOT = Path("/source")
HOME = "http://127.0.0.1:3000/"


async def main():
    data = json.loads(Path(sys.argv[1]).read_text())
    proof = json.loads(Path(sys.argv[2]).read_text())
    fixture = data["fixture"]
    key = fixture["id"]
    if key not in {"B02", "B05"} or not proof["passed"]:
        raise ValueError("Requires a successful independent B02/B05 check")
    harness = runpy.run_path(str(ROOT / "scripts/4gaboards-agent-check.py"))
    _, expected, controls, counts = harness["scenario"](
        key, fixture["ticket"], fixture["url"]
    )
    target = proof["last_url"]
    assertions = [url_check(target), *[
        {"condition": "count", "locator": {"strategy": "css", "value": selector}, "expected": n}
        for selector, n in counts
    ]]
    if key == "B05":
        assertions.append({
            "condition": "text_equals", "locator": {"strategy": "css", "value": controls[4]},
            "expected": fixture["card"],
        })
    allowed = {a["locator"]["value"] for a in assertions if "locator" in a}
    store = MemoryArtifacts()
    password = dotenv_values(ROOT / ".local/4gaboards/.env")["BOARDS_ADMIN_PASSWORD"]
    run_id = f'{key.lower()}-short-check-{uuid4().hex[:10]}'
    async with async_playwright() as driver:
        browser = await driver.chromium.launch()
        prepared = await harness["prepared_browser"](browser, password, fixture["url"])
        engine = TestEngine(
            llm=FakeLLM([planning_response(case_plan(f"{key} persisted outcome", assertions)),
                         assistant_text("Verify the already saved state.")]),
            browser=PlaywrightAdapter(
                browser=prepared, allowed_origins={HOME}, preferred_css_selectors=allowed,
                allowed_websocket_paths={"/socket.io/"}, allow_screenshots=True,
            ),
            artifact_store=store,
            config=EngineConfig(capture_final_screenshot=True, max_browser_actions_per_run=35),
        )
        result = await engine.run(TestRequest(target_url=target, goal=f"Verify {key}",
                                             expected_behavior=expected), run_id=run_id)
        await browser.close()
    output = Path("/tmp") / run_id
    output.mkdir()
    saved = {"run": result.model_dump(mode="json"), "source_run_id": data["metrics"]["run_id"],
             "independent": proof, "paid_tokens": 0}
    for artifact in result.artifacts:
        suffix = ".png" if artifact.kind == "screenshot" else ".json"
        (output / (artifact.artifact_id + suffix)).write_bytes(store.saved[artifact.artifact_id].content)
    (output / "report.json").write_text(json.dumps(saved, indent=2))
    print(json.dumps({"run_id": run_id, "verdict": result.verdict,
                      "checks": [a.passed for c in result.cases for a in c.assertions]}), flush=True)
    assert result.verdict == "passed"


if __name__ == "__main__":
    asyncio.run(main())
