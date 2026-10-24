skill_name: {{SKILL_NAME}}
owner: {{OWNER}}
created: {{DATE}}
stage: {{STAGE}}
stage_history:
charter_version: {{CHARTER_VERSION}}
round:
round_in_progress:
evals: no
<!-- evals 字段：出生时按目标是否已有 evals/evals.json 写入；出生后新建 evals/evals.json 须改为 yes 并追加变更日志行（check_skill 会校验字段与文件的一致性，125852）。 -->
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
<!-- 变更日志：新条目追加在上一行之后（本节内）；禁止写到文件末尾（否决索引在下方）。 -->

## 否决索引

<!-- 否决索引：新条目追加到本节内。 -->
（每条一行：D1 | 日期 | 提案ID | 理由 | 重开条件）
