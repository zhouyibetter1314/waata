# C6 · 平台持久化契约

## 1. 范围

WAATA v0.1 的 FastAPI 后端与 Worker 使用 **PostgreSQL 17** 保存运行任务、事件、报告和证据元数据。本地开发和数据库验收使用 `postgres:17`。Vue 通过 C1、C4、C5 读取平台数据，独立 `waata` 包通过 C2 接收执行参数及注入的存储能力。事件与报告的公开格式继续以 [C4](../events/c4-test-run-events.md) 和 [C2](../waata/c2-waata-python-api.md) 为准。

截图、观察文件、Playwright Trace 和可选报告快照由 [C5 ArtifactStore](../artifacts/c5-test-evidence-artifacts.md) 保存字节。PostgreSQL 保存可查询元数据和内部存储键。Langfuse 追踪保留在观测系统，通过报告中的 `langfuse_trace_id` 关联。

## 2. 数据模型

下面是首版关系模型。Run ID 与证据 ID 沿用现有契约的不透明字符串。数据库时间戳采用 `timestamptz`，HTTP 和 SSE 继续输出 UTC。完整的字段、键、索引及同行约束见 [PostgreSQL 参考 DDL](examples/schema.sql)。

| 表 | 主键及关系 | 保存内容 |
| --- | --- | --- |
| `test_runs` | `run_id` 主键，`owner_id` 为服务端认定的授权主体标识 | 经 C1 校验的请求、内部凭据引用、状态、判定、错误、进度、取消标记、时间戳及 Run 内事件计数器 |
| `run_events` | `(run_id, sequence)` 主键，`(run_id, event_id)` 唯一，`run_id` 外键 | C4 信封的版本、类型、发生时间、Case/Step 关联和 JSONB 载荷 |
| `run_reports` | `run_id` 为主键和外键 | 一次运行的一份最终或部分 C2 结果，按 JSONB 快照保存，带提交时间 |
| `run_artifacts` | `artifact_id` 全局主键，`run_id` 外键 | C5 元数据、Case/Step/工具调用关联、私有存储键、过期时间和删除记录 |

