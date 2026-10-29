# Changelog

## 3.5.1 — 2026-10-29

- Make "no AI contributor credit" a core protocol rule: the director and every worker
  prompt use the human Git identity and never add AI/model/bot author, `Co-authored-by`,
  generated-by, contributor or PR credit.
- Consolidate superseded audit/delivery reports into [docs/VERIFICATION.md](docs/VERIFICATION.md);
  keep the overview and accepted ADRs. Remove obsolete release archives and bytecode.

## 3.5.0 — 2026-10-29

- Add protocol-1 target/domain/constraint reconciliation, DRAFT discovery boundaries,
  deterministic risk normalization and separately scoped verification Inputs.
- Bind checks to dependency/configuration/tool/host-adapter freshness, reuse valid
  receipts and avoid completed Pool-job RPC/check repeats. Keep explicit readback.
- Add bounded durable progress/handoff records, repeated-failure and explicit check
  budget guards, reviewer registration/identity revalidation and safe retention.
- Keep only project secret aliases in source; require approved external scoped
  adapters/scanners for secret-dependent checks, never delegate credential-bearing
  tasks, sanitize final logs and fail closed on rejected/excessive output.
- Scan staged bytes before strict acceptance; reject malformed/private records and
  public handoffs containing host-private paths. Preserve all uncertain operations.
- Add adversarial strict-protocol tests and independent cold lifecycle evaluation.
  See [production verification](docs/VERIFICATION.md) for limits.

## 3.4.0 — 2026-10-29

- Keep Brain tracking artifacts together; establish a project-specific external
  secret/access reference once, without embedding personal directories or values.
  Document host isolation and raw-log limits; see the long-run architecture audit.
- Ask once for EXEC/REV resource modes; reset choices with `agents mode --new`,
  optionally bind them to host `PB_SESSION_ID`, and keep native/SOLO discovery offline.
- Preserve quality/independence floors across all resource caps; require an explicit
  SOLO audit/review rather than generating a PASS in acceptance. `--force` cannot
  widen P-L/P-ML; P-ALL permits high-tier Pool dispatch.
- Reuse scoped verification only with intact current logs and typed attachments;
  outside-Areas edits still require investigation. Bound Pool stdout, keep full logs.
- Upgrade supported old state with raw-input backups; finalize version-only upgrades,
  reject future state, and offer `boot --read-only` for non-mutating inspection.
- Collect only unchanged committed closed work and recoverable evidence; retain
  unknown/dirty artifacts, active logs and unreconciled migration originals.
- Consolidate boot/handoff/quality guidance without prescribing a visual style.
  Installed copies remain managed separately through Skills Manager.
- Add adversarial handoff/cleanup/review/migration regressions. See
  [verification guide](docs/VERIFICATION.md) for verification and limits.

## 3.3.1 — 2026-10-19

- Document Pool 1.4 project/installed skill attachment source resolution and unchanged RPC compatibility.
- Require artifact/Verify evidence rather than treating a completed CLI turn as a successful project.
- Keep worker nesting, owner filters/effort and Windows native sandbox boundaries intact.
- Align both plugin manifests with the distributed skill/runtime version.

## 3.3.0 — 2026-10-19

- Use the separate CLI Agent Pool for normal discovery, exact model identity,
  owner strength/effort policy, quota reserves and contained worker execution.
- Automatically wake Pool through its editor-neutral JSON stdin transport; keep
  the shared daemon outside short-lived metadata process containment on Windows.
- Persist task-bound requests, strength and idempotency keys outside the project;
  recover lost acknowledgements and poll existing jobs without replaying writes.
- Keep Brain's scoring, local research, source evidence and independent review;
  enforce task-bound reviewer strength and block recursive Pool delegation.
- Preserve explicit standalone `--backend direct` / `--registry` operation.
- Add offline transport/policy/recovery checks and a real synthetic-worker
  integration check without provider inference or user workspace changes.

## 3.2.1 — 2026-10-18

- Preserve previously measured quota windows when a partial response omits, nulls or drops them, including Codex refresh and configured metadata commands.
- Share one timeout budget across OmniRoute health checks, daemon startup and readiness polling.
- Refuse built-in OmniRoute chat as a coding worker: it returns text without repository tools. Catalog discovery remains available; execution requires an explicit coding-agent adapter.
- Expand adapter placeholders once so literal placeholder text inside prompts remains unchanged.

