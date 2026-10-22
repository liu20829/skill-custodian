# Skill Custodian · Governance for AI-Agent Skills

> Guardrails for AI-agent skills (`SKILL.md`): **proposal → adjudication → maintenance round → snapshot → regression evidence → rollback.**
>
> English | [中文](README.md)

[![status](https://img.shields.io/badge/status-v0.2.11-brightgreen)]() [![reference tests](https://img.shields.io/badge/reference%20tests-200%20passed-brightgreen)]() [![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## The problem: skills rot

An agent skill is not a document you write once. It is a **production asset** that gets called, patched, and re-patched. Without governance it usually rots like this:

**Scenario 1 — patch pile-up.** A worker agent notices a bad instruction and edits `SKILL.md` on the spot. Next week another agent edits a different spot. Three months later the skill is a pile of patches: rules contradict each other, new agents can't follow it, and old behavior silently disappears.

**Scenario 2 — the same complaint, three times.** Agent A says "this needs an example." Agent B says the same. Agent C too. Nobody knows the issue was adjudicated six months ago and rejected with a reason. The discussion lives in chat logs, invisible from the skill directory.

**Scenario 3 — changed, but no proof.** A maintainer rewrites a rule based on feedback. Nobody can show that the next agent hitting the same kind of project will no longer fail. The change happened; the effect is unverified.

**Scenario 4 — the owner can't audit.** "Who changed this rule last week? Why? Can we roll it back?" All you have is chat history — no snapshot, no ledger, no approval record.

**Scenario 5 — boundaries blur.** Every new request gets a "while we're at it, also support…" The skill grows, triggering gets less accurate, and it ends up owning everything and nothing.

Skill Custodian is the answer to these five problems.

---

## What it is

**Skill Custodian is a governance protocol plus a set of deterministic scripts**, distributed as an Agent Skill (`SKILL.md` + assets). It adds a **maintenance surface** to any skill it governs:

```
governed-skill/
├── SKILL.md                 # runtime: the instructions the agent reads
├── README.md                # birth background / boundaries / use cases
├── MAINTENANCE.md           # maintenance surface: skill map / anchors / changelog / rejection index
├── proposals/               # proposals: open (incl. draft) + archive + two INDEXes
├── rounds/                  # rounds: reports + pre-change snapshots
├── evals/                   # regression baseline
└── approvals/               # owner approvals
```

**Division of labor:** worker agents only file proposals; they do not edit the skill. A maintainer agent adjudicates, integrates, verifies, and archives in fixed rounds. The owner owns boundaries, invariants, and promotion/demotion.

---

## Core mechanisms

| Mechanism | What it solves |
|---|---|
| **Two surfaces**: runtime vs maintenance | One surface for agents, one for governance — no cross-contamination |
| **12-step maintenance round** | Load → snapshot → audit → review last round → boundary filter → cluster → adjudicate → anchor-level integration → verify → budget → archive → self-check |
| **Four verdicts + lifecycle states** | Adopt / transform / reject / escalate-to-owner; plus open/triaged/needs-info/deferred/duplicate/archived |
| **Boundary filter** | First ask: is this an in-boundary improvement, a boundary expansion, or out-of-scope noise? Boundary expansions require owner approval |
| **Provenance classes** | User-reported issue / user-proposed solution / worker self-check / audit anomaly — a maintainer may not unilaterally reject a user-reported issue |
| **Anchor-level integration** | Every rule has an `[R#]` anchor; changes must report before/after line counts, replace-vs-append, and deleted text — anti-patch-pile-up by design |
| **Skill map + manifest version** | sha256 + line count per file; `manifest:<hash>` pins the exact version a proposal refers to |
| **Snapshots + round reports** | A snapshot before every round; reports include a verification matrix — auditable and rollback-able |
| **Regression evidence** | Behavioral changes must cite an eval/assertion (fails before, passes after); otherwise the proposal can only be deferred |
| **Rejection index** | Every rejection records the reason and "reopen conditions", preventing repeated proposals |
| **Dual INDEX dedupe** | `proposals/open/INDEX.md` + `proposals/archive/INDEX.md`; workers check before filing |
| **Cadence** | A round opens at ≥5 non-suspended proposals or ≥2 weeks since the last one; critical proposals use a 24h fast lane (owner approval → trace proposal → regression next round) |
| **Birth ritual / adoption** | New skills must be born via `init_ledger`; existing skills are adopted with `--adopt` (keeps the existing README, adds the ledger) |

In one sentence: **it turns skill maintenance from improvised chat edits into an engineering process with proposals, verdicts, snapshots, evidence, and rollback.**

---

## Dependencies & external tools

| Type | Dependency | Notes |
|---|---|---|
| Required | Python 3.9+ | Standard library only; runs `scripts/*.py` and self-checks |
| Required | An agent runtime that loads `SKILL.md` | e.g. Claude Code / Codex / DSH |
| Optional | `skill-creator` | Used only during birth/drafting/evaluation as a methodology and an eval loop; without it, follow §C manually — the birth ritual and maintenance rounds are unaffected |

### Relationship to skill-creator: delegation, not a fork

- This repo does **not** distribute or modify `skill-creator`. It is maintained upstream and usually ships with your agent runtime (Claude Code / Codex), or can be obtained from its official distribution.
- The birth flow (§C) delegates its "interview → draft → evaluate → iterate" methodology to it; step 8 of a maintenance round may use its eval loop for a before/after comparison.
- **It works without it**: `init_ledger.py`, the 12-step maintenance round, `check_skill.py`, `index_proposals.py`, and `verify.py` all run independently. Without `skill-creator`, the creation phase degrades to hand-writing `SKILL.md`, authoring evals yourself, and manual comparison.
- **Never** use it to modify a governed skill directly: changes to governed skills go through proposals + maintenance rounds (§A prohibition).

## Quick start (5 minutes)

### 1) Install as a skill

Drop `skill-maintenance/` into your agent's skill-discovery path:

```bash
# Claude Code
cp -r skill-maintenance ~/.claude/skills/skill-maintenance
# Codex / DSH and similar
cp -r skill-maintenance ~/.agents/skills/skill-maintenance
```

### 2) Adopt an existing skill

```bash
python skill-maintenance/scripts/init_ledger.py \
  --skill-dir ~/skills/my-existing-skill --adopt --stage governed
```

This adds `MAINTENANCE.md`, `proposals/`, `rounds/`, and the maintenance-channel block to the target skill, keeping its existing README.

### 3) Birth a new skill

```bash
python skill-maintenance/scripts/init_ledger.py --skill-dir ~/skills/my-new-skill
# write SKILL.md / README.md
python skill-maintenance/scripts/check_skill.py --skill-dir ~/skills/my-new-skill --rebuild-map
```

### 4) Run a maintenance round

Fill in `skill-maintenance/assets/launch-template.md` (target path, round ID, type) and hand it to a general-purpose agent:

```text
You are the maintainer of the skill at <absolute target path>, not a worker;
you only maintain it and do not perform the skill's own job.
Charter version: 0.2.11
Charter: <skill-maintenance>/SKILL.md (read §B first)
...
```

The maintainer executes the 12 steps and writes a round report to `rounds/<round-id>/REPORT.md`.

### 5) Self-check

```bash
python skill-maintenance/scripts/check_skill.py --skill-dir ~/.claude/skills/skill-maintenance
python skill-maintenance/scripts/check_skill.py --skill-dir ~/skills/my-existing-skill
```

---

## Evidence (not just a design doc)

| Validation | Result |
|---|---|
| Regression tests (development repo) | **200 passed** |
| Dry run on a synthetic skill (19 findings) | After the revision round: 10 resolved / 2 partial / 0 still present |
| Real pilot (`codebase-learning-plan`, 12 real proposals) | 2 rounds: **12/12 transformed (100%)**, 0 adopted, 0 recurrence, 0 unauthorized changes; SKILL.md 291→305 lines (+14), within budget |
| Proposal quality | Real user proposals → 3 clusters → transformed into 3 stable rules; no patch pile-up |
| Dogfooding | The companion `agent-supervisor` skill ran a real task (a one-command verification tool): one review round + one fix round, approved |
| Self-check | staging and installed copies share the same `manifest`; `check_skill` is clean |

> The regression suite, design spec, and pilot data live in the development repo; this repo distributes the skill itself.

---

## Repository layout

```
.
├── README.md              # Chinese
├── README.en.md           # this file
├── LICENSE                # MIT
└── skill-maintenance/     # the skill (copy it into your skills directory)
    ├── SKILL.md           #   worker protocol / maintainer charter / 12 steps
    ├── README.md          #   birth background / boundaries / use cases
    ├── MAINTENANCE.md     #   dogfood ledger (self-governed)
    ├── scripts/           #   init_ledger / check_skill / index_proposals
    ├── references/        #   audit details / verdict precedents
    ├── assets/            #   README / ledger / proposal / round-report / launch templates
    └── evals/             #   regression baseline
```

---

## Who it's for / not for

**Good fit:** teams where multiple agents share skills; projects whose skills keep evolving and need regression + audit; individuals who want to engineer skill maintenance; organizations that need owner sign-off on skill boundaries.

**Not a fit:** one-off experimental skills; single-file tweaks; cases where you just want an agent to edit `SKILL.md` directly (use a plain skill-creator).

---

## Design principles

- **No patch pile-up**: a healthy round shows ≥50% "transform" and ≤20% "adopt". More rules is not better; fewer, sharper anchors is.
- **Changes must be provable**: behavioral changes carry regression evidence; an "improvement" without evidence is just a rephrasing.
- **Boundaries belong to the owner**: maintainers can adjudicate proposals, but they cannot expand a skill's boundary on the owner's behalf.
- **Everything is rollback-able**: pre-round snapshot + ledger + manifest; you can always return to the previous round.

---

## Roadmap

- [ ] Eval runner: turn newly added evals into automated regression runs
- [ ] More real-world pilots (multi-language, multi-domain)
- [ ] Cross-repo skill distribution and version migration tooling
- [ ] Two-way sync between proposals and team tools (Issues/PRs)

## Contributing

1. File an issue with the proposal template (`skill-maintenance/assets/REPORT.template.md`): symptom + reproduction + evidence + suggested change + acceptance criteria;
2. A maintainer processes it through the 12 steps in `skill-maintenance/SKILL.md`;
3. PRs should include test evidence: fails before, passes after.

## License

MIT — see [`LICENSE`](LICENSE).

---

<sub>Skill Custodian · v0.2.11 · rounds over improvisation</sub>
