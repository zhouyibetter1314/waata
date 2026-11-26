# WAATA × Discourse 联调记录

## 范围与环境

依据 `examples/README.md` 的组员 C 场景，使用真实模型规划、真实 Playwright 和 Discourse 站点执行。最新结果包含三轮共 30 条 Run；剩余四项已完成真实续测，结论见[成果汇总](discourse-summary.md)。未执行离线回放、未用脚本替代 Agent 完成业务变更。

## 2026-11-26 图片清理与只读重截

按要求删除 `docs/testing/evidence/discourse/` 中 9 张含粉色遮罩的旧 PNG，重新登录测试账号，以不带 mask 的原生页面截图保存 7 张当前状态图。仅浏览设置、搜索书签和读取 Pending 列表；不调用模型，不保存偏好、不修改邀请或主题。邀请完整链接弹窗未打开，页面正常显示的缩短短码与 0/1、0/2 计数未遮盖。

字号已保存为 Larger，历史 DC-11 目标已被删除，因此没有把账号改回 Normal 或重建邀请来补拍历史中途状态。旧 Normal 图及删除前 0/1 图从交付图片目录撤下，历史事实仍以原始报告和 `DC11-updated-stage.json` 为准。新截图按实际 tag 核对：第一轮书签仍存在；第二轮目标搜索无结果；第三轮书签存在；DC-08 practice 为 0/1；第三轮 DC-11 scoped 不存在且 keep 为 0/2；第二轮旧 scoped/keep 均仍为 0/2。

