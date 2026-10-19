# Project Brain 3.3.1

Git-native project memory, executable tasks, source-bound evidence and approved
CLI/native delegation. Python 3.8+, standard library only; project schema 4,
session schema 1.

## Source map

- `skills/project-brain/SKILL.md`: workflow and authority rules.
- `QUALITY.md`, `SCHEMAS.md`, `REFERENCE.md`, `AGENTS_CLI.md` in that directory:
  quality, formats, recovery and routing contracts.
- `scripts/brain.py`: CLI, tasks, checkpoints and validation.
- `scripts/runtime_verify.py`: checks, evidence, review, acceptance and containment.
- `scripts/runtime_agents.py`, `runtime_pool.py`, `runtime_discovery.py`:
  discovery, model approval, quotas and durable job accounting.
- `scripts/runtime_agent_pool.py`, `POOL.md`: default separate CLI Agent Pool
  transport, owner policy and task-bound dispatch/recovery. Standalone discovery
  and session accounting remain available explicitly with `--backend direct`.
- `scripts/migrate.py`, `runtime_adopt.py`: conversion, archive and recovery.
- `scripts/test_brain.py`: complete offline regression entry point.

## Delivery and design

- [Release verification](design/12-final-delivery.md).
- [Execution contract](design/11-execution-protocol.md).
- [Latest audit and four fixes](design/15-runtime-audit.md).
- [Evidence recovery](design/decisions/ADR-001.md).
- [Architecture decision](design/decisions/ADR-003.md).

Superseded prompts, completed plans and machine-specific notes remain in Git history.
They are not active work or authorization. This source repository's temporary
`.project-brain/` was completed and removed; do not recreate it.
Consumer-project tracking remains part of the distributed skill.

## Limits

Hashes establish freshness, not truth or product quality. Approval records are not
authenticated identity. Process containment is not a filesystem/network sandbox.
Unknown quota requires an approved job cap; readings cannot reserve capacity against
other clients. OmniRoute coding work needs an explicit coding-agent adapter.
Application store publishing remains outside scope.

Store Automation adoption requires preview, reconciliation, verified archive and
cleanup. No user projects were inspected or migrated for this release.
