# W01 · 给 yck 的 C2 接入说明

本阶段交付公共模型、依赖注入边界和 `FakeTestEngine`，对应 FR-001、FR-004、FR-005、NFR-001/002/003/005/006 的 W01 部分，以及 C2-AT-01～05 的模型和替身验证。真实规划、浏览器执行、验证和资源清理留待 W02～W08；本次没有完成这些阶段的验收。

## 安装与验证

在仓库根目录使用 Python 3.12+ 和 uv：

```powershell
uv sync --locked --package waata
uv run --locked python -m unittest discover -s tests/contract -v
uv run --locked --package waata python -m unittest discover -s packages/waata/tests/unit -v
uv run --locked --package waata python examples/w01_fake_engine.py
uv run --locked pre-commit run --all-files
```

独立环境可用 `python -m pip install -e packages/waata`。不需要 FastAPI、Playwright、模型 API 或启动 Web 服务。已有 `httpx`、Pydantic 运行依赖保持不变。

修复后实际验证：契约测试 12 项、W01 单元测试 55 项通过，独立示例的五种场景通过。本次变更文件的 pre-commit 检查通过。全仓库 `--all-files` 在隔离副本中检查，只有 `end-of-file-fixer` 因旧 Draft 契约末尾的多余空行失败；其余钩子通过。原仓库的旧 Draft 及其他成员文件保持不变，此已有格式问题仍待单独处理。

新增文件尚未暂存时，`--all-files` 不包含这些文件，可在 PowerShell 补充执行：

```powershell
$w01Files = @(git diff --name-only HEAD -- packages/waata examples/w01_fake_engine.py) + @(git ls-files --others --exclude-standard -- packages/waata examples/w01_fake_engine.py)
uv run --locked pre-commit run --files @w01Files
```

## 公共入口

```python
from waata.orchestrator import (
    TestEngine, FakeTestEngine, TestRequest, TestOptions, TestResult,
    RunError, WAATAError, ExecutionContext, TestCaseResult, StepResult,
    ToolCallSummary, AssertionResult,
)
from waata.orchestrator.config import EngineConfig
from waata.core.events import TestEvent, EventCallback
from waata.artifacts import ArtifactInput, ArtifactRef, ArtifactStore
```

`TestEngine` 的 C2 签名如下，`FakeTestEngine.run` 与其完全相同：

```python
TestEngine(
    *, llm: LLMProvider, browser: BrowserAdapter, artifact_store: ArtifactStore,
    observability: Observer | None = None, config: EngineConfig | None = None,
)
async def run(
    self, request: TestRequest, *, run_id: str | None = None,
    on_event: EventCallback | None = None,
) -> TestResult: ...
```

`LLMProvider`、`BrowserAdapter`、`Observer` 分别位于 `waata.llm`、`waata.browser`、`waata.observability`，W01 仅作为注入类型边界，没有规定或调用任何操作。`ArtifactStore` 规定异步 `save(artifact: ArtifactInput) -> ArtifactRef`。`ArtifactInput.content` 为调用方提供的有界、已脱敏字节；W01 不实现存储或自动脱敏。所有注入对象仍由调用方持有，Fake 不调用或关闭它们。

直接调用真实 `TestEngine.run` 会抛出 `CONFIGURATION_ERROR`，明确说明执行能力尚未实现；Worker 当前应注入 Fake。

## 最小可执行示例

以下代码可在安装后的 Python 环境独立运行；使用空计划替身，按 C2 返回 `succeeded + inconclusive`。

```python
import asyncio
from waata.artifacts import ArtifactInput, ArtifactRef
from waata.orchestrator import FakeTestEngine, TestRequest

class UnusedStore:
    async def save(self, artifact: ArtifactInput) -> ArtifactRef:
        raise AssertionError("Fake does not save artifacts")

async def main():
    engine = FakeTestEngine(
        llm=object(), browser=object(), artifact_store=UnusedStore(),
    )
    request = TestRequest(
        target_url="https://demo-app.test/login",
        goal="验证登录流程",
        expected_behavior="有效凭据进入控制台",
    )
    result = await engine.run(request, run_id="platform_run_001")
    print(result.model_dump_json(indent=2))

asyncio.run(main())
```

