# Discourse 测试证据索引

新增[网页测试与 Debug 视频](VIDEO.md)：独立的真实平台录制，含失败预跑、成功执行、报告截图和新会话复核；与下方历史 30 条独立 Run 分开登记。

日期：2026-11-25。截图来自各轮真实执行、只读阶段取证及独立会话复核，经查看后纳入。它们包含成功、失败和阶段证据，不能统一解释为通过。

## 2026-11-26 无遮挡重截

已删除目录内 9 张带粉色遮罩的旧图，以以下 7 张当前状态截图替代相关复核展示。所有新图直接从专用账号的新会话截图：不传截图 mask、不修改页面 DOM、不涂抹或遮盖，业务字段和兑换计数正常显示。邀请页面只显示站点自身缩短的短码，未打开包含完整邀请 URL 的编辑弹窗。

这些图片于 **2026-11-26** 重新采集，是旧 Run 相关夹具的当前状态复核，不是旧 Run 执行当时的截图。未调用模型、未保存字号修改、未创建或修改邀请、未重做业务动作。采集时间、URL、定位核查、SHA-256 和被替换文件记录见 [clean-capture-manifest.json](clean-capture-manifest.json)。

| 新截图 | 关联 Run / tag | 本次重新读取的状态 |
| --- | --- | --- |
| [DC04-larger-clean.png](DC04-larger-clean.png) | `dc04-agent-6b4588eb9f` | Interface 页面保存的 Text Size 为 Larger；复选框全部可见 |
| [DC06-first-bookmarks-clean.png](DC06-first-bookmarks-clean.png) | `dc06-agent-860315d135` / `11250730-97ca` | 当前书签列表中有精确目标；不冒充历史跟随前阶段图 |
| [DC06-bookmarks-clean.png](DC06-bookmarks-clean.png) | `dc06-agent-79b4a5a95d` / `11251212-7b87` | 搜索精确标题后只有对应书签 |
| [DC06-round2-bookmarks-clean.png](DC06-round2-bookmarks-clean.png) | `dc06-agent-062fe3873b` / `11250946-e107` | 精确目标搜索无结果，搜索框与提示完整可见 |
| [DC08-pending-clean.png](DC08-pending-clean.png) | `dc08-agent-bc292a3596` / `11250946-e107` | Pending 中 practice 目标仍在，显示 0/1 和到期时间 |
| [DC11-removed-clean.png](DC11-removed-clean.png) | `dc11-agent-f5c849595b` / `11251212-7b87` | 完整 Pending 列表没有 scoped 目标，keep 对照仍为 0/2 |
| [DC11-scoped-remains-clean.png](DC11-scoped-remains-clean.png) | `dc11-agent-a69f38e044` / `11250946-e107` | 旧失败夹具的 scoped 和 keep 仍各为 0/2，未覆盖失败事实 |

旧 Normal 字号图及 DC-11 删除前 0/1 阶段图无法通过只读方式重现，已从图片目录移除，没有回改业务状态来伪造历史图。历史失败判定仍在原报告；删除前的 0/1 事实保留在 [DC11-updated-stage.json](DC11-updated-stage.json)。其余无粉色色块的历史图片保留如下。

## 第三轮证据（历史原图）

累计 30 条 Run；本次新增 6 条真实执行。DC-06、DC-11 使用 tag `11251212-7b87`，最后 DC-07、DC-10 使用新 tag `11251217-7e0b`。不混用不同 tag 的结果。

| 文件 | Run ID | 来源与含义 |
| --- | --- | --- |
| [DC06-follow-stage.png](DC06-follow-stage.png) | `dc06-agent-79b4a5a95d` | Agent 会话点击精确书签链接后到达目标主题；原报告 stage 1 保存此前列表观察，stage 2 保存跟随结果 |
| [DC06-bookmark-followed.png](DC06-bookmark-followed.png) | `dc06-agent-79b4a5a95d` | 独立新会话：从书签列表点击进入目标，标题/书签状态正确 |
| [DC07-wiki.png](DC07-wiki.png) | `dc07-agent-ddf6fe706f` | 最终 passed Run 的独立新会话：原正文、Wiki 指示器和 Remove Wiki 菜单 |
| [DC10-ordinary.png](DC10-ordinary.png) | `dc10-agent-e08b1e1cff` | 最终 passed Run 的独立新会话：新正文、无 Wiki 指示器，菜单为 Make Wiki |
| [DC11-updated-stage.json](DC11-updated-stage.json) | `dc11-agent-f5c849595b` | 删除前 0/1 行的结构化观察摘录，去掉邀请短码，包含原报告 SHA-256 |
| [DC07-wiki-recheck.png](DC07-wiki-recheck.png) | `dc07-agent-5d6532e802` | 中间 inconclusive Run 的追加只读复核，证实业务保存成功；不是最终 passed Run 的截图 |
| [DC10-ordinary-recheck.png](DC10-ordinary-recheck.png) | `dc10-agent-c56275ffaa` | 中间 inconclusive Run 的追加只读复核，原 Agent 未完成重开/收尾；不是最后完整 Run |
| [round3-persisted-state.json](round3-persisted-state.json) | 上述两组 tag | 只读数据库前后状态摘录：书签由无到有且无提醒，普通/Wiki 状态转换，邀请目标移除及对照 ID/0/2 保留；附原快照哈希 |

