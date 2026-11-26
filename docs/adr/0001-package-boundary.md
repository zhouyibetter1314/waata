# ADR 0001｜将 WAATA 作为独立 Python 包

状态为已采纳。

平台需要提供 Web 界面、任务调度和浏览器测试执行。Python 调用方也需要独立使用测试规划、执行和验证能力。

在同一仓库维护 Vue、FastAPI 和可独立打包的 `waata`。API 管理 HTTP 与任务入队，独立 Worker 调度执行，通过 uv 工作区依赖调用 `waata.orchestrator.TestEngine`。平台持有数据库和文件存储，通过 `ArtifactStore` 向核心包注入证据能力。通用 Agent Runtime 依赖接口，测试编排负责组装模型和浏览器适配器。

公共契约变更须与调用方协同更新。运行状态、判定和证据的跨层映射由 C1、C2、C4、C5 和 C6 定义。[系统架构](../03-architecture.md) · [公共契约](../../contracts/README.md)
