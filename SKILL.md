---
name: project-brain
version: 1.0.0
license: MIT
description: >-
  Git-native persistent project cognition and execution protocol for coding
  agents. Use for substantial repository work that may span tasks, sessions,
  models, handoffs, branches, or interruptions; when adopting an existing
  project mid-development; when maintaining current/target architecture;
  or when reliable resume, verification, checkpointing, and context
  minimization are important.
---

# Project Brain

Git-native execution and continuity protocol for coding agents.

Project Brain preserves the information Git and source code cannot cheaply
preserve: current architectural understanding, approved target architecture,
user intent and constraints, unresolved decisions, active and future work,
and enough structure to resume safely.

```text
repository reality       (implementation truth)
+ Git history            (durable execution history)
+ Project Brain          (semantic layer over them)
+ verification evidence
= reliable next action
```

Do not create a second history database when Git already contains the history.

# 1. Autonomy Contract

The user is usually away. Follow these rules without exception.

**Never ask the user anything.** Instead:

- Ambiguity → pick the most conservative reasonable option, record it
  as a decision in the appropriate ADR or task, continue.
- Needs a human (credentials, payment, legal/product decision,
  destructive/irreversible action: force-push, dropping data, prod deploy,
  deleting user files) → mark task BLOCKED with the reason, move to the
  next unblocked task.

**Never stop early.** After completing a task:

- immediately select the next executable task and continue.
- never stop to report after a task.
- never ask "shall I continue?"
- stop only when: all tasks are complete with verification passed,
  or every remaining task is BLOCKED.

**Before any stop:** update the active task's resume notes (if interrupted),
commit, push if policy allows.

**Context or session ending:** reach the next safe point — complete or
checkpoint the current task, commit, continue or stop cleanly.

**One session per project assumed.** If evidence shows another agent
committed since the last checkpoint, reconcile first (§14), never overwrite
their work.

# 2. Core Memory Model

```text
GROUND TRUTH     repository + Git
HOT MEMORY       current architecture + target + constraints + active task
WARM MEMORY      future tasks + unresolved decisions
COLD MEMORY      Git history + old versions of Brain files
```

## Store by reconstruction cost

```text
Git can answer it cheaply             → do not duplicate it
Repository inspection can answer it   → do not persist it
  cheaply
Inspection can answer it but at       → cache or summarize it
  substantial cost (>5 files or
  >500 lines to read)
Human intent, rationale, or an        → preserve it
  unresolved decision
Active execution state                → keep it hot
Execution complete                    → let Git own the history
```

# 3. Default Layout

```text
.project-brain/
├── config.yaml          # stable configuration, not runtime state
├── current.md           # verified present architecture (what exists)
│   OR current/          # domain-split for large repos
│       ├── auth.md
│       └── billing.md
├── target.md            # approved intended architecture (where we go)
│   OR target/           # domain-split for large repos
│       └── auth.md
├── constraints.md       # durable invariants and requirements
├── tasks/
│   └── PB-*.md          # only unfinished work
├── decisions/
│   └── ADR-*.md         # rationale Git cannot cheaply preserve
└── .cache/              # reconstructable, gitignored
```

Split by domain only when it materially reduces context/reconciliation cost.

`.project-brain/.cache/` must be gitignored and contain only reconstructable
information.

# 4. What Each File Means

| File | Contains | Does NOT contain |
|---|---|---|
| `config.yaml` | Stable PB configuration, repository policy | Runtime state, current HEAD, active task, session info |
| `current.md` | Verified present architecture | Plans, assumptions presented as fact, desired state |
| `target.md` | Approved intended architecture | Implementation details, speculative designs |
| `constraints.md` | Durable invariants, compatibility, security, user requirements | Generic boilerplate ("write good code") |
| `tasks/PB-*.md` | Unfinished operationally relevant work | Completed tasks (Git preserves those) |
| `decisions/ADR-*.md` | Rationale not reconstructable from code/diff | Trivial implementation choices |

# 5. Boot Sequence

Every session begins here. Run these steps in order:

## Step 1: Observe repository state

Determine:

