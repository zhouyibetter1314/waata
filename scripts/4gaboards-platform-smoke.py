"""Run a zero-billing, local-only platform smoke with an injected model."""

import asyncio
import os
import sys

from test_engine_integration import assistant_text, case_plan, planning_response, url_check
from waata.llm import FakeLLM
from waata_api.infrastructure.config import Settings
from waata_api.workers.runtime import run_worker


class VisibleFake(FakeLLM):
    async def chat(self, *args, **kwargs):
        await asyncio.sleep(2)
        return await super().chat(*args, **kwargs)


async def main():
    os.environ.update(
        WAATA_ALLOW_HEADFUL="true",
        WAATA_TARGET_POLICY="/source/.local/4gaboards/waata-targets.json",
        WAATA_ENGINE_CONFIG='{"max_browser_actions_per_run":35,"capture_final_screenshot":true}',
    )
    # No provider or remote tracing is used for this smoke.
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        os.environ.pop(key, None)
    checkpoint = url_check("http://127.0.0.1:3000/login")
    if "--inconclusive" in sys.argv:
        checkpoint = {
            "condition": "text_equals",
            "locator": {"strategy": "test_id", "value": "nonexistent-smoke-checkpoint"},
            "expected": "evidence not available",
        }
    model = VisibleFake([
        planning_response(case_plan("4gaBoards login page", [checkpoint])),
        assistant_text("Login page opened."),
    ])
    stop = asyncio.Event()
    asyncio.get_running_loop().call_later(16, stop.set)
    await run_worker(Settings.from_env(), stop, llm=model)


if __name__ == "__main__":
    asyncio.run(main())
