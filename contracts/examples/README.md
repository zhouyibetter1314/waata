# 契约示例 · 在 4gaBoards 创建项目

这组离线测试数据展示请求、工具调用、事件、证据和报告如何关联。标识、时间和页面观察均为样本。[平台启动](../../README.md) · [4gaBoards 夹具](../../examples/README.md#4gaboards-组员-a)

样本以本地 4gaBoards v3.2.16 为目标。在独立用例会话中登录专用账号，创建 `Course Test 01`，从新项目页返回仪表盘，检查项目卡片和侧边栏是否均出现。复现时使用实际配置的目标 URL 和凭据集合，授权需要的浏览器操作，确认侧边栏打开且项目名尚未使用。示例集合 `boards_local_fixture` 的字段级引用为 `boards_fixture_login` 和 `boards_fixture_password`，各自绑定到对应的登录输入框。

| 阶段 | 对照样本 |
| --- | --- |
| 提交与排队 | [创建请求](../http/examples/4gaboards-create-run.json) · [202 响应](../http/examples/4gaboards-run-created.json) |
| Worker 调用 | [TestRequest](../waata/examples/4gaboards-test-request.json) · [TestResult](../waata/examples/4gaboards-test-result.json) |
| 执行和检查 | [工具分发与结果](../tools/examples/4gaboards-tool-calls.json) |
| 发布进度 | [SSE 响应体](../events/examples/4gaboards-events.sse) |
| 保存观察 | [证据元数据](../artifacts/examples/4gaboards-artifact-views.json) · [仪表盘](../artifacts/examples/4gaboards-dashboard-observation.json) · [侧边栏](../artifacts/examples/4gaboards-sidebar-observation.json) |
| 查看结果 | [详情](../http/examples/4gaboards-run-detail.json) · [HTTP 报告](../http/examples/4gaboards-report.json) |

两个断言分别引用 `art_4ga_dashboard` 与 `art_4ga_sidebar`。报告与序号 40 的 `report.generated`、序号 41 的 `run.completed` 同时提交。使用 `Last-Event-ID: 40` 重连时收到终态，游标为 `41` 时收到 `204`。

本例以 `succeeded + passed` 结束。登录页回归报告展示流程完成但业务断言失败的 `succeeded + failed`。[登录页回归报告](../http/examples/test-run-report.json)
