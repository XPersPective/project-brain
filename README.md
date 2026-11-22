# Project Brain

Current release: **4.0.3** — [website](https://xperspective.github.io/project-brain/) · [changelog](CHANGELOG.md) · [CLI Agent Pool](https://github.com/XPersPective/cli-agent-pool).

**Git-native project memory and planning for coding agents.** Any agent — Claude, Codex, Antigravity, OpenCode or
another — can recover a project's recorded goal, architecture and task plan from the repository.
The protocol is designed for different model sizes; reliable execution still depends on the agent
following it and verifying the evidence. No chat history is required for the recorded state.

```text
session 1 (strong model)          session 2 (token limit hit)        session 3 (small model)
genesis: map, interview user  ->  executes PB-003..PB-005       ->   "continue": boot, PB-006, ...
writes target + task plan         commits each verified step         repairs plan with evidence
```

## Why

4.0.0 separates standalone core Project Brain (`solo` or host `native`, zero external
dependencies, single-line safe setup) from opt-in power features: [CLI Agent Pool](skills/project-brain/POOL.md)
(external CLI discovery/auth/quotas), [durable orchestration](skills/project-brain/ORCHESTRATION.md)
(SQLite WAL run ledger and isolated worktrees), [QRP](skills/project-brain/RECOVERY.md), and
[Baton Relay](skills/project-brain/RELAY.md). Native execution requires a host bridge; real
billed-token savings depend on provider counters.

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

## Protocol 1

Version 3.5 separates ownership Areas from verification Inputs and binds task proof
also to reconciled intent, dependencies and local tool/adapter identity. After init,
confirm Target, choose session EXEC/REV, record `security --ref none|<alias>` once,
write the task, then `reconcile` before `start`/`delegate`. DRAFT permits explicitly
bounded independent discovery. `progress` and `handoff` preserve small durable state;
intact proof is reused, not repeatedly regenerated.

See [the protocol reference](skills/project-brain/PROTOCOL.md) for exact commands,
revision handling and external secret adapter requirements. These guards are not
an OS sandbox or a guarantee of provider token usage/model judgment.

## Install

Requirements: Git and Python 3.8+ (stdlib only).

| Agent | Install |
|---|---|
| Claude Code | `/plugin marketplace add XPersPective/project-brain` then `/plugin install project-brain@project-brain` |
| Codex | `codex plugin marketplace add XPersPective/project-brain` then `codex plugin add project-brain@project-brain` |
| Any Agent Skills tool | `npx skills add XPersPective/project-brain` |
| Manual | copy `skills/project-brain/` into your agent's skills directory (e.g. `~/.claude/skills/`, `~/.codex/skills/`, `~/.gemini/config/skills/`, `~/.agents/skills/`) |
| CLI Agent Pool (optional, for `mixed` and `cap-*` multi-CLI execution) | `git clone https://github.com/XPersPective/cli-agent-pool.git && cd cli-agent-pool && npm ci --ignore-scripts && npm run setup` ([repo](https://github.com/XPersPective/cli-agent-pool) · [releases](https://github.com/XPersPective/cli-agent-pool/releases/latest)) |

When you set up a project, `brain.py init` adds a short block to the project's `AGENTS.md` (and to an
existing `CLAUDE.md` / `GEMINI.md`), so every agent that opens the repository loads the skill. For agents
that do not auto-load skills, add the same pointer to their global instruction file:

```text
# Project Brain
If `.project-brain/` exists in the project root, use the `project-brain` skill before any other work:
read <path-to>/skills/project-brain/SKILL.md and follow it (first step: its boot command).
```

## Use

External CLI agent discovery, authentication, quotas and execution live exclusively in the separate [CLI Agent Pool](https://github.com/XPersPective/cli-agent-pool) companion (legacy `--backend direct` and OmniRoute adapters were removed in 4.0). Standalone Brain runs in `solo` or host `native` mode with zero external dependencies.

At a new implementation session use `orient`, then `boot --new-session` and `setup ask`.
Safe core defaults are `native · parallel (auto) · QRP off · BRP off`. Confirm in one step
with `setup confirm`, or override inline via `policy --source solo|native|mixed|cap-catalog|cap-category --schedule parallel|serial --confirm`.
Opt-in power features (`mixed`/`cap-*`, durable SQLite `runs`, `QRP`, `BRP`) stay cleanly separated from the core workflow.
`PB qualify` provides optional advisory/override model tier caps without blocking fresh repositories.

Opted-in QRP checkpoints before the chosen director quota threshold and prepares a
host same-chat wake intent. Account/policy/checkpoint binding and verified renewal
guard one-shot resume; cancellation revokes locally before host deletion.
[Recovery](skills/project-brain/RECOVERY.md) covers supported host tools and limits.
No uninterrupted-execution or measured billed-token guarantee is claimed.
Same-session questions preserve choices/context; new-session continue confirms
saved settings while retaining unfinished jobs. Solo/native require no Pool.

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
brain.py orient   [root]   metadata-only project entry (auto-upgrades legacy Brain)
brain.py boot     [root] [--new-session] [--read-only]
                           state, target, plan, focus, progress board, unfinished runs and next action
brain.py board    [root] [on|off|status] [--force]
                           default-on zero-token Progress Board (also accepts show/hide/göster/gösterme)
brain.py setup    <ask|confirm|defaults|wait|recover-cap> [root] [--advanced]
                           default-safe single-line session confirmation and CAP recovery
brain.py policy   [root] [--source <src>] [--schedule serial|parallel] [--confirm]
                           view, configure inline, save and confirm ESP/SP/QRP/BRP
brain.py brief    [root]   strictly read-only <=4 KiB JSON status for questions
brain.py watch    [root] [--heal]   compact 1-line status monitor (<25 est. tokens)
brain.py map      [root]   compact repo overview + detected test/lint/build commands
brain.py init     [root]   create .project-brain/ skeleton + AGENTS.md pointer (never overwrites)
brain.py new root "title" [--priority P1] [--tier L|M|H] [--risk LOW|MEDIUM|HIGH] [--depends PB-001]
brain.py score    [task] [root] [--write] [--json]
                           measure task complexity (0..100), Tier (L/M/H), effort and risk floor
brain.py intake   [root] --item "<req>" [--relation related|question|new-work|cancel]
brain.py reconcile <task> [root] --note "<reason>"
brain.py progress  <task> [root] --next "<step>" [--failing "<err>"]
brain.py handoff   <task> [root]
brain.py start    <task> [root] [--agent <alias>] [--takeover "<reason>"]
brain.py check    <task> [root] [--timeout <sec>] [--as <alias>] [--rerun]
brain.py evidence <task> [root] --kind <kind> --note "<text>" [--criterion <id>] [--file <relpath>]
brain.py review   <task> [root] --reviewer <alias> --verdict PASS|BLOCKED [--finding "SEVERITY: text"] [--self-review]
brain.py accept   <task> [root] [--as <alias>]
brain.py runs     <plan|prepare|submit|observe|wait|verify|integrate|cancel|cleanup|status> [root]
                           opt-in durable SQLite orchestration with isolated worktrees (native or CAP)
brain.py qualify  [root] --route <r> --model <m> --tier L|M|H --note "<text>"
                           optional advisory model-fit override (non-blocking by default)
brain.py quota    <status|assess|prepare|arm|resume|cancel> [root]
brain.py relay    <status|start|assess|next|handoff|takeover|recover|stop|complete> [root]
brain.py agents   <scan|quota|list|select|mode> [root]
brain.py delegate <task> [root] [--cli <cli>] [--model <alias>] [--effort low|medium|high] [--dry-run]
brain.py changed  [root]   files and domains changed since their Current checkpoints
brain.py validate [root]   structure, executable-spec checks, UI Triad checks, size budgets
brain.py migrate  [root] [--apply]   convert a legacy Brain (schema <=3 or PROJECT_BRAIN.md)
brain.py legacy   [root] [--apply]   detect and adopt foreign planning systems (.taskmaster, .planning, etc.)
brain.py doctor   [root]   verify Python runtime, ProcessTree containment and Git readiness
```

Exit codes: 0 ok, 1 warnings / review or user feedback pending, 2 errors / blocked, 3 no Project Brain.

## What it runs, reads and writes

- Runs local commands: `git` (read-only queries during core `boot`/`changed`/`validate`, plus isolated worktree/commit/ff-merge operations when opt-in `PB runs` is used), the bundled Python scripts, configured `Verify` commands inside an OS-contained `ProcessTree` (`brain.py check`), and optional CLI Agent Pool RPC calls when you enable CAP (`mixed` / `cap-*`).
- Reads files inside the current repository. Writes `.project-brain/`, a short pointer block in the project's `AGENTS.md` (plus an existing `CLAUDE.md` / `GEMINI.md`), and the local agent registry `~/.project-brain/agents.json`.
- Never reads or stores secret credential values.
- Discovery is not access approval. Unknown or stale quota blocks worker dispatch;
  it needs an explicitly approved bounded job allowance to proceed. Model quality scores
  are routing estimates. Evidence hashes detect stale source/specs,
  while actual visual, interaction and architecture quality requires independent review.
- Store publishing, uploads, signing and release automation are outside this skill.

Machine-local run ledgers beside the actor registry track durable orchestration jobs (`PB runs`). Reservations survive crashes; inspect and read back uncertain jobs before retrying. Native host handoff is an explicit action for the parent, not a claim that a model has run. External CLI routing, auth and containment live exclusively in the companion CLI Agent Pool.
- Commits and pushes happen only through the agent, following `git.commit` / `git.push` in `config.yaml` and your platform's own permission rules.

Completed tasks keep their digest-bound Evidence and Review until committed. With no Git or deferred commits, DONE files stay in place so IDs and dependencies remain recoverable. A missing task by itself is not proof of completion.

## Repository layout

```text
skills/project-brain/   the skill: SKILL.md, WORKFLOW.md, PROTOCOL.md, QUALITY.md, POOL.md, ORCHESTRATION.md, RECOVERY.md, RELAY.md, REFERENCE.md, SCHEMAS.md, scripts/
.claude-plugin/         Claude Code plugin + marketplace manifests
plugin.json             portable plugin manifest (Codex)
.agents/plugins/        Codex marketplace
docs/                   PROJECT-OVERVIEW.md, VERIFICATION.md and accepted architecture decisions
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
