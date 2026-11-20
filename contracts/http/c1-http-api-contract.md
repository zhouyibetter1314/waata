# C1 · HTTP API 契约

> 范围：`apps/web` ↔ `apps/api`，API 前缀 `/api/v1`  
> 关联：FR-001、FR-004～FR-007；AC-01、AC-03～AC-06；C2（运行结果）、C4（事件）、C5（证据）

## 1. 目标与边界

本契约定义平台 **测试任务创建、列表、详情、事件订阅、报告查询和取消** 的 HTTP 接口，包括请求、响应、状态语义和错误格式。Vue 仅通过 FastAPI 访问任务与证据，不直接调用 WAATA Python Package。

- 当前是接口设计，不代表仓库已实现这些端点。
- 首版优先完成受控登录测试的端到端闭环；场景 CRUD、批量提交、重新运行和完整导出接口不在本版六个端点内，若纳入 v0.1 需另行评审。
- FastAPI Pydantic 请求/响应模型是实现阶段的定义来源；`contracts/http/openapi.json` 应从服务端自动导出，前端类型由 OpenAPI 生成。本文作为评审与语义说明，不维护第二套独立 Schema。

## 2. 通用约定

| 项目          | 约定                                                         |
| ------------- | ------------------------------------------------------------ |
| API 基础路径  | `/api/v1`                                                    |
| 普通请求/响应 | `application/json; charset=utf-8`                            |
| SSE 响应      | `text/event-stream; charset=utf-8`                           |
| 标识符        | `run_id` 为不透明字符串；客户端不得依赖其生成规则            |
| 时间          | ISO 8601 UTC 时间字符串，如 `2026-11-20T05:00:00Z`           |
| 字段命名      | `snake_case`                                                 |
| 未产生的数据  | 使用显式 `null`；集合为空时使用 `[]`，不省略已定义的必需字段 |
| 长任务        | 创建接口返回 `202 Accepted`，表示已接收并入队，不表示测试成功 |
| 凭据          | 不在 HTTP 请求、事件、报告中传输明文密码、Cookie 或 API Key；测试账号通过服务端配置的凭据引用获取 |
| 授权边界      | 仅允许对已授权的受控站点发起测试；目标 URL 的校验和重定向策略需与 Q-008 一致 |

**约束分工：** C1 规定 HTTP 传输与外部可观察语义；TestEngine 内部流程由 C2 定义，事件载荷由 C4 定义，证据元数据及访问控制由 C5 定义。

## 3. 数据类型与状态

### 3.1 执行状态与业务判定

```typescript
type RunStatus = 'queued' | 'running' | 'succeeded' | 'errored' | 'cancelled';
type TestVerdict = 'passed' | 'failed' | 'blocked' | 'inconclusive';
```

| 状态        | 含义                                                         |
| ----------- | ------------------------------------------------------------ |
| `queued`    | 任务已创建，等待 Worker 执行                                 |
| `running`   | Worker 正在执行任务                                          |
| `succeeded` | 测试流程正常结束，已有可查询的最终报告；不表示被测应用通过测试 |
| `errored`   | 测试执行基础设施或运行时异常，无法正常完成                   |
| `cancelled` | 取消已生效，执行停止并完成必要清理                           |

**`status` 是运行状态，`verdict` 是测试结果。** 例如 `status=succeeded, verdict=failed` 表示执行成功完成，但应用未满足断言；`status=errored, verdict=null` 表示执行系统发生异常。`queued` 和 `running` 的 `verdict` 为 `null`；`errored`、`cancelled` 的最终 `verdict` 暂定为 `null`，已形成的用例结论仍可在部分报告中保留（此项需 C2 共同确认）。

`blocked` 表示执行受权限、环境或前置依赖阻碍；`inconclusive` 表示执行后证据不足以作可靠判定。**多用例的聚合优先级及与课程评测三分类的映射由 C2/验收规约统一确定，C1 只透传结果，不自行推导。**

### 3.2 任务摘要的字段

