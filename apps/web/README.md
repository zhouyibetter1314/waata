# WAATA Web

Vue 3 和 TypeScript 前端。开发服务器监听 `127.0.0.1:5173`，将 `/api` 转发给 `127.0.0.1:8000`，并使用原生 `EventSource` 订阅运行事件。页面读取任务、运行进度、报告和证据时使用同源 API。[启动 FastAPI 和 Worker](../api/README.md#本地启动与目标配置) · [C1、C4 和 C5](../../contracts/README.md)

## 本地运行

使用 Node.js 22.12+ 和 npm。在 `apps/web` 安装锁定依赖并启动开发服务器。端口占用时服务器会报错。

```bash
npm ci
npm run dev
```

## 页面与数据

| 页面       | 入口             | 数据来源                                                             |
| ---------- | ---------------- | -------------------------------------------------------------------- |
| 场景与应用 | `/scenarios`     | 浏览器本地存储。先建应用，再维护或导入场景。批量运行时各场景独立提交 |
| 新建任务   | `/runs/new`      | 用户填写目标地址、测试目标和预期行为后提交 C1                        |
| 运行与报告 | `/runs`          | 分页查看任务，可删除已结束的记录，搜索和筛选应用于当前页            |
| 运行详情   | `/runs/{run_id}` | 在执行时间线展开报告，或打开各事件关联的截图与检查记录              |
| 环境与设置 | `/settings`      | 前端接口和环境信息                                                   |

场景 JSON 的 `application_id` 使用场景库中已有应用的实际 ID。场景库属于当前浏览器与站点 origin。平台运行和报告由服务端持久化。报告页可以预览观察和截图，并下载仍有效的已登记 Trace。

## 开发检查

```bash
npm run format:check
npm run typecheck
npm run lint
npm run test
npm run build
npx playwright install chromium
npm run test:e2e
```

`tests/` 包含单元与组件测试，`e2e/` 使用 Playwright 验证浏览器流程，测试响应只在这些检查中加载。可用 `WAATA_BROWSER_EXECUTABLE` 指定已安装的浏览器。完整平台联调使用授权站点和实际服务。[手工验收](../../docs/04-acceptance.md)

HTTP 模型变更后，先按后端说明导出 OpenAPI，再在 `apps/web` 运行 `npm run generate:api` 和 `npm run typecheck`。生成文件为 `src/api/schema.d.ts`，SSE 信封由 `src/api/types.ts` 按 C4 定义。[导出 OpenAPI](../api/README.md#校验)

## 部署

`npm run build` 生成 `dist/`。同源网关把 `/api` 转到 FastAPI，并将前端路由回退到 `index.html`。SSE 路径需要流式转发。[共享部署](../api/README.md#运行设置)

配有同源 `/live/` 只读画面代理的本机调试环境，可在启动 Vite 或构建前端时设置 `VITE_LOCAL_LIVE_VIEW=true`。在回环地址打开运行详情时，进行中的任务会显示画面入口。[4gaBoards 联调记录](../../docs/testing/4gaboards-integration.md)