`TestRequest.model_validate_json(text)` 读取 C2 请求样例；`TestResult.model_validate_json(text)` 读取结果样例。`model_dump(mode="json")` / `model_dump_json()` 交付可移植报告，固定可空字段保留 `null`，空列表保留 `[]`。不要对报告使用 `exclude_none=True` 或 `exclude_unset=True`。

请求中省略 `credential_ref` 等价于默认 `None`；省略 `options` 使用默认 `TestOptions`，`options=null` 无效。`max_steps_per_case` 缺省或显式 `null` 都继承引擎默认值，`false`、字符串、非整数和非正数无效。`model_fields_set` 可以区分显式提供字段与缺省字段。报告中的 `false`、`0`、`null` 保持各自 JSON 类型，断言 `expected` 和 `actual` 只允许 JSON 标量。

模型校验失败抛出 Pydantic `ValidationError`；进入 `run()` 后发现配置超限或被绕过构造校验的对象，抛出带 `CONFIGURATION_ERROR` 的 `WAATAError`。Worker 应只向用户发布脱敏的错误说明，不直接记录请求或原始校验异常。

## 配置模拟场景

`FakeTestEngine` 保留所有 C2 构造参数，并增加以下仅用于测试的关键字参数：

| 参数 | 行为 |
| --- | --- |
| `result: TestResult | None = None` | 正常返回的结果模板，只接受 `status=succeeded`，可配置四种判定 |
| `error: WAATAError | None = None` | 在预设进度发完及等待门释放后抛出；可携带 `errored + null` 的部分报告 |
| `events: Sequence[TestEvent] = ()` | 按顺序逐个等待回调，不自行生成事件；禁止提供 Worker 生产的生命周期/报告事件 |
| `started: asyncio.Event | None = None` | 入参和预算校验通过后置位，用于确定性同步 |
| `wait_for: asyncio.Event | None = None` | 预设回调完成后等待，置位则继续；调用方可在等待期间取消运行协程 |

`result` 与 `error` 互斥。模板在构造时复制，每次调用再生成独立副本。实际 `run_id` 替换报告、产物元数据及回调事件中的模板 Run ID；报告 `execution` 替换为实际生效的请求与配置。其余用例、断言、证据 ID 和事件 ID 保留，便于精确断言。未传 `result` 或 `error` 时模拟空计划，不生成虚假通过结论。

完整可执行示例见 [`examples/w01_fake_engine.py`](../../examples/w01_fake_engine.py)。它从正式 C2 样例加载模板并运行以下五种场景：

| 场景 | 配置/处理 |
| --- | --- |
| 检查通过 | `result=TestResult.model_validate(data)`，返回 `succeeded + passed` |
| 检查失败 | 更新样例的用例和总体 `verdict="failed"`、断言 `actual=False, passed=False`，正常返回 `succeeded + failed` |
| 技术异常 | `error=WAATAError(RunError(code="MODEL_UNAVAILABLE", message="Scripted model outage"))` |
| 部分报告 | 将样例改为 `status="errored", verdict=None`，设置 `error`，用 `WAATAError(error, partial_result=partial)` 注入；可保留未判定用例、未完成工具调用及已完成断言 |
| 可控取消 | 等待 `started.wait()` 后执行 `task.cancel()`，等待任务传播 `asyncio.CancelledError`，Worker 持久化 `cancelled`，无报告 |

取消也会穿透正在等待的进度回调；Fake 不捕获或吞掉 `CancelledError`。回调普通异常转换为 `EVENT_DELIVERY_FAILED`，停止后续回调，不返回预设的未来结果。取消前已交给 Worker 保存的事件继续保留。Fake 不创建会话，也不执行真实清理或超时逻辑；`CLEANUP_FAILED`、`RUN_TIMEOUT` 等技术分支可通过 `error` 配置。

`events` 只接收 C4 的 WAATA 进度事件。Worker 自己生成 `run.started`、`report.generated` 和唯一终态事件，并在持久化时添加 `sequence`。`TestEvent` 不接收 `sequence`。重放示例 SSE 时需先去掉该平台字段，并筛除 Worker 事件。请用同一个 Fake 实例脚本复现预设序列，事件 ID 在同一 Run 内不可重复。

