# Project Brain — Recovery and Edge-Case Reference

Read only the sections relevant to the current repository state.
This file supplements SKILL.md. In case of conflict, SKILL.md takes
precedence.

# Contents

1. Existing-project genesis
2. Git history modes
3. Architecture checkpoint discovery
4. Dirty worktrees
5. Unknown user modifications
6. Interrupted work
7. Branch changes
8. Detached HEAD
9. Merge/rebase/cherry-pick conflicts
10. History rewrites
11. Squash workflows
12. Shallow clones
13. Sparse checkouts
14. Worktrees
15. Parallel agents
16. Remote divergence
17. CI divergence
18. Submodules
19. Monorepos
20. Generated/vendor/LFS content
21. No-Git operation
22. Corrupt or stale Project Brain
23. Missing checkpoint metadata
24. Target changes mid-project
25. Partial architecture knowledge
26. WIP commits
27. Push failures
28. Task dependency corruption
29. Security-sensitive work
30. Database migrations
31. Long-running projects
32. Final reconciliation
33. Agent crash recovery
34. Catch-all error procedure

# 1. Existing-Project Genesis

This is one of the highest-risk scenarios. Project Brain may be
introduced after years of development.

Do not convert historical commits into fictional PB tasks.

```text
current HEAD
→ repository mapping
→ targeted architecture reconstruction
→ user-provided future intent
→ target architecture
→ unfinished plan
→ genesis checkpoint
```

Treat everything before genesis as historical evidence.

## Dirty repository at genesis

If changes already exist when introducing Project Brain:

1. identify tracked modifications (`git diff --name-only`)
2. identify staged modifications (`git diff --cached --name-only`)
3. identify untracked files (`git ls-files --others --exclude-standard`)
4. classify ownership: user work / generated / unknown
5. if Brain files can be committed independently → do so selectively
6. otherwise → keep genesis pending until resolved

→ NEXT: After genesis completes, proceed to Task Execution Loop (SKILL.md §23).

# 2. Git History Modes

Set `git.history_mode` in config.yaml to one of:

| Mode | Meaning | Brain behavior |
|---|---|---|
| `preserve` | Normal commits remain reachable | Rely on trailers for history |
| `squash` | Intermediate commits destroyed on merge | Preserve milestone info in final trailers and ADRs |
| `rewrite-prone` | SHAs frequently change | Use task IDs as identity, treat SHAs as temporary |
| `unknown` | Cannot determine workflow | Keep critical rationale in tracked Brain documents |

**For squash mode specifically:**

Before squash/merge, ensure the surviving commit contains enough
metadata to recover the milestone:

```text
PB-Tasks: PB-041,PB-042,PB-043
PB-Current-Checkpoint: auth
PB-Verification: domain
```

Do not store essential rationale solely in intermediate commits.

→ NEXT: Configure `history_mode` in config.yaml during genesis or when workflow is discovered.

# 3. Architecture Checkpoint Discovery

Preferred source:

```text
git log --grep="PB-Current-Checkpoint" --format="%H %s" -1
```

For specific domain:

```text
git log --grep="PB-Current-Checkpoint: auth" --format="%H %s" -1
```

If multiple domains exist, each may have a different latest checkpoint.

## Fallback (no trailers exist)

1. Find the latest relevant commit touching Current Architecture
   (`git log -1 -- .project-brain/current.md`)
2. Treat it as a candidate checkpoint
3. Verify enough repository state to establish trust
4. Create a proper checkpoint at the next semantic commit

Do not rewrite old commits merely to add metadata.

→ NEXT: Use the discovered checkpoint as the reconciliation baseline.

# 4. Dirty Worktrees

Classify each dirty path:

```text
active PB work        → continue if non-overlapping
user work             → preserve, do not touch
another agent's work  → preserve, reconcile
generated output      → safe to regenerate
expected tool output  → note and continue
unknown               → do not destroy
```

## Safe continuation

Non-overlapping work may continue when:
- ownership is clear
- active task files do not overlap
- build/test effects are understood
- checkpoint can exclude unrelated modifications

## Unsafe continuation

Stop (mark task BLOCKED) when:
- modifications overlap intended edits
- ownership is unknown
- staging state is complex and could be lost
- recovery would require guessing

→ NEXT: Classify → continue if safe, block if unsafe.

# 5. Unknown User Modifications

User work has priority over convenience.

**Never run without clear justification:**

```text
git reset --hard
git clean -fd
git checkout -- <unknown-file>
git restore <unknown-file>
```

Do not fold user modifications into an agent commit merely for a
clean tree. If the task requires the same file, inspect and preserve
the user's changes while applying new work if safely possible.

→ NEXT: Classify ownership, preserve user work, continue non-overlapping tasks.

