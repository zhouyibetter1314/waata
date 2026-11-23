# 本地测试站点

三个上游项目以 Git 子模块管理，分别固定源代码版本。需要哪个站点时，可只检出对应路径。下面的命令检出全部三个站点。

```bash
git submodule update --init -- testsites/4gaboards testsites/admidio testsites/discourse
```

| 站点 | 路径 | 固定版本 | 部署文档 |
| --- | --- | --- | --- |
| 4gaBoards | `testsites/4gaboards` | `v3.2.16` · `b76dcc95` | [4gaBoards 部署说明](https://github.com/RARgames/4gaBoards/blob/b76dcc95fb693ca1cf7bf7ee9380f0c755d2d31c/README.md#deploy) |
| Admidio | `testsites/admidio` | `v5.0.2` · `4484b503` | [Admidio 安装说明](https://github.com/Admidio/admidio/blob/4484b50396e290900bc25bf953a4eb5040c7646b/README.md#installation) |
| Discourse | `testsites/discourse` | `v2025.12.0-latest` · `3e7317b3` | [Discourse 本地开发容器说明](https://github.com/discourse/discourse/blob/3e7317b3344cca6c6510a32cc4c5c0f540132ad9/bin/docker/README.md) |

检出后按表中的固定版本文档部署需要的站点，为每个站点选择独立的 Compose 项目和数据卷。记录访问 origin 和测试账号初始化步骤，便于同版本复跑。接入 WAATA 时在目标策略中声明 origin、主体、动作与凭据引用。 [后端运行设置](../apps/api/README.md#运行设置) · [本地依赖](../infra/README.md) · [4gaBoards 契约示例](../contracts/examples/README.md)

[`testsites/demo-app/`](demo-app/) 提供独立运行的本地登录夹具。基准版和仅改变错误提示的回归版可使用同一套测试数据与预期。启动方式见 [后端启动与联调](../apps/api/README.md#本地登录夹具)，验收规则见 [MVP 与验收](../docs/04-acceptance.md#测试夹具)。
