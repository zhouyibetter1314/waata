import asyncio
import json
import unittest
from dataclasses import replace
from typing import Literal

import httpx
from pydantic import BaseModel, RootModel
from waata.core.agent import AgentHistory, ContextLimitError, agent_step
from waata.core.model import (
    ChatMessage,
    ChatResponse,
    ModelError,
    ModelMetadata,
    ModelResponseError,
    ToolCall,
)
from waata.core.tools import ToolContext, ToolRegistry, ToolResult, ToolSpec
from waata.llm import OpenAILike


class CountArgs(BaseModel):
    count: int


class PageCheck(BaseModel):
    check: Literal["page"]


class TitleCheck(BaseModel):
    check: Literal["title"]


class InspectArgs(RootModel[PageCheck | TitleCheck]):
    pass


async def count(params: CountArgs, context: ToolContext) -> ToolResult:
    return ToolResult(True, {"count": params.count, "run_id": context.run_id})


def tool_response(*calls: ToolCall) -> ChatResponse:
    return ChatResponse(ChatMessage("assistant", tool_calls=calls), "tool_calls")


class OpenAILikeTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_completions_replays_complete_tool_pair(self):
        bodies = []

        def transport(request):
            self.assertEqual(request.url, "https://model.test/v1/chat/completions")
            self.assertEqual(request.headers.get("Authorization"), "Bearer fixture-key")
            body = json.loads(request.content)
            bodies.append(body)
            if len(bodies) == 1:
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "demo_count",
                                                "arguments": '{"count":2}',
                                            },
                                        }
                                    ],
                                },
                            }
                        ],
                        "usage": {"prompt_tokens": 12, "completion_tokens": 5},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "Done"},
                        }
                    ]
                },
            )

        tools = [ToolSpec("demo.count", "Count items", CountArgs, count)]
        registry = ToolRegistry(tools)
        history = AgentHistory()
        context = ToolContext(
            "run_1",
            "case_1",
            "step_1",
            "internal_1",
            asyncio.get_running_loop().time() + 1,
        )

        async def execute(call):
            return await registry.execute(call.name, call.arguments, context)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(transport)
        ) as client:
            llm = OpenAILike(
                base_url="https://model.test/v1",
                model="fixture",
                api_key="fixture-key",
                client=client,
                thinking=False,
            )
            async with llm:
                messages = history.build_messages(
                    "Use provided tools",
                    {"goal": "Count"},
                    tools=tools,
                    metadata=llm.metadata,
                )
                first = await llm.chat(messages, tools=tools)
                self.assertEqual(first.message.tool_calls[0].name, "demo.count")
                self.assertEqual(first.usage.total_tokens, 17)
                self.assertTrue(await agent_step(first, execute, history))
                messages = history.build_messages(
                    "Use provided tools",
                    {"goal": "Count"},
                    tools=tools,
                    metadata=llm.metadata,
                )
                last = await llm.chat(messages, tools=tools)
                self.assertFalse(await agent_step(last, execute, history))
            self.assertFalse(client.is_closed)

        self.assertEqual(bodies[0]["tools"][0]["function"]["name"], "demo_count")
        self.assertEqual(bodies[0]["thinking"], {"type": "disabled"})
        self.assertEqual(bodies[1]["messages"][2]["tool_calls"][0]["id"], "call_1")
        self.assertEqual(bodies[1]["messages"][3]["tool_call_id"], "call_1")
        self.assertEqual(
            json.loads(bodies[1]["messages"][3]["content"])["data"],
            {"count": 2, "run_id": "run_1"},
        )

    async def test_union_schema_has_object_type_on_wire(self):
        def transport(request):
            body = json.loads(request.content)
            self.assertEqual(
                body["tools"][0]["function"]["parameters"]["type"], "object"
            )
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"role": "assistant", "content": "Done"}}]
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(transport)
        ) as client:
            llm = OpenAILike(
                base_url="https://model.test", model="fixture", client=client
            )
            await llm.chat(
                [ChatMessage("user", "Use the checker")],
                tools=[ToolSpec("demo.inspect", "Check page", InspectArgs, count)],
            )

    async def test_retriable_http_error_exposes_status_only(self):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(429, text="private-provider-text")
            )
        ) as client:
            llm = OpenAILike(
                base_url="https://model.test", model="fixture", client=client
            )
            with self.assertRaisesRegex(ModelError, "HTTP 429$") as raised:
                await llm.chat([ChatMessage("user", "Check a fixture")])
        self.assertTrue(raised.exception.retryable)

    async def test_bad_argument_json_is_left_for_tool_rejection(self):
        response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "demo_count",
                                    "arguments": '{"count":1,"count":2}',
                                },
                            }
                        ],
                    }
                }
            ]
        }
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
        ) as client:
            llm = OpenAILike(
                base_url="https://model.test", model="fixture", client=client
            )
            tools = [ToolSpec("demo.count", "Count items", CountArgs, count)]
            result = await llm.chat([ChatMessage("user", "Count")], tools=tools)
        self.assertIsNone(result.message.tool_calls[0].arguments)


class ToolRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_batch_is_sanitized_only_for_model_history(self):
        history = AgentHistory(
            sanitize_message=lambda message: replace(message, content="[redacted]")
        )
        response = ChatResponse(
            ChatMessage(
                "assistant", "fixture marker", (ToolCall("x", "demo.count", {}),)
            )
        )

        async def execute(call):
            self.assertEqual(call.name, "demo.count")
            return ToolResult(True, {"count": 0})

        self.assertTrue(await agent_step(response, execute, history))
        messages = history.build_messages(
            "Use provided tools", {}, tools=[], metadata=ModelMetadata()
        )
        self.assertEqual(messages[2].content, "[redacted]")
        self.assertEqual(messages[3].tool_call_id, "x")

    async def test_rejects_duplicate_ids_before_dispatch(self):
        response = tool_response(
            ToolCall("duplicate", "demo.count", {"count": 1}),
            ToolCall("duplicate", "demo.count", {"count": 2}),
        )

        async def execute(_):
            self.fail("No tool should be dispatched for this malformed response")

        with self.assertRaises(ModelResponseError):
            await agent_step(response, execute, AgentHistory())

    async def test_tool_registry_handles_strict_argument_errors(self):
        registry = ToolRegistry(
            [ToolSpec("demo.count", "Count items", CountArgs, count)]
        )
        context = ToolContext(
            "r", None, None, "id", asyncio.get_running_loop().time() + 1
        )
        for arguments in ({"count": "1"}, {"count": 1, "extra": 0}, None):
            with self.subTest(arguments=arguments):
                result = await registry.execute("demo.count", arguments, context)
                self.assertEqual(result.error.code, "INVALID_ARGUMENTS")
        unknown = await registry.execute("demo.unknown", {}, context)
        self.assertEqual(unknown.error.code, "UNKNOWN_TOOL")

    async def test_compacts_completed_turns_and_keeps_latest_pair_together(self):
        history = AgentHistory(summarize=lambda _, result: {"ref": result.data["ref"]})
        history.append(
            tool_response(ToolCall("old", "demo.first", {})).message,
            [ToolResult(True, {"ref": "old_ref", "details": "x" * 1_600})],
        )
        history.append(
            tool_response(
                ToolCall("current_1", "demo.next", {}),
                ToolCall("current_2", "demo.next", {}),
            ).message,
            [ToolResult(True, {"ref": "ref_1"}), ToolResult(True, {"ref": "ref_2"})],
        )
        messages = history.build_messages(
            "Use provided tools",
            {"checkpoint": "visible"},
            tools=[],
            metadata=ModelMetadata(),
            max_input_tokens=700,
        )
        self.assertEqual(
            [message.role for message in messages],
            [
                "system",
                "user",
                "assistant",
                "tool",
                "tool",
            ],
        )
        self.assertEqual(
            [message.tool_call_id for message in messages[3:]],
            [
                "current_1",
                "current_2",
            ],
        )
        self.assertIn("old_ref", messages[1].content)
        self.assertIn("checkpoint", messages[1].content)
        with self.assertRaises(ContextLimitError):
            history.build_messages(
                "Use provided tools",
                {"checkpoint": "visible"},
                tools=[],
                metadata=ModelMetadata(),
                max_input_tokens=100,
            )
