# WAATA

WAATA（Web App Auto Test Agent）面向 Web 应用的功能与回归测试。用户提交目标地址、自然语言测试目标和预期结果，WAATA 生成测试用例，通过 Playwright 操作受控测试站点，并输出含断言、结果和证据的报告。

当前处于需求与架构设计阶段。仓库包含目录骨架、Python 工作区和供团队评审的规约。前端、API 服务、测试引擎和演示站点将在实现阶段接入。

## 项目结构

| 路径 | 职责 |
| --- | --- |
| [`apps/web/`](apps/web/) | Vue 3 前端，负责任务创建、运行进度与报告展示 |
| [`apps/api/`](apps/api/) | FastAPI 应用，负责 HTTP API、任务调度、运行状态与持久化 |
| [`packages/waata/`](packages/waata/) | 独立 Python 包，负责测试编排、Agent 运行、模型调用、浏览器适配与追踪 |
| [`contracts/`](contracts/) | HTTP、Python 包、工具、事件、证据五类跨模块契约 |
| [`examples/`](examples/) | 独立使用 WAATA 的设计示例 |
| [`testsites/demo-app/`](testsites/demo-app/) | 端到端验收使用的受控演示站点 |
| [`tests/`](tests/) | 跨模块契约测试与全系统端到端测试 |
| [`infra/docker/`](infra/docker/)、[`scripts/`](scripts/)、[`.github/workflows/`](.github/workflows/) | 容器、工程脚本和 CI 的预留位置 |
| `artifacts/` | 本地生成的截图、Trace 与报告，受 Git 忽略规则覆盖 |

根目录的 uv 工作区包含 `apps/api` 和 `packages/waata`，统一锁定 Python 依赖。后端通过工作区依赖引用核心包，前端单独管理 JavaScript 依赖。各子模块的职责见[系统架构](docs/03-architecture.md)。

## 项目规约

- [项目愿景](docs/01-project-vision.md)说明用户、目标和 v0.1 的范围。
- [软件需求规格说明](docs/02-requirements.md)定义功能、质量属性与可追踪的需求编号。
- [系统架构](docs/03-architecture.md)说明模块边界、依赖方向和运行流程。
- [MVP 与验收](docs/04-acceptance.md)定义受控登录场景和对应的验证方式。
- [开放问题](docs/05-open-questions.md)记录团队需要评审或实验验证的事项。
- [ADR 0001](docs/adr/0001-package-boundary.md)记录独立 Python 包的边界决策。
- [团队协作规约](CONTRIBUTING.md)和 [AI 开发约定](AGENTS.md)说明设计阶段的协作方式。