| 字段          | 类型                | 约束                            |
| ------------- | ------------------- | ------------------------------- |
| `run_id`      | string              | 必填，唯一任务标识              |
| `target_url`  | string              | 必填，提交时的授权目标地址      |
| `goal`        | string              | 必填，原始自然语言测试目标      |
| `status`      | RunStatus           | 必填                            |
| `verdict`     | TestVerdict \| null | 必填，未产生最终判定时为 `null` |
| `created_at`  | string              | 必填，UTC 时间                  |
| `started_at`  | string \| null      | 必填，尚未开始时为 `null`       |
| `finished_at` | string \| null      | 必填，尚未终止时为 `null`       |

## 4. 端点清单

| Method | Endpoint                            | 用途                | 成功状态                 |
| ------ | ----------------------------------- | ------------------- | ------------------------ |
| POST   | `/api/v1/test-runs`                 | 创建测试任务        | `202`                    |
| GET    | `/api/v1/test-runs`                 | 分页查询任务列表    | `200`                    |
| GET    | `/api/v1/test-runs/{run_id}`        | 查询任务详情与进度  | `200`                    |
| GET    | `/api/v1/test-runs/{run_id}/events` | 订阅运行事件（SSE） | `200`                    |
| GET    | `/api/v1/test-runs/{run_id}/report` | 查询测试报告        | `200`                    |
| POST   | `/api/v1/test-runs/{run_id}/cancel` | 请求取消任务        | `202` 或 `200`（见下文） |

### 4.1 创建任务

`POST /api/v1/test-runs`

**请求体**

```json
{
  "target_url": "https://staging.example.com",
  "goal": "验证登录功能的正确密码和错误密码场景",
  "expected_behavior": "正确密码进入控制台并显示已登录状态；错误密码停留在登录页并显示约定提示",
  "credential_ref": "demo_login_fixture",
  "options": {
    "headless": true,
    "max_steps_per_case": 35
  }
}
```

| 字段                         | 类型           | 约束                                                         |
| ---------------------------- | -------------- | ------------------------------------------------------------ |
| `target_url`                 | string         | 必填；合法 HTTP(S) URL，且符合目标授权配置                   |
| `goal`                       | string         | 必填；非空自然语言测试目标                                   |
| `expected_behavior`          | string         | 必填；非空预期行为，用于形成检查点                           |
| `credential_ref`             | string \| null | 可选；服务端受控凭据引用，不包含秘密本身                     |
| `options.headless`           | boolean        | 可选，默认 `true`                                            |
| `options.max_steps_per_case` | integer        | 可选；正整数，受服务端配置上限约束；课程评测配置不得超过教师规定的 35 次浏览器操作预算 |

> 预算术语需协调：`max_steps_per_case` 是「每用例预算」，教师的「每场景最多 35 次浏览器操作」可能对应整个 Run 或每个场景；确认前不能用每用例 35 步替代总预算。服务端必须强制执行课程评测的实际计步规则。

**响应 · `202 Accepted`**

```json
{
  "run_id": "run_001",
  "status": "queued",
  "created_at": "2026-11-20T05:00:00Z"
}
```

创建成功后，前端使用 `run_id` 查询详情或订阅 SSE；不能根据 `202` 推断业务 `verdict`。参数错误返回 `422`；未获授权目标返回 `403`（相关安全策略待 Q-008 确认）。

### 4.2 分页查询任务列表

`GET /api/v1/test-runs?page=1&page_size=20`

| 参数        | 类型    | 约束                             |
| ----------- | ------- | -------------------------------- |
| `page`      | integer | 可选，默认 `1`，最小 `1`         |
| `page_size` | integer | 可选，默认 `20`，允许 `1`～`100` |

**响应 · `200 OK`**

