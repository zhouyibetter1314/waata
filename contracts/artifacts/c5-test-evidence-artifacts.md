# C5 · 测试证据

| `kind` | `mime_type` | 内容 |
| --- | --- | --- |
| `observation` | `application/json` | 适配器保存 `observe` 的页面摘要或 `inspect` 的比较记录 |
| `screenshot` | `image/png` | 策略启用时保存截图，遮挡已识别的敏感区域 |
| `playwright_trace` | `application/zip` | 保留的可读取记录类型，内置适配器关闭采集 |
| `test_report` | `application/json` | 保留的可读取记录类型，平台报告保存在 PostgreSQL |

Langfuse 追踪保存在观测系统，以报告中的 `langfuse_trace_id` 关联。平台通过报告接口提供结构化报告。[C1 报告接口](../http/c1-test-run-http-api.md)

## 写入与引用

异步 `ArtifactStore.save(artifact: ArtifactInput) -> ArtifactRef` 传入证据内容字节和采集元数据，内容可读且元数据登记成功后返回引用。失败由浏览器工具报告 `ARTIFACT_WRITE_FAILED`，已有有效证据仍可用于判定。[存储接口](../../packages/waata/src/waata/artifacts.py) · [C3 工具](../tools/c3-browser-tools.md)

平台按 MIME 类型给新证据文件加 `.png`、`.json` 或 `.zip` 后缀。已有记录可用原存储键读取，证据的公开 ID 与访问路径由登记元数据确定。

| `ArtifactRef` | 含义 |
| --- | --- |
| `artifact_id` | 存储层分配的全局不透明 ID |
| `run_id`、`case_id`、`step_id`、`tool_call_id` | 可信运行上下文。除 Run 外可空，步骤级证据必须有用例 ID |
| `kind`、`mime_type` | 按上表配对 |
| `captured_at`、`size_bytes` | UTC 采集时间、实际字节数 |

页面观察保存页面摘要，可以包含同时登记的截图 ID。检查记录保存 `condition`、`actual`、`matched`、`url` 和 `observed_at`，以及该条件使用的预期值或脱敏定位器。两种记录的可信关联范围存入元数据，记录内容省略其自身的证据 ID。工具输出、事件和报告引用已登记 ID，报告断言引用同用例的检查证据。[观察样本](examples/4gaboards-dashboard-observation.json) · [元数据样本](examples/4gaboards-artifact-views.json)

## 读取与保留

`ArtifactView` 在 `ArtifactRef` 上增加同源读取路径 `url=/api/v1/artifacts/{artifact_id}` 和可空的 UTC `expires_at`，内部存储键留在后端。GET 按所属 Run 验证主体，然后检查有效期、文件可读性和字节数。

| HTTP | 结果 |
| --- | --- |
| `200` | 返回证据字节及 MIME。响应采用 `private, no-store` 与 `nosniff`，ZIP 和报告快照以附件下载 |
| `404` | `ARTIFACT_NOT_FOUND`，证据不存在或所属 Run 不可访问 |
| `410` | `ARTIFACT_EXPIRED`，已授权且过期 |
| `503` | `ARTIFACT_UNAVAILABLE`，未过期的证据暂不可读或大小与登记不符 |

API 与 Worker 共享 `WAATA_ARTIFACT_ROOT`。`WAATA_ARTIFACT_MAX_BYTES` 配置各类证据大小限制，`WAATA_ARTIFACT_RETENTION_SECONDS` 默认 604800 秒（7 天），以平台登记时钟起算。Worker 回收过期文件后保留元数据，历史报告仍可显示证据关联。[文件存储](../../apps/api/src/waata_api/infrastructure/artifacts.py) · [数据库边界](../database/c6-platform-persistence.md) · [证据验收](../../docs/04-acceptance.md#ac-04-报告与证据)
