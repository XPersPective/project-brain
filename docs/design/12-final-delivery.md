# Project Brain 3.2.1 delivery

Release date: 2026-10-18. Project schema 4; session schema 1.

This patch preserves quota windows on partial responses, bounds OmniRoute startup,
refuses text-only chat as a coding worker and fixes recursive adapter substitution.
See [audit](15-runtime-audit.md) and [changelog](../../CHANGELOG.md).

## Repeatable verification

```text
python -B skills/project-brain/scripts/test_brain.py
python -B skills/project-brain/scripts/brain.py --version
git diff --check
```

The full suite covers task lifecycle, migration/recovery, review rules, process
containment, approval/reservation races, quotas, routing, archive cleanup and discovery.
Tests use temporary repositories, local processes and mocked metadata, not paid models.
The audit passed on Windows/Python 3.11. All 16 Python files parsed with Python 3.8
grammar; this is not Python 3.8/POSIX runtime proof.

Live provider validation, Z.AI quota and missing-CLI installation/login remain
environment-dependent. No independent second-agent review was performed in this patch.

## Release scope

Source, skill references, tests and accepted decisions remain. Obsolete plans and
machine-specific notes live in Git history. Bytecode caches are not release source.
Skills Manager keeps the existing entry, local source, preset and deployment targets.
The library was updated through `skills-manager-cli skills update project-brain`;
all 21 source files matched all 40 existing deployments by SHA-256. The library
contains no bytecode cache files. The Default preset and skill ID were preserved.
Source push and skill deployment do not migrate consumer projects. Existing Store
Automation projects were explicitly excluded from inspection and migration.