```text
repository root           → git rev-parse --show-toplevel
Git availability          → git status (if fails: NO_GIT mode)
branch / detached HEAD    → git symbolic-ref HEAD
HEAD                      → git rev-parse --short HEAD
working-tree status       → git status --porcelain
merge/rebase state        → .git/MERGE_HEAD, .git/rebase-merge/
Project Brain presence    → .project-brain/ directory exists?
repository instructions   → AGENTS.md, GEMINI.md, etc.
```

## Step 2: Classify session

| Classification | Condition | Action |
|---|---|---|
| `GENESIS` | No `.project-brain/` directory | → §10 Genesis |
| `CLEAN_RESUME` | Clean tree, HEAD == last checkpoint, Brain valid | → §16 Clean Resume |
| `HEAD_ADVANCED` | Commits exist after last checkpoint | → §17 HEAD Advanced |
| `DIRTY_RESUME` | Uncommitted changes exist | → §18 Dirty Resume |
| `INTERRUPTED` | Task has IN_PROGRESS status | → §19 Interrupted Work |
| `BRANCH_CHANGED` | Branch differs from expected | → Read REFERENCE.md §7 |
| `HISTORY_REWRITTEN` | Stored SHAs not reachable | → Read REFERENCE.md §10 |
| `CONFLICTED` | Active merge/rebase/cherry-pick | → Read REFERENCE.md §9 |
| `DEGRADED_HISTORY` | Shallow clone or sparse checkout | → Read REFERENCE.md §12-13 |
| `BRAIN_INVALID` | Brain files exist but are corrupt | → Read REFERENCE.md §22 |
| `NO_GIT` | Git unavailable | → Read REFERENCE.md §21 |

**If multiple conditions apply:** prioritize CONFLICTED > DIRTY_RESUME >
INTERRUPTED > HEAD_ADVANCED > BRANCH_CHANGED > CLEAN_RESUME.

**After classification is resolved:** proceed to the Task Execution Loop (§23).

## Step 3: Fast path for trivial requests

If the user's request is a single small change (typo fix, one-line edit,
simple rename) AND a valid Project Brain already exists:

1. perform the change,
2. verify it,
3. update affected Brain files if architecture changed,
4. checkpoint,
5. done.

Do not create a task file for work that takes less than 2 minutes.

# 6. Instruction Precedence

```text
latest explicit user instruction
  >
explicitly approved decisions (ADRs)
  >
task acceptance criteria
  >
target architecture
  >
constraints and repository conventions
  >
existing plan
  >
historical assumptions
```

When user intent changes, reconcile Project Brain instead of continuing an
obsolete plan.

SKILL.md rules override REFERENCE.md if they conflict. REFERENCE.md provides
additional detail for edge cases.

# 7. Current Architecture Rules

Current Architecture must contain verified present reality.

**Never place in Current Architecture as fact:**
- planned changes
- partially implemented design presented as complete
- assumptions
- desired architecture
- claims inherited from another agent without verification

**Epistemic markers** (use only when uncertainty is material):

| Marker | Meaning | Use when |
|---|---|---|
| `VERIFIED` | Confirmed by code inspection | Default for genesis, task completion |
| `OBSERVED` | Seen in code but not deeply inspected | Quick scan, not full audit |
| `INFERRED` | Derived from indirect evidence | Logs, config, naming patterns |
| `STALE` | Was verified but code may have changed | Checkpoint is old |
| `UNKNOWN` | Not yet investigated | Domain not mapped |

`ASSUMED` is not a valid marker for Current Architecture. If you must assume,
use a task to verify.

# 8. Target Architecture Rules

Target Architecture represents approved intent. Do not silently alter it
because implementation becomes inconvenient.

When implementation reveals a conflict:

```text
DISCOVERY → IMPACT → OPTIONS → AUTHORITY CHECK → DECISION
```

If the choice changes user intent, public behavior, security semantics,
infrastructure, persistence semantics, or another material contract:
obtain user direction (mark task BLOCKED) unless already delegated.

Target changes only when:
- the user changes intent
- the user approves a discovered alternative
- an already-delegated decision legitimately refines the target

# 9. Constraints

Constraints represent things that must survive implementation:
public API compatibility, migration reversibility, deployment restrictions,
supported runtimes, security boundaries, user-provided nonfunctional
requirements.

**A constraint must change decisions.** Do not add generic boilerplate.
Do not silently violate a constraint.

# 10. Genesis: New Project Brain

When `.project-brain/` does not exist:

