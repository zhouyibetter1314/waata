# C2 · WAATA Python API 契约

## 1. 范围

定义 TestEngine 的公共接口、输入、测试结果、进度回调和资源生命周期。Worker 管理调度、平台状态及访问权限，WAATA 完成规划、执行、验证和报告构建。核心包独立于 FastAPI、队列和平台数据库。浏览器工具、事件和证据分别见 [C3](../tools/c3-browser-tools.md)、[C4](../events/c4-test-run-events.md)、[C5](../artifacts/c5-test-evidence-artifacts.md)。

## 2. 公共接口

```python
from collections.abc import Awaitable, Callable

EventCallback = Callable[[TestEvent], Awaitable[None]]

class TestEngine:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        browser: BrowserAdapter,
        artifact_store: ArtifactStore,
        observability: Observer | None = None,
        config: EngineConfig | None = None,
    ) -> None: ...

    async def run(
        self,
        request: TestRequest,
        *,
        run_id: str | None = None,
        on_event: EventCallback | None = None,
    ) -> TestResult: ...
```

| 公共对象 | 导入位置或用途 |
| --- | --- |
| `TestEngine`、`TestRequest`、`TestResult`、`WAATAError` | `waata.orchestrator` |
| `EngineConfig` | `waata.orchestrator.config`，可信默认值、资源上限与收尾期限 |
| `OpenAILike`、`PlaywrightAdapter`、`Observer` | 分别从 `waata.llm`、`waata.browser`、`waata.observability` 导入。后者同时提供可选的 `LangfuseObserver` |
| `TestEvent` | `waata.core.events`，参数结构见 C4 |
| `ArtifactStore` | 调用方注入的存储能力，保存并登记结构见 C5 |

`run()` 异步完成整次测试并收尾。平台传入创建任务时分配的 `run_id`，独立调用可省略并由引擎生成。同一次运行的报告、进度和证据复用该标识。引擎在调用方协程中按产生顺序等待 `on_event` 完成。Worker 的回调只在事件持久化后返回。若回调最终失败，引擎停止新增动作、清理资源，并以 `EVENT_DELIVERY_FAILED` 报告。Observer 独立记录追踪，平台事件发布走回调。

## 3. 请求与配置

| 字段 | Python 类型 | 约束 |
| --- | --- | --- |
| `target_url` | `str` | 绝对 HTTP(S) URL，禁止内嵌用户名或密码，执行前按可信策略校验 |
| `goal` | `str` | 非空测试目标 |
| `expected_behavior` | `str` | 非空预期行为，规划器据此生成用例检查点 |
| `credential_ref` | `str \| None` | 可选，默认 `None`，指向为此 Run 授权的测试凭据集合 |
| `options` | `TestOptions` | 可省略，默认使用引擎配置 |
| `options.max_steps_per_case` | `int \| None` | 正整数，缺省继承引擎默认值，由可信上限约束 |

[C1](../http/c1-test-run-http-api.md) 的 `options.headless` 由 Worker 据此选择注入的 Browser。可信凭据解析器把已授权集合映射为 C3 允许使用的字段级 `secret_ref`。结果、公开事件和普通日志均须省略凭据值与引用。

