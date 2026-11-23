# WAATA API 与 Worker

FastAPI 提供 C1 任务和报告、C4 SSE 重放及 C5 证据读取。独立的 Worker 从 PostgreSQL 17 领取任务，调用 WAATA 的 C2 公共接口，再提交进度、报告或终态。两个进程使用同一数据库及持久证据目录。 [C1～C6](../../contracts/README.md)

## 准备数据库和依赖

在仓库根目录执行，后端使用 Linux 或其他支持 POSIX 文件锁的环境，以及本机专用 PostgreSQL 17 测试库。以下示例将数据库绑定到本机 `55432`，用 Docker 管理独立的数据卷。

```bash
uv sync --locked --all-packages
```

首次运行或锁定的 Playwright 版本需要新的 Chromium 时，安装与之匹配的完整浏览器。已有匹配版本时会复用缓存。Linux 默认存放在 `~/.cache/ms-playwright`。 [Playwright 浏览器安装](https://playwright.dev/python/docs/browsers)

```bash
uv run --locked playwright install chromium
```

在同一个终端里创建本地 PostgreSQL。

```bash
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

## 本地启动与目标配置

在仓库根目录创建 `.env`，例如执行 `cp -n .env.example .env`。将以下值写入该文件，或分别导出到运行进程环境。数据库 DSN 形如 `postgresql://waata:<数据库密码>@127.0.0.1:55432/waata`，密码使用前一步生成的值。实际密码和密钥保存在本地环境。 [.env.example](../../.env.example)

| 变量 | 本地配置 |
| --- | --- |
| `WAATA_DATABASE_DSN` | 上面创建的数据库 DSN |
| `WAATA_AUTH_MODE` | 本机联调填 `local`。API 使用固定的请求者标识 `local` 接收来自本机的请求 |
| `WAATA_TARGET_POLICY` | 目标授权 JSON 的路径，例如 `.local/targets.json` |
| `WAATA_MODEL_BASE_URL`、`WAATA_MODEL_NAME`、`WAATA_MODEL_API_KEY` | 已授权的 OpenAI 兼容服务根地址、支持工具调用的模型 ID 和访问密钥。服务无需认证时可省略密钥 |
| `WAATA_ALLOW_HEADFUL` | Worker 在桌面环境运行时可设为 `true`，允许任务显示 Chromium 窗口 |
| `LANGFUSE_BASE_URL`、`LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY` | 可选。追踪地址与 Langfuse 项目的一对密钥。 [本地 Langfuse](../../infra/README.md#langfuse) |

已有配置中的 `DEEPSEEK_*` 模型变量仍可作为兼容回退。对应的 `WAATA_MODEL_*` 变量有值时优先使用新配置。

### 配置一个你有权限测试的站点

`WAATA_AUTH_MODE` 决定 API 把请求视为谁发来的。`WAATA_TARGET_POLICY` 决定这位请求者能让 Worker 打开哪些站点、执行哪些动作。浏览器执行层也会应用该策略。

例如，若测试页面是 `http://127.0.0.1:3000/projects`，可在仓库根目录创建 `.local/targets.json`，并在 `.env` 中填写 `WAATA_TARGET_POLICY=.local/targets.json`。下面的策略允许本机请求者访问该服务和点击页面控件。`origin` 填协议、主机和端口，具体页面路径由新建任务提供。

```json
[
  {
    "origin": "http://127.0.0.1:3000",
    "owners": ["local"],
    "actions": ["browser.navigate", "browser.click"]
  }
]
```

将示例 origin 换成实际测试站。需要输入文本时加入 `browser.fill`，需要选择下拉选项时加入 `browser.select_option`。无需登录的任务可以留空「凭据引用」。需要登录时，在目标策略的 `credentials` 中为账号取一个引用名，登记每个字段的本地环境变量名 `env` 及输入框定位方式 `locator`。在任务里只填写该引用名。 [凭据填充契约](../../contracts/tools/c3-browser-tools.md#54-browserfill)

### 启动平台

先启动自己的测试站。在仓库根目录打开两个终端，分别执行一条命令启动 API 和 Worker。

```bash
uv run --locked uvicorn waata_api.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
uv run --locked python -m waata_api.workers
```

另一个终端启动 Vue。

```bash
cd apps/web
npm ci
VITE_API_MOCKING=disabled npm run dev
```

Vue 启动后，打开 <http://127.0.0.1:5173/runs/new>，填写自己的目标页面、测试目标和预期行为。要看到 Chromium 窗口，先用 `WAATA_ALLOW_HEADFUL=true` 启动 Worker，然后取消勾选「无头浏览器运行」再提交任务。使用已有 Worker 时，修改 `.env` 后重启它。 [手工验收](../../docs/04-acceptance.md)

## 停止与重建

先停止本机 API 和 Worker，再执行 `docker stop waata-postgres`。后续可用 `docker start waata-postgres` 继续使用同一数据。确认要重置此专用本地数据库后，删除该容器及 `waata-postgres-data` 数据卷，再按启动说明创建空库，应用全部迁移。需要同步清空运行证据时，删除本次实例的 `WAATA_ARTIFACT_ROOT`。 [迁移规约](../../migrations/README.md)

## 运行设置

- **授权**。可信目标配置为 JSON 数组。每项明确允许的 origin、主体、浏览器动作及凭据引用。未配置目标时无任务可进入执行。Worker 再次验证配置，并按需要解析字段级环境变量。浏览器只在授权的受控测试环境使用，部署时将浏览器的网络出口限制在该环境内。
- **共享部署**。设置 `WAATA_AUTH_MODE=gateway`、`WAATA_GATEWAY_TOKEN`、`WAATA_ALLOWED_HOSTS` 和 `WAATA_WEB_ORIGINS`。后两项为逗号分隔的精确 Host 与 origin。同源网关验证会话，剥除外部请求的 `X-WAATA-Principal`、`X-WAATA-Gateway-Token`，再用经认证的主体和内部令牌重写这两个头。API 只接收网关转发的请求。禁用 SSE 缓冲，并将网关流空闲超时设为大于 SSE 保活间隔。
- **并发与预算**。`WAATA_WORKER_CONCURRENCY` 控制每个 Worker 的运行槽数。可用 `WAATA_ENGINE_CONFIG` JSON 设置 WAATA 的用例、动作、步骤、模型和超时预算。`WAATA_WORKER_POLL_SECONDS`、`WAATA_WORKER_HEARTBEAT_SECONDS`、`WAATA_WORKER_LEASE_SECONDS`、`WAATA_WORKER_SHUTDOWN_SECONDS` 默认分别为 0.25、2、15 和 15 秒。`WAATA_SSE_POLL_SECONDS` 与 `WAATA_SSE_KEEPALIVE_SECONDS` 默认分别为 0.25 和 15 秒。使用可显示界面的 Chromium 环境时，可设置 `WAATA_ALLOW_HEADFUL=true` 启用 headed 模式。
- **证据**。`WAATA_ARTIFACT_ROOT` 默认是 `artifacts/platform`，API 与 Worker 需使用支持原子重命名与文件锁的同一私有持久目录。`WAATA_ARTIFACT_RETENTION_SECONDS` 默认七天，`WAATA_ARTIFACT_MAX_BYTES` 以 JSON 按类型覆盖写入大小。结构化观察默认保存，截图由目标策略选择并配置遮罩。原始 Playwright Trace 采集关闭。 [C5](../../contracts/artifacts/c5-test-evidence-artifacts.md)

## 校验

仓库层的数据库测试使用独立的 PostgreSQL 17 测试库。将该库的 DSN 设置为 `WAATA_TEST_DATABASE_URL`。平台端到端运行按自己的测试站和场景手工验收。 [手工验收](../../docs/04-acceptance.md)

```bash
uv run --locked python -m unittest discover -s apps/api/tests -v
uv run --locked python -m unittest discover -s tests/contract -v
uv run --locked pre-commit run --all-files
```

修改 HTTP 模型后生成并检查 OpenAPI 及前端类型。

```bash
uv run --locked python -m waata_api.openapi contracts/http/openapi.json
npm --prefix apps/web run generate:api
npm --prefix apps/web run typecheck
```
