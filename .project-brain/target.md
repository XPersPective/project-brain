# Target Architecture
Status: CONFIRMED

## Goal
"Bu skill'i mükemmel hale getirmemiz gerekiyor. Hem frontend tarafında hem backend tarafında hem de state'ler durumunda. Yani bu skill her şeyi alıp götürebilmeli... UI güzel olmuyor bu skill'le yapıldığı zaman. İki, arka taraftaki mimarinin mükemmel olması gerekiyor. Yani bir mimari kurgulandığı zaman bir işin yürütücü tarafından zorluğu ölçülebilmeli aşağı yukarı ve başka alt ajanlara verebilmeli... CLI üzerinden mesela codex CLI'ya vesaire gibi benim sistemi önce sistemi tarayacak. Sistemdeki CLI şeyleri ajanları bulacak. Ondan sonra orada o ajanların token seviyeleri ya da bunlar çoğu şey token aboneliğine ait. Onların aboneliğine göre de iş yapabilecek. Yani onlara iş verecek. Kendi zor işleri yapacak. Yani yüksek modeller sadece mimariyi kurgulayacak, işleri kontrol edecek... küçük işleri alt ajanlara verecek ve kotayı bitirmeyecek... D:\repositories\store-otomaston ... O projede state durumları var. Oradaki alabileceğin iyi şeyleri al... yayın kısmı için ayrı bir skill yazacağım... O kısmı almayacağım. Oradan alabileceklerini al ve bu skill'i mükemmel hale getir. Başka bir ajan bir yerden aldığı zaman bunu devralabilmesi gerekiyor... open code da dahil. Bunların mümkünse küçük işleri düşük modellere, düşük eforla falan vererek token gözeterek işleri stabil bir şekilde baştan sona token bitmeden yapabilmesini sağlamak." (user, 2026-10-17)

## Target State
### Protocol
- Git-native, vendor-neutral multi-agent protocol (`SKILL.md`, `QUALITY.md`, `AGENTS_CLI.md`, `SCHEMAS.md`, `REFERENCE.md`).
- Enforce Frontend Design System Foundation + UI Triad (`[visual]`, `[interaction]`, `[accessibility]`) and Backend Clean Architecture + Sealed State Machine + Resilience proof (`QUALITY` findings block acceptance).
- High-tier models (`Tier H`) act as Architect/Director/Reviewer; low/medium models (`Tier L/M`) execute fully specified `READY` tasks at `low`/`medium` effort.

### Runtime
- Evidence-bound task lifecycle (`PLANNED -> READY -> IN_PROGRESS -> REVIEW -> DONE`, `BLOCKED`) with `start`, `check`, `evidence`, `review`, `accept`, `score`, `agents`, `delegate`, `legacy`, `migrate`, `doctor`; WAITING_USER is BLOCKED and READBACK_FIRST is a boot result.
- Mechanical difficulty & complexity estimator (`PB score`): 0–100 score, computed Tier (`L/M/H`), recommended Effort (`low/medium/high`), Risk floor (`LOW/MEDIUM/HIGH`), and split/delegation guidance.
- CLI Agent Discovery, Subscription Quota Tracker & Dispatcher (`PB agents scan|list|quota|select|merge`, `PB delegate`): scans `codex`, `claude`, `gemini`, `opencode`, `agy`, `qwen`, `aider`, `kilocode`, `mcode`, `kimi`, `omniroute`; checks live quota windows (`10%` worker reserve, `25%` director reserve); dispatches bounded tasks in `ProcessTree` and runs automatic `PB check`.
- Full backward compatibility with Project Brain schemas 0–4 (`migrate.py`) plus foreign state adoption (`legacy`: `.store-automation`, `.taskmaster`, `memory-bank`, `.kiro/specs`, `.factory`).

### Distribution
- Version `3.0.0` (schema 4, backward-compatible) across `SKILL.md`, `brain.py`, `plugin.json`, `.claude-plugin/`, `.agents/plugins/`, `gemini-extension.json`, `README.md`, `CHANGELOG.md`.
- Local agent installations and global rules updated so all installed agents use Project Brain 3.0.

### Confirmed follow-ups (2026-10-18; not implemented by PB-008)
- PB-009: At session start, cheap-agent inventory and cached model/CLI/access/quota summary; user confirms model groups/roles and additions/exclusions before inference. No automatic high-model or paid fallback.
- PB-010: Compact, verified transfer of useful foreign tracking state followed by recoverable removal of obsolete files/pointers; one plan on next boot.
- PB-011: After all project work is complete, remove this skill repository's own .project-brain development state and self-boot pointers, preserving source/tests/durable requirements.
- Preserve the main task when interrupted: record new messages in durable tasks/docs, keep Resume current, then continue. Full requirement: docs/design/09-session-pool-and-clean-adoption.md.

## Non-Goals
- Store publishing, Play Store / App Store upload, or Fastlane release automation (handled by a separate skill).
- Paid API fallback without explicit user permission or reading secret credential contents.

## Open Decisions
- None blocking; user explicitly authorized full design, implementation, and verification.

## Success Conditions
- `python skills/project-brain/scripts/test_brain.py` passes all v2 regression checks and all v3 checks (`score`, `start`, `check`, `evidence`, `review`, `accept`, `agents`, `delegate`, `legacy`, UI/Backend quality gates).
- `python skills/project-brain/scripts/brain.py validate` passes with 0 FAIL and 0 WARN.
- `python skills/project-brain/scripts/brain.py agents scan` discovers installed local CLI agents and live quotas cleanly.
- Master Prompt and architectural blueprint documented in `docs/design/07-v3-master-prompt.md`.
