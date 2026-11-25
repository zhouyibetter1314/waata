# WAATA API 与 Worker

FastAPI 接收入队请求，提供详情、报告、SSE 和证据读取。Worker 从 PostgreSQL 领取任务并运行 `waata`。两者共用数据库、目标策略和私有证据目录。[运行流程](../../docs/03-architecture.md) · [C1～C6](../../contracts/README.md)

## 准备数据库和依赖

在使用 POSIX 文件锁的环境中，从仓库根目录执行以下命令。首次安装 Chromium 或 Playwright 的锁定版本更新时，需要对应版本的浏览器。

```bash
uv sync --locked --all-packages
uv run --locked playwright install chromium
```

以下示例在本机 `55432` 启动专用 PostgreSQL 17，数据保存在 Docker 卷内。配置 DSN 时使用当前终端生成的 `POSTGRES_PASSWORD`。

```bash
export POSTGRES_PASSWORD="$(uv run --locked python -c 'from secrets import token_hex; print(token_hex(24))')"
docker run -d --name waata-postgres -p 127.0.0.1:55432:5432 \
  -e POSTGRES_USER=waata -e POSTGRES_DB=waata -e POSTGRES_PASSWORD \
  -v waata-postgres-data:/var/lib/postgresql/data postgres:17
docker exec waata-postgres pg_isready -U waata -d waata
```

数据库就绪后，对空库依次应用以下迁移。已有库按编号应用尚未执行的版本。[迁移规约](../../migrations/README.md)

```bash
docker exec -i waata-postgres psql -X -v ON_ERROR_STOP=1 -U waata -d waata -f - < migrations/0001_platform_persistence.sql
docker exec -i waata-postgres psql -X -v ON_ERROR_STOP=1 -U waata -d waata -f - < migrations/0002_run_execution_lease.sql
```

## 本地启动与目标配置

在仓库根目录执行 `cp -n .env.example .env`。填写配置，也可通过进程环境变量覆盖同名值。[环境模板](../../.env.example)

| 变量 | 本地配置 |
| --- | --- |
| `WAATA_DATABASE_DSN` | `postgresql://waata:<数据库密码>@127.0.0.1:55432/waata` |
| `WAATA_AUTH_MODE` | 本地联调用 `local`。接受回环访问，默认主体为 `local`，可由 `WAATA_LOCAL_OWNER_ID` 指定 |
| `WAATA_TARGET_POLICY` | 目标授权 JSON 路径，例如 `.local/targets.json` |
| `WAATA_MODEL_BASE_URL`、`WAATA_MODEL_NAME`、`WAATA_MODEL_API_KEY` | OpenAI 兼容服务根地址、支持工具调用的模型 ID 和访问密钥。服务端允许匿名时密钥可省略。对应的 `DEEPSEEK_*` 变量仍可用作回退 |
| `LANGFUSE_BASE_URL`、`LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY` | 可选，配置追踪地址和一对项目密钥。[本地 Langfuse](../../infra/README.md#langfuse) |

### 配置一个你有权限测试的站点

在授权文件中添加目标。下面允许本机主体访问服务并点击页面控件。任务填写具体页面路径，例如 `http://127.0.0.1:3000/projects`。

```json
[
  {
    "origin": "http://127.0.0.1:3000",
    "owners": ["local"],
    "actions": ["browser.navigate", "browser.click"]
  }
]
```

根据场景授权 `browser.fill` 或 `browser.select_option`。Agent 从页面观察选择控件定位器。需要登录时，在目标的 `credentials` 中为账号登记集合名和字段。每个字段包含受信任的环境变量名 `env` 和定位器 `locator`，用于绑定秘密与登录输入框。任务只填集合名。同源 WebSocket 和截图通过目标策略启用。配置修改后重启 API 和 Worker。[配置实例](../../examples/README.md#目标策略与凭据引用) · [凭据填充契约](../../contracts/tools/c3-browser-tools.md#54-browserfill)

### 启动平台

启动已授权测试站点。以下两个命令分别在仓库根目录的不同终端运行。

```bash
uv run --locked uvicorn waata_api.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
uv run --locked python -m waata_api.workers
```

从 `apps/web` 运行 `npm ci` 和 `npm run dev`，打开 [新建任务](http://127.0.0.1:5173/runs/new)。要观察 Chromium 窗口，在有桌面环境的 Worker 上设置 `WAATA_ALLOW_HEADFUL=true`，再在提交时取消勾选「无头浏览器运行」。Worker 会将未启用的有界面运行报告为配置错误。[前端说明](../web/README.md) · [手工验收](../../docs/04-acceptance.md)

## 运行设置

| 主题 | 配置与行为 |
| --- | --- |
| 共享部署 | 设置 `WAATA_AUTH_MODE=gateway`、`WAATA_GATEWAY_TOKEN`、`WAATA_ALLOWED_HOSTS` 和 `WAATA_WEB_ORIGINS`。后两者为逗号分隔的精确 Host 和 origin。可信同源网关校验用户会话，剥除外来身份头，再用 `X-WAATA-Principal` 与 `X-WAATA-Gateway-Token` 转发。限制 API 仅可由网关访问 |
| 并发与预算 | `WAATA_ENGINE_CONFIG` 以 JSON 配置引擎预算。每个 Worker 的槽数由 `WAATA_WORKER_CONCURRENCY` 决定，默认使用引擎的 `max_concurrent_runs`，其默认值为 2 |
| 模型限流 | `MODEL_RATE_LIMITED` 表示供应商限制了请求量。同一 Worker 在 `Retry-After` 指定的时间内暂停发送模型请求，缺少该响应头时等待 30 秒。引擎在运行期限和 `model_retries` 预算内重试。共享配额较紧时可设置 `WAATA_WORKER_CONCURRENCY=1`，让本机任务串行 |
| Worker 定时 | `WAATA_WORKER_POLL_SECONDS`、`WAATA_WORKER_HEARTBEAT_SECONDS`、`WAATA_WORKER_LEASE_SECONDS`、`WAATA_WORKER_SHUTDOWN_SECONDS` 分别默认为 0.25、2、15 和 15 秒。租约须长于两次心跳间隔 |
| SSE 定时 | `WAATA_SSE_POLL_SECONDS` 默认 0.25 秒，`WAATA_SSE_KEEPALIVE_SECONDS` 默认 15 秒。网关关闭 SSE 缓冲，流空闲超时设为大于保活间隔 |
| 证据存储 | `WAATA_ARTIFACT_ROOT` 默认 `artifacts/platform`，须由 API 与 Worker 共用，支持文件锁和原子重命名。`WAATA_ARTIFACT_RETENTION_SECONDS` 默认七天。`WAATA_ARTIFACT_MAX_BYTES` 以 JSON 按证据类型覆盖写入上限。[C5](../../contracts/artifacts/c5-test-evidence-artifacts.md) |

重启前保留数据库与证据目录即可继续查询历史。停止 API 和 Worker 后可用 `docker stop waata-postgres` 暂停本地数据库，后续用 `docker start waata-postgres` 继续使用同一数据。

## 校验

设置 `WAATA_TEST_DATABASE_URL` 后，数据库测试在独立的 PostgreSQL 17 测试库内验证迁移和事务。每条测试创建自己的 schema。

```bash
uv run --locked python -m unittest discover -s apps/api/tests -v
uv run --locked python -m unittest discover -s tests/contract -v
```

HTTP 模型变更后，从根目录更新 OpenAPI 和前端类型。

```bash
uv run --locked python -m waata_api.openapi contracts/http/openapi.json
npm --prefix apps/web run generate:api
npm --prefix apps/web run typecheck
```
