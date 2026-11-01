# Project Brain 3.7.1

Git-native project memory, executable tasks, source-bound evidence and approved
CLI/native delegation. Python 3.8+, standard library only; project schema 4,
session schema 1.

## Source map

- `skills/project-brain/SKILL.md`: workflow and authority rules.
- `QUALITY.md`, `SCHEMAS.md`, `REFERENCE.md`, `AGENTS_CLI.md` in that directory:
  quality, formats, recovery and routing contracts.
- `scripts/brain.py`: CLI, tasks, checkpoints and validation.
- `scripts/runtime_protocol.py`, `runtime_security.py`: intent/input guards, bounded
  continuity, external access contracts and output checks.
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
