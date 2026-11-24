# waata · Web App Auto Test Agent

`waata`（Web App Auto Test Agent）是执行 Web 功能测试的独立 Python 包。它为 WAATA（Web App Auto Test App）平台提供测试能力，也可由 Python 脚本或其他服务调用。平台介绍见 [项目 README](../../README.md)。

C2 定义的公共入口 `waata.orchestrator.TestEngine` 编排测试计划、执行、验证和报告，使用调用方注入的模型、浏览器、证据存储和可选 Observer。首版支持 OpenAI 兼容工具调用、用例内操作历史、隔离的 Chromium 会话和基于证据的确定性检查。 [C2 公共接口](../../contracts/waata/c2-waata-python-api.md#2-公共接口)

Playwright 通过 `browser` extra 安装。首次使用或 Playwright 需要新版浏览器时，安装与锁文件匹配的 Chromium。已有对应版本时可以复用。

```bash
uv run --locked --package waata --extra browser playwright install chromium
```

开发时可独立运行 Python 包测试。

```bash
uv run --locked --package waata --extra browser python -m unittest discover -s packages/waata/tests -v
```

调用方应为受控夹具显式配置 `allowed_origins`，格式为完整的 `scheme://host:port`。每个用例的 BrowserContext 仅访问该用例的目标 origin。默认保存脱敏的结构化观察。截图由调用方针对可校验遮罩的夹具开启，原始 Playwright Trace 当前关闭。

依赖 WebSocket 的测试站点可通过 `allowed_websocket_paths` 显式启用同源路径，例如 4gaBoards 的 `/socket.io/`。默认拦截 WebSocket 连接。

使用 `observability` extra 和 `waata.observability.LangfuseObserver(client=…)` 可将运行元数据提交到 Langfuse。调用方加载实例地址和项目的一对密钥，持有 SDK 客户端，并在退出前调用 `flush()` 或 `shutdown()`。平台 Worker 已接入此生命周期管理。仓库的 `uv.lock` 将 Langfuse Python SDK 固定到兼容 `v4.30.0` 服务端的 v4 系列。 [本地 Langfuse](../../infra/README.md#langfuse) · [系统架构](../../docs/03-architecture.md)
