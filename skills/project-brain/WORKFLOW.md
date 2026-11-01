# Project Brain execution reference

Load the relevant section when specifying, verifying, reviewing or closing work.
Authority and session rules remain in SKILL.md.

## 3. Intake and task contracts

Questions stay read-only. A trivial ≤1-file/≤20-line change with no behavior/API/
architecture change needs only a relevant check and authorized checkpoint. New
non-trivial work: `PB new . "title" --priority P1` per verifiable piece. Continue
requests work the queue; new input steers the active task unless it replaces it.
Record new requirements before losing Next/Failing/Dirty context.
Split a multipart message into complete concise items and record
`PB intake --item "..." --item "..." --relation related|question|new-work|cancel`.
The durable requests.json ledger retains every item and the active resume task.
Link directives with `intake --resolve RQ-NNN --task PB-NNN`; resolve answered
questions without a task link. Never silently drop an item. Questions do not replace
the active task: answer briefly, then resume its saved Next. Queue unrelated work
unless the user changes priority; only explicit cancellation stops the objective.
After setup, `PB security --ref none|<alias> --note "<user decision>"` records the
project secret choice without values or personal paths. Missing credential access
blocks only secret-dependent checks; continue fixture-based implementation.

Write a ≤80-line task for a zero-history smaller model:

Use the executable template created by `PB new`: Objective, numbered Steps, typed Acceptance, Verify commands, Areas/Inputs, Purpose and Secrets. See [SCHEMAS.md](SCHEMAS.md) for the complete format.


READY requires objective, numbered steps with concrete paths/symbols, observable
Acceptance and backticked Verify commands. Avoid vague instructions. Specify outcomes,
contracts, ownership, affected callers and real constraints; leave implementation
choices open within accepted architecture. A small model must escalate an unsupported
assumption, never guess past a failed check. Large tasks are split by behavior, not
artificially scored down. [SCHEMAS.md](SCHEMAS.md) defines formats/IDs/digests.

## 4. Execution, quality and review

1. Select active IN_PROGRESS/REVIEW, else highest-priority READY with evidenced
   dependencies. `PB score <id> --write` computes tier/risk/effort and split hints.
2. Route by EXEC. Pool: `PB agents select --task <id>`, `PB delegate <id>` (preview
   with `--dry-run`). Native: bounded task, Areas, relevant Current slices and ADRs.
   Before dispatch/start, `PB reconcile <id> --note "<target impact decision>"`
   binds the finished spec to current intent. DRAFT permits only explicitly
   `Purpose: discovery` work reconciled with `--goal-independent`.
   SOLO/main work: `PB start <id> --agent <alias>`. One writer per checkout; isolated
   worktrees for concurrent edits. Read back interrupted dispatches, never replay.
3. Read [QUALITY.md](QUALITY.md) when planning/changing UI, backend/state or reviewing.
   Reuse the design foundation and smallest existing architecture. A new design
   gets an ADR and foundation task; no layers/framework merely to satisfy a template.
   Preserve creative freedom in visual direction and implementation while proving
   observable quality. For new direction, compare options and show one real journey early.
4. `PB check <id>` runs Verify inside ProcessTree and writes machine evidence. It
   reuses intact current inputs/environment/spec logs; `--rerun` requests a fresh
   observation when required. Changed premises invalidate old checks. For each non-machine criterion,
   inspect actual behavior and `PB evidence <id> --kind <kind> --criterion <id>
   --note "<observation>" [--file <artifact>]`. Tick only proven Acceptance items.
   UI requires visual/interaction/accessibility triad; source reading is not render
   proof. Backend/state checks cover applicable boundaries, validation, authorization,
   errors, concurrency, idempotency, persistence/restart and migration recovery.
5. MEDIUM/HIGH risk: `PB accept <id>` reports REVIEW_PENDING once implementation
   evidence is complete. Dispatch an independent qualified REV reviewer to inspect
   diff, task, callers, evidence and QUALITY; record `PB review <id> --reviewer <alias>
   --verdict PASS|BLOCKED [--finding "SEVERITY: text"]`. The state is REVIEW, not a
   literal REVIEW_PENDING header. In SOLO, do a dedicated audit and explicitly record
   `PB review <id> --reviewer <owner> --self-review --verdict PASS|BLOCKED`; `accept`
   never creates a PASS for you. BLOCKER/MAJOR/unwaived QUALITY gaps block completion.
6. `PB accept <id>` verifies checked criteria, current logs/artifacts and current
   review; HIGH also requires the configured full test command. Reconcile Current
   when structure changes, `PB validate`, checkpoint code + closure. Continue within
   user scope. LOW risk still needs relevant checks and all applicable typed evidence.

