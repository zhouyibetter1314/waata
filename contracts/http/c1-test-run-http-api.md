# C1 · 测试任务 HTTP API 契约

## 1. 范围

定义受控 Web 测试任务的创建、查询、订阅、取消、报告和证据读取。FastAPI 请求与响应模型作为实现来源，导出 `contracts/http/openapi.json` 供前端生成类型。C1 使用 [C2](../waata/c2-waata-python-api.md) 的结果及判定、[C4](../events/c4-test-run-events.md) 的事件和 [C5](../artifacts/c5-test-evidence-artifacts.md) 的证据元数据。

平台排队、状态和报告的数据库事务边界见 [C6](../database/c6-platform-persistence.md)。

## 2. 通用约定

| 项目 | 约定 |
| --- | --- |
| 路径与编码 | 前缀 `/api/v1`，普通消息为 UTF-8 JSON |
| 标识与时间 | `run_id` 为不透明字符串，时间为 ISO 8601 UTC，字段使用 `snake_case` |
| 空值 | 响应保留定义的字段。尚未产生的可空值为 `null`，空集合为 `[]` |
| 权限 | 仅返回调用方有权访问的任务或证据。测试目标和服务端凭据引用均须授权 |
| 脱敏 | 响应、日志和事件不得包含明文密码、Cookie、API Key、凭据引用或敏感 URL 值 |

| `status` | 含义 |
| --- | --- |
| `queued` | 已接收并排队 |
| `running` | Worker 正在处理，可同时有待生效的取消请求 |
| `succeeded` | 测试流程正常完成，最终报告可查询 |
| `errored` | 测试执行或平台处理故障 |
| `cancelled` | 取消已生效，执行已停止并完成必要清理 |

总体 `verdict` 由 C2 计算，取 `passed`、`failed`、`blocked` 或 `inconclusive`。仅 `succeeded` 有总体判定，例如 `succeeded + failed` 表示正常完成测试并发现断言失败。其他状态的总体 `verdict` 为 `null`。错误的部分报告可保留已经确定的用例判定。

## 3. 端点

| 方法 | 路径 | 成功状态与用途 |
| --- | --- | --- |
| POST | `/api/v1/test-runs` | `202`，创建并排队 |
| GET | `/api/v1/test-runs` | `200`，分页列出任务 |
| GET | `/api/v1/test-runs/{run_id}` | `200`，查询详情与进度 |
| GET | `/api/v1/test-runs/{run_id}/events` | `200`，SSE。已读终态的重连返回 `204` |
| GET | `/api/v1/test-runs/{run_id}/report` | `200`，读取结构化报告 |
| POST | `/api/v1/test-runs/{run_id}/cancel` | `202`，受理运行中任务的取消。排队任务立即取消时返回 `200` |
| GET | `/api/v1/artifacts/{artifact_id}` | `200`，按 C5 授权读取证据 |

### 3.1 创建任务

| 请求字段 | 类型 | 约束 |
| --- | --- | --- |
| `target_url` | string | 必填，合法的绝对 HTTP(S) URL。禁止 URL 内嵌用户名或密码，目标须授权 |
| `goal`、`expected_behavior` | string | 必填，非空测试目标与预期行为，传给 C2 |
| `credential_ref` | string 或 null | 可选，默认 `null`。非空值引用服务端为该 Run 授权的测试凭据集合 |
| `options` | object | 可选，缺省时使用默认配置 |
| `options.headless` | boolean | 可选，默认 `true`。Worker 据此选择 Browser |
| `options.max_steps_per_case` | integer | 可选，正整数，继承服务端默认值并受服务端上限约束 |

每用例步骤上限和 C3 的 Run 级浏览器动作上限分别计数，课程计步见 C2。拒绝明文凭据、越界配置及未知字段。排队记录提交后返回 `202`，响应含 `run_id: string`、`status: "queued"`、`created_at: string`。错误响应见第 5 节。

### 3.2 列表与详情

列表支持 `page`（默认 `1`，最小 `1`）和 `page_size`（默认 `20`，范围 `1–100`）。返回 `items: RunSummary[]`、`page: int`、`page_size: int`、`total: int`。在授权范围内统计总数，并按 `created_at`、`run_id` 依次降序排列。

| 模型 | 字段与约束 |
| --- | --- |
| `RunSummary` | `run_id`、`target_url`、`goal`、`created_at` 为字符串，`started_at` 和 `finished_at` 为可空时间，`status` 和可空的 `verdict` 取第 2 节定义的值 |
| `RunDetail` | 继承摘要，另有 `expected_behavior: string`、`progress`、`summary`、`error`、`cancellation_requested: boolean` |
| `progress` | `total_cases: int \| null` 在计划产生前为 `null`。非负 `completed_cases: int` 计算已判定的用例数 |
| `summary` | 无可查询报告时为 `null`，其余情况包含 `passed`、`failed`、`blocked`、`inconclusive` 四项用例计数，未判定的用例不计入 |
| `error` | `errored` 时为 C2 的 `RunError`，其余状态为 `null` |

`target_url`、目标及预期行为均为脱敏展示值。`started_at` 未启动时为 `null`，`finished_at` 进入终态前为 `null`。`cancellation_requested` 初始为 `false`，受理取消后为 `true`。

### 3.3 事件、报告与证据

事件接口的 `text/event-stream` 信封、重放游标及终态见 C4。未建立流时使用第 5 节的 JSON 错误。连接关闭后可查询任务详情。

