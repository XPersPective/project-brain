---
name: project-brain
description: >-
  Git-native project memory, tasks, verification and economical orchestration.
  Use for .project-brain/ or PROJECT_BRAIN.md projects, adoption, multi-session
  planning, resumption or audits. Excludes store publishing.
license: MIT
metadata:
  version: 3.11.0
  author: XPersPective
---

# Project Brain 3.11.0

`PB` = `python <this-skill>/scripts/brain.py` (Python 3.8+, stdlib).

## 1. Economy, roles and authority

Use deterministic tools → cheapest authorized capable worker → lead decision.
Tools/low-tier (`L`) workers handle scans, callers, routine edits/checks and map
discovery (≤5 entrypoints, ≤150 words); never waste high-tier tokens on boot scans.
Roles and independent second opinion are mandatory: [WORKFLOW §2.2](WORKFLOW.md#22-roles-economy-and-context).
Yönetici owns architecture/acceptance; Uygulayıcı implements/proves;
Denetleyici independently reviews. Initial architecture/roadmaps and critical
decisions require ≥1 unbiased opinion. Turbo never waives these rules.
Read this entry once and only relevant references. No whole-chat forks, broad
preloading, duplicate scans, summary-of-summary calls, or unchanged polling/retests.

User/platform/repo rules govern; source reality beats stale Brain. Preserve user
work, requirements and uncertain operations. Routing grants resources, not scope,
messages, destructive actions, publishing or paid fallback. Only user changes Goal.
Honor git.commit: ask; existing human Git identity only. No AI/bot/provider author,
co-author, generated-by or contributor credit (workers too). Only start/check/
evidence/review/accept write Evidence/Review; never forge proof.
Keep state under `.project-brain/`; `boot` prunes committed closed evidence/old logs.
Setup/security: [WORKFLOW §1](WORKFLOW.md#1-authority-and-durable-state).
Confirm secret references, never values; missing access blocks dependent work.

## 2. Seven-item setup, ESP, SP, speed, QRP and BRP

Use Turkish names/options from `setup ask`; keep internal identifiers English.

| Executor Selection Policy (ESP) | Resources |
|---|---|
| solo | Main agent works with tools, without subagents (parallel tools allowed) |
| native | Host models/agents (`Yerleşik ajanlar`) |
| native-cheap | Cheapest suitable host models/agents |
| native-pinned | Exact user-named host models/agents |
| mixed | Host agents + CLI Agent Pool (`Yerleşik ajanlar + CLI Ajan Havuzu`), optional `categories` |
| cap-category | CLI Agent Pool (CAP): user-selected returned categories |
| cap-catalog | CAP: director selects catalog models (`Yalnız CLI Ajan Havuzu`) |
| cap-pinned | Exact user-selected CAP models/services |

Scheduling Policy (SP): Parallel (auto ceiling up to capacity, or user cap) or Serial.
Speed: `balanced` (Dengeli) or `turbo` (max useful parallelism/faster tier on critical
path; never lowers quality/proof/review floors). Quota Recovery Policy (QRP) and
Baton Relay Policy (BRP): prepare checkpoint at threshold+5% (15%), trigger at
threshold (10%, reserve kept). If BRP is on, try ready successor first; if none and
QRP is on, wait; else save and stop. [RELAY](RELAY.md).

New implementation session, including "continue": `PB orient`, `PB boot
--new-session`, read back unfinished jobs, `PB setup ask`: relay its 7-item Turkish
batch (and embed `.project-brain/.cache/setup-form.html` via `<agent-embed>` when
the host supports inline HTML). If `RELAY_ACTIVE` or `QUOTA_WAITING` is returned,
show that status screen instead. After a submitted form with missing `Kullanıcı seçimi`
details, run `setup clarify --answer "<answer>" --file <resolved-policy.json>`;
relay its follow-up, never dispatch while pending. `setup wait` (≤60 s/call) then
`setup defaults` after 300 s preserves resolved choices; policy confirmation resolves it.
Workers/successors inherit. On CAP failure run `setup recover-cap --role exec|rev`
and relay its notification. Explicit CAP-only waits unless `cap_fallback: native`
was allowed; mixed uses its allowed native half. Read back uncertain jobs first.
Save explicit choices: `PB policy --file <project-relative-json> --confirm
--note "<user choices>"`; `policy --full` shows exact bounds. [WORKFLOW](WORKFLOW.md#2-session-and-boot-details).

CAP supplies current compact categories/catalog/efforts through its own skill;
never freeze its API or assume category names/strength. No CAP call for explicit
solo/native/no-CAP. Before use record reasoned exact-model task fit with `PB qualify`;
routing assessment is not acceptance evidence. [POOL](POOL.md) defines bounded selection.
Check workers/reviewers against saved identities/categories/effort/SP; no silent
fallback/cost escalation. Workers inherit all rules; no boot/interview/delegation.

## 3. Recovery, relay stop and questions

At threshold, save Resume/handoff: `PB quota prepare --task <id> --next "<actual next>"
--snapshot <ignored-json>`. Use HOST same-chat automation tool, then `quota arm`.
Wake reads fresh account/quota and calls `quota resume`; code only on RESUMED.
"Cancel alarm"/"disable QRP": `quota cancel` revokes locally first, then delete host
alarm. `PB relay stop` requests a 2-minute graceful save-and-withdraw (`STOPPING`);
the holder saves Resume and runs `relay complete`, or `relay stop` forces after 120 s.
[RECOVERY](RECOVERY.md) gives host steps/limits; never promise continuous execution.

Same-session questions reuse context then resume Next: no boot/reset, history or
skill reload, dispatch/tests merely for a question. Missing focus: `PB brief`
is read-only ≤4 KiB with explicit omissions/readback warnings, not execution
authority. Record new directives with intake; preserve objective unless cancelled.

## 4. Work and proof

Load applicable [WORKFLOW](WORKFLOW.md) sections: §3 intake/spec, §4 execution/
evidence/review, §5 recovery, §6 audit, §7 adoption. Record architecture/tasks before
non-trivial changes; specify acceptance, Areas/Inputs, callers and Verify.
Read [QUALITY](QUALITY.md) for applicable UI/backend planning/review.
MEDIUM/HIGH needs qualified independent review; REV=solo needs explicit dedicated
self-review. Reports/hashes alone are not acceptance. Serious findings, stale proof
or required feedback block closure. `PB runs` is opt-in: read [ORCHESTRATION](ORCHESTRATION.md).
Do not claim token savings without counters.
