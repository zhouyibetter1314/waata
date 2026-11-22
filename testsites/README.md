# 本地测试站点

三个上游项目以 Git 子模块管理，固定到旧项目 WebAppAutoTestAgent 使用的版本。在项目根目录检出站点源代码。

```bash
git submodule update --init -- testsites/4gaboards testsites/admidio testsites/discourse
```

| 站点 | 路径 | 固定版本 | 部署文档 |
| --- | --- | --- | --- |
| 4gaBoards | `testsites/4gaboards` | `v3.2.16` · `b76dcc95` | [4gaBoards 部署说明](https://github.com/RARgames/4gaBoards/blob/b76dcc95fb693ca1cf7bf7ee9380f0c755d2d31c/README.md#deploy) |
| Admidio | `testsites/admidio` | `v5.0.2` · `4484b503` | [Admidio 安装说明](https://github.com/Admidio/admidio/blob/4484b50396e290900bc25bf953a4eb5040c7646b/README.md#installation) |
| Discourse | `testsites/discourse` | `v2025.12.0-latest` · `3e7317b3` | [Discourse 本地开发容器说明](https://github.com/discourse/discourse/blob/3e7317b3344cca6c6510a32cc4c5c0f540132ad9/bin/docker/README.md) |

站点运行时和测试数据由各自的本地环境管理。配置目标时使用隔离的实例、专用测试账号和显式授权的地址。4gaBoards 的输入与结果见 [端到端契约示例](../contracts/examples/README.md)。

`testsites/demo-app/` 预留给团队自建的登录验收夹具。基准和回归版本的要求见 [MVP 与验收](../docs/04-acceptance.md#测试夹具)。
