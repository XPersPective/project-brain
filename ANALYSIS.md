# Project Brain — Comprehensive Audit, Simplification & Verification Record (4.0.6)

- **Baseline Version:** `3.12.0` → **Released Version:** `4.0.6`
- **Audit & Verification Dates:** 2026-11-21 – 2026-11-22
- **Scope:** Multi-cycle architectural, protocol-vs-code, security/authority, concurrency, crash-recovery, UX/context-footprint, real-world E2E, live CAP token A/B benchmark, and companion CAP integration audit of `skills/project-brain/`.

> Durable architectural decisions live in [ADR-008](docs/design/decisions/ADR-008.md), current system architecture in [docs/PROJECT-OVERVIEW.md](docs/PROJECT-OVERVIEW.md), and ongoing verification checks in [docs/VERIFICATION.md](docs/VERIFICATION.md). This root summary preserves the 3.12.0 → 4.0.0 multi-cycle audit, measurements, and clean handoff state for future sessions.

---

## 1. Before vs After (`3.12.0` → `4.0.0`)

| Metric | Baseline (`3.12.0`) | Final (`4.0.0`) | Delta / Verification |
|---|---:|---:|---|
| Runtime Python modules | 20 files / 13,070 LOC (19-module SCC, 118 lazy internal imports) | 20 files / ~13,100 LOC (**0 circular imports, 0 lazy internal imports**) | Enforced by `test_v4_hardening.py` & `tools/build_release.py` |
| Python 3.8+ AST & stdlib-only | 3.8 syntax (runtime `fromisoformat` edge failures on 3.8–3.10) | 100% Python 3.8 AST across all tracked `.py` + custom `parse_iso_utc()` | Verified by AST & unit tests |
| Legacy `--backend direct` / OmniRoute / registry scanner | ~2,656 LOC (`runtime_agents.py`, `runtime_pool.py`, `runtime_discovery.py`, `AGENTS_CLI.md`) | **Removed** (ADR-008); external CLIs live exclusively in `cli-agent-pool` | Standalone `solo`/`native` has 0 external deps |
| `SKILL.md` entry size (LF UTF-8) | 6,358 B / 6,500 B budget | **4,160 B** / 4,500 B budget | **-34.6%** |
| `WORKFLOW.md` size (LF UTF-8) | 29,250 B (duplicate headings & rules) | **16,064 B** (deduplicated, single source of truth) | **-45.1%** |
| All skill docs & assets (LF UTF-8) | 168,547 B | **121,484 B** | **-27.9%** |
| Setup ceremony per new session | 7-item Turkish form + CDN HTML + `clarify` + 5×60s wait (QRP/BRP opt-out) | 1-line safe default (`native · parallel (auto) · QRP off · BRP off`) + `setup confirm` / inline `PB policy` | Opt-in `--advanced` power disclosure |
| `PB qualify` fresh-repo behavior | Hard `MODEL_QUALIFICATION_REQUIRED` deadlock | Optional advisory warning; explicit overrides strictly enforced | Hard ESP/paid/review gates preserved |
| Unused `speed` (`balanced`/`turbo`) | Stored placebo with 0 dispatch consumers | Removed from active schema/setup; legacy JSON tolerated on read | Verified in `test_v4_hardening.py` |
| `test_brain.py` inside `CLI_AGENT_POOL_WORKER=1` | **FAIL** (`test_brain.py:539`) | **100% PASS** (clean & CAP-worker env) | Scrubbed via `test_helpers.py` |

---

## 2. Iterative Multi-Cycle Audit & Remediation Summary

