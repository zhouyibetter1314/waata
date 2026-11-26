# C3 · 浏览器工具

Agent Runtime 按 Pydantic 输入模型校验工具调用，Playwright 适配器在当前用例的独立会话中执行。工具参数由模型提供，Run、Case、Step、调用 ID、期限与动作预算来自可信 `ToolContext`。[输入模型](../../packages/waata/src/waata/browser/models.py) · [注册与分发](../../packages/waata/src/waata/core/tools/__init__.py) · [Playwright 会话](../../packages/waata/src/waata/browser/session.py)

## 调用与定位

`ToolResult` 包含 `success: bool`、`data: object | null`、`error: object | null`。错误含 `code`、脱敏后的 `message` 和 `retryable`。工具执行成功表示完成操作或取得观察。业务结果由 C2 汇总，`inspect` 可成功返回 `matched=false`。未知工具和额外字段在分发前拒绝。

| `locator.strategy` | 必填字段 | 可选字段与条件 |
| --- | --- | --- |
| `role` | `role`、`name` | `exact` 默认 `true`，role 限于输入模型的枚举 |
| `label`、`text`、`placeholder` | `value` | `exact` 默认 `true` |
| `test_id` | `value` | 由 Playwright 使用测试 ID 定位 |
| `css` | `value` | 当前页面的标准 CSS 选择器 |

元素操作和元素截图要求唯一匹配。导航、点击、填写与下拉选择受动作策略约束，操作后可重新观察页面。定位失败、存在多匹配和控件不可操作分别使用 `ELEMENT_NOT_FOUND`、`AMBIGUOUS_LOCATOR`、`ELEMENT_NOT_INTERACTABLE`。点击、填写与下拉选择可在期限内等待目标出现。

## 4. 工具清单

| 工具 | 输入 | 成功 `data` |
| --- | --- | --- |
| `browser.navigate` | `url`，已授权且同源的绝对 HTTP(S) URL | `action`、脱敏的实际 `url` |
| `browser.click` | `locator` | `action`、`url` |
| `browser.fill` | `locator`，加 `value` 或 `secret_ref` | `action`、`url` |
| `browser.select_option` | `locator`、`value`，根据原生单选 `<select>` 的 option 值选择 | `action`、`url` |
| `browser.observe` | `include_screenshot` 可选，默认 `false` | `observation_id`、`observed_at`、`url`、`title`、`aria`、`elements`、`truncated`、`evidence_ids` |
| `browser.inspect` | `condition`，及条件所需的 `locator` 或 `expected` | `condition`、`actual`、`matched`、`url`、`observed_at`、`evidence_ids`，以及条件使用的脱敏定位器和预期值 |
| `browser.screenshot` | `full_page` 默认 `false`，可传 `locator` 截取唯一元素，二者不能同时启用 | `artifact_id`、`kind=screenshot`、`page_url`、`captured_at` |

七个工具均接受可选正整数 `timeout_ms`。超过适配器最大值时返回 `INVALID_ARGUMENTS`。实际期限取请求上限、适配器默认上限及可信上下文期限中的最早值。导航等待 DOM 内容加载，HTTP 响应状态由后续页面检查解释。对原生下拉框中缺失或禁用的选项返回 `OPTION_NOT_FOUND`。

页面观察包含脱敏的可访问性摘要与可见控件摘要。优先保留输入框、下拉控件、可见选项和操作按钮，定位提示来自当前页面的测试 ID、唯一 CSS 匹配或语义属性。每个控件包括 `locator`、可空的 `role`、`name`、`text` 以及 `enabled`。缺少唯一 CSS 定位器的同源链接可附带无查询参数和片段的 `href`，供 Agent 导航。上限触发时设置 `truncated=true`。观察或检查遇到页面切换时可能得到 `OBSERVATION_UNSTABLE`。截图默认关闭。启用后记录普通表单的实际画面，用灰色遮挡密码、配置的敏感区域和含已知凭据的输入框。截图会检查页面可见文本、尺寸及字节数。观察和截图登记成功后返回引用。[C5 存储](../artifacts/c5-test-evidence-artifacts.md)

