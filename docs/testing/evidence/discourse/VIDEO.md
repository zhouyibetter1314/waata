# Discourse 测试与 Debug 视频

[播放 / 下载 MP4](discourse-platform-demo.mp4) · [本次 Run 与证据摘要](video-run-summary.json) · [独立会话截图](video-independent-topic.png)

录制日期：2026-11-25（北京时间）。时长约 2 分 02 秒，1600 × 1120、25 fps、H.264 MP4，无配音，带中文分段说明及 MP4 章节。网页主体按原速保留；片头、片尾为结果说明卡，前面的 12 秒 Debug 段来自另一条失败预跑，已明确标记，没有将两次运行当作同一次。

## 视频流程

| 时间 | 画面 |
| --- | --- |
| 00:00–00:04 | 场景与环境：DC-01 创建主题 |
| 00:04–00:16 | 失败预跑实录：Discourse 拦截短时间内重复正文 |
| 00:16–00:30 | 从真实 Vue 网页填写并提交新任务 |
| 00:30–01:10 | 真实模型登录、进入分类、创建主题并重开；实时浏览器画面 |
| 01:10–01:29 | 读取原始报告、放大 C5 截图和检查三项断言 |
| 01:29–01:49 | 独立新会话登录，再打开主题验证持久化 |
| 01:49–01:56 | 返回平台详情，确认正常完成 / 通过 |
| 01:56–02:02 | 结果与验证范围 |

## 成功运行

Run ID：`run_e8f269457abd4202b7f9227d7fe7733e`。平台时间为 22:58:14–22:58:51，37.11 秒；完整录制含表单填写、证据浏览、独立会话及等待，原片约 100 秒。模型 `deepseek-v4.1-flash`，19 次成功响应、222,761 Token，10 次动作工具调用。凭据通过服务端引用，实际登录计入 Run；独立复核登录不计入 Run 用量。

- C1 POST 返回 `202`；最终状态 `succeeded`、判定 `passed`，1 个用例、标题/正文/分类 3 项断言全部通过。
- 32 项 C5 证据（29 观察 + 3 截图）均通过真实 API 读取，HTTP 全部为 200；108 条 C4 事件持久化。
- PostgreSQL 中该 Run 有 1 份报告、32 项 artifact、1 条 `report.generated` 和唯一 `run.completed` 终态。
- 独立浏览器会话及 Discourse 数据库只读复核：同名主题恰好一条，标题、正文、`WAATA Lab` 分类与会员作者一致。

原始报告摘要及 SHA-256 见 `video-run-summary.json`。本视频的 **4 条平台 Run** 与此前 `run-index.json` 中的 **30 条独立 Python Run** 是不同数据集，未合并或覆盖历史统计。

## 预跑 Debug 与修正

| Run / 阶段 | 原始结果 | 发现及处理 |
| --- | --- | --- |
| 最初表单预检，无 Run ID | HTTP 422 | 目标正文含服务端凭据引用名，命中保密过滤；正文改为描述凭据集合，把引用保留在专用字段 |
| `run_891b939c737448fa923daee962bede45` | `errored` | Chromium 对远程 CDP Host 校验拒绝；只在本机调试连接明确设置回环 Host |
| `run_44156f31b4cf4f91b29702f4b9ab3fc8` | `succeeded / failed` | 业务创建成功，但模型把中间分类 URL 加入最终检查；核对页面 DOM，将预期明确为标题、正文和分类三项 |
| `run_b9b1818ed14745f4a439084bd1064bb3` | `succeeded / inconclusive` | Discourse 的 `unique_posts_mins=5` 拦截重复正文，目标主题未创建；视频 Debug 段来自此 Run |
| `run_e8f269457abd4202b7f9227d7fe7733e` | `succeeded / passed` | 新主题完整重跑及独立复核通过 |

为重复录制手册固定正文，仅在授权本地夹具临时设 `unique_posts_mins=0` 并清理专用会员未提交草稿；录制后已恢复为 `5`。没有通过脚本代替模型创建主题，也未把失败 Run 改成通过。

## 环境与边界

本次为真实 Vue → FastAPI → PostgreSQL 17 → Worker → 公共 TestEngine / PlaywrightAdapter 流程。PostgreSQL 位于独立 `waata-video-pg` 容器，未在 Windows 安装数据库。API 使用现有真实路由与 POSIX 文件证据存储；Worker 位于 `waata-video-runtime` 容器，任务专用入口通过现有公开接口连接隔离的 Windows Chromium，采用真实模型，无测试替身或动作回放。

Worker 的模型窗口、浏览器等待及页面观察上限由本地入口装配；不是零配置的生产 Worker 启动。平台浏览器为无头 Chromium，通过受控实时截图流显示在网页；录制的是浏览器视口，不是整个 Windows 桌面。登录字段和邀请短码区域遮罩；API Key、密码、数据库 DSN、网关令牌没有进入交付视频。

本片验证了单场提交、C4 实时进度、C1 报告、C5 证据读取和数据库落盘；未覆盖取消、重启恢复、多身份权限及全部 AC-05/06。关联 FR-001–FR-005、FR-007 和 AC-01/02/03/04 的本场行为，不代表完整平台验收。

完整原片、失败预跑原片、事件、报告、提供方用量、复核及录制/导出脚本留在忽略目录 `.local/discourse/video/`。运行脚本是 `record-demo.py`，导出脚本是 `encode-video.py`；再次录制需先启动本地 API/Worker、浏览器连接和网关，并准备新的唯一标题，不能把已有成功数据冒充新执行。

视频参考只用于流程和展示方式；未执行参考视频后半段的 Git 操作，未 commit、push、合并 main 或创建 PR。
