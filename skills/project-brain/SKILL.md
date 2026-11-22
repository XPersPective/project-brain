---
name: project-brain
description: >-
  Git-native project memory, executable tasks, source-bound verification and
  economical orchestration. Use for .project-brain/ or PROJECT_BRAIN.md
  projects, adoption, multi-session planning, resumption or audits. Excludes
  store publishing.
license: MIT
metadata:
  version: 4.0.6
  author: XPersPective
---

# Project Brain 4.0.6

`PB` = `python <this-skill>/scripts/brain.py` (Python 3.8+, stdlib only).

## 1. Core authority and economy

Use deterministic tools → cheapest authorized capable worker → lead decision.
Tools and `L` workers handle scans, callers, routine edits/checks and bounded
map discovery (≤5 entrypoints, ≤150 words). Read this entry once and only
relevant references; never preload histories, full catalogs, all domains, or
repeat unchanged checks/scans.

User, platform and repository rules govern; source reality beats stale Brain.
Preserve user work, requirements and uncertain operations. Routing grants
resources, never scope, external messages, destructive actions, publishing or
silent paid fallback. Only the user changes `Goal`.

- **Git identity:** honor `git.commit: ask`; existing human Git identity only.
  Never add AI, model, provider or bot author, `Co-authored-by`, generated-by,
  contributor or PR credit (workers too).
- **Proof:** only `start`, `check`, `evidence`, `review`, `accept` write
  Evidence/Review; never forge proof.
- **State & secrets:** keep plans under `.project-brain/`; `boot` prunes
  committed closed evidence/old logs. Confirm a symbolic secret reference once,
  never secret values; missing access blocks only secret-dependent work.
  [WORKFLOW §1](WORKFLOW.md#1-authority-and-durable-state).

## 2. Session setup: Core defaults vs Power features

Core Brain runs standalone (`solo` or host `native`, zero external deps).
External CLIs live exclusively in [CLI Agent Pool](POOL.md) (CAP); legacy
`--backend direct` is removed.

| Executor Selection Policy (ESP) | Resources |
|---|---|
| `solo` | Main agent works with tools only (no subagents) |
| `native` *(default)* | Host agents/models |
| `native-cheap` / `native-pinned` | Cheapest suitable or exact user-named host models |
| `mixed` *(power)* | Host agents + CAP (optional CAP `categories`) |
| `cap-category` / `cap-catalog` / `cap-pinned` *(power)* | CAP only |

New implementation session (including "continue"): `PB orient`,
`PB boot --new-session`, read back unfinished jobs, then `PB setup ask` (on
`NO_BRAIN`, see WORKFLOW §7). Core defaults: `native · parallel (auto) · QRP off · BRP off`.
Present the 1-line summary and wait for user confirmation before `PB setup confirm`
(or inline `PB policy --source <src> --schedule parallel|serial --confirm`). Use
`setup ask --advanced` only when power features are requested. Workers/relay
successors inherit settings. On CAP failure: `PB setup recover-cap --role exec|rev`.
[WORKFLOW §2](WORKFLOW.md#2-session-and-boot-details).

Same-session questions reuse context then resume `Next` (no boot/reset/reloads).
Use `PB board` for progress, `PB watch` (1-line), or `PB brief` (≤4 KiB) only for missing focus.

- **Progress Board (`PB board`, TR: *İlerleme Panosu*, default `on`):** On boot,
  transitions, or status queries, echo only the latest `PROGRESS_BOARD` block
  verbatim once per reply (0 layout tokens; never on errors). To hide/show (EN/TR:
  *gösterme/kapat*, *göster/aç*): `PB board off|on`.

## 3. Work, quality and review

Load only applicable [WORKFLOW](WORKFLOW.md) sections (§3 intake/spec, §4 work/
review, §5 checkpoints, §6 audit, §7 adoption) and [QUALITY](QUALITY.md) for
UI/backend planning or review.

- **Roles:** Lead owns architecture/planning/acceptance; Implementer builds and
  proves; Reviewer independently audits `MEDIUM`/`HIGH` work (registered via
  `PB runs` receipt or CAP; `solo` review needs explicit `--self-review`).
  Initial architecture and critical decisions need ≥1 independent opinion.
- **Verification:** `score`, `reconcile`, `start`, `check`, `evidence`, `review`,
  `accept`. UI requires `[visual]`, `[interaction]`, `[accessibility]` proof.
  Serious findings, stale proof or pending user feedback block closure.

## 4. Opt-in power references

Load only when enabled: [POOL.md](POOL.md) (CAP, advisory `qualify`),
[ORCHESTRATION.md](ORCHESTRATION.md) (`PB runs`), [RECOVERY.md](RECOVERY.md)
(QRP), [RELAY.md](RELAY.md) (BRP). Never claim billed-token savings without counters.
