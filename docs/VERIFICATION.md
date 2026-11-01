# Verification guide — Project Brain 3.7.1

3.7.1 adds `test_startup.py` to the complete regression entry point. It covers
automatic orientation/boot conversion without Git/HEAD, raw-byte backups, task
and Resume/External continuity, idempotency, read-only startup, deferred merge/
rebase maintenance, future-version refusal before session reset, and unknown
single-file refusal without initializing Brain. Startup conversion uses no model.
The full offline suite passed on Windows Python 3.8.20 and 3.11.15.

3.7.0 final validation (2026-11-01): full test_brain.py exited 0 under Windows Python
3.8.20 and 3.11.15. Separate Pool 1.8.1 real-daemon/synthetic-CLI integration exited
0. Python 3.8 grammar, local links, manifest versions and diff checks passed.
The 64-file release ZIP passed CRC/SHA-256, extracted CLI and production-regression
checks; two consecutive index-identical builds produced the same SHA-256.

3.7 adds opt-in durable orchestration without changing legacy delegation. The
production regressions in `test_orchestration_production.py` use protocol 1 with
confirmed intent, immutable actual worker identity, a distinct native reviewer and
the existing source/environment-bound check/review/accept gates. They are included
in `test_brain.py` alongside `test_orchestration.py`.

An independent read-only auditor reproduced launch-policy, candidate-contract,
identity, commit-hook and destination-hook defects during development. These are
fixed and covered by regressions. The final scoped independent review (including
rejection from a linked worker after lost merge acknowledgement) found no
reproducible release-blocking P1; that is not a universal correctness guarantee.

Coverage includes two actual OS clients contending for capacity, serial drain of
prepared/running jobs, immutable exact-key recovery, normalized same-model review
rejection despite missing registry records, copied-session authority, candidate
and destination mutation rejection, collected-task merge readback, retained bad
candidates, rejection of inspected partial results without automatic retry,
hash-checked log transfer, and readback-only restore into a different
clean Git clone while the original job stays RUNNING.

The separate real CLI Agent Pool 1.8.1 daemon test uses a synthetic CLI. It proves
actual isolated edits plus default-protocol start/check/accept/integrate through
the unchanged Pool RPC schema and actual selected model alias. It proves transport
and artifact handling, not paid-provider model quality or quota availability.

On 2026-11-01 the Codex collaboration host launched a real read-only native review
worker against a temporary fixture, collected its structured report, and left the
source unchanged. A second real worker was observed RUNNING, interrupted through
the host, then observed INTERRUPTED before CANCELLED was recorded. State/result
readback used new Python processes and the persisted ledger. A malformed first
report was corrected as report formatting in the same job, without replaying work.
The host did not report exact model identity or token counters; they remain unknown.
Other hosts and arbitrary provider/model combinations are not certified by this test.

The skill entry was reduced from 19,877 to 12,059 LF-normalized UTF-8 bytes by
moving detailed rules to WORKFLOW.md. Applicable rules remain mandatory. This is
not a billed-token/reasoning benchmark. `runs metrics` preserves failures/unknowns,
rejects mismatched acceptance contracts, and does not claim the proposed 50% pilot
target when real counters are absent. Token savings remain an unmeasured performance
objective, not an advertised release guarantee.

3.6.1 adds the Pool 1.8 request/effective-capability terminology. Catalog metadata
is distinct from native authorization and provider quota; legacy text-only imports
do not remove coding CLI tools. Native denial is still a blocker, never bypassed.

Maintained record of how this source is verified, which invariants the tests
protect and which limits remain. It replaces the former per-release audit and
delivery reports (11–18 under `docs/design/`); those remain in Git history and are
not active work or authorization. Update this file instead of adding new reports.

## Repeatable checks

3.6 verification covers Pool 1.7 response/execute, compact reports, independent wait,
mandatory protocol-1 session choices and fresh-session resets, serial/parallel
settings, metadata-only orientation, complete multipart intake/focus/handoff,
editable Current architecture inputs, compact catalogs and immutable old jobs.
The migration fixture upgrades 3.5.1 with raw backups and no dispatch replay.
The synthetic live integration exercises Brain -> execute -> MCP -> worker edits
-> compact report -> independent Verify. Solo/native remain independent of Pool.
Python 3.8 grammar checks pass; provider token savings are not measured. Source
scope/test reuse and smaller metadata/catalog output reduce repeated context,
but a skill cannot OS-enforce an editor that writes outside the Brain commands.
On the local installed catalog, the previous complete status serialized to 65,044
characters and the default compact catalog to 4,313, with no model inference.
This measures response size, not billed tokens or model reasoning consumption.
Installed semantic skill files are hash-checked across 42 managed deployments;
the legacy Antigravity CLI copy is backed up and junction-linked to that central
skill so subsequent updates reach it. User projects are not batch-migrated.

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

All Python files must parse with Python 3.8 grammar. Windows runtime checks use
Python 3.8.20 and 3.11.15. The private host-adapter fixture resolves the interpreter
path to avoid an installation junction; runtime link rejection remains enforced.
POSIX execution is not claimed without a separate actual POSIX run.

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

Native receipts declare host observations, not authenticated identity or measured
model strength. Unknown identity cannot authorize independent review. Literal
search is paginated and scan-budgeted, not a semantic dependency graph. Conflicts
need explicit repair/rebuild and fresh checks. Dirty worktrees and request keys
are retained. Restore relocates private observations only: imported jobs cannot
be submitted, cancelled, snapshotted, integrated or cleaned by the copy. No remote
process-control transfer or distributed/network-filesystem scheduler is claimed.

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
3. Stage reviewed source, then `python tools/build_release.py`. It builds
   `dist/project-brain-<version>.zip` + `.sha256` from Git-index bytes only and
   smoke-tests extracted version/CLI commands. Rebuild to check reproducibility.
   `dist/` is ignored; preserve older user archives rather than deleting blindly.
4. Commit with the human identity and push. Installed skill copies are refreshed
   separately (Skills Manager); no consumer project is migrated by a release.