- Remove superseded development plans and machine-specific audit notes; preserve runtime, tests, current protocol and architecture decisions.

## 3.2.0 — 2026-10-18

- **OmniRoute Auto-Start, Full Catalog & Worker Dispatch (`runtime_agents.py`)**:
  - Automatically checks local OmniRoute server health (`/api/health`) and starts `omniroute serve --daemon --no-open --no-tray` outside `ProcessTree` when offline during `agents scan` or `delegate`.
  - Queries `omniroute api models get-api-models --output json` (with `models --output json` fallback) to discover the complete un-truncated model catalog (`fullModel`, `model_id`, `id`) and registers `omniroute:<model>` routes with `low|medium|high|default` effort support.
  - Adds first-class non-interactive `omniroute chat --stdin --no-history -m <model> [--reasoning-effort <effort>]` worker dispatch.
- **Retire `gemini` CLI in favor of Antigravity (`agy`)**:
  - Removes `gemini` CLI agent discovery and worker adapter (`agy` provides Google Antigravity / Gemini 3.1 Pro & Flash models), purges stale `gemini` entries from `~/.project-brain/agents.json`, and removes `gemini-extension.json`.
- **Windows CLI Economy, Pool & Security Hardening (`runtime_discovery.py`, `runtime_pool.py`, `runtime_verify.py`, `runtime_adopt.py`)**:
  - Zero-subprocess `snapshot_agents` for instant `agents session --new` proposals and deadline-bounded `agents scan` (`budget_exhausted` / `deferred`).
  - Deduplicated Win32 + Windows Store app discovery (`installed_ai_apps`) and bundled ZCode CLI detection.
  - Multi-window quota floor enforcement (`_quota` / `_inventory` / `_pool_status`), Windows junction reparse-tag protection (`is_link`), atomic `fsync` before replace, and strict registry schema validation (`_validate_registry`).

## 3.1.0 — 2026-10-18

- Explicit project/session model proposals, user-controlled roles/efforts/billing and configuration-bound approval before actual delegation.
- Bounded allowances for explicitly approved unknown-quota routes; reserve floors, persisted job reservations and readback/settlement after interrupted work.
- Native-host handoff and configured argv/stdin adapters alongside installed CLI routes; low-cost metadata discovery without assumed provider access.
- Recoverable, trace-verified foreign-plan cleanup and final removal of this repository's own development plan (consumer skill sources remain).

## 3.0.0 audit corrections — 2026-10-18

- Close model-override, task-status and same-model-review bypasses; enforce current risk floors and HIGH full-suite checks.
- Bound quota probes and stdin delivery; protect Windows command arguments and linked log paths.
- Refuse unknown/stale quota and director-reserve worker fallback; distinguish discovery from authorized access.
- Recognize both External formats, prioritize readback on boot, and require UI Triad even on untyped tasks.
- Preserve imported task detail and filter publishing across supported foreign task sources.
- Reuse existing design/architecture, plan risk probes and real journeys, and document honest privacy, schema and runtime limits.

## 3.0.0 — 2026-10-17

- **Task Complexity Scoring (`brain.py score`)**: Deterministic `0..100` complexity scorer computing effective `Tier` (`L|M|H`), recommended reasoning effort (`low|medium|high`), surface risk floor (`LOW|MEDIUM|HIGH`), UI Triad completeness, and CLI worker delegation eligibility (`DELEGATABLE`, `LEAD_ONLY`, `SPLIT_FIRST`).
- **System CLI Agent Discovery & Live Subscription Quota Tracking (`brain.py agents`)**:
  - `agents scan` discovers installed CLI coding agents (`codex`, `claude`, `gemini`, `opencode`, `agy`, `qwen`, `aider`, `kilocode`, `mcode`, `kimi`, `omniroute`) and populates `~/.project-brain/agents.json`.
  - `agents quota` queries supported live subscription rate limits (Codex JSON-RPC `account/rateLimits/read`); auth status/model listings from other CLIs are separate from remaining quota.
  - `agents select` enforces a `10%` worker reserve floor and a `25%` director reserve floor so `Tier L/M` worker tasks automatically shift to secondary/free CLI pools before exhausting primary subscription quotas.