```text
Step 1: existing repository
Step 2: → structural map (key directories, entry points, dependencies)
Step 3: → targeted inspection (read important files, not everything)
Step 4: → current architecture (from code evidence, not docs/wishes)
Step 5: → user intent (from user message, README, issues, recent history)
Step 6: → target architecture (approved desired state)
Step 7: → constraints (from user, existing configs, conventions)
Step 8: → gap analysis (target − current)
Step 9: → task graph (from gap, ordered by dependency)
Step 10: → create all Brain files
Step 11: → genesis checkpoint
```

**Do not:**
- reconstruct imaginary history for pre-genesis work
- invent target decisions the user hasn't approved
- absorb unexplained dirty changes into the genesis commit

**If target is incomplete:** record known objectives, mark unknowns
explicitly, create only tasks justified by known intent. `UNKNOWN` is
preferable to fabricated architecture.

**If repository is dirty:** classify each dirty path's ownership
(user work / generated / unknown). If Brain files can be committed
independently, do so. Otherwise leave genesis pending.

**Genesis commit:**

```text
Subject: chore(brain): establish project baseline
Trailers:
  PB-Genesis: true
  PB-Current-Checkpoint: <scope>   (all | comma-separated domains)
  PB-Target-Checkpoint: <scope>
```

**After genesis:** immediately proceed to the Task Execution Loop (§23).

# 11. Respect Existing Repository Instructions

Before substantial work, identify applicable instructions:
AGENTS.md, nested AGENTS.md, contribution guides, test/build instructions.

Project Brain supplements existing instructions; it does not replace them.

# 12. Architecture Source Mapping

Where useful, architecture documents should identify source areas:

```text
Auth sources:
  - src/auth/**
  - src/middleware/**
  - tests/auth/**
```

When changed paths intersect those sources, mark the domain potentially
stale and inspect it. Source mapping is an optimization, not absolute proof.

# 13. Finding the Last Checkpoint

Preferred: find the latest reachable commit with trailer:

```text
git log --grep="PB-Current-Checkpoint" --format="%H %s" -1
```

For a specific domain:

```text
git log --grep="PB-Current-Checkpoint: auth" --format="%H %s" -1
```

**Fallback** (no trailers exist): find the latest commit touching the
relevant `current` architecture file.

A checkpoint means: the declared Current Architecture was reconciled
against repository reality through this commit for the declared scope.

# 14. Reconciliation

When HEAD is newer than the last checkpoint:

```text
checkpoint → Git delta (changed paths) → affected domains
  → targeted inspection → architecture reconciliation
  → task reconciliation
```

Do not reread the whole repository. Use changed paths to determine
what may have become stale. Unrelated changes leave unaffected
architecture trusted.

# 15. Never Use Brain as Higher Authority Than the Repository

If Brain conflicts with code:

1. inspect the relevant repository state
2. determine whether Brain is stale or code is incomplete
3. reconcile the discrepancy
4. update affected plans
5. continue only from reconciled state

Never modify working code merely to make it agree with stale documentation.

# 16. Clean Resume

Conditions: clean working tree, HEAD == latest trusted checkpoint,
no unfinished conflict operation, Brain valid.

Action:
1. trust unaffected verified state
2. identify next executable task
3. load only relevant context
4. proceed to Task Execution Loop (§23)

Do not perform a full project audit.

# 17. HEAD Advanced

Commits exist after the last trusted checkpoint:

1. inspect commit range and changed paths
2. determine whether changes are PB-managed or external
3. invalidate only affected knowledge
4. inspect affected architecture and constraints
5. adjust unfinished tasks if needed
6. establish new checkpoint when reconciliation completes
7. proceed to Task Execution Loop (§23)

External commits are not automatically incorrect. They simply require
reconciliation.

# 18. Dirty Resume

Never assume dirty files belong to the active task.

1. Run `git status`, inspect relevant diffs
2. Classify each dirty path: active PB work / user work /
   another agent's work / generated output / unknown
3. Do not automatically reset, clean, checkout, restore, stash,
   amend, or rebase
4. If safe non-overlapping work can continue, continue
5. If proceeding could destroy unknown work, stop at the boundary
   and mark task BLOCKED

# 19. Interrupted Work

An unfinished IN_PROGRESS task must have resume notes:

