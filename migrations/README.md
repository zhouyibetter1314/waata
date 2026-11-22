# PostgreSQL 迁移

本目录中的版本化 SQL 定义 WAATA 平台的 PostgreSQL 17 表、约束和索引。数据模型与事务边界见 [C6](../contracts/database/c6-platform-persistence.md)。

## 编写迁移

- 文件采用 `NNNN_description.sql`，使用四位递增编号及小写下划线描述。变更表结构时新增下一版本。已应用的文件保持原名和内容。
- 每个文件在同一事务内完成变更，并向 `schema_migrations` 写入版本号、文件名和应用时间。迁移失败时，结构变更和版本记录一并回滚。
- 在空 PostgreSQL 17 库验证完整迁移链。新增版本还须从上一版本升级带代表性数据的测试库，核对结果及数据保留情况。

## 应用迁移

由单一发布步骤负责迁移，在启动依赖新结构的 FastAPI 和 Worker 前完成。应用进程只使用已迁移的库。连接配置通过 PostgreSQL 客户端环境提供，并确认目标数据库。

从仓库根目录对空库应用 [首版迁移](0001_platform_persistence.sql)。

```bash
psql -X -v ON_ERROR_STOP=1 -f migrations/0001_platform_persistence.sql
```

升级已有库时，先核对已应用的版本和文件名，再按编号升序逐个执行待应用的文件。遇到错误时停止，确认当前版本已回滚后再重试。[PostgreSQL 17 psql 文档](https://www.postgresql.org/docs/17/app-psql.html#APP-PSQL-VARIABLES-ON-ERROR-STOP)

```sql
SELECT version, filename, applied_at FROM schema_migrations ORDER BY version;
```

已有表但缺少版本记录的库须先核对结构和数据，再制定接入迁移的方案。
