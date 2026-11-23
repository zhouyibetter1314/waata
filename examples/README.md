# 独立调用示意

以下示例按 C2 注入模型、Chromium Browser 和证据存储。调用方在自己的授权站点选择一个无需登录的页面及预期行为。 [C2 公共接口](../contracts/waata/c2-waata-python-api.md) · [4gaBoards 端到端示例](../contracts/examples/README.md)

```python
from waata.browser import PlaywrightAdapter
from waata.llm import OpenAILike
from waata.orchestrator import TestEngine, TestRequest


async def run_page_check(
    model_config, browser, artifact_store, origin, target_url, goal, expected_behavior
):
    async with OpenAILike(**model_config) as model:
        engine = TestEngine(
            llm=model,
            browser=PlaywrightAdapter(
                browser=browser,
                allowed_origins={origin},
            ),
            artifact_store=artifact_store,
        )
        return await engine.run(
            TestRequest(
                target_url=target_url,
                goal=goal,
                expected_behavior=expected_behavior,
            )
        )
```

`model_config` 至少提供 `base_url` 和 `model`。需认证的供应商还使用调用方加载的 `api_key`。支持 JSON mode 时可设置 `supports_json=True`，DeepSeek 兼容端点可显式设置 `thinking=False`。调用方持有 Browser 和 ArtifactStore，适配器负责每个用例的会话与清理。`run()` 的进度通过 C2 的 `on_event` 获取，可选追踪通过 `observability` 注入。证据的保存与读取见 [C5](../contracts/artifacts/c5-test-evidence-artifacts.md)。