- **Sub-Agent CLI Worker Delegation (`brain.py delegate`)**: Dispatches `READY`/`IN_PROGRESS` `Tier L/M` tasks to non-interactive CLI workers (`codex exec`, `opencode run --pure`, `claude -p`, `gemini -p`, `agy --print`, `qwen -p`) inside `ProcessTree` with a compact zero-history prompt, followed by automatic `brain.py check`.
- **Digest-Bound State Machine & Verification (`start`, `check`, `evidence`, `review`, `accept`)**:
  - Full lifecycle `PLANNED -> READY -> IN_PROGRESS -> REVIEW -> DONE` (`BLOCKED`, `WAITING_USER`, `READBACK_FIRST`).
  - `ProcessTree` containment (Windows JobObject `KILL_ON_JOB_CLOSE` / POSIX session process group) with isolated Python bytecode cache.
  - Cryptographic `areas_digest` (LF-normalized SHA-256) and `contract` digest binding for machine checks, non-machine evidence, and independent reviews.
- **Frontend UI & Backend/State Excellence Rubrics (`QUALITY.md`, `AGENTS_CLI.md`)**:
  - Mandatory Design System & Token Foundation (ADR + first UI milestone), UI Verification Triad (`[visual]`, `[interaction]`, `[accessibility]`), and blocking `QUALITY` review findings.
  - Backend Clean Architecture layer boundaries, explicit sealed state machines, boundary validation, idempotency, and up/down migration verification.
- **Foreign Planning System Adoption (`brain.py legacy`)**: Detects and imports tasks from `.planning`, `.taskmaster`, `memory-bank`, `.kiro`, and flat checklists while filtering out store-publishing/distribution tasks.

## 2.1.0 — 2026-10-08

- Reconcile source drift against actual per-domain checkpoints; PB mentions no longer hide changes.
- Require completion evidence before satisfying dependencies; retain DONE+Evidence until committed.
- Reserve task IDs from Git paths and legacy backups; new task scaffolds start PLANNED.
- Load global target and domain context reliably during handoff.
- Preserve quoted/custom commands and supported config fields; reject unsupported config explicitly.
- Back up migration input, retain task priority/tier, infer no target approval and finalize schema last.
- Fix Python 3.8/3.9-incompatible file writes; add interrupted migration and recovery regressions.
- Keep narrow and read-only requests within scope; protect pre-staged user changes at checkpoints.
- Document the architectural audit and unmeasured cross-model/platform limitations.

## 2.0.1 — 2026-10-08

Packaging only, no protocol change: logo and icon (`assets/`), privacy policy, directory listing
fields for Anthropic's directory and the OpenAI plugin directory, "What it runs" section in the README.

## 2.0.0 — 2026-10-08

First public release.

### Added
- `brain.py boot` prints one screen: state, target status, prioritized plan, focus task with its next step
  and open acceptance items, recent closed tasks with the agent that closed them, the exact files (or line
  ranges of a long `current.md`) to load, test/lint/build commands and the next action.
- `map`, `init`, `new`, `changed`, `validate`, `migrate` commands; `--version`.
- Task schema 4: `Priority` (P1-P3), `Tier` (L/M/H), `## Steps`, checkbox acceptance; READY means an
  executable spec a weaker model can follow.
- Target `Status: DRAFT|CONFIRMED` and a user-owned `## Goal`.
- Protocol: intake routing for user messages, takeover check, evidence gate for plan changes, plan audits
  (every 5 closed tasks) and a final audit, interview step for genesis/adoption, discovery focus rule.
- Lossless migration from schema ≤3 and from the single-file `PROJECT_BRAIN.md` format.
- `AGENTS.md` pointer written by `init`/`migrate` so any agent loads the skill.
- Packaging for Claude Code, Codex, Gemini CLI and Agent Skills tools.

### Changed
- SKILL.md rewritten around the script; edge cases moved to REFERENCE.md and formats to SCHEMAS.md.
- External commits are those after the newest commit mentioning a `PB-` ID or `[PB]`.
- Format problems are warnings, never a stop; only a missing Current architecture makes a Brain INVALID.

### Fixed (from 1.0.0)
- Completed task IDs could be reused; partial commits were counted as completions.
- First dirty path was truncated; domain checkpoints missed `all` and comma lists.
- Dependencies were read from anywhere in a task file; READY-with-open-dependency check was inverted.

## 1.0.0 — 2026-09-23

Internal release: Git-native protocol, current/target architecture, task files, checkpoint trailers,
edge-case reference, schemas and a helper script.
