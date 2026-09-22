# Project Brain — Schemas and Templates

Use these formats as defaults. Adapt only when repository requirements
justify it.

# 1. config.yaml

```yaml
schema_version: 3

architecture:
  mode: single
  # single    → current.md and target.md as single files
  # domains   → current/ and target/ as directories with domain files

git:
  history_mode: unknown
  # preserve       → normal commits remain reachable
  # squash         → intermediate commits destroyed on merge
  # rewrite-prone  → SHAs frequently change (aggressive rebase)
  # unknown        → cannot determine workflow

  push_policy: manual
  # every-task   → push after each task completion
  # milestone    → push at milestone boundaries
  # session-end  → push when stopping
  # manual       → do not push automatically

tasks:
  id_prefix: PB
  # all task IDs will be PB-NNN

verification:
  default_risk: medium
  # low | medium | high
  # determines default verification scope for new tasks
```

**config.yaml is stable configuration, not runtime state.**

Do not store here: current HEAD, active task, last commit SHA,
last session timestamp, current model, temporary verification results.

Derive runtime state from Git + task files.

# 2. current.md (single mode)

```markdown
# Current Architecture

## Scope

Repository-wide current architecture.

## Runtime

<verified runtime structure: language, framework, entry points>

## Domains

### <Domain Name>

**Status:** VERIFIED | OBSERVED | INFERRED | STALE | UNKNOWN

**Sources:**
- `src/<domain>/**`
- `tests/<domain>/**`

<describe present implementation: components, data flow, boundaries>

## External Dependencies

<architecture-relevant dependencies only>

## Known Unknowns

<only unknowns that could materially affect active/future work>
```

Do not include commit SHAs inside the file. The Git commit/trailer is
the checkpoint.

# 3. Domain Current File (domains mode)

For large repositories using `architecture.mode: domains`:

```markdown
# Current Architecture — <Domain Name>

## Status

VERIFIED | OBSERVED | INFERRED | STALE | UNKNOWN

## Source Areas

- `src/<domain>/**`
- `tests/<domain>/**`

## Boundaries

<interfaces and ownership>

## Data Flow

<current behavior>

## Persistence

<current state>

## External Contracts

<relevant public/internal contracts>

## Known Unknowns

<only material unknowns>
```

# 4. target.md

```markdown
# Target Architecture

## Objective

<approved desired outcome — what success looks like>

## Target State

### <Domain Name>

<intended end state for this domain>

## Explicit Non-Goals

<boundaries — what will NOT be built>

## Open Target Decisions

### TD-001

**Status:** OPEN | RESOLVED | DEFERRED

<unresolved decision — do not invent an answer>

## Success Conditions

<observable conditions showing the target has been reached>
```

Target encodes approved intent, not speculative implementation details.

# 5. constraints.md

```markdown
# Project Constraints

## User Requirements

### C-001: <title>

<explicit durable user requirement that changes decisions>

## Compatibility

### C-010: <title>

<required compatibility — versions, APIs, formats>

## Security

### C-020: <title>

<security invariant — authentication, authorization, data handling>

## Operations

### C-030: <title>

<deployment/runtime restriction>

## Development

### C-040: <title>

<meaningful repository-specific development constraint>
```

**A constraint must change decisions.** Avoid generic statements
like "write good code" or "follow best practices."

# 6. Task File

Filename: `.project-brain/tasks/PB-NNN.md`

```markdown
# PB-014 — <Task Title>

## Status

READY

## Objective

<what this task achieves>

## Dependencies

- PB-012
- PB-013

(Use "None" when empty)

## Affected Areas

- `src/auth/**`
- `tests/auth/**`

## Acceptance Criteria

- <observable condition 1>
- <observable condition 2>

## Verification

Risk: LOW | MEDIUM | HIGH

Required:
- <specific checks to run>
- <specific tests to pass>

## Architecture Impact

Expected: YES | NO

Domains:
- <affected domain names>

## Decision Boundary

User decision required if implementation requires:
- <material change 1>
- <material change 2>

## Discoveries

<only discoveries relevant while this task is unfinished>

## Resume

(Use only when task is IN_PROGRESS and interrupted)

Verified:
- <what is confirmed working>

Incomplete:
- <what remains to be done>

Known failures:
- <what is currently broken>

Dirty areas:
- <files with uncommitted changes>

Next action:
- <the exact next safe step>
```

**Task status values:**

| Status | Meaning | Transitions to |
|---|---|---|
| `PLANNED` | Dependencies not satisfied or details not refined | READY, BLOCKED |
| `READY` | Dependencies satisfied, can be started | IN_PROGRESS, BLOCKED |
| `IN_PROGRESS` | Actively being worked on | (completed → file deleted), BLOCKED |
| `BLOCKED` | Concrete external blocker | READY (when unblocked) |

Do not use `BLOCKED` merely because implementation is difficult.

# 7. Blocked Task Addition

When a task becomes blocked, add after the Status section:

```markdown
## Status

BLOCKED

## Blocker

<concrete blocker description>

## Needed Resolution

<exact missing decision/access/dependency>

## Safe Work Remaining

<whether any non-blocked portion may continue>
```

# 8. ADR (Architecture Decision Record)

Filename: `.project-brain/decisions/ADR-NNN.md`

```markdown
# ADR-007 — <Decision Title>

## Status

Accepted

## Context

<material problem that required a durable decision>

## Decision

<selected choice>

## Rationale

<why this choice was made — be explicit, not terse>

## Alternatives

<only serious alternatives considered>

## Consequences

<meaningful tradeoffs>

## Related

Tasks: PB-014, PB-015
Architecture: <affected domains>
Constraints: C-020
```

**ADR status values:** Proposed, Accepted, Superseded, Rejected

Use ADRs only when future agents would otherwise re-open or
misunderstand the decision.

# 9. Commit Trailers

## Genesis Commit

```text
Subject: chore(brain): establish project baseline

PB-Genesis: true
PB-Current-Checkpoint: all
PB-Target-Checkpoint: all
```

For domain architecture:

```text
PB-Current-Checkpoint: auth,database,api
PB-Target-Checkpoint: auth,api
```

Do not claim a domain checkpoint that was not sufficiently inspected.

## Normal Task Completion

```text
Subject: feat(auth): extract session lifecycle [PB-014]

PB-Task: PB-014
PB-Verification: domain
PB-Current-Checkpoint: auth
```

Optional:

```text
PB-Target-Checkpoint: auth
PB-Risk: high
```

## Multiple Tasks (Squash/Milestone)

When task-level commits will not survive:

```text
Subject: feat(auth): complete session architecture migration

PB-Tasks: PB-014,PB-015,PB-016
PB-Verification: global
PB-Current-Checkpoint: auth
PB-Target-Checkpoint: auth
PB-Milestone: auth-session-migration
```

Prefer `PB-Tasks` (plural) over repeated `PB-Task` trailers.

## Architecture-Unchanged Task

When current.md did not change but was reconciled:

```text
PB-Task: PB-021
PB-Verification: local
PB-Current-Checkpoint: auth
```

This advances the checkpoint without meaningless document edits.

## Target Change

```text
Subject: docs(brain): revise approved authentication target

PB-Target-Checkpoint: auth
PB-Decision: ADR-009
```

## WIP Preservation

```text
Subject: wip(brain): preserve partial PB-014 state

PB-Task: PB-014
PB-WIP: true
```

**WIP rules:**
- MUST include `PB-WIP: true`
- MUST NOT include `PB-Current-Checkpoint` (unless genuinely reconciled)
- MUST NOT include `PB-Verification` (unless verification actually ran)
- MUST NOT represent WIP as completed work

# 10. Trailer Semantics

## PB-Current-Checkpoint

```text
PB-Current-Checkpoint: auth
```

Means: the Project Brain representation of the auth domain was
reconciled with repository reality through this commit.

Does NOT mean: architecture changed, every test passed, no bugs exist,
every file was inspected.

Verification strength is separately represented by `PB-Verification`.

## PB-Target-Checkpoint

```text
PB-Target-Checkpoint: auth
```

Means: the checked-in Target Architecture for auth reflects approved
intent through this commit.

Does NOT mean: the target has been implemented.

## PB-Verification

```text
PB-Verification: local | domain | global
```

Declares the breadth of verification performed:
- `local` → affected files only
- `domain` → related integration scope
- `global` → broad regression suite

## PB-WIP

```text
PB-WIP: true
```

Declares this commit preserves unverified work for continuity.
This is not completion evidence.

## Task Completion

A task is considered durably completed when the reachable Git
history contains a non-WIP checkpoint representing its verified
semantic completion:

```text
PB-Task: PB-014           (single task)
PB-Tasks: PB-014,PB-015   (squash/milestone)
```

Do not maintain a duplicate completed-task registry.

# 11. Validation Invariants

A validator should detect at least:

```text
Structural:
  - duplicate task IDs
  - dependency cycles
  - dangling dependency references
  - unknown task status values
  - missing required task fields (objective, acceptance criteria, verification)
  - READY task with unresolved dependency
  - multiple IN_PROGRESS tasks

Referential:
  - task references nonexistent ADR
  - ADR references nonexistent task
  - constraint referenced but not defined
  - target references impossible/missing domain

Consistency:
  - current domain file with invalid source mapping
  - completed task files unnecessarily retained
  - malformed config.yaml
  - tracked files in .cache/ when prohibited
  - config.yaml references domain mode but no domain directory exists

Git:
  - WIP commit with completion trailers
  - checkpoint trailer for unreconciled domain
```

A validator must not pretend to prove semantic architecture correctness
from syntax alone.

# 12. Minimalism Test

Before persisting new Project Brain information, ask:

```text
1. Can Git answer this cheaply?
2. Can code inspection answer this cheaply?
3. Will this still matter after the active task finishes?
4. Would losing this cause a future agent to make a
   materially worse decision?
```

If answers 1 or 2 are yes and reconstruction is cheap → do not persist.

If answer 4 is no → do not persist.

Project Brain should contain high-value semantics, not exhaust.

# 13. Cache Rules

`.project-brain/.cache/` may store:

```text
repository map
path-to-domain map
detected test commands
dependency graph from manifests
symbol index
last expensive scan result
```

Cache must be disposable. Deleting cache must never destroy:

```text
user intent
target
constraints
unfinished tasks
decision rationale
durable history
```

Cache should be in `.gitignore`.
