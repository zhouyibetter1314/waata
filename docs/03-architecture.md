# 03 系统架构

本文描述 v0.1 的实现。公共接口、字段和状态语义见 [C1～C6 契约](../contracts/README.md)。

## 系统边界

Vue 通过 HTTP 调用 FastAPI。FastAPI 和独立 Worker 共享 PostgreSQL 17 及私有证据目录。Worker 通过 C2 调用独立的 `waata` Python 包，与受控浏览器、OpenAI 兼容模型和可选 Langfuse 组合执行测试。`waata` 仅依赖调用方注入的平台相关能力。 [契约通信图](../contracts/README.md#项目结构) · [独立 Python 包决策](adr/0001-package-boundary.md)

## 应用层

| 路径 | 职责 |
| --- | --- |
| `apps/web/src/features/catalog` | `/scenarios`，将应用和模板保存在 `localStorage`，批量运行逐项提交 C1 请求 |
| `apps/web/src/features/test-runs` | `/runs/new`、`/runs` 和 `/runs/:runId`，负责创建、查询、取消、时间线和报告 |
| `apps/web/src/features/settings` | `/settings`，显示环境和契约信息 |
| `apps/web/src/api`、`apps/web/src/mocks` | HTTP 客户端、生成的 API 类型及本地开发使用的 MSW 契约模拟 |
| `apps/api/src/waata_api/api`、`schemas`、`services` | C1 HTTP 路由和模型、C4 SSE 及 C5 证据查询 |
| `apps/api/src/waata_api/workers` | 领取和协调 Run，注入依赖并调用 WAATA，提交事件和终态 |
| `apps/api/src/waata_api/repositories`、`infrastructure` | PostgreSQL 队列和事务、私有文件证据存储、部署与策略配置 |

## 一次运行的生命周期

1. FastAPI 校验请求身份、目标 origin、凭据引用和执行选项。排队记录提交后返回 HTTP `202` 和 `run_id`。
2. Worker 使用 PostgreSQL 领取任务，在同一事务写入 `running`、租约及首条 `run.started` 事件。Worker 再次检查目标策略，解析获授权的凭据字段，启动该 Run 的 Chromium 并构建 `TestEngine`。
3. Worker 接收测试引擎的进度回调，持久化带连续序号的 C4 事件。FastAPI 从 PostgreSQL 读取已提交的事件，通过 SSE 按序重放并发送新事件。Vue 按 Run ID 和序号维护时间线，收到终态后重新查询详情。
4. Worker 原子提交运行终态、可用报告及相关事件。`succeeded` 可搭配 `passed`、`failed`、`blocked` 或 `inconclusive`。技术故障对应 `errored`，取消生效对应 `cancelled`。两者的总体判定均为空。

Worker 心跳续租时读取取消标记。数据库根据执行令牌和租约校验事件、证据元数据及终态写入。失去租约的运行以 `WORKER_ERROR` 收尾，已提交的历史继续可查。部署按顺序应用 SQL 迁移后再启动 API 和 Worker。 [C1](../contracts/http/c1-test-run-http-api.md) · [C4](../contracts/events/c4-test-run-events.md) · [C6](../contracts/database/c6-platform-persistence.md) · [SQL 迁移](../migrations/README.md)

## 核心包

| 模块 | 职责 |
| --- | --- |
| `waata.orchestrator` | 对外暴露 `TestEngine`，生成计划、运行用例、核对检查点并整理 `TestResult` |
| `waata.core` | 提供 ReAct 循环、上下文、事件与工具注册和执行 |
| `waata.llm` | 提供统一模型接口、OpenAI 兼容适配和独立验证用的替身 |
| `waata.browser` | 抽象浏览器适配、页面观察与测试工具，封装 Playwright 会话、授权检查及证据采集 |
| `waata.observability` | 定义 `Observer` 接口，`LangfuseObserver` 可按同一 Run 关联计划、模型元数据、工具动作和判定 |

规划阶段由模型生成用例及可执行检查点。执行阶段由模型根据页面观察选择注册动作，运行时负责预算、参数和权限检查。用例末尾通过 `browser.inspect` 对 URL、标题、文本、控件存在性、可见性或数量做确定性检查。断言以同一用例已登记的观察作为证据，无法取得充分证据时保留无法判定的结论。 [C2 Python API](../contracts/waata/c2-waata-python-api.md) · [C3 浏览器工具](../contracts/tools/c3-browser-tools.md)

## 资源与隔离

- 调用方持有模型、Playwright Browser 和可选的观测客户端。平台 Worker 为每次 Run 启动并关闭 Chromium，BrowserAdapter 为各用例创建独立的 `BrowserContext` 和 Page。站点数据库等共享业务状态由夹具负责重置。 [隔离待验事项](05-open-questions.md#q-004-运行和用例隔离)
- 每个用例持有独立的 Agent 历史和检查点缓存。运行级预算涵盖时间、动作、工具尝试和模型用量，每用例另有步骤与检查点上限。API 和 Worker 使用部署方配置的目标策略，浏览器执行层按授权 origin 和动作检查实际操作。
- `waata` 通过注入的 `ArtifactStore` 保存脱敏的结构化观察和策略允许的遮罩截图。平台将字节保存到私有目录、元数据保存到 PostgreSQL，FastAPI 按权限与有效期提供读取。原始 Playwright Trace 采集关闭。可选的 Langfuse 保存运行追踪元数据，并用报告中的 `langfuse_trace_id` 关联。 [C5 证据](../contracts/artifacts/c5-test-evidence-artifacts.md) · [后端配置](../apps/api/README.md#运行设置) · [本地 Langfuse](../infra/README.md#langfuse)
