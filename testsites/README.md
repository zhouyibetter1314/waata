# 本地测试站点

三个上游站点以 Git 子模块固定版本。可在仓库根目录用以下脚本启动需要的站点，脚本会检查或检出相应版本。每个站点有独立的本地数据。

| 站点 | 固定版本 | 本机地址 | 启动 |
| --- | --- | --- | --- |
| [4gaBoards](../examples/README.md#4gaboards-组员-a) | `v3.2.16` · `b76dcc95` | `http://127.0.0.1:3000` | `bash scripts/4gaboards.sh start` |
| [Admidio](../examples/README.md#admidio-组员-b) | `v5.0.2` · `4484b503` | `http://127.0.0.1:8081` | `bash scripts/admidio.sh start` |
| [Discourse](../examples/README.md#discourse-组员-c) | `v2025.12.0-latest` · `3e7317b3` | `http://127.0.0.1:4200` | 首次 `bash scripts/discourse.sh init`，随后 `bash scripts/discourse.sh start` |

脚本支持 `status`、`logs` 和 `stop`。只检出源码时运行 `git submodule update --init -- testsites/<站点>`。接入这些站点或已有的授权环境时，为实际 origin、账号引用及动作配置策略。[目标配置](../apps/api/README.md#配置一个你有权限测试的站点)