```text
Verified:      what is confirmed working
Incomplete:    what remains to be done
Known failures: what is currently broken
Dirty areas:   files with uncommitted changes
Next action:   the exact next safe step
```

On resume: verify actual repository state before trusting the handoff.
Resume from the first unverified point.

# 20. Task Model

Tasks are executable units, not diary entries. Each task defines:

```text
ID:                  PB-NNN
Objective:           what this task achieves
Status:              PLANNED | READY | IN_PROGRESS | BLOCKED
Dependencies:        list of PB-IDs or None
Affected areas:      source paths
Acceptance criteria: observable conditions for completion
Verification:        risk level (LOW | MEDIUM | HIGH) + required checks
Architecture impact: YES/NO + affected domains
Decision boundary:   what requires user direction
Resume notes:        only when interrupted
```

**Status rules:**
- `PLANNED` → dependencies not yet satisfied or details not refined
- `READY` → dependencies satisfied, can be started
- `IN_PROGRESS` → actively being worked on (only one at a time)
- `BLOCKED` → concrete external blocker (not "difficult")

Completed tasks are deleted from `tasks/`. Git preserves their history.

# 21. Selecting Work

A task is executable when:
- dependencies are satisfied
- required decisions exist
- required assumptions are sufficiently validated
- execution does not knowingly violate constraints

Prefer work that:
- advances the approved objective
- produces a coherent checkpoint
- avoids unnecessary parallel partial state

Do not choose tasks purely by number.

# 22. Progressive Planning

Plan globally, specify locally. Distant tasks may remain coarse.
Before execution, refine the selected task with concrete:
objective, acceptance criteria, affected areas, verification, decision
boundaries.

Do not pretend to know distant implementation details that depend on
unfinished work.

# 23. Task Execution Loop

This is the core work cycle. Repeat until all tasks are complete or
BLOCKED:

```text
SELECT task
  → LOAD minimal context (§24)
  → VALIDATE assumptions
     ├─ assumptions invalid → RECONCILE (§14), update task, restart loop
     └─ assumptions valid ↓
  → IMPLEMENT
  → VERIFY (§26)
     ├─ verification fails → FIX implementation, re-verify
     │   (max 3 attempts, then mark BLOCKED with failure details)
     └─ verification passes ↓
  → REVIEW DIFF (§28)
     ├─ issues found → FIX, re-verify
     └─ clean ↓
  → CHECK CONSTRAINTS
     ├─ violation → FIX or escalate (mark BLOCKED if user decision needed)
     └─ satisfied ↓
  → RECONCILE architecture (§29)
  → CHECKPOINT (§35)
  → DELETE completed task file
  → SELECT next task (loop continues)
```

**When no executable task remains:**
- All tasks complete → Final reconciliation (§31)
- Only BLOCKED tasks remain → record blockers, commit, stop

**Loop invariant:** never proceed past VERIFY with known failures.
Never skip REVIEW DIFF because implementation "looks correct."

# 24. Minimal Context Rule

For the active task, load only:

- the task file
- relevant Current sections
- relevant Target sections
- relevant constraints
- relevant ADRs
- directly affected source
- relevant tests
- recent relevant Git history (only when needed)

Do not load: every old task, full Git history, every ADR,
all architecture domains, historical Brain versions.

Retrieve history on demand.

# 25. Recent History

When recent completed work is useful, derive it from Git:

```text
git log --grep="PB-Task" -5 --format="%h %s"
```

Do not maintain a duplicate completed-task list.

# 26. Verification

A task is not complete because code exists. Completion requires
evidence that acceptance criteria hold.

**Risk-proportional verification:**

| Risk | Scope | When |
|---|---|---|
| LOW | Local: affected files compile/lint, targeted tests pass | Localized, low-impact change |
| MEDIUM | Domain: local + related integration tests | Medium-impact, single-domain change |
| HIGH | Global: domain + broad regression suite | Cross-cutting, security, persistence, public API |

**For projects without automated tests:**
- Use static analysis (lint, typecheck) as minimum verification
- Manual smoke-test descriptions in acceptance criteria
- Create test tasks when verification gaps are found
- Never skip verification — reduce scope, not rigor

# 27. Baseline Failures

Do not assume every failing test was introduced by the active task.

When useful, establish a baseline before changing code.

Classify failures as:
- new regression (task-introduced)
- pre-existing
- environmental
- unrelated discovery
- uncertain