报告响应采用 C2 的 `TestResult`，将其中的 `ArtifactRef` 投影为 C5 的 `ArtifactView`。进入终态前查询报告返回 `409 REPORT_NOT_READY`。技术故障若已保存部分报告则返回 `200`，总体判定为 `null`。已终止且无报告时返回 `409 REPORT_UNAVAILABLE`，包含取消分支。证据读取返回 C5 定义的内容和 MIME 类型。

### 3.4 取消任务

取消请求无需请求体。返回 `run_id`、`status`、`cancellation_requested`。

| 当前状态 | 处理与响应 |
| --- | --- |
| `queued` | 原子提交取消和终态事件，返回 `200`、`cancelled`、`true` |
| `running` | 登记取消请求，返回 `202`、`running`、`true`。运行中重复提交复用同一取消请求 |
| 终态 | 返回 `409 RUN_NOT_CANCELLABLE` |

取消和完成并发时以提交顺序裁决。如果先受理取消，Worker 应停止执行，并在确认停止和清理后提交 `cancelled`。若取消过程中无法完成必要清理，按技术故障提交 `errored`。前端随后查询详情确认结果。

## 4. 示例

完整的提交、响应和报告见 [4gaBoards 端到端示例](../examples/README.md)。

创建任务的请求体如下。

```json
{
  "target_url": "https://demo-app.test/login",
  "goal": "验证演示站点的登录流程",
  "expected_behavior": "有效凭据进入控制台，错误密码显示约定的提示",
  "credential_ref": "demo_login_fixture",
  "options": {"headless": true, "max_steps_per_case": 30}
}
```

成功排队后返回 `202`。

```json
{
  "run_id": "run_001",
  "status": "queued",
  "created_at": "2026-11-21T00:59:00Z"
}
```

以下为同一夹具在回归站点的任务详情。完整报告含有效凭据和错误密码两个用例。[查看报告 JSON](examples/test-run-report.json)。

```json
{
  "run_id": "run_001",
  "target_url": "https://demo-app.test/login",
  "goal": "验证演示站点的登录流程",
  "expected_behavior": "有效凭据进入控制台，错误密码显示约定的提示",
  "status": "succeeded",
  "verdict": "failed",
  "progress": {"total_cases": 2, "completed_cases": 2},
  "summary": {"passed": 1, "failed": 1, "blocked": 0, "inconclusive": 0},
  "error": null,
  "cancellation_requested": false,
  "created_at": "2026-11-21T00:59:00Z",
  "started_at": "2026-11-21T00:59:02Z",
  "finished_at": "2026-11-21T01:00:04Z"
}
```

## 5. 错误

流建立之前的 HTTP 失败使用统一结构。任务已受理后，执行故障通过任务状态、事件和报告表达。

```json
{
  "error": {
    "code": "RUN_NOT_FOUND",
    "message": "测试任务不存在",
    "request_id": "req_123"
  }
}
```

| HTTP 状态 | 错误码 | 条件 |
| --- | --- | --- |
| `400` | `INVALID_REQUEST`、`INVALID_EVENT_CURSOR` | 无法解析请求格式，或 SSE 游标非法 |
| `401` | `UNAUTHENTICATED` | 调用方缺少有效的平台身份认证 |
| `403` | `TARGET_NOT_ALLOWED`、`CREDENTIAL_NOT_ALLOWED` | 测试目标或凭据引用未获授权 |
| `404` | `RUN_NOT_FOUND`、`ARTIFACT_NOT_FOUND` | 资源不存在或对调用方不可见 |
| `409` | `REPORT_NOT_READY`、`REPORT_UNAVAILABLE`、`RUN_NOT_CANCELLABLE` | 报告或取消与当前状态不相容 |
| `410` | `ARTIFACT_EXPIRED` | 已授权的证据过期 |
| `422` | `VALIDATION_ERROR` | 已解析请求的字段缺失、类型错误、值越界或包含不支持字段 |
| `429` | `TOO_MANY_REQUESTS` | 已配置的限流或并发配额触发 |
| `500` | `INTERNAL_ERROR` | 未预期的服务端错误 |
| `503` | `SERVICE_UNAVAILABLE`、`ARTIFACT_UNAVAILABLE` | 服务或存储暂不可用 |

错误消息须脱敏，`request_id` 用于关联服务日志。FastAPI 的请求校验错误需通过异常处理器映射成上述结构。参见 [FastAPI 错误处理文档](https://fastapi.tiangolo.com/tutorial/handling-errors/#override-request-validation-exceptions)。

## 6. 契约验收

| ID | 验证条件 |
| --- | --- |
| C1-AT-01 | 合法任务返回 `202` 和可查询 Run ID，未授权目标、无效字段和无法解析的请求分别使用约定错误 |
| C1-AT-02 | 查询能区分 `succeeded + failed` 和 `errored + null`，列表仅列出可访问任务 |
| C1-AT-03 | SSE 可重放，前端能从详情恢复并校准终态 |
| C1-AT-04 | 报告可表达最终结果、部分结果及明确的无报告状态，证据访问通过授权检验 |
| C1-AT-05 | 排队取消、运行中受理、重复请求和终态竞争符合约定 |
| C1-AT-06 | FastAPI 生成的 OpenAPI 与快照一致，生成的前端类型通过检查 |

## 7. 部署配置与扩展

部署时配置测试目标与凭据授权。报告导出、筛选、场景管理和批量运行如需扩展，通过契约变更评审。见 [开放问题](../../docs/05-open-questions.md)。