# 6. Interrupted Work

An interrupted task exists in one of four forms:

| Form | Action |
|---|---|
| Clean committed partial checkpoint | Resume from Git and task file |
| Dirty verified-but-uncommitted work | Re-verify if state may have changed, then checkpoint |
| Dirty unverified work | Treat as in-progress, do not assume correctness |
| WIP commit (`PB-WIP: true`) | Inspect task notes, resume from documented state |

→ NEXT: Verify actual repository state, resume from first unverified point.

# 7. Branch Change

When the current branch differs from expected context:

1. Check if Brain files exist on the branch
2. Check if the branch descended from PB genesis
3. Check if Target applies
4. Check if task IDs overlap with unrelated history

If the branch is a legitimate descendant: reconcile from merge-base
or checkpoints.

Do not blindly import task state across unrelated branches.

→ NEXT: Reconcile if legitimate, treat as new context if unrelated.

# 8. Detached HEAD

Do not automatically create a branch unless repository/user policy
permits it.

Read-only analysis and verification are safe.

Commits created on detached HEAD risk becoming unreachable.

Before durable implementation commits: establish an allowed persistence
strategy (create branch or confirm policy).

→ NEXT: Create a branch if policy allows, or work read-only.

# 9. Merge/Rebase/Cherry-Pick/Revert in Progress

Do not begin a new unrelated task.

1. Inspect operation state first
   (`git status`, check `.git/MERGE_HEAD` or `.git/rebase-merge/`)
2. Resolve only conflicts you understand
3. If conflict exceeds your understanding → mark task BLOCKED with
   details of the unresolvable conflict

After the operation completes:
- inspect affected architecture
- inspect task files
- reconcile Target/constraints
- rerun required verification
- create new Current checkpoint when trustworthy

A successful Git merge is not semantic verification.

→ NEXT: Resolve understood conflicts → reconcile → checkpoint. Block if unsure.

# 10. History Rewrites

Indicators: stored SHA not reachable, remote force-push, rebased
feature branch, changed merge base.

```text
find surviving task IDs (from .project-brain/tasks/)
→ inspect reachable history (git log --grep="PB-Task")
→ compare repository reality
→ re-establish checkpoints
```

Do not panic merely because a SHA changed. Task IDs, Current
Architecture, Target, constraints, and ADRs provide semantic continuity.

→ NEXT: Re-establish checkpoints using task IDs and current Brain files.

# 11. Squash Workflows

Before a group of PB tasks is squashed, ensure the surviving commit
preserves milestone-level metadata:

```text
PB-Tasks: PB-041,PB-042,PB-043
PB-Current-Checkpoint: auth
PB-Verification: domain
PB-Milestone: auth-migration
```

Do not attempt to preserve every intermediate verification result.

For completed tasks whose files were already deleted: their history
is in Git. If Git history will also be squashed, ensure acceptance
criteria and key rationale exist in an ADR or the final commit body
before the squash.

→ NEXT: Preserve milestone metadata before squash, ADR if rationale matters.

# 12. Shallow Clones

A shallow clone cannot prove that older history does not exist.

**Never conclude from shallow history alone:**
- no genesis exists
- no prior PB task exists
- this is the first architecture checkpoint

Use available Brain files and current repository state.

Fetch deeper history only when:
- network/policy permits
- historical knowledge is necessary
- current evidence is insufficient

Otherwise operate in degraded-history mode: Brain files are the
primary semantic source.

→ NEXT: Work with available Brain files. Fetch deeper history only when needed.

# 13. Sparse Checkouts

Sparse repositories may hide architecture-relevant files.

Do not claim repository-wide Current Architecture verification based
only on a sparse working tree.

Scope Current claims to visible/verified domains.

Expand sparse checkout only if allowed and necessary.

→ NEXT: Scope architecture claims to visible domains.

# 14. Worktrees

Each Git worktree has its own working tree and branch/HEAD.

Do not use dirty state from another worktree.

Shared Git history may change underneath the current worktree.

Before checkpointing long-running work: inspect whether relevant
branch refs advanced externally.

→ NEXT: Treat each worktree independently, check for external advances.

# 15. Parallel Agents

Project Brain does not implement a distributed lock.

Recommended strategy:

```text
one agent → one branch/worktree → non-overlapping task/domain
```

When tasks overlap:
- coordinate externally
- serialize work, or
- establish an explicit integration owner

Before integration:
- reconcile both deltas
- re-evaluate architecture
- rerun appropriate verification

For large parallel projects: domain-separated Current files reduce
merge conflicts.

→ NEXT: Assign non-overlapping domains. Reconcile before integration.

# 16. Remote Divergence

Before pushing when remote state matters:

1. Determine whether the remote branch advanced
   (`git fetch --dry-run` or `git remote show origin`)
2. If remote commits exist:
   - inspect → reconcile → integrate per repository policy → verify
3. Do not force-push merely to make local history authoritative

→ NEXT: Fetch, reconcile, integrate, verify.

# 17. CI Divergence

Local success is not CI success.

If CI later fails, classify whether the failure is:

```text
environment difference    → not a code bug
platform difference       → investigate, may need fix
race/flakiness            → retry, not a regression
missing generated artifact → fix build pipeline
dependency resolution     → fix dependency spec
real regression           → task to fix
unrelated infrastructure  → not a code bug
```

Do not change Current Architecture because CI infrastructure failed.
Do change task completion claims if acceptance evidence is invalidated.

→ NEXT: Classify CI failure → fix if regression, ignore if infrastructure.

# 18. Submodules

Treat each submodule as a separate Git repository.

The parent records the submodule commit pointer, not its internal
working history.

Do not commit inside a submodule unless the task explicitly includes
that repository.

Parent Current Architecture may describe the dependency relationship.
Detailed submodule architecture belongs in the submodule's own
Project Brain.

→ NEXT: Work within submodule boundaries. Don't cross without explicit scope.

# 19. Monorepos

Avoid one enormous Current Architecture document.

Prefer domain/package boundaries that align with actual ownership
and change patterns:

```text
.project-brain/
├── current/
│   ├── platform.md
│   ├── api.md
│   ├── web.md
│   └── worker.md
└── target/
    ├── platform.md
    └── api.md
```

Do not split so aggressively that every task needs many tiny files.

Use domain boundaries that reduce context and merge contention.

Checkpoint trailers can declare domain-specific scopes:

```text
PB-Current-Checkpoint: api,worker
```

Nested AGENTS/instruction files may impose additional package-specific
rules.

→ NEXT: Split by domain when context/contention cost justifies it.

# 20. Generated Files, Vendor Trees, LFS, Large Assets

Do not use generated/vendor content as the primary architecture source
when authoritative source files exist.

Do not map large binary assets in architecture documents.

Respect repository generation workflows.

Do not manually edit generated files unless conventions require it.

Dependency/lockfile changes should be intentional and verified.

→ NEXT: Architecture should reference source files, not generated output.

# 21. No-Git Operation

If the repository is not under Git, Project Brain may still provide:
Current, Target, Constraints, Tasks, Decisions.

But it loses durable checkpoint/history guarantees.

Do not automatically run `git init` unless authorized.

State clearly that execution history is operating in degraded mode:
- no checkpoint trailers
- no commit-based task completion evidence
- no history queries

If Git is later initialized, establish a genesis baseline then.

→ NEXT: Work with Brain files only. No checkpoint guarantees.

# 22. Corrupt Project Brain

Examples: malformed YAML, missing target referenced by tasks,
impossible dependency graph, conflicting Current documents, duplicate
task IDs, obviously stale Brain across many domains.

```text
repository observation
→ Git history inspection (recent commits touching .project-brain/)
→ surviving Brain validation (which files parse correctly?)
→ reconstruct minimum trustworthy semantic state
→ create tasks for repair work
```

Preserve valid user intent. Discard/rewrite only demonstrably
invalid generated state.

→ NEXT: Reconstruct from Git + valid Brain fragments. Task the repairs.

# 23. Missing Checkpoint Metadata

If Brain files exist but no PB trailers exist in Git:

Possible causes:
- legacy Brain (created before trailers were used)
- manually created docs
- imported project
- squash that stripped trailers

Use repository reality plus document history to establish a new
checkpoint. Do not rewrite old commits merely to add metadata.

→ NEXT: Use Brain files as-is, create proper checkpoint at next commit.

# 24. Target Changes Mid-Project

When the user changes the goal:

1. Preserve previous target in Git history (commit before changing)
2. Update current target
3. Identify tasks now invalid
4. Delete/supersede obsolete unfinished tasks
5. Retain completed implementation that remains useful
6. Create new tasks for the new gap
7. Record an ADR only when rationale will matter later
8. Checkpoint

Do not rebuild the entire plan if most of it remains valid.

→ NEXT: Targeted update → gap analysis → new tasks → checkpoint.

# 25. Partial Architecture Knowledge

Do not require full-system architecture to work on one bounded
subsystem.

Current Architecture may explicitly scope itself:

```text
Verified domains:
  - auth
  - API routing

Not yet mapped:
  - billing
  - analytics
```

Expand architecture knowledge on demand when a task requires it.

This is preferable to inventing a comprehensive map during genesis.

→ NEXT: Map only what the current task needs. Expand incrementally.

# 26. WIP Commits

Use only when continuity requires Git persistence before verification
and policy allows it.

