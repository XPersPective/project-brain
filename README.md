# Project Brain — Git-Native Project Cognition

A persistent execution and continuity protocol for coding agents.

## Files

| File | Purpose | When to read |
|---|---|---|
| `SKILL.md` | Runtime protocol — boot, execution loop, rules | Every session start |
| `REFERENCE.md` | Edge-case recovery procedures | Only when facing a specific problem |
| `SCHEMAS.md` | File templates, commit trailer schemas, validation rules | When creating or modifying Brain files |
| `scripts/brain.py` | Stdlib-only helper for session classification, validation, context | Called from SKILL.md procedures |

## Installation

Copy the `project-brain` folder to your agent's skill directory:

```text
~/.gemini/config/skills/project-brain/
~/.agents/skills/project-brain/
<project>/.agents/skills/project-brain/
```

## Helper Script

```bash
python scripts/brain.py boot      <root>              # Classify session state
python scripts/brain.py validate  <root>              # Check Brain integrity
python scripts/brain.py context   <root>              # Show minimal context files
python scripts/brain.py checkpoint <root> [--domain D] # Find last checkpoint
python scripts/brain.py changed   <root> [--domain D]  # Files changed since checkpoint
```

Requires Python 3.8+. Stdlib only — no dependencies.

## Architecture

```text
repository reality       (implementation truth)
+ Git history            (durable execution history)
+ Project Brain          (semantic layer)
= reliable next action
```

Project Brain preserves what Git cannot cheaply preserve:
architectural understanding, approved targets, user intent,
constraints, unresolved decisions, and active work.

## License

MIT
