# Project Brain — Schemas (schema 4)

`brain.py init` and `brain.py new` write these templates; `brain.py migrate` converts older ones. Read this
file to change a format, interpret a trailer, or understand a migration.

# config.yaml

Stable policy only — never HEAD, active task, timestamps, model, or test results.

```yaml
schema_version: 4
architecture:
  mode: single          # single: current.md/target.md | domains: current/<d>.md, target/<d>.md
git:
  history_mode: unknown # preserve | squash | rewrite-prone | unknown
  commit: auto          # auto | ask
  push: manual          # every-task | milestone | session-end | manual
commands:
  test: "python -m pytest -q"
  lint: "ruff check ."
  build: ""
```

The parser supports exactly this shape: top-level keys, one level of `key: value`, quoted or bare values,
`#` comments.

# current.md

```markdown
# Current Architecture

## Runtime
- Python 3.11, FastAPI; entry `src/app/main.py:create_app`

## Map
- `src/app/main.py` — app factory, router registration
- `src/auth/` — sessions, JWT; `tokens.py:refresh` is the hot path

## Domains

### Auth
Status: VERIFIED
Sources: `src/auth/**`, `tests/auth/**`
- session lifecycle in `src/auth/session.py:Session`

## Known Unknowns
- billing retry semantics (not inspected)
```

- **Map** ≤40 lines, `path — role`. It replaces exploration in later sessions; keep it current.
- **Domain** = a `##`/`###` heading with a `Sources:` line (backticked globs; bullets under it also count).
  Name is normalized to lowercase-with-dashes (`API Routing` → `api-routing`); use that form in trailers
  and in task `Domains:` (boot then loads only those line ranges of a long current.md).
  `*` matches across `/`; a path without wildcards matches itself and everything below it.
- **Markers**: VERIFIED (code read), OBSERVED (skimmed), INFERRED (indirect evidence), STALE (code changed
  since), UNKNOWN (not inspected). `ASSUMED` is not allowed — create a task to verify instead.
- No SHAs in the file; the commit carrying `PB-Current-Checkpoint` is the checkpoint.
- **Domain mode**: `current/<domain>.md`, file name = domain name, same sections minus `## Domains`.

# target.md

```markdown
# Target Architecture
Status: CONFIRMED

## Goal
"Every user can export their data as CSV and JSON" (user, 2026-10-08).

## Target State
### Export
- streaming exporter in `src/export/`, formats CSV + JSON

## Non-Goals
- XML export

## Open Decisions
- TD-001 OPEN: include deleted records? -> blocks PB-021

## Success Conditions
- `pytest -q tests/export` green; a 1 GB account exports in < 60 s on the CI runner
```

- `Status: DRAFT` until the user confirms the Goal; while DRAFT only goal-independent work is planned.
- **Goal** is the user's, verbatim; agents never edit it (SKILL.md §8c/d). Target State may be revised only
  through the evidence gate (§8b) with an ADR.
- Open Decision status: OPEN | RESOLVED | DEFERRED. Success Conditions must be observable.

# constraints.md

One line each: `- C-001: <rule that changes decisions> (source: user | config | convention)`.
No generic advice ("write clean code").

# Task — tasks/PB-NNN.md

```markdown
# PB-014 — Add Turkish date parser
Status: READY
Priority: P2
Tier: L
Risk: LOW
Depends: PB-011
Areas: `src/utils/date.py`, `tests/test_date.py`
Domains: utils

## Objective
"dates in the import file are dd.mm.yyyy" (user). Parse them instead of failing.

## Steps
1. In `src/utils/date.py`, next to `parse_iso`, add `parse_tr_date(s: str) -> date`.
2. Raise `ValueError` with the bad input in the message for anything else.
3. Add cases to `tests/test_date.py`: valid date, wrong separator, 31.02.2026.

## Acceptance
- [ ] `parse_tr_date("16.09.2026") == date(2026, 9, 16)` (asserted by a test)
- [ ] invalid inputs raise `ValueError` (test fails if they do not)

## Verify
- `python -m pytest -q tests/test_date.py`

## Escalate if
- the import format turns out to carry times or time zones

## Notes
- Milestone: import v2
```

| Header | Values |
|---|---|
| `Status` | one word: PLANNED → READY → IN_PROGRESS → (done: file deleted); any → BLOCKED → READY |
| `Priority` | P1 user's current ask or blocker · P2 normal (default) · P3 later. FOCUS = best priority, then lowest ID |
| `Tier` | L mechanical, fully specified · M normal engineering · H design, ambiguity, security, specs |
| `Risk` | LOW / MEDIUM / HIGH (sets verification breadth) |
| `Depends` | task IDs, `-` when none. Absent from `tasks/` = completed |
| `Areas` | backticked globs; boot uses them to tell your dirty files from someone else's |
| `Domains` | Current domains this task may change; boot loads only those sections |
| `Blocked` | only when BLOCKED: what is needed, from whom |

**READY means executable spec**: `## Steps` (numbered, exact paths/symbols/commands), `## Acceptance` with
`- [ ]` checkboxes, `## Verify` with a backticked command, no vague words. Otherwise PLANNED.
Optional `## Resume` (when stopping mid-task): `Next:`, `Failing:`, `Dirty:` lines. Boot prints `Next:`
and the unchecked Acceptance items.

# ADR — decisions/ADR-NNN.md

Sections: Status (Proposed | Accepted | Superseded | Rejected), Context, Decision, Rationale (explicit),
Alternatives (serious ones only), Consequences, Related (tasks, domains, constraints). For a replan (§8b):
problem, evidence, options, choice, impact on tasks. Write one only when a future agent would otherwise
re-open or misread the decision.

# Commit trailers

| Trailer | Means | Does not mean |
|---|---|---|
| `PB-Current-Checkpoint: auth,api` / `all` | Current for these domains was reconciled with the code through this commit | architecture changed; all tests pass |
| `PB-Target-Checkpoint: auth` | Target reflects confirmed intent through this commit | target is implemented |
| `PB-Verification: local/domain/global` | breadth of verification actually run | — |
| `PB-Task: PB-014` / `PB-Tasks: PB-1,PB-2` | work on these tasks; completed once their files are gone (unless WIP) | — |
| `PB-Agent: <model id>` | who did the work; boot's RECENT line uses it for the takeover check | — |
| `PB-Plan-Audit: <scope>` / `final` | a plan audit ran; resets boot's audit counter | the plan is perfect |
| `PB-WIP: true` | unverified work preserved for continuity | completion; never with Checkpoint/Verification |
| `PB-Genesis: true` | Brain baseline | — |
| `PB-Decision: ADR-009` | ADR recorded/changed | — |
| `PB-Milestone: <name>` | milestone completed (squash workflows) | — |

The commit body carries `Evidence:` (commands and results). Architecture unchanged but reconciled → still add
`PB-Current-Checkpoint`; do not fake a document edit. `boot`/`changed` treat every commit after the newest
commit whose message mentions `PB-` or `[PB]` as external and map its files to domains through `Sources:`.
Task IDs are permanent; SHAs are not (rebase/squash).

# Validator (`brain.py validate`)

FAIL: no Current file, unknown status, more than one IN_PROGRESS, dependency cycle, `mode: domains` without
`current/`. WARN: legacy schema or `PROJECT_BRAIN.md`, missing config/target, target without `Status:`,
unfilled template placeholders, READY/IN_PROGRESS that is not an executable spec, vague words, invalid
Priority/Tier, notes on the Status line, kept DONE files, missing Acceptance/Verify, BLOCKED without
`Blocked:`, IN_PROGRESS without Areas, READY with an open dependency, dependency neither open nor in Git
history, title/file ID mismatch, missing ADR, tracked `.cache/` files, size budgets (current 200, target
150, constraints 100, task 80 lines; 25 open tasks). It checks structure, not whether the text is true.

# Cache

`.project-brain/.cache/` is gitignored and disposable (repo maps, symbol indexes, scan results). Deleting
it must never lose intent, target, constraints, tasks, or rationale.

# Migration (`brain.py migrate`)

Preview by default; `--apply` writes; nothing is deleted. Lossless rule: a value that cannot fit a header
line is also kept verbatim in Notes as `<Field> (migrated, original): ...`.

| Legacy | Becomes |
|---|---|
| config schema ≤3 (`push_policy`, `tasks`, `verification`) | schema 4; `history_mode`, push and commands kept |
| target without `Status:` | `Status: CONFIRMED` (older targets were approved by definition); `## Objective` → `## Goal` |
| `## Status` / inline `Status:` | `Status:` header; extra text → Notes (or `Blocked:`); missing → PLANNED + note; DONE → reported |
| `## Dependencies`, `## Affected Areas` | `Depends:`, `Areas:` |
| `Risk:` inside Verification | `Risk:` header (highest level named) |
| `Domains:` inside Architecture Impact | `Domains:`; other impact text → Notes |
| `## Acceptance Criteria` bullets | `## Acceptance` checkboxes |
| `## Decision Boundary` | `## Escalate if` |
| other sections (Resume, Discoveries, Blocker...) | kept verbatim |
| `PROJECT_BRAIN.md` §1 GOAL, §2 TARGET | target.md Goal / Target State; header `Goal status` → `Status` |
| §3 CURRENT, §4 FILE MAP | current.md Domains / Map |
| §5 open tasks `[ ]` `[~]` `[!]` | `PB-<same number>`; Where/Do → Steps, Done when → Acceptance + Verify, Needs → Depends, `[L/M/H]` → Tier, section → `Milestone:` note; open sub-tasks → parent Steps |
| §5 closed `[x]` `[-]` | not migrated (Git keeps them) |
| §6 DECISION LOG, §7 HANDOFF | `decisions/ADR-000.md`; handoff → Resume of the IN_PROGRESS task |
| custom §0 / extra sections | constraints.md "(review)" sections |

After `--apply`: follow the printed TODO lines, then SKILL.md §11.
