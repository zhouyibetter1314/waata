# WAATA 本地 Web 应用测试手册

本手册提供 36 个可在固定版本上游站点练习的英文场景。每条列出数据前置条件、测试目标、预期行为和参考操作。运行时按实际报告与证据记录结果。

| 分工 | 固定版本与提交 | 本地入口 | 基础 / 进阶 / 综合 | 小计 |
| --- | --- | --- | --- | ---: |
| [组员 A · 4gaBoards](#4gaboards-组员-a) | `v3.2.16` · `b76dcc95` | `http://127.0.0.1:3000` | 5 / 5 / 3 | 13 |
| [组员 B · Admidio](#admidio-组员-b) | `v5.0.2` · `4484b503` | `http://127.0.0.1:8081` | 4 / 4 / 4 | 12 |
| [组员 C · Discourse](#discourse-组员-c) | `v2025.12.0-latest` · `3e7317b3` | `http://127.0.0.1:4200` | 4 / 4 / 3 | 11 |
| **合计** | | | **13 / 13 / 10** | **36** |

## 通用流程

1. 用下方脚本启动站点。脚本需要 Bash、Git、curl、OpenSSL、Docker 和支持 `up --wait` 的 Compose。在 Windows 上从启用 Docker 集成的 WSL2 运行。Discourse 优先用 Linux x86_64 或 WSL2。
2. 按场景准备英文界面、专用账号和可重置数据。把目标加入本地策略，启动 WAATA 的 API、Worker 和 Vue。[平台启动](../apps/api/README.md#本地启动与目标配置)
3. 在 [新建任务](http://127.0.0.1:5173/runs/new) 填写本地 URL、`Goal`、`Expected` 和专用凭据引用。如需先登录，在目标中说明。将场景中的标记替换为当次测试数据。`Steps` 用于复核执行路径，`Evidence` 用于核对过程中的状态。
4. 从 [运行记录](http://127.0.0.1:5173/runs) 按 Run ID 打开报告，核对实际结果、判定和证据。复跑前恢复前置条件。各场景预算是预估，执行结果由当次证据确定。[验收](../docs/04-acceptance.md)

### 目标策略与凭据引用

每台电脑的 `.local/targets.json` 是 JSON 数组。下面是一个目标对象的写法。将 `origin`、引用名、环境变量名和定位器换成该应用启动章节的值。多个角色在该目标的 `credentials` 里分别登记。环境变量的实际值放在本机 `.env` 或启动环境中，任务表单填写集合名，例如 `dc_member`，模型工具使用集合里的字段级引用。字段别名采用带站点和角色的唯一名称。WAATA 会脱敏这些别名及凭据值，过于通用的名字可能截断页面文字或选择器。 [C3 凭据填充](../contracts/tools/c3-browser-tools.md#54-browserfill)

```json
{
  "origin": "http://127.0.0.1:4200",
  "owners": ["local"],
  "actions": ["browser.navigate", "browser.click", "browser.fill", "browser.select_option"],
  "credentials": {
    "dc_member": {
      "dc_member_login": {
        "env": "WAATA_DC_MEMBER_LOGIN",
        "locator": { "strategy": "css", "value": "#login-account-name" }
      },
      "dc_member_password": {
        "env": "WAATA_DC_MEMBER_PASSWORD",
        "locator": { "strategy": "css", "value": "#login-account-password" }
      }
    }
  }
}
```

用例执行身份由其凭据引用决定。涉及权限的场景，先用管理员准备角色和内容，再给对应运行选择成员或管理员引用。Agent 根据页面观察选择唯一的控件定位器。凭据字段的 `locator` 用于绑定秘密与登录输入框。需要截图时，目标策略可设置 `allow_screenshots: true` 并配置 `screenshot_mask_selectors`，任务目标明确要求取证。普通表单内容可见，密码、凭据输入框和配置的敏感区域会遮挡。测试邮件、截图和报告使用虚构数据。 [C3 定位与截图](../contracts/tools/c3-browser-tools.md)

### 35 步与当前工具覆盖

- 按课程截图计数。每次点击、输入、选择、滚动、拖拽、导航各算 1 次，失败重试也算。计划预算含初始导航与登录，留出重试空间。到 35 次停止操作，只观察并报告。准备夹具和复跑时清理数据应在场景开始前完成。
- WAATA 默认的 `max_browser_actions_per_run=35` 计入已分发的导航、点击、填写和下拉选择。课程计数还包含部分工具拒绝与 WAATA 未提供的动作，复核时按两种口径分别记录。表单的「每用例 Agent 步骤上限」统计模型决策轮数，新建任务默认 `16`。较长用例可增加轮数，课程操作数仍需单独核对。 [C2 运行预算](../contracts/waata/c2-waata-python-api.md#3-请求与配置) · [C3 预算口径](../contracts/tools/c3-browser-tools.md#72-预算和副作用)
- 当前 C3 提供 `navigate`、`click`、`fill`、`select_option`、`observe`、`inspect` 和 `screenshot`。需要拖拽、显式滚动、文件上传或读取下载文件的环节按场景说明做手工对照。有等价界面入口时，报告记录实际使用的路径。结果表可填「需手工对照」，并附上可复核证据。 [C3 工具清单](../contracts/tools/c3-browser-tools.md#4-工具清单)

组员交接时为每个场景填一行。应用版本来自上表，运行结果以报告判定和实际证据为准。团队汇总时保留每个场景一条结果，等权统计。课程场景通过率按教师的标准答案、证据和步数核算，保留 WAATA 判定准确识别出的应用缺陷及工具缺口。

| 场景 ID | WAATA 版本 / 模型 / 应用版本 | 账号角色与夹具 | Run ID | 课程操作数 / WAATA 动作数 | 实际结果与证据 ID | 判定与原因 |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

## 4gaBoards 组员 A

项目创建场景参考跨模块契约示例。[子模块版本](../testsites/README.md) · [项目创建参考](../contracts/examples/README.md)

### 本地启动 4gaBoards

```bash
bash scripts/4gaboards.sh start
```

脚本使用独立 Compose 项目、固定版本镜像和本地数据卷。首次部署会生成 `.local/4gaboards/docker-compose.yml` 和本机凭据文件。新库的测试管理员是 `waataadmin`，密码在 `.local/4gaboards/.env` 的 `BOARDS_ADMIN_PASSWORD` 中。已有 Compose 配置和数据库卷会继续使用原有账号。

打开 [4gaBoards](http://127.0.0.1:3000/)，登录后确认项目面板和侧边栏可见。 [启动脚本](../scripts/4gaboards.sh) · [固定版本部署说明](../testsites/4gaboards/README.md#deploy)

### WAATA 与夹具

- 场景从 `http://127.0.0.1:3000/` 发起。项目和看板深链分别形如 `/projects/<id>`、`/boards/<id>`。提前在人工准备夹具时记下实际 URL，把场景中的对象名和对应本地 URL 填进英文目标。登录后按需要导航到已记录的项目或看板。
- 4gaBoards 目标策略可授权 `browser.navigate`、`browser.click` 和 `browser.fill`，同源 WebSocket 使用 `/socket.io/`。凭据集合可用 `boards_admin`，字段别名 `boards_admin_login_ref` 和 `boards_admin_pass_ref` 分别映射 `WAATA_BOARDS_ADMIN_LOGIN` 和 `WAATA_BOARDS_ADMIN_PASSWORD`。对应定位器是 `input[name="emailOrUsername"]`、`input[name="password"]`。英文界面中登录按钮为 `Log in`。
- 准备一个能创建项目且是目标项目经理的专用账号。进入其偏好设置选择英文，保持侧边栏可见。项目、列表、卡片用不同的场景编号命名，每条场景开始前单独准备夹具。点击自定义下拉框的条目时使用 `browser.click`。`browser.select_option` 适用于原生 `<select>`。
- 以下英文 `Goal` 和 `Expected` 可直接复制到平台。英文 `Steps` 是执行顺序，若同一次 WAATA Run 须遵循指定顺序，可和 `Goal` 一起提交。预算为包含登录和导航的估算，队员按课程口径另记重试。手工场景的 WAATA 字段用于复核其中可自动观察的部分。

### Basic（基础）· 5

#### B01 — Create a project and find both entries

- **Fixture** Use the home page with the sidebar open. The project `B01 Release Lab` is absent and the test account can create projects.
- **Goal** Sign in using the authorized test account. Create a project named `B01 Release Lab` and verify that it appears on the dashboard and in the sidebar.
- **Expected** After returning to the dashboard, a project tile and a distinct sidebar link both display `B01 Release Lab`.
- **Steps** Open `Add Project` on the dashboard, fill the name, click `Add Project`, then return to the dashboard and inspect both regions. **Budget** 10 operations.

#### B02 — Rename a project

- **Fixture** Create `B02 Draft Lab`. Leave `B02 Review Lab` unused. Keep the sidebar open, with the test account as the project manager.
- **Goal** Rename `B02 Draft Lab` to `B02 Review Lab` using the project's edit menu, then reopen the dashboard to check the stored name.
- **Expected** The same project link displays `B02 Review Lab` in the sidebar and the dashboard shows the new name. The old title is absent from both regions.
- **Steps** Sign in, open the sidebar project's `Edit Project` menu, select `Rename Project`, replace the name, save, and return to the dashboard. **Budget** 12 operations.

#### B03 — Add a board from the Kanban template

- **Fixture** An empty project `B03 Delivery Lab` with the test account as its manager. The board `B03 Workflow` is absent.
- **Goal** Add `B03 Workflow` to project `B03 Delivery Lab`. Select the Kanban template and open the resulting board.
- **Expected** The board named `B03 Workflow` contains lists named `Open`, `Todo`, `In Progress`, `To Test`, and `Done`.
- **Steps** Sign in, open the project, click `Add Board`, fill the board name, choose `Kanban` from the template dropdown, click `Add Board`, and open the board if needed. **Budget** 14 operations.

#### B04 — Add a list on an empty board

- **Fixture** An existing board `B04 Intake` created with the Empty template, openable in board view by the test account.
- **Goal** Add a list named `B04 Incoming` to `B04 Intake`, then revisit the board.
- **Expected** The list heading `B04 Incoming` appears once on the same board after revisiting it.
- **Steps** Sign in, open the board, click `Add List`, fill the list name, click `Add list`, and navigate back to the recorded board URL. **Budget** 10 operations.

#### B05 — Create a card in a specified list

- **Fixture** Board `B05 Support` has one list named `B05 Inbox`. The card title `B05 Confirm delivery` is unused.
- **Goal** Create one card named `B05 Confirm delivery` in `B05 Inbox` on `B05 Support`.
- **Expected** The new card appears inside `B05 Inbox`, and opening it shows `B05 Confirm delivery` as the card title.
- **Steps** Sign in, open the board, use the list's `Add card` control, fill the title, click the add control, and open the card to inspect it. **Budget** 11 operations.

### Intermediate（进阶）· 5

#### B06 — Save a card description

- **Fixture** Board `B06 Notes` has the card `B06 Handover` with an empty description. The test account can edit the card.
- **Goal** Set the description on `B06 Handover` to `Confirm pickup at the north desk.` Reopen the card and check the saved description.
- **Expected** The card still has title `B06 Handover` and displays the exact sentence `Confirm pickup at the north desk.` in its description.
- **Steps** Sign in, open the board and card, click `Add description`, fill the editor with placeholder `Enter description...` in Edit mode, click `Save`, close the modal, then reopen the card. **Budget** 14 operations.

#### B07 — Filter cards by a text query

- **Fixture** Board `B07 Search` contains exactly the cards `B07 Quartz queue` and `B07 Amber queue`, without other content mentioning `Quartz`. Clear the board's filters before the run.
- **Goal** Use the board's card search with the text `Quartz` and inspect the filtered board.
- **Expected** `B07 Quartz queue` is visible and `B07 Amber queue` is absent from the filtered card results.
- **Steps** Sign in, open the board, fill `Filter cards...` with `Quartz`, and leave the filter applied for verification. **Budget** 9 operations.

#### B08 — Filter cards by label

- **Fixture** Board `B08 Labels` contains `B08 Red parcel` with label `B08 Priority` and `B08 Blue parcel` without that label. Clear the board's filters before the run.
- **Goal** Apply the `B08 Priority` label filter on `B08 Labels` and inspect its visible cards.
- **Expected** The applied label is shown, `B08 Red parcel` is visible, and `B08 Blue parcel` is absent from the result.
- **Steps** Sign in, open the board, choose `Filter By Labels`, click `B08 Priority`, and close the picker with the filter active. **Budget** 12 operations.

#### B09 — Move a card to another list on the same board

- **Fixture** Board `B09 Work` contains list `B09 Pending` with card `B09 Verify totals`, and an empty list `B09 Reviewed`. The test account can edit the card.
- **Goal** Move `B09 Verify totals` from `B09 Pending` to `B09 Reviewed` using the card's list selector. Reopen the card to verify its list.
- **Expected** `B09 Reviewed` is the card's selected list and there is no copy of `B09 Verify totals` in `B09 Pending`.
- **Steps** Sign in, open the board and card, click its current list in the card modal, choose `B09 Reviewed`, close the card, revisit the board and reopen it. **Budget** 14 operations.

#### B10 — Transfer a card to a second board

- **Fixture** Project `B10 Transfer Lab` contains boards `B10 Requests` and `B10 Fulfilment`. `B10 Inspect parcel` is in `B10 Requests` → `B10 Queue`. Destination list `B10 Received` exists and is empty. Record both board URLs. The test account can edit both boards.
- **Goal** Transfer `B10 Inspect parcel` to `B10 Fulfilment` → `B10 Received` using the card's Move action. Inspect the source board before the final destination check.
- **Expected** The original card is visible exactly once in `B10 Received` on the final board `B10 Fulfilment`.
- **Evidence** The source board observation taken before checking the destination shows that the card is absent from `B10 Requests`.
- **Steps** Sign in, open the source board and card, choose `Edit Card` → `Move Card`, select the destination board and list, click `Move`, then record an observation on the source board and finish on the destination board. **Budget** 20 operations.

### Advanced（综合）· 3

#### B11 — Reorder two cards by dragging

- **Fixture** Board `B11 Sequence` contains a single list `B11 Queue` with, from top to bottom, `B11 First parcel` and `B11 Second parcel`. Both are visible at once. The test account can edit them.
- **Goal** Drag `B11 Second parcel` above `B11 First parcel` within `B11 Queue`, then revisit the board to check the saved order.
- **Expected** The list contains exactly those two cards in the new order, second parcel first and first parcel second, after revisiting.
- **Steps** In a regular browser, sign in, open the board, drag the second card above the first, then revisit the board and record the order. **Budget** 10 operations.
- **WAATA follow-up** Use `Sign in and inspect the two cards in B11 Queue after the manual reorder.` as Goal. Require both cards to appear exactly once in the same list. Add order as an automated checkpoint only if the team has verified an approved order-sensitive locator. Keep the manual order evidence with the Run ID.

#### B12 — Export a small board archive

- **Fixture** Board `B12 Sample Export` has one list `B12 Ready` and one card `B12 Archive item`, with synthetic data only and no attachments. The test account manages its project. Keep the source board URL.
- **Goal** Export the board `B12 Sample Export` with attachments excluded and verify that the browser receives a nonempty 4gaBoards `.tgz` archive.
- **Expected** The board export produces a readable `.tgz` archive. Save it as a local fixture for the import exercise if desired.
- **Steps** In a regular browser, sign in, open the board, choose `Edit Board` in the sidebar, open `Export Board`, select `Skip attachments`, click `Export Board`, and confirm the downloaded archive is readable with `tar -tzf <archive.tgz>`. **Budget** 13 browser operations.
- **WAATA follow-up** Use `Sign in, open the Export Board options for B12 Sample Export, and inspect the options without submitting the export.` as Goal. Require the `Export Board` dialog and `Skip attachments` option to be visible. Keep the archive proof separately.

#### B13 — Import a board into a separate project

- **Fixture** Prepare a valid 4gaBoards `.tgz` from the same version with list `B12 Ready` and card `B12 Archive item`. It can be prepared before either exercise. Project `B13 Import Lab` has no board named `B13 Restored Board`. The test account manages it.
- **Goal** Import the prepared 4gaBoards board archive into `B13 Import Lab` as `B13 Restored Board`. Open the board and verify its restored structure.
- **Expected** `B13 Restored Board` is visible in the destination project. On the imported board, list `B12 Ready` contains card `B12 Archive item`.
- **Steps** In a regular browser, sign in, open the destination project, click `Add Board`, enter the new name, choose `Import` → `From 4ga Boards`, select the fixture `.tgz`, leave user and project-manager imports unchecked, click `Import Board`, and open the result. **Budget** 17 operations.
- **WAATA follow-up** Use `Sign in, open B13 Restored Board in B13 Import Lab, and verify its restored list and card.` as Goal, with the expected board contents above. Record the manual file selection and import alongside the Run ID.

B11 验证拖拽手势，B12 验证下载文件，B13 验证文件选择器和导入的实际保存结果。目前 C3 工具没有独立的拖拽或文件上传接口，适配器会取消下载。请把人工结果和 WAATA 后续观察各自记录，尤其在导出提示出现时还要验证本地文件。[C3 工具](../contracts/tools/c3-browser-tools.md) · [浏览器下载处理](../packages/waata/src/waata/browser/session.py) · [4gaBoards 导入界面实现](../testsites/4gaboards/client/src/components/BoardAddPopup/ImportStep.jsx)

## Admidio 组员 B

负责成员使用本地 `http://127.0.0.1:8081`。本组含 12 个场景，其中 Basic、Intermediate、Advanced 各 4 个。覆盖联系人、角色成员关系、角色权限及活动日程和报名。

### 启动 Admidio

```bash
bash scripts/admidio.sh start
```

Compose 从固定子模块构建应用并运行 MariaDB。首次启动需要下载构建依赖。脚本将配置和随机数据库密码放在 `.local/admidio/`，数据库与应用数据使用命名卷。 [启动脚本](../scripts/admidio.sh) · [上游容器说明](../testsites/admidio/README-Docker.md)

1. 首次打开[安装向导](http://127.0.0.1:8081/install/index.php)。组织短名填 `WAATA`，名称可填 `WAATA Admidio Lab`，时区选 `Asia/Shanghai`。创建专用管理员，邮件使用保留测试域，例如 `admin@example.invalid`。活动夹具关闭通知邮件。
2. 打开[登录页](http://127.0.0.1:8081/system/login.php)，确认能登录并打开英文界面的 `Contacts`、`Groups & roles` 和 `Events`。

### WAATA 接入和准备数据

- 目标地址统一填写 `http://127.0.0.1:8081/system/login.php`。在目标策略添加 origin `http://127.0.0.1:8081`，分配本机任务所有者，允许 `browser.navigate`、`browser.click`、`browser.fill`、`browser.select_option`。下表的字段级引用分别绑定用户名和密码输入框。在 `credentials` 下以凭据集合为键，例如 `admidio_admin`。在集合对象中以字段级引用为键，值包含对应的 `env` 和 `locator`（`strategy: css`、`value: #usr_login_name` 或 `#usr_password`）。
- 在应用内准备三个专用账号。管理员负责联系人、角色和活动配置。普通会员在组织内已可登录，另有参加活动用的普通角色。活动编辑员仅需要其专用角色的 **Manage events**，保留普通账号所需的组织成员身份。管理员可从 `Contacts` 创建测试联系人，在 `Create member` 表单填写 `Username`，并分配普通成员角色。测试联系人可留空邮箱，在用户的资料页点击 `Change password` 设置本地测试密码。测试管理员先手工验证这些账号在无痕窗口均可登录。账号环境变量写入 WAATA 的本地环境，网页提交时填写表中的凭据引用。
- 在 `Groups & roles` 准备角色类别 `WAATA Training`，在 `Events` 准备日历 `WAATA Events`。后者对相应测试角色可见，事件编辑员可管理。各场景用独立的联系人、角色、活动或初始状态，实际提交时将 `{R}` 替换为本次编号。按日期的活动使用测试当天之后的日期，统一替换 `{DATE}` 为 `YYYY-MM-DD`，并记录系统时区。权限和报名场景可从初始状态各自准备，便于独立重跑。
- 登录使用 **Username**、**Password**、**Sign in**。如果组织尚未预选，选 **WAATA**。运行下列场景时，在目标开头加上 `Sign in with the supplied test credential and select WAATA if the organization is not already selected.` 预算包含初始导航、登录和可选组织选择。若字段用增强下拉呈现，可点击可见下拉和选项。原生单选可使用 `browser.select_option`。界面自动刷新属于应用结果，证据检查用 `browser.observe` 或 `browser.inspect`。

| 凭据集合 | 用户名字段引用及环境变量 | 密码字段引用及环境变量 |
| --- | --- | --- |
| `admidio_admin` | `admidio_admin_login_ref` · `ADMIDIO_WAATA_ADMIN_USERNAME` | `admidio_admin_pass_ref` · `ADMIDIO_WAATA_ADMIN_PASSWORD` |
| `admidio_member` | `admidio_member_login_ref` · `ADMIDIO_WAATA_MEMBER_USERNAME` | `admidio_member_pass_ref` · `ADMIDIO_WAATA_MEMBER_PASSWORD` |
| `admidio_editor` | `admidio_editor_login_ref` · `ADMIDIO_WAATA_EDITOR_USERNAME` | `admidio_editor_pass_ref` · `ADMIDIO_WAATA_EDITOR_PASSWORD` |

[登录表单源码](../testsites/admidio/system/classes/ModuleLogin.php) · [英文界面字典](../testsites/admidio/languages/en.xml) · [目标策略配置](../apps/api/README.md#配置一个你有权限测试的站点)

### Basic（基础）· 4

#### ADM-01 · Create a contact

- **Fixture** Use `admidio_admin`. No contact uses the name Ava Fixture{R}. The administrator can create contacts.
- **Goal** Create a contact named Ava Fixture{R} and find that contact in Contacts.
- **Expected** Contacts contains one matching entry for Ava Fixture{R} after saving.
- **Steps** Sign in. Open **Contacts** and click **Create contact**. Fill **First name** and **Surname**, then submit. On the **Create member** profile form, keep the supplied name and click **Save**. If the role assignment page opens, leave default memberships in place. Return to **Contacts** and search for `Fixture{R}`.
- **Budget** Up to 16.

#### ADM-02 · Update one contact field

- **Fixture** Use `admidio_admin`. Contacts contains one entry named Ben Fixture{R} with a City different from `Fixture Harbor`.
- **Goal** Change Ben Fixture{R}'s City to Fixture Harbor and reopen the saved profile.
- **Expected** Ben Fixture{R}'s profile shows City as Fixture Harbor after a new navigation to that profile.
- **Steps** Sign in. Open **Contacts**, search for the test contact and open their profile. Click **Edit profile**, fill **City**, click **Save**, and revisit the profile.
- **Budget** Up to 15.

#### ADM-03 · Create a role

- **Fixture** Use `admidio_admin`. The role category `WAATA Training` exists and has no role named `Volunteer Crew {R}`.
- **Goal** Create a role named Volunteer Crew {R} in the WAATA Training category.
- **Expected** The Groups & roles list shows one active role named Volunteer Crew {R} in WAATA Training.
- **Steps** Sign in. Open **Groups & roles** and click **Create role**. Fill **Name**, select `WAATA Training` in **Category**, then click **Save**. Return to the active role list and filter by category if necessary.
- **Budget** Up to 15.

#### ADM-04 · Read an upcoming event

- **Fixture** Use `admidio_member`. A published future event `Open Studio {R}` in `WAATA Events` is visible to that account and has venue `West Room`. Record the event detail link during setup.
- **Goal** Open the upcoming Open Studio {R} event and check its published venue.
- **Expected** The event detail shows the title Open Studio {R}, the WAATA Events calendar and venue West Room.
- **Steps** Sign in. Open **Events**, then open the event using its visible title or the recorded same-origin detail link. Read the title, calendar and venue on the detail page.
- **Budget** Up to 10.

### Intermediate（进阶）· 4

#### ADM-05 · Assign a contact to an existing role

- **Fixture** Use `admidio_admin`. Contact Casey Fixture{R} and active role `Welcome Team {R}` exist. The contact is not a member of that role. Record the exact checkbox selector `#role-{ROLE_UUID}` from the assignment dialog for this run if the UI label is ambiguous.
- **Goal** Assign Casey Fixture{R} to Welcome Team {R} as a regular member.
- **Expected** The role appears under Current role memberships on Casey Fixture{R}'s profile after reopening the profile.
- **Steps** Sign in, find Casey Fixture{R} in **Contacts** and open the profile. Open **Role memberships**, then **Change role memberships**. Click the membership checkbox on the `Welcome Team {R}` row. Wait for the automatic save, close the dialog, and reopen the Profile and **Role memberships**.
- **Budget** Up to 18.

#### ADM-06 · End a single role membership

- **Fixture** Use `admidio_admin`. Dana Fixture{R} has regular organization membership and is also currently a member of `Short Project {R}`. Show current and former memberships in the profile preferences. Ensure the membership began before the test date.
- **Goal** End Dana Fixture{R}'s membership in Short Project {R}.
- **Expected** Dana Fixture{R} still has a profile, and Short Project {R} is shown under Former role memberships rather than Current role memberships.
- **Steps** Sign in. Open Dana Fixture{R}'s profile via **Contacts**, open **Role memberships → Change role memberships**, and clear the checkbox of `Short Project {R}`. Wait for the automatic save, close the dialog and revisit the role memberships.
- **Budget** Up to 18.

#### ADM-07 · Publish a calendar event

- **Fixture** Use `admidio_admin`. `WAATA Events` is available for event creation. No event `Planning Session {R}` exists. Select a future `{DATE}` with time 14:00–15:00.
- **Goal** Create Planning Session {R} in WAATA Events on {DATE} from 14:00 to 15:00 at North Room.
- **Expected** A single upcoming event shows the title Planning Session {R}, the selected calendar, the expected date/time range and North Room.
- **Steps** Sign in and choose **Events → Create event**. Fill **Title** and **Venue**. Use the date and time fields for **Start** and **End**. Select `WAATA Events` in **Calendar**, click **Save**, and open the saved event from the list or save destination.
- **Budget** Up to 20.

#### ADM-08 · Reschedule an existing event

- **Fixture** Use `admidio_admin`. The future event `Review Slot {R}` exists in `WAATA Events`, starts at 14:00 and ends at 15:00 on the recorded date. It has no participants. Record the same-origin **Edit event** link when setting up.
- **Goal** Move Review Slot {R} to 16:00–17:00 on its existing date and change its venue to East Room.
- **Expected** The existing event has the same title and calendar and shows 16:00–17:00 and East Room after reopening the event.
- **Steps** Sign in and open **Events**. Open the target event and choose **Edit event** or use its recorded edit link. Fill the two time fields and **Venue**. Click **Save** and reopen the event detail.
- **Budget** Up to 17.

### Advanced（综合）· 4

#### ADM-09 · Delegate event management to a role

- **Fixture** Use `admidio_admin`. The custom role `Event Editors {R}` exists in `WAATA Training` and has no **Manage events** permission. The Events module is enabled.
- **Goal** Enable the Manage events permission for the Event Editors {R} role and verify it persists. Inspect the permitted CSS locator `#rol_events:checked` on the reopened form.
- **Expected** The edit form for Event Editors {R} shows Manage events checked after a fresh navigation. The role is still in WAATA Training.
- **Steps** Sign in and open **Groups & roles**. Locate the exact role and enter **Edit role**. Click **Manage events** once and save. Reopen the same role's edit page and inspect `#rol_events:checked` for existence. This verifies saved configuration without relying on the icon-only permission column.
- **Budget** Up to 16.

#### ADM-10 · Use delegated event permissions

- **Fixture** Use `admidio_editor`. The editor is a member of the fixture role `Event Editors {R}` with **Manage events**, plus regular membership required for login. `WAATA Events` is available to this account. No event named `Editor Briefing {R}` exists. Choose a future `{DATE}`.
- **Goal** As the event editor, create Editor Briefing {R} in WAATA Events on {DATE} from 10:00 to 11:00.
- **Expected** The event editor has access to the Create event control, and the saved Editor Briefing {R} appears in the calendar with the requested date and time.
- **Steps** Sign in as the event editor. Open **Events → Create event**. Fill **Title** and Start/End date/time, select **Calendar**, click **Save**, and open the upcoming event.
- **Budget** Up to 20.

#### ADM-11 · Register as an eligible member

- **Fixture** Use `admidio_member`. Published future event `Community Walk {R}` is visible and open for registration to the member's ordinary role. No deadline or capacity restriction is active. The test user has no existing attendance. Turn off guest and comment fields on this event for the simple participation menu.
- **Goal** Register the member for Community Walk {R} and verify the saved attendance status.
- **Expected** The same event displays I take part after reopening the event detail.
- **Steps** Sign in. Open **Events** and the exact event detail. Open the **Participate** dropdown and choose **Participate**. After the page updates, reopen that event and read its attendance status.
- **Budget** Up to 14.

#### ADM-12 · Cancel enrollment without removing the event

- **Fixture** Use `admidio_member`. Published future event `Workshop Seat {R}` is open for registration, the account has existing confirmed attendance, and the organization saves cancellations. Turn off guest and comment fields on this event for the simple participation menu.
- **Goal** Cancel the member's own attendance for Workshop Seat {R} and verify the event remains published.
- **Expected** Workshop Seat {R} still opens and its member attendance status shows Participation canceled after reopening.
- **Steps** Sign in and open the exact event detail. Open **I take part**, choose **Cancel**, and wait for the update. Reopen the event detail and verify its title and cancellation status.
- **Budget** Up to 14.

[联系人模块](../testsites/admidio/modules/contacts/contacts.php) · [资料与角色分配](../testsites/admidio/modules/profile/roles.php) · [角色权限表单](../testsites/admidio/src/UI/Presenter/GroupsRolesPresenter.php) · [活动表单](../testsites/admidio/modules/events/events_new.php) · [活动与报名](../testsites/admidio/modules/events/events.php)

## Discourse 组员 C

### 启动本地 Discourse

```bash
bash scripts/discourse.sh init
bash scripts/discourse.sh start
```

首次在交互式终端运行 `init`。脚本把固定源码复制到 `.local/discourse/src`，安装依赖、迁移数据库，并提示创建本地测试管理员。输入测试邮箱（例如 `waata_admin@example.test`），设置密码并确认授予管理员权限。之后用 `start` 启动论坛和本地邮件收件箱。首次前端编译可能需要几分钟。 [启动脚本](../scripts/discourse.sh) · [固定版开发容器](../testsites/discourse/.devcontainer/devcontainer.json) · [上游开发容器指南](https://meta.discourse.org/t/install-discourse-for-development-using-docker/102009)

1. 打开[论坛登录页](http://127.0.0.1:4200/login)，用初始化时创建的专用管理员登录。
2. 注册普通测试账号 `waata_member`（例如 `waata_member@example.test`），公开显示名取 `Member Fixture`。在[本地邮件收件箱](http://127.0.0.1:8025/)完成激活，随后在管理员用户详情把该账号设置为 Trust Level 1。
3. 创建公开分类 `WAATA Lab`，让普通测试账号能创建主题和回复，再按下文准备测试数据。

### Discourse 场景准备

- 将 `http://127.0.0.1:4200` 加入本地 WAATA 目标策略，登记 `dc_member` 与 `dc_admin` 两组凭据引用。会员使用本页通用示例中的字段和环境变量。管理员沿用相同定位器，把相应的 `member`、`MEMBER` 替换为 `admin`、`ADMIN`。固定版登录字段为 `#login-account-name`、`#login-account-password`。 [登录表单](../testsites/discourse/frontend/discourse/app/components/local-login-form.gjs) · [Wiki 指示器](../testsites/discourse/frontend/discourse/app/components/post/meta-data/edits-indicator.gjs)
- 目标地址统一填 `http://127.0.0.1:4200/login`，把对应角色的凭据引用填在专用字段。登录凭据用测试邮箱，资料页路径使用对应的论坛用户名。步骤数预估包含打开登录页、填写账号、填写密码和点击登录。每条有独立的初始状态，表中路径里的 `{member}`、`{admin}`、`{topic}` 需要换成当次账号名或完整同源路径。`{tag}` 用同一次运行的唯一标识替换。去除首次登录的提示后，从新会话验证流程。
- 帖子用英语原文。输入框如果显示富文本编辑器，在本地固定副本中确认已使用上面的 Markdown 编辑配置。自定义下拉通过点击打开和点击选项完成。带有同名操作的页面使用明确的分类、主题、帖号或上下文来限定目标。
- 邀请练习使用本地未兑换链接。`Pending` 页仅验证描述、行状态及兑换计数。保存证据时使用结构化观察，避免读取或记录邀请链接值。账号激活和邮件检查在 WAATA 运行前由组员通过本地收件箱完成。 [邀请系统测试](../testsites/discourse/spec/system/create_invite_spec.rb) · [邀请列表操作](../testsites/discourse/frontend/discourse/app/templates/user-invited/show.gjs)

### Basic（基础）· 4

#### DC-01 · Create a topic

- **Fixture** Use `dc_member`. The public `WAATA Lab` category is open for new member topics. Use an unused title. When repeating the scenario, update `DC01-01` to the same new value in Goal and Expected.
- **Goal** Sign in with the supplied test credential. Open All categories and enter WAATA Lab before clicking New Topic. Enter the title “WAATA launch checklist DC01-01” and the body “The local team will review the launch checklist before opening the forum.” Click Create Topic and wait until the new topic page opens.
- **Expected** A new topic titled “WAATA launch checklist DC01-01” is published. It belongs to the “WAATA Lab” category. Its first post reads exactly “The local team will review the launch checklist before opening the forum.”
- **Steps** Sign in. Open the WAATA Lab category. Click New Topic. Fill title and body. Choose WAATA Lab if the category is not preselected. Click Create Topic. Inspect the topic page.
- **Budget** 12 operations.

#### DC-02 · Reply to a topic

- **Fixture** Use `dc_member`. The administrator has an open topic `{topic}` titled “WAATA reply practice”. The reply text below is unused.
- **Goal** Reply to the WAATA reply practice topic with “I reviewed the local fixture and confirmed that the discussion is ready for testing.”
- **Expected** The same topic displays the new reply with the supplied text below the first post, attributed to the fixture member's public display name.
- **Steps** Sign in. Open `{topic}`. Click the topic Reply action. Fill the body. Click Reply in the composer. Inspect the rendered reply.
- **Budget** 9 operations.

#### DC-03 · Like a post and verify persistence

- **Fixture** Use `dc_member`. An open topic `{topic}` has a single first post by the administrator. Start with the member’s reaction unset.
- **Goal** Like the first post in the specified topic once, then return to that topic to verify the result.
- **Expected** The first post still shows the member's liked state after reopening, with the Undo like action available.
- **Steps** Sign in. Open `{topic}`. Click Like on its first post. Navigate again to `{topic}`. Inspect the first post's Undo like action.
- **Budget** 8 operations.

#### DC-04 · Save a text-size preference

- **Fixture** Use `dc_member`. Interface Text Size is Normal and the device-only text-size override is off.
- **Goal** Change my forum Text Size preference from Normal to Larger and save it for this account.
- **Expected** The Interface settings show Larger after reopening, and the page reflects the larger text-size setting.
- **Steps** Sign in. Open `/u/{member}/preferences/interface`. Open Text Size. Choose Larger. Click Save Changes. Reopen the Interface settings. Inspect the selected value.
- **Budget** 10 operations.

### Intermediate（进阶）· 4

#### DC-05 · Edit a member reply

- **Fixture** Use `dc_member`. The member can still edit their reply “The test meeting starts on Thursday.” in open topic `{topic}`.
- **Goal** Edit my reply in the specified topic to read “The local test meeting starts on Friday at ten in the morning.”
- **Expected** The same reply shows the revised text after reopening the topic. The old sentence is absent from that reply.
- **Steps** Sign in. Open `{topic}`. Open the reply's More menu if needed. Click Edit. Replace the body. Click Save Edit. Reopen the topic. Inspect the reply.
- **Budget** 12 operations.

#### DC-06 · Bookmark a topic and find it in Activity

- **Fixture** Use `dc_member`. An open topic `{topic}` is titled “WAATA bookmark practice” and is absent from the member’s bookmarks.
- **Goal** Bookmark the WAATA bookmark practice topic without a reminder and find the saved topic in my personal bookmarks.
- **Expected** Following the saved bookmark reopens exactly the target topic.
- **Evidence** Keep the observation of the matching entry in Activity bookmarks before following it.
- **Steps** Sign in. Open `{topic}`. Click the topic-level Bookmark. Navigate to `/u/{member}/activity/bookmarks`. Inspect the exact topic entry. Click the entry. Inspect the title.
- **Budget** 10 operations.

#### DC-07 · Convert the first post to a Wiki

- **Fixture** Use `dc_admin`. An open topic `{topic}` in WAATA Lab contains a single ordinary post.
- **Goal** Convert the first post of the specified topic into a Wiki while keeping its content unchanged.
- **Expected** The first post retains its content and shows the Wiki indicator after reopening the topic. Its post Admin menu contains Remove Wiki.
- **Steps** Sign in. Open `{topic}`. Open the first post's More menu if needed. Open its post Admin menu. Click Make Wiki. Reopen the topic. Open the same post menu and inspect the state.
- **Budget** 14 operations.

#### DC-08 · Create a local invitation link

- **Fixture** Use `dc_admin` with invite permission. The name “WAATA practice invite {tag}” is unused in Pending.
- **Goal** Create a local link invitation named “WAATA practice invite {tag}” with one use and no email recipient.
- **Expected** Pending shows the invitation description with zero of one uses redeemed and a future expiry.
- **Steps** Sign in. Open `/u/{admin}/invited/pending`. Click Invite or Create invite link. Open Edit link options. Fill Description and Max uses. Leave Restrict to blank. Click Create link. Close the modal. Inspect the matching Pending row.
- **Budget** 15 operations.

### Advanced（综合）· 3

#### DC-09 · Edit another user's Wiki as a regular member

- **Fixture** `dc_member` at Trust Level 1. `{wiki-topic}` and `{ordinary-topic}` each have one first post by the administrator. The first is a Wiki and the second is ordinary. Trust Level 1 is allowed to edit Wiki posts.
- **Goal** Verify the ordinary control post has no Edit action for my member account. Edit the other topic's Wiki first post to “The shared test guide now includes a local account verification step.”
- **Expected** The Wiki shows the new text after reopening and keeps the Wiki indicator.
- **Evidence** The ordinary control post exposes no Edit action to the member account when its available actions are inspected.
- **Steps** Sign in. Open `{ordinary-topic}`. Inspect the first post and its available actions. Open `{wiki-topic}`. Click Edit on the Wiki. Replace the body. Click Save Edit. Reopen the Wiki topic. Inspect the text and Wiki indicator. Retain the control observation before moving to the Wiki.
- **Budget** 15 operations.

#### DC-10 · Update a Wiki and return it to an ordinary post

- **Fixture** Use `dc_admin`. The Wiki post in `{topic}` reads “The fixture checklist currently describes a draft handoff.”
- **Goal** Update the Wiki body to “The fixture checklist records the completed handoff for the local project.” Then remove Wiki status from that same post.
- **Expected** After reopening, the updated body is still present, the Wiki indicator is absent, and the first post's Admin menu offers Make Wiki.
- **Steps** Sign in. Open `{topic}`. Click Edit. Fill the revised body. Click Save Edit. Open the first post's More menu and then its Admin menu. Click Remove Wiki. Reopen the same topic. Inspect the post and its Admin menu.
- **Budget** 18 operations.

#### DC-11 · Change and remove one pending invitation

- **Fixture** Use `dc_admin`. Pending contains two unredeemed links. The “WAATA scoped invite {tag}” link has two uses and the “WAATA keep invite {tag}” link is the control. Create both during fixture setup if absent.
- **Goal** Update only “WAATA scoped invite {tag}” to one use, verify the updated pending row and then remove that invitation. Leave the keep invitation available.
- **Expected** After removal and reopening Pending, the scoped row is absent and the keep invitation is still listed.
- **Evidence** Before removal, the scoped row shows zero of one uses redeemed.
- **Steps** Sign in. Open `/u/{admin}/invited/pending`. Click Edit on the scoped row. Change Max uses to one. Click Update. Close the modal. Inspect the scoped row. Open More options on that row and click Remove. Reopen Pending. Inspect both descriptions. Retain the updated row observation before removal.
- **Budget** 20 operations.

复跑前重置该场景的初始条件，例如对测试账号取消点赞或书签，把字号改回 Normal，还原测试帖的正文和 Wiki 状态，删除用完的模拟邀请。保留一份场景 ID 到主题 URL、分类和账号角色的对应表，邀请链接值留在本地站点。DC-09 与 DC-11 的中途条件可用运行时间线和阶段观察复核，最终页面检查由 WAATA 报告呈现。 [帖子动作系统测试](../testsites/discourse/spec/system/post_menu_spec.rb) · [书签系统测试](../testsites/discourse/spec/system/bookmarks_spec.rb) · [用户偏好测试](../testsites/discourse/frontend/discourse/tests/acceptance/user-preferences-interface-test.js)
