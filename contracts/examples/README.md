# 端到端示例 · 在 4gaBoards 创建项目

## 测试输入

| 项目 | 内容 |
| --- | --- |
| 本地地址 | `http://localhost:3000/` |
| 测试目标 | 在本地 4gaBoards 创建名为 Course Test 01 的项目 |
| 预期行为 | 创建完成后，仪表盘和侧边栏均显示 Course Test 01 |
| 测试夹具 | 使用 4gaBoards v3.2.16、英文桌面界面和专用测试账号。侧边栏保持打开，项目名尚未使用 |
| 授权与凭据 | 明确授权该本地站点和创建项目操作。凭据引用 `boards_local_fixture` 对应一个为本次运行准备的已登录会话 |

测试目标位于 [本地测试站点](../../testsites/README.md)。C3 示例中的 CSS 定位器由受信配置允许。重复测试时重置测试数据，或在目标、预期和夹具中使用另一个唯一名称。

## 从提交到查看结果

| 阶段 | 运行行为 | 对应示例 |
| --- | --- | --- |
| **C1 · 提交任务** | 用户在 Vue 填写目标地址、自然语言目标及预期。FastAPI 校验后排队，返回 `202` 和 `run_4gaboards_001` | [HTTP 请求](../http/examples/4gaboards-create-run.json) · [排队响应](../http/examples/4gaboards-run-created.json) |
| **C2 · 调用独立包** | Worker 选择 Browser，注入依赖，并调用 `TestEngine.run(request, run_id=run_id, on_event=store_event)`。引擎规划一个用例 | [TestRequest](../waata/examples/4gaboards-test-request.json) · [TestResult](../waata/examples/4gaboards-test-result.json) |
| **C3 · 操作和检查** | 浏览器打开仪表盘，填写项目名并提交。Verifier 分别检查仪表盘项目卡片和侧边栏入口是否可见 | [六次工具调用及结果](../tools/examples/4gaboards-tool-calls.json) |
| **C4 · 发布进度** | Worker 接收进度、编号并保存事件，FastAPI 通过 SSE 推送。断线重连携带 `Last-Event-ID`，例如 `10`，服务端从序号 `11` 补发 | [完整 SSE 响应体](../events/examples/4gaboards-events.sse) |
| **C5 · 保存证据** | 两条结构化观察分别登记，用证据 ID 关联断言。Playwright Trace 随运行收尾登记，授权用户可从报告里的链接读取 | [证据元数据](../artifacts/examples/4gaboards-artifact-views.json) · [仪表盘观察](../artifacts/examples/4gaboards-dashboard-observation.json) · [侧边栏观察](../artifacts/examples/4gaboards-sidebar-observation.json) |
| **C1 · 查看结果** | Worker 保存报告并提交终态。Vue 展示运行完成、用例通过和两条断言证据 | [任务详情](../http/examples/4gaboards-run-detail.json) · [HTTP 报告](../http/examples/4gaboards-report.json) |

最终结果为 `status=succeeded`、`verdict=passed`。仪表盘断言引用 `art_4ga_dashboard`，侧边栏断言引用 `art_4ga_sidebar`。Trace 条目展示 ZIP 的元数据与读取路径。该示例的 `langfuse_trace_id` 为 `null`，表示未接入可选的 Langfuse 观测。

## 历史记录与示例来源

旧项目 `WebAppAutoTestAgent` 在同一地址对 4gaBoards 3.2.16 实测了创建 Course Test 01 的场景。旧报告 `.waat/runs/74f2ba4fdad54c93a881a25198240e8c/report.json` 记录了 `completed / PASS`，使用了 7 次浏览器操作并保留了 Trace。

本目录将该场景改写为 WAATA v0.1 的联调数据。示例中的标识、时间戳、工具序列、报告及 Trace 元数据用于说明新契约，运行文件由实际服务生成。本例的端点和文件路径供 Mock 与契约测试使用。