Agent 每启动一个步骤扣一个用例步骤额度，单步允许零个或多个工具调用。C3 的浏览器动作预算整次 Run 共享，由 `EngineConfig.max_browser_actions_per_run` 配置。独立约束还包括用例数、总时间、模型用量和工具尝试次数。课程的 35 次操作要求以教师确认的计数口径为准，测试配置须单独核对 [Q-005](../../docs/05-open-questions.md#q-005-运行预算与基线)。

## 4. 结果与判定

生命周期使用 `queued`、`running`、`succeeded`、`errored`、`cancelled`。Worker 持有平台生命周期。正常返回的 `TestResult` 采用 `succeeded`，技术错误携带的部分结果采用 `errored`。

| 判定 | 含义 |
| --- | --- |
| `passed` | 所有必需断言均有支持证据且满足预期 |
| `failed` | 有可靠证据表明至少一项必需断言不满足预期 |
| `blocked` | 因权限、环境或前置条件受阻，无法完成验证 |
| `inconclusive` | 执行产生的有效证据不足以支持结论 |

`succeeded` 时总体判定按 `failed > blocked > inconclusive > passed` 聚合。空计划作为无有效用例处理，正常生成说明并返回 `inconclusive`。其余生命周期的总体 `verdict` 为 `null`。用例的 `verdict` 在技术故障中断且未判定时可为 `null`。课程若还需要独立分类，参见 [Q-006](../../docs/05-open-questions.md#q-006-结果可信度)。

下列字段为报告模型的固定字段。可空字段序列化为 `null`，空列表序列化为 `[]`。

| 模型 | 字段与约束 |
| --- | --- |
| `TestResult` | `run_id: str`、`status`、`verdict`、`error: RunError \| None`、`execution: ExecutionContext`、`cases: list[TestCaseResult]`、`artifacts: list[ArtifactRef]`、`langfuse_trace_id: str \| None` |
| `RunError` | `code: str`、`message: str`，面向调用方的稳定错误码与脱敏短说明 |
| `ExecutionContext` | `target_url: str`（脱敏）、`max_steps_per_case: int`、`max_browser_actions_per_run: int`、`max_test_cases: int`、`timeout_seconds: float`，均为实际生效值 |
| `TestCaseResult` | `case_id: str`、`name: str`、`preconditions: list[str]`、`expected_behavior: str`、`verdict`、`reason: str \| None`、`steps: list[StepResult]`、`assertions: list[AssertionResult]` |
| `StepResult` | `step_id: str`、`summary: str \| None`、`tool_calls: list[ToolCallSummary]` |
| `ToolCallSummary` | `tool_call_id: str`、`tool: str`、`success: bool \| None`、`duration_ms: int \| None`、`error_code: str \| None`、`evidence_ids: list[str]`，未完成的工具调用保留 `success=null`、`duration_ms=null`、`error_code=null` |
| `AssertionResult` | `assertion_id: str`、`expected` 和 `actual` 为 JSON 标量，`passed: bool \| None`，`evidence_ids: list[str]`。无法判定时 `passed=null`，未观测时 `actual=null` |
| `ArtifactRef` | 可移植的证据元数据见 C5，HTTP 访问字段由平台添加 |

用例、步骤和断言 ID 在所属 Run 内按各自类型唯一。正常报告收录所有计划用例，部分报告可包含未判定的已开始用例，并保留已完成的断言及其证据。报告中的证据引用均可在同一报告的 `artifacts` 找到。断言为 `true` 或 `false` 时应包含有效证据。技术错误报告填入 `error`，正常报告的 `error=null`。HTTP 映射示例见 C1。

## 5. 生命周期、错误与取消

调用方持有 LLM 客户端、Playwright Browser、Langfuse 客户端和底层存储。WAATA 管理隔离的 BrowserContext、Page、Agent 上下文、预算和本次 Run 的资源。完成、故障或取消后，先停止新动作，在有限收尾时间内完成允许保存的证据和会话清理，保留原始故障原因。

| 情况 | WAATA 与 Worker 的处理 |
| --- | --- |
| 应用断言不满足，或某个用例因前置条件受阻 | 正常返回 `TestResult`，通过用例判定表达 |
| 工具失败可恢复 | 留下工具记录，由编排层判断是否重新观察。重复动作遵循 C3 |
| 用例步骤或共享动作额度耗尽 | 停止相应动作，按已有证据判定。证据不足时通过 `inconclusive` 和原因表达 |
| 无法完成运行 | 抛出 `WAATAError`，携带 `RunError` 及可用时的 `partial_result: TestResult \| None`。Worker 持久化 `errored` |
| Worker 取消执行协程 | WAATA 完成清理后传播 `asyncio.CancelledError`，Worker 写入 `cancelled`。必要清理失败时抛出带 `CLEANUP_FAILED` 的 `WAATAError` 并保留取消原因，Worker 写入 `errored` |
| 取消时仍有已保存证据 | 保留已持久化的进度和证据。v0.1 的取消分支无测试报告 |

WAATA 的运行错误码包括 `CONFIGURATION_ERROR`、`MODEL_UNAVAILABLE`、`BROWSER_ERROR`、`RUN_TIMEOUT`、`EVENT_DELIVERY_FAILED`、`CLEANUP_FAILED`、`INTERNAL_ERROR`。总运行时间耗尽使用 `RUN_TIMEOUT`。Worker 对报告提交或自身执行故障使用 `REPORT_WRITE_FAILED` 或 `WORKER_ERROR`，并按 C4 完成终态发布。常规工具错误码来自 C3。若错误发生在 HTTP 任务创建后，通过已接受任务的状态和报告呈现。

## 6. 示例

4gaBoards 场景的 [TestRequest](examples/4gaboards-test-request.json) 与 [TestResult](examples/4gaboards-test-result.json) 可用于 Worker 联调。

```python
from waata.browser import PlaywrightAdapter
from waata.llm import OpenAILike
from waata.orchestrator import TestEngine, TestRequest

engine = TestEngine(
    llm=OpenAILike(**model_config),
    browser=PlaywrightAdapter(
        browser=browser,
        allowed_origins={"https://demo-app.test"},
        credential_sets=credential_sets,
    ),
    artifact_store=artifact_store,
    observability=observer,
)
result = await engine.run(
    TestRequest(
        target_url="https://demo-app.test/login",
        goal="验证演示站点的登录流程",
        expected_behavior="有效凭据进入控制台，错误密码显示约定的提示",
        credential_ref="demo_login_fixture",
    ),
    run_id="run_001",
    on_event=store_progress_event,
)
```

注入项由调用方提供。该夹具若触发可验证的登录回归，返回 `succeeded + failed`。若模型服务不可用，引擎抛出 `WAATAError`，错误码为 `MODEL_UNAVAILABLE`，Worker 记录 `errored + null`。

## 7. 契约验收

| ID | 验证条件 |
| --- | --- |
| C2-AT-01 | 用 FakeLLM、FakeBrowserAdapter 和存储替身完成独立调用，验证输入校验、Run ID 和资源归属 |
| C2-AT-02 | 对照 C1 验证字段、判定聚合、空计划以及部分报告中未判定的用例 |
| C2-AT-03 | 回调按顺序收到 C4 进度事件，模拟存储失败时停止并清理 |
| C2-AT-04 | 技术错误、预算耗尽与取消各自保留明确原因，外部资源仍可使用 |
| C2-AT-05 | 断言与步骤可引用已登记的同 Run 证据，公开数据中没有测试秘密 |

## 8. 实现与部署配置

实现时配置用例间夹具重置、默认资源上限与凭据解析器。课程计步和判定映射按课程要求单独核对。见 [开放问题](../../docs/05-open-questions.md)。
