import asyncio
import json
import unittest
from datetime import UTC, datetime

from waata.artifacts import ArtifactInput, ArtifactRef
from waata.core.model import ChatMessage, ChatResponse, ToolCall
from waata.core.tools import ToolResult
from waata.orchestrator import TestEngine, TestRequest
from waata_test_support.browser import FakeBrowserAdapter
from waata_test_support.model import FakeLLM

_START = "http://fixture.test/start"
_NEXT = "http://fixture.test/next"


class MemoryStore:
    def __init__(self):
        self.inputs = {}

    async def save(self, artifact):
        artifact_id = f"art_{len(self.inputs) + 1}"
        self.inputs[artifact_id] = artifact
        return ArtifactRef(
            artifact_id=artifact_id,
            size_bytes=len(artifact.content),
            **artifact.model_dump(exclude={"content"}),
        )


class NavigatingFixture(FakeBrowserAdapter):
    def __init__(self):
        super().__init__(self.handle, allowed_origins=[_START])
        self.page_url = _START
        self.clicks = []
        self.session = None

    async def open_case(self, target_url, *, credential_ref, artifact_store):
        self.session = await super().open_case(
            target_url, credential_ref=credential_ref, artifact_store=artifact_store
        )
        return self.session

    def page_changed(self):
        self.page_url = _NEXT
        self.session.revision += 1
        self.session.observation_stale = True

    async def handle(self, name, args, context, store):
        if name == "browser.navigate":
            return ToolResult(True, {"action": "navigate", "url": args.url})
        if name == "browser.click":
            self.clicks.append(self.page_url)
            return ToolResult(True, {"action": "click", "url": self.page_url})
        now = datetime.now(UTC)
        if name == "browser.observe":
            result = {
                "observation_id": f"obs_{self.session.revision}",
                "observed_at": now.isoformat(),
                "url": self.page_url,
                "title": "Fixture",
                "aria": '- button "Continue"',
                "elements": [],
                "truncated": False,
            }
        else:
            result = {
                "condition": "url_equals",
                "actual": self.page_url,
                "matched": self.page_url == args.root.expected,
                "url": self.page_url,
                "observed_at": now.isoformat(),
            }
        ref = await store.save(
            ArtifactInput(
                run_id=context.run_id,
                case_id=context.case_id,
                step_id=context.step_id,
                tool_call_id=context.tool_call_id,
                kind="observation",
                mime_type="application/json",
                captured_at=now,
                content=json.dumps(result).encode(),
            )
        )
        return ToolResult(True, {**result, "evidence_ids": [ref.artifact_id]})


class ScriptedModel(FakeLLM):
    def __init__(self, *, delay_first_call: bool):
        plan = {
            "cases": [
                {
                    "name": "Observe fixture navigation",
                    "preconditions": [],
                    "expected_behavior": "The fixture reaches its next page",
                    "checkpoints": [{"condition": "url_equals", "expected": _NEXT}],
                }
            ]
        }
        super().__init__(
            [
                ChatResponse(ChatMessage("assistant", json.dumps(plan))),
                ChatResponse(
                    ChatMessage(
                        "assistant",
                        tool_calls=(
                            ToolCall(
                                "click_1",
                                "browser.click",
                                {
                                    "locator": {
                                        "strategy": "role",
                                        "role": "button",
                                        "name": "Continue",
                                    }
                                },
                            ),
                        ),
                    )
                ),
                ChatResponse(ChatMessage("assistant", "Done")),
            ]
        )
        self.delay_first_call = delay_first_call
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()

    async def chat(self, messages, **kwargs):
        result = await super().chat(messages, **kwargs)
        if self.delay_first_call and len(self.requests) == 2:
            self.waiting.set()
            await self.release.wait()
        return result


class TestEngineContext(unittest.IsolatedAsyncioTestCase):
    async def test_repeat_observation_is_deferred_only_while_page_is_unchanged(self):
        request = TestRequest(
            target_url=_START,
            goal="Inspect the current fixture page",
            expected_behavior="The fixture has loaded",
        )
        for changed in (False, True):
            with self.subTest(changed=changed):
                browser = NavigatingFixture()
                expected = _NEXT if changed else _START
                plan = {
                    "cases": [
                        {
                            "name": "Observe fixture",
                            "preconditions": [],
                            "expected_behavior": "The fixture has loaded",
                            "checkpoints": [
                                {"condition": "url_equals", "expected": expected}
                            ],
                        }
                    ]
                }
                model = FakeLLM(
                    [
                        ChatResponse(ChatMessage("assistant", json.dumps(plan))),
                        ChatResponse(
                            ChatMessage(
                                "assistant",
                                tool_calls=(
                                    ToolCall("observe_once", "browser.observe", {}),
                                ),
                            )
                        ),
                        ChatResponse(ChatMessage("assistant", "Done")),
                    ]
                )
                observations = 0

                async def on_event(event):
                    nonlocal observations
                    if (
                        event.type == "tool.completed"
                        and event.payload["tool"] == "browser.observe"
                    ):
                        observations += 1
                        if changed and observations == 2:
                            browser.page_changed()

                engine = TestEngine(
                    llm=model, browser=browser, artifact_store=MemoryStore()
                )
                result = await engine.run(request, on_event=on_event)
                self.assertEqual(result.verdict, "passed")
                self.assertIn(
                    "browser.observe", {tool.name for tool in model.requests[1].tools}
                )
                self.assertEqual(
                    "browser.observe"
                    in {tool.name for tool in model.requests[2].tools},
                    changed,
                )
                self.assertEqual(observations, 3)

    async def test_stale_click_is_skipped_after_model_wait(self):
        await self.check_stale_click(delay_first_call=True)

    async def test_stale_click_is_skipped_after_progress_callback_wait(self):
        await self.check_stale_click(delay_first_call=False)

    async def check_stale_click(self, *, delay_first_call):
        browser = NavigatingFixture()
        model = ScriptedModel(delay_first_call=delay_first_call)
        engine = TestEngine(llm=model, browser=browser, artifact_store=MemoryStore())

        async def on_event(event):
            if (
                not delay_first_call
                and event.type == "tool.called"
                and event.payload["tool"] == "browser.click"
            ):
                model.waiting.set()
                await model.release.wait()

        request = TestRequest(
            target_url=_START,
            goal="Check the navigation of the fixture",
            expected_behavior="The fixture reaches its next page",
        )
        task = asyncio.create_task(engine.run(request, on_event=on_event))
        try:
            await asyncio.wait_for(model.waiting.wait(), timeout=2)
            self.assertEqual(
                json.loads(model.requests[1].messages[1].content)["state"]["page"][
                    "url"
                ],
                _START,
            )
            browser.page_changed()
        finally:
            model.release.set()
            result = await asyncio.wait_for(task, timeout=2)

        self.assertEqual(browser.clicks, [])
        self.assertEqual(result.verdict, "passed")
        next_messages = model.requests[2].messages
        self.assertEqual(
            json.loads(next_messages[1].content)["state"]["page"]["url"], _NEXT
        )
        self.assertEqual(next_messages[-1].tool_call_id, "click_1")
        self.assertFalse(json.loads(next_messages[-1].content)["success"])
