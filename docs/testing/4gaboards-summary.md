# WAATA × 4gaBoards 3.2.16 成果汇总

范围：仓库提供的 B01–B05 五个调试场景，4gaBoards 固定提交 `b76dcc95fb693ca1cf7bf7ee9380f0c755d2d31c`。

## 真实执行结果

五个业务变更都由真实 Agent 完成，并在独立会话中核对了保存结果。原始真测 3 个 `passed`；B01 的误判、B05 的证据不足另用离线引擎验证，不覆盖历史记录。

| 场景 | 原始 Run ID | 模型版本 | 原判定 | 耗时 / Token / 浏览器操作 | 独立复核与判定修复 | 代表截图 |
| --- | --- | --- | --- | --- | --- | --- |
| B01 创建项目 | `run_bc1b842faeaf479b94d21b5c7bc77821` | DeepSeek / 火山方舟；精确版本未留存 | `failed` | 97.58 秒 / 未记录 / 8 | 仪表盘和侧栏各一条，链接相同，重新打开后仍在。侧栏文本在子元素，修正选择器后 3 次离线回放通过。 | [B01 PNG](evidence/4gaboards/B01-project.png) |
| B02 项目改名 | `b02-agent-25dbd71dcd` | `deepseek-v4-pro-ga-260813` | `passed` | 26.29 秒 / 30,271 / 6 | 两处显示新名，旧名消失，仍指向原项目；修复了长侧栏中的编辑菜单定位与观察。 | [B02 PNG](evidence/4gaboards/B02-rename.png) |
| B03 Kanban 看板 | `b03-agent-2571c558d7` | `deepseek-v4-pro-ga-260813` | `passed` | 22.37 秒 / 23,636 / 6 | Agent 选择 Kanban 后提交；Open、Todo、In Progress、To Test、Done 各一条。早期 Empty 模板失败保留。 | [B03 PNG](evidence/4gaboards/B03-kanban.png) |
| B04 创建列表 | `b04-agent-102296c5e6` | DeepSeek / 火山方舟；精确版本未留存 | `passed` | 13.27 秒 / 20,989 / 4 | 独立重开同一看板，目标列表恰好一条。原 Agent 未自行截图，所附为独立复核截图。 | [B04 PNG](evidence/4gaboards/B04-list.png) |
| B05 指定列表建卡 | `b05-agent-d13f2554e9` | `deepseek-v4-pro-ga-260813` | `inconclusive` | 10.24 秒 / 10,796 / 4 | Agent 提交后卡片已保存；未打开详情。离线 Run `b05-agent-7e37dfec12` 对已有卡片验证 Inbox 计数及精确标题，结果 `passed`。Token 只计该执行 Run，不含此前规划。 | [B05 PNG](evidence/4gaboards/B05-card.png) |

所有代表性真实 Run 均低于 35 次浏览器操作。不同运行的模型、登录起点和证据流程不完全相同，耗时和用量仅作实测记录。

## WAATA 统一验收

[平台 Run `run_657e5fe551fe4e8fa53fc84dca7d38a4`](http://127.0.0.1:5173/runs/run_657e5fe551fe4e8fa53fc84dca7d38a4)：`succeeded / passed`，5/5 用例、19 条断言、5 张引擎自动截图，17.47 秒、23 次浏览器操作、0 次失败动作。这里是对历史真实 Agent 业务结果的有界面只读复核，不是新一轮自主创建。DeepSeek `deepseek-v4-pro-ga-260813` 只调用一次确定检查顺序，报告用量 78 Token；零付费复跑复用了该顺序。

- 网页的执行时间线包含“查看本步截图”，报告区仍支持预览和下载。五张平台 PNG 均经 C5 读取成功。
- [本机实时画面](http://127.0.0.1:5173/live/)已保留；运行期间确认可获取浏览器帧和 SSE 进度。回放结束后画面可能空闲，不是录像。

## 结论与剩余缺陷

- 对重复按钮使用区域或唯一授权选择器；模板保存前检查选中值。自动断言与独立复核用于发现假通过或假失败。
- 取证与模型决策分开：引擎截图不计浏览器业务操作；预登录、离线回放和人工复核不算真实 Agent 自主执行。
- B01、B05 尚没有修复后重新创建业务对象且原始报告为 `passed` 的真测记录。C1 网页报告尚未持久化提供方 Token，也没有逐条工具来源字段；原始 Playwright Trace 未开启。
- [详细联调记录](4gaboards-integration.md)保留失败历史、修复过程和复现命令；[精简证据索引](evidence/4gaboards/README.md)不包含原始模型消息或凭据。