Do not repair unrelated failures without scope justification.
Do not claim successful verification when a relevant new regression
remains unexplained.

# 28. Diff Review Gate

Before checkpointing, inspect the relevant final diff.

Check for:
- unintended scope expansion
- accidental public behavior changes
- weakened/deleted/skipped tests
- debug artifacts (console.log, print, TODO/FIXME)
- secret material
- generated noise
- duplicated logic
- unnecessary dependency changes
- undocumented architecture changes
- accidental user-work modification

Tests do not replace diff review.

# 29. Current Architecture Update

If implementation materially changes architecture:

1. implement
2. verify
3. inspect resulting reality
4. update Current Architecture (from code, not from memory)
5. checkpoint

Do not update Current Architecture before implementation is real.

If architecture did not change but was reconciled, record a checkpoint
trailer without fabricating a document change.

# 30. Target Changes

Target changes are recorded in Git history and, when rationale matters,
an ADR. Do not rewrite history to hide an abandoned target.

When the user changes the goal:
1. update target.md
2. identify tasks now invalid → delete or supersede
3. retain completed work that remains useful
4. create new tasks for the new gap
5. checkpoint

# 31. Final Reconciliation

At milestone or project completion:

1. verify no stale IN_PROGRESS tasks exist
2. verify Current matches repository reality
3. verify Target is achieved or explicitly revised
4. verify constraints hold
5. run appropriate broad verification
6. inspect final relevant Git range
7. ensure checkpoint trailers exist
8. remove obsolete temporary notes
9. checkpoint with appropriate trailers

# 32. Scope Control

Do not opportunistically refactor unrelated code.

When a useful non-blocking issue appears:
- create a future task if within project scope, OR
- record it as a discovery in the active task
- continue current work

Discovery does not automatically expand scope.

# 33. Decision Boundary

Agent may decide normal implementation details consistent with approved
intent.

**Escalate (mark BLOCKED) when a decision materially changes:**
- user intent
- public API
- security semantics
- persistence semantics
- infrastructure
- external compatibility
- major scope
- irreversible behavior

Do not ask the user about trivial implementation choices.
"Trivial" = the decision is reversible and does not affect any item
in the escalation list above.

# 34. Commit Policy

Preferred unit: one verified semantic unit → one checkpoint commit.

Do not commit every keystroke.
Do not combine unrelated semantic work.
Do not include unrelated user modifications.

**Commit message format:**

```text
<type>(<scope>): <summary> [PB-NNN]

<optional body>

PB-Task: PB-NNN
PB-Verification: local | domain | global
PB-Current-Checkpoint: <scope>
```

**Optional trailers:**

```text
PB-Target-Checkpoint: <scope>
PB-Risk: low | medium | high
PB-WIP: true                    (only for unverified preservation)
PB-Genesis: true                (only for genesis commit)
PB-Tasks: PB-014,PB-015         (for multi-task squash commits)
PB-Milestone: <name>            (for milestone completion)
PB-Decision: ADR-NNN            (when an ADR is recorded)
```

See SCHEMAS.md for full trailer semantics.

# 35. Checkpoint

A checkpoint commit marks that Brain state was reconciled with repository
reality. After committing:

1. the task file for completed work is deleted from the working tree
2. Git preserves the task's full history
3. trailers declare what was reconciled

Do not copy completed tasks to a `completed/` directory.
Do not create evidence JSON by default.

Critical rationale not reconstructable from Git belongs in an ADR.

# 36. Push Policy

Follow repository/user policy. Supported modes:

```text
every-task     push after each task completion
milestone      push at milestone boundaries
session-end    push when stopping
manual         do not push automatically
```

Never assume successful commit = successful remote persistence.
Never force-push without explicit user authorization.

# 37. Token Discipline

**Reading:**
- Search (grep/glob) before opening files
- Open specific line ranges of large files
- Never re-read what you just wrote
- Load Brain files progressively: task → relevant current → relevant
  target → relevant constraints → relevant ADRs

**Tool output:**
- Always filter/limit (tail, grep, quiet flags)
- Never pull lockfiles, logs, build output, or generated code into context

**Writing:**
- Terse fragments in Brain files
- `path:symbol` references instead of pasted code
- Each fact in one place

**Exception:** verification evidence, ADR rationale, and task acceptance
criteria are written explicitly, never terse.

