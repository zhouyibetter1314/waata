# 独立调用示意

以下伪代码按 C2 展示如何注入模型、Playwright Browser、证据存储与 Langfuse 客户端。公共接口见 [C2](../contracts/waata/c2-waata-python-api.md)，平台联调数据见 [4gaBoards 端到端示例](../contracts/examples/README.md)。

```python
from waata.browser import PlaywrightAdapter
from waata.llm import OpenAILike
from waata.observability import LangfuseObserver
from waata.orchestrator import TestEngine, TestRequest


async def run_login_check(model_config, browser, artifact_store, langfuse_client):
    engine = TestEngine(
        llm=OpenAILike(**model_config),
        browser=PlaywrightAdapter(
            browser=browser,
            allowed_hosts={"demo-app.test"},
        ),
        artifact_store=artifact_store,
        observability=LangfuseObserver(client=langfuse_client),
    )

    request = TestRequest(
        target_url="https://demo-app.test/login",
        goal="验证演示站点的登录流程",
        expected_behavior="有效凭据进入控制台，错误密码显示约定的提示",
        credential_ref="demo_login_fixture",
    )
    return await engine.run(request)
```

调用方管理注入资源的生命周期，并从测试夹具提供凭据。浏览器适配器管理运行级会话、Trace 和清理。`run()` 完成整次测试，进度可通过 C2 的 `on_event` 回调获取。证据的保存与读取见 [C5](../contracts/artifacts/c5-test-evidence-artifacts.md)。
