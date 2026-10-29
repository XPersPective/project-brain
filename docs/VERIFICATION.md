# Verification guide — Project Brain 3.5.1

Maintained record of how this source is verified, which invariants the tests
protect and which limits remain. It replaces the former per-release audit and
delivery reports (11–18 under `docs/design/`); those remain in Git history and are
not active work or authorization. Update this file instead of adding new reports.

## Repeatable checks

```text
python -B skills/project-brain/scripts/test_brain.py
python -B skills/project-brain/scripts/brain.py --version
git diff --check
```

`test_brain.py` is the complete offline entry point. It runs the lifecycle,
migration/recovery, checkpoint, review/identity, ProcessTree containment, quota,
owner routing, adoption/archive/retry, discovery, Pool journal/replay, handoff and
strict protocol-1 suites (`test_*.py`); each module also runs alone. Tests use
temporary repositories, local processes and mocked metadata — no paid model, no
provider quota and no user project.

Optional live Pool integration (fresh private data directory, synthetic worker):

```text
python -B skills/project-brain/scripts/test_pool_integration.py --pool-entry <Pool>/bin/pool.js
```

All Python files must parse with Python 3.8 grammar. Runtime evaluation has been on
Windows/Python 3.11; actual Python 3.8/POSIX execution is not claimed.

## Protected invariants

- **Evidence:** only `start`, `check`, `evidence`, `review`, `accept` write
  Evidence/Review. Proof is bound to Areas, verification Inputs, dependency/config
  defaults, tool/host-adapter identity and local environment. A valid receipt is
  reused without re-running commands; a completed Pool receipt also skips the
  result RPC. Missing logs in a fresh checkout force a recheck.
- **Intent (protocol 1):** tasks record reconciled target/domain/constraints. DRAFT
  permits only goal-independent work; meaningful target changes need an impact
  decision before execution or closure. Migration never invents user confirmation.
- **Progress:** bounded progress/handoff records, repeated-failure guard and explicit
  run/time check budgets. Provider token limits are backend/host policy, not claimed.
- **Session authority:** approval binds project, session and execution configuration
  (PROPOSED → APPROVED → REVOKED). Dispatch re-checks approval under the pool lock
  before reservation. Known quota keeps 10% worker / 25% director floors; unknown
  quota needs an explicit bounded job allowance. No silent paid/director fallback.
  Uncertain or crashed jobs require readback/settlement, never a blind retry.
- **Pool:** CLI Agent Pool owns catalogs, auth, effort, quota admission, containment
  and recovery; Brain uses a stdlib JSON-stdin client. The dispatch journal is
  outside the repository; a lost acknowledgement replays the same request/key.
  Nested workers cannot re-delegate. `--backend direct` keeps standalone discovery.
- **Adoption/cleanup:** foreign plans are previewed as data. Every source needs a
  destination or drop reason; cleanup requires a verified out-of-project archive
  (names, SHA-256, CRC, archive hash journaled) and refuses code, linked, escaping or
  private paths. Interrupted phases resume their journal.
- **Secrets:** source keeps only a project secret reference. Secret-dependent checks
  run only through an approved host adapter/scanner whose binding matches project,
  reference, command, adapter and scanner; otherwise only those actions are blocked.
  Known-pattern masking runs before log hashing; output caps and staged-byte export
  scans reject leaks and host-private paths. Credential-bearing tasks never delegate.
- **Attribution:** commits use the user's human Git identity. No AI/model/provider/bot
  author, `Co-authored-by`, generated-by, contributor or PR credit — for the director
  and every worker prompt.

## Limits

Hashes establish freshness, not truth or product quality. Review/approval records
are not authenticated identity. ProcessTree is process containment, not a
filesystem/network sandbox; host capability declarations do not install isolation.
Masking and text scans are partial defences, not universal DLP. Percentage quotas
cannot guarantee a token budget or stop another client exhausting an account.
Live providers, paid model chains and comparative small-model quality are not
measured. Store publishing remains outside scope.

## Next improvement

Measure before adding protocol: a small fixed evaluation set (one responsive UI
flow, one state/recovery feature, a user revision and a forced interruption taken
over by another agent), comparing capability levels on identical acceptance. Report
real token counters where available (otherwise "unknown"), wall time, retries,
first-pass acceptance and review findings; tune routing/effort from that data.

## Release procedure

1. Keep the version identical in `SKILL.md`, `SCHEMAS.md`, `brain.py`, both plugin
   manifests, `README.md`, `docs/PROJECT-OVERVIEW.md` and `CHANGELOG.md`.
2. Run the checks above.
3. Build `dist/project-brain-<version>.zip` (+ `.sha256`) from tracked files only;
   `dist/` is ignored and holds only the current package. Smoke-test the extracted
   `brain.py --version`.
4. Commit with the human identity and push. Installed skill copies are refreshed
   separately (Skills Manager); no consumer project is migrated by a release.