```json
{
  "items": [
    {
      "run_id": "run_001",
      "target_url": "https://staging.example.com",
      "goal": "验证登录功能",
      "status": "succeeded",
      "verdict": "failed",
      "created_at": "2026-11-20T05:00:00Z",
      "started_at": "2026-11-20T05:00:03Z",
      "finished_at": "2026-11-20T05:01:25Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

默认按 `created_at` 降序排列，同时间记录以稳定次序排序；无结果时 `items=[]`、`total=0`。鉴权后仅返回调用方有权查看的任务。分页方案是本版建议，团队若采用游标分页应在实现前统一修改契约。

### 4.3 查询任务详情

`GET /api/v1/test-runs/{run_id}`

**响应 · `200 OK`**

```json
{
  "run_id": "run_001",
  "target_url": "https://staging.example.com",
  "goal": "验证登录功能",
  "expected_behavior": "正确密码进入控制台；错误密码显示约定提示",
  "status": "succeeded",
  "verdict": "failed",
  "progress": {
    "total_cases": 2,
    "completed_cases": 2
  },
  "summary": {
    "passed": 1,
    "failed": 1,
    "blocked": 0,
    "inconclusive": 0
  },
  "created_at": "2026-11-20T05:00:00Z",
  "started_at": "2026-11-20T05:00:03Z",
  "finished_at": "2026-11-20T05:01:25Z"
}
```

`progress.total_cases` 在计划尚未生成时可以是 `null`，`completed_cases` 初始为 `0`。在运行结束前 `summary` 可为 `null`，`finished_at` 必须为 `null`；`started_at` 在尚未启动时为 `null`。不存在的 `run_id` 返回 `404`。

### 4.4 订阅运行事件

`GET /api/v1/test-runs/{run_id}/events`

响应 `200 OK`、`Content-Type: text/event-stream`。示例：

```text
id: 17
event: tool.completed
data: {"event_id":"evt_000017","run_id":"run_001","sequence":17,"type":"tool.completed","timestamp":"2026-11-20T05:00:21Z","payload":{"tool":"browser.click","success":true}}

