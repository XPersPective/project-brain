# Project Brain 3.9.0

Git-native project memory, executable tasks, source-bound evidence and approved
CLI/native delegation. Python 3.8+, standard library only; project schema 4,
session schema 1.

## Token economy contract

Deterministic work precedes bounded low-tier discovery. The lead retains
architecture/planning, ambiguity and acceptance; risk, review and proof floors
remain unchanged. Saved ESP/SP prefill a single new-session confirmation; current
session answers and intervening questions never trigger repeated interviews.
Intervening questions reuse active context rather than boot/history/skill reloads.
The read-only `brief` CLI emits at most 4 KiB with explicit missing detail and
pending/readback warnings, without migration, dispatch or session changes.
Executor Selection Policy (ESP) names seven worker choices: Solo, Native, Native
Cheapest, Native Pinned, CAP Categories, CAP Catalog, CAP Pinned. CAP explicitly
means CLI Agent Pool. Scheduling Policy (SP) separately names Serial/Parallel and
its maximum. Solo means main-agent work with tools and no subagent delegation.
The director records both in `.project-brain/executor-policy.json`; new sessions
(including continue) confirm saved ESP/SP; same-session questions reuse them.
The runtime parses and validates the policy, binds session confirmation to its
bytes, and enforces source/model/category/effort/SP bounds before new dispatch.
First new-session boot requires ESP/SP/QRP choices on old projects too.
Saved-policy workers use the shared durable runs scheduler; legacy delegate is
readback-only, preventing a parallel capacity bypass. CAP
category labels never qualify model strength; an exact-model task-fit record is
required, separate from acceptance evidence. Native constrained launch candidates
and receipts must agree. Legacy missing-policy APIs remain compatibility paths,
never authority to bypass an existing policy. CAP owns its current procedure.

Quota Recovery Policy (QRP) is opt-in and director-only: checkpoint before a chosen
quota threshold, prepare an idempotent host wake intent, acknowledge its ID, and
consume it once after same-account verified quota renewal. Account switch, cancel,
changed policy/checkpoint or unknown observations prevent automatic coding.
The host creates/removes the actual same-chat alarm; Python installs no scheduler.
This session's user cancelled its alarm; no active release-task alarm remains.
Many waves reuse state/evidence/cursors; SOLO needs no provider connection.

Baton Relay Policy (BRP) is opt-in and separate from QRP: at the user's threshold
the director checkpoints, starts the next listed CAP route with quota as the new
director and stops; the successor takes a one-time token, cancels a still-running
predecessor task and continues. Boot shows the active director with UTC times;
only the token holder may implement, delegate or orchestrate, so a project is not
run twice. Logins stay in CAP; `relay stop` ends circulation and cancels its tasks.

The protocol governs agent behavior and CLI gates, not a host's billed-token
counter or editor actions outside Brain. Model capability and real savings still
need measurement; smaller context is not a guarantee of lower billed usage.

## Source map

- `skills/project-brain/SKILL.md`: workflow and authority rules.
- `QUALITY.md`, `SCHEMAS.md`, `REFERENCE.md`, `AGENTS_CLI.md` in that directory:
  quality, formats, recovery and routing contracts.
- `scripts/brain.py`: CLI, tasks, checkpoints and validation.
- `scripts/runtime_protocol.py`, `runtime_security.py`: intent/input guards, bounded
  continuity, external access contracts and output checks.
- `scripts/runtime_executor_policy.py`, `runtime_quota_recovery.py`, `runtime_control.py`:
  validated ESP/SP/QRP, exact bounds, session receipts and host wake guards.
- `scripts/runtime_relay.py`, `RELAY.md`: optional BRP director circulation, baton
  tokens, single-director gate and CAP successor start/cancel.
- `scripts/runtime_session.py`: bounded metadata orientation, durable multipart
  intake and saved-focus continuity. Session settings live in the ignored cache;
  requests.json is durable project intent, separate from proof.
- `scripts/runtime_context.py`, `runtime_reports.py`: source-bound task packets,
  literal read-only discovery, validated reports and bounded lead-agent views.
- `scripts/runtime_runs.py`, `runtime_orchestration.py`: opt-in SQLite run/request/
  event accounting, admission, isolated workspaces, Pool/native transport boundary,
  candidate checks, acceptance-gated integration, export, backup and safe cleanup.
- `scripts/runtime_verify.py`: checks, evidence, review, acceptance and containment.
- `scripts/runtime_agents.py`, `runtime_pool.py`, `runtime_discovery.py`:
  discovery, model approval, quotas and durable job accounting.
- `scripts/runtime_agent_pool.py`, `POOL.md`: default separate CLI Agent Pool
  transport, owner policy and task-bound dispatch/recovery. Standalone discovery
  and session accounting remain available explicitly with `--backend direct`.
- `scripts/migrate.py`, `runtime_adopt.py`: conversion, archive and recovery.
- `scripts/test_brain.py`: complete offline regression entry point.

## Verification and design

- [Verification guide](VERIFICATION.md): checks, protected invariants, limits,
  release procedure.
- [Evidence recovery](design/decisions/ADR-001.md).
- [Architecture decision](design/decisions/ADR-003.md).
- [Orchestration decision](design/decisions/ADR-004.md).
- [Executor/recovery decision](design/decisions/ADR-005.md).

## Orchestration development

- [Orchestration roadmap](design/ORCHESTRATION-ROADMAP.md): requested future work
  prioritizing the main agent's token consumption and end-to-end delivery time.
  The opt-in implementation and executable checks are present. The roadmap keeps
  release evidence and host limits explicit, including the real Codex read-only
  lifecycle probe, relocated readback-only restore, and unknown provider counters. It is the single development ledger, not a revival
  of the completed temporary `.project-brain/` plan.
  [User protocol](../skills/project-brain/ORCHESTRATION.md) describes runnable
  commands and conservative recovery boundaries.

Superseded audits, prompts, completed plans and machine-specific notes remain in Git history.
They are not active work or authorization. This source repository's temporary
`.project-brain/` was completed and removed; do not recreate it.
Consumer-project tracking remains part of the distributed skill.

## Limits

Normal `orient` and `boot` upgrade recognized old project tracking on use, with
raw-input backups, including no-Git and unborn-Git projects. Read-only startup and
merge/rebase defer conversion; future versions and unknown legacy shapes stop
without conversion. Project state migration does not download a new skill release.
Installed skill updates remain the responsibility of the deployment manager.

Hashes establish freshness, not truth or product quality. Approval records are not
authenticated identity. Process containment is not a filesystem/network sandbox.
Unknown quota requires an approved job cap; readings cannot reserve capacity against
other clients. OmniRoute coding work needs an explicit coding-agent adapter.
Native launch/attach/cancel and counters depend on the calling host. This update
was initially developed SOLO/SERIAL, then independently reviewed and exercised
with real read-only Codex native workers on 2026-11-01. Other hosts/providers
require their own validation; this is not blanket live-provider certification. Dirty worktrees and all dedup keys
are retained; worktree isolation does not hide Brain or install a sandbox.
Application store publishing remains outside scope.

Foreign tracker adoption requires preview, reconciliation, verified archive and
cleanup. No user projects were inspected or migrated for this release.