- `test_runs.request` 保存执行所需的目标 URL、目标、预期行为和选项。`credential_ref` 单独持久化为受信凭据解析器使用的不透明引用。任务查询返回脱敏展示值，事件、报告及公开元数据采用各自契约的字段投影。
- `status` 与 `verdict` 分开保存。只有 `succeeded` 有总体判定，只有 `errored` 有结构化错误。终态填写 `finished_at`，排队取消时 `started_at` 可为 `null`。报告中的用例判定继续遵循 C2。
- `run_reports.result` 使用 C2 的可移植结果，包含用例、步骤、断言和证据引用。C1 在读取时补充 C5 的同源 URL 和有效期。按关联 Run 校验证据归属和报告内容，跨表约束由写入事务负责。参见 [PostgreSQL 17 约束文档](https://www.postgresql.org/docs/17/ddl-constraints.html)。
- C1 列表在授权过滤后排序、分页和统计总数。默认按 `created_at DESC, run_id DESC` 查询。包含额外访问授权时，由后端用完整的授权规则确定可见范围。

## 3. 排队、取消与事务

| 操作 | 提交边界 |
| --- | --- |
| 创建 | 在一次事务中保存并排队 Run，提交后返回 C1 的 `202`。首版使用处于 `queued` 的 PostgreSQL 记录作为持久化待办，Worker 重启后能继续领取这些记录 |
| 领取 | 并发 Worker 对同一 Run 只有一个领取成功。期望状态为 `queued`，原子写入 `running`、`started_at` 与 `run.started`，提交后才启动浏览器执行 |
| 排队取消 | 同一次提交设置取消标记、`cancelled`、`finished_at` 并追加 `run.cancelled`，随后返回 `200` |
| 运行中取消 | 持久化 `cancellation_requested=true` 后返回 `202`。重复请求复用该标记。Worker 停止并清理后才提交 `cancelled`，清理失败提交 `errored` |
| 完成或故障 | 终态、总体判定或错误、`finished_at`、可用报告和对应事件在同一事务提交。有报告时先追加 `report.generated`，再追加唯一终态事件 |

取消和完成对同一 Run 串行处理。持锁确认最新状态与取消标记后提交，胜负取决于提交顺序。终态完成先提交时，后来的取消返回 C1 的 `409 RUN_NOT_CANCELLABLE`。取消标记先提交时，完成方遵循 C2 的停止与清理规则，报告按 C1/C4 的终态语义发布。报告无法写入时记录 `REPORT_WRITE_FAILED`。事件、状态与报告的事务失败时回滚，按 C4 在存储恢复后收敛到可查询的终态。

事务保持短小，网络、模型、浏览器和外部文件存储操作在事务之外执行。Worker 失效后的恢复必须先确认旧执行已停止或阻止旧执行继续写入，再将失去执行者的 Run 收敛为技术错误。恢复过程保留已提交的事件与证据，并避免自动重放可能已产生副作用的浏览器动作。存活判定和接管方式见 [Q-003](../../docs/05-open-questions.md#q-003-队列持久化与恢复)。

## 4. 事件序号与重放

1. 写入事件时锁定对应的 `test_runs` 行，再查询 `(run_id, event_id)`。同一事件 ID 的版本、类型、发生时间、关联和载荷一致时，返回原序号。内容不一致时，按 C4 拒绝并记录故障。
2. 新事件的 Run 必须仍允许追加。由 `last_event_sequence` 从 0 开始递增，与事件插入一起提交。终态过渡在同一事务中追加允许的事件，终态提交以后只允许已有事件的幂等重试。每个 Run 的序号连续，取值范围与 C4 一致。
3. SSE 从已提交的 `run_events` 按 `sequence > cursor` 升序读取。历史回放和实时跟随使用同一游标，唤醒信号只负责提示重新查询。Run 可查询期间保留可重放的事件。

Run 行锁可通过 `SELECT ... FOR UPDATE` 实现。PostgreSQL 的数据库序列在事务回滚时保留已发出的值。C4 的无空洞序号使用上述同一事务内的 Run 计数器。[PostgreSQL 17 行锁](https://www.postgresql.org/docs/17/explicit-locking.html#LOCKING-ROWS) · [PostgreSQL 17 序列函数](https://www.postgresql.org/docs/17/functions-sequence.html)

## 5. 证据登记与访问

- `ArtifactStore.save` 在证据字节可读且元数据已提交后返回 `ArtifactRef`。写入失败时保留失败结果并处理未登记文件。数据库提交结果不明确时，先根据存储键核对登记记录，再清理孤儿文件。
- 事件或报告引用证据前，在写入边界确认其登记已提交且属于同一 Run。报告断言的证据满足 C2 的关联要求。公开响应按 C5 生成同源访问 URL，存储键只供后端使用。
- 下载时先验证调用者可访问证据所属的 Run，再判断过期或存储可读性。使用 C5 的 `404 ARTIFACT_NOT_FOUND`、`410 ARTIFACT_EXPIRED` 和 `503 ARTIFACT_UNAVAILABLE`。
- 到期回收文件后保留最小元数据、过期时间和删除记录，直到 Run 删除。移除 Run 时，平台先清理证据文件或记录待清理项，再清除 PostgreSQL 中的关联记录。

## 6. 验收

后端实现的数据库验收使用独立 PostgreSQL 17 测试库，以并发连接和可控故障验证事务边界。

| ID | 通过条件 |
| --- | --- |
| C6-AT-01 | 排队提交后重启 Worker 仍能领取。两个 Worker 竞争同一 Run 时只写入一次 `run.started`，只启动一次执行 |
| C6-AT-02 | 事件重试复用原序号，内容冲突被拒绝。模拟事务回滚时计数器与事件一起回退，下一条事件编号连续。不同 Run 独立编号 |
| C6-AT-03 | 取消先提交和完成先提交分别得到 C1/C2 规定的结果。每次 Run 恰有一个终态。含报告时，终态、报告与事件原子可见，`report.generated` 的序号在终态前 |
| C6-AT-04 | 重启后按原游标重放事件。回放期间并发追加新事件，消费者最终按序收到已提交记录。回滚事件不会发送 |
| C6-AT-05 | 文件写入或元数据提交失败时无可发布的悬空证据引用。未授权请求返回 `404`。过期文件回收后，授权请求返回 `410` 且历史报告仍可显示证据元数据 |
| C6-AT-06 | 报告或事件引用另一 Run 的证据时写入失败。使用带标记的测试凭据证明公开查询、事件和报告已脱敏 |

参考 DDL 可用于临时库验证字段与约束。后端生产迁移、数据库连接库和运维参数由实现阶段确定。
