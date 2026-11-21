# WAATA Python 包

WAATA（Web App Auto Test Agent）是 Web 功能测试框架。C2 定义的公共入口 `waata.orchestrator.TestEngine` 负责测试计划、执行、验证和报告，使用调用方注入的模型、浏览器、证据存储和可选 Observer。

核心包具有独立打包元数据。Playwright 和 Langfuse 接入分别通过 `browser` 和 `observability` 可选依赖安装。当前源目录保留包和模块边界。公共调用方式见[独立调用示意](../../examples/README.md)，职责与依赖方向见[系统架构](../../docs/03-architecture.md)。
