# WAATA API

B01/B02 交付 C1 的创建任务、分页列表和任务详情，覆盖 FR-001、FR-006 及 C1-AT-01、C1-AT-06 的本阶段范围。任务入队后返回 202。仓储与队列为单进程内存替身，重启会清空任务，联调期间状态保持 queued。

本地联调阶段的每用例步骤预算默认值及输入上限均为 35。整次运行的浏览器操作预算由后续 Worker 与 C2 执行配置确定。

## 本地联调

在仓库根目录用 PowerShell 运行。开发身份仅用于本机联调。终端会生成一个临时令牌。

~~~powershell
uv sync --locked --package waata-api
$env:WAATA_DEV_TOKEN = [guid]::NewGuid().ToString('N')
$env:WAATA_DEV_TOKEN
uv run --locked --package waata-api uvicorn waata_api.main:app --host 127.0.0.1 --port 8000 --no-access-log
~~~

- API 基地址 http://127.0.0.1:8000/api/v1
- Swagger UI [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- OpenAPI [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

在 Swagger UI 的 Authorize 对话框将临时令牌填入 HTTPBearer 栏。开发身份允许提交目标 origin 为 https://demo-app.test、http://127.0.0.1:3000 或 http://localhost:3000 的任务，可选择凭据引用 demo_login_fixture 或 boards_local_fixture。提交只登记并排队。[C1 创建请求样例](../../contracts/http/examples/4gaboards-create-run.json)

连接 Vue 时，在 apps/web 启动 Vite 并将 VITE_API_MOCKING 设为 disabled。打开 http://127.0.0.1:5173，在该页面的浏览器控制台调用以下命令并输入刚才生成的临时令牌。Vite 将同源请求转发给 FastAPI，浏览器收到 HttpOnly 会话 Cookie 后刷新页面即可联调。会话有效期 1 小时。

~~~javascript
await fetch('/api/dev/session', {
  method: 'POST',
  headers: { Authorization: 'Bearer ' + prompt('输入本次本地联调令牌') },
}).then((response) => response.status)
~~~

返回 204 表示会话建立。未配置开发令牌时，本地启动入口不开放会话路由，任务接口要求显式注入的合法身份。共享环境的身份方案、配置与联调地址需与前端确认。

## 快照与验证

~~~bash
uv run --locked --package waata-api python scripts/export_openapi.py
uv run --locked --package waata-api python scripts/export_openapi.py --check
uv run --locked --package waata-api python -m unittest discover -s apps/api/tests -v
uv run --locked python -m unittest discover -s tests/contract -v
~~~

前端从 [OpenAPI 快照](../../contracts/http/openapi.json)生成 B01/B02 类型。证据可见性授权入口由 B01 提供，可读证据接口接入 B06。事件、取消和报告路由将在 B03 接通 Worker 与 FakeTestEngine 后按 B04/B05 提供。
