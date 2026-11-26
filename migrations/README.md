# PostgreSQL 迁移

本目录中的版本化 SQL 定义 WAATA 平台的 PostgreSQL 17 表、约束和索引。数据模型与事务边界见 [C6](../contracts/database/c6-platform-persistence.md)。

| 迁移 | 内容 |
| --- | --- |
| [0001](0001_platform_persistence.sql) | 运行、事件、证据元数据及迁移记录 |
| [0002](0002_run_execution_lease.sql) | Worker 执行令牌与租约，以及租约回收、用例事件和证据到期索引 |
| [0003](0003_run_artifact_cleanup.sql) | 已删除任务的证据文件清理队列 |

## 编写迁移

- 文件采用 `NNNN_description.sql`，使用四位递增编号及小写下划线描述。变更表结构时新增下一版本。已应用的文件保持原名和内容。
- 每个文件在同一事务内完成变更，并向 `schema_migrations` 写入版本号、文件名和应用时间。迁移失败时，结构变更和版本记录一并回滚。
- 在空 PostgreSQL 17 库验证完整迁移链。新增版本还须从上一版本升级带代表性数据的测试库，核对结果及数据保留情况。

## 应用迁移

由单一发布步骤在启动 FastAPI 和 Worker 前执行迁移。两者启动时都核对 `schema_migrations` 是否包含版本 3。先通过 PostgreSQL 客户端环境指定目标库，使用 Docker 时可按后端说明执行同一组 SQL。[PostgreSQL 启动示例](../apps/api/README.md#准备数据库和依赖)

从仓库根目录对空库按序应用全部迁移。

```bash
psql -X -v ON_ERROR_STOP=1 -f migrations/0001_platform_persistence.sql
psql -X -v ON_ERROR_STOP=1 -f migrations/0002_run_execution_lease.sql
psql -X -v ON_ERROR_STOP=1 -f migrations/0003_run_artifact_cleanup.sql
```

升级已有库时，查询已应用的版本和文件名，按编号升序执行待应用的 SQL。应用中止时先核对该版本是否已回滚。已有表且缺少版本记录的库应先核对结构和数据。[PostgreSQL 17 psql](https://www.postgresql.org/docs/17/app-psql.html#APP-PSQL-VARIABLES-ON-ERROR-STOP)

```sql
SELECT version, filename, applied_at FROM schema_migrations ORDER BY version;
```

执行 0002 前停止旧 Worker 及其浏览器执行。新版 Worker 会将遗留的无租约 `running` 记录收尾为 `errored`、判定为空，并继续领取原有排队任务。[C6](../contracts/database/c6-platform-persistence.md)
