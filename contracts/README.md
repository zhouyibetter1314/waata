# WAATA 跨模块契约

[4gaBoards 端到端示例](examples/README.md)展示 WAATA v0.1 从提交任务到查看报告的 C1～C6 数据流。

## 项目结构

```mermaid
flowchart LR
    Web["Vue 前端"]
    Backend["FastAPI 后端"]
    Database[("PostgreSQL 17")]

    Web <-->|"C1 · 任务与报告<br/>C4 · SSE 执行进度<br/>C5 · 证据读取"| Backend
    Backend <-->|"C6 · 运行、事件、报告与证据元数据"| Database
```

## 后端如何调用 WAATA

```mermaid
flowchart TB
    Web["Vue 前端"]

    subgraph Backend["平台后端"]
        API["FastAPI<br/>校验请求与权限"]
        Worker["Worker<br/>调度、取消与依赖注入"]
        Database[("PostgreSQL 17")]
        Artifacts[("ArtifactStore")]

        API <-->|"C6 · 排队、请求取消与查询"| Database
        Worker <-->|"C6 · 领取任务、读取取消标记<br/>提交状态、报告与 C4 事件"| Database
        API -->|"C5 · 授权后读取证据"| Artifacts
    end

    WAATA["waata · 独立 Python 包"]
    Langfuse["Langfuse（可选）"]

    Web -->|"C1 · 目标 URL、测试目标与预期行为<br/>凭据引用与运行选项"| API
    API -->|"C1 · 状态与报告<br/>C4 · SSE 推送与重放<br/>C5 · 证据"| Web
    Worker -->|"C2 · TestRequest、run_id、on_event"| WAATA
    WAATA -->|"C2 · 结果或执行异常<br/>C4 · 进度回调"| Worker
    WAATA -->|"C5 · Playwright Trace、截图等"| Artifacts
    WAATA -->|"模型、工具与验证追踪"| Langfuse
```

Worker 将模型、浏览器适配器、证据存储和可选的 Observer 注入 TestEngine，并为 C4 事件编号后持久化。报告通过 `langfuse_trace_id` 关联 Langfuse 追踪。

## WAATA 包内部结构

```mermaid
flowchart TB
    Caller["Python 调用方<br/>Worker、CLI 或脚本"]

    subgraph Package["独立 waata Python 包"]
        Engine["orchestrator · TestEngine<br/>规划 → 执行 → 验证 → 报告"]
        Agent["core · Agent Runtime"]
        Browser["browser · BrowserAdapter<br/>每次运行隔离 BrowserContext 和 Page"]
        LLM["llm · 模型接口"]
        Observer["observability · Observer（可选）"]

        Engine -->|"执行用例"| Agent
        Agent <-->|"C3 · 工具调用与观察结果"| Browser
        Engine -->|"规划与语义验证"| LLM
        Agent -->|"决定下一步动作"| LLM
        Engine -.->|"关联执行追踪"| Observer
    end

    Artifacts["调用方提供的 ArtifactStore"]

    Caller <-->|"C2 · 调用与结果<br/>C4 · on_event 回调"| Engine
    Browser -->|"C5 · 登记浏览器证据"| Artifacts
    Engine -->|"C5 · 保存报告快照（可选）"| Artifacts
```

## 契约索引

| 契约 | 参与模块 | 内容 | 参考 |
| --- | --- | --- | --- |
| [C1 · 测试任务 HTTP API](http/c1-test-run-http-api.md) | Vue ↔ FastAPI | 任务、报告和证据的 HTTP 接口 | [创建请求](http/examples/4gaboards-create-run.json) |
| [C2 · WAATA Python API](waata/c2-waata-python-api.md) | Worker ↔ WAATA | TestEngine、输入输出、错误与取消 | [TestRequest](waata/examples/4gaboards-test-request.json) · [TestResult](waata/examples/4gaboards-test-result.json) |
| [C3 · 浏览器工具](tools/c3-browser-tools.md) | Agent Runtime ↔ BrowserAdapter | 工具输入、结果与执行边界 | [工具调用](tools/examples/4gaboards-tool-calls.json) |
| [C4 · 测试运行事件](events/c4-test-run-events.md) | WAATA → Worker → Vue | 事件信封、终态与 SSE 重放 | [SSE 响应体](events/examples/4gaboards-events.sse) |
| [C5 · 测试证据与产物](artifacts/c5-test-evidence-artifacts.md) | WAATA、存储层、Vue | 证据登记、引用和授权读取 | [证据元数据](artifacts/examples/4gaboards-artifact-views.json) |
| [C6 · 平台持久化](database/c6-platform-persistence.md) | FastAPI、Worker ↔ PostgreSQL | 排队、运行状态、事件、报告和证据元数据的持久化 | [SQL 迁移](../migrations/README.md) |

变更公共契约时，由相关方共同评审，并同步更新来源模型、示例和契约测试。详见 [协作规约](../CONTRIBUTING.md)。
