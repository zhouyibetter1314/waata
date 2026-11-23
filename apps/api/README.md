# WAATA API 与 Worker

FastAPI 提供 C1 任务和报告、C4 SSE 重放及 C5 证据读取。独立的 Worker 从 PostgreSQL 17 领取任务，调用 WAATA 的 C2 公共接口，再提交进度、报告或终态。两个进程使用同一数据库及持久证据目录。 [C1～C6](../../contracts/README.md)

## 准备数据库和依赖

在仓库根目录执行，后端使用 Linux 或其他支持 POSIX 文件锁的环境，以及本机专用 PostgreSQL 17 测试库。以下示例将数据库绑定到本机 `55432`，用 Docker 管理独立的数据卷。

```bash
uv sync --locked --all-packages
uv run --locked playwright install chromium --only-shell
export POSTGRES_PASSWORD="$(uv run --locked python -c 'from secrets import token_hex; print(token_hex(24))')"
docker run -d --name waata-postgres -p 127.0.0.1:55432:5432 \
  -e POSTGRES_USER=waata -e POSTGRES_DB=waata -e POSTGRES_PASSWORD \
  -v waata-postgres-data:/var/lib/postgresql/data postgres:17
docker exec waata-postgres pg_isready -U waata -d waata
```

等数据库就绪后，在空库按顺序执行迁移。

```bash
docker exec -i waata-postgres psql -X -v ON_ERROR_STOP=1 -U waata -d waata -f - < migrations/0001_platform_persistence.sql
docker exec -i waata-postgres psql -X -v ON_ERROR_STOP=1 -U waata -d waata -f - < migrations/0002_run_execution_lease.sql
```

已有库依据 `schema_migrations` 应用未执行的版本。升级至租约版本前停止旧写入者。Worker 启动后会将失去执行者的历史 `running` 记录收尾为 `WORKER_ERROR`，保留已提交事件和证据。可在本机直接使用 `psql` 应用同一 SQL 文件。 [迁移规约](../../migrations/README.md)

## 本地登录夹具

参考仓库根目录的 [.env.example](../../.env.example)，将以下值配置到同一工作目录的 `.env` 或分别导出到运行进程环境。数据库 DSN 形如 `postgresql://waata:<数据库密码>@127.0.0.1:55432/waata`。保留实际密码和密钥在本地环境。

| 变量 | 本地配置 |
| --- | --- |
| `WAATA_DATABASE_DSN` | 上面创建的数据库 DSN |
| `WAATA_AUTH_MODE` | `local`，使用回环地址与固定主体 `local` |
| `WAATA_TARGET_POLICY` | `testsites/demo-app/targets.example.json` |
| `WAATA_DEMO_PASSWORD`、`WAATA_DEMO_WRONG_PASSWORD` | 两个不同的随机夹具值 |
| `WAATA_MODEL_BASE_URL`、`WAATA_MODEL_NAME`、`WAATA_MODEL_API_KEY` | 已授权的 OpenAI 兼容服务根地址、支持工具调用的模型 ID 和访问密钥。服务无需认证时可省略密钥 |

已有配置中的 `DEEPSEEK_*` 模型变量仍可作为兼容回退。对应的 `WAATA_MODEL_*` 变量有值时优先使用新配置。

分别在不同终端启动夹具、API 和 Worker。

```bash
uv run --locked --env-file .env python testsites/demo-app/server.py --port 3010
uv run --locked --env-file .env python testsites/demo-app/server.py --port 3011 --regression
uv run --locked uvicorn waata_api.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
uv run --locked python -m waata_api.workers
```

另一个终端启动 Vue。

```bash
cd apps/web
npm ci
VITE_API_MOCKING=disabled npm run dev
```

打开 [新建任务](http://127.0.0.1:5173/runs/new)。目标使用 `http://127.0.0.1:3010/login` 和 `http://127.0.0.1:3011/login`，凭据引用均为 `demo_login_fixture`。目标为验证有效和无效密码两个场景。预期为有效密码进入 `/dashboard` 且显示 `Signed in`，错误密码留在 `/login` 且显示 `Wrong password`。基准版正常完成且通过，回归版正常完成且显示失败断言。

## 运行设置

- **授权**。可信目标配置为 JSON 数组。每项明确允许的 origin、主体、浏览器动作及凭据引用。未配置目标时无任务可进入执行。Worker 再次验证配置，并按需要解析字段级环境变量。浏览器只在授权的受控测试环境使用，部署时将浏览器的网络出口限制在该环境内。
- **共享部署**。设置 `WAATA_AUTH_MODE=gateway`、`WAATA_GATEWAY_TOKEN`、`WAATA_ALLOWED_HOSTS` 和 `WAATA_WEB_ORIGINS`。后两项为逗号分隔的精确 Host 与 origin。同源网关验证会话，剥除外部请求的 `X-WAATA-Principal`、`X-WAATA-Gateway-Token`，再用经认证的主体和内部令牌重写这两个头。API 只接收网关转发的请求。禁用 SSE 缓冲，并将网关流空闲超时设为大于 SSE 保活间隔。
- **并发与预算**。`WAATA_WORKER_CONCURRENCY` 控制每个 Worker 的运行槽数。可用 `WAATA_ENGINE_CONFIG` JSON 设置 WAATA 的用例、动作、步骤、模型和超时预算。`WAATA_WORKER_POLL_SECONDS`、`WAATA_WORKER_HEARTBEAT_SECONDS`、`WAATA_WORKER_LEASE_SECONDS`、`WAATA_WORKER_SHUTDOWN_SECONDS` 默认分别为 0.25、2、15 和 15 秒。`WAATA_SSE_POLL_SECONDS` 与 `WAATA_SSE_KEEPALIVE_SECONDS` 默认分别为 0.25 和 15 秒。使用可显示界面的 Chromium 环境时，可设置 `WAATA_ALLOW_HEADFUL=true` 启用 headed 模式。
- **证据**。`WAATA_ARTIFACT_ROOT` 默认是 `artifacts/platform`，API 与 Worker 需使用支持原子重命名与文件锁的同一私有持久目录。`WAATA_ARTIFACT_RETENTION_SECONDS` 默认七天，`WAATA_ARTIFACT_MAX_BYTES` 以 JSON 按类型覆盖写入大小。结构化观察默认保存，截图由目标策略选择并配置遮罩。原始 Playwright Trace 采集维持关闭。Langfuse 可用 `LANGFUSE_BASE_URL`、`LANGFUSE_PUBLIC_KEY` 与 `LANGFUSE_SECRET_KEY` 启用。

## 校验

用独立的 PostgreSQL 17 测试库，将该库的 DSN 设置为 `WAATA_TEST_DATABASE_URL`。真实 HTTP 与 Vue 验收要求已应用全部迁移、已安装 Chromium 和前端依赖，且本机 `8000`、`5173` 空闲。测试会启动真实 API、Worker、Vue 和本机夹具，使用可控模型替身。

```bash
uv run --locked python -m unittest discover -s apps/api/tests -v
uv run --locked python -m unittest discover -s tests/contract -v
uv run --locked python -m unittest discover -s tests/e2e -v
uv run --locked pre-commit run --all-files
```

修改 HTTP 模型后生成并检查 OpenAPI 及前端类型。

```bash
uv run --locked python -m waata_api.openapi contracts/http/openapi.json
npm --prefix apps/web run generate:api
npm --prefix apps/web run typecheck
```