```

- SSE `event:` 与数据对象中的 `type` 一致；事件载荷字段以 C4 为准。
- 同一 Run 的 `sequence` 必须能够用于排序和去重；前端不将 SSE 连接断开等同于 Run 失败。
- 事件必须先持久化再推送，保证可重放；重连使用 `Last-Event-ID` 继续获取缺失事件，或由后端提供等效补读机制。具体游标约定由 C4 冻结。
- 当任务进入终态时，前端以 `GET /test-runs/{run_id}` 的权威状态为准。取消后的事件终态名称和无事件时保活格式由 C4 统一定义。
- 不发送密码、Cookie、API Key 或模型内部原始推理内容。

### 4.5 获取测试报告

`GET /api/v1/test-runs/{run_id}/report`

**响应 · `200 OK`（示例为最小结构）**

```json
{
  "run_id": "run_001",
  "status": "succeeded",
  "verdict": "failed",
  "cases": [
    {
      "case_id": "case_001",
      "name": "错误密码登录",
      "verdict": "failed",
      "assertions": [
        {
          "assertion_id": "assert_001",
          "expected": "显示指定错误提示",
          "actual": "显示了与预期不一致的提示",
          "passed": false,
          "evidence_ids": ["art_001"]
        }
      ]
    }
  ],
  "artifacts": [
    {
      "artifact_id": "art_001",
      "kind": "screenshot",
      "url": "/api/v1/artifacts/art_001"
    }
  ]
}
```

- `cases` 及 `assertions` 用于表达计划、预期、实际及关联证据；完整字段需要与 C2 `TestResult` 一致。
- `artifacts` 仅返回引用和可展示元数据；文件不以内嵌 Base64 形式提供；完整元数据、授权访问与有效期以 C5 为准。
- `url` 是 C5 拟议的证据访问路径，**不表示此端点目前已纳入已冻结的 C1 路由清单**。C5 确认后须在 C1 中补充证据访问端点。
- 报告尚未生成时返回 `409 REPORT_NOT_READY`；执行错误或取消时是否提供部分报告，需 C2/C5 评审。不存在的 Run 返回 `404`。

### 4.6 取消任务

`POST /api/v1/test-runs/{run_id}/cancel`

无需请求体。该接口**请求取消**，不能将“已收到取消请求”等同于“取消完成”。

**响应 · `202 Accepted`（运行中，取消已受理）**

```json
{
  "run_id": "run_001",
  "status": "running",
  "cancellation_requested": true
}
```

**响应 · `200 OK`（排队任务已经同步取消）**

```json
{
  "run_id": "run_001",
  "status": "cancelled",
  "cancellation_requested": true
}
```

已处于 `succeeded`、`errored` 或 `cancelled` 终态的任务，再请求取消时返回 `409 RUN_NOT_CANCELLABLE`（建议语义；最终须与 Worker 取消策略共同冻结）。前端应继续查询 Run 详情直至进入终态。取消信号如何传至 WAATA、何时清理 BrowserContext 属于 C2/Worker 契约。

## 5. 统一错误响应

除 SSE 连接建立后的流内事件外，失败的 HTTP 请求统一返回：

```json
{
  "error": {
    "code": "RUN_NOT_FOUND",
    "message": "测试任务不存在",
    "request_id": "req_123"
  }
}
```

| HTTP 状态 | 错误码示例                         | 触发场景                                           |
| --------- | ---------------------------------- | -------------------------------------------------- |
| `400`     | `INVALID_REQUEST`                  | 请求格式错误，无法正常解析                         |
| `403`     | `TARGET_NOT_ALLOWED` / `FORBIDDEN` | 测试目标无授权，或无权访问资源                     |
| `404`     | `RUN_NOT_FOUND`                    | 任务不存在或对调用方不可见（具体信息隐藏策略待定） |
| `409`     | `REPORT_NOT_READY`                 | 报告尚未生成                                       |
| `409`     | `RUN_NOT_CANCELLABLE`              | 无法取消已经进入终态的任务                         |
| `422`     | `VALIDATION_ERROR`                 | 字段缺失、类型错误、取值越界                       |
| `429`     | `TOO_MANY_REQUESTS`                | 触发限流或并发配额（若启用）                       |
| `500`     | `INTERNAL_ERROR`                   | 未预期服务端错误                                   |
| `503`     | `SERVICE_UNAVAILABLE`              | 服务暂不可用或必要依赖不可用                       |

错误响应不得泄露凭据、内部文件路径或堆栈细节。`request_id` 便于定位服务日志。若采用此统一格式，FastAPI 默认 `422` 响应必须经异常处理器转换；不能仅在文档中声明。

## 6. 契约验收

| ID       | 对应行为       | 最低验证条件                                                 |
| -------- | -------------- | ------------------------------------------------------------ |
| C1-AT-01 | 创建任务       | 合法请求返回 `202`、可查询的 `run_id`；无效请求返回 `422`    |
| C1-AT-02 | 状态与判定分离 | `succeeded + failed` 可合法返回；运行时异常为 `errored + null` |
| C1-AT-03 | 列表与详情     | 列表分页、详情字段与 OpenAPI 一致；未知 Run 为 `404`         |
| C1-AT-04 | SSE            | 前端能收到结构化事件；重复、断线后的状态能够正确恢复或补读   |
| C1-AT-05 | 报告           | 完成后可查询用例、断言与证据引用；未生成时为约定错误         |
| C1-AT-06 | 取消           | 已受理与已取消可区分；最终状态可查询；终态取消行为一致       |
| C1-AT-07 | 数据安全       | 未授权目标被拒绝；普通响应、事件及报告不泄露秘密             |
| C1-AT-08 | Schema 一致性  | Pydantic 导出的 OpenAPI 与提交快照一致；前端生成类型检查通过 |

验收应优先使用 MockTestEngine 验证 HTTP 层，不依赖真实 LLM 或 Playwright；完整流程由 AC-05 进一步验证。

## 7. 待团队确认（冻结前）

1. **输入边界**：`expected_behavior` 采用必填自然语言还是结构化检查点；`credential_ref` 的命名和可用范围（Q-001、Q-008）。
2. **操作预算**：统一每用例、每场景和整次 Run 的计数单位与上限；确保课程评测不超过 35 次浏览器操作（Q-005）。
3. **判定聚合**：`blocked`、`inconclusive` 的业务含义、多用例总体 `verdict` 规则及课程输出映射（Q-002、Q-006）。
4. **运行终态**：取消、技术故障后的部分报告和 `verdict` 是否允许保留（Q-002、Q-003）。
5. **事件重连**：`Last-Event-ID` 的具体语义、重放窗口、终止事件与历史事件补读（Q-009、C4）。
6. **证据访问**：Artifact 下载路由、元数据、授权、保留期限，以及报告导出范围（Q-007、C5）。
7. **任务列表**：页码分页或游标分页、是否需要状态筛选；明确本版不包含的场景 CRUD 和批量运行（Q-001）。

通过评审后，将本文件标记为 `Accepted v0.1`，由 FastAPI 维护 Pydantic 类型并导出 OpenAPI；涉及 C2、C4、C5 的字段必须由相关模块负责人共同审核。

