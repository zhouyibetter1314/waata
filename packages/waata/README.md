# waata · Web App Auto Test Agent

`waata`（Web App Auto Test Agent）是执行 Web 功能测试的独立 Python 包。它为 WAATA（Web App Auto Test App）平台提供测试能力，也可由 Python 脚本或其他服务调用。平台介绍见 [项目 README](../../README.md)。

C2 定义的公共入口 `waata.orchestrator.TestEngine` 使用调用方注入的模型、浏览器、证据存储和可选 Observer。W01 已实现公共请求、报告、配置、错误和事件模型，以及可供 Worker 注入的 `FakeTestEngine`。真实测试执行尚未实现，直接调用 `TestEngine.run` 会明确报告 `CONFIGURATION_ERROR`。

安装、模拟场景、Run ID、预算与回调处理见 [W01 接入说明](W01-HANDOFF.md)。在仓库根目录运行 `uv run --locked --package waata python examples/w01_fake_engine.py`，即可独立验证通过、断言失败、技术错误、部分报告与取消。正式接口见 [C2 契约](../../contracts/waata/c2-waata-python-api.md)。

该包具有独立打包元数据。Playwright 和 Langfuse 接入分别通过 `browser` 和 `observability` 可选依赖安装。包与平台之间的依赖方向见 [系统架构](../../docs/03-architecture.md)。
