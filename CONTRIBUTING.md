# WAATA 团队协作规约

模块按 [v0.1 契约](contracts/README.md)联调。分支保护和 CI 的规划见 [Q-010](docs/05-open-questions.md#q-010-工程工具与流程)。

## 并行工作流

| 工作流 | 责任范围 | 独立验证方式 | 关联契约 |
| --- | --- | --- | --- |
| 前端 | Vue 页面、API 客户端、运行时间线和报告 | 用 Mock API 验证提交任务、状态更新与报告展示 | C1、C4、C5 |
| 后端 | FastAPI、Worker、任务生命周期、PostgreSQL、证据存储和 SSE | 用 Mock TestEngine 验证调度、状态查询和报告查询，用 PostgreSQL 17 验证事务与重放 | C1、C2、C4、C5、C6 |
| WAATA 核心 | 模型接口、Agent Runtime、测试编排与判定 | 用 Fake LLM 和 Fake BrowserAdapter 验证公共调用流程 | C2、C3、C4 |
| 浏览器与可观测性 | Playwright、会话隔离、证据采集和 Langfuse | 用预设的功能测试动作验证受控页面操作与追踪 | C3、C4、C5 |
| 契约与 QA | 公共契约、Mock、契约测试和端到端验收 | 对照实现验证契约，跑通受控登录场景 | C1～C6 |

按团队人数合并工作流。任务记录负责人、需求编号、涉及的契约和验收条件。优先联调 HTTP、公共 Python API 和事件三条主链路，使用 [4gaBoards 示例](contracts/examples/README.md)与替身并行开发。

## 本地提交检查

### 新成员初始化

准备 Git 和 uv。每次新克隆后，在项目根目录运行以下命令，安装并初始化 `pre-commit` 和 `commit-msg` 两个 Git 钩子。

```bash
uv sync --locked
uv run --locked pre-commit install --install-hooks
```

`uv sync --locked` 按锁文件安装开发工具 `pre-commit`。`install --install-hooks` 在本机检查各钩子的缓存，下载并初始化缺少的工具版本。首次初始化需要联网。更新钩子版本后，运行 `uv run --locked pre-commit install-hooks` 可提前初始化新版本。 [pre-commit 安装说明](https://pre-commit.com/#pre-commit-install-hooks)

个人安装的 `ruff`、`prettier` 或 `.ruff/` 工具目录可用于个人工作流。项目钩子使用自己的工具环境和仓库规则，安装状态由钩子缓存管理，无需设置 `RUFF_INSTALLED` 之类的变量。需要自定义缓存位置时可设置 `PRE_COMMIT_HOME`。

### 格式化和验证

| 工具 | 适用文件 | 共享规则 |
| --- | --- | --- |
| Ruff 0.14.14 | Python，检查代码、整理导入并格式化 | [根目录 pyproject.toml](pyproject.toml) |
| Prettier 3.8.1 | `apps/web/` 下的 Vue、JS、TS、CSS、SCSS、Less、HTML 和 JSON，包含 JSX 与 TSX | [前端格式配置](apps/web/.prettierrc.json) |

工具版本以 [钩子配置](.pre-commit-config.yaml)为准。编辑器中使用同一份规则。提交时只检查已暂存文件，同时验证配置文件语法、冲突标记和私钥。格式化写回后，先审阅改动，再重新暂存并提交。

```bash
# 检查仓库中的受版本控制文件
uv run --locked pre-commit run --all-files

# 单独运行格式化钩子
uv run --locked pre-commit run ruff-format --all-files
uv run --locked pre-commit run prettier-web --all-files
```

`commit-msg` 校验 Conventional Commits 标题，格式为 `type(scope): description`，`scope` 可省略。例如 `docs(contracts): clarify event replay` 或 `fix: preserve run evidence on cancellation`。常用类型见 [钩子配置](.pre-commit-config.yaml)。Git 自动生成的合并提交标题可用于同步主分支。

## 提交 PR 前同步主分支

创建或更新 GitHub PR 前，必须获取项目主仓库最新的 `main` 并合入本地功能分支。开始同步前，确认已切到功能分支且工作区干净。

```bash
git fetch origin main && git merge FETCH_HEAD
```

如果 `origin` 指向个人 fork，使用指向项目主仓库的远端，例如将第一条命令改为 `git fetch upstream main`。出现冲突时，在本地解决并暂存冲突文件，通过 `git merge --continue` 完成合并。重新运行提交检查和受影响的测试，确认同步与验证通过后再推送功能分支并创建或更新 GitHub PR。

## 评审要求

1. 在任务中链接需求编号或 ADR，写明行为变化和验证条件。从 `main` 建立工作分支，通过 PR 评审。
2. 变更公共契约时同步更新来源定义、示例与相关测试，并请受影响模块共同评审。兼容性变更说明旧调用方的影响。破坏性变更同时说明迁移方式。
3. PR 说明需求、实现范围和实际验证结果。重要架构变更记录 ADR，需求变更同步更新 SRS 和验收条目。

完成条件是实现满足关联验收条件，适用的测试通过，受影响的契约和文档已更新，PR 完成评审并合并。
