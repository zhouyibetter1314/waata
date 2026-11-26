# C2 · WAATA Python API

Worker 和独立 Python 调用方使用同一个测试引擎。引擎处理规划、执行、验证和报告，平台处理排队、授权与持久化。[包入口](../../packages/waata/src/waata/orchestrator/__init__.py) · [独立运行](../../packages/waata/README.md)

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

从 `waata.orchestrator` 导入 `TestEngine`、`TestRequest`、`TestOptions`、`TestResult`、`WAATAError` 和 `EventCallback`。从 `waata.orchestrator.config` 导入 `EngineConfig`。常用实现为 `waata.llm.OpenAILike`、`waata.browser.PlaywrightAdapter`、`waata.observability.LangfuseObserver`，证据接口为 `waata.artifacts.ArtifactStore`。调用方持有底层模型、Browser、存储及观测客户端。引擎为每个用例管理独立的 BrowserContext、Page 和 Agent 上下文。

平台传入已有的 Run ID，独立调用可由引擎生成。引擎按产生顺序等待 `on_event`，Worker 在事件持久化后返回。回调失败时引擎停止操作、清理会话并报 `EVENT_DELIVERY_FAILED`。可选 Observer 独立记录追踪元数据，观测异常按尽力而为处理。[C4 事件](../events/c4-test-run-events.md)

## 3. 请求与配置

| `TestRequest` 字段 | 要求 |
| --- | --- |
| `target_url` | 绝对 HTTP(S) URL，禁止内嵌用户名和密码。运行时仍须通过适配器的目标策略校验 |
| `goal`、`expected_behavior` | 非空测试目标及预期 |
| `credential_ref` | 可选的授信测试凭据集合引用，适配器向模型提供字段级引用，由浏览器根据目标输入位置解析 |
| `options.max_steps_per_case` | 可选正整数，`None` 继承配置默认值，允许值由可信上限决定 |

`EngineConfig` 默认每用例 16 步（上限 50）及 8 个检查点，每 Run 最多 8 个用例、35 次浏览器动作、160 次工具尝试、48 个模型请求、200000 个模型 token、120 秒。单个引擎默认最多并发两次运行，等待该引擎的并发许可计入 Run 期限。Worker 另有领取并发和浏览器配置，HTTP 的 `options.headless` 在 Worker 消化。独立调用方可用 `setup_case(run_id, case_id)` 在创建会话前准备各用例夹具。[配置模型](../../packages/waata/src/waata/orchestrator/config.py) · [动作计数](../tools/c3-browser-tools.md#72-预算和副作用) · [平台配置](../../apps/api/README.md)

## 4. 结果与判定

`EngineConfig.capture_final_screenshot` 默认为 `false`。开启后，用例到达目标页面时在检查点验证后尝试保存截图。截图沿用适配器的策略、遮罩和运行限制，业务判定由检查点证据决定。[证据契约](../artifacts/c5-test-evidence-artifacts.md)

| 用例判定 | 条件 |
| --- | --- |
| `passed` | 全部检查点有观察证据且匹配 |
| `blocked` | 夹具准备失败，或验证未通过且遇到权限、动作或凭据限制 |
| `failed` | 已确认至少一个检查点不满足预期，且未被策略阻塞 |
| `inconclusive` | 有效证据不足以作出上述判定 |

结果使用 `succeeded` 表示流程完成，总体判定按 `failed > blocked > inconclusive > passed` 聚合。合法空计划得到 `inconclusive`。Verifier 以 `browser.inspect` 的已登记观察支持断言，稳定的同页不匹配才计为失败。未确定的断言使用 `passed=null`。截图受策略限制时工具仍可能返回 `ACTION_NOT_ALLOWED`，断言继续以已登记的检查点观察判定。

用例如果指定终态 URL 路径前缀，Verifier 先检查路径。路径未确认时，页面内容断言保持未判定，避免将编辑器预览或中间页面计作发布结果。

| 模型 | 内容 |
| --- | --- |
| `TestResult` | `run_id`、`status`、`verdict`、`error`、`execution`、`cases`、`artifacts`、`langfuse_trace_id` |
| `ExecutionContext` | 脱敏后的 `target_url` 及实际生效的 `max_steps_per_case`、`max_browser_actions_per_run`、`max_test_cases`、`timeout_seconds` |
| `TestCaseResult` | 用例 ID、名称、前置条件、预期、判定、原因、步骤及断言 |
| `StepResult`、`ToolCallSummary` | 步骤 ID、摘要及其工具调用，含调用 ID、工具名、成功状态、耗时、错误码及证据 ID |
| `AssertionResult` | 断言 ID、预期与实际的 JSON 标量、可空的 `passed` 及同用例观察证据 ID |
| `RunError`、`ArtifactRef` | 错误码和脱敏说明，或 C5 的可移植证据元数据 |

技术故障抛出 `WAATAError`。其 `error` 提供错误详情，`partial_result` 可保留已开始用例及证据，状态为 `errored`、总体判定为 `null`。技术故障中断的用例可保留空判定，未完成的工具调用可保留空状态和耗时。证据引用可在同一报告的 `artifacts` 中找到。[结果模型](../../packages/waata/src/waata/orchestrator/models.py) · [样本请求](examples/4gaboards-test-request.json) · [样本结果](examples/4gaboards-test-result.json)

## 5. 故障与取消

- 引擎先停止操作和清理会话，再返回或传播错误。常见运行错误包含 `CONFIGURATION_ERROR`、`MODEL_UNAVAILABLE`、`MODEL_RATE_LIMITED`、`BROWSER_ERROR`、`RUN_TIMEOUT`、`EVENT_DELIVERY_FAILED`、`CLEANUP_FAILED`、`INTERNAL_ERROR`。收到模型限流后，在运行期限和重试预算内按供应商给出的等待时间重试。
- 规划响应经过 JSON 和检查点校验。首轮不合格时，使用字段级诊断及完整检查点结构请求修复一次。仍未得到合法计划时返回 `MODEL_PLAN_INVALID`。
- Worker 取消执行协程。常规取消在清理后传播 `asyncio.CancelledError`，平台保留已有进度与证据。正常取消分支的报告接口返回 `REPORT_UNAVAILABLE`。必要清理失败时按 `CLEANUP_FAILED` 处理。
- 步骤、动作或 Runner 模型额度到限后，以剩余期限和可用证据完成验证。规划阶段模型预算不足报 `CONFIGURATION_ERROR`，Run 超时报 `RUN_TIMEOUT`。
- Agent 一轮只做页面观察且页面未变化时，下一轮由引擎再次刷新页面。如果页面仍未变化，这一轮直接把观察结果提供给 Agent，暂缓再次提供观察工具。

[浏览器工具](../tools/c3-browser-tools.md) · [证据存储](../artifacts/c5-test-evidence-artifacts.md) · [引擎集成测试](../../packages/waata/tests/test_engine_integration.py) · [独立使用验收](../../docs/04-acceptance.md#ac-07-独立使用与可复现性)
