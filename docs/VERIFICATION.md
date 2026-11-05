# Verification guide — Project Brain 3.11.0

3.11.0 adds the seven-item Turkish form and durable missing-choice follow-up.
The complete offline `test_brain.py` entry point passed on Windows Python 3.11.15.
The 43 `test_relay.py` checks pass on Windows Python 3.11.15 and 3.8.20, including real CLI
ask → clarify → policy confirmation, fresh follow-up deadlines, dispatch blocking,
resolved-answer retention, stale-session refusal, persisted CAP-only restrictions,
role-specific authorized native recovery, active/stopping holder authority, HTML
script escaping, unified quota preparation and graceful stop. An independent scoped
source review found the missing wiring, role/provenance and holder issues; fixes
and regressions were reviewed with no remaining scoped blocking finding.

Playwright renders at 390×844 and 1280×800 were inspected; missing-selection output,
native-fallback permission and reset were exercised with no horizontal overflow.
Artifacts are local under `output/playwright/`. The form copies a chat answer; it
has no direct host submit API. The host runs `setup wait/defaults`, so an inactive
host cannot autonomously enforce a wall-clock timer. Python 3.8 grammar and changed
protocol links pass; the skill entry remains below its 6,500-byte budget.
Boot GC keeps active/dirty/recovery evidence; it cannot erase host chat history or
force the current host model.

Installed CAP 2.2.0 compatibility: compact help/categories/catalog and all eight
pb-director/1 features were read from the real service. Both real-daemon checks
passed against the installed package: `test_pool_integration.py` (auto-start,
worker execution, fixed effort, no replay, isolated verification/integration) and
`tools/test_relay_integration.mjs` (START, HANDOFF, FAILOVER, TAKEOVER, COMPLETE;
final director task succeeded). Executors are synthetic; no provider inference,
paid fallback or unrelated workspace writes are claimed. The obsolete legacy-only
policy/category assertions in the transport test now also exercise compact CAP.
The local Skills Manager source refresh was hash-verified across the central
library and all 42 existing deployments (57 non-cache files each). Normal new
project-session orient/boot upgrades older project state with backups, deferring
read-only/merge/future-format cases; it installs no Windows login service.

3.10.0 makes setup and the Baton Relay safe to leave unattended (ADR-006,
contract `skills/project-brain/references/director-contract.md`). 33 offline
checks in test_relay.py use a fake CAP that implements pb-director/1: strict
relay policy (director tier, default same tier), quota-unknown last resort,
preflight table and refusal, same-tier resolution, token argument authority,
two-phase handoff/takeover with secretEnv, idle and deadline fields, older-skill
refusal, failover after a failed or silent successor, restart after a dead
director, unplanned-transfer bound and single notification, relay-owned versus
foreign `needs_review` locks, START_TIMEOUT and lost responses without penalty,
stray director cancellation, stale-record reset, confirmed/unconfirmed policy
edits, in-place upgrade of a live 3.9 record, stop/complete, max_handoffs, and
the one-batch setup question with the 5-minute default. Continuation regressions
also cover preserving a lost-acknowledgement successor, leaving a new unrelated
review lock untouched, explicit director profile/read paths, fast takeover task
identity, confirmation by the current holder and worker setup suppression.
The Pool adapter transport test preserves CAP's scoped task lease/worker marker
while filtering provider secrets. They pass under Python
3.11.15 and 3.8.20. A copy of a real 3.9 project's relay record and policy was
read by the new code with its confirmation hash unchanged.

User-facing setup questions/defaults now use Turkish conceptual names while
policy JSON and machine statuses stay compatible. Existing setup regressions
check the Turkish batch, saved defaults and timeout; inheritance still suppresses
questions for successors and workers.

End-to-end on 2026-11-05 through the installed CAP 2.1.1 service on a scratch Git
repository (not a user project). That CAP has none of the pb-director/1 features
yet, so `relay start --unverified` printed every missing guarantee. Live quota
skipped `codex-local` (3-6%) and, once known, `claude-local` (7%) below the 10%
threshold, and a later recover correctly ended `EXHAUSTED` with one CAP_NOTIFY.
After a restart with free candidates: handoff to `mcode-local`, which was killed
before takeover twice; `relay recover` failed over with fresh tokens, marked it
unhealthy after the second failure, printed the exact resolve command for each
leftover `needs_review` lock, and moved to `qoder-local`. The real Qoder successor
ran `relay takeover` (generation 2), wrote and committed relay.txt, accepted
PB-001 and ran `relay complete`. Events: START, HANDOFF, FAILOVER, FAILOVER,
TAKEOVER, COMPLETE. Its CAP task still ended `needs_review` (`INVALID_REPORT`),
which recover reported on the completed relay; locks were released manually
because this CAP lacks `resolve`/fingerprint release. This original live-provider
run did not exercise the new CAP mechanisms.

The subsequent `tools/test_relay_integration.mjs` check runs against the sibling
CAP source service with private data, port 0 and a scratch Git repository/local
bare remote. Real Python CLI -> JSON stdin -> CAP HTTP/MCP exercises verified
preflight, explicit director admission, secretEnv delivery, task identity and
self-acknowledgement. A synthetic native executor fails the first director before
takeover; the actual onExit watchdog invokes `relay recover`, preflights and starts
the next candidate, which takes over, commits/pushes to the local remote and
completes. Events: START, HANDOFF, FAILOVER, TAKEOVER, COMPLETE; final CAP state:
succeeded. No provider is called. Native tool observations are synthetic; this
proves cross-repository transport and recovery wiring, not provider permissions.
Deadline/idle behavior remains covered by offline PB/CAP tests.


