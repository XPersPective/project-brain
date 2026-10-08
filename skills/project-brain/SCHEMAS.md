# Project Brain — Schemas (schema 4)

`brain.py init` and `brain.py new` write these templates; `brain.py migrate` converts older ones. Read this
file to change a format, interpret a trailer, or understand a migration.

# config.yaml

Stable policy only — never HEAD, active task, timestamps, model, or test results.

```yaml
schema_version: 4
architecture:
  mode: single          # domains: current/<d>.md, optional target/<d>.md; target.md always holds Goal/Status
git:
  history_mode: unknown # preserve | squash | rewrite-prone | unknown
  commit: auto          # auto | ask
  push: manual          # every-task | milestone | session-end | manual
commands:
  test: "python -m pytest -q"
  lint: "ruff check ."
  build: ""
```

The parser supports top-level scalars and sections with two-space `key: value` entries. Double quotes
use JSON string escapes; single quotes escape an apostrophe as `''`; bare values support whitespace
followed by `#` comments. Quoted `#` is literal. Lists, block scalars, deeper nesting, duplicate keys and
future schema versions are rejected with exit 2; convert them explicitly rather than losing values.

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
  Keep an optional current.md Map for shared context. Global target.md remains required; target/<domain>.md
  files hold additional detail. Boot loads global intent even with an active task.

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
| `Status` | PLANNED → READY → IN_PROGRESS → DONE with Evidence → deleted after its checkpoint; any → BLOCKED → READY |
| `Priority` | P1 user's current ask or blocker · P2 normal (default) · P3 later. FOCUS = best priority, then lowest ID |
| `Tier` | L mechanical, fully specified · M normal engineering · H design, ambiguity, security, specs |
| `Risk` | LOW / MEDIUM / HIGH (sets verification breadth) |
| `Depends` | task IDs, `-` when none. Requires verified Git completion or retained DONE+Evidence; absence alone is insufficient |
| `Areas` | backticked globs; boot detects overlap, not ownership; inspect actual edits before resuming |
| `Domains` | Current domains this task may change; boot loads only those sections |
| `Blocked` | only when BLOCKED: what is needed, from whom |

**READY means executable spec**: `## Steps` (numbered, exact paths/symbols/commands), `## Acceptance` with
`- [ ]` checkboxes, `## Verify` with a backticked command, no vague words. Otherwise PLANNED.
Optional `## Resume` (when stopping mid-task): `Next:`, `Failing:`, `Dirty:` lines. Boot prints `Next:`
and the unchecked Acceptance items.
`new` always creates PLANNED scaffolding. DONE requires a nonempty `## Evidence` with actual commands
and results. Keep it until that content is committed, or indefinitely in No Git mode. Cleanup after
the successful work commit is included in the next authorized commit; Git retains the full task spec.
DONE without Evidence remains unfinished in the plan and cannot satisfy a dependency.

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
| `PB-Task: PB-014` / `PB-Tasks: PB-1,PB-2` | task work; completion also needs Verification and either deletion or DONE+Evidence in that commit | task mention alone proves completion |
| `PB-Agent: <model id>` | who did the work; boot's RECENT line uses it for the takeover check | — |
| `PB-Plan-Audit: <scope>` / `final` | a plan audit ran; resets boot's audit counter | the plan is perfect |
| `PB-WIP: true` | unverified work preserved for continuity | completion; never with Checkpoint/Verification |
| `PB-Genesis: true` | Brain baseline | — |
| `PB-Decision: ADR-009` | ADR recorded/changed | — |
| `PB-Milestone: <name>` | milestone completed (squash workflows) | — |

The commit body carries `Evidence:` (commands and results). Architecture unchanged but reconciled → still add
`PB-Current-Checkpoint`; do not fake a document edit. `boot`/`changed` compare each domain against its newest
non-WIP checkpoint, including `all`, using `Sources:`. Unmapped files use the last `all` checkpoint.
Without checkpoints, the last commit editing Current is a legacy fallback. A PB mention or a checkpoint
for another domain does not establish freshness. IDs are reserved by task files, reachable Git task paths
and trailers, and the v0 migration backup; unreachable/shallow history cannot guarantee global uniqueness.

# Validator (`brain.py validate`)

FAIL: unsupported configuration, no Current file, unknown status, duplicate task IDs, more than one IN_PROGRESS, dependency cycle, `mode: domains` without
`current/`. WARN: legacy schema or `PROJECT_BRAIN.md`, missing config/target, target without `Status:`,
unfilled template placeholders, READY/IN_PROGRESS that is not an executable spec, vague words, invalid
Priority/Tier/Risk, notes on the Status line, DONE without Evidence, missing Acceptance/Verify, BLOCKED without
`Blocked:`, IN_PROGRESS without Areas, READY with an open dependency, dependency without completion
evidence, title/file ID mismatch, missing ADR, tracked `.cache/` files, size budgets (current 200, target
150, constraints 100, task 80 lines; 25 open tasks). It checks structure, not whether the text is true.

# Cache

`.project-brain/.cache/` is gitignored and disposable (repo maps, symbol indexes, scan results). Deleting
it must never lose intent, target, constraints, tasks, or rationale.

# Migration (`brain.py migrate`)

Preview by default; `--apply` writes; nothing is deleted. Original inputs are copied to
`.project-brain/migration-backup/` before updates; retries never overwrite those copies. Config is
finalized last with a file replacement so interrupted migration remains retryable. Uninterpreted
content stays in the backup for review; a converted field that cannot fit a header also stays in Notes.

| Legacy | Becomes |
|---|---|
| config schema ≤3 (`push_policy`, `tasks`, `verification`) | schema 4; supported scalar fields, empty/custom commands and policy kept; original comments in backup |
| target without `Status:` | `Status: DRAFT` (approval must be established); `## Objective` → `## Goal` |
| task `Priority:` / `Tier:` | retained, including on interrupted migration retries |
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
| §5 closed `[x]` `[-]` | original retained in migration-backup/PROJECT_BRAIN.md; IDs remain reserved |
| §6 DECISION LOG, §7 HANDOFF | `decisions/ADR-000.md`; handoff → Resume of the IN_PROGRESS task |
| custom §0 / extra sections | constraints.md "(review)" sections |

After `--apply`: follow the printed TODO lines, then SKILL.md §11.
