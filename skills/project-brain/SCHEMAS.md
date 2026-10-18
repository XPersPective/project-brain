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
Owner:
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
- [ ] [machine] `parse_tr_date("16.09.2026") == date(2026, 9, 16)` (asserted by a test)
- [ ] [machine] invalid inputs raise `ValueError` (test fails if they do not)

## Verify
- `python -m pytest -q tests/test_date.py`

## Escalate if
- the import format turns out to carry times or time zones

## Evidence

## Review

## Notes
- Milestone: import v2
```

Pool-backed `PB start` appends `| strength=<low, medium or high>` before any
takeover reason in its source/contract-bound start record. This records ordinary
non-delegated work too. Reviewer checks use immutable start and dispatch strengths,
never a model's latest global selection. The `pool/<24-hex>` actor namespace retains
exact model identity in the external registry. Incomparable cross-backend review
is refused.

| Header | Values |
|---|---|
| `Status` | `PLANNED → READY → IN_PROGRESS → REVIEW → DONE` with Evidence → deleted after its checkpoint; any → `BLOCKED → READY` |
| `Priority` | `P1` user's current ask or blocker · `P2` normal (default) · `P3` later. FOCUS = best priority, then lowest ID |
| `Tier` | `L` mechanical (`score <= 32`) · `M` normal engineering (`33..64`) · `H` architecture, security, UI foundation (`>= 65`) |
| `Risk` | `LOW` / `MEDIUM` / `HIGH` (sets verification breadth and independent review requirement) |
| `Owner` | model/agent alias set by `PB start` (e.g. `codex/gpt-5.2-codex`); implementers may never review their own task |
| `Depends` | task IDs, `-` when none. Requires verified Git completion or retained DONE+Evidence; absence alone is insufficient |
| `Areas` | backticked globs; `PB check`, `PB evidence`, `PB review`, and `PB accept` hash every public file matched by `Areas` |
| `Domains` | Current domains this task may change; boot loads only those sections |
| `Blocked` | only when BLOCKED: what is needed, from whom |

### Typed Acceptance Items (`KINDS`)
Each Acceptance checkbox may specify an explicit kind tag `- [ ] [<kind>] <observable condition>` (untagged items default to `machine`; UI tasks still require the explicit Triad):
- `machine` — proven by `PB check` running the backticked `Verify` commands (`exit=0` on current `digest` and `contract`).
- `visual` — proven by `PB evidence --kind visual --criterion <id> --file <screenshot.png>` (real rendered viewport).
- `interaction` — proven by `PB evidence --kind interaction --criterion <id> --note "step -> step -> result"` (or trace/recording file).
- `accessibility` — proven by `PB evidence --kind accessibility --criterion <id> --note "..."` (keyboard, focus, platform touch targets, contrast; see QUALITY.md).
- `security` / `integration` / `architecture` — proven by `PB evidence --kind <kind> --criterion <id> --note "..."`.
- `user_feedback` — when all other items pass, `PB accept` sets `Status: BLOCKED` (`WAITING_USER`) with empty `Owner:` until the user confirms.

### Tool-Written `## Evidence` & `## Review` Lines
Never hand-write these sections; `brain.py` writes and verifies them against `areas_digest` (16-hex LF-normalized SHA-256 of `Areas`) and `contract` (16-hex SHA-256 of the task's spec):
- `- start: IN_PROGRESS | owner=<alias> | risk=<RISK> | digest=<hex> | contract=<hex>`
- `- [machine] check \`<cmd>\` | PASS|FAIL | exit=<rc> | <sec>s | by=<alias> | digest=<hex> | contract=<hex> | log=.cache/runs/<file>@<hash>`
- `- [<kind>] <note> | criterion=<id> [| files=<path>@<hash>] | by=<alias> | digest=<hex> | contract=<hex>`
- `- review by <reviewer> | PASS|BLOCKED | digest=<hex> | contract=<hex>`
- `- finding BLOCKER|MAJOR|QUALITY|MINOR: <text> [| accepted: <reason> | owner: user|PB-NNN]`
- `- accept: DONE | digest=<hex> | contract=<hex>`

# ADR — decisions/ADR-NNN.md

Sections: Status (Proposed | Accepted | Superseded | Rejected), Context, Decision, Rationale (explicit),
Alternatives (serious ones only), Consequences, Related (tasks, domains, constraints). For a replan (§8b):
problem, evidence, options, choice, impact on tasks. Write one only when a future agent would otherwise
re-open or misread the decision (always write an ADR for the UI Design System & Token Foundation).

# Commit trailers

| Trailer | Means | Does not mean |
|---|---|---|
| `PB-Current-Checkpoint: auth,api` / `all` | Current for these domains was reconciled with the code through this commit | architecture changed; all tests pass |
| `PB-Target-Checkpoint: auth` | Target reflects confirmed intent through this commit | target is implemented |
| `PB-Verification: local/domain/global` | breadth of verification actually run | — |
| `PB-Task: PB-014` / `PB-Tasks: PB-1,PB-2` | task work; completion also needs Verification and either deletion or DONE+Evidence in that commit | task mention alone proves completion |
| `PB-Agent: <model id>` | who implemented the task; boot's RECENT line uses it for the takeover check | — |
| `PB-Reviewer: <model id>` | independent reviewer who passed `PB review` on MEDIUM/HIGH risk tasks | — |
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
unfilled template placeholders, READY/IN_PROGRESS/REVIEW that is not an executable spec, vague words, invalid
Priority/Tier/Risk, unknown Acceptance kind tags, UI task missing `[visual]`/`[interaction]`/`[accessibility]`, notes on the Status line, DONE without Evidence, missing Acceptance/Verify, BLOCKED without
`Blocked:`, IN_PROGRESS/REVIEW without Areas, READY with an open dependency, dependency without completion
evidence, title/file ID mismatch, missing ADR, tracked `.cache/` files, size budgets (current 200, target
150, constraints 100, task 80 lines; 25 open tasks). It checks structure, not whether the text is true.

# Cache & Agent Registry

- `.project-brain/.cache/` is gitignored and disposable (`runs/*.log` check/delegation logs, `writer.lock`). Deleting it must never lose intent, target, constraints, tasks, or rationale.
- `~/.project-brain/agents.json` stores machine-local CLI agent paths, benchmark scores, and live subscription quota pools (`PB agents scan|quota|list|select|merge`).
- The wire format remains schema 4 in v3.0.0; the earlier design's proposed schema 5 was not implemented. `WAITING_USER` is BLOCKED with a reason; `READBACK_FIRST` is a boot result, and failed reviews are handled through REVIEW/start, not extra persisted task statuses.
- v3.1 also retains project schema 4. Machine-local `sessions/<project-hash>.json`
  beside the registry uses its own schema 1: PROPOSED/APPROVED/REVOKED, project/session
  ID, sanitized inventory, configuration digest, explicit selection/approval note and
  reserved/running/response_unknown/completed/failed jobs. It never lives in config.yaml.
  Known quota snapshots expire after 5 minutes; an approved max_jobs cap is required for
  unknown/stale quota. Attempts remain counted after completion or readback settlement.
  New proposals cannot discard unsettled jobs. `default` effort means no effort selector.
- IDs and hashes provide freshness/integrity checks, not signatures or authenticated identities. A trusted agent must observe evidence, and actual user approval is needed for a user-owned waiver.

# Migration (`brain.py migrate`)

Foreign adoption uses `legacy --apply` for supported task extraction, followed by
semantic reconciliation and `legacy --prepare [--path <tracker>]`. Its schema-1
`adoption.json` has roots, per-file source hashes and targets/drop reasons, exact
instruction removals, verification snapshots and archive/journal state. Destinations
must be useful public files outside removed roots; Brain tasks/current/target/ADRs
are allowed, cache/trace/legacy backups are not completion targets. `legacy --verify
--note "<review>"` validates the plan and binds mappings. `legacy --cleanup
[--archive-dir <outside-project>]` verifies the archive before deletion and supports
crash retry. This explicit trace supports unfamiliar trackers without pretending the
parser can semantically understand every vendor format. Unresolved external operations
must survive in mapped targets and cannot simply be dropped.

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
