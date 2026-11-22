# C3 · 浏览器工具契约

## 1. 范围

定义 WAATA 注册的七个浏览器工具及其输入、输出、错误与执行边界。BrowserAdapter 封装 Playwright 定位和执行，工具返回实际操作及观察，由 Verifier 按 C2 判定结果。输入模型是 Tool JSON Schema 的生成来源。

首版仅开放第 4 节列出的功能测试操作。执行器禁止任意 JavaScript 和文件读写，调用者接收结构化数据。[C2](../waata/c2-waata-python-api.md) 管理运行生命周期，[C4](../events/c4-test-run-events.md) 定义公开事件，[C5](../artifacts/c5-test-evidence-artifacts.md) 定义证据登记与读取。

## 2. 通用约定

| 项目 | 约定 |
| --- | --- |
| 调用方式 | Python 包内部异步调用，不新增 HTTP/SSE 接口。不得依赖 FastAPI 或平台数据库 |
| 工具名称 | 使用第 4 节列出的 `browser.*` 名称，未知工具在执行前拒绝 |
| 字段与值 | 字段为 `snake_case`。只传 JSON 可序列化值，不传 Page、Locator、文件句柄 |
| Schema | 参数按工具名区分。拒绝未知字段、缺失字段和错误类型，不静默忽略 |
| 时间 | 观察时间使用 ISO 8601 UTC。耗时使用非负整数毫秒 |
| 无结果 | 无数据为 `null`，空集合为 `[]`，不省略返回信封的字段 |
| 凭据 | 普通输入文本和秘密引用分开。秘密在可信执行边界解析，不经模型传递明文 |
| 执行范围 | 工具只操作当前 Run 的当前 Page。同一 Page 的调用串行执行 |
| 重试 | `retryable` 是恢复建议，不代表可以直接重复有副作用的动作 |
| 超时 | 可选 `timeout_ms` 必须是正整数。默认值和服务端上限由有效运行配置给出，不允许 `0` 表示无限等待 |

可信 Runtime 为每次调用提供 `run_id`、可空的 `case_id` 和 `step_id`、在 Run 内唯一的 `tool_call_id`，并绑定授权策略、预算、取消信号、凭据解析和证据保存能力。这些字段位于模型参数之外。`tool_call_id` 用于关联工具记录和证据。重用调用 ID 不会使动作幂等。

`timeout_ms` 只能缩短有效期限。执行期限不得超过工具上限和 Run 剩余期限。读取类调用也受总时间和调用次数限制，不能无限观察绕过运行预算。

### 2.1 调用示例

```json
{
  "tool": "browser.click",
  "arguments": {
    "locator": {
      "strategy": "role",
      "role": "button",
      "name": "登录"
    }
  }
}
```

`tool`、`arguments` 均必填，`arguments` 必须为对象。无参数也传 `{}`。Runtime 从模型提供方的 tool-call 格式转换为此结构，再校验和分发。

### 2.2 结果模型

