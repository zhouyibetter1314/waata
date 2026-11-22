# C4 · 测试运行事件契约

## 1. 范围

定义 Python 回调事件、平台发布信封、事件类型与 SSE 重放规则。[C2](../waata/c2-waata-python-api.md) 定义回调与判定，[C3](../tools/c3-browser-tools.md) 定义工具结果，[C5](../artifacts/c5-test-evidence-artifacts.md) 定义证据引用，[C1](../http/c1-test-run-http-api.md) 定义 HTTP 端点和错误。

## 2. 信封

WAATA 向回调提交 `TestEvent`。平台持久化时添加 `sequence`，形成供 SSE 传输和重放的发布信封。Worker 自己产生的生命周期和报告事件使用同一信封。

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `schema_version` | integer | 本版为 `1` |
| `event_id` | string | 由生产方生成的不透明事件标识，同一事件重试时保持稳定 |
| `run_id` | string | 与平台任务及 WAATA 执行使用的 Run ID 相同 |
| `sequence` | integer | 平台发布字段。同一 Run 从 `1` 开始按持久化顺序连续递增，最大为 JavaScript 安全整数 |
| `type` | string | 事件名，见下表 |
| `timestamp` | string | 事件发生时间，ISO 8601 UTC。排序使用 `sequence` |
| `case_id`、`step_id` | string 或 null | 无对应范围时为 `null`。有步骤时必须带用例 ID |
| `payload` | object | 必有对象，按事件类型校验 |

Worker 以 `(run_id, event_id)` 幂等写入，并在同一事务内为新事件分配序号。重试复用已提交序号。同一标识收到不同内容时拒绝写入并记录故障。前端按 Run 和 `sequence` 去重及排序。

## 3. 事件类型

| `type` | 生产者 | 关联范围 | `payload` 字段 |
| --- | --- | --- | --- |
| `run.started` | Worker | Run | `{}` |
| `plan.created` | Planner | Run | `total_cases: int`，非负 |
| `case.started` | Runner | Case | `name: string` |
| `agent.step.started` | Agent | Step | `summary: string \| null`，短行动摘要 |
| `tool.called` | Tool Executor | 调用上下文 | `tool_call_id: string`、`tool: string` |
| `tool.completed` | Tool Executor | 同上 | `tool_call_id`、`tool`、`success: bool`、`duration_ms: int`、`error_code: string \| null`、`evidence_ids: string[]` |
| `case.verified` | Verifier | Case | `verdict`，C2 的用例判定 |
| `report.generated` | Worker | Run | `artifact_id: string \| null`，可选报告快照的引用。结构化报告已可查询 |
| `run.completed` | Worker | Run | `status: "succeeded"`、`verdict` 为 C2 的总体判定、`error: null` |
| `run.failed` | Worker | Run | `status: "errored"`、`verdict: null`、`error: RunError` |
| `run.cancelled` | Worker | Run | `status: "cancelled"`、`verdict: null`、`error: null` |

Run 级的 `case_id` 和 `step_id` 均为 `null`。Case 级需要 `case_id`，`step_id=null`。Step 级需要两个标识。工具事件沿用 C3 的可信调用上下文，两端通过 `tool_call_id` 配对。该 ID 在 Run 内唯一。工具成功时 `error_code=null`，失败时使用 C3 错误码。工具耗时为非负整数毫秒。取消或故障可能留下未配对的 `tool.called`。证据先登记，再通过 `evidence_ids` 发布。

## 4. 持久化与终态

数据库中的事件序号、幂等写入与终态提交遵循 [C6](../database/c6-platform-persistence.md)。

