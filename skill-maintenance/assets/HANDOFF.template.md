# 轮次汇报：{{ROUND_ID}}

> 填写说明：维护轮收轮时必写（委托子 agent 时由子 agent 本人写，不得只发聊天消息）。主 agent/owner **以本文件 + check 输出验收，不凭消息**：本文件缺失或章节不全 = 轮次未完成。8 个节标题不得省略；每节内容按轮次规模裁剪，无内容写"无"。

## 1. 执行方式

- 执行者：子 agent（名称：{{EXECUTOR}}） | 当前 AI 自执行（用户选择：{{CHOICE}}）
- 目标技能：{{TARGET_SKILL}}
- 轮次：{{ROUND_ID}}
- 轮次类型：普通轮 | 插队轮（提案ID：{{PROPOSAL_ID}}）

## 2. 结果

- 轮前 manifest：manifest:{{MANIFEST_BEFORE}}
- 轮后 manifest：manifest:{{MANIFEST_AFTER}}
- 裁决分布：采纳 {{ACCEPT}} / 改造 {{REFORM}} / 拒绝 {{REJECT}} / 挂起-待人工批准 {{SUSPEND}}
- 归档数：{{ARCHIVED}}
- SKILL.md 行数变化：{{LINES_BEFORE}} → {{LINES_AFTER}}
- 其他文件变化：<文件 + 行数/内容摘要；无则写"无">

## 3. 验证

- `<skill-maintenance>/scripts/check_skill.py --skill-dir <目标> --rebuild-map`：<输出与退出码>
- `<skill-maintenance>/scripts/check_skill.py --skill-dir <目标>`：<输出与退出码>
- pytest（如适用）：<命令 + 结果>
- 回归（evals 存在时）：<pass rate 改前 → 改后 + 失败项>

## 4. 产物

| 产物 | 路径 |
|---|---|
| 轮报告 | rounds/<轮次ID>/REPORT.md |
| 遗留问题单快照 | rounds/<轮次ID>/LEFTOVERS.md |
| 轮次汇报（本文件） | rounds/<轮次ID>/HANDOFF.md |
| 修改前快照 | rounds/<轮次ID>/snapshot/ |
| 根遗留问题单 | LEFTOVERS.md（本轮最新全量快照） |
| 提案索引 | proposals/open/INDEX.md、proposals/archive/INDEX.md |

## 5. 遗留

- 遗留 ID 列表：<L-001, L-002 | 无（根 LEFTOVERS.md 与 rounds/<轮次ID>/LEFTOVERS.md 均已写"无遗留"快照）>
- 本轮新增：<ID + 一句话 | 无>
- 本轮关闭：<ID + 关闭轮次/依据 | 无>

## 6. 回滚

- 修改前快照：rounds/<轮次ID>/snapshot/
- 备份：<路径 | 无>
- 回滚方式：<从 snapshot 恢复哪些文件、如何还原账本/根 LEFTOVERS.md；无快照不得回滚，交 owner>

## 7. 副本同步

| 副本 | 状态 | 说明 |
|---|---|---|
| 开发版（dev repo / staging） | 已同步 / 待同步 / 不适用 | <manifest 或原因> |
| 服役版（.claude） | 已同步 / 待同步 / 不适用 | <manifest 或原因> |
| 公布版（发布仓库/远端） | 已同步 / 待同步 / 不适用 | <manifest 或原因> |
| DSH 镜像（.agents） | 已同步 / 待同步 / 不适用 | <manifest 或原因> |

## 8. 结论与下一步

- 结论：PASS | FAIL（FAIL 必须写明卡在哪一步、缺什么）
- 下一步：<剩余事项/建议的下一轮触发条件；无则写"无">
