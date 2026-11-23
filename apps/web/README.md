# WAATA Web

WAATA 的 Vue 3 + TypeScript 前端。任务、进度、报告和证据接口遵循 [C1、C4 和 C5](../../contracts/README.md)。

## 当前功能

- 提交测试任务，分页查询运行记录，跟踪 SSE 进度或申请取消。
- 查看用例、步骤与断言，读取证据或下载 Trace。
- 本地场景库支持应用配置、JSON 导入与批量提交。场景模板保存在当前浏览器，运行时逐项发送 C1 创建请求。

## 本地运行

使用 Node.js 22.12 或更高版本及 npm 10.9.2。在仓库根目录运行以下命令。

```bash
cd apps/web
npm ci
npm run dev
```

开发服务器使用 <http://127.0.0.1:5173>。端口被占用时启动失败。

开发模式默认用 MSW 加载共享 JSON 和 SSE 样例。联调时禁用 Mock，`/api` 会代理到 `http://127.0.0.1:8000`。 [后端启动与联调](../api/README.md)

Bash

```bash
VITE_API_MOCKING=disabled npm run dev
```

PowerShell

```powershell
$env:VITE_API_MOCKING='disabled'
npm run dev
```

## 页面与数据来源

| 页面       | 路径             | 数据来源                       |
| ---------- | ---------------- | ------------------------------ |
| 场景与应用 | `/scenarios`     | 浏览器本地存储，提交时调用 C1  |
| 新建任务   | `/runs/new`      | C1 `POST /api/v1/test-runs`    |
| 运行与报告 | `/runs`          | C1 分页列表                    |
| 运行详情   | `/runs/{run_id}` | C1 详情与报告、C4 SSE、C5 证据 |
| 环境与设置 | `/settings`      | 前端构建配置和静态契约信息     |

## 验证

从 `apps/web/` 运行检查。

```bash
npm run format:check
npm run typecheck
npm run lint
npm run test
npm run build
npx playwright install chromium
npm run test:e2e
```

单元及组件测试位于 `tests/`，浏览器测试位于 `e2e/`。已有 Chrome 时，可用 `WAATA_BROWSER_EXECUTABLE` 指定浏览器路径。

现有测试覆盖 Mock 提交、查询、事件重放、排队取消、报告和 JSON 证据。仍需验证以下场景。

- SSE 断线、重复事件、保活、切换 Run、未来游标的重试上限，以及收到 `204` 后停止重连。
- 运行中取消返回 `202` 后的状态刷新，以及取消竞争返回 `409`。
- 截图预览、ZIP 下载，以及证据读取返回 `404`、`410`、`503`。
- 浏览器中的真实平台链路由 [全链路测试](../../tests/e2e/test_platform.py) 验证，覆盖提交、基准与回归结果、证据读取和重启后重放。

## API 类型

`src/api/types.ts` 从生成的 HTTP 类型导出 C1 和 C5 数据模型，同时按 C4 定义 SSE 信封。后端更新 `contracts/http/openapi.json` 后，从 `apps/web/` 重新生成类型。

```bash
npm run generate:api
```

生成结果写入 `src/api/schema.d.ts`。运行 `npm run typecheck` 验证 C1-AT-06。
