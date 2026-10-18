# Current Architecture

## Runtime
- Python CLI (`brain.py`, `runtime_verify.py`, `runtime_agents.py`, `migrate.py`), stdlib only; Windows JobObject / POSIX process group containment. Self-check results are recorded in PB-008 on Windows/Python 3.11.15.
- Skill instructions run through the host coding agent and orchestrate installed local CLI coding agents (`codex`, `claude`, `gemini`, `opencode`, `agy`, `qwen`, etc.) via `~/.project-brain/agents.json`.

## Map
- `skills/project-brain/SKILL.md` — v3.0 agent workflow, state machine, and multi-agent delegation loop.
- `skills/project-brain/QUALITY.md` — Frontend Design System & Token Foundation, UI Triad (`[visual]`, `[interaction]`, `[accessibility]`), `QUALITY` review findings, Backend Clean Architecture & explicit state machine rubric.
- `skills/project-brain/AGENTS_CLI.md` — mechanical complexity scoring (`PB score`), CLI agent discovery (`PB agents scan`), live subscription quota tracking (`PB agents quota`), reserve floors (`10%`/`25%`), and CLI worker delegation (`PB delegate`).
- `skills/project-brain/SCHEMAS.md`, `REFERENCE.md` — file formats, digest-bound Evidence/Review schemas, trailers, and edge cases.
- `skills/project-brain/scripts/brain.py` — v3.0 CLI entrypoint, task/config parsing, Git checkpoints, and command routing.
- `skills/project-brain/scripts/runtime_verify.py` — `ProcessTree` containment, `public_path`, `digest`, `check`, `evidence`, `review`, `accept`.
- `skills/project-brain/scripts/runtime_agents.py` — `score_task`, `scan_agents`, `probe_codex_quota`, `candidates`, `gate`, `delegate_task`, `cmd_legacy`.
- `skills/project-brain/scripts/runtime_pool.py` — project/session proposal, configuration-bound user selection, bounded quota/job reservation, crash settlement and compact boot summary.
- `skills/project-brain/scripts/runtime_adopt.py` — source/destination trace, out-of-project archive and resumable cleanup of obsolete tracking state (PB-010 in verification).
- `skills/project-brain/scripts/migrate.py` — legacy Brain (`schema <= 3` and `PROJECT_BRAIN.md`) conversion.
- `skills/project-brain/scripts/test_brain.py` — regression suite including `test_protocol_audit.py`, `test_verify_audit.py`, `test_agents_audit.py` for handoff, native locks, identity/review policy, deadlines, quota and adoption.
- `docs/design/07-v3-master-prompt.md` — self-contained Master Prompt and architectural synthesis for Project Brain 3.0.
- `docs/design/08-integration-audit.md` — audit prompt, Store Automation comparison, repaired defects and verified scope/limits.
- `docs/PROJECT-OVERVIEW.md` — ordered Turkish requirement checklist, completed/pending work and cold handoff; read before new implementation.
- `docs/design/09-session-pool-and-clean-adoption.md`, `10-local-agent-inventory.md` — confirmed follow-up details and lightweight metadata inventory.
- `plugin.json`, `.claude-plugin/`, `.agents/plugins/`, `gemini-extension.json` — distribution manifests (`3.0.0`).

## Domains
### Protocol
Status: VERIFIED
Sources: `skills/project-brain/*.md`, `README.md`, `docs/design/**`, `docs/PROJECT-OVERVIEW.md`
- Task states `PLANNED -> READY -> IN_PROGRESS -> REVIEW -> DONE`, `BLOCKED`; WAITING_USER is a BLOCKED reason and READBACK_FIRST a boot result. Evidence/Review bind source and contract digests.
- Frontend UI Excellence Rubric (`QUALITY.md` §1) enforces Design System & Token Foundation ADRs, the UI Verification Triad (`[visual]`, `[interaction]`, `[accessibility]`), and blocking `QUALITY` findings.
- Backend & State Excellence Rubric (`QUALITY.md` §2) enforces Clean Architecture layer separation, explicit sealed state machines, boundary validation, and idempotency.
- Store publishing/distribution (Play Store, App Store, Fastlane) is explicitly excluded from Project Brain.

### Runtime
Status: VERIFIED
Sources: `skills/project-brain/scripts/**`
- Seventeen commands (`boot`, `map`, `init`, `new`, `start`, `check`, `evidence`, `review`, `accept`, `score`, `agents`, `delegate`, `changed`, `validate`, `migrate`, `legacy`, `doctor`).
- `runtime_verify.py` runs `Verify` commands inside `ProcessTree` with secret-filtered env and isolated `PYTHONPYCACHEPREFIX`, binding results to `areas_digest` and `contract`.
- `runtime_agents.py` scores task difficulty (`0..100`), discovers installed CLI coding agents (`codex`, `claude`, `gemini`, `opencode`, `agy`, `qwen`, `kimi`, `mcode`, `omniroute`), probes live subscription rate limits (`codex app-server --stdio` JSON-RPC `account/rateLimits/read`), enforces `10%` worker and `25%` director quota reserves, and delegates `Tier L/M` tasks to CLI workers.

### Packaging
Status: VERIFIED
Sources: `plugin.json`, `.claude-plugin/**`, `.agents/plugins/**`, `gemini-extension.json`, `assets/**`, `PRIVACY.md`, `CHANGELOG.md`
- Version `3.1.0` synchronized across `SKILL.md`, `brain.py`, `plugin.json`, `.claude-plugin/plugin.json`, `gemini-extension.json`, and `CHANGELOG.md`; project schema stays 4, machine session schema 1.

## Known Unknowns
- Full audit in PB-008; live model execution is not part of self-checks. CLI adapter/model availability depends on installed versions and explicit access. POSIX process groups require verification on a POSIX host; this session runs Windows.
