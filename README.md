# Skill Custodian · 技能管家

> 给 AI Agent 的技能（SKILL.md）装上**治理护栏**：提案 → 裁决 → 维护轮 → 快照 → 回归证据 → 可回滚。
>
> [English](README.en.md) | 中文

[![status](https://img.shields.io/badge/status-v0.2.12-brightgreen)]() [![tests](https://img.shields.io/badge/reference%20tests-200%20passed-brightgreen)]() [![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## 先说场景：技能为什么会"越用越烂"

Agent 技能不是写完就结束的文档，它是会被反复调用、反复修改的**生产资产**。没有治理，它通常这样烂掉：

**场景一：热修堆积**
Worker agent 发现指引不对，顺手把 SKILL.md 改了；下次另一个 agent 再改一处。三个月后，SKILL.md 变成补丁堆——规则互相矛盾，新 agent 读不懂，旧行为悄悄消失。

**场景二：同一个坑，三个 agent 各提一遍**
A 说"这里该补示例"，B 说"这里该补示例"，C 也说。没人知道这问题半年前已经裁决过、当时为什么拒绝。讨论记录散在聊天里，技能目录里看不到。

**场景三：改完没有证据**
维护者按反馈改了规则，但没人证明"下一个遇到同样项目的 agent 不会再犯"。改是改了，效果无从验证。

**场景四：owner 无法审计**
老板问："上周是谁改了这条规则？为什么改？能回滚吗？" 答案只有聊天记录，没有快照、没有账本、没有审批。

**场景五：技能边界糊了**
每来一个需求就"顺便支持一下"，技能越长越长，触发越来越不准，最后变成什么都想管、什么都管不好。

Skill Custodian 就是回答这五个问题的。

---

## 它是什么

**Skill Custodian 是一套技能治理协议 + 一组确定性脚本**，以 Agent Skill 的形式分发（`SKILL.md` + 附件）。它给被维护的技能加一个"维护面"：

```
被维护技能/
├── SKILL.md                 # 运行时：agent 读的指引
├── README.md                # 诞生背景 / 技能边界 / 使用场景
├── MAINTENANCE.md           # 维护面：技能地图 / 规则锚点 / 变更日志 / 否决索引
├── proposals/               # 提案区：open（含 draft）+ archive + 双 INDEX
├── rounds/                  # 轮次区：报告 + 修改前快照
├── evals/                   # 回归基线：越用越准的验证
└── scripts/                 # 确定性脚本：出生 / 自检 / 索引 / 发布校验
```

**核心分工**：worker agent 只提提案，不直接改技能；维护者 agent 按固定轮次裁决、整合、验证、归档；owner 掌握边界、不变量与晋级/降级。

---

## 核心机制（为什么它能兜住）

| 机制 | 解决的问题 |
|---|---|
| **双表面**：运行时 vs 维护面 | 一边给 agent 用，一边给治理用，互不污染 |
| **12 步维护轮** | 加载 → 快照 → 审计 → 上轮复核 → 边界过滤 → 聚类 → 裁决 → 锚点级整合 → 验证 → 预算 → 归档 → 自查 |
| **四裁决 + 生命周期状态** | 采纳 / 改造 / 拒绝 / 挂起-待人工批准；外加 open/triaged/needs-info/deferred/duplicate/archived |
| **边界过滤** | 先问"这是边界内改进、扩张边界，还是边界外碎碎念"，再裁决；扩张边界只能 owner 批 |
| **来源分级** | 用户指出问题 / 用户提议方案 / worker 自查 / 审计异常——用户指出的问题维护者不得单独拒绝 |
| **锚点级整合** | 每条规则有 `[R#]` 锚点；改规则必须报告"改前/改后行数、替换还是追加、删了哪段"，防止堆砌 |
| **技能地图 + manifest 版本** | 每个文件 sha256 + 行数；`manifest:<hash>` 钉住提案对应的确切版本 |
| **快照与轮次报告** | 每轮修改前快照；报告含验证矩阵，可回滚、可审计 |
| **回归证据** | 行为性变更必须挂 eval/assertion（改前失败、改后通过），否则只能挂起 |
| **否决索引** | 每条拒绝记录理由与"重开条件"，防止同一方案反复提出 |
| **双 INDEX 去重** | `proposals/open/INDEX.md` + `proposals/archive/INDEX.md`，worker 提交前先查 |
| **触发节奏** | 普通提案 ≥5 条或距上轮 ≥2 周开轮；critical 走 24h 快速通道（owner 批准 → 补追溯提案 → 下轮补回归） |
| **出生仪式 / 收养** | 新技能必须 `init_ledger` 出生；老技能 `--adopt` 收养（保留既有 README，补账本） |

一句话：**它把"技能维护"从聊天里的即兴修改，变成有提案、有裁决、有快照、有证据、可回滚的工程流程。**

---

## 依赖与外部工具

| 类型 | 依赖 | 说明 |
|---|---|---|
| 必需 | Python 3.9+ | 仅标准库；跑 `scripts/*.py` 与自检 |
| 必需 | 支持 `SKILL.md` 的 agent 运行器 | 如 Claude Code / Codex / DSH 等 |
| 可选 | `skill-creator` | 仅在"出生/起草/评估"阶段作为方法论与 eval 循环；缺失时按 §C 手动执行，出生仪式与维护轮不受影响 |

### 与 skill-creator 的关系：委托，而不是 fork

- 本仓库**不分发、不修改** `skill-creator`；它由上游维护，随你的 agent 运行器安装（Claude Code / Codex 通常自带），或从其官方分发源获取。
- 出生流程（§C）委托它的"访谈 → 起草 → 评估 → 迭代"方法论；维护轮第 8 步可借用它的评估循环做新旧版对比。
- **没有它也能用**：出生仪式（`init_ledger`）、维护轮 12 步、`check_skill`、`index_proposals` 全部独立运行；缺少它时，创建阶段的起草/评估降级为"手写 SKILL.md + 自建 evals + 手动对照"。
- **禁止**用它直接修改受治理技能：受治理技能的改动一律走提案 + 维护轮（§A 禁令）。

## 5 分钟上手

### 1）安装成一个技能

把 `skill-maintenance/` 放到你的 agent 技能发现路径（不同运行器不同）：

```bash
# Claude Code
cp -r skill-maintenance ~/.claude/skills/skill-maintenance
# Codex / DSH 等
cp -r skill-maintenance ~/.agents/skills/skill-maintenance
```

### 2）给一个已有技能"上户口"（收养）

```bash
python skill-maintenance/scripts/init_ledger.py \
  --skill-dir ~/skills/my-existing-skill --adopt --stage governed
```

它会给目标技能补上 `MAINTENANCE.md`、`proposals/`、`rounds/`、维护通道块，并保留原有 README。

### 3）从零创建一个新技能

```bash
python skill-maintenance/scripts/init_ledger.py --skill-dir ~/skills/my-new-skill
# 然后写 SKILL.md / README.md
python skill-maintenance/scripts/check_skill.py --skill-dir ~/skills/my-new-skill --rebuild-map
```

### 4）让维护者跑一轮

把 `skill-maintenance/assets/launch-template.md` 填好（目标路径、轮次ID、类型），交给一个通用 agent：

```text
你是技能 <目标绝对路径> 的维护者，不是工作者；你只做维护，不执行该技能的本职任务。
章程版本: 0.2.12
章程：<skill-maintenance>/SKILL.md（先读 §B）
...
```

维护者会按 12 步执行；轮报告写到 `rounds/<轮次ID>/REPORT.md`。

### 5）一键自检

```bash
python skill-maintenance/scripts/check_skill.py --skill-dir ~/.claude/skills/skill-maintenance
python skill-maintenance/scripts/check_skill.py --skill-dir ~/skills/my-existing-skill
```

---

## 实测效果（不是设计稿）

| 验证 | 结果 |
|---|---|
| 回归测试（开发仓库） | **200 passed** |
| Dry-run（合成技能，19 条发现） | 修订后复跑：10 条消解 / 2 条部分 / 0 条仍存在 |
| 真实试点（`codebase-learning-plan`，12 条真实提案） | 2 轮维护：**改造 12/12（100%）**，采纳 0，复发 0，越权 0；SKILL.md 291→305 行（+14），在预算内 |
| 提案质量 | 真实用户提案 → 3 簇 → 改造入 3 条稳定规则；拒绝堆砌 |
| Dogfooding | 用配套的「智能体总管」技能跑真实任务（一键验证工具），一轮审查 + 一轮修复后通过 |
| 自检 | staging 与安装副本 `manifest` 一致；`check_skill` 0 |

> 回归测试、设计规格与试点数据在开发仓库中；本仓库只分发技能本体。

---

## 仓库结构

```
.
├── README.md              # 本文件（中文）
├── README.en.md           # English
├── LICENSE                # MIT
└── skill-maintenance/     # 技能本体（复制到技能目录即可用）
    ├── SKILL.md           #   worker 协议 / 维护者章程 / 12 步
    ├── README.md          #   技能诞生背景 / 边界 / 场景
    ├── MAINTENANCE.md     #   狗粮账本（自监督）
    ├── scripts/           #   init_ledger / check_skill / index_proposals
    ├── references/        #   审计细则 / 裁决判例
    ├── assets/            #   README/账本/提案/轮报告/启动模板
    └── evals/             #   回归基线
```

---

## 适合谁 / 不适合谁

**适合**：有多个 agent 共用技能的团队；技能会持续迭代、需要回归与审计的项目；想把"技能维护"工程化的个人；需要给技能做 owner 把关的组织。

**不适合**：一次性实验技能；单文件小改动；只想让 agent 直接改 SKILL.md 的临时场景（那就用普通 skill-creator）。

---

## 设计原则（为什么这样写）

- **拒绝堆砌**：改造占比 ≥50%、采纳 ≤20% 是健康信号；规则不是越加越好，是把根因收敛成更少、更准的锚点。
- **改完要能证明**：行为性变更必须挂回归证据；没有证据的"改进"只是换了一种说法。
- **边界归 owner**：维护者可以裁决提案，但不能替 owner 扩张技能边界。
- **一切可回滚**：每轮修改前快照 + 账本 + manifest；随时能回到上一轮。

---

## Roadmap

- [ ] evals runner 实证（把维护轮新增的 eval 自动跑成回归基线）
- [ ] 更多真实技能的试点数据（多语言、多领域）
- [ ] 技能的跨仓库分发与版本迁移工具
- [ ] 与团队协作工具（Issue/PR）双向同步提案

## 参与贡献

1. 用 `skill-maintenance/assets/REPORT.template.md` 提 issue（现象 + 复现 + 证据 + 建议改动 + 验收标准）；
2. 维护者按 `skill-maintenance/SKILL.md` 的 12 步处理；
3. PR 请附"改前失败、改后通过"的测试证据。

## License

MIT —— 见 [`LICENSE`](LICENSE)。

---

<sub>Skill Custodian / 技能管家 · v0.2.12 · 用"轮次"代替"即兴修改"</sub>
