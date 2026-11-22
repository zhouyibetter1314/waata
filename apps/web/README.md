# WAATA Web

WAATA v0.1 的 Vue 3 + TypeScript 前端，正式接口以仓库中的 C1、C4、C5 契约为准。前端负责测试任务提交、查询、进度、取消、报告与证据复核，不直接调用 WAATA Python Package，也不保存模型密钥或明文测试凭据。

## 当前功能

- F01：Vue 工程、路由、C1 API Client、MSW Mock 和前端测试基础设施。
- F02：目标地址、自然语言目标、预期行为、凭据引用及运行选项表单。
- F03：任务分页列表、状态/判定、任务详情、空状态和错误处理。
- F04：C4 执行时间线、连续序号、去重、缺口恢复、终态关闭和详情校准。
- F05：排队/运行中取消交互、防重复提交和终态竞争重新查询。
- F06：结构化报告、用例/步骤/断言、C5 证据读取与 ZIP 下载。
- 场景与应用：浏览器本地场景库、应用配置、JSON 导入和批量运行；运行时统一转换成 C1 创建任务请求，不增加后端私有接口。
- 环境与设置：展示前端模式、契约状态和 Vue/FastAPI/WAATA 的配置边界，不返回或展示 DeepSeek API Key。

场景与应用保存在当前浏览器的 Local Storage，适合作为提交模板，不是平台持久化数据。C1 当前没有删除 Run 的端点，因此前端不提供虚假的任务删除功能。

## 本地运行

依赖已安装时直接运行：

```bash
npm run dev
```

开发服务器固定使用 <http://127.0.0.1:5173>，`strictPort` 已启用，端口被占用时会明确失败，不会自动切换。

开发模式默认启用基于正式 JSON/SSE 样例的 Mock，不依赖 FastAPI、WAATA Package 或真实被测站点。连接真实 FastAPI 时禁用 Mock，同源 `/api` 会代理到 `http://127.0.0.1:8000`。

PowerShell：

```powershell
$env:VITE_API_MOCKING='disabled'
npm run dev
```

Bash：

```bash
VITE_API_MOCKING=disabled npm run dev
```

如需重新安装依赖且不希望 npm 缓存写入 C 盘，可先把缓存配置到 E 盘：

```powershell
$env:npm_config_cache='E:\npm-cache'
npm install
```

## 页面与数据来源

| 页面       | 路径             | 数据来源                            |
| ---------- | ---------------- | ----------------------------------- |
| 场景与应用 | `/scenarios`     | 浏览器 Local Storage；运行时调用 C1 |
| 新建任务   | `/runs/new`      | C1 `POST /api/v1/test-runs`         |
| 运行与报告 | `/runs`          | C1 分页列表                         |
| 运行详情   | `/runs/{run_id}` | C1 详情、C4 SSE、C1 报告及 C5 证据  |
| 环境与设置 | `/settings`      | 前端构建配置和静态契约信息          |

## 验证

```bash
npm run format:check
npm run typecheck
npm run lint
npm run test
npm run build
npm run test:e2e
```

单元和组件测试位于 `tests/`，浏览器流程位于 `e2e/`。未安装 Playwright 浏览器时，可以通过 `WAATA_BROWSER_EXECUTABLE` 复用本机 Chrome：

```powershell
$env:WAATA_BROWSER_EXECUTABLE='C:\Program Files\Google\Chrome\Application\chrome.exe'
npm run test:e2e
```

当前验证覆盖 F01–F03 的主要通过条件，以及 F04–F06 的契约样例重放、基础事件顺序、排队取消、报告状态和 JSON 证据流程。以下边界仍需补齐后才能将 F04–F06 标记为完整验收：

- F04：真实连接断开、重复事件、keep-alive、切换 Run、未来游标恢复上限和 `204` 后停止重连的完整客户端测试。
- F05：运行中 `202`、最终终态刷新和完成/取消竞争 `409` 的组件测试。
- F06：截图预览、ZIP 下载以及证据 `404`、`410`、`503` 的组件反馈测试。
- F07：真实 OpenAPI 快照、FastAPI + FakeTestEngine 以及最终 WAATA Package 联合验收。

## API 类型

`src/api/types.ts` 当前按 C1、C4、C5 和共享样例手工维护。后端导出 `contracts/http/openapi.json` 后运行：

```bash
npm run generate:api
```

生成类型写入 `src/api/schema.d.ts`。随后需要让 API 层使用快照类型，并执行 C1-AT-06 类型检查。

## 当前外部依赖

- 后端 B02 提供 `contracts/http/openapi.json` 和任务查询服务。
- 后端 B04 提供真实报告与取消事务。
- 后端 B05 提供 SSE 重放、心跳、游标和 `204` 行为。
- 后端 B06 提供 C5 证据授权、过期和存储错误响应。
- F07 最终联调依赖后端 B02–B06；最终联合验收还依赖 B07 和 WAATA W08。
