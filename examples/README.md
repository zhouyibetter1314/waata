# 独立调用示意

以下示例按 C2 注入模型、Chromium Browser、证据存储和登录夹具。`origin` 是测试团队授权的夹具 origin，两个密码由调用方从本地测试配置加载。公共接口见 [C2](../contracts/waata/c2-waata-python-api.md)，平台联调数据见 [4gaBoards 端到端示例](../contracts/examples/README.md)。

```python
from waata.browser import CredentialField, PlaywrightAdapter
from waata.llm import OpenAILike
from waata.orchestrator import TestEngine, TestRequest


async def run_login_check(
    model_config, browser, artifact_store, origin, valid_password, invalid_password
):
    password_field = {"strategy": "label", "value": "Password"}
    async with OpenAILike(**model_config) as model:
        engine = TestEngine(
            llm=model,
            browser=PlaywrightAdapter(
                browser=browser,
                allowed_origins={origin},
                credential_sets={
                    "demo_login_fixture": {
                        "demo.valid": CredentialField(valid_password, password_field),
                        "demo.invalid": CredentialField(invalid_password, password_field),
                    },
                },
            ),
            artifact_store=artifact_store,
        )
        return await engine.run(
            TestRequest(
                target_url=f"{origin}/login",
                goal="验证演示站点的登录流程",
                expected_behavior=(
                    "有效密码进入 /dashboard 且显示 Signed in，"
                    "错误密码留在 /login 且显示 Wrong password"
                ),
                credential_ref="demo_login_fixture",
            )
        )
```

`model_config` 至少提供 `base_url` 和 `model`。需认证的供应商还使用调用方加载的 `api_key`。支持 JSON mode 时可设置 `supports_json=True`，DeepSeek 兼容端点可显式设置 `thinking=False`。调用方持有 Browser 和 ArtifactStore，适配器负责每个用例的会话与清理。`run()` 的进度通过 C2 的 `on_event` 获取，可选追踪通过 `observability` 注入。证据的保存与读取见 [C5](../contracts/artifacts/c5-test-evidence-artifacts.md)。
