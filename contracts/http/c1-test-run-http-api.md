# C1 · 测试任务 HTTP API

FastAPI 的请求和响应模型用于生成 OpenAPI 快照，Vue 从快照生成类型。普通消息为 JSON，字段使用 `snake_case`，Run ID 为不透明字符串，时间为 UTC。响应以 `null` 表示缺省的可空值，以 `[]` 表示空列表。[请求和响应模型](../../apps/api/src/waata_api/schemas/test_runs.py) · [OpenAPI 快照](openapi.json)

## 端点

| 方法 | 路径 | 成功响应 |
| --- | --- | --- |
| POST | `/api/v1/test-runs` | `202`，已提交排队记录，返回 `run_id`、`status=queued`、`created_at` |
| GET | `/api/v1/test-runs` | `200`，返回当前主体的 `items`、`page`、`page_size`、`total` |
| GET | `/api/v1/test-runs/{run_id}` | `200`，返回运行状态、进度及报告摘要 |
| GET | `/api/v1/test-runs/{run_id}/events` | `200` SSE，读至终态的游标返回 `204`。[C4](../events/c4-test-run-events.md) |
| GET | `/api/v1/test-runs/{run_id}/report` | `200`，返回最终或部分报告 |
| POST | `/api/v1/test-runs/{run_id}/cancel` | `200` 排队取消，`202` 运行中受理，返回 `run_id`、`status`、`cancellation_requested=true` |
| GET | `/api/v1/artifacts/{artifact_id}` | `200`，返回证据字节及 MIME 类型。[C5](../artifacts/c5-test-evidence-artifacts.md) |

## 创建与查询

| 创建字段 | 约束 |
| --- | --- |
| `target_url` | 必填，已授权的绝对 HTTP(S) URL，URL 内的用户名或密码会被拒绝 |
| `goal`、`expected_behavior` | 必填的非空字符串 |
| `credential_ref` | 可选字符串，默认 `null`。字符串引用此主体及目标已授权的凭据集合 |
| `options.headless` | 可选布尔值，默认 `true`。有界面运行需要 Worker 启用 `WAATA_ALLOW_HEADFUL` 并有可用显示环境 |
| `options.max_steps_per_case` | 可选正整数，默认为 `16`，可信上限默认为 `50`。限额计数见 [C2](../waata/c2-waata-python-api.md) |

省略 `options` 使用默认值。未知字段和命中服务端保密规则的请求内容会被拒绝。

列表使用 `page`（最小和默认均为 `1`）和 `page_size`（默认 `20`，范围 `1–100`），按 `created_at DESC, run_id DESC` 排序。列表项和详情共有 `run_id`、`target_url`、`goal`、`status`、`verdict`、`created_at`、`started_at`、`finished_at`。详情增加以下字段。

| 详情字段 | 含义 |
| --- | --- |
| `expected_behavior` | 脱敏后的预期行为 |
| `progress` | 计划产生前 `total_cases=null`，`completed_cases` 统计已验证的用例 |
| `summary` | 有报告时统计 `passed`、`failed`、`blocked`、`inconclusive` 四种用例，无报告时为 `null` |
| `error` | `errored` 时为 C2 的 `RunError`，其余情况为 `null` |
| `cancellation_requested` | 取消已受理时为 `true` |

`status` 描述 `queued`、`running`、`succeeded`、`errored`、`cancelled` 五个生命周期状态。总体 `verdict` 仅在 `succeeded` 时有值，例如 `succeeded + failed` 表示流程正常完成且有业务断言失败。技术故障保存的部分报告可保留已有用例判定。

报告把 `TestResult` 中的 `ArtifactRef` 转为 `ArtifactView`。运行未结束时报告接口返回 `409 REPORT_NOT_READY`，运行结束但没有报告时返回 `409 REPORT_UNAVAILABLE`。[C2 结果](../waata/c2-waata-python-api.md) · [C5 证据](../artifacts/c5-test-evidence-artifacts.md)

取消无需请求体。排队任务原子提交 `cancelled` 和终态事件。运行中的重复取消复用同一个标记，Worker 清理后提交终态。终态任务返回 `409 RUN_NOT_CANCELLABLE`。并发规则见 [C6](../database/c6-platform-persistence.md)。

## 身份与错误

本机模式识别来自回环连接的配置主体。网关模式校验可信网关令牌和主体标识。两种模式都校验 Host，POST 校验浏览器 Origin，本机模式也允许省略 Origin。运行和证据由创建者访问，目标和凭据按主体授权。[后端配置](../../apps/api/README.md)

失败响应包含 `error.code`、脱敏的 `error.message` 和用于关联日志的 `error.request_id`。HTTP 同时返回 `X-Request-ID`。已受理任务的执行故障由状态、事件和报告表达。

| HTTP | 错误码与条件 |
| --- | --- |
| `400` | 无效请求格式或 POST Origin 为 `INVALID_REQUEST`，非法 SSE 游标为 `INVALID_EVENT_CURSOR` |
| `401` | `UNAUTHENTICATED`，连接、Host 或认证校验失败 |
| `403` | `TARGET_NOT_ALLOWED`、`CREDENTIAL_NOT_ALLOWED`，目标或凭据未授权 |
| `404` | `RUN_NOT_FOUND`、`ARTIFACT_NOT_FOUND`，资源不存在或不可见 |
| `409` | `REPORT_NOT_READY`、`REPORT_UNAVAILABLE`、`RUN_NOT_CANCELLABLE`，当前状态不支持该操作 |
| `410` | `ARTIFACT_EXPIRED`，已授权的证据过期 |
| `422` | `VALIDATION_ERROR`，字段缺失、类型错误、值越界、含不支持字段或触及保密规则 |
| `500` | `INTERNAL_ERROR`，未预期的服务端错误 |
| `503` | `SERVICE_UNAVAILABLE`、`ARTIFACT_UNAVAILABLE`，数据库或证据存储暂不可用 |

## 示例与验证

4gaBoards 示例串起创建请求、状态与报告。登录页回归报告展示 `succeeded + failed`。[4gaBoards 示例](../examples/README.md) · [登录页回归报告](examples/test-run-report.json)

HTTP 测试验证请求、访问、取消、SSE 和报告契约，并比对生成的 OpenAPI 与快照。[HTTP 测试](../../apps/api/tests/test_http_contract.py) · [平台操作验收](../../docs/04-acceptance.md)
