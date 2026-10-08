# Project Brain

**Git-native project memory and planning for coding agents.** Any agent — Claude, Codex, Gemini or
another, a frontier model or a small cheap one — continues a project exactly where the previous session
stopped, from the repository alone. No chat history needed, no re-scanning the codebase.

```text
session 1 (strong model)          session 2 (token limit hit)        session 3 (small model)
genesis: map, interview user  ->  executes PB-003..PB-005       ->   "continue": boot, PB-006, ...
writes target + task plan         commits each verified step         repairs plan with evidence
```

## Why

Long projects outlive sessions: tokens run out, sessions crash, you switch models or vendors. Project
Brain keeps the state where every agent can read it — in the repository — and holds every agent to one
protocol:

1. **State lives in files and commits, never only in chat.**
2. **The plan is the product.** Tasks are written so a weaker model with zero chat history can execute
   them: numbered steps with exact paths, checkable acceptance criteria, verify commands.
3. **Trust nothing unverified.** Each agent checks what it inherits and repairs the plan only with
   evidence, recorded in an ADR.

## How it works

```text
.project-brain/
├── current.md       where are we?      verified architecture + Map (path -> role)
├── target.md        where are we going? the user's Goal (verbatim), target state, open decisions
├── tasks/PB-*.md    what is left?      prioritized, executable task specs (finished ones are deleted)
├── constraints.md   rules that change decisions
├── decisions/       ADRs: rationale Git cannot keep
└── config.yaml      policy + exact test/lint/build commands
```

Git owns history: commit trailers mark checkpoints, commit bodies carry the evidence. A stdlib Python
script does everything mechanical, so the model spends no tokens on it:

```text
$ python skills/project-brain/scripts/brain.py boot
STATE: RESUME
git: main @ 4f1c2aa | last PB commit 4f1c2aa (= HEAD) | dirty 0 (+0 brain)
TARGET: CONFIRMED
PLAN: 3 open, 12 done
   PB-013 READY       P1 L Add Turkish date parser
   PB-014 PLANNED     P2 M Export to JSON  [deps PB-013]
   PB-015 BLOCKED     P2 H Store upload  [needs store credentials from the user]
FOCUS PB-013 (READY, P1, tier L, risk LOW): 2/2 acceptance open
RECENT: PB-012 by claude-haiku-5-5 (4f1c2aa); PB-011 by codex-agent (9ab01de)
LOAD: .project-brain/tasks/PB-013.md .project-brain/current.md (lines 3-40, 88-120) .project-brain/constraints.md
CMDS: test=python -m pytest -q | lint=ruff check .
NEXT: Takeover check, then the user's message. 'continue' or empty: start PB-013 and keep working the queue.
```

## Install

Requirements: Git and Python 3.8+ (stdlib only).

| Agent | Install |
|---|---|
| Claude Code | `/plugin marketplace add XPersPective/project-brain` then `/plugin install project-brain@project-brain` |
| Codex | `codex plugin marketplace add XPersPective/project-brain` then `codex plugin add project-brain@project-brain` |
| Gemini CLI | `gemini extensions install https://github.com/XPersPective/project-brain` |
| Any Agent Skills tool | `npx skills add XPersPective/project-brain` |
| Manual | copy `skills/project-brain/` into your agent's skills directory (e.g. `~/.claude/skills/`, `~/.codex/skills/`, `~/.gemini/skills/`, `~/.agents/skills/`) |

When you set up a project, `brain.py init` adds a short block to the project's `AGENTS.md` (and to an
existing `CLAUDE.md` / `GEMINI.md`), so every agent that opens the repository loads the skill. For agents
that do not auto-load skills, add the same pointer to their global instruction file:

```text
# Project Brain
If `.project-brain/` exists in the project root, use the `project-brain` skill before any other work:
read <path-to>/skills/project-brain/SKILL.md and follow it (first step: its boot command).
```

## Use

| You say | The agent does |
|---|---|
| "set up project brain" / `/project-brain` | Genesis: maps the repo once, asks you the questions that shape the target, writes target + roadmap |
| "continue" / "devam et" | Works the task queue until it is empty or everything left is blocked; commits each verified step |
| a new request mid-way | Adds it as a P1 task ahead of the backlog, so the next agent sees it too |
| "audit the plan" | Traceability, code spot-checks, executability probe of the next tasks |

Already using Project Brain 1.x (`.project-brain/` schema ≤3) or a single-file `PROJECT_BRAIN.md`?
`python <skill>/scripts/brain.py migrate` shows a preview; `migrate --apply` converts losslessly. Nothing is deleted.

## Helper script

```text
brain.py boot     [root]   state, target, plan, focus, recent work, files to load, next action
brain.py map      [root]   compact repo overview + detected test/lint/build commands
brain.py init     [root]   create .project-brain/ skeleton + AGENTS.md pointer (never overwrites)
brain.py new root "title" [--priority P1] [--tier L] [--risk HIGH] [--depends PB-001]
brain.py changed  [root]   files and domains changed by commits made outside the protocol
brain.py validate [root]   structure, executable-spec checks, size budgets
brain.py migrate  [root] [--apply]   convert a legacy Brain
```

Exit codes: 0 ok, 1 warnings, 2 errors, 3 no Project Brain.

## What it runs, reads and writes

- Runs only local commands: `git` (read-only queries such as `log`, `status`, `diff`, `ls-files`) and the
  bundled Python scripts. The agent itself runs your project's own test/lint/build commands from `config.yaml`.
- Reads files inside the current repository. Writes only `.project-brain/` and a short pointer block in the
  project's `AGENTS.md` (plus an existing `CLAUDE.md` / `GEMINI.md`), and only when you run `init` or
  `migrate --apply`.
- No network access, no telemetry, no credentials. It never stores secrets and tells agents not to.
- Commits and pushes happen only through the agent, following `git.commit` / `git.push` in `config.yaml`
  and your platform's own permission rules.

## Repository layout

```text
skills/project-brain/   the skill: SKILL.md, REFERENCE.md, SCHEMAS.md, scripts/
.claude-plugin/         Claude Code plugin + marketplace manifests
plugin.json             portable plugin manifest (Codex)
.agents/plugins/        Codex marketplace
gemini-extension.json   Gemini CLI extension manifest
docs/design/            design analysis and review notes (Turkish)
```

## Development

```bash
python skills/project-brain/scripts/test_brain.py
```

```bash
claude plugin validate .
```

See [CHANGELOG.md](CHANGELOG.md). Versions follow semver; the skill version lives in `SKILL.md` metadata,
the manifests and `brain.py --version`.

## License

MIT © XPersPective
