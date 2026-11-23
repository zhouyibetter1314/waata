# C5 · 测试证据与产物契约

## 1. 范围

定义截图、结构化观察、浏览器 Trace 和报告快照的登记、引用和平台读取。WAATA 通过调用方注入的存储接口交付证据。FastAPI 将可移植的元数据投影为 HTTP 引用，并在每次读取时校验调用方权限。相关接口见 [C1](../http/c1-test-run-http-api.md)、[C2](../waata/c2-waata-python-api.md)、[C3](../tools/c3-browser-tools.md) 和 [C4](../events/c4-test-run-events.md)。

## 2. 类型与元数据

| `kind` | `mime_type` | 生产者与内容 |
| --- | --- | --- |
| `observation` | `application/json` | BrowserAdapter，脱敏的 `observe` 或 `inspect` 观察记录 |
| `screenshot` | `image/png` | BrowserAdapter，已遮罩并校验的截图 |
| `playwright_trace` | `application/zip` | 为已脱敏且可安全交付的浏览器 Trace 保留 |
| `test_report` | `application/json` | 为可选的结构化报告快照保留。快照的产物列表排除快照自身 |

内置 BrowserAdapter 生成结构化观察和已启用的截图。Worker 将结构化报告保存至 PostgreSQL，供报告接口读取。证据读取接口支持已登记的上述类型。Langfuse Trace 通过 C2 报告的可空 `langfuse_trace_id` 关联，追踪内容与访问授权由观测系统管理。

| `ArtifactRef` 字段 | 类型 | 约束 |
| --- | --- | --- |
| `artifact_id` | string | 全局唯一的不透明证据标识，由存储层分配 |
| `run_id` | string | 所属 Run ID |
| `case_id`、`step_id`、`tool_call_id` | string 或 null | 在对应范围产生时填充。存在 `step_id` 时必须有 `case_id` |
| `kind`、`mime_type` | string | 按上表配对 |
| `captured_at` | string | 内容采集或生成的 UTC 时间 |
| `size_bytes` | integer | 已登记内容的字节数，非负 |

HTTP 的 `ArtifactView` 增加 `url: string` 和 `expires_at: string | null`。URL 是形如 `/api/v1/artifacts/{artifact_id}` 的同源读取路径。已知失效时间时返回 UTC 值，其余情况返回 `null`。路径、对象存储键、签名、秘密与文件字节留在存储边界。报告和事件使用证据标识及元数据。

## 3. 保存与引用

平台证据元数据的数据库模型和登记边界见 [C6](../database/c6-platform-persistence.md)。

- `ArtifactStore.save(artifact: ArtifactInput) -> ArtifactRef` 是异步能力。`ArtifactInput` 含 `run_id`、`case_id`、`step_id`、`tool_call_id`、`kind`、`mime_type`、`captured_at` 及有界的脱敏内容字节。调用方可提供本地目录或平台存储实现。
- 只有内容可读取且元数据登记成功后才返回引用。失败时回报保存错误，用内部清理处理未登记的文件。C3 使用 `ARTIFACT_WRITE_FAILED`，WAATA 根据已有证据在 C2 报告里表明缺口。收尾和清理遵守 C2 的期限。
- 结构化观察保存所需的脱敏数据及采集上下文，排除记录自身的证据 ID。截图保存完成后再附加其 ID。`inspect` 的有效结论引用本次成功登记的观察。报告中所有证据引用都须来自同一个 Run，并能解析到其 `artifacts` 条目。
- 先登记证据，再在报告或事件中发布引用。用例及步骤上下文来自可信运行时。证据保存失败时不得重放可能已有副作用的浏览器动作。业务断言仍依据当时已有的有效证据判定。

## 4. 授权、保留与脱敏

`GET /api/v1/artifacts/{artifact_id}` 先解析证据所属 Run，再验证调用者权限。成功返回 `200` 和对应 MIME 类型。响应使用 `Cache-Control: private, no-store`。ZIP 和报告快照采用带安全文件名的附件响应。

| 状态 | 错误码 | 触发条件 |
| --- | --- | --- |
| `404` | `ARTIFACT_NOT_FOUND` | ID 未知，或调用者无法访问所属 Run |
| `410` | `ARTIFACT_EXPIRED` | 调用者有权查看该 Run，证据保留期已结束 |
| `503` | `ARTIFACT_UNAVAILABLE` | 调用者有权读取未过期证据，存储暂不可读取 |

证据删除时保留最小的证据元数据和过期记录，直到 Run 被删除，便于历史报告解释引用失效。访问授权先于过期判断。证据不可访问时，报告和历史事件仍可说明采集时的结果。

观察与报告需清除秘密内容和敏感 URL 值。截图遮罩输入与敏感区域。Trace 的校验覆盖其网络记录、页面快照和截图等内容。无法验证脱敏时停用相关采集或丢弃原件，并记录证据缺口。参见 [Playwright Trace Viewer](https://playwright.dev/python/docs/trace-viewer)。

## 5. 示例

4gaBoards 的 [证据元数据示例](examples/4gaboards-artifact-views.json) 包含观察记录及供前端联调的 Playwright Trace 条目。

错误密码用例的一条 `inspect` 观察已登记。报告使用下列 HTTP 证据元数据，断言通过 `evidence_ids: ["art_002"]` 引用它。

```json
{
  "artifact_id": "art_002",
  "run_id": "run_001",
  "case_id": "case_002",
  "step_id": "step_004",
  "tool_call_id": "call_004",
  "kind": "observation",
  "mime_type": "application/json",
  "captured_at": "2026-11-21T01:00:03Z",
  "size_bytes": 204,
  "url": "/api/v1/artifacts/art_002",
  "expires_at": "2026-11-28T01:00:03Z"
}
```

授权用户在保留期后读取该证据，收到 `410 ARTIFACT_EXPIRED`。其他用户访问同一个 ID 时收到 `404 ARTIFACT_NOT_FOUND`。

## 6. 契约验收

| ID | 验证条件 |
| --- | --- |
| C5-AT-01 | MIME 与种类一致，报告和事件中的每个证据 ID 可关联到正确的 Run、用例和步骤 |
| C5-AT-02 | 模拟字节写入和元数据登记失败，确认调用方未收到无效引用，并有可说明的证据缺口 |
| C5-AT-03 | 验证授权下载、越权响应、过期响应和存储不可用响应 |
| C5-AT-04 | 用标记夹具验证观察、截图、Trace 和报告脱敏，检查无法脱敏时未交付原件 |
| C5-AT-05 | 本地存储替身支持独立 Python 调用，平台报告只投影证据元数据与读取地址 |

## 7. 部署配置

平台目前使用 `WAATA_ARTIFACT_ROOT` 指定的本地文件目录。API 和 Worker 共享该目录。`WAATA_ARTIFACT_MAX_BYTES` 可调整各类证据的大小上限，`WAATA_ARTIFACT_RETENTION_SECONDS` 默认保留 `604800` 秒（7 天）。Trace 采集和报告快照导出的评审见 [Q-007](../../docs/05-open-questions.md#q-007-证据和报告)。