3.9.0 adds the optional Baton Relay Policy (BRP). 11 offline checks cover strict
optional policy JSON, threshold and model-scoped quota windows, circular candidate
choice skipping exhausted/unknown accounts, hash-only tokens, the single-director
gate and boot line, handoff/takeover with predecessor CAP task cancellation, lost-
submit retry that voids the earlier successor, policy/checkpoint mutation blocking,
stop/complete authority, max_handoffs and damaged-record refusal. Policies without
`relay` validate unchanged. No Pool, provider or account was contacted by these
checks; real circulation depends on CAP accounts the user signed in once.

3.8.0 adds validated seven-source ESP, independent SP and explicit director QRP.
Tests cover strict bounded policy JSON, exact native/CAP identities, opaque
categories, user/default effort constraints, fresh-session policy-byte receipts,
environment/legacy override resistance, unknown cost/quality blockers and bounded
qualification metadata. No category name is treated as a capability score.

Native candidates are bound before launch; receipts must match. Tests exercise
serial capacity/drain, changed-policy PREPARED rejection, old-job readback and
same-origin internal worktree inheritance. New saved-policy workers use the
durable runs scheduler; legacy delegate is readback-only for them, preventing a
second capacity path. Missing-policy legacy APIs remain compatible; explicit
new-session boot requires all three choices, including for existing projects.

QRP tests cover actual saved handoff, idempotent PREPARED/ARMED state, account and
limit hashes, policy/checkpoint mutation, early/unknown quota, demonstrable window
renewal, cancellation before host deletion, late callbacks and one-shot consumption.
CLI regressions prove cancelling does not confirm unrelated pending ESP/SP and
response discovery cannot escape quota waiting. Main-agent quota differs from
worker quota/context-token capacity.

The actual Codex host supplied quota/account metadata. A paused same-chat
heartbeat was created then deleted to check host acknowledgement; no active test
alarm remains. The user subsequently cancelled QRP for this release session.
CAP current help/category/catalog readback is verified separately before publish;
no provider worker is needed to prove metadata compatibility. Portable host wake
and native identity remain host-dependent; uninterrupted coding is not guaranteed.

Validation: complete offline test_brain.py passed under Windows Python 3.11.15
and 3.8.20, including every new policy/control/orchestration and 14 QRP checks.
Python 3.8 grammar, local links, version and diff checks passed. Current CAP help,
category summary and catalog summary returned successfully with zero submitted
workers. The skill entry is 6,493 LF-normalized UTF-8 bytes (budget 6,500).
Independent scoped review found cancellation-confirmation, response-wait and
provider-default-effort issues; all fixed with regressions.

3.7.3 recognizes current CAP compact metadata (help-like policy, modelId/category/
effort, alternative count and paginated model memberships) alongside the legacy
format. Targeted checks cover overridable supported category defaults, preserved
legacy fixed effort, exact bounded membership lookup, malformed/hidden metadata,
review strength/identity, compact summaries and bounded --full detail. A real
read-only low/discovery selection passed on 2026-11-01 without submitting a worker.
New-session ESP/SP confirmation and continuation are protocol rules; there is no
new runtime ESP/SP parser or automatic host-level model restriction.

Validation: targeted test_agent_pool.py, test_pool_modes.py and test_session.py,
Python 3.8 grammar, local links, entry budget and diff checks passed. Native
independent review found and verified the opt-in detail fix; no remaining scoped
findings. Complete offline test_brain.py passed under Windows Python 3.11.15 and
3.8.20. This validates the adapter regressions, not live provider execution.

3.7.2 adds a read-only question/continuity path and low-tier discovery defaults.
`test_session.py` exercises CLI `brief` without Brain creation, migration, boot,
mapping, Pool calls or session writes; source/task/ledger/session bytes stay intact.
Large Unicode Resume and external fields remain valid JSON within 4096 UTF-8 bytes
(including newline), with explicit omissions, pending/readback counts and private
run sample lower bounds. IN_PROGRESS precedes REVIEW; READY scheduling is explicitly
not evaluated. Malformed task/ledger state is surfaced rather than repaired.
Selection tests preserve explicit task tiers/resource caps and reviewer H default,
default discovery to L, and distinguish compact from `--full` output.

At 3.7.3 the skill entry was 6,498 LF-normalized UTF-8 bytes versus
12,366 at the starting revision (47.5% smaller);
a 6,500-byte regression budget guards expansion.
Detailed authority/session rules moved to relevant WORKFLOW sections, rather than
being deleted. This is input size, not a measured reduction in billed/reasoning
tokens. The protocol covers SOLO, repeated waves and intervening questions; host
behavior outside Brain commands cannot be OS-enforced by a skill.

Validation: complete offline test_brain.py passed under Windows Python 3.11.15
and 3.8.20; Python 3.8 grammar, local reference links and diff checks passed.
Skills Manager refreshed the installed copy; five principal skill/runtime files
matched source SHA-256 across all 42 managed deployments. Scoped native independent review
found and verified the fix for active-focus precedence; no remaining actionable
findings in its scope. Runtime validation was offline; this adds no live-provider
certification or measured model-quality/token claim.

The subsequent ESP change is documentation only: actual Pool options
come through Pool's own skill; no catalog/API schema is specified by Brain. Native,
cheaper native, native pinned, solo, CAP category/catalog/pinned choices and
separate scheduling have a director-maintained durable record and explicit change
flow. Existing CLI does not parse that record; unsupported enforcement must not
be claimed. Entry-budget, example JSON, links and diff checks passed. Runtime was
unchanged. CAP's updated skill and a compact four-entry metadata page were read;
no worker job was submitted.

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

Optional pb-director/1 cross-repository relay integration (Node with CAP's source
dependencies installed; no Python runtime dependencies):

```text
node tools/test_relay_integration.mjs <Pool-source-root> <absolute-python-executable>
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
