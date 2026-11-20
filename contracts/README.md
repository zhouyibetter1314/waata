# WAATA 跨模块契约

本目录供团队共同设计和评审。当前记录接口边界、设计问题与预期交付物。路径、签名、字段、状态值及传输语义在对应生产方和消费方评审后确定。

| 编号 | 位置 | 参与模块 | 评审内容与交付物 |
| --- | --- | --- | --- |
| C1 · HTTP API | [`http/`](http/) | Vue、FastAPI | 任务创建、列表、详情、进度、报告和取消。确定 HTTP 方法、响应状态、错误与授权。由 FastAPI 导出 OpenAPI 快照 |
| C2 · Python Package | [`package/`](package/) | FastAPI Worker、WAATA | TestEngine 的依赖注入、运行入口、结果模型、生命周期、错误和取消。由公开 Python 类型与模型提供定义 |
| C3 · Tools | [`tools/`](tools/) | Agent Runtime、BrowserAdapter | 页面观察和常见功能操作的输入、输出与错误，授权校验由执行边界实施。确认工具注册和校验规则 |
| C4 · Events | [`events/`](events/) | WAATA、FastAPI、Vue | 事件标识与版本、Run/Case/Step 关联、终态、排序、重连和去重。确定 WAATA 事件与 SSE 的映射 |
| C5 · Artifacts | [`artifacts/`](artifacts/) | BrowserAdapter、Reporter、后端存储、Vue | 截图、Playwright Trace、报告与 Langfuse 引用，确认元数据、保存和授权访问方式 |

## 跨契约约束

- 运行生命周期和用例判定分别表达。业务断言未满足时，系统仍可正常完成运行并交付报告。
- 事件、报告、截图和 Trace 可关联到同一 Run。产生于特定用例或步骤的记录附带相应标识。
- 结果携带证据元数据和引用。平台为访问证据提供授权检查，Python 包可由调用方提供存储能力。
- FastAPI 的请求和响应模型作为 C1 的来源，OpenAPI 快照从服务导出，前端按快照生成类型。C2 的定义以核心包的公共类型和模型为准。

C1、C2、C4 优先评审。每份契约应包含正常与失败示例，并在实现接入后由 [`tests/contract/`](../tests/contract/) 验证。变更流程见[团队协作规约](../CONTRIBUTING.md)。相关未决事项见[开放问题](../docs/05-open-questions.md)。