```json
{
  "success": true,
  "data": {
    "action": "click",
    "url": "https://demo-app.test/dashboard"
  },
  "error": null
}
```

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ELEMENT_NOT_FOUND",
    "message": "未找到匹配的登录按钮",
    "retryable": true
  }
}
```

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `success` | boolean | 只表示工具请求是否完成，不表示用例通过 |
| `data` | object \| null | 成功时为对应工具的数据。失败时为 `null` |
| `error` | ToolError \| null | 成功时为 `null`。失败时必填结构化错误 |
| `error.code` | string | 第 6 节定义的稳定错误码。调用方不解析 message 判断错误类型 |
| `error.message` | string | 已脱敏、可解释的短信息，不含内部路径、堆栈、凭据 |
| `error.retryable` | boolean | 是否可能通过重新观察、等待或修正参数恢复 |

失败响应不保证动作尚未执行。例如，点击分发后发生页面关闭或等待超时，仍可能已经产生副作用。Runtime 应保留已有记录并重新观察，不自动重放点击、提交等动作。

## 3. 共享数据类型

### 3.1 LocatorSpec

`locator` 为判别联合类型，由 `strategy` 决定允许的字段。禁止同时包含不同分支的专有字段。

| strategy | 必填字段 | 可选字段 | Playwright 映射建议 |
| --- | --- | --- | --- |
| `role` | `role`、`name` | `exact`，默认 `true` | `page.get_by_role(role, name=name, exact=exact)` |
| `label` | `value` | `exact`，默认 `true` | `page.get_by_label(value, exact=exact)` |
| `text` | `value` | `exact`，默认 `true` | `page.get_by_text(value, exact=exact)` |
| `placeholder` | `value` | `exact`，默认 `true` | `page.get_by_placeholder(value, exact=exact)` |
| `test_id` | `value` | 无 | `page.get_by_test_id(value)` |
| `css` | `value` | 无 | `page.locator(value)`，仅允许配置中授权的 CSS 定位 |

字符串字段非空。`role` 使用实现明确支持的 ARIA role 白名单。优先使用 role、label 或 test_id，CSS 使用可信配置允许的定位器。参见 [Playwright 定位器文档](https://playwright.dev/python/docs/locators)。

click、fill、select_option 和元素级截图要求唯一匹配。多匹配返回 `AMBIGUOUS_LOCATOR`，禁止使用 `.first()` 隐式选择元素。零匹配可在期限内等待，耗尽后返回 `ELEMENT_NOT_FOUND`。不可见、不可操作与无效选择等情况分别归因，禁止自动替换目标元素。首版不开放 `force` 和任意坐标点击。

inspect 的 `exists`、`count`、`visible` 可以读取多匹配。其精确语义见 5.7。

### 3.2 PageObservation

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `observation_id` | string | 由 BrowserAdapter 生成，在当前 Run 中唯一 |
| `observed_at` | string | 实际采集时间，UTC |
| `url` | string | 采集时的实际授权页面 URL，移除敏感查询值等秘密 |
| `title` | string | 已脱敏的页面标题 |
| `aria` | string | 已脱敏的页面可访问性摘要，不包含整个原始 HTML |
| `elements` | array | 可交互控件摘要，元素字段见下文。无控件为 `[]` |
| `truncated` | boolean | 摘要或控件因大小上限截断时为 `true`。截断结果不得作为页面完整性的证明 |
| `evidence_ids` | string[] | 已登记的当前观察证据引用。失败或尚未持久保存的文件不能作为有效引用 |

`elements` 中每项包含 `locator: LocatorSpec`、`role: str | null`、`name: str | null`、`text: str | null`、`enabled: bool`。只输出当前页相关的可见控件摘要，不回传密码值、隐藏字段、Cookie 或 storage 内容。推荐定位器用于后续动作定位，页面变化后须重新验证其有效性。

同一次观察中的 URL、标题、ARIA、控件和截图不得混用导航切换前后的页面内容。检测到导航变化时，应在有效期限内重新采集。仍无法取得一致观察时返回 `OBSERVATION_UNSTABLE`。页面观察不提供事务级快照一致性保证，Verifier 应结合采集时间和实际证据验证结果。

### 3.3 证据引用

工具数据中的 `evidence_ids` 和截图返回的 `artifact_id` 引用 C5 的登记记录。可信上下文为记录绑定 Run、Case、Step、工具调用及采集时间。用于断言的观察、`inspect` 结果和截图须保存成功后才可引用。保存失败时返回 `ARTIFACT_WRITE_FAILED`，由 C2 判定证据缺口。

## 4. 工具清单

| Tool | 主要输入 | 成功 data | 类别 |
| --- | --- | --- | --- |
| `browser.observe` | 可选观察参数 | PageObservation | 观察 |
| `browser.navigate` | `url` | `action`、实际 `url` | 动作 |
| `browser.click` | `locator` | `action`、实际 `url` | 动作 |
| `browser.fill` | `locator`、`value` 或 `secret_ref` | `action`、实际 `url` | 动作 |
| `browser.select_option` | `locator`、`value` | `action`、实际 `url` | 动作 |
| `browser.screenshot` | 可选截图参数 | `artifact_id`、`kind`、`page_url`、`captured_at` | 取证 |
| `browser.inspect` | 检查条件 | 实际值、比较结果、证据引用 | 检查 |

七个工具均接受可选的 `timeout_ms`。动作成功 data 固定 `action` 为 `navigate`、`click`、`fill`、`select_option`。`url` 是本次操作返回时的脱敏页面 URL。返回成功只说明动作方法已完成，不保证异步业务结果已呈现，Runner 应再 observe/inspect。

## 5. 各工具输入与行为

4gaBoards 场景的调用上下文、输入和结果见 [工具调用示例](examples/4gaboards-tool-calls.json)。

### 5.1 browser.observe

```json
{
  "tool": "browser.observe",
  "arguments": {"include_screenshot": false}
}
```

`include_screenshot` 为可选 boolean，默认 `false`。返回 3.2 定义的 PageObservation。如设为 `true`，同时采集并登记已脱敏的截图，把引用附到 `evidence_ids`。ARIA/控件长度上限由可信配置决定，超限标记 `truncated`，不允许模型关闭保护。

observe 不执行导航或点击，不依据页面文本改变授权或动作权限。没有可用 Page 时返回 `SESSION_NOT_READY`，不得以空观察替代错误响应。

### 5.2 browser.navigate

```json
{
  "tool": "browser.navigate",
  "arguments": {"url": "https://demo-app.test/login"}
}
```

`url` 必填，为非空绝对 HTTP(S) URL。拒绝内嵌用户名/密码、`file:`、`javascript:` 等方案。不接受任意本机地址作为默认授权，允许目标来自调用方策略。

导航前必须校验目标。建议以 `domcontentloaded` 作为返回条件。`networkidle` 不作为统一前置要求。每次重定向以及点击触发的导航同样经过执行边界校验，详见第 7 节。

成功结果的 `data` 形如 `{"action":"navigate","url":"https://demo-app.test/login"}`。HTTP 4xx/5xx 响应本身不直接构成工具执行错误或业务断言结论。页面可正常加载和观察时返回实际 URL，由后续检查判断。网络、TLS 或导航错误返回结构化工具错误。

### 5.3 browser.click

输入为必填 `locator: LocatorSpec`，示例见 2.1。仅点击唯一、可见、可操作的元素，不自动接受额外弹窗或切换标签页。若触发未支持的新窗口、下载或对话框，适配层停止继续操作并返回 `UNSUPPORTED_PAGE_EVENT`，Runner 重新判断已发生的页面状态与副作用。

click 执行成功不表示登录成功、表单校验通过或检查点通过。

### 5.4 browser.fill

普通测试文本使用 `value`。

```json
{
  "tool": "browser.fill",
  "arguments": {
    "locator": {"strategy": "label", "value": "用户名"},
    "value": "demo_user"
  }
}
```

测试秘密使用 `secret_ref`。

```json
{
  "tool": "browser.fill",
  "arguments": {
    "locator": {"strategy": "label", "value": "密码"},
    "secret_ref": "demo_login_fixture.password"
  }
}
```

- `locator` 必填。`value` 与 `secret_ref` 严格二选一，同时提供或均不提供时返回 `INVALID_ARGUMENTS`。
- `value` 是字符串，允许 `""` 以清空输入。只用于非秘密测试数据。已知秘密字段不接受明文 `value`。
- `secret_ref` 是非空的字段级引用，例如 `demo_login_fixture.password`。可信解析器只解析 C2 为本次 Run 授权的夹具条目，禁止读取任意环境变量或文件。错误密码也使用专用夹具引用。
- 输入框必须唯一、可编辑。使用 fill 替换当前内容，不累计追加。成功 data 不回显输入值或解析出的秘密。

### 5.5 browser.select_option

```json
{
  "tool": "browser.select_option",
  "arguments": {
    "locator": {"strategy": "label", "value": "角色"},
    "value": "viewer"
  }
}
```

`locator` 必填且唯一。`value` 必填，为 `<option>` 的 value 字符串（允许空字符串选项）。首版只支持原生 `<select>` 的单值选择，不使用 label/index 替代 value，也不模拟自定义下拉框的隐式多次点击。控件不支持选择或选项不可用时分别返回 `ELEMENT_NOT_INTERACTABLE` / `OPTION_NOT_FOUND`。

### 5.6 browser.screenshot

```json
{
  "tool": "browser.screenshot",
  "arguments": {"full_page": false}
}
```

可选参数为 `full_page: boolean = false` 和 `locator: LocatorSpec`。未传 locator 时截当前视口，`full_page=true` 截整页。传 locator 时只截唯一元素，禁止同时设 `full_page=true`。不允许模型指定文件名、路径、保存后端或关闭脱敏。

成功结果的 `data` 包含下列字段。

```json
{
  "artifact_id": "art_003",
  "kind": "screenshot",
  "page_url": "https://demo-app.test/login",
  "captured_at": "2026-11-21T01:00:00Z"
}
```

`page_url` 是采集时的脱敏页面地址，证据读取地址见 C5。截图受尺寸和字节数限制，且应遮罩密码及可信配置指定的敏感区域。无法确认脱敏时拒绝交付。Trace 在 Run 收尾阶段按 C5 单独登记。

### 5.7 browser.inspect

inspect 执行确定性读取/比较，为 Verifier 提供依据，不运行任意代码，不产生业务最终判定。输入为判别联合，必填的 `condition` 决定其他字段。

| condition | 必填字段 | 返回 `actual` 类型 | `matched` 语义 |
| --- | --- | --- | --- |
| `url_equals` | `expected: string` | string | 实际脱敏 URL 与 expected 精确比较 |
| `title_equals` | `expected: string` | string | 实际页面标题与 expected 精确比较 |
| `exists` | `locator` | boolean | 至少一个匹配则为 `true` |
| `visible` | `locator` | boolean | 至少一个匹配可见则为 `true` |
| `count` | `locator`、`expected: integer >= 0` | integer | 匹配数量等于 expected |
| `text_equals` | `locator`、`expected: string` | string | 唯一可见元素的 `inner_text` 与 expected 比较 |

URL/标题/文本比较都对已脱敏的可展示值执行，不用秘密本身作为断言内容。文本比较仅统一 CRLF 为 LF 并去除首尾空白，不隐式做子串匹配、大小写折叠或语义推断。URL 不做额外的尾斜线等归一化。

`exists`、`visible`、`count` 的“零匹配”是合法的实际观察，`matched=false` 不表示工具错误。`text_equals` 零匹配为 `ELEMENT_NOT_FOUND`，多匹配为 `AMBIGUOUS_LOCATOR`，因为此时无法取得要求的单个文本值。

inspect 读取一次当前可用状态，不自动轮询直到满足预期。`timeout_ms` 约束读取和取证过程。Runner 若需等待，应在整体预算内重新观察。单次观察未发现预期状态，不足以单独认定应用缺陷。

以下调用成功取得观察，实际文本与预期不同。

```json
{
  "tool": "browser.inspect",
  "arguments": {
    "condition": "text_equals",
    "locator": {"strategy": "test_id", "value": "login-error"},
    "expected": "用户名或密码错误"
  }
}
```

```json
{
  "success": true,
  "data": {
    "condition": "text_equals",
    "actual": "服务暂不可用",
    "matched": false,
    "url": "https://demo-app.test/login",
    "observed_at": "2026-11-21T01:00:03Z",
    "evidence_ids": ["art_002"]
  },
  "error": null
}
```

inspect 成功 data 必须包含 `condition`、`actual`、`matched`、`url`、`observed_at`、`evidence_ids`，并引用已登记的 C5 `observation`。Verifier 结合用例预期、前置状态和证据给出 C2 判定。

## 6. 错误、超时与恢复

| code | 触发条件 | retryable 建议 |
| --- | --- | --- |
| `UNKNOWN_TOOL` | 未注册或本 Run 不提供该工具 | `false` |
| `INVALID_ARGUMENTS` | Schema 不匹配、非法 locator、超时越界 | `false`。应修正调用 |
| `TARGET_NOT_ALLOWED` | 目标或重定向不在授权范围 | `false` |
| `ACTION_NOT_ALLOWED` | 动作不在当前授权动作集合 | `false` |
| `SECRET_NOT_AVAILABLE` | 凭据引用未配置、不可访问或不属于当前 Run | `false` |
| `SESSION_NOT_READY` | 会话未创建或已完成清理 | `false` |
| `ELEMENT_NOT_FOUND` | 必需元素在期限内不存在 | `true` |
| `AMBIGUOUS_LOCATOR` | 需要唯一元素时匹配多个 | `true`。重新观察并改定位 |
| `ELEMENT_NOT_INTERACTABLE` | 不可见、禁用、不可编辑或控件类型不符 | 由原因决定 |
| `OPTION_NOT_FOUND` | 指定 option 不可用 | `true`。核对实际选项 |
| `NAVIGATION_FAILED` | 网络、TLS 或导航加载故障 | 由原因决定 |
| `OBSERVATION_UNSTABLE` | 页面切换导致无法取得一致观察 | `true` |
| `TOOL_TIMEOUT` | 单工具期限耗尽 | 由原因决定。副作用可能已发生 |
| `BUDGET_EXCEEDED` | 动作/工具预算已经耗尽 | `false` |
| `RUN_CANCELLED` | 可信上下文已要求停止 | `false` |
| `UNSUPPORTED_PAGE_EVENT` | 首版不支持的弹窗、新页、下载等 | `false` |
| `BROWSER_CLOSED` | 浏览器或会话意外关闭 | `false` |
| `ARTIFACT_WRITE_FAILED` | 证据保存或登记失败 | 由原因决定。不得重放业务动作补证 |
| `INTERNAL_ERROR` | 未分类的适配层异常 | `false` |

错误码面向调用方保持稳定。`message` 必须在移除凭据、内部路径和堆栈后生成，不得直接返回未经处理的 Playwright 异常文本。`retryable` 由执行边界根据实际错误原因设置，超时错误不统一视为可重试。

可预期的参数与工具错误转换为统一结果结构。Python `asyncio.CancelledError` 必须在必要清理后继续向 C2 生命周期层传播，禁止捕获后抑制取消。`RUN_CANCELLED` 用于尚未分发时检测到的取消请求。取消和浏览器崩溃不得按普通定位失败继续执行。

工具错误由 C2 和 Runner 判断如何恢复或结束。HTTP 端点使用 C1 的错误模型。

## 7. 执行限制与生命周期

### 7.1 授权校验

执行边界必须验证当前页面和目标授权，不能只依赖 Prompt 或仅校验首次 navigate。导航、表单提交、点击引起的跳转、重定向及新页面均需要受策略约束。至少按规范化的 scheme/host/port 判断 origin，不做字符串前缀匹配。额外允许的路径、资源 origin、身份提供方由可信配置指定，模型不得扩大白名单。

跨域跳转应在网络/浏览器执行边界拦截。授权检查不得仅在访问完成后对最终 URL 执行。未授权的新页应关闭且不继续交互。首版的新页/下载能力默认关闭。子资源与弹窗的允许策略由 Q-008 共同确认，页面 origin 授权不自动覆盖其全部网络请求。

### 7.2 预算和副作用

Runtime 与执行边界使用同一份可信预算，统一计数并强制执行限制。navigate、click、fill、select_option 在通过参数/授权校验后、分发 Playwright 前原子预占一次动作预算。已分发后即使失败也不退还。Schema 拒绝、授权拒绝和预算拒绝不占浏览器动作次数，但计入工具尝试/总时间限制。

observe、screenshot、inspect 不消耗浏览器动作预算，但受独立调用/时间/证据大小限制。动作预算耗尽后不得继续操作，仍可在剩余收尾期限内观察和保存证据。Playwright 对同一次动作的内置等待不重复计数，Runtime 新发起一次动作则重新计数。Adapter 不做隐式多动作恢复。

`max_steps_per_case` 控制 Agent 步骤数。浏览器动作按 C2 的 `max_browser_actions_per_run` 在整个 Run 内累计，用例切换时继续计数。课程场景的计数口径由团队核对。

### 7.3 资源和敏感信息

- 调用方持有 Browser。Adapter 为每次 Run 建立隔离 BrowserContext 和 Page，退出时只关闭自身创建的会话，不关闭外部 Browser，遵循 C2。
- 工具不得自行创建未受上下文管理的会话、绕过授权导航，或跨 Run 共享 Page、Cookie、证据引用及秘密。
- 取消/故障后停止新动作，在收尾期限内保存允许保留的已有证据与 Trace，再清理 context。清理错误必须单独记录并保留原始错误信息。
- 分别校验截图与 Trace 的脱敏结果。Trace 可能包含 DOM、输入值、网络记录和截图。无法可靠脱敏时，停用相关采集或扣留原件，并在可用的报告中记录证据缺口。
- 同 Run 的 Case 是否重建会话和如何重置测试数据由 C2/Q-004 约定。清空 Cookie 不视为完成业务数据重置。

## 8. 工具注册与实现责任

`waata.core.tools` 负责定义通用 ToolSpec、注册表和执行器。`waata.browser` 负责定义浏览器输入/输出模型、BrowserAdapter 抽象、Playwright 实现及工具绑定。通用 core 不得导入 Playwright 或包含浏览器专有执行分支。

| 责任方 | 交付 |
| --- | --- |
| Agent Runtime | 消费工具 Schema。转换模型调用。校验名称/参数。串行分发。关联 Run/Case/Step。根据结果决定下一步 |
| BrowserAdapter | 提供七个工具的模型与处理函数。执行定位、授权、动作限制、观察和证据采集。将可预期异常转为 ToolError |
| 编排层/C2 | 注入会话、预算、取消、凭据与存储能力。汇总结果和清理生命周期 |
| C4/C5 实现方 | 将脱敏调用摘要和结果映射成事件，将证据引用映射到保存和授权访问机制 |

ToolSpec 至少包含 `name`、`description`、`input_schema` 和异步 `handler`。`input_schema` 从 Pydantic 模型导出。handler 接收校验后的参数与可信调用上下文，返回统一 ToolResult。注册重名须失败。未注册工具不得通过动态执行处理。

下例展示 click 的 role 分支。完整 locator 联合由输入模型生成。

```json
{
  "type": "object",
  "properties": {
    "locator": {
      "type": "object",
      "properties": {
        "strategy": {"const": "role"},
        "role": {"type": "string", "minLength": 1},
        "name": {"type": "string", "minLength": 1},
        "exact": {"type": "boolean", "default": true}
      },
      "required": ["strategy", "role", "name"],
      "additionalProperties": false
    },
    "timeout_ms": {"type": "integer", "minimum": 1}
  },
  "required": ["locator"],
  "additionalProperties": false
}
```

按 C4 发布 `tool.called` 和 `tool.completed` 的脱敏摘要。完成事件关联调用 ID、耗时、成功标志、错误码和已登记的证据 ID。

## 9. 契约验收

| ID | 验证条件 |
| --- | --- |
| C3-AT-01 | 七个工具可发现。重名、未知工具、非法类型、额外字段及互斥字段在执行前被拒绝 |
| C3-AT-02 | 受控站点的导航、点击、填写与单值选择可用，零匹配、多匹配、禁用控件和缺失选项分别有明确结果 |
| C3-AT-03 | 观察返回实际 URL、标题、ARIA、控件与已登记证据，截断有标记，切页时证据来自同一页面 |
| C3-AT-04 | 检查不匹配仍为 `success=true`，零匹配的 exists、visible 和 count 按约定返回 |
| C3-AT-05 | 显式导航、点击跳转、重定向、新页和凭据解析均遵循授权范围 |
| C3-AT-06 | 工具超时有界。动作预算在分发前扣减，已分发失败仍计数。同一动作只分发一次 |
| C3-AT-07 | 故障和取消会停止新动作并清理 Run 会话。外部 Browser 继续可用，并行 Run 互相隔离 |
| C3-AT-08 | 秘密标记从公开输出和证据中移除。保存失败不会产生无效证据引用 |
| C3-AT-09 | Agent 可借助 FakeBrowserAdapter 验证正常、工具失败和检查不匹配。BrowserAdapter 可使用预设调用验证受控页面 |

BrowserAdapter 实现方应提供符合本契约 Schema 与结果约束的 FakeBrowserAdapter。Agent Runtime 实现方应提供支持预设工具调用序列的 FakeLLM。契约测试纳入 `tests/contract/`，浏览器集成测试使用 `testsites/demo-app/` 的受控登录夹具。C3 契约验收不依赖真实 LLM 服务。

## 10. 部署配置与扩展

用测试夹具配置允许的目标、定位器、副作用、默认超时和跨用例重置策略。课程计步按课程要求单独核对。滚动、拖拽、键盘、iframe 和多页能力通过契约变更扩展。见 [开放问题](../../docs/05-open-questions.md)。
