# Changelog

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
