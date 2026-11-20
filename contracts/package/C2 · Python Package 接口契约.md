# C2 · Python Package 接口契约

**状态：Draft（待确认）**

**参与模块：** FastAPI Worker、WAATA Python Package

**契约版本：** v0.1-draft

## 1. 目的与适用范围

本契约定义 FastAPI Worker 与 WAATA Python Package 之间的公共接口，包括依赖注入、任务运行、数据模型、事件回调、资源生命周期和错误处理。

本契约不规定 WAATA 内部的 ReAct 实现、Prompt 设计、测试规划算法或浏览器工具的具体实现细节。

WAATA 应能够脱离 FastAPI 独立使用。

## 2. 公共接口

### 2.1 公共导入路径

拟议支持以下导入：

```
from waata.orchestrator import TestEngine, TestRequest, TestResult
from waata.orchestrator.config import EngineConfig
from waata.llm import OpenAILike
from waata.browser import PlaywrightAdapter
from waata.observability import LangfuseObserver
```

### 2.2 TestEngine 初始化

拟议签名：

```
class TestEngine:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        browser: BrowserAdapter,
        observability: Observer | None = None,
        config: EngineConfig | None = None,
    ) -> None:
        ...
```

各参数约定如下：

| 参数            | 必选 | 说明                               |
| --------------- | ---- | ---------------------------------- |
| `llm`           | 是   | 提供模型调用能力                   |
| `browser`       | 是   | 提供网页观察与操作能力             |
| `observability` | 否   | 接收模型、工具与测试执行的追踪信息 |
| `config`        | 否   | 控制运行步数、超时及其他执行策略   |

`TestEngine` 应依赖抽象能力，而不是强制要求某个具体 LLM 服务或监控平台。

### 2.3 测试运行入口

拟议签名：

```
async def run(
    self,
    request: TestRequest,
    *,
    run_id: str | None = None,
    on_event: EventCallback | None = None,
) -> TestResult:
    ...
```

行为约定：

1. `run()` 异步执行完整测试任务，包括规划、执行、验证和报告生成。
2. `run()` 不仅返回下一步浏览器 Action。
3. 调用方可以指定 `run_id`，不指定时由 WAATA 生成。
4. 运行期间通过 `on_event` 可选回调报告执行进度。
5. 测试正常完成时返回 `TestResult`，即使被测应用未通过测试。
6. 框架无法完成运行时应通过定义好的异常或取消语义报告。

## 3. 数据模型

### 3.1 TestRequest

```
class TestRequest(BaseModel):
    target_url: str
    goal: str
```

| 字段         | 类型  | 说明                           |
| ------------ | ----- | ------------------------------ |
| `target_url` | `str` | 被测 Web 应用的入口地址        |
| `goal`       | `str` | 用户使用自然语言描述的测试目标 |

后续可根据需求扩展预期结果、测试数据引用与执行配置。测试凭据不应直接作为普通事件或日志内容输出。

### 3.2 TestResult

拟议最小结构：

```
class TestResult(BaseModel):
    run_id: str
    status: RunStatus
    verdict: TestVerdict | None
    cases: list[TestCaseResult]
    artifacts: list[ArtifactRef]
```

其中：

- `status` 表示测试运行本身的执行状态。
- `verdict` 表示被测应用是否符合测试预期。
- `cases` 保存各测试用例的结果和证据。
- `artifacts` 保存截图、Trace 等证据的引用。

运行状态与测试判定必须分别表达。

例如，测试正常执行并发现登录功能错误时，运行状态可以是 `succeeded`，测试判定为 `failed`。

具体枚举值及结果聚合规则应与 C1、C4 协同评审。

## 4. 事件回调

WAATA 应提供结构化事件回调，使 FastAPI Worker 能够接收测试过程中的进度信息。

拟议接口：

```
EventCallback = Callable[
    [TestEvent],
    Awaitable[None],
]
```

每个事件至少应包含：

- `run_id`：运行标识
- `type`：事件类型
- `timestamp`：事件发生时间
- `payload`：事件数据

事件还应支持关联具体测试用例与执行步骤。

事件名称、事件排序和终态语义以 C4 Events 契约为准。

FastAPI 负责将事件持久化并传递给前端，WAATA 不直接依赖 SSE 或 WebSocket。

回调抛出异常时的处理策略需要团队共同确定。

## 5. 资源生命周期

资源管理应遵循以下原则：

1. LLM、Playwright Browser 和 Langfuse Client 可以由外部调用方创建。
2. WAATA 使用注入的资源，不应擅自关闭外部持有的客户端或 Browser。
3. BrowserAdapter 为每次 Run 创建隔离的 BrowserContext 和 Page。
4. WAATA 负责清理自己创建的测试会话及相关资源。
5. 每次 Run 应有独立的上下文、测试状态和执行证据。
6. Trace、报告等证据应能够通过 `run_id` 关联。

## 6. 错误与取消

WAATA 应区分以下情况：

| 情况                   | 预期处理                      |
| ---------------------- | ----------------------------- |
| 网站不满足测试预期     | 记录测试失败，正常返回结果    |
| 浏览器操作失败但可恢复 | 由 Agent 或 Runner 按策略处理 |
| LLM 服务不可用         | 报告框架运行错误              |
| 测试达到步数或时间限制 | 按终止策略结束并记录原因      |
| 测试被取消             | 停止后续操作并清理运行级资源  |

建议提供统一的 `WAATAError` 异常基类及具体异常类型。

取消 API、超时后的返回规则、部分结果保留方式和回调异常策略，留待团队评审。

## 7. 标准调用示例

```
from waata.orchestrator import TestEngine, TestRequest
from waata.llm import OpenAILike
from waata.browser import PlaywrightAdapter
from waata.observability import LangfuseObserver

engine = TestEngine(
    llm=OpenAILike(**model_config),
    browser=PlaywrightAdapter(browser=browser),
    observability=LangfuseObserver(client=langfuse_client),
)

result = await engine.run(
    TestRequest(
        target_url="https://staging.example.com",
        goal="测试用户登录功能",
    ),
    run_id="run_001",
    on_event=handle_test_event,
)
```

示例中的客户端创建、事件处理函数和资源关闭由调用方实现。

## 8. 契约验收

C2 完成后，应能够验证以下场景：

- 使用 FakeLLM 和 FakeBrowserAdapter 创建 TestEngine。
- 使用 TestRequest 启动并完成一个模拟测试任务。
- 正常完成测试后返回符合类型约定的 TestResult。
- 测试断言失败不会被误认为框架运行异常。
- 通过 on_event 接收结构化执行事件。
- 外部注入资源不会被 TestEngine 错误关闭。
- 执行失败或取消后，运行级资源能够正确清理。

相关测试统一纳入 `tests/contract/`。