### Cycle 1 — Baseline Audit & 4.0.0 Core Refactor (ADR-008)
- [x] Extracted acyclic zero-internal-import foundation (`runtime_core.py`, `runtime_scoring.py`, `runtime_actors.py`), eliminating all 118 lazy internal imports and the 19-module strongly connected cycle.
- [x] Retired `runtime_agents.py`, `runtime_pool.py`, `runtime_discovery.py`, `AGENTS_CLI.md`, `assets/setup-form.html`, and superseded `docs/design/PROTOCOL-DISCUSSION.md`.
- [x] Separated Core (`solo`/`native`, safe single-line `setup ask`/`confirm`, inline `PB policy`) from opt-in Power features (`mixed`/`cap-*`, durable SQLite WAL `PB runs`, QRP, BRP).
- [x] Made `PB qualify` advisory/override metadata and retired unused `speed` while preserving backward compatibility on read.
- [x] Hardened QRP CAP normalization, BRP relay failover/wake/locking, orchestration worker commits/deletions, secret redaction, `.svg` scanning, `watch`, and release packaging checks (`tools/build_release.py`).

### Cycle 2 — Independent Two-Agent Adversarial Re-Audit & Fixes
Two fresh read-only auditors (Architecture/Docs/Hygiene and Security/Concurrency/Relay/QRP) plus live suite execution uncovered and closed the following defects:
- [x] **Lock self-deadlock (`runtime_core.py`):** made `file_lock()` and `project_lock()` thread-reentrant (fixing `legacy --apply` → `cmd_init`/`cmd_new` 15s deadlock on Windows).
- [x] **`Q.cancel()` crash (`runtime_quota_recovery.py`):** fixed missing `Path` import (`NameError`), added raw `policy_file_hash` binding so unconfirmed disk edits revoke on `quota resume`, and tightened CAP snapshot status allowlisting.
- [x] **CAP director policy escalation (`runtime_control.py`):** blocked `CLI_AGENT_POOL_WORKER=1` (including CAP relay directors) from `PB policy --file/--confirm`/quick-flags and `PB quota cancel`.
- [x] **Inline policy flag bugs (`runtime_control.py`, `runtime_executor_policy.py`):** defaulted `--qrp-threshold`, `--relay-threshold`, and `--relay-category` to `None` so standalone updates and default resets (`10`/`same`) work without clobbering existing `candidates` or thresholds; fixed invalid `PB policy set` message and empty `director_category: ""` validation.
- [x] **Baton Relay state-machine hardening (`runtime_relay.py`, `runtime_protocol.py`, `brain.py`):** allowed `STOPPING` baton holder to save Resume via `PB progress`/`PB handoff`; closed `relay recover --from-hook` worker guard bypass (returning exit 2 without `CAP_RETRY_AFTER`); added `pending_hash` CAS to `start()` stale reset and `wakeAt`; handled terminal lost-submit recovery, gen-1 host handoff wake recovery, consecutive non-progress recovery cap, `request_stop()` generation CAS, and `--from-hook`-gated `CAP_NOTIFY` for JSON stdout purity.
- [x] **Orchestration & verification hardening (`runtime_orchestration.py`, `runtime_runs.py`, `runtime_verify.py`, `runtime_security.py`):** enforced explicit `--self-review` in `REV=solo` `review()` and checked recorded review findings on `LOW` risk; flagged synthesized `INVALID_REPORT` reports with `decision_required: True`; refused `runs cancel` without `--force` when `backend_id` is missing and logged `FORCE_CANCELLED`; added `.candidate-merged` crash recovery to `runs verify`; added `PB-Agent`/`PB-Reviewer` commit trailers to `runs integrate`; made `runs status`/`report`/`export`/`plan` strictly read-only; added Git mode `120000` symlink refusal and NUL/UTF-16/ASCII-run secret scanning in `scan_staged()` and `snapshot()`.
- [x] **Portability, migration & CLI hygiene (`runtime_core.py`, `brain.py`, `migrate.py`, `runtime_adopt.py`, `runtime_agent_pool.py`):** added junction-safe `Core.iter_files()` across `os.walk`/evidence/verify/protocol loops; fixed POSIX `ProcessTree._close()` orphan process-group kill; fixed macOS `safe_private_path()` `/var` stop comparison; anchored `migrate_v0()` `Goal status:` to header/§1; rejected future non-`X.Y.Z` versions (`4.1`, `5.0`, `4.0.1-rc1`); guarded `migrate --apply` against active merges; set `sys.stdout.reconfigure(newline="\n")` so `brief` stays ≤4,096 B on Windows; fixed `watch_status()` `solo`/`unset` labels and `select_policy --group` under `cap-catalog`/`mixed`.
- [x] **Docs & test cleanup:** marked `ADR-007.md` partially superseded by `ADR-008.md`, completed `references/director-contract.md` fallbacks table, updated `README.md`, `CHANGELOG.md`, `docs/VERIFICATION.md`, and fixed `test_pool_integration.py` Windows CAP daemon teardown (`stop --force`).

