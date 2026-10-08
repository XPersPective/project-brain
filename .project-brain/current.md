# Current Architecture

## Runtime
- Python CLI, stdlib only; read-only Git subprocess queries. Advertises Python 3.8+; baseline tested on 3.11.15.
- Skill instructions run through the host coding agent; no server or network service.

## Map
- `skills/project-brain/SKILL.md` — agent workflow.
- `skills/project-brain/SCHEMAS.md`, `REFERENCE.md` — formats and exceptional workflows.
- `skills/project-brain/scripts/brain.py` — parsing, Git state, boot, new, validate.
- `skills/project-brain/scripts/migrate.py` — legacy conversion.
- `skills/project-brain/scripts/test_brain.py` — temporary-repository self-checks.
- `README.md`, `docs/design/` — purpose and design evidence.
- `plugin.json`, `.claude-plugin/`, `.agents/plugins/`, `gemini-extension.json` — distribution.

## Domains
### Protocol
Status: VERIFIED
Sources: `skills/project-brain/*.md`, `README.md`, `docs/design/**`
- Current, target and unfinished tasks separated; Git trailers hold history.
- Scope follows the current request; read-only questions precede repairs/tests. DONE+Evidence is committed before cleanup.
- `docs/design/06-audit.md` records the 2026-10-08 audit, regression evidence and empirical limitations.

### Runtime
Status: VERIFIED
Sources: `skills/project-brain/scripts/**`
- Seven commands; Markdown and a two-level config subset. Baseline self-check passes.
- Per-domain checkpoints preserve unreconciled changes; verified completion gates dependencies.
- New tasks start PLANNED; domain LOAD includes Current and target context. Configuration round-trips quoted commands; migration keeps original input and finalizes schema last.

### Packaging
Status: OBSERVED
Sources: `plugin.json`, `.claude-plugin/**`, `.agents/plugins/**`, `gemini-extension.json`, `assets/**`, `PRIVACY.md`, `CHANGELOG.md`
- Version 2.0.1 in manifests, skill metadata and runtime.

## Known Unknowns
- Cross-vendor/small-model reliability and live marketplace installation are not established by this audit.
- Claude manifest validation passes with five ignored directory-metadata warnings. Python 3.8 syntax checked; runtime tests use 3.11.15.
