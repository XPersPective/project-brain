# Project Brain

**Git-native project memory and planning for coding agents.** Any agent — Claude, Codex, Gemini or
another — can recover a project's recorded goal, architecture and task plan from the repository.
The protocol is designed for different model sizes; reliable execution still depends on the agent
following it and verifying the evidence. No chat history is required for the recorded state.

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
script computes the mechanical state; the agent still reviews its output and verifies code:

```text
$ python skills/project-brain/scripts/brain.py boot
STATE: RESUME
git: main @ 4f1c2aa | current baseline 4f1c2aa (= HEAD) | dirty 0 (+0 brain)
TARGET: CONFIRMED
PLAN: 3 open, 12 done
   PB-013 READY       P1 L Add Turkish date parser
   PB-014 PLANNED     P2 M Export to JSON  [deps PB-013]
   PB-015 BLOCKED     P2 H Verify service recovery  [needs test environment access]
FOCUS PB-013 (READY, P1, tier L, risk LOW): 2/2 acceptance open
RECENT: PB-012 by claude-haiku-5-5 (4f1c2aa); PB-011 by codex-agent (9ab01de)
LOAD: .project-brain/tasks/PB-013.md .project-brain/current.md (lines 3-40, 88-120) .project-brain/target.md .project-brain/constraints.md
CMDS: test=python -m pytest -q | lint=ruff check .
NEXT: Route the user's request before tests or writes. If authorized, run the takeover check; 'continue' starts the queue.
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

At a new session, a low/mid-cost discovery worker (or local metadata tools when no
worker is approved yet) prepares the model pool. Project Brain shows available
CLI/native routes, access, billing and dated quota information. You approve or edit
roles/models/efforts before jobs run; it does not fall back to the director's account.
`agents session --new`, `agents approve`, `agents revoke` and `agents settle` expose
that protocol. See [the session contract](skills/project-brain/AGENTS_CLI.md).

| You say | The agent does |
|---|---|
| "set up project brain" / `/project-brain` | Genesis: maps the repo once, asks you the questions that shape the target, writes target + roadmap |
| "continue" / "devam et" | Works the task queue until it is empty or everything left is blocked; commits each verified step |
| a new request mid-way | Records it as a P1 task and completes that request plus prerequisites; unrelated backlog waits |
| "audit the plan" | Traceability, code spot-checks, executability probe of the next tasks |

Already using Project Brain 1.x (`.project-brain/` schema ≤3) or a single-file `PROJECT_BRAIN.md`?
`python <skill>/scripts/brain.py migrate` shows a preview; `migrate --apply` converts it and preserves
original inputs in `.project-brain/migration-backup/` for review. Nothing is deleted; unrecognized content
may need manual reconciliation. Missing target approval becomes DRAFT.

For another tracking system, preview/import with `legacy`/`legacy --apply`, reconcile
useful goals, constraints, decisions and open work into one compact Brain, then use
`legacy --prepare`, `legacy --verify --note "<review>"`, `legacy --cleanup`. Every old
file needs a reviewed destination or drop reason; cleanup verifies an outside-project
archive and current source/destination hashes before removal. Source code and unrelated
team docs are protected. Interrupted cleanup resumes its journal instead of reimporting.

## Helper script

```text
brain.py boot     [root]   state, target, plan, focus (with complexity score & delegation hint), files to load, next action
brain.py map      [root]   compact repo overview + detected test/lint/build commands
brain.py init     [root]   create .project-brain/ skeleton + AGENTS.md pointer (never overwrites)
brain.py new root "title" [--priority P1] [--tier L|M|H] [--risk LOW|MEDIUM|HIGH] [--depends PB-001]
brain.py score    [task] [root] [--write] [--json]
                           measure task complexity (0..100), Tier (L/M/H), effort (low/medium/high), and delegation readiness
brain.py agents   <scan|quota|list|select|merge>
                           discover installed CLI coding agents, read live subscription quotas, and select optimal models
brain.py delegate <task> [root] [--cli <cli>] [--model <alias>] [--effort low|medium|high] [--dry-run]
                           dispatch a Tier L/M task to a CLI worker inside ProcessTree + auto-run check
brain.py start    <task> [root] [--agent <alias>] [--takeover "<reason>"]
brain.py check    <task> [root] [--timeout <sec>] [--as <alias>]
brain.py evidence <task> [root] --kind <kind> --note "<text>" [--criterion <id>] [--file <relpath>]
brain.py review   <task> [root] --reviewer <alias> --verdict PASS|BLOCKED [--finding "SEVERITY: text"]
brain.py accept   <task> [root] [--as <alias>]
brain.py changed  [root]   files and domains changed since their Current checkpoints
brain.py validate [root]   structure, executable-spec checks, UI Triad checks, size budgets
brain.py migrate  [root] [--apply]   convert a legacy Brain (schema <=3 or PROJECT_BRAIN.md)
brain.py legacy   [root] [--apply]   detect and adopt foreign planning systems (.store-automation, .taskmaster, etc.)
brain.py doctor   [root]   verify Python runtime, ProcessTree containment, Git, and CLI agent readiness
```

Exit codes: 0 ok, 1 warnings / review or user feedback pending, 2 errors / blocked, 3 no Project Brain.

## What it runs, reads and writes

- Runs local commands: `git` (read-only queries such as `log`, `status`, `diff`, `ls-files`), the bundled Python scripts, configured `Verify` commands inside an OS-contained `ProcessTree` (`brain.py check`), and local CLI coding agents when you run `brain.py agents scan` or `brain.py delegate`.
- Reads files inside the current repository. Writes `.project-brain/`, a short pointer block in the project's `AGENTS.md` (plus an existing `CLAUDE.md` / `GEMINI.md`), and the local agent registry `~/.project-brain/agents.json`.
- Never reads or stores secret credential values.
- Discovery is not access approval. Unknown or stale quota blocks worker dispatch;
  it needs an explicitly approved bounded job allowance to proceed. Model quality scores
  are routing estimates. Evidence hashes detect stale source/specs,
  while actual visual, interaction and architecture quality requires independent review.
- Store publishing, uploads, signing and release automation are outside this skill.

Machine-local session files beside the agent registry bind user-selected roles and
execution configuration. Changes require reapproval. Reservations survive a crashed
CLI; inspect the actual result and settle the job before retrying. Native host handoff
is an explicit action for the parent, not a claim that a model has run. Configured
argv/stdin adapters allow additional installed CLIs without adding a dependency.
- Commits and pushes happen only through the agent, following `git.commit` / `git.push` in `config.yaml` and your platform's own permission rules.

Completed tasks keep their digest-bound Evidence and Review until committed. With no Git or deferred commits, DONE files stay in place so IDs and dependencies remain recoverable. A missing task by itself is not proof of completion.

## Repository layout

```text
skills/project-brain/   the skill: SKILL.md, QUALITY.md, AGENTS_CLI.md, REFERENCE.md, SCHEMAS.md, scripts/
.claude-plugin/         Claude Code plugin + marketplace manifests
plugin.json             portable plugin manifest (Codex)
.agents/plugins/        Codex marketplace
gemini-extension.json   Gemini CLI extension manifest
docs/design/            design analysis, audit, and v3.0 master prompt
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
