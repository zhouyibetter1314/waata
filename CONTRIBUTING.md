# WAATA 团队协作

从 `main` 创建功能分支。任务记录负责人、需求或 ADR 编号、关联契约和验收条件。跨模块变更由受影响的维护者共同评审，公共契约变更同步更新源模型、生成文件、样例和检查，并说明兼容性影响。架构决策记录到 ADR，功能变更同步更新需求与验收。[需求](docs/02-requirements.md) · [契约](contracts/README.md) · [验收](docs/04-acceptance.md)

## 本地开发与检查

从仓库根目录安装锁定的 Python 工作区和 Git 钩子。首次安装钩子需要联网。

```bash
uv sync --locked --all-packages
uv run --locked pre-commit install --install-hooks
```

按改动范围运行测试，提交前运行全部钩子。PostgreSQL 用例需要由 `WAATA_TEST_DATABASE_URL` 指定独立的 PostgreSQL 17 测试库，浏览器用例需要安装 Chromium。

```bash
uv run --locked python -m unittest discover -s tests/contract -v
uv run --locked python -m unittest discover -s apps/api/tests -v
uv run --locked --package waata --extra browser python -m unittest discover -s packages/waata/tests -v
uv run --locked pre-commit run --all-files
```

前端检查见 [Vue 验证命令](apps/web/README.md#开发检查)。修改 Python 依赖时运行 `uv lock --check`。Ruff 和 Prettier 版本以钩子配置为准，Python 和前端沿用仓库规则。钩子写回格式后，审阅改动并重新暂存。[钩子](.pre-commit-config.yaml) · [Python](pyproject.toml) · [前端](apps/web/.prettierrc.json)

运行验收使用授权测试站点和专用账号。记录项目修订、站点版本、模型、运行配置、Run ID 和实际判定。自动化测试将测试替身及样例留在测试路径，平台联调按真实启动流程验证。[开发启动](apps/api/README.md) · [验收](docs/04-acceptance.md)

## 数据库变更

新增版本化 SQL 并同步 C6。保留已应用的 SQL，记录空库初始化和带代表数据的旧库升级结果。[迁移规约](migrations/README.md) · [C6](contracts/database/c6-platform-persistence.md)

## 提交和评审

使用 Conventional Commits 格式 `type(scope): description`，可省略 `scope`。按逻辑变更分开提交，保留工作区中其他人的改动。

创建或更新 GitHub PR 前，在干净的功能分支同步主仓库最新的 `main`。主仓库远端名为 `origin` 时执行以下命令。使用 fork 时，将 `origin` 换成主仓库远端，例如 `upstream`。

```bash
git fetch origin main
git merge FETCH_HEAD
```

遇到冲突时在本地解决、暂存并执行 `git merge --continue`。重新运行检查和受影响的测试，再推送功能分支。PR 说明关联需求、实现范围、验证结果和未运行的检查。评审通过后合并。
