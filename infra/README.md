# 本地依赖

| 依赖 | 用途 | 位置 |
| --- | --- | --- |
| PostgreSQL 17 | WAATA 任务、事件、报告及证据元数据 | [API 与 Worker 启动说明](../apps/api/README.md#准备数据库和依赖) |
| Langfuse v4.30.0 | 可选的 Worker 运行追踪 | [`infra/langfuse/`](langfuse/)，本页提供 Compose 启动方式 |
| 4gaBoards、Admidio、Discourse | 按需部署的外部测试站点 | [固定版本与上游部署说明](../testsites/README.md) |

按需检出子模块。平台基本运行使用 PostgreSQL、模型服务和授权测试站点，Langfuse 独立启用。

```bash
git submodule update --init -- infra/langfuse
git submodule status
```

## Langfuse

[`infra/langfuse/`](langfuse/) 固定到上游 `v4.30.0`（`2f00fd4`）。该版本自带的 Compose 使用浮动 `:4` 镜像。[本地覆盖文件](docker/langfuse.local.yaml) 将 Web 和 Worker 固定为 `4.30.0`，使用独立 Compose 项目 `waata-langfuse`，并且只向回环地址发布 Web `13038` 和 MinIO `9090`。Docker Compose 需为 2.24.4 或更新版本。 [Langfuse 发布记录](https://github.com/langfuse/langfuse/releases/tag/v4.30.0) · [Docker Compose 合并规则](https://docs.docker.com/reference/compose-file/merge/#replace-value)

在单独的终端从仓库根目录复制环境文件。Compose 会优先读取终端中同名的变量，请使用 Langfuse 独立配置。

```bash
cp -n infra/docker/.env.langfuse.example infra/docker/.env.langfuse
```

编辑 `infra/docker/.env.langfuse`，用 `openssl rand -hex 32` 为每处 `replace_me` 生成不同的值。完成后在同一终端启动服务。

```bash
langfuse_compose() {
  docker compose -p waata-langfuse \
    --env-file infra/docker/.env.langfuse \
    -f infra/langfuse/docker-compose.yml \
    -f infra/docker/langfuse.local.yaml "$@"
}

langfuse_compose config --images
langfuse_compose up -d
langfuse_compose ps
```

打开 <http://127.0.0.1:13038>，创建 Langfuse 项目及 API 密钥。在 WAATA 根目录的 `.env` 中填写 `LANGFUSE_BASE_URL=http://127.0.0.1:13038`，并分别填写 `LANGFUSE_PUBLIC_KEY` 和 `LANGFUSE_SECRET_KEY`。重新启动 Worker 以读取配置。报告中的 `langfuse_trace_id` 可用于在 Langfuse 项目中查找运行追踪。省略两项密钥即可关闭 Worker 追踪。

`uv.lock` 固定了兼容此服务端的 Langfuse Python SDK v4。升级时同时核对 Git 子模块版本、Web 和 Worker 镜像及 SDK 兼容性。 [Langfuse 兼容性说明](https://langfuse.com/docs/compatibility)

`langfuse_compose down` 停止容器并保留数据卷。对本地实例执行 `langfuse_compose down --volumes` 会清空 PostgreSQL、ClickHouse、Redis 和对象存储数据，下次启动需要重新创建项目和密钥。WAATA 平台数据库由 API 启动说明中的独立容器管理。
