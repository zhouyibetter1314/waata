# WAATA 跨模块契约

| 契约 | 边界 | 来源 |
| --- | --- | --- |
| [C1 · HTTP](http/c1-test-run-http-api.md) | Vue 调用 FastAPI 创建、查询和取消任务，查看报告 | [OpenAPI 快照](http/openapi.json) · [路由](../apps/api/src/waata_api/api/v1/endpoints/test_runs.py) |
| [C2 · Python](waata/c2-waata-python-api.md) | Worker 或 Python 调用方运行 `TestEngine` | [公共入口](../packages/waata/src/waata/orchestrator/__init__.py) |
| [C3 · 浏览器工具](tools/c3-browser-tools.md) | Agent 与 Playwright 会话交换操作和观察结果 | [输入模型](../packages/waata/src/waata/browser/models.py) |
| [C4 · 运行事件](events/c4-test-run-events.md) | WAATA 回调、Worker 编号、FastAPI SSE、Vue 重放 | [回调模型](../packages/waata/src/waata/core/events.py) · [SSE 实现](../apps/api/src/waata_api/services/run_events.py) |
| [C5 · 证据](artifacts/c5-test-evidence-artifacts.md) | 浏览器保存证据，平台生成受控读取路径 | [存储接口](../packages/waata/src/waata/artifacts.py) |
| [C6 · 持久化](database/c6-platform-persistence.md) | API、Worker 和 PostgreSQL 管理排队、租约、事件与报告 | [SQL 迁移](../migrations/README.md) |

联调时以代码和生成的 schema 核对字段，变更时同步更新实现、快照和测试。[协作规约](../CONTRIBUTING.md) · [架构](../docs/03-architecture.md)

[4gaBoards 示例](examples/README.md)是供离线契约校验和自动化测试使用的样本。实际运行请配置授权目标并启动平台。[启动和目标配置](../apps/api/README.md)
