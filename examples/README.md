# 独立调用示意

以下是供 C2 评审的伪代码，展示如何注入模型、Langfuse 客户端与 Playwright Browser。类名、签名和返回结构待团队共同确认。

```python
from waata.browser import PlaywrightAdapter
from waata.llm import OpenAILike
from waata.observability import LangfuseObserver
from waata.orchestrator import TestEngine, TestRequest


async def run_login_check(model_config, browser, langfuse_client):
    engine = TestEngine(
        llm=OpenAILike(**model_config),
        browser=PlaywrightAdapter(
            browser=browser,
            allowed_hosts={"demo-app.test"},
        ),
        observability=LangfuseObserver(client=langfuse_client),
    )

    request = TestRequest(
        target_url="http://demo-app.test",
        goal="验证演示站点登录。有效凭据进入控制台，错误密码显示约定的提示。",
    )
    return await engine.run(request)
```

`browser` 和 `langfuse_client` 由调用方创建并关闭。浏览器适配器负责运行级会话、Trace 和清理。模型配置和假账号凭据由调用环境或测试夹具提供。拟议的 `run()` 完成整次测试，事件接口及其与 `run()` 的关系见[契约目录](../contracts/README.md)。