Evidence binds source + verification Inputs, intent epoch, local tool/environment
identity and task contract. Areas stays the write boundary. Include nested config,
shared contracts and remote environment identity explicitly; local fingerprints
cannot detect an unrecorded external service change.
Proof is freshness/coverage, never authenticated identity or an automated quality score.

## 5. Checkpoints, recovery and plan changes

Checkpoint trailers (blank line after commit subject/body):

```text
PB-Task: PB-014
PB-Verification: local | domain | global
PB-Current-Checkpoint: <reconciled domains | all>
PB-Agent: <implementer>
PB-Reviewer: <reviewer when reviewed>
```

Use local/domain/global for LOW/MEDIUM/HIGH respectively. Commit closure before
removing its task, or preserve closure via trailers when deleting in the same commit.
After a verified chunk/before pause, `PB progress <id> --next "..." [--failing "..."]
[--strategy "..."] [--dirty "..."]` replaces Resume and tracks repeated failures.
`PB handoff <id>` exports a bounded public manifest; private logs/secrets stay local.
External operations use `- <op> | prepared|sent|confirmed|failed|response_unknown |
readback: <how>`; unresolved operations survive handoff. Owner is bookkeeping, not a lock.

Revise wrong task specs in place with a dated reason; contract changes invalidate
old evidence. For target/task-graph changes use an ADR and impact pass over open tasks.
Architecture is editable: update Current to observed code; change design within the
authorized Goal using a task and an ADR when appropriate. Expand Areas before editing
another area, reconcile affected intent and refresh affected proof. An old ADR,
Current map or "only the user changes Goal" is not a blanket architecture freeze.
Ask only for an actual change to user intent, external authority or explicit constraints.
On a meaningful Target/constraint change reconcile affected tasks again. An explicit
unchanged-outcome `reconcile --keep-evidence` preserves proof for editorial changes
only; contract/source/input changes still invalidate it. Only the user changes Goal. Escalate decisions outside authorized intent, security,
data/public APIs, deployment or irreversible scope; continue independent work.

## 6. Audits and bounded context

Every ≥5 closed tasks, after adoption/migration, or on request: trace Target − Current
into tasks; spot-check three Current claims; score/probe the next five READY tasks.
Final audit: configured tests/build/lint, each success condition, Current == Target,
UI/backend quality and remaining blockers. Checkpoint with `PB-Plan-Audit: <scope|final>`.

Keep Current ≤200 lines/file, Target ≤150, constraints ≤100, tasks ≤80 and open tasks
≤25 (warning budgets, not permission to lose useful intent). Load next-milestone
specs; defer distant detail. Prefer boot/map/changed/score/validate over rediscovery.
Do not repeat worker exploration without a changed premise; return checks, failures,
changed paths and next step. Never keep secrets or volatile session state in committed
Brain documents. Git history retains closed work; active tracking keeps open intent.

## 7. Genesis, adoption and cleanup

1. `PB map`; inspect detected manifests/entrypoints and only necessary source.
2. Foreign trackers: `PB legacy` preview, authorized `--apply` imports non-publishing
   work. Reconcile goal approval, facts, constraints, decisions, dependencies, Resume
   and unresolved External records; do not copy completed history into the active queue.
3. `PB init` never overwrites files. Resolve session choices once (§2.1). Fill Current,
   Target, constraints and exact commands; ask only unresolved target-changing questions.
4. Record new design/state decisions, one real end-to-end milestone, executable tasks;
   `PB score --write`, `PB validate`, checkpoint `PB-Genesis: true` and Current/Target
   checkpoints. Preserve accepted architecture/visual language in existing projects.
5. Foreign cleanup: `PB legacy --prepare [--path <tracker>]`, map sources to durable
   destinations or justified drops; `PB legacy --verify --note "<reconciliation>"`,
   then `--cleanup`. Verified recoverable archive precedes deletion; changed sources/
   destinations block it. Never blindly delete team docs, application code or global skills.

Boot GC removes a committed unchanged DONE task only after durable historical closure.
Closed evidence files must also match HEAD/index; dirty/untracked artifacts survive.
Referenced active logs remain; uncited logs have bounded age/count retention.
No Git means no GC. Migration backups/legacy originals need semantic reconciliation;
boot never deletes them just because a checkpoint exists. Git can recover committed
files; it does not preserve ignored logs or reduce its own object database on deletion.
Read [REFERENCE.md](REFERENCE.md) for crashes, conflicts, worktrees and containment;
[SCHEMAS.md](SCHEMAS.md) for migration/file contracts; [POOL.md](POOL.md) and
[AGENTS_CLI.md](AGENTS_CLI.md) only for the selected backend. Store publishing stays outside scope.

[PROTOCOL.md](PROTOCOL.md) holds the executable setup/revision/security/continuity commands; load its relevant section only.
