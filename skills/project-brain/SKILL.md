---
name: project-brain
description: >-
  Git-native project memory, executable tasks, source-bound verification and
  model-aware handoffs for multi-session software projects. Use when a repository
  has .project-brain/ or PROJECT_BRAIN.md, or the user wants project adoption,
  planning, resumption or an audit. Includes frontend and architecture quality,
  optional native/CLI delegation and quota protection. Excludes store publishing.
license: MIT
metadata:
  version: 3.7.3
  author: XPersPective
---

# Project Brain 3.7.3

Git-native intent, tasks, evidence and continuity. Python 3.8+, stdlib only.
`PB` = `python <this-skill>/scripts/brain.py`.

## 1. Mandatory economy

Use deterministic tools → cheapest authorized capable worker → lead decision.
Tools/workers handle inventory, search, callers, routine edits/checks/formatting.
The lead owns architecture, planning, ambiguity, serious findings and acceptance.
Spend enough reasoning there; never lower risk/quality/review floors for tokens.
Solo uses tools, no worker/CAP probes. Trivial answers need no orchestration.

Read this entry once; load only applicable references. No whole-chat forks,
broad preloading, duplicate scans, summary-of-summary calls, busy polling or
unchanged-premise retests. Reports need evidence; inspect named gaps/changes.

## 2. Authority

User/platform/repo rules govern; source reality beats stale Brain. Preserve user
work, requirements and uncertain operations. Routing grants resources, not new scope,
external messages, destructive actions, publishing or paid fallback. Only the user
changes Goal. Honor `git.commit: ask`; use existing human Git identity, never
AI/bot/provider author/co-author/generated-by/contributor credit (workers too).
Only `start/check/evidence/review/accept` write Evidence/Review; never forge proof.

Keep Brain state under `.project-brain/`; no parallel trackers or retired source
plan recreation. Setup/security: [WORKFLOW §1](WORKFLOW.md#1-authority-and-durable-state).
Confirm secret references once, never values; missing access blocks dependent work.

## 3. Executor Selection Policy (ESP) and Scheduling Policy (SP)

Keep names English; localize explanations.
Solo means the main agent performs the work with tools, without subagent delegation.

New implementation session, including a new-session "continue": `PB orient`,
then `PB boot --new-session`. Preserve/read back unfinished jobs. Show saved ESP
and SP; ask ONE short keep/change confirmation covering BOTH before new dispatch.
Use explicit answers already given for this session. Do not reset unfinished work.

| ESP choice | Subagent source |
|---|---|
| solo | Main agent performs the work; no subagents |
| native | Host models/agents, including stronger ones |
| native-cheap | Cheapest suitable host agents/models |
| native-pinned | Only user-named host agents/models |
| cap-category | CLI Agent Pool (CAP): user-selected returned categories |
| cap-catalog | CAP: director selects from the available catalog |
| cap-pinned | CAP: only user-named catalog models/services |

SP is separate: Serial (one at a time) or Parallel (user-confirmed maximum within
host limits). Recommend saved parallel settings for unfinished parallel work;
never silently switch. Existing jobs keep their authorization; changes govern new
dispatches, with drain/readback instead of replay or automatic cancellation.

For CAP choices use its skill's compact categories/catalog/efforts, not fixed
category assumptions. No CAP call for explicit solo/native/no-CAP. Metadata is not
dispatch. Caller-selected effort may override a category default when supported.
Hidden/disabled/removed models are excluded; unknown cost/suitability is not proof.
Save exact ESP bounds/effort and SP under `execution`/`review`/`scheduling` in
`.project-brain/executor-policy.json`. "Change ESP"/"change SP" shows current
choices and asks what to keep/change. Normal questions never reopen either.
[WORKFLOW §2](WORKFLOW.md#2-session-and-boot-details) defines the record/CLI limits.

Check every worker/reviewer against source/model/category/effort/SP bounds.
Unavailability blocks that action; no silent fallback or cost escalation.
Workers inherit ESP, SP and economy; no boot/interview/nested delegation.
Discovery uses tools then the cheapest suitable authorized worker: ≤5 entrypoints
or a bounded query, ≤150 words. Never duplicate its scan or lower quality floors.
Reuse metadata across waves; refresh changed/stale/invalid choices only. No full
catalogs, dashboard/login/provider probes just to connect. [POOL](POOL.md) covers
CAP; [AGENTS_CLI](AGENTS_CLI.md) covers direct adapters. ESP/SP is a protocol record;
legacy CLI does not parse it.

An intervening question/status is NOT a new session. Answer from current context,
then resume Next: no boot/reset, history or skill reload, scan, full diff, dispatch,
tests or planning interview just for the question. Missing focus: `PB brief`
provides a read-only ≤4 KiB observation with explicit omissions/readback warnings;
it never grants execution or replaces boot at actual takeover. Simple answered
questions need no intake write. Record new/multipart directives with `intake`;
preserve the objective unless cancelled. Reconcile changed scope, not whole history.

## 4. Work and quality

Load applicable [WORKFLOW](WORKFLOW.md) sections: §3 intake/spec, §4 execution/
evidence/review, §5 recovery, §6 audit, §7 adoption. Record architecture/tasks before
non-trivial changes; specify acceptance, Areas/Inputs, callers and Verify. Reconcile
intent before execution; reuse existing architecture/helpers and valid evidence.
Read [QUALITY](QUALITY.md) for applicable UI/backend planning/review.

MEDIUM/HIGH needs qualified independent review; REV=solo needs dedicated explicit
self-review. Reports/hashes alone are not acceptance. Serious findings, stale proof
or required user feedback block closure. No blind external replay. Keep concise
Resume; continue authorized work without repeated permission questions.

`PB runs` is opt-in: read [ORCHESTRATION](ORCHESTRATION.md). One writer per checkout;
parallel edits need separate worktrees and serialized integration. Across 10/20/100
waves reuse packets, cursors, ready state and evidence; never restart orientation
or re-plan everything each wave. Waves are not concurrency. Wake the lead for
decisions, serious findings, integration and completion. Do not claim measured
token savings without real provider/host counters.
