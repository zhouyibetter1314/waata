# WAATA

WAATA（Web App Auto Test App）面向授权测试环境中的 Web 功能测试。用户在网页提交目标 URL、自然语言测试目标和预期行为，查看实时进度、断言和证据。执行由可独立调用的 `waata` Python 包完成，使用 OpenAI 兼容模型规划和选择浏览器动作，通过 Playwright 执行与验证。

## 本地启动

1. 准备 Python 3.12+、uv、Node.js 22.12+、npm、Docker 和支持工具调用的模型服务。安装锁定依赖与 Chromium，启动 PostgreSQL 17 并执行迁移。[数据库与 Python 环境](apps/api/README.md#准备数据库和依赖)
2. 在根目录配置 `.env` 和目标授权策略，启动 FastAPI、Worker 和 Vue。[平台启动](apps/api/README.md#本地启动与目标配置)
3. 打开 [新建任务](http://127.0.0.1:5173/runs/new)，提交授权站点中的测试场景，复核运行判定和证据。[手工验收](docs/04-acceptance.md)

可单独启动固定版本的 4gaBoards、Admidio 或 Discourse 作为测试目标，也可接入可选的 Langfuse 追踪。[测试站点与启动脚本](testsites/README.md) · [本地依赖](infra/README.md)

## 项目导航

| 阅读目标 | 入口 |
| --- | --- |
| Web 页面、开发代理和前端检查 | [Vue](apps/web/README.md) |
| API、Worker、目标策略和部署 | [后端](apps/api/README.md) |
| 从 Python 调用测试引擎 | [waata 包](packages/waata/README.md) |
| 边界、依赖和一次运行的流向 | [系统架构](docs/03-architecture.md) · [ADR 0001](docs/adr/0001-package-boundary.md) |
| 能力范围、需求编号与验证步骤 | [项目愿景](docs/01-project-vision.md) · [软件需求](docs/02-requirements.md) · [验收](docs/04-acceptance.md) · [开放问题](docs/05-open-questions.md) |
| 接口、事件、证据和数据库 | [C1～C6](contracts/README.md) · [契约样例](contracts/examples/README.md) · [SQL 迁移](migrations/README.md) |
| 可在本地上游站点复现的测试场景 | [场景手册](examples/README.md) |
| Discourse DC-01–DC-11 联调状态、Windows 启停、Agent 复核和重跑 | [结果摘要](docs/testing/discourse-summary.md) · [联调记录](docs/testing/discourse-integration.md) |
| 4gaBoards 五条练习的零模型调用验证、步骤和截图 | [联调记录与复现](docs/testing/4gaboards-integration.md#课程验收快跑) · [验收摘要](docs/testing/4gaboards-summary.md) |
| 开发协作、检查和 PR 流程 | [团队协作](CONTRIBUTING.md) · [仓库约定](AGENTS.md) |
