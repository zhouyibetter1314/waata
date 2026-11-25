# waata · Web App Auto Test Agent

`waata` 是可独立使用的 Web 功能测试 Python 包。平台 Worker 和其他 Python 调用方通过 `waata.orchestrator.TestEngine` 规划用例、执行浏览器动作、验证检查点并取得报告。[C2 公共接口](../../contracts/waata/c2-waata-python-api.md#2-公共接口)

## 安装与调用

从仓库根目录安装锁定依赖，以及匹配 Playwright 版本的 Chromium。

```bash
uv sync --locked --package waata --extra browser
uv run --locked --package waata --extra browser playwright install chromium
```

调用方创建 `waata.llm.OpenAILike`，启动 Chromium 并传给 `waata.browser.PlaywrightAdapter`，实现或提供 `waata.artifacts.ArtifactStore`。构建 `TestEngine(llm=..., browser=..., artifact_store=...)` 后，异步执行 `engine.run(TestRequest(...), on_event=...)`。可选的事件回调接收 C4 进度，技术错误通过 `WAATAError` 暴露可用的部分结果。[请求与报告](../../contracts/waata/c2-waata-python-api.md) · [证据存储](../../contracts/artifacts/c5-test-evidence-artifacts.md)

调用方负责关闭模型客户端和 Chromium。适配器使用明确授权的 `allowed_origins` 和动作集合，为每个用例创建并关闭独立上下文。依赖 WebSocket 的夹具可在 `allowed_websocket_paths` 登记同源路径。运行生成结构化观察，截图须由策略启用并配置遮罩。[浏览器与证据约束](../../contracts/tools/c3-browser-tools.md)

安装 `observability` extra 后，可传入 `waata.observability.LangfuseObserver(client=...)`。SDK 客户端由调用方持有，退出前执行 `flush()` 或 `shutdown()`。[本地 Langfuse](../../infra/README.md#langfuse)

## 验证

```bash
uv run --locked --package waata --extra browser python -m unittest discover -s packages/waata/tests -v
```

模型与浏览器测试替身位于包的测试目录。集成测试使用本地页面和实际 Chromium。[独立使用验收](../../docs/04-acceptance.md#ac-07-独立使用与可复现性)
