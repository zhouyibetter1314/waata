# WAATA × Discourse 测试成果汇总

测试日期：2026-11-25（北京时间）。WAATA 基线 `fd800f149bda1f62056eef5adbe0c5115808646e`，Discourse 固定提交 `3e7317b3344cca6c6510a32cc4c5c0f540132ad9`。交付范围与 #11 的 4gaBoards 测试相同：真实 Agent 业务运行、独立复核、复现脚本、联调报告与脱敏证据。

图片更新（2026-11-26）：9 张带粉色遮罩的旧图已删除，重截 7 张无人工遮挡的当前状态图。下表 DC-04/08/11 的链接指向本次复核图，原 Run 判定和用量不变；历史中途状态以原报告与结构化证据为准。详见[图片更新及来源](evidence/discourse/README.md#2026-11-26-无遮挡重截)。

## 最新场景结论

**DC-01–DC-11 的业务结果均有符合预期的复核证据。** 11 条代表 Run 中 10 条原判定为 `passed`；DC-08 原判定为 `failed`，只读独立复核确认是假阴性，不覆盖历史。不是同一轮 11/11 全部自动通过，也不是平台端到端验收通过。

本次恢复测试新增 6 条 Run：DC-06、DC-11 首次续测通过；DC-07、DC-10 各保留一次 `inconclusive`，再在独立新夹具完整重跑为 `passed`。没有用脚本替 Agent 保存场景业务结果，也没有离线回放代替真实模型执行。

代表 Run 使用预登录夹具；耗时和动作不含登录准备及独立复核。DC-01/03/05 模型为 `deepseek-v4.1-flash-1017`，其余为 `deepseek-v4.1-flash`。动作数是包含定位失败的动作工具调用上界。

| 场景 | 代表 Run ID | Agent 原判定 | 秒 / Token / 动作调用 | 独立复核与结论 | 截图 |
| --- | --- | --- | --- | --- | --- |
| DC-01 创建主题 | `dc01-agent-a764cc042c` | `passed` | 27.07 / 138,022 / 5 | 精确标题、正文、分类；数据库同名主题一条。 | [证据](evidence/discourse/DC01-topic.png) |
| DC-02 回复主题 | `dc02-agent-1b99b5923e` | `passed` | 12.59 / 57,270 / 4 | 精确回复、会员作者和 Member Fixture 显示名。 | [证据](evidence/discourse/DC02-member-name.png) |
| DC-03 点赞持久化 | `dc03-agent-86598432c3` | `passed` | 19.08 / 56,637 / 3 | 重开后 Undo like 可用；数据库点赞关系存在。 | [证据](evidence/discourse/DC03-liked.png) |
| DC-04 保存字号 | `dc04-agent-6b4588eb9f` | `passed` | 33.05 / 97,116 / 6 | 新会话 Larger、页面字体类和数据库 larger。 | [证据](evidence/discourse/DC04-larger-clean.png) |
| DC-05 编辑会员回复 | `dc05-agent-15ea0da561` | `passed` | 26.45 / 68,815 / 8 | 原 post 2 更新，新正文持久化，旧句消失。 | [证据](evidence/discourse/DC05-edited-reply.png) |
| DC-06 书签与活动列表 | `dc06-agent-79b4a5a95d` | `passed` | 17.27 / 84,204 / 4 | Agent 先留存列表再点击书签进入同一主题；新会话能跟随，数据库无提醒。 | [证据](evidence/discourse/DC06-bookmark-followed.png) |
| DC-07 转换 Wiki | `dc07-agent-ddf6fe706f` | `passed` | 37.29 / 151,734 / 10 | 新夹具从普通帖转为 Wiki，原正文保留；重开菜单为 Remove Wiki。 | [证据](evidence/discourse/DC07-wiki.png) |
| DC-08 创建邀请 | `dc08-agent-bc292a3596` | `failed` | 35.76 / 144,223 / 8 | 独立复核恰好一条、0/1、无邮箱、未来过期。原宽泛 tr 检查误判，保留 failed。 | [证据](evidence/discourse/DC08-pending-clean.png) |
| DC-09 会员编辑他人 Wiki | `dc09-agent-2656474d6b` | `passed` | 32.56 / 149,007 / 8 | 普通管理员帖无 Edit 阶段证据；另一 Wiki 新正文持久化，Wiki 保留。 | [证据](evidence/discourse/DC09-wiki-edited.png) |
| DC-10 编辑并取消 Wiki | `dc10-agent-e08b1e1cff` | `passed` | 32.25 / 197,545 / 11 | 新 Wiki 保存新正文，再取消 Wiki，Agent 重开；新会话无 Wiki 标记，菜单为 Make Wiki。 | [证据](evidence/discourse/DC10-ordinary.png) |
| DC-11 修改/删除指定邀请 | `dc11-agent-f5c849595b` | `passed` | 23.66 / 138,351 / 7 | 删除前已记录 0/1，目标随后删除；重开保留同 ID 的 0/2 对照邀请。 | [证据](evidence/discourse/DC11-removed-clean.png) |

## 续测配置与统计

20:07 最小调用确认新配置 HTTP 200。20:12–20:19 对余下四项真实执行；最新两条 Wiki Run 保持菜单打开以供最终检查。默认上限为 35 动作、27 步、30 次模型请求、180,000 Token、300 秒；最终 DC-07/10 显式放宽到 260,000 Token，实际分别 151,734 / 197,545。其余预算不变，完整工具集保留，观察上限从 12,000 增至 18,000 字符。所有配置仅在测试脚本，不修改核心运行逻辑或固定子模块。

累计 **30 条 Run**：23 `succeeded`（12 `passed`、9 `failed`、2 `inconclusive`）、7 `errored`。全部历史记录纳入统计，包括模型权限/额度错误和重跑，不只挑选成功结果。

- 290 次已捕获成功模型响应、2,914,135 Token；本次新增 72 次、836,709 Token。不含连接探测及未返回用量的 HTTP 错误，不等同账单。
- 179 次动作工具调用、28 次失败，单 Run 最多 18 次，低于课程 35 次上限。最终 DC-10 的 11 次动作在 18 次手册建议内；未计登录，不能作为完整登录预算结论。
- 引擎登记 382 项证据：355 结构化观察、27 截图。独立/阶段截图另计；未采集 Playwright Trace 或 Langfuse。
- Run 耗时之和 945.66 秒；部分并行，不是墙钟总耗时。
- SQLite 中 30 条 Run 与原报告 JSON/Run ID 一致，索引保留原报告 SHA-256。额外只读复核保存在独立文件及 `verifications` 表。

本地完整数据为 `.local/discourse/runs/`、`.local/discourse/qa.sqlite` 和 `.local/discourse/summary/discourse-qa-20261125-round3.zip`；提交目录含截图、30 条指标索引、DC-11 中途结构化观察与续测数据库前后状态摘录。凭据、邀请链接和完整模型消息不提交。

## 验证与限制

- 契约测试 12 项、Python 包测试 32 项（16 项真实 Chromium 集成 + 16 项单元测试）及全仓库 pre-commit 通过；命令和数据一致性验证见[联调记录](discourse-integration.md#本次检查与交付)。
- Windows API 测试发现基线 `FileArtifactStore` 直接导入 Unix `fcntl`：2 个模块导入错误，5 项 Worker 测试通过，6 项 PostgreSQL 测试跳过。未修复或模拟该平台模块，不声称 API 全套通过。
- 本机未安装 Windows PostgreSQL。仅使用 Discourse 容器自身数据库及本地 SQLite QA 索引；FastAPI/Worker 实际服务、Vue、SSE、取消、队列及平台 PostgreSQL 未验收，本次结果覆盖 FR-001–FR-005、AC-02/03/04/07 的部分独立调用能力。
- 最终 DC-07 仍有 3 次定位失败，早期菜单观察截断、重复观察和 schema 参数问题均有历史记录。DC-08 误判尚无重新创建邀请且原判定通过的 Run；定位提示和预算调整后的样本不足以推断跨模型稳定成功率。

[详细联调过程、历史与复现](discourse-integration.md) · [截图与指标](evidence/discourse/README.md)
