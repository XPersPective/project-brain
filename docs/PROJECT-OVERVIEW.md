# Project Brain 4.0.6

Git-native project memory, executable tasks, source-bound verification and
economical orchestration. Python 3.8+, standard library only; project schema 4,
policy schema 1, opt-in SQLite run ledger schema 1.

## Core vs Power separation

- **Core product (standalone, zero external dependencies):** Git-native memory
  (`current.md`, `target.md`, `constraints.md`, `decisions/ADR-*.md`,
  `tasks/PB-*.md`), deterministic task scoring, protocol-1 intent/input-bound
  verification (`start`, `check`, `evidence`, `review`, `accept`), `solo` and
  host `native` execution, safe core defaults (`native · parallel (auto) · QRP
  off · BRP off`), single-line `setup ask` → `setup confirm`, inline `policy`
  flags, `board` (default-on zero-token Progress Board), `watch` (<25 tokens) and bounded read-only `brief` (≤4 KiB).
- **Power features (strictly opt-in):**
  - **CLI Agent Pool (CAP)** (`mixed`, `cap-category`, `cap-catalog`,
    `cap-pinned`): external CLI discovery, auth, quotas, model catalogs and
    process execution live exclusively in the separate `cli-agent-pool`
    repository. Legacy `--backend direct`, OmniRoute and standalone CLI
    discovery were removed in 4.0 (ADR-008). `PB qualify` is optional advisory/
    override metadata rather than a fresh-repo deadlock.
  - **Durable Orchestration (`PB runs`):** transactional SQLite WAL run ledger,
    isolated worktrees, native host bridge, candidate verification, worker
    commit snapshots and ff-only single-writer integration.
  - **Quota Recovery Policy (QRP):** opt-in director checkpoint + host same-chat
    wake intent with strict account/limit/reset validation.
  - **Baton Relay Policy (BRP):** opt-in multi-account director circulation over
    CAP `pb-director/1` (`preflight`, `onExit`, `ack`, `idle`, `secretEnv`,
    `resolve`, `releaseLockOnFailure`, `directorProfile`, `quotaBarrier`,
    `wakeAt`, `supersede`).

## Source map (acyclic layered runtime)

All 20 runtime modules under `skills/project-brain/scripts/` are acyclic with
zero lazy internal imports and Python 3.8+ syntax:

- **Foundation layer:**
  - `runtime_core.py`: version (`4.0.6`), crash-safe atomic writes (`fsync` +
    Windows retry), OS file/project locks, Python 3.8–3.13 UTC ISO parsing,
    bounded JSON loading, safe public/private path checks, secret-scrubbed Git
    runner and `ProcessTree` containment.
  - `runtime_scoring.py`: deterministic task surface, complexity scoring and
    risk floor escalation.
  - `runtime_security.py`: longest-first secret redaction, staged-byte scans,
    public-path guard and host private-binding adapter/scanner contract.
  - `runtime_actors.py`: slim locked actor registry, canonical identity
    comparison, worker prompt builder and acyclic backend gate dispatcher.
- **Policy, protocol & verification layer:**
  - `runtime_executor_policy.py`: validated 8-source ESP, SP, QRP and relay
    policy schema, session-byte confirmation receipts and CAP fallback rules.
  - `runtime_protocol.py`: protocol-1 intent/input digests, check-log
    validation, progress budgets, bounded handoffs and request ledger.
  - `runtime_verify.py`: `check`, `evidence`, `review`, `accept`, log pruning
    and `ProcessTree` command execution.
  - `runtime_context.py`, `runtime_reports.py`: source-bound task packets,
    literal read-only discovery, compact reports and metrics comparison.
- **Orchestration & recovery layer:**
  - `runtime_runs.py`, `runtime_orchestration.py`: SQLite WAL ledger, admission,
    worktrees, native/CAP transport, candidate verify/integrate/rebuild/restore.
  - `runtime_agent_pool.py`: stdlib JSON-stdin CAP RPC client, bounded policy
    selection, advisory/explicit `qualify` and legacy journal readback.
  - `runtime_quota_recovery.py`, `runtime_relay.py`, `runtime_setup.py`,
    `runtime_control.py`, `runtime_session.py`: QRP, BRP, streamlined setup,
    control CLI and bounded `orient`/`brief`/`intake`.
- **Entry & migration layer:**
  - `runtime_adopt.py`, `migrate.py`: legacy Brain upgrade (`v0`/schema 3/3.x)
    and foreign tracker adoption/archive/cleanup.
  - `brain.py`: unified CLI entry point.
- **Tests & tooling:**
  - `skills/project-brain/scripts/test_brain.py`: complete offline regression
    entry point (with `test_helpers.py` environment scrubbing and
    `test_v4_hardening.py`).
  - `skills/project-brain/scripts/test_pool_integration.py` and
    `tools/test_relay_integration.mjs`: optional real CAP daemon/watchdog tests.
  - `tools/build_release.py`: reproducible Git-index ZIP builder + version/AST/
    cycle/budget checks.

## Design & verification

- [Verification guide](VERIFICATION.md): checks, measurements, protected
  invariants, limits and release procedure.
- Accepted ADRs: [ADR-001](design/decisions/ADR-001.md) (evidence recovery),
  [ADR-003](design/decisions/ADR-003.md) (architecture),
  [ADR-004](design/decisions/ADR-004.md) (orchestration),
  [ADR-005](design/decisions/ADR-005.md) (executor/recovery),
  [ADR-006](design/decisions/ADR-006.md) (unattended relay),
  [ADR-007](design/decisions/ADR-007.md) (roles/economy),
  [ADR-008](design/decisions/ADR-008.md) (4.0 acyclic core & CAP separation).

## Limits

Hashes establish freshness, not truth or product quality. Review/approval
records are not authenticated identity. `ProcessTree` limits process lifetime,
not filesystem/network access. Regex masking and text scans are partial
defences, not universal DLP. Percentage quotas cannot guarantee a billed-token
budget. Native launch/attach/cancel and token counters depend on the calling
host. Application store publishing remains outside scope.
