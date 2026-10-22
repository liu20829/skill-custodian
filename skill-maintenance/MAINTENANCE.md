skill_name: skill-maintenance
owner: owner
created: 2026-10-19
stage: governed
stage_history: 2026-10-19 governed by owner (dogfood Task 9)
charter_version: 0.2.11
round:
round_in_progress:
evals: yes
adopted: false

## 设计意图

1. **账本文件化，而不是维护者进程化**：智能体是无状态的，维护者的身份与记忆必须落在技能目录的持久化文件里（MAINTENANCE.md + rounds/）。账本不进运行时路径，工作者不必为维护付 token；维护者启动时强制全量加载。
2. **批处理，而不是逐条修补**：单条反馈立即改，只会把"路过的智能体各改一刀"换一种形式重演。攒一批再分诊，才能按根因合并成一条好规则，替代五个补丁。
3. **产物可核对，而不是相信行为**：提示词约束是软的。把约束设计成可机械核对的产物——技能地图 sha256、轮报告、变更日志、否决索引、快照——审计兜底才有对象，越权与腐化才能被发现。

## 不变量

- I1（唯一写入者）：治理期技能目录只有维护者写入。工作者只能向 proposals/open 追加提案；出生/收养由 init_ledger.py 执行；人/owner 的修改视为授权，但须补账本行并注明 approval_id。
- I2（裁决四词汇）：裁决只有 采纳 / 改造 / 拒绝 / 挂起-待人工批准，且必须覆盖本轮提案集全部提案；不得引入第五种裁决词。
- I3（三处同步）：边界变更必须同步 README（权威）→ description 与 SKILL.md 判断规则（派生）→ 变更日志（记录）。
- I4（审计兜底）：发现来源异常或未经流程的直接改动，先做技能地图 sha256 对账与来源分类，再决定保留（补录账本）或回滚（从 snapshot 恢复）；审计兜底先于常规维护。

## 规则锚点

| anchor | summary | status | last_round | void_round |
|---|---|---|---|---|

## 技能地图

| path | purpose | sha256 | lines | last_verified_round |
|---|---|---|---|---|
| assets/launch-template.md | asset template | 28dba58a537ead9bedbccda3f2851bd6f098e0c28c2d0fd957a30aafcce9d0df | 10 | init |
| assets/MAINTENANCE.template.md | asset template | 928344ce77adb7bc8b56cf5a01300c5282f99ef233514aeb10f6993798bd5c8a | 38 | init |
| assets/README.template.md | asset template | cfb1754bc33817520ab1db51c21b521d8bec74d5d5b131c3bac37fa003ef927a | 21 | init |
| assets/REPORT.template.md | asset template | 5f737c00d10d1bb3c9f9b270393e3bd28e1878b8e9b59aa3b5806c4fccc7b01d | 38 | init |
| assets/ROUND-REPORT.template.md | asset template | 8a808d3818e0420a69bc120b5d0d34c76b18d95e6a67cbe5ec39df87029366de | 56 | init |
| references/audit.md | reference | a07e7f056eeb889432597cd2b3e09679c459bed45b6498b738567c4ea5f7326a | 32 | init |
| references/verdict-rules.md | reference | a1181952b2a63d345d37e41b7df4bf9256ed91198daed59b581d784fbbd849c5 | 14 | init |
| scripts/check_skill.py | script | 7dd96608be523ae094429a900fd77e37bd9b25e1a00658267473c429c65446be | 287 | init |
| scripts/index_proposals.py | script | c0532fb8dea20e12109bc266e004ff0a05cb0bf96bf800eded33f5800e1e40db | 351 | init |
| scripts/init_ledger.py | script | fdbaaae444c47f871907a3b48d8d2a1b4b27e34aa0552aa5114df4f6fd5d5971 | 221 | init |
| SKILL.md | skill instructions | b8ddb8a2ad9bbbce44853b8c06e39c5ccdb989ea7474510f63942c7fb437ceda | 114 | init |

## 变更日志

- - | 2026-10-19 | birth | - | 初始化维护面 | 出生仪式 | - | - | 0→0 | open=0；越权=0
- - | 2026-10-20 | fix | - | 不变量 I2 术语对齐为四裁决全称（owner 批准：本轮修订指示；语义不变） | 10.7a 修复轮 2 | - | - | - | open=0；越权=0
- - | 2026-10-21 | fix | - | 确定性脚本例外纳入 index_proposals.py（owner 已批准：本轮修订指示；与 init_ledger.py 并列） | 10.7b 修复轮 | - | - | - | open=0；越权=0
- - | 2026-10-21 | fix | - | 提案质量字段（复现证据/通用性论证/验收分档/绕过处置/簇字段）与双索引（open+archive） | 10.8 | - | - | - | open=0；越权=0
- - | 2026-10-21 | fix | - | draft 排除触发计数/schema 标注/归档解析限定/双 INDEX 文档同步（spec 0.2.10） | 10.8 修复轮 | - | - | - | open=0；越权=0
- - | 2026-10-22 | fix | - | 章程版本绑定 0.2.10（SKILL/launch/init 默认/账本）、V3 证据不足改 needs-info、README 模板填写说明转 HTML 注释、agent-supervisor 出生骨架入库 | 10.9 终审修复批 | - | - | - | open=0；越权=0；clp/har 账本版本对齐 defer（待 owner 批准）
- - | 2026-10-22 | fix | - | 结构校验/地图 purpose 路径规则/--round 约束/术语与命令路径清理（spec 0.2.11） | 10.10 Minor 清理批 | - | - | - | open=0；越权=0；章程产物版本对齐 defer（控制者执行）

## 否决索引