**Required trailers:**

```text
PB-Task: PB-014
PB-WIP: true
```

**Rules:**
- Do NOT add `PB-Current-Checkpoint` unless Current Architecture was
  genuinely reconciled (not merely partially implemented)
- Do NOT add `PB-Verification` unless verification actually ran
- Do NOT represent WIP as completed work
- When later completed, normal completion commits supersede the WIP
- Whether WIP commits are later squashed depends on repository policy

→ NEXT: Create WIP commit with minimal honest trailers.

# 27. Push Failure

A local commit remains a valid local checkpoint.

Record the difference:

```text
committed locally    → checkpoint is valid for local work
persisted remotely   → checkpoint is durable
```

Do not retry destructive remote operations automatically.

If continuity depends on remote availability, surface the push failure
as a blocker.

→ NEXT: Keep local commit. Note push failure. Continue if non-blocking.

# 28. Task Dependency Corruption

Examples:

```text
A depends on B, B depends on A     (cycle)
Task depends on nonexistent ID      (dangling reference)
READY task has unresolved dependency (premature status)
```

Do not execute through a corrupt graph.

Repair from approved intent and repository reality:
- Remove invalid dependencies
- Fix status inconsistencies
- Create missing tasks if needed

Task graph metadata is planning state, not immutable history.

→ NEXT: Repair graph → validate → continue.

# 29. Security-Sensitive Work

Increase verification for:
authentication, authorization, sessions, cryptography, secrets,
permission boundaries, sandbox boundaries, data exposure.

Never record live credentials in Project Brain.

A security-semantic change usually requires explicit authority
(mark task BLOCKED if not already requested by user).

→ NEXT: HIGH risk verification + escalation check for security work.

# 30. Database / Persistent-State Changes

Inspect:
- migration direction (up/down)
- rollback expectations
- old/new application compatibility
- deployment ordering
- existing data impact
- destructive transformations
- indexes/constraints
- runtime assumptions

Schema/code agreement is part of Current Architecture.

Do not mark migration work complete based only on static code review
when executable verification is available.

→ NEXT: Verify migrations can run AND roll back. Update Current Architecture.

# 31. Long-Running Projects

Project Brain should not grow linearly with project age.

```text
task files decrease    (completed → deleted)
Git history increases  (natural growth)
Current evolves        (reflects reality)
Target converges       (approaches completion)
ADRs remain            (only when durable rationale exists)
```

A mature completed project may have very little active Brain state.

Periodically review: are there stale tasks, outdated ADRs, or
obsolete constraints that should be cleaned?

→ NEXT: Clean stale Brain state. Less is more.

# 32. Final Reconciliation

At milestone or final completion:

1. Inspect remaining task files → none should be IN_PROGRESS
2. Verify Current matches repository reality
3. Verify Target is achieved or explicitly revised
4. Verify constraints hold
5. Run appropriate broad verification (full test suite if available)
6. Inspect final relevant Git range
7. Ensure checkpoint trailers exist
8. Remove obsolete temporary notes

The final active Brain should describe present truth and durable intent,
not the implementation diary.

→ NEXT: Clean up → verify → final checkpoint.

# 33. Agent Crash Recovery

When an agent's session is violently terminated (crash, timeout,
context exhaustion):

**Possible states left behind:**

| State | Recovery |
|---|---|
| Clean committed checkpoint | No recovery needed, normal resume |
| Committed WIP (`PB-WIP: true`) | Resume from WIP, verify what exists |
| Uncommitted but saved files | `git status` + `git diff` to assess |
| Half-written files | Check file integrity, restore from Git if corrupt |
| Mid-Git-operation | Check `.git/` for lock files, clean if safe |

**Recovery procedure:**

1. `git status` — assess working tree
2. Check `.git/index.lock` — remove if stale
3. Check `.git/MERGE_HEAD`, `.git/rebase-merge/` — resolve if present
4. Read active task file — check resume notes
5. Verify any uncommitted changes are coherent
6. If changes are coherent → continue from documented state
7. If changes are incoherent → `git checkout -- <corrupted-files>`,
   resume from last commit

→ NEXT: Assess damage → clean locks → resume from last safe point.

# 34. Catch-All Error Procedure

When encountering any situation not covered by sections 1-33:

```text
1. STOP — do not proceed with uncertain state
2. PRESERVE — WIP commit current coherent work if any
3. OBSERVE — git status, git log -5, ls .project-brain/
4. RECONCILE — compare Brain state with repository reality
5. REPAIR — create tasks for any discovered gaps
6. CONTINUE — proceed from reconciled state
```

**Principle:** observation over assumption, safety over speed,
preservation over cleanup.

→ NEXT: Follow the 6-step procedure above.
