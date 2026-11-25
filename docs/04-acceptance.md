# 04 本地验收

启动 PostgreSQL、FastAPI、Worker 和 Vue。选择经授权的测试站点，准备可重置的数据和专用账号，在目标策略登记 origin、所需动作和凭据引用。记录 WAATA 修订、应用版本、模型、运行配置、Run ID 和实际判定。[平台启动](../apps/api/README.md#本地启动与目标配置) · [可选场景](../examples/README.md)

## AC-01 提交与规划

从 `/runs/new` 提交目标地址、测试目标和预期行为。核对 HTTP `202` 和可查询的 `run_id`。运行开始后检查 `plan.created`，报告中核对用例目标、前置条件、预期行为与检查点的关联。[C1](../contracts/http/c1-test-run-http-api.md) · [C2](../contracts/waata/c2-waata-python-api.md)

## AC-02 受控站点执行

对照用例目标，核对报告中的工具结果、实际页面 URL 和观察证据。通过依赖登录态的夹具验证两个用例使用独立浏览器会话。[C3](../contracts/tools/c3-browser-tools.md)

## AC-03 断言与失败归因

| 场景 | 运行状态与判定 | 复核 |
| --- | --- | --- |
| 所有用例有证据且符合预期 | `succeeded` + `passed` | 断言关联可读的同用例证据 |
| 有用例证实断言不符且该用例未被策略阻止 | `succeeded` + `failed` | 报告可对照预期值与实际值 |
| 无失败用例，至少一个用例受阻 | `succeeded` + `blocked` | 报告保留阻止原因 |
| 无失败或受阻用例，证据不足以判定通过 | `succeeded` + `inconclusive` | 报告体现无法判定的检查点 |
| 浏览器或模型发生终止性技术错误 | `errored` + 空判定 | 详情包含错误码，可用的部分报告仍可查询 |

## AC-04 报告与证据

按 Run ID 打开报告，核对用例、步骤、断言和异常，再通过引用读取该运行的结构化观察。验证启用截图时的预览和遮罩。如果配置了 Langfuse，用 `langfuse_trace_id` 查找对应的运行及模型、工具和判定元数据。[C5](../contracts/artifacts/c5-test-evidence-artifacts.md)

## AC-05 平台端到端

1. 从运行列表打开详情，检查状态和时间线。断开并恢复连接，验证 `Last-Event-ID` 或 `after` 只补读游标后的事件，界面各显示一次。已有终态且游标已读完时，SSE 返回 `204`。
2. 分别取消排队与运行中的任务。前者直接进入 `cancelled`，后者先受理，运行清理成功后再进入 `cancelled`。每次运行只提交一个终态事件。
3. 重启 API 和 Worker，保留数据库和证据目录，确认历史详情、事件、报告及未过期证据仍可查询。
4. 在 `/scenarios` 创建应用并保存或导入场景，从列表提交选中项，核对每项产生独立的 Run。刷新后核对本地模板仍可查询。

[C1](../contracts/http/c1-test-run-http-api.md) · [C4](../contracts/events/c4-test-run-events.md) · [C6](../contracts/database/c6-platform-persistence.md)

## AC-06 错误与资源边界

- 在本地夹具验证未授权 origin 不能提交，执行阶段也遵守目标和动作策略。在报告、观察和启用的追踪中检查测试秘密标记是否已处理。
- 分别验证模型不可用、浏览器故障、超时、取消和租约丢失。核对终止原因、已提交的历史和浏览器资源清理。
- 降低运行预算与 Worker 并发配置，核对时间、用例、步骤、动作、工具尝试、模型用量和并发边界。比较并发 Run 及同一 Run 各用例的会话状态。

[后端运行设置](../apps/api/README.md#运行设置) · [C2](../contracts/waata/c2-waata-python-api.md)

## AC-07 独立使用与可复现性

从 Python 直接调用 `TestEngine`，注入真实模型、浏览器和证据存储，在同一版本的本地夹具上执行。重置该夹具后复跑，以前置条件、有效配置和证据引用核对结果。核心流程也有独立的自动化测试。[Python 包](../packages/waata/README.md) · [C2](../contracts/waata/c2-waata-python-api.md#2-公共接口)
