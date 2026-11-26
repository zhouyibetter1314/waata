# Agent Guidelines for WAATA

## Git and pull requests

- Follow the workflow in [CONTRIBUTING.md](CONTRIBUTING.md). Work on a feature branch. Before opening or updating a GitHub pull request, fetch the current `main` from the canonical repository, merge it into the feature branch, resolve conflicts locally, and rerun checks before pushing. Use the canonical upstream remote when `origin` points to a fork.
- Use Conventional Commits. Keep changes for each commit focused and preserve unrelated work in the working tree.
- Report what was verified and list any checks that could not run in the pull request.

## Architecture and contracts

- Read the [requirements](docs/02-requirements.md), [acceptance criteria](docs/04-acceptance.md), and relevant [contracts](contracts/README.md) before changing behavior. Use the [architecture](docs/03-architecture.md) and ADRs when a change crosses module boundaries.
- Keep the dependency direction Vue → FastAPI → the public WAATA Python API. Keep `packages/waata` independent of the web framework, task queue, and platform database. Keep the general agent runtime independent of test orchestration and concrete adapters.
- Manage PostgreSQL schema changes with versioned SQL in [migrations/](migrations/README.md). Add a new migration for each schema change, preserve applied files, and verify upgrades with representative data.
- Reference the relevant requirement IDs in behavior changes. Coordinate public contract changes with affected maintainers, and update the source models, examples, and checks together. Preserve the distinction between run status and test verdict.

## Checks and test data

- Use the root uv workspace and the hooks documented in [CONTRIBUTING.md](CONTRIBUTING.md). Run the relevant tests and `uv run --locked pre-commit run --all-files`. Check the lockfile with `uv lock --check` when changing Python dependencies.
- Use the formatter versions pinned in [.pre-commit-config.yaml](.pre-commit-config.yaml), with Python rules in [pyproject.toml](pyproject.toml) and frontend rules in [apps/web/.prettierrc.json](apps/web/.prettierrc.json).
- Test on authorized local fixtures or explicitly approved test environments with dedicated accounts. Enforce target and action restrictions at the browser execution boundary, and make test setup repeatable.
- Keep test doubles and contract sample responses in test-only paths. Use the configured API, Worker, database, browser and model provider in the normal application entry points.
- Keep credentials out of source, prompts, logs, reports, and traces. Redact sensitive evidence and use fixture references or environment configuration for secrets. Keep generated artifacts and IDE metadata local.
- Treat the [test site submodules](testsites/README.md) as pinned upstream fixtures. Change their contents or revision pointers only when the task calls for it.