# 38. Delegation

When the harness supports sub-agents with model selection:

| Risk | Typical work | Route to |
|---|---|---|
| LOW | Renames, boilerplate, running tests, applying specified edits | Cheapest available model |
| MEDIUM | Normal feature/bug work with clear spec | Mid-tier model or self |
| HIGH | Architecture, ambiguous bugs, security, writing specs | Main session (strongest model) |

**Delegation rules:**
- Delegation prompt must be self-contained: task objective, affected files,
  acceptance criteria, verification command
- Main session owns Brain files: verifies acceptance criteria itself,
  updates Brain, commits
- Sub-agents never modify Brain files directly
- Parallel sub-agents only for tasks touching disjoint files

# 39. Parallel Agents

Project Brain does not implement a distributed lock.
`IN_PROGRESS` means semantic state, not exclusive ownership.

Recommended strategy: one agent → one branch/worktree →
explicitly assigned non-overlapping task/domain.

Before integration: reconcile both deltas, re-evaluate architecture,
rerun appropriate verification.

# 40. Security

Never place secrets, credentials, private keys, tokens, or sensitive
runtime values in Brain files, task files, commit trailers, ADRs,
or Git notes.

Treat authentication/authorization/cryptographic/persistence-boundary
changes as HIGH risk with mandatory escalation check.

# 41. Handoff

If stopping before completion, leave the active task truthful:

```text
what is verified
what is incomplete
what is currently failing
important discoveries
unknowns
safe next action
```

Do not create long narrative session logs. Git records completed history.

# 42. WIP Preservation

When work must survive across environments but is not yet verified:

1. Create a clearly marked WIP commit with `PB-WIP: true` trailer
2. Do NOT add `PB-Current-Checkpoint` or `PB-Verification` trailers
   (unless architecture was genuinely reconciled)
3. Do NOT represent WIP as completed work
4. When later completed, normal completion commits supersede the WIP

Prefer a verified checkpoint whenever possible.

# 43. Compaction

Project Brain should not grow linearly with project age.

As tasks finish:
- task files decrease
- Git history increases
- Current evolves
- Target converges
- ADRs remain only when durable rationale exists

A mature completed project may have very little active Brain state.
That is success.

# 44. Failure Principle

When Project Brain and reality diverge:

```text
do not defend Brain
do not defend the old plan
do not restart blindly

observe → reconcile → replan → continue
```

# 45. Catch-All Recovery

When encountering a situation not covered by this protocol or
REFERENCE.md:

1. Do not proceed with uncertain state
2. Preserve current work (WIP commit if needed)
3. Inspect repository reality (git status, git log, file system)
4. Reconcile Brain state with observed reality
5. Create/update tasks for any discovered gaps
6. Continue from reconciled state

When in doubt: observation over assumption, safety over speed,
preservation over cleanup.

# 46. Read Additional References Only When Needed

Read `REFERENCE.md` for edge cases: dirty repos, shallow/sparse clones,
detached HEAD, rewritten history, squash workflows, merge/rebase conflicts,
worktrees, parallel agents, submodules, CI divergence, WIP recovery,
missing/corrupt Brain, branch changes, external modifications, database
migrations, long-running projects.

Read `SCHEMAS.md` when creating or modifying: config, Current Architecture,
Target Architecture, constraints, tasks, ADRs, commit trailers.

Do not load these files on a simple clean resume.

# Golden Rules

1. Repository reality beats Brain.
2. Git owns completed execution history.
3. Brain preserves semantics Git cannot cheaply preserve.
4. Current means verified present reality — never assumptions.
5. Target means approved intent — never speculative design.
6. Do not invent target decisions.
7. Do not duplicate Git history.
8. Reconcile deltas instead of rediscovering everything.
9. Keep only unfinished work hot.
10. Completed tasks disappear from the active tree.
11. Rationale that cannot be reconstructed belongs in ADRs.
12. Preserve unknown user work.
13. Never use destructive Git operations casually.
14. Verification is required for completion.
15. Review the diff before checkpointing.
16. Commit semantic units, not activity.
17. Task IDs are logical identifiers; commit SHAs are unstable.
18. Never treat branch-local task status as a distributed lock.
19. Leave less active context than you found.
20. When stuck: observe → reconcile → replan → continue.