### 5.4 browser.fill

`value` 填写普通测试文本，允许空串以清空已有内容。输入 `secret_ref` 时，浏览器只在该 Run 获授权的集合内查找引用，并校验定位元素是对应的已配置输入框。两个参数必须恰好提供一个。密码框、可信配置中的凭据字段和命中脱敏规则的文本通过 `secret_ref` 处理，错配返回 `SECRET_NOT_AVAILABLE`。填充结果省略输入值。[目标凭据配置](../../apps/api/README.md)

### 5.7 browser.inspect

| `condition` | 其他输入 | `actual` 与 `matched` |
| --- | --- | --- |
| `url_equals` | `expected: string` | 脱敏 URL，与预期精确比较 |
| `url_path_starts_with` | `expected: string`，以 `/` 开始 | 脱敏 URL 的路径，与预期路径前缀比较 |
| `title_equals` | `expected: string` | 脱敏标题，与预期精确比较 |
| `exists` | `locator` | 至少匹配一个节点时均为 `true` |
| `visible` | `locator` | 至少一个匹配节点具有可见的布局框时均为 `true` |
| `count` | `locator`、`expected: integer >= 0` | 匹配数，及其是否等于预期 |
| `text_equals` | `locator`、`expected: string` | 唯一可见元素的脱敏文本，统一 CRLF 后去掉首尾空白再比较 |

`exists`、`visible`、`count` 允许零匹配。检查仅读取当前可用状态，Verifier 复核证据并确定断言。成功检查在 `evidence_ids` 返回已登记的结构化观察引用。[C2 判定](../waata/c2-waata-python-api.md)

## 7. 执行边界

Chromium 会话绑定目标 origin（scheme、主机、端口）。适配器允许当前主框架发起的同源请求，并在浏览器边界拦截跨源跳转。WebSocket 默认拦截，可信配置可以指定同源连接的精确路径。会话禁用 Service Worker，关闭新页、取消下载和关闭对话框。独立调用方保有 Browser 的关闭责任。

### 7.2 预算和副作用

每次 Agent 步骤计入用例上限，可包含零次或多次工具调用。Run 级动作预算在导航、点击、填写或下拉选择送入 Playwright 前扣减一次，已分发失败仍计数。参数、授权和定位阶段拒绝可消耗工具尝试额度。观察、检查及截图计入工具尝试和期限。检测到页面状态变化时重新观察，已分发的动作可能产生副作用。

| 错误场景 | 错误码 |
| --- | --- |
| 注册与输入 | `UNKNOWN_TOOL`、`INVALID_ARGUMENTS` |
| 目标、动作或凭据未授权 | `TARGET_NOT_ALLOWED`、`ACTION_NOT_ALLOWED`、`SECRET_NOT_AVAILABLE` |
| 元素和选项 | `ELEMENT_NOT_FOUND`、`AMBIGUOUS_LOCATOR`、`ELEMENT_NOT_INTERACTABLE`、`OPTION_NOT_FOUND` |
| 会话、导航与页面事件 | `SESSION_NOT_READY`、`BROWSER_CLOSED`、`NAVIGATION_FAILED`、`UNSUPPORTED_PAGE_EVENT`、`OBSERVATION_UNSTABLE` |
| 执行上限、证据和内部错误 | `TOOL_TIMEOUT`、`BUDGET_EXCEEDED`、`ARTIFACT_WRITE_FAILED`、`INTERNAL_ERROR` |

异步取消继续传播至引擎生命周期，由引擎清理用例会话。分发器将工具调用摘要和已登记证据映射至 C4 事件。[示例工具调用](examples/4gaboards-tool-calls.json) · [Playwright 集成测试](../../packages/waata/tests/test_engine_integration.py) · [受控站点验收](../../docs/04-acceptance.md#ac-02-受控站点执行)
