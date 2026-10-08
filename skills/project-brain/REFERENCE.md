# Project Brain — Edge Cases

Read only the heading you need (grep `^## <name>`). SKILL.md wins on conflict.
Universal rule: **observe → reconcile → replan → continue.** Observation over assumption, preservation over cleanup.

## Dirty genesis

Brain introduced into a repo with uncommitted work:
1. `git diff --name-only`, `git diff --cached --name-only`, `git ls-files --others --exclude-standard`.
2. Classify each path: user work / generated / unknown. Do not read or "fix" them.
3. Stage only `.project-brain/` for the genesis commit. If the index already holds user-staged files,
   commit with `git commit -- .project-brain` so their staging survives; if that is impossible, leave
   genesis uncommitted and say so in the report.

## Missing checkpoints

Brain exists but no `PB-Current-Checkpoint` trailer (legacy Brain, hand-written docs, squash stripped it).
`brain.py` falls back to the last commit touching Current. Spot-check the domains your task needs, then
checkpoint them at your next commit. Never rewrite old commits to add trailers.
Per-domain trailers must use normalized Current names; a checkpoint for one domain cannot clear another.
An `all` checkpoint also reconciles unmapped paths. WIP checkpoints are ignored.

## History modes

Set `git.history_mode` once known:
- `preserve` — commits stay reachable; trailers are the history.
- `squash` — before the squash/merge, make the surviving commit carry `PB-Tasks: <all ids>`,
  `PB-Current-Checkpoint`, `PB-Verification`, `PB-Milestone`. Move rationale that lives only in
  intermediate commits into an ADR or the final commit body first.
- `rewrite-prone` — task IDs are identity; treat SHAs as temporary.
- `unknown` — keep critical rationale in tracked Brain files, not only in commit messages.

## Branch change

Branch differs from the one you worked on last:
1. Brain files present on this branch? Branch descends from the genesis commit (`git merge-base --is-ancestor`)?
2. Legitimate descendant → `brain.py changed`, reconcile, continue.
3. Unrelated branch → treat its Brain (or its absence) as a separate context. Never copy task state across.

## Detached HEAD

Read-only analysis and verification are safe. Commits here can become unreachable: before implementation
commits, create a branch if repo/user policy allows (`git switch -c pb/<task>`); otherwise work read-only
and report.

## Conflicts

Merge / rebase / cherry-pick / revert in progress:
1. `git status`; inspect each conflicted file.
2. Resolve only conflicts whose intent you understand from both sides; never pick a side blindly.
   Otherwise mark the related task BLOCKED with the file list and stop that line of work.
3. Never start an unrelated task mid-operation.
4. Afterwards: `brain.py changed`, reconcile affected domains, check tasks and target, re-run verification,
   then checkpoint. A clean Git merge is not semantic verification.

## History rewrite

Symptoms: force-pushed remote, rebased branch, checkpoint commit missing. Task IDs, Current, Target,
constraints and ADRs carry the meaning — SHAs do not. `git log --grep=PB-Task` for surviving history, verify
the domains you need against the code, checkpoint at the next commit.

## Shallow

A shallow clone cannot prove that genesis, a task, or a checkpoint never existed. Work from Brain files
and the code. `git fetch --deepen=<n>` / `--unshallow` only when history is truly needed and policy allows.
`new` may reuse an ID hidden by the shallow history — check `git log --grep` after deepening if unsure.

## Sparse

Hidden paths may hold architecture. Scope Current claims to visible domains; mark others UNKNOWN. Expand
the sparse checkout only if allowed and necessary.

## Worktrees

Each worktree has its own HEAD, index and dirty state; never use another worktree's uncommitted files.
Shared refs may advance underneath you: before checkpointing long work, `git fetch` / check the branch tip.
One agent per worktree, disjoint Areas, reconcile both deltas before integrating.

## Remote divergence

Before pushing: `git fetch`, compare with upstream. Remote advanced → inspect, integrate per repo policy
(merge or rebase), re-verify, then push. Never force-push to make local history win.

## Push failure