### Cycle 3 & Cycle 4 — Live CAP A/B Experiment Findings & Deep Edge-Case Hardening (`4.0.1`)
- [x] **Cold `boot --new-session` `TAKEOVER_CHECK: SKIP` & `review: PASS valid` visibility (`brain.py`, `runtime_protocol.py`, `runtime_verify.py`):** added `check_session=False` for read-only observational `boot` digest checks (never weakening execution/mutation gates) so `boot --new-session` accurately displays `TAKEOVER_CHECK: SKIP` and `review: PASS valid on current digest (DO NOT re-review; run accept)` when proof and review are intact.
- [x] **Digest-verified uncommitted batch `DONE` tasks (`_done_task_intact()` in `brain.py`):** uncommitted `DONE` tasks exempt their `Areas` from `STATE: DIRTY` / `dirty outside active task` ONLY while their current digest and contract still match their recorded `- accept: DONE | digest=<hex> | contract=<hex>` evidence line; post-acceptance tampering immediately flips `STATE: DIRTY` and `TAKEOVER_CHECK: REQUIRED`.
- [x] **Generated bytecode/cache noise filtering (`_is_generated_noise()` in `brain.py`):** excluded `__pycache__/`, `*.pyc`, `*.pyo`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.DS_Store`, `Thumbs.db` from `dirty` and `UNMAPPED`.
- [x] **Review progress & unified finding acceptance (`V.finding_accepted()` in `runtime_verify.py` & `brain.py`):** `PB review` updates `progress.next` (`Review passed on current digest; run accept and commit` or `Fix review findings, recheck, then re-review`), and `V.finding_accepted()` unifies finding-waiver validation across `review()`, `accept()`, and `cmd_boot()`.
- [x] **Clean migration, worker prompts & helper deduplication (`migrate.py`, `runtime_actors.py`, `runtime_context.py`, `runtime_scoring.py`, `runtime_executor_policy.py`, `runtime_security.py`, `PROTOCOL.md`):** removed false `VERSION_CHECK: auto-upgraded project` on unstarted schema-4 tasks lacking `Owner:`, updated worker prompts to prevent redundant planning-skill autoloads, and removed duplicate internal helpers.

---

## 3. Real-World E2E, Companion CAP & Context-Footprint Measurements

### A. Offline & Companion CAP Suites (Windows, Python 3.11.15)
- `python -B skills/project-brain/scripts/test_brain.py` (clean env): **PASS (exit 0)** — all 20 suites including 15 QRP, 45 Relay/Setup, and `test_v4_hardening.py`.
- `CLI_AGENT_POOL_WORKER=1 python -B skills/project-brain/scripts/test_brain.py`: **PASS (exit 0)**.
- `python -B skills/project-brain/scripts/test_pool_integration.py --pool-entry <cli-agent-pool>/bin/pool.js`: **PASS (exit 0)** against CAP v2.29.2.
- `node tools/test_relay_integration.mjs <cli-agent-pool> <python>`: **PASS (exit 0)** (`START -> HANDOFF -> FAILOVER -> TAKEOVER -> COMPLETE`, `directorState: succeeded`).

### B. External Small-Project E2E (`med-tracker` Medication Reminder CLI)
Tested in an isolated temporary Git repository outside `project-brain` with **zero protocol violations** and **zero AI attribution** in Git history:
- Exercised full lifecycle: `map`, `doctor`, pre-init read-only `brief`, `init`, `orient`, `boot --new-session`, `setup ask` / `ask --advanced` / `confirm`, inline `policy`, `security`, `intake`, `new`, `score --write`, `validate`, `reconcile`, `start`, `check` + `PASS CACHED` reuse, `review` (verified `REV=solo` blocks without `--self-review` and passes with it), `accept`, human Git commit, `boot` `gc_brain` cleanup, `watch --heal`, `brief` (LF-only ≤4,096 B), `progress`/`handoff`, `ESP=mixed` durable `PB runs` (`prepare`/`submit`/isolated worktree worker commit/`receipt`/`verify`/`integrate` with `PB-Agent` trailer/`cleanup`), and cold-session `boot --read-only`.
- Measured CLI output footprint (UTF-8 bytes; estimated tokens = `ceil(bytes/4)`, not provider billed tokens):
  - `watch --heal`: **66 B** (~17 est. tokens)
  - `map`: **232 B** (~58 est. tokens)
  - `orient`: **475 B** (~119 est. tokens)
  - `setup ask`: **591 B** (~148 est. tokens)
  - `brief`: **939 B** (~235 est. tokens)
  - `boot --new-session`: **976 B** (~244 est. tokens)
  - `boot --read-only` (cold handoff): **1,433 B** (~359 est. tokens)
  - `runs context`: **1,829 B** (~458 est. tokens)

### C. Live `cli-agent-pool` 2-Session Cold-Takeover A/B Token Benchmark (`opencode/deepseek-v4.1-flash-free`)
Executed on two identical 3-feature `medapp` repositories with an uncommitted interruption after Session 1 and a zero-history cold takeover in Session 2 (exact OpenCode session token counters):

| Metric (OpenCode Session Counters) | **Arm A (No Project Brain)** | **Arm B (Project Brain 4.0.x)** | Delta (Arm B vs Arm A) |
|---|---:|---:|---:|
| **Session 1** (Features 1+2, uncommitted) | 6 turns · 12 tools · **73,625** total tokens (`12,825` non-cached) · 29.9s | 7 turns · 13 tools · **90,076** total tokens (`12,636` non-cached) · 39.6s | Non-cached **-1.5%**, total **+22.3%** |
| **Session 2 — Cold Takeover** (0 history, close 1+2 & build/commit 3) | **10 turns · 15 tools · 163,812 total tokens** (`17,380` non-cached · `2,179` output · `709` reasoning) · 43.7s | **6 turns · 6 tools · 74,209 total tokens** (`11,617` non-cached · `1,301` output · `167` reasoning) · 31.2s | Total **-54.7%** · Non-cached **-33.2%** · Output **-40.3%** · Reasoning **-76.4%** · Tools **-60.0%** |
| **Combined (2 Sessions)** | **16 turns · 27 tools · 237,437 total tokens** (`30,205` non-cached · `4,443` output · `863` reasoning) · 73.6s | **13 turns · 19 tools · 164,285 total tokens** (`24,253` non-cached · `3,849` output · `541` reasoning) · 70.8s | **Total -30.8% · Non-cached -19.7% · Output -13.4% · Reasoning -37.3% · Tools -29.6%** |
| **Hidden Acceptance Suite** | PASS | PASS | 100% pass on both arms |

---

## 4. Known Limits & Handoff Notes for Future Sessions
- **Platform coverage:** Verified on Windows Python 3.11.15 with Python 3.8 AST parsing enforced across all `.py` files; live POSIX/Linux/macOS and Python 3.8.x interpreter execution were not run in this Windows environment.
- **Provider billed tokens:** Input/output footprint reductions (`SKILL.md` -34.6%, `WORKFLOW.md` -45.1%, docs -27.9%) are measured UTF-8 byte sizes, not provider billed-token counters; never advertise unmeasured billed-token savings.
- **Next steps if extending 4.0.x:** Keep `runtime_core.py` at zero internal imports, keep `SKILL.md` under 4,500 LF bytes, run `python -B skills/project-brain/scripts/test_brain.py` and `python tools/build_release.py` before any commit, and never add AI/bot Git attribution.
