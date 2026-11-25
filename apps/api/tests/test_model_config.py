"""FR-002: explicit provider thinking configuration keeps NFR-006 budgets."""

import asyncio
import json
import os
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from waata.core.model import ChatMessage
from waata.llm import OpenAILike
from waata.orchestrator.config import EngineConfig
from waata_api.infrastructure.config import Settings
from waata_api.workers import runtime

_BAILIAN = "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"


def load_settings(values, environment=None):
    with (
        patch("waata_api.infrastructure.config.dotenv_values", return_value=values),
        patch.dict(os.environ, environment or {}, clear=True),
    ):
        return Settings.from_env()


class ModelConfigurationTests(unittest.TestCase):
    def test_unset_and_empty_thinking_keep_defaults(self):
        for value in (None, "", "  "):
            values = {} if value is None else {"WAATA_MODEL_ENABLE_THINKING": value}
            with self.subTest(value=value):
                settings = load_settings(values)
                self.assertIsNone(settings.model_enable_thinking)
                self.assertEqual(settings.engine_config, EngineConfig())

    def test_false_setting_is_validated_and_environment_can_override_dotenv(self):
        for value in ("false", "FALSE", " false "):
            settings = load_settings(
                {"WAATA_MODEL_BASE_URL": _BAILIAN, "WAATA_MODEL_ENABLE_THINKING": value}
            )
            self.assertIs(settings.model_enable_thinking, False)
        settings = load_settings(
            {"WAATA_MODEL_BASE_URL": _BAILIAN, "WAATA_MODEL_ENABLE_THINKING": "false"},
            {"WAATA_MODEL_ENABLE_THINKING": ""},
        )
        self.assertIsNone(settings.model_enable_thinking)

    def test_legacy_model_url_fallback_can_use_thinking_setting(self):
        settings = load_settings(
            {
                "DEEPSEEK_BASE_URL": _BAILIAN,
                "DEEPSEEK_MODEL": "fixture",
                "WAATA_MODEL_ENABLE_THINKING": "false",
            }
        )
        self.assertEqual(settings.model_base_url, _BAILIAN)
        self.assertIs(settings.model_enable_thinking, False)

    def test_false_is_compatible_with_existing_provider_overrides(self):
        for url in (
            "https://api.deepseek.com/v1",
            "https://ark.cn-beijing.volces.com/api/v3",
        ):
            settings = load_settings(
                {"WAATA_MODEL_BASE_URL": url, "WAATA_MODEL_ENABLE_THINKING": "false"}
            )
            self.assertIs(settings.model_enable_thinking, False)

    def test_invalid_environment_values_name_the_configuration_field(self):
        for value in ("true", "1", "0", "no", "disabled", "null"):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "WAATA_MODEL_ENABLE_THINKING"),
            ):
                load_settings(
                    {
                        "WAATA_MODEL_BASE_URL": _BAILIAN,
                        "WAATA_MODEL_ENABLE_THINKING": value,
                    }
                )

    def test_unknown_or_lookalike_hosts_are_rejected_for_explicit_setting(self):
        for url in (
            "https://model.test/v1",
            "https://notdashscope.aliyuncs.com/compatible-mode/v1",
            "https://workspace.cn-beijing.maas.aliyuncs.com.evil.test/compatible-mode/v1",
            "https://maas.aliyuncs.com/compatible-mode/v1",
            "https://workspace.unknown.maas.aliyuncs.com/compatible-mode/v1",
            "https://workspace.extra.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        ):
            with (
                self.subTest(url=url),
                self.assertRaisesRegex(ValueError, "WAATA_MODEL_ENABLE_THINKING"),
            ):
                load_settings(
                    {
                        "WAATA_MODEL_BASE_URL": url,
                        "WAATA_MODEL_ENABLE_THINKING": "false",
                    }
                )
        self.assertIsNone(
            load_settings(
                {"WAATA_MODEL_BASE_URL": "https://model.test/v1"}
            ).model_enable_thinking
        )

    def test_invalid_url_and_bailian_path_are_rejected_for_explicit_setting(self):
        for url in (
            "",
            "not-a-url",
            "ftp://dashscope.aliyuncs.com/compatible-mode/v1",
            "https://dashscope.aliyuncs.com/api/v1",
            "https://dashscope.aliyuncs.com/compatible-mode/v1?key=private-value",
        ):
            with (
                self.subTest(url=url),
                self.assertRaisesRegex(
                    ValueError, "WAATA_MODEL_ENABLE_THINKING"
                ) as raised,
            ):
                load_settings(
                    {
                        "WAATA_MODEL_BASE_URL": url,
                        "WAATA_MODEL_ENABLE_THINKING": "false",
                    }
                )
            self.assertNotIn("private-value", str(raised.exception))

    def test_direct_settings_construction_cannot_bypass_validation(self):
        for value in (True, "false", 0):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "WAATA_MODEL_ENABLE_THINKING"),
            ):
                Settings(model_base_url=_BAILIAN, model_enable_thinking=value)


class WorkerModelConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_settings_reach_real_client_without_changing_budgets(self):
        for url, value, expected in (
            (_BAILIAN, "false", {"enable_thinking": False}),
            (_BAILIAN, "", {}),
            ("https://api.deepseek.com/v1", "", {"thinking": {"type": "disabled"}}),
            (
                "https://ark.cn-beijing.volces.com/api/v3",
                "false",
                {"thinking": {"type": "disabled"}},
            ),
        ):
            with self.subTest(url=url, value=value):
                settings = load_settings(
                    {
                        "WAATA_MODEL_BASE_URL": url,
                        "WAATA_MODEL_NAME": "fixture",
                        "WAATA_MODEL_API_KEY": "synthetic-key",
                        "WAATA_MODEL_ENABLE_THINKING": value,
                    }
                )
                bodies, clients, construction = [], [], []

                def transport(request):
                    bodies.append(json.loads(request.content))
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

                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(transport)
                ) as http:

                    def construct(**kwargs):
                        construction.append(kwargs)
                        model = OpenAILike(**kwargs, client=http)
                        clients.append(model)
                        return model

                    @asynccontextmanager
                    async def repository(_settings):
                        yield object()

                    @asynccontextmanager
                    async def playwright():
                        yield object()

                    class IdleWorker:
                        def __init__(self, *_args, **_kwargs):
                            pass

                        async def run(self, _stop):
                            await clients[0].chat(
                                [ChatMessage("user", "Local transport probe")]
                            )

                    artifacts = SimpleNamespace(
                        purge_expired=AsyncMock(), drain=AsyncMock()
                    )
                    with (
                        patch.object(runtime, "OpenAILike", side_effect=construct),
                        patch.object(runtime, "open_repository", repository),
                        patch.object(runtime, "async_playwright", playwright),
                        patch.object(
                            runtime.FileArtifactStore,
                            "from_settings",
                            return_value=artifacts,
                        ),
                        patch.object(runtime, "Worker", IdleWorker),
                    ):
                        await runtime.run_worker(settings, asyncio.Event())
                self.assertEqual(
                    construction,
                    [
                        {
                            "base_url": url,
                            "model": "fixture",
                            "api_key": "synthetic-key",
                            "thinking": False if value == "false" else None,
                        }
                    ],
                )
                self.assertEqual(len(bodies), 1)
                self.assertEqual(
                    {
                        key: bodies[0][key]
                        for key in ("thinking", "enable_thinking")
                        if key in bodies[0]
                    },
                    expected,
                )
                self.assertEqual(bodies[0]["max_tokens"], 2048)
                self.assertEqual(clients[0].metadata.max_output_tokens, 2048)
                self.assertEqual(settings.engine_config, EngineConfig())
                self.assertEqual(
                    settings.engine_config.max_model_tokens_per_run, 200_000
                )
                self.assertEqual(settings.engine_config.max_model_requests_per_run, 48)
                self.assertEqual(settings.engine_config.model_retries, 1)
                artifacts.drain.assert_awaited_once()
