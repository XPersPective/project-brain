---
name: project-brain
description: >-
  Git-native project memory, tasks, verification and economical orchestration.
  Use for .project-brain/ or PROJECT_BRAIN.md projects, adoption, multi-session
  planning, resumption or audits. Excludes store publishing.
license: MIT
metadata:
  version: 3.10.0
  author: XPersPective
---

# Project Brain 3.10.0

`PB` = `python <this-skill>/scripts/brain.py` (Python 3.8+, stdlib).

## 1. Economy and authority

Use deterministic tools → cheapest authorized capable worker → lead decision.
Tools/workers handle scans, callers, routine edits/checks and formatting; the lead
owns architecture, planning, ambiguity, serious findings and acceptance. Spend
enough reasoning there; never lower risk/quality/review floors to save tokens.
Read this entry once and only relevant references. No whole-chat forks, broad
preloading, duplicate scans, summary-of-summary calls, unchanged polling/retests.
Trivial answers need no orchestration.

User/platform/repo rules govern; source reality beats stale Brain. Preserve user
work, requirements and uncertain operations. Routing grants resources, not scope,
messages, destructive actions, publishing or paid fallback. Only user changes Goal.
Honor git.commit: ask; existing human Git identity only. No AI/bot/provider author,
co-author, generated-by or contributor credit (workers too). Only start/check/
evidence/review/accept write Evidence/Review; never forge proof.
Keep state under `.project-brain/`; no parallel trackers or retired source-plan
recreation. Setup/security: [WORKFLOW §1](WORKFLOW.md#1-authority-and-durable-state).
Confirm secret references, never values; missing access blocks dependent work.

## 2. ESP, SP and QRP

Use Turkish names/questions from `setup ask`; keep internal identifiers English.

| Executor Selection Policy (ESP) | Resources |
|---|---|
| solo | Main agent works with tools, without subagents |
| native | Host models/agents, including stronger ones |
| native-cheap | Cheapest suitable host models/agents |
| native-pinned | Exact user-named host models/agents |
| cap-category | CLI Agent Pool (CAP): user-selected returned categories |
| cap-catalog | CAP: director selects catalog models |
| cap-pinned | Exact user-selected CAP models/services |

Scheduling Policy (SP): Serial or Parallel with a confirmed maximum. Waves are
not concurrency. Quota Recovery Policy (QRP): enabled/disabled, plus threshold
if enabled (suggest 10%); director quota only. Baton Relay Policy (BRP), optional:
circulate director across CAP accounts, threshold, director tier. [RELAY](RELAY.md).

New implementation session, including "continue": `PB orient`, `PB boot
--new-session`, read back unfinished jobs, `PB setup ask`: relay its ONE numbered
batch unchanged. No reply: `setup wait` (≤60 s/call) until TIMEOUT_REACHED, then
`setup defaults`. Session answers count; relay successors inherit, never asked.
Never reset/replay old jobs; changes govern new dispatch, with safe serial drain.
Save explicit choices: `PB policy --file <project-relative-json> --confirm
--note "<user choices>"`; `policy --full` shows exact bounds. Changing policy
invalidates confirmation. Legacy mode/environment cannot widen it. [WORKFLOW](WORKFLOW.md#2-session-and-boot-details)
defines JSON/commands. "Change ESP/SP/QRP" opens saved choices; same-session
questions do not. Unsupported host identity/effort/cost blocks affected dispatch.

CAP supplies current compact categories/catalog/efforts through its own skill;
never freeze its API or assume category names/strength. No CAP call for explicit
solo/native/no-CAP. Catalog pins need no forced category. Supported caller effort
may override a category default; hidden/disabled models are excluded.
Before use record reasoned exact-model task fit with `PB qualify`; routing
assessment is not acceptance evidence. [POOL](POOL.md) defines bounded selection.
Check workers/reviewers against saved identities/categories/effort/SP; no silent
fallback/cost escalation. Workers inherit all rules; no boot/interview/delegation.

## 3. Recovery and questions

At opted-in QRP threshold, save actual Resume/handoff before exhaustion:
`PB quota prepare --task <id> --next "<actual next>" --snapshot <ignored-json>`.
Use the HOST same-chat automation tool for returned wake intent, then `quota arm`
with its acknowledged ID. Lost acknowledgement requires readback by nonce/name,
never duplicate creation. Wake reads fresh account/quota and calls `quota resume`;
code only on RESUMED. Account switch, cancelled/changed policy/checkpoint or
unrenewed quota blocks auto-work. Delete old heartbeat before continuing; repeat
at later limits. "Cancel alarm"/"disable QRP": `quota cancel` revokes locally first,
then delete/read back host alarm. Unknown host capability blocks auto-resume,
not unrelated authorized work. No reset credits; QRP never switches accounts.
[RECOVERY](RECOVERY.md) gives host steps/limits; never promise continuous execution.

Same-session questions reuse context then resume Next: no boot/reset, history or
skill reload, dispatch/tests merely for a question. Missing focus: `PB brief`
is read-only ≤4 KiB with explicit omissions/readback warnings, not execution
authority. Record new directives with intake; preserve objective unless cancelled.
Discovery uses tools then the cheapest suitable allowed worker: ≤5 entrypoints or
bounded query, ≤150 words. Do not reorient at every wave.

## 4. Work and proof

Load applicable [WORKFLOW](WORKFLOW.md) sections: §3 intake/spec, §4 execution/
evidence/review, §5 recovery, §6 audit, §7 adoption. Record architecture/tasks before
non-trivial changes; specify acceptance, Areas/Inputs, callers and Verify.
Reconcile intent; reuse architecture/helpers and valid evidence.
Read [QUALITY](QUALITY.md) for applicable UI/backend planning/review.
MEDIUM/HIGH needs qualified independent review; REV=solo needs explicit dedicated
self-review. Reports/hashes alone are not acceptance. Serious findings, stale proof
or required feedback block closure. No blind replay. Keep concise Resume and
continue authorized work without repeated permission questions.

`PB runs` is opt-in: read [ORCHESTRATION](ORCHESTRATION.md). One writer per checkout;
parallel edits need separate worktrees and serialized integration. Across many
waves reuse packets/cursors/ready state/evidence; lead wakes for decisions, serious
findings, integration and completion. Do not claim token savings without counters.