The local commit is still a valid local checkpoint; it is just not durable yet. Do not retry destructive
remote operations. Note "not pushed" in the stop report; if continuity depends on the remote, mark BLOCKED.

## CI failure

Local success is not CI success. Classify: environment/infra or flaky → not a code bug, note it;
platform difference, missing generated artifact, dependency resolution → fix task; real regression →
task (HIGH priority). Never change Current because CI infrastructure failed; do revoke completion claims
whose evidence CI invalidated.

## Submodules

Each submodule is a separate repository with its own Brain. The parent records only the pointer and the
dependency relationship. Never commit inside a submodule unless the task explicitly includes it.

## Monorepo

Use `architecture.mode: domains` with one `current/<package>.md` per ownership/change boundary; checkpoint
per domain (`PB-Current-Checkpoint: api,worker`). Do not split so finely that a task needs many tiny files.
Respect nested agent instruction files (AGENTS/CLAUDE/GEMINI.md) for package rules.

## Generated files

Architecture comes from source, never from generated, vendored, lockfile, LFS or binary content. Do not
edit generated files by hand unless the repo's convention requires it. Lockfile/dependency changes must be
intentional, listed in the diff review, and verified.

## No Git

Brain still holds Current, Target, Constraints, Tasks, Decisions, but has no Git history. Keep completed
tasks as `Status: DONE` with a nonempty `## Evidence`; do not delete them. This preserves IDs, completion
and dependencies. The same retention rule applies when commits are forbidden or waiting for approval.
Say so in the report. Never `git init` unasked; once Git/authorization exists, commit retained evidence
before task cleanup. A recorded result still needs the normal takeover verification before relying on it.

## Corrupt Brain

Malformed config, duplicate/cyclic/dangling task IDs, several IN_PROGRESS, Current contradicting code
across many domains:
1. `brain.py validate` for the structural list. Old format (schema ≤3, `PROJECT_BRAIN.md`) is not corrupt:
   use `brain.py migrate` instead (SKILL.md §11).
2. `git log --oneline -10 -- .project-brain` — find the last good version of broken files.
3. Keep every piece of user intent that still parses; rebuild only demonstrably invalid generated state
   (status, deps, markers) from code and Git.
4. `brain.py new` repair tasks for anything you cannot fix now; commit `docs(brain): repair`.

## Crash recovery

Session died (crash, timeout, context exhaustion). Possible leftovers:
| Found | Do |
|---|---|
| clean tree at a checkpoint | normal boot |
| `PB-WIP` commit | resume from its task's Resume notes; re-verify what exists |
| dirty, task IN_PROGRESS | boot says INTERRUPTED/DIRTY; compare `git diff` with Resume notes |
| task DONE with Evidence | if committed, cleanup may join the next authorized commit; otherwise retain it until the verified work commit succeeds |
| deleted task with no completion evidence | deletion is not completion; inspect the diff and recover your task spec from Git before resuming |
| partial legacy migration | rerun `migrate --apply`; original inputs remain in migration-backup and schema is finalized last |
| half-written file | check syntax; if broken, restore that one file from `git show HEAD:<path>` only if it is yours |
| `.git/index.lock` | no git process running (check) → delete the lock |
| merge/rebase markers | see Conflicts |

## Migrations

Persistent-state changes are HIGH risk. Check: up and down migration, rollback plan, old/new app
compatibility during deploy, deploy order, existing data impact, destructive transforms, indexes and
constraints. Run migrations when an executable environment exists; static review alone is not completion.
Schema/code agreement belongs in Current.

## Security

Auth, authorization, sessions, crypto, secrets, permission/sandbox boundaries, data exposure → HIGH risk,
full verification, and escalate unless the user explicitly requested that change. Never write credentials
into Brain files, tasks, trailers, ADRs, or notes.

## Unknown situation

1. Stop changing things. 2. Preserve coherent work (`PB-WIP` commit if needed). 3. Observe: `git status`,
`git log --oneline -5`, `brain.py boot`. 4. Reconcile Brain with what you saw. 5. `brain.py new` tasks for
the gaps. 6. Continue from the reconciled state.
