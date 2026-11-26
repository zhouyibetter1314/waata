# C6 · 平台持久化

FastAPI 和 Worker 共享 PostgreSQL 17 中的运行、事件、报告和证据元数据。文件字节存放在共享证据目录，追踪留在可选的 Langfuse。[PostgreSQL 仓库](../../apps/api/src/waata_api/repositories/postgres.py) · [数据库迁移](../../migrations/README.md) · [C5 证据读取](../artifacts/c5-test-evidence-artifacts.md)

## 数据模型

| 表 | 保存内容 |
| --- | --- |
| `test_runs` | 按 `run_id` 保存 `owner_id`、请求、内部凭据引用、状态、判定、错误、进度、取消标记、时间、事件计数器和执行租约 |
| `run_events` | 按 `(run_id, sequence)` 保存事件，`(run_id, event_id)` 唯一 |
| `run_reports` | 每个 Run 保存一份最终或部分 C2 JSONB 结果和提交时间 |
| `run_artifacts` | 按全局唯一的 `artifact_id` 保存关联 Run、Case、Step、工具调用、证据元数据、内部存储键和过期删除记录 |
| `schema_migrations` | 已应用迁移的版本、文件名和时间 |

数据库使用 `timestamptz`，HTTP 和 SSE 输出 UTC。列表在同一只读事务内按 `owner_id` 过滤、汇总和分页。请求中的 `credential_ref` 单独保存供可信解析器使用，公开响应对照 C1、C4、C5 生成。[初始结构](../../migrations/0001_platform_persistence.sql) · [执行租约](../../migrations/0002_run_execution_lease.sql)

## 事务与恢复

| 写入 | 提交内容 |
| --- | --- |
| 创建 | 保存 `queued` 记录后返回 `202`。Worker 重启后仍可领取 |
| 领取 | 按创建时间取最早可锁定的任务，同时写入 `running`、`started_at`、令牌、租约到期时间及 `run.started` |
| 排队取消 | 写入取消标记、`cancelled`、`finished_at` 和 `run.cancelled`，随后返回 `200` |
| 运行中取消 | 持久化取消标记后返回 `202`。Worker 清理后提交 `cancelled`，必要清理失败提交 `errored` |
| 结束 | 同时提交终态、判定或错误、结束时间及可用报告，清空租约。有报告时先追加 `report.generated`，再追加终态事件 |
| 回收租约 | 锁定租约已过期或缺少租约的遗留运行，提交 `WORKER_ERROR` 与 `run.failed`，保留已有事件和证据 |

每次续租读取取消标记，追加新事件、登记证据和提交终态均检查执行令牌与数据库时钟。终态提交与取消对 Run 行加锁，先提交的取消会影响最终结果。过期执行无法继续发布，恢复流程保留记录以便复查，重新运行由调用方发起。模型、浏览器和文件 I/O 在数据库事务外执行。

删除按主体锁定终态任务，在同一事务内将仍有文件的证据加入 `deleted_run_artifacts` 并级联删除任务、事件、报告和证据元数据。API 提交后尝试清理，Worker 定期处理剩余任务。文件已经不存在时也可清除队列条目，文件删除失败时延迟重试。[迁移](../../migrations/0003_run_artifact_cleanup.sql)

Worker 轮询和续租的默认值分别为 `WAATA_WORKER_POLL_SECONDS=0.25` 和 `WAATA_WORKER_HEARTBEAT_SECONDS=2`，`WAATA_WORKER_LEASE_SECONDS=15` 且须大于两个心跳间隔。[Worker](../../apps/api/src/waata_api/workers/runner.py)

## 事件与证据

- 事件写入锁定 Run 行。同一事件 ID 且内容一致时返回原序号，内容冲突时拒绝。新序号由同一事务中的 `last_event_sequence` 分配，随事件插入一起提交或回滚。SSE 升序推送 `sequence > cursor` 的已提交记录。[C4](../events/c4-test-run-events.md)
- 文件存储先使字节可读，再登记元数据。提交结果不明确时，用存储键核对记录后清理未登记文件。报告和事件写入边界会校验证据引用及关联。[C5](../artifacts/c5-test-evidence-artifacts.md)
- Worker 定期清理过期和孤立的文件。清理过期文件后保留元数据和删除时间，让报告继续解释历史证据。[文件存储实现](../../apps/api/src/waata_api/infrastructure/artifacts.py)

集成测试覆盖迁移、并发领取、事件幂等、取消、租约回收和证据约束。[PostgreSQL 集成测试](../../apps/api/tests/test_repository.py) · [平台验收](../../docs/04-acceptance.md)