Fake 只返回预设的 C5 元数据，不写入或生成对应证据文件。证据下载端点测试需要 Worker 自己预置存储夹具。模板证据和事件 ID 用于模拟，跨独立测试运行时需要各自隔离的存储；它们不会由 Fake 重新分配或登记。

## W01 验收修复与待协调事项

P1 已在 `TestCaseResult` 的模型校验边界修复：`passed` 用例中的已记录断言必须全部为 `passed=True`；已判定用例中若存在 `passed=False`，用例必须为 `failed`。技术中断的部分报告仍允许用例 `verdict=None`、断言 `passed=None` 及未完成工具调用。校验不比较 `expected` 和 `actual`，也不自动改写判定。C2 没有定义可选断言标志，本阶段不新增该字段。

`TestResult` 的总体聚合仍使用正式优先级 `failed > blocked > inconclusive > passed`，新增测试覆盖非空计划中所有错误总体判定的拒绝。Fake 现有的模板复制和返回前重新解析会应用新增模型校验，构造后被调用方修改成矛盾状态的模板也会拒绝。公共签名、JSON 字段及依赖声明保持不变。

P2 尚待契约维护方与 yck、报告消费方协调：正式 C2 第 4 节要求空计划生成说明，但固定 `TestResult` 字段没有总体说明字段；`TestCaseResult.reason` 只能用于实际用例，空计划没有用例；正常报告又要求 `error=null`。现有 C4 的 `plan.created` 仅允许 `total_cases`，也没有说明载体。需要共同确定总体说明字段或正式规定另一说明载体，然后同步契约、示例与实现。本次不新增公共字段、不虚构用例，也不把空计划变成技术错误；仍返回 `succeeded + inconclusive`、`cases=[]`、`error=null`。此项作为非阻塞警告保留。

## Run ID、预算与尚待确认项

正式契约为 [`contracts/waata/c2-waata-python-api.md`](../../contracts/waata/c2-waata-python-api.md)。[`contracts/package/C2-FastAPI与WAATA接口契约.md`](../../contracts/package/C2-FastAPI与WAATA接口契约.md) 标记为 Draft，缺少 `artifact_store`、`expected_behavior` 等正式字段，本实现不采用旧签名。正式契约没有规定以下数值和格式，本次选择是可替换的 W01 实现约定：

- 平台 Run ID 为不透明非空字符串，原样保留；省略时生成 `run_` 加 UUID4 的 32 位十六进制值。不要让 Worker 依赖生成前缀。
- 可信默认值：每用例 12 步、整 Run 20 次浏览器动作、最多 2 个用例、120 秒运行期限、5 秒收尾期限。前四项取联调样例数值，不代表已完成性能基线实验。
- `EngineConfig.max_steps_per_case_limit=100` 是 W01 可配置的可信请求上限；默认步数不得超过它，请求超限时拒绝。`TestOptions` 只验证正整数，具体上限由引擎入参校验执行。此字段名称及 100 的数值属于实现配置，正式 C2 没有固定它们。
- `EngineConfig` 的预算和期限必须有限且为正；具体默认值和上限仍需按 [`Q-005`](../../docs/05-open-questions.md#q-005-运行预算与基线) 做基线后确认。Fake 记录这些配置，不模拟实际计步、时间耗尽或动作执行。
- Fake 的公开 `execution.target_url` 移除全部查询和片段。预设结果与事件内容必须由测试调用方提供已脱敏数据，Fake 不具有通用秘密识别能力；实际页面、证据和 Trace 的脱敏留待后续阶段。
- C5 规定字节内容但没有固定 `ArtifactInput` 的内容字段名，本实现采用 `content: bytes`。大小及脱敏策略由可信存储/执行边界实施，W01 不虚构统一字节上限。
- 没有在仓库找到《WAATA v0.1 开发任务拆解.md》，W01 范围依据本次任务提示词；`testsites/demo-app/` 仍是文档规划位置，无现成实现。本次未更改任何站点或子模块指针。

下一阶段 W02 应明确 LLMProvider 的异步操作、计划模型与 FakeLLM；W03 应根据 C3 实现工具注册、参数 Schema、可信调用上下文与串行分发。两者沿用本阶段请求、错误、事件和证据模型，真实预算与资源生命周期在后续 Runner 中落地。
