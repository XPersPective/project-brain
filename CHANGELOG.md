# Changelog

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
- **Foreign Planning System Adoption (`brain.py legacy`)**: Detects and imports tasks from `.store-automation`, `.taskmaster`, `memory-bank`, `.kiro`, and flat checklists while filtering out store-publishing/distribution tasks.

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