[证据索引](evidence/discourse/README.md#2026-11-26-无遮挡重截)和 `clean-capture-manifest.json` 保存新旧文件映射、采集时间、检查结果及 SHA-256。下文关于遮罩与“原件哈希”的描述是 2026-11-25 采集时的历史记录；当前交付目录以本次索引为准。原始 Run、判定、模型用量与 `.local/` 内的原件不变。未 commit。

## 第三轮恢复与完成（20:07–20:19）

本次从现有功能分支、未提交脚本/文档、24 条本地报告与 SQLite 恢复工作。读取 #11（`930b0d6`）的报告、证据索引和执行脚本，沿用“真实 Agent → 原判定 → 独立会话 → 持久化核查”的证据口径。旧失败、额度错误和截图保留，全部原始报告不可变。

新 CSV 配置仅写入本机 Git 忽略的 `.env`，模型固定为 `deepseek-v4.1-flash`；20:07 最小调用为 HTTP 200 / OK，探测用量 10 Token 单独记录，不计入 Run 汇总。恢复已存在的 Discourse 容器，无需 Windows PostgreSQL。登录准备改为等待 DOMContentLoaded 和登录标记，避免开发站点页面等待 load 超时。

### 定位和夹具

- DC-06 核对真实主题页底部 `.topic-footer-main-buttons button.bookmark`。点击后立即保存无提醒书签；无需选择提醒时间。之前的 `#post_1 button.bookmark` 可能隐藏且不等价于主题级操作。
- Wiki 菜单实际位于 `.fk-d-menu button.wiki`，旧 `.post-admin-menu .widget-button` 不存在。菜单按钮文本用于区分 Make Wiki / Remove Wiki；观察不点击反向操作。复核显式等待菜单可见，再读取文本，修复即时 `is_visible()` 的时序误报。
- 邀请保存使用 `.create-invite-modal button.save-invite`，排除同为 `.btn-primary` 的 Copy link；关闭按钮实际为 `.modal-close`。Remove 使用限定目标行的 More 菜单及 `.fk-d-menu button.btn-danger`。
- 保留完整 C3 工具集；观察字符上限增至 18,000，元素上限仍为 60。Wiki 收尾要求菜单保持打开供最终检查，DC-10 保存编辑后先重开页面以恢复明确的操作状态。

控件诊断使用单独 tag `11251208-64e2`。诊断时点击主题书签按钮本身已产生书签，故该夹具明确排除 Agent 场景验收；随后新建 `11251212-7b87`，保存执行前只读基线。最终 Wiki 复跑另用 `11251217-7e0b`，同样保存普通帖/Wiki 初始状态，不能在已成功状态上冒充新执行。两组均用 `--keep-preferences` 保留旧 DC-04 字号结果。

### 六条真实 Run

| 场景 / Run ID | 原判定 | 完整复核与诊断 |
| --- | --- | --- |
| DC-06 `dc06-agent-79b4a5a95d` | `passed` | Agent 点击主题书签，先观察 Activity 列表再点击精确标题链接到目标，阶段 1/2 均保留；新会话可跟随，数据库书签无提醒 |
| DC-07 `dc07-agent-5d6532e802` | `inconclusive` | 已成功转 Wiki，但结束前点击标题关闭菜单，最终 Remove Wiki 检查缺证。初次独立复核菜单即时可见检查误报；追加只读复核通过，原报告不改 |
| DC-10 `dc10-agent-c56275ffaa` | `inconclusive` | 保存正文和取消 Wiki 后已满足业务状态；但菜单定位 2 次超时，模型预算耗尽，未完成 Agent 重开和菜单检查。追加独立重开通过，不冒充完整 Agent 流程 |
| DC-11 `dc11-agent-f5c849595b` | `passed` | 在目标行把 2 改为 1，记录 0/1，再移除目标。新会话目标缺席且 keep 对照仍在；数据库确认对照 ID/0/2 未变 |
| DC-07 `dc07-agent-ddf6fe706f` | `passed` | 新普通帖转 Wiki，Agent 重开并保留 Remove Wiki 菜单；4 条引擎断言、新会话与数据库一致。含 3 次失败动作尝试，未隐去 |
| DC-10 `dc10-agent-e08b1e1cff` | `passed` | 新 Wiki 更新正文、取消 Wiki、Agent 重开并保留 Make Wiki 菜单；4 条引擎断言、新会话与数据库一致 |

前四条 `harness_version=3`，默认 180,000 Token；最后两条 `harness_version=4`，显式 `--tokens 260000`，实际 151,734 / 197,545。所有 Run 最多 35 动作、27 步、30 次模型请求、300 秒；预登录不计入预算。版本 1/2 的观察/工具配置差异按历史记录解释，不将各轮用量视为受控性能实验。

新增 6 条共 72 次成功模型响应、836,709 Token、49 次动作调用（5 次失败），耗时之和 186.07 秒。累计 30 条的准确指标由 `discourse-summarize.py` 生成，详见成果汇总和 `run-index.json/csv`。

### 原件、脱敏和阶段证据

每条 Run 的报告、C5 观察、模型响应、事件和截图写入 `.local/discourse/runs/<run_id>/`，SQLite `runs` 同步登记；追加菜单只读复核在 `.local/discourse/rechecks/<run_id>/verification.json`，由汇总脚本登记 `verifications` 表。原报告的初次复核误报仍在，索引以 `rechecked_passed` 单列追加结果。

`baseline-<tag>.json` / `audit-<tag>.json` 是容器目标数据库执行前后只读快照；最新 tag 的其它未执行场景维持初始状态是正常的，只按对应场景/tag 判断。提交的 `round3-persisted-state.json` 仅摘录本次执行范围，并标记源快照哈希，不包含凭据或邀请链接。

DC-11 的第一张阶段图仍有编辑弹窗且短码区域遮罩，**截图本身不证明 0/1**。`DC11-updated-stage.json` 从当时报告的只读 `stages[0]` 提取已更新行，移除邀请短码，保留 0/1、描述和到期时间及报告哈希。Agent 关窗后的模型观察亦有该行，最终截图和数据库分别证明删除及对照保留。没有删除后重新创建邀请补拍中途状态。

新增 9 张截图均已查看。输入和邀请短码区域沿用遮罩；截图来源、失败含义、补充复核与指标可在[证据索引](evidence/discourse/README.md)对应到 Run。完整本地归档为 `.local/discourse/summary/discourse-qa-20261125-round3.zip`，包含报告、证据、夹具、数据库前后核查、只读复核、SQLite 一致性快照及文件哈希清单；旧 round1/round2 归档保留。

### 复现本次执行

按根工作区安装锁定依赖，并为 `waata` 安装 browser extra / Chromium。模型连接值和专用账号沿用 `examples/README.md`，写入本地 `.env`：`WAATA_MODEL_BASE_URL`、`WAATA_MODEL_API_KEY`、`WAATA_MODEL_NAME`，以及 `WAATA_DC_ADMIN_LOGIN/PASSWORD`、`WAATA_DC_MEMBER_LOGIN/PASSWORD`。不要输出 `.env` 或把 CSV 复制进提交目录。Windows 的 uv 安装不在 PATH 时使用本机 uv.exe 完整路径，命令其余参数一致。

```powershell
uv sync --locked --all-packages --extra browser
uv run --locked --package waata --extra browser playwright install chromium
powershell -ExecutionPolicy Bypass -File scripts/discourse-local.ps1 start
uv run --locked python scripts/discourse-agent-check.py prepare --keep-preferences
# 用上一步实际返回的 tag 替换 <tag>。先 audit，并将输出另存 baseline-<tag>.json。
uv run --locked python scripts/discourse-agent-check.py audit .local/discourse/fixture-<tag>.json
uv run --locked python scripts/discourse-agent-check.py preflight .local/discourse/fixture-<tag>.json
uv run --locked python scripts/discourse-agent-check.py run .local/discourse/fixture-<tag>.json DC06 --prepared
uv run --locked python scripts/discourse-agent-check.py run .local/discourse/fixture-<tag>.json DC11 --prepared
uv run --locked python scripts/discourse-agent-check.py run .local/discourse/fixture-<tag>.json DC07 --prepared --tokens 260000
uv run --locked python scripts/discourse-agent-check.py run .local/discourse/fixture-<tag>.json DC10 --prepared --tokens 260000
uv run --locked python scripts/discourse-agent-check.py audit .local/discourse/fixture-<tag>.json
uv run --locked python scripts/discourse-summarize.py
```

首次部署用 `discourse-local.ps1 init`；本次使用已有命名卷，未重新走全新空卷初始化。每个场景每套夹具只执行一次；重跑先新建夹具。若只追加独立复核，使用 `verify <fixture> <DC编号> --output <本地目录>`，不调用模型、不保存业务变更。所有代表 Run 为显式预登录模式；完整登录端到端预算尚需另测。

### 本次检查与交付

- 契约：`uv run --locked python -m unittest discover -s tests/contract -v`，12 项通过。
- Python 包全套（16 项真实 Chromium 集成 + 16 项单元测试）：`uv run --locked --package waata --extra browser python -m unittest discover -s packages/waata/tests -v`，32 项通过。
- API：`uv run --locked python -m unittest discover -s apps/api/tests -v`，5 项 Worker 测试通过、6 项 PostgreSQL 用例跳过、2 个模块导入错误。错误为基线 `apps/api/src/waata_api/infrastructure/artifacts.py` 在 Windows 导入 Unix `fcntl`，影响 `test_artifact_store` / `test_http_contract`。未设置 `WAATA_TEST_DATABASE_URL`，未连接 Discourse 数据库冒充平台测试库。
- 包单元：`uv run --locked --package waata --extra browser python -m unittest discover -s packages/waata/tests/unit -t packages/waata/tests -v`，16 项通过，已计入上述包全套 32 项，不重复累计；`-t` 使测试辅助包从正确根路径导入。
- Python 两个执行/汇总脚本编译通过，Ruby 两个夹具/核查脚本在 Discourse 容器 `ruby -c` 通过，PowerShell 启停脚本通过 Parser 语法检查。
- 30 条原报告与 SQLite JSON/Run ID/索引 SHA-256 完全一致，382 个 artifact 文件大小及断言证据引用有效，27 张提交截图均与本地原件哈希一致；提交文本未包含配置密钥、登录值、密码或可兑换邀请 URL。
- `uv run --locked pre-commit run --all-files` 全部通过。首次仅因统一 LF 行尾写回而失败，复跑通过；未将无语义变化的其它模块加入提交。Python 依赖和锁文件无变更。

交付仅包含本次及已恢复的 Discourse 测试脚本、报告、截图、指标与 README 入口；无需改变公共契约、WAATA 核心、平台数据库迁移或上游子模块。原始 `.env`、SQLite、模型消息、诊断脚本和归档保留在忽略的 `.local/`。使用功能分支 `codex/discourse-agent-workflows`，按 Conventional Commits 提交；未推送或创建 PR。

以下是原两轮历史，旧日期、数量、停止原因及当时尚未完成项只描述该轮，不代表当前最终状态。

## 第二轮续测（17:43–17:56）

新密钥调用 `deepseek-v4.1-flash` 返回 200 后，创建 tag `11250946-e107` 新夹具；DC-10 重跑使用 `11250953-33e1`，保持会员已保存字号不重置。所有新增 Run 均为真实模型，不复用第一轮规划/动作。原始 14 条 Run 和第一轮归档不改写；累计 24 条。

已修正并实际使用：`display_name_on_posts=true`；更精确 Larger 选项和邀请表格范围；独立会话按真实页面内容就绪；书签数据库核查同时覆盖 Topic/Post；恢复完整 C3 observe/inspect 工具集。重用账号时不重复设置原密码（Discourse 拒绝重复密码），使用 `--keep-preferences` 可避免新建独立主题时覆盖之前字号结果。

| 场景 | 新 Run / 追加复核 | 结果与实际问题 |
| --- | --- | --- |
| DC-02 | `dc02-agent-1b99b5923e` | 正文和 Member Fixture 显示名均通过 Agent 检查及独立复核 |
| DC-04 | `dc04-agent-6b4588eb9f` | 新会话 Larger、html 对应类和数据库 larger 均正确 |
| DC-06 | `dc06-agent-062fe3873b` | 仍因控件定位/重复观察消耗预算，最终无目标书签；本轮 Post/Topic 联合查询确认均不存在 |
| DC-07 | `dc07-agent-3bf4f566ed` | 最终仍为普通帖；模型认为观察未变化，实际每次 observation_id 都在更新，但页面过长导致返回观察截断，未包含 Make Wiki 菜单项 |
| DC-08 | `dc08-agent-bc292a3596` | 已创建邀请；原 count 检查得到 2，独立查看真实邀请表只有一条，开发 profiler 中也有含请求内容的表格。修正限定 `table.user-invite-list tbody > tr` 后只读新会话复核通过，数据库一条 0/1、无邮箱、未来过期；不重建邀请、不改写原 failed |
| DC-09 | `dc09-agent-2656474d6b` | 普通帖无 Edit 阶段证据、另一 Wiki 新正文与 Wiki 保留均通过，数据库相符 |
| DC-10 | `dc10-agent-33f496805d`、`dc10-agent-f45e16d354` | 两次均只保存正文未完成取消 Wiki；后一次在请求时因额度耗尽 errored，未强行转换为 failed/passed |
| DC-11 | `dc11-agent-360c2857f2`、`dc11-agent-a69f38e044` | 前者范围/观察问题，后者定位到编辑表单但 `.btn-primary` 匹配多个控件，未成功提交；0/2 目标和对照均在，无 0/1 中途证据，不计通过 |

DC-08 的补充 `verify` 命令只重新登录并读取列表，不创建、编辑或删除邀请。记录在 `.local/discourse/rechecks/dc08-agent-bc292a3596/verification.json` 和 SQLite `verifications` 表；原始 Run/断言/独立复核错误仍保留。截图遮罩 `.invite-shortkey`，兑换数由结构化检查和数据库核查佐证。

17:56 最小调用确认 `403 insufficient_quota`。本轮总共新增 120 次已返回模型响应、1,256,903 Token；累计 218 次、2,077,426 Token。服务拒绝后的请求不计用量。没有继续使用不可用模型，也没有修改供应商计费模式。

新增最终只读核查：`.local/discourse/audit-11250946-e107.json`、`.local/discourse/audit-11250953-33e1.json`；保留前者中间版本 `audit-11250946-e107-intermediate.json`。DC-10 正文已改但 Wiki 仍 true；DC-11 仍是 0/2 且对照未动；DC-04 为 larger；DC-09 新正文 Wiki 为 true。没有把其他 tag 的初始数据当成对应场景成功结果。

最新归档为 `.local/discourse/summary/discourse-qa-20261125-round2.zip`，包含 24 条报告、证据、全部夹具/只读核查、额外复核、SQLite 快照及哈希清单。原始数据与 SQLite 已比对 Run ID 和 JSON 一致性。`run-index.json/csv` 新增 fixture_tag、harness_version、rechecked_passed、local_recheck 字段。

以下章节保留第一轮部署、故障和 14 条运行的历史口径，最新状态以上文及成果汇总为准。

| 配置项 | 实际值 |
| --- | --- |
| WAATA 基线 | `fd800f149bda1f62056eef5adbe0c5115808646e` |
| 分支 | `codex/discourse-agent-workflows`；本次新增脚本与文档尚未提交 |
| Discourse | `3e7317b3344cca6c6510a32cc4c5c0f540132ad9`，`discourse/discourse_dev:20250930-0017` |
| 站点 | `http://127.0.0.1:4200`，分类 `WAATA Lab`，英语、Markdown 编辑器 |
| 账号 | 管理员 `waata_admin`；普通会员 `waata_member`（Trust Level 1，公开姓名 `Member Fixture`） |
| 夹具 tag | `11250730-97ca`；场景 URL/对象 ID 存于本机 fixture JSON |
| 可用模型 | `deepseek-v4.1-flash-1017`，使用授权的 OpenAI 兼容配置；无密钥进入提交内容 |
| 模式 | 公共 `TestEngine`、`OpenAILike`、`PlaywrightAdapter`；业务动作由模型调用浏览器工具执行 |
| 单 Run 上限 | 1 用例、27 步、35 动作、30 次模型请求、180,000 Token、300 秒 |
| 数据库 | 被测 Discourse 容器数据库；本地 SQLite QA 索引；未使用 WAATA 平台 PostgreSQL |

## 本机保存的数据

| 路径（仓库根目录下） | 内容 |
| --- | --- |
| `.local/discourse/runs/<run_id>/report.json` | 完整 Run、原始 Agent 判定、事件、模型响应/用量、独立复核、阶段记录 |
| 同目录 `decisions.json`、`events.jsonl` | 持续写入的模型响应和运行事件；首轮模型请求失败时可能没有此文件 |
| 同目录 `dc-art-*.json`、`dc-art-*.png` | C5 引擎登记的结构化观察与自动截图，ID 对应报告 artifact 引用 |
| 同目录 `independent*.png`、`stage-*.png` | 独立新会话与只读阶段观察截图，不冒充引擎自动证据 |
| `.local/discourse/qa.sqlite` | `runs` 表：Run ID、场景、完整 JSON、报告路径，共 14 条 |
| `.local/discourse/fixture-11250730-97ca.json` | 场景到主题 URL、帖子 ID、分类及邀请描述的映射，不含密码或邀请链接 |
| `.local/discourse/baseline-11250730-97ca.json` | 执行前目标数据库只读基线 |
| `.local/discourse/audit-11250730-97ca.json` | 执行后的目标数据库只读核查；DC-06 查询范围限制见后文 |
| `.local/discourse/summary/` | 从已存在报告提取的全量运行 JSON/CSV 指标，不访问站点或模型 |
| `.local/discourse/artifact-inventory.json` | 本机原始数据文件大小及 SHA-256 清单 |
| `.local/discourse/summary/qa-index-snapshot.sqlite` | 停止时 QA SQLite 索引的备份 |

上述原始数据、环境变量和凭据受 Git 忽略保护。提交候选文件仅含脚本、说明、经检查的截图，以及不含请求文本/密钥/邀请链接的运行指标索引。提交目录内 `run-index.json` 保存原始 `report.json` 的 SHA-256，便于核对本机原件。

## 接入故障与执行历史

### 模型权限与额度

最初使用 CSV 中配置及模型 `deepseek-v4.1-flash`，服务返回 HTTP 403 `AccessDenied.Unpurchased`。对应 DC-01/03 Run 分别为 `dc01-agent-2bf9b8f065`、`dc03-agent-cbe25cfea3`：均在规划前失败，无浏览器业务动作、无返回 token 用量。

改用另一经授权的模型配置后，`deepseek-v4.1-flash-1017` 返回 HTTP 200，随后真实执行多个场景。只替换本机 `.env` 的模型 URL、模型名和模型密钥，未引入参考环境的数据库 DSN。后续 DC-08/09 在执行中收到 `insufficient_quota`，最小请求确认服务提示免费额度耗尽；用户要求停止本轮。没有调整供应商计费设置，也没有继续 DC-10/11。

2026-11-25 16:43（北京时间），用户提供新的 API CSV 并要求续测。重新读取该文件中的密钥和兼容地址，使用模型 `deepseek-v4.1-flash` 发起最小请求，返回 HTTP 403 `AccessDenied.Unpurchased`，未返回用量。脱敏接入记录存于 `.local/discourse/new-model-probe.json`。本次只验证模型接入，未启动新的业务场景，既有 14 条 Run 与归档不变，也未用不可用的新配置覆盖本机模型设置。

2026-11-25 17:00（北京时间），使用随后提供的另一份 API CSV（文件编号 9108069）再次发起同一模型的最小调用，仍返回 `HTTP 403 / AccessDenied.Unpurchased`，没有返回用量。脱敏结果保存于 `.local/discourse/model-probe-9108069.json`；未创建新 Run、未操作被测场景、未覆盖本机模型配置。

### 导航超时与登录起点

模型恢复后的首轮 DC-01/03（`dc01-agent-0b12c96a49`、`dc03-agent-acd9a0fcf3`）均在初次 `browser.navigate` 超过适配器默认 5 秒上限，报 `BROWSER_ERROR / TOOL_TIMEOUT`。原始失败保留。随后测试脚本将适配器默认/最大等待设为 15 秒，引擎工具等待设为 12 秒，并使用显式 `--prepared` 登录夹具；代表性场景不是完整登录端到端测试。

预登录由独立 Chromium 上下文进行，再以内存 storage state 为该用例创建会话；账号登录行为先预检通过。Run 开始后的场景动作由 Agent 执行；独立复核另开浏览器上下文重新登录。登录准备和独立复核不在 Run 耗时/动作统计内。

### DC-02：精确 Reply 定位与显示名

首轮 `dc02-agent-463e4bae78` 命中多个 `button.create`，没有提交回复，原判定 `failed`；独立复核等待 post 2 超时，故没有可用独立结果。测试脚本提供 composer 范围 `#reply-control button.create` 后，重跑 `dc02-agent-5c6ed8270d` 成功提交一次精确文本。

数据库中作者用户名/姓名分别为 `waata_member` / `Member Fixture`，但主题页面 `.names` 仅显示用户名。上游另有 `display_name_on_posts` 开关（默认 false）；本轮准备只设置 `enable_names` 和 `prioritize_username_in_ux`，未设置该开关，因此显示名是夹具配置缺口。Agent 生成检查点遗漏作者显示条件，使 Run 判 `passed`；正文与作者账号正确不代表原完整预期已满足。停止后未补改站点或重跑。

### DC-04：自定义下拉未能保存

Agent 多次尝试 Larger 菜单项及文本定位，出现 8 次失败动作调用；18 次动作调用超过手册建议的 10 次，但未越过课程上限 35 次。重开后页面为 Normal，数据库仍为 `normal`，所以判失败正确。只读界面检查已识别选项是 `li.select-kit-row[data-value="larger"]`，但本轮未验证新的定位方案；不能把该候选定位写成已修复。

### DC-06：最终标题检查不足以证明书签流程

阶段截图确实显示 Activity → Bookmarks 中存在目标条目，故不能简单声称“没有创建书签”。随后跟随条目发生定位错误，Agent 通过直接导航回主题完成了标题检查；这不证明是跟随书签到达。独立新会话的书签页截图为空白，报告布尔值 `false` 混入了页面就绪问题，不能据此证明持久化不存在。

此外 `discourse-verify.rb` 的本轮书签查询仅覆盖 `bookmarkable_type="Post"`，而上游也支持 `Topic` 类型，因此其 `bookmarked:false` 不是“不存在任何主题书签”的结论。原始核查结果保留，未用不完整查询覆盖阶段证据。完整场景结论为证据不足；需要未来完善检查点、就绪等待、Topic/Post 查询与跟随验证后复测。

### DC-07：将检查操作误作点击

Agent 成功选择 Make Wiki，重开后又为确认 Remove Wiki 而实际点击，将 Wiki 撤销，并误点书签。最终数据库 `wiki=false`，正文不变；独立截图也显示普通帖及 Make Wiki，故 Run `failed` 正确，模型收尾文字声称“满足”不能作为依据。

本轮曾为减少反复付费观察而把 runner 工具集缩为 navigate/click/fill/select_option；DC-03、DC-01、首轮 DC-02 在此改动之前，其后运行使用缩减工具集。引擎的自动观察、确定性检查与最终截图始终保留，但缩减导致模型无法主动 observe/inspect，是本轮测试配置限制，可能影响 DC-04/06/07 等诊断和行为。不能将所有失败直接归因于默认 WAATA 配置。停止后未再改变工具配置或重跑。

### DC-08/09：额度中断与未完成复核

DC-08 没有保存目标邀请；DC-09 已记录普通帖无 Edit 的两个阶段，其中展开 More 后的阶段图可查看完整动作。两条 Run 在模型请求报错后均为 `errored / verdict=null`；独立会话均登录等待超时，不提供成功结论。只读核查显示 DC-09 Wiki 正文仍为初始值、Wiki 保留。DC-10/11 无 Run，仅存在初始测试数据。

## 数据和证据口径

- 14 条原始报告与 SQLite Run ID 集合一致。共 98 次已返回并捕获的模型响应、820,523 Token；最小连接探测及错误 HTTP 请求未计入此数，不等同供应商账单。
- Run 耗时总和 386.13 秒；部分 Run 并行执行，该和不是墙钟时间，也不含夹具登录、独立复核与部署耗时。
- 动作工具调用共 71 次，失败 13 次；策略拒绝或定位失败未必实际产生动作，计数是动作上界。引擎自动观察/断言/截图不列为业务动作。
- 引擎证据 123 项（115 观察 + 8 自动截图）；阶段和独立截图另计。没有生成 Playwright trace 文件，也没有配置 Langfuse。
- 早期两条权限错误报告的 `started_at` 曾在执行后写入；索引称为 recorded_at，避免伪造精确开始时间，其余按运行前时间记录。

## 交付工具与后续使用

| 文件 | 作用与本轮验证范围 |
| --- | --- |
| `scripts/discourse-local.ps1` | Windows 使用命名卷启动固定 Discourse；start/status 已验证，首次初始化流程的各操作在本机部署时执行，封装后的全新空卷 init 未再重跑 |
| `scripts/discourse-fixtures.rb` | 专用账号、分类、独立主题/回复、Wiki 和邀请夹具；prepare 已实际执行 |
| `scripts/discourse-agent-check.py` | 真实 C2/C3 Agent 运行、独立会话复核、自动截图、SQLite；保留当前本轮实际工具配置与已知局限 |
| `scripts/discourse-verify.rb` | 只读目标数据库核查，已执行；书签仅查 Post 的范围缺陷已明确记录 |
| `scripts/discourse-summarize.py` | 纯本地整理已存在数据，输出指标/摘要哈希并比对 SQLite；不调用模型、不访问站点 |

停止后只整理本机数据，可复现汇总：

```powershell
uv run --locked python scripts/discourse-summarize.py
```

未来恢复测试前，应先解决已记录的夹具/就绪/检查点/工具集问题，再确认模型额度和是否计入登录步骤。以下命令会运行真实业务，本轮停止后没有再执行：

```powershell
powershell -NoProfile -File scripts/discourse-local.ps1 start
uv run --locked python scripts/discourse-agent-check.py prepare
uv run --locked python scripts/discourse-agent-check.py preflight .local/discourse/fixture-<tag>.json
uv run --locked python scripts/discourse-agent-check.py run .local/discourse/fixture-<tag>.json DC01 --prepared
uv run --locked python scripts/discourse-agent-check.py audit .local/discourse/fixture-<tag>.json
```

重复运行前必须准备新的夹具或重置相应场景状态；不在旧结果上再次创建相同主题/回复或点赞。`--prepared` 不覆盖 Agent 登录测试，去掉它才从登录页开始。不要把已有成功状态用于冒充新一轮执行。

## 验证边界

本轮代表性业务执行与报告复核涉及 FR-001–FR-005、AC-02/03/04/07 的部分能力；不声称这些验收已全部完成。平台 PostgreSQL、FastAPI/Worker、Vue、SSE、取消和重启恢复均不在本轮已验证范围，本地 SQLite 不能作为 C6 验收依据。

停止前现有 Python 包 32 项测试及全仓库 pre-commit 通过；停止后仅检查整理脚本与文档格式、索引和文件一致性，不再启动业务测试。没有提交 Git commit、没有推送或创建 PR。