DC-07/10 两条中间 Run 的首次独立菜单检查因未等待出现而误报；原报告/布尔值保留，追加结果在独立 verification 文件及 `rechecked_passed`。最终新 Run 原判定和首次独立复核均通过。JSON 摘录与截图不替代引擎 C5 证据；完整原件仍在本机运行目录。

## 第二轮证据（历史）

第二轮结束时累计 24 条 Run，以下为该轮截图和独立复核。第一轮图保留在下一表，不能将不同 tag 或不同 Run 的证据混用。

| 文件 | Run ID | 来源与含义 |
| --- | --- | --- |
| [DC02-member-name.png](DC02-member-name.png) | `dc02-agent-1b99b5923e` | 独立新会话：精确回复及 Member Fixture 显示名 |
| [DC07-round2-ordinary.png](DC07-round2-ordinary.png) | `dc07-agent-3bf4f566ed` | 独立新会话：最终仍是普通帖 |
| [DC09-wiki-edited.png](DC09-wiki-edited.png) | `dc09-agent-2656474d6b` | 独立新会话：新正文及 Wiki 标记 |
| [DC09-round2-control.png](DC09-round2-control.png) | `dc09-agent-2656474d6b` | 修改前 Agent 会话展开普通帖动作，无 Edit 的阶段证据 |
| [DC10-still-wiki.png](DC10-still-wiki.png) | `dc10-agent-f45e16d354` | 独立新会话：新正文已保存，但 Wiki 未取消，Run 因额度中断 |

## 第一轮历史证据

| 文件 | Run ID | 来源及含义 |
| --- | --- | --- |
| [DC01-topic.png](DC01-topic.png) | `dc01-agent-a764cc042c` | 独立新会话：精确标题、正文、分类已保存 |
| [DC02-author-mismatch.png](DC02-author-mismatch.png) | `dc02-agent-5c6ed8270d` | 独立新会话：回复保存，但作者仅显示用户名，显示名条件不满足 |
| [DC03-liked.png](DC03-liked.png) | `dc03-agent-86598432c3` | 独立新会话：已点赞状态；确定性检查确认 Undo like |
| [DC05-edited-reply.png](DC05-edited-reply.png) | `dc05-agent-15ea0da561` | 独立新会话：原会员回复已变为新句 |
| [DC07-ordinary-post.png](DC07-ordinary-post.png) | `dc07-agent-b89377a3da` | 独立新会话：最终为普通帖，Admin 菜单提供 Make Wiki，失败证据 |
| [DC09-control-stage.png](DC09-control-stage.png) | `dc09-agent-b1e9543ffe` | Agent 会话中只读截取：普通管理员帖展开动作后会员没有 Edit；未完成 Wiki 修改 |
| [member-session-preflight.png](member-session-preflight.png) | 无 Run | 早期站点预检，只证明测试会员已登录并可读主题 |

目录内 PNG 已检查，粉色遮罩图片已移除。新图只包含专用夹具账号和业务文本，不含密码、API Key 或完整可兑换邀请 URL。全尺寸原件、引擎自动截图与观察证据留在 `.local/discourse/runs/<run_id>/`，每条报告列出引擎 artifact ID。

## 可检索指标

- [run-index.json](run-index.json)：30 条 Run 的原始状态、原判定、用量、动作计数、证据数量、原报告 SHA-256 和本机相对路径；同时记录追加只读复核。
- [run-index.csv](run-index.csv)：相同指标的表格形式，便于组会比较和筛选。
- 原始 `independent_reported_passed` 字段保留原值。DC-06 的 false 混入页面未就绪问题，DC-02 的 false 是显示名条件不满足；应按[联调记录](../../discourse-integration.md)解释。

`fixture_tag` 与 `harness_version` 标记不同轮次配置。`rechecked_passed` 为后续独立复核结果，不覆盖原判定；`screenshots` 统计全部引擎登记截图，含 Agent 主动截图。旧版指标曾将该数称为 automatic_screenshots，现已修正名称。

JSON/CSV 不包含模型请求文本、密钥、账号登录值或邀请令牌。原始报告、SQLite 和数据库核查 JSON 仅保存在本机，不随提交上传。

[成果汇总](../../discourse-summary.md) · [联调记录与限制](../../discourse-integration.md)
