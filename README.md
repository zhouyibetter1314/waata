# WAATA

WAATA（Web App Auto Test App）是面向 Web 应用功能测试和回归测试的平台。用户通过 Vue 前端提交目标地址、自然语言测试目标和预期结果，并查看运行进度、断言和证据。FastAPI 后端负责任务调度和结果访问，平台使用 PostgreSQL 17 保存运行状态、事件、报告和证据元数据。

后端通过独立的 `waata` Python 包编排测试。该包全称为 Web App Auto Test Agent，负责规划用例、通过 Playwright 在受控站点执行测试、验证结果并生成报告。详见 [waata Python 包](packages/waata/README.md)。

Vue 前端已可通过 Mock API 本地运行。FastAPI 服务和 `waata` 引擎目前是代码骨架，自建登录夹具待实现。

## 项目结构

| 路径 | 职责 |
| --- | --- |
| [`apps/web/`](apps/web/README.md) | Vue 3 前端，负责任务创建、运行进度与报告展示 |
| [`apps/api/`](apps/api/) | FastAPI 应用，负责 HTTP API、任务调度、运行状态与持久化 |
| [`packages/waata/`](packages/waata/README.md) | 独立的 `waata` Python 包，负责测试编排、Agent 运行、模型调用、浏览器适配与追踪 |
| [`contracts/`](contracts/README.md) | HTTP、Python 包、工具、事件、证据与平台持久化的 v0.1 契约 |
| [`migrations/`](migrations/README.md) | PostgreSQL 17 的版本化 SQL 迁移 |
| [`examples/`](examples/) | 独立调用 `waata` Python 包的设计示例 |
| [`testsites/`](testsites/README.md) | 4gaBoards、Admidio、Discourse，以及计划中的自建登录夹具 |
| `tests/` | 共享契约测试，全系统端到端测试待实现 |
| `infra/docker/`、`scripts/`、`.github/workflows/` | 容器、工程脚本和 CI 的预留位置 |
| `artifacts/` | 本地生成的截图、Trace 与报告，受 Git 忽略规则覆盖 |

根目录的 uv 工作区包含 `apps/api` 和 `packages/waata`，统一锁定 Python 依赖。后端通过工作区依赖引用 `waata`，前端单独管理 JavaScript 依赖。应用与核心包的职责见 [系统架构](docs/03-architecture.md)。

## 测试示例

[4gaBoards 端到端示例](contracts/examples/README.md)展示 C1～C6 如何贯通任务提交、执行、持久化与结果查看。首轮验收使用 [自建登录场景](docs/04-acceptance.md)。

## 项目规约

- [项目愿景](docs/01-project-vision.md)说明用户、目标和 v0.1 的范围。
- [软件需求规格说明](docs/02-requirements.md)定义功能、质量属性与可追踪的需求编号。
- [系统架构](docs/03-architecture.md)说明模块边界、依赖方向和运行流程。
- [MVP 与验收](docs/04-acceptance.md)定义受控登录场景和对应的验证方式。
- [开放问题](docs/05-open-questions.md)记录团队需要评审或实验验证的事项。
- [ADR 0001](docs/adr/0001-package-boundary.md)记录独立 Python 包的边界决策。
- [团队协作规约](CONTRIBUTING.md)和 [AI 开发约定](AGENTS.md)说明开发与提交规范。
