skill_name: {{SKILL_NAME}}
owner: {{OWNER}}
created: {{DATE}}
stage: {{STAGE}}
stage_history:
charter_version: {{CHARTER_VERSION}}
round:
round_in_progress:
evals: no
adopted: false

## 设计意图

（规则级理由：为什么这样写，而不那样写。）

## 不变量

（I1..In；删改须 owner 批准。）

## 规则锚点

| anchor | summary | status | last_round | void_round |
|---|---|---|---|---|

## 技能地图

| path | purpose | sha256 | lines | last_verified_round |
|---|---|---|---|---|
{{SKILL_MAP}}

## 变更日志

<!-- 列序（10 列）：round_id | date | type | proposal_ids | what | why | rejected_alt | anchors | before→after 行数 | 指标快照 -->
- - | {{DATE}} | birth | - | 初始化维护面 | 出生仪式 | - | - | 0→0 | open=0；越权=0

## 否决索引

（每条一行：D1 | 日期 | 提案ID | 理由 | 重开条件）
