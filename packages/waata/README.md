# waata · Web App Auto Test Agent

`waata`（Web App Auto Test Agent）是执行 Web 功能测试的独立 Python 包。它为 WAATA（Web App Auto Test App）平台提供测试能力，也可由 Python 脚本或其他服务调用。平台介绍见 [项目 README](../../README.md)。

C2 定义的公共入口 `waata.orchestrator.TestEngine` 编排测试计划、执行、验证和报告，使用调用方注入的模型、浏览器、证据存储和可选 Observer。测试引擎处于实现准备阶段，当前源码保留包和模块边界。接口与调用示意见 [C2 契约](../../contracts/waata/c2-waata-python-api.md)和 [独立调用示例](../../examples/README.md)。

该包具有独立打包元数据。Playwright 和 Langfuse 接入分别通过 `browser` 和 `observability` 可选依赖安装。包与平台之间的依赖方向见 [系统架构](../../docs/03-architecture.md)。
