# 4gaBoards 代表性证据

五份 PNG 均来自本地专用测试夹具，输入已遮罩。这里只提交代表性截图和精简记录，不提交会话数据、完整模型响应或原始日志。Run 数字、性能和原始判定见[成果汇总](../../4gaboards-summary.md)。

| 文件 | 证据来源 | 可复核结果 |
| --- | --- | --- |
| [B01-project.png](B01-project.png) | 真实平台 Run `run_bc1b842faeaf479b94d21b5c7bc77821` 的终点截图 | 同名项目出现在仪表盘和侧栏；原报告失败，判定修复另有离线记录。 |
| [B02-rename.png](B02-rename.png) | 真测 `b02-agent-25dbd71dcd` 后独立核对 | 项目卡片为改后名称；侧栏全名和旧名缺失由结构化检查确认。 |
| [B03-kanban.png](B03-kanban.png) | 真测 `b03-agent-2571c558d7` 后宽视口独立核对 | 五个模板列表；仅打开已保存看板，没有新建。 |
| [B04-list.png](B04-list.png) | 真测 `b04-agent-102296c5e6` 后独立重开 | 同一个看板有且只有一条目标列表。 |
| [B05-card.png](B05-card.png) | 离线引擎 `b05-agent-7e37dfec12` 自动取证 | 已保存卡片同时显示在目标 Inbox 与详情区域；没有重新创建。 |

## 本机平台统一验收记录

Run：`run_657e5fe551fe4e8fa53fc84dca7d38a4`，`succeeded / passed`，17.47 秒，B01–B05 共 23 次操作。平台自动截图与以上代表性 PNG 是不同来源。

| 场景 | 操作 | 匹配断言 | 平台 C5 自动截图 ID |
| --- | ---: | ---: | --- |
| B01 | 4 | 3 | `art_b377ab57a7944f5583b5afb0a820fe04` |
| B02 | 4 | 5 | `art_2eff9c89a8b34b6c816eba4f3bb061ad` |
| B03 | 5 | 6 | `art_3a245c2178584b43af09b37db5d222a9` |
| B04 | 5 | 2 | `art_148634909f6946e9abb8a8a4e70403a1` |
| B05 | 5 | 3 | `art_4ccb178ebd3b41f0b2934c014482f494` |
