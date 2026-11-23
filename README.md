# WAATA

WAATA（Web App Auto Test App）是面向 Web 应用功能测试和回归测试的平台。用户通过 Vue 前端提交目标地址、自然语言测试目标和预期结果，并查看运行进度、断言和证据。FastAPI 后端负责任务调度和结果访问，平台使用 PostgreSQL 17 保存运行状态、事件、报告和证据元数据。

后端通过独立的 `waata` Python 包编排测试。该包全称为 Web App Auto Test Agent，负责规划用例、通过 Playwright 在受控站点执行测试、验证结果并生成报告。详见 [waata Python 包](packages/waata/README.md)。

## 从空环境启动

1. 准备 Python 3.12+、uv、Node.js 22.12+、npm 和 Docker。启动独立的 WAATA PostgreSQL 17 容器并应用全部迁移。 [数据库与 Python 环境](apps/api/README.md#准备数据库和依赖)
2. 配置根目录 `.env`，启动自建登录站点、FastAPI、Worker 和 Vue。使用本地 Mock 浏览页面时，只需启动 Vue。 [真实平台启动](apps/api/README.md#本地登录夹具) · [前端 Mock](apps/web/README.md#本地运行)
3. 提交基准版和回归版登录场景，依次核对运行状态、判定、事件及证据。 [手工验收](docs/04-acceptance.md)

需要追踪时，从仓库的 Langfuse 子模块启动 `v4.30.0`。需要额外测试站点时，初始化 4gaBoards、Admidio 或 Discourse 的固定版本子模块。 [本地依赖与重建](infra/README.md)

## 项目结构

| 路径 | 职责 |
| --- | --- |
| [`apps/web/`](apps/web/README.md) | Vue 3 前端，包含场景库、任务提交、运行详情和报告 |
| [`apps/api/`](apps/api/README.md) | FastAPI 与独立 Worker，负责 HTTP API、执行、运行持久化和证据访问 |
| [`packages/waata/`](packages/waata/README.md) | 独立的 `waata` Python 包，负责测试编排、Agent 运行、模型调用、浏览器适配与追踪 |
| [`contracts/`](contracts/README.md) | HTTP、Python 包、工具、事件、证据与平台持久化的 v0.1 契约 |
| [`migrations/`](migrations/README.md) | PostgreSQL 17 的版本化 SQL 迁移 |
| [`examples/`](examples/README.md) | 独立调用 `waata` Python 包的示例 |
| [`testsites/`](testsites/README.md) | 4gaBoards、Admidio、Discourse，以及自建登录夹具 |
| [`infra/`](infra/README.md) | Langfuse 子模块与本地 Compose 配置 |
| `tests/` | 共享契约和全链路自动化测试 |
| `artifacts/` | API 与 Worker 的本地证据目录，受 Git 忽略规则覆盖 |

根目录的 uv 工作区包含 `apps/api` 和 `packages/waata`，统一锁定 Python 依赖。后端通过工作区依赖引用 `waata`，前端单独管理 JavaScript 依赖。应用与核心包的职责见 [系统架构](docs/03-architecture.md)。

## 契约示例

[4gaBoards 端到端示例](contracts/examples/README.md)展示 C1～C6 如何贯通任务提交、执行、持久化与结果查看。

## 项目规约

- [项目愿景](docs/01-project-vision.md)说明用户、目标和 v0.1 的范围。
- [软件需求规格说明](docs/02-requirements.md)定义功能、质量属性与可追踪的需求编号。
- [系统架构](docs/03-architecture.md)说明模块边界、依赖方向和运行流程。
- [MVP 与验收](docs/04-acceptance.md)定义受控登录场景和对应的验证方式。
- [开放问题](docs/05-open-questions.md)记录团队需要评审或实验验证的事项。
- [ADR 0001](docs/adr/0001-package-boundary.md)记录独立 Python 包的边界决策。
- [团队协作规约](CONTRIBUTING.md)和 [AI 开发约定](AGENTS.md)说明开发与提交规范。