- Worker 领取任务时一起写入 `running` 与 `run.started`。每个 Run 恰好提交一个终态事件，排队取消可以直接提交 `run.cancelled`。
- Worker 在同一次提交中保存终态及可用报告，并追加相应事件。有报告时 `report.generated` 的序号排在终态事件之前。接收 `report.generated` 时对应报告已经可查询，`artifact_id` 可引用已登记的报告快照。
- 若报告无法保存，Worker 使用 `REPORT_WRITE_FAILED` 并发布 `run.failed`，保留已有的原始诊断。若事件存储不可用，Worker 保留故障信息，恢复后补交终态。终态与其事件同一提交，已入库事件才可推送。
- `run.completed` 可携带 `verdict=failed`。运行进入终态后停止发布新事件。Vue 通过详情接口校准最终状态。
- 事件仅包含允许展示的摘要、标识和错误码。原始工具参数、凭据值及凭据引用、Cookie、API Key、原始模型推理和未经脱敏的页面内容不进入发布信封。

## 5. SSE 与重放

`GET /api/v1/test-runs/{run_id}/events` 按 C1 校验权限。SSE 采用 UTF-8。每个事件的 `id:` 使用十进制 `sequence`，`event:` 使用 `type`，`data:` 放完整 JSON 信封，以空行结束。保活使用注释 `: keep-alive` 加空行。

游标优先取非空的 `Last-Event-ID`，其次取查询参数 `after`，两者均缺省时为 `0`。合法游标为不大于当前已提交最大序号的非负十进制整数。服务端先补发所有 `sequence > cursor` 的历史事件，再续发新提交的事件。历史读取与实时跟随的切换必须保证没有遗漏。只要 Run 仍可查询，就保留其发布流以支持重放。

收到终态后前端关闭连接。服务端发送终态后结束本次流，若重连的游标已覆盖终态，则返回 `204 No Content` 终止自动重连。游标错误在建立流前返回 `400 INVALID_EVENT_CURSOR`。前端收到流错误时可查询详情并从已知游标补读，或重建该 Run 的时间线后从 `0` 重放。连接中断只说明传输中断。

参见 [WHATWG HTML 的 SSE 规范](https://html.spec.whatwg.org/multipage/server-sent-events.html)。

## 6. 示例

4gaBoards 场景从开始到终态的所有事件见 [SSE 响应体](examples/4gaboards-events.sse)。

一次对错误密码提示的观察成功完成，并已保存结构化证据。工具的成功表示成功取得观察，断言不匹配由后续的 `case.verified` 表达。

```text
id: 17
event: tool.completed
data: {"schema_version":1,"event_id":"evt_000017","run_id":"run_001","sequence":17,"type":"tool.completed","timestamp":"2026-11-21T01:00:03Z","case_id":"case_002","step_id":"step_004","payload":{"tool_call_id":"call_004","tool":"browser.inspect","success":true,"duration_ms":120,"error_code":null,"evidence_ids":["art_002"]}}

```

若客户端已应用序号 `17` 并断线，携带 `Last-Event-ID: 17` 重连只收到序号大于 `17` 的事件。若 Worker 之前仅提交到 `17`，收到游标 `99` 时返回 `400 INVALID_EVENT_CURSOR`。模型服务中断时，流以 `run.failed` 结束，错误码为 `MODEL_UNAVAILABLE`。

## 7. 契约验收

| ID | 验证条件 |
| --- | --- |
| C4-AT-01 | 回调及发布信封字段可校验，Case、Step、工具调用和证据可正确关联 |
| C4-AT-02 | 重试复用事件 ID 与序号，同一 Run 顺序连续，多个 Run 的序号相互独立 |
| C4-AT-03 | 首次订阅、刷新和断线重连无遗漏，重复记录不重复应用，保活不改变游标 |
| C4-AT-04 | 业务断言失败、技术故障和取消分别产生唯一的正确终态，收到 `report.generated` 时可查询报告 |
| C4-AT-05 | 已读终态的重连返回 `204`，未来游标返回 `400`，公开事件通过脱敏检查 |

## 8. 部署配置

部署时配置保活间隔、事件存储与异常恢复策略。破坏性协议变更由生产方和消费方共同评审。见 [Q-003 和 Q-009](../../docs/05-open-questions.md)。
