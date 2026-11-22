# 03 系统架构

公共接口、字段和状态语义以 [v0.1 契约](../contracts/README.md)为准。

## 系统边界

Vue、FastAPI 与 PostgreSQL 17 构成平台。Worker 通过 C2 调用独立的 WAATA Python 包。通用 `core` 执行注册的工具，浏览器适配层提供 Playwright 工具。平台、后端调用和包内部结构见 [契约通信图](../contracts/README.md#项目结构)。

## 应用层

| 路径 | 职责 |
| --- | --- |
| `apps/web/src/api` | HTTP 客户端和前端 API 调用 |
| `apps/web/src/features/test-runs` | 任务创建、运行与报告视图，以及对应组件和 Pinia 状态 |
| `apps/web/src/components`、`apps/web/src/router` | 通用组件与路由 |
| `apps/api/src/waata_api/api/v1`、`schemas` | HTTP 路由、请求和响应 |
| `apps/api/src/waata_api/services`、`workers` | 任务协调和 WAATA 调用 |
| `apps/api/src/waata_api/repositories`、`infrastructure` | 运行记录、证据存储、队列和数据库适配 |

创建任务后，API 分配 Run ID，持久化排队记录后返回 `202`。Worker 领取任务，执行长任务并为 C4 事件编号。Vue 通过 C1 查询状态和报告，通过 C4 的 SSE 流接收进度。数据库模型与事务边界见 [C6](../contracts/database/c6-platform-persistence.md)，部署中的故障恢复见 [Q-003](05-open-questions.md#q-003-队列持久化与恢复)。

## 核心包

| 模块 | 职责 |
| --- | --- |
| `waata.orchestrator` | 对外暴露 TestEngine，协调 Planner、Runner、Verifier 与 Reporter |
| `waata.core` | 提供 ReAct 循环、上下文、事件与工具注册和执行 |
| `waata.llm` | 提供统一模型接口与 OpenAI 兼容适配，支持 DeepSeek 等兼容服务 |
| `waata.browser` | 抽象浏览器适配、页面观察与测试工具，封装 Playwright 会话和 Trace |
| `waata.observability` | 定义 Observer 接口，将模型调用、工具动作与验证结果串到同一个 Run。Langfuse 是可选实现 |

Planner 把目标和预期转成用例。Runner 在预算内观察页面、选择并调用注册的功能操作、记录实际结果。Verifier 优先执行确定性断言，按需使用模型判断语义，并把结论关联到证据。Reporter 汇总结构化结果与证据引用。引擎的调用方式见 [独立调用示例](../examples/README.md)。

## 资源与隔离

- 调用方创建并持有 Playwright Browser、模型客户端与观测客户端。BrowserAdapter 为每个 Run 建立独立的 BrowserContext 与 Page，负责会话级追踪及退出时清理。共享浏览器进程时仍保持会话隔离。
- 每次 Run 使用独立的 Agent 上下文、验证结果和证据索引。规划、执行、验证可共享模型接口并保留各自的上下文和预算。用例间的测试数据与会话复用策略见 [Q-004](05-open-questions.md#q-004-运行和用例隔离)。
- 浏览器适配层校验授权目标及动作范围。追踪记录保留 Run、用例和步骤关联，以及足以解释结果的观察、动作和短摘要。
- 核心包通过注入的 ArtifactStore 保存观察、截图和 Playwright Trace，并返回结构化报告与证据引用。FastAPI 按 C5 授权读取证据。可选的 Langfuse 追踪通过报告中的 `langfuse_trace_id` 关联。
