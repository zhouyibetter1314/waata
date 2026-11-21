# WAATA 开发约定

- 修改行为前查看 [SRS](docs/02-requirements.md)、[验收规约](docs/04-acceptance.md)和相关[契约](contracts/README.md)。跨模块改动同时查看[架构](docs/03-architecture.md)及相关 ADR。
- 保持依赖方向为 Vue → FastAPI → WAATA 公共 Python API。测试编排、Agent 和浏览器执行由 `packages/waata` 提供，核心包独立于 Web 框架、任务队列和平台数据库。通用 `core` 保持独立于测试领域和具体适配器。
- 把授权目标校验和动作限制落实在浏览器执行边界。集成测试使用受控站点与测试数据，凭据配置走运行环境或测试夹具。日志、Trace、报告和示例中的敏感数据须脱敏。
- 用需求编号关联行为变更和验证。涉及公共接口、状态含义或证据引用的变更，按 [CONTRIBUTING.md](CONTRIBUTING.md) 与受影响模块共同评审。

当前阶段可从根目录运行 `uv lock --check` 检查 Python 工作区的锁定状态。应用启动、测试和 lint 命令由对应模块在实际接入后记录。
