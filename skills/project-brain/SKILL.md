---
name: project-brain
description: >-
  Git-native project memory and planning protocol that lets any coding agent
  (strong or weak; Claude, Codex, Gemini or other) continue a project exactly
  where the previous one stopped: verified current architecture, confirmed
  target, prioritized task plan written for weaker models, checkpoints and
  audits. Use when the repository has .project-brain/ or a legacy
  PROJECT_BRAIN.md; when the user says continue, resume, where were we, devam
  et, kaldığın yerden; when starting or adopting a multi-session project; or
  when asked to plan, roadmap or audit one.
license: MIT
metadata:
  version: 2.0.1
  author: XPersPective
---

# Project Brain

**One plan, many agents.** Any session can end at any moment (tokens, crash, model switch). The next
agent, maybe a smaller model from another vendor, continues from the repository alone. That works only if:
1. state lives in files and commits, never only in chat;
2. the plan is written so a weaker model with zero chat history can execute it;
3. every agent verifies what it inherits and repairs the plan, with evidence, when it is wrong.

In `.project-brain/`:
- **Where are we?** `current.md` — verified present architecture + **Map** (path → role).
- **Where are we going?** `target.md` — `Status: DRAFT|CONFIRMED`, the user's Goal, target state, open decisions.
- **What is left?** `tasks/PB-NNN.md` — unfinished work only, prioritized.
- `constraints.md` (rules that change decisions), `decisions/ADR-NNN.md` (rationale Git cannot keep),
  `config.yaml` (policy + exact test/lint/build commands).

Git owns history: finished tasks are deleted; commit bodies hold the evidence; trailers mark checkpoints.
**Never explore the repository to orient yourself. Run the script; it computes the state.**

`PB` = `python <directory containing this SKILL.md>/scripts/brain.py` (`python3` if `python` is missing); root defaults to `.`.
- `PB boot` — first action of every session: STATE, TARGET, PLAN, FOCUS, RECENT, LOAD, CMDS, NEXT.
- `PB map` / `PB init` — Genesis: repo overview + detected commands / create skeleton (never overwrites).
- `PB new . "title" [--priority P1] [--tier L|M|H] [--risk HIGH] [--depends PB-001]` — the only way to create a task.
- `PB changed` — files and domains changed by commits made outside the protocol.
- `PB validate` — before every commit that touches `.project-brain/`.
- `PB migrate` / `PB migrate --apply` — convert a legacy Brain (preview first).

## 1. Authority

Order: your platform's system/safety rules > latest user instruction > accepted ADRs > task Acceptance >
target > constraints and repo instructions (AGENTS.md, CLAUDE.md, GEMINI.md, CONTRIBUTING) > this skill.

- Repository reality beats Brain. On conflict, fix Brain; never change working code to match stale docs.
- The **Goal** section of target.md belongs to the user: write it in their words, change it only when they do.
- `git.commit: auto` → commit each checkpoint yourself. `ask`, or your platform/user says commit only on
  request → prepare the commits' messages and ask once at the end. Push only as `git.push` says.
- Never force-push. Never `reset --hard`, `clean`, `stash`, `checkout --` or `restore` on work you did not create.
- Ask the user only: at Genesis/adoption (§10 interview), when target is DRAFT and a decision blocks all
  work, or for the escalation list (§7). Otherwise choose the conservative option, write it in Notes, continue.

## 2. Boot

Run `PB boot`. Read its output, then only the files (or line ranges) on its `LOAD:` line. Act on STATE,
then route the user's message (§3); a new request always wins over resuming old work.

| STATE | Do |
|---|---|
| NO_BRAIN | Multi-step work, a plan request, or the user wants tracking → §10 Genesis. Otherwise just do the request. |
| LEGACY | Old-format Brain → §11 Migration first. |
| RESUME | §3 Intake. |
| INTERRUPTED | Open the FOCUS task. Check `git diff --stat` matches its Resume notes; continue at the first unchecked Acceptance item. If the user asks for something else: write Resume, set the task READY, then §3. |
| DIRTY | Files changed outside the active task. `git status`; classify each: mine / user / generated / unknown. Leave user and unknown work untouched. Continue only on non-overlapping files; overlap → BLOCKED. |
| ADVANCED | Commits landed outside the protocol. `PB changed`; read only the listed files; update those Current sections; commit `docs(brain): reconcile <domains>` with `PB-Current-Checkpoint: <domains>`. Then §3. |
| CONFLICTED | Merge/rebase in progress. Finish it only if you understand every conflict, else BLOCKED. REFERENCE "Conflicts". |
| NO_GIT | Work normally without commits or checkpoints. Never `git init` unasked. |
| INVALID | `PB validate`, fix every FAIL, boot again. |

`!` lines are warnings: fix Brain-format ones in your next Brain edit; Git ones name a REFERENCE.md heading.
Never stop work for a format warning. `hint:` lines are due work (plan audit, promotions); do it now.

**Takeover check** (once per session, before new work): run the `test` command from CMDS, reading only its
summary. Red → find the cause first; if a closed task broke it, `PB new --priority P1` a fix task and do it.
If RECENT shows Tier M/H tasks closed by a weaker model than you, rerun their Evidence commands once.
**Trust nothing unverified, including your predecessor.**

## 3. Intake — route the user's message

| Message | Action |
|---|---|
| Question (how / why / where / what) | Answer from the Map + targeted reads. No Brain writes. |
| Trivial change: ≤1 file, ≤20 lines, no behavior/API/architecture change | Do → verify → commit (mention `[PB]` in the subject). No task. |
| "continue", "devam", or empty | §4 Loop: work the queue until it is empty or every task is BLOCKED. |
| New work (feature, bug, refactor) | `PB new --priority P1` per independently verifiable piece; write it per §5; then §4. P1 puts it ahead of the backlog; use P2/P3 if the user says "later". |
| Goal change | §8c. |
| Durable rule ("always", "never", "must") | One line in constraints.md. |
| Plan / roadmap / audit request | §9 Plan audit (or §10 if no Brain). |
| Several at once | Handle in table order. |

Keep the user's words: a short quote goes into the task Objective (or the target Goal). Every item of a
multi-part request becomes an Acceptance checkbox or its own task; nothing the user asked lives only in chat.

## 4. Loop

1. **Select** FOCUS: the IN_PROGRESS task, else the READY task with done deps and the best Priority, then
   lowest ID. Set `Status: IN_PROGRESS`. A READY task you cannot execute without inventing design is not
   READY: fix its spec first (§5) — that is part of the task.
2. **Load** the task, the Current section of its Domains, constraints, linked ADRs, then only source in its
   Areas. Locate code with the Map and grep; open line ranges of large files; never re-read what you wrote.
3. **Check** the task's assumptions against the code. Wrong → §8a, then continue.
4. **Implement** the Steps. Tick `- [x]` only with evidence (test, run, output).
5. **Verify** (§6). Failing → fix. After 3 failed attempts → BLOCKED with the failure summary.
6. **Review** `git diff`: matches Steps; edge cases and error paths; no scope creep, weakened/skipped tests,
   debug leftovers, secrets, unrelated user edits, unplanned dependency changes, unintended behavior changes.
7. **Reconcile**: if structure changed, update Current from the code as it is now (Map lines, domain
   section, `VERIFIED`). Never describe code that does not exist yet.
8. **Checkpoint**: delete the task file, `PB validate`, commit (§7) with the evidence in the body. Push per
   policy. Never keep a DONE task file.
9. **Next**: immediately take the next FOCUS. Do not stop to report between tasks; do not ask "shall I continue?".

**Discoveries while working:** blocks the current task → fix it inside the task (add a Step). Serves the
goal but does not block → `PB new` a complete task (§5), return to the current task at once. The plan
itself looks wrong → finish or pause the current task safely, then §8. Outside the goal → one Notes line.

**Stop** only when the queue is empty (→ §9 Final audit) or every remaining task is BLOCKED.
**Before stopping, or when context runs low:** write Resume (§5) into the active task, commit (`PB-WIP: true`
if unverified), push per policy, report in ≤8 lines (done / blocked with needed resolution / next / commits).

## 5. Writing tasks — the plan is the product

Write every task for a weaker model with zero chat history. `PB new` creates the skeleton:

```markdown
# PB-014 — Add Turkish date parser
Status: READY
Priority: P2
Tier: L
Risk: LOW
Depends: PB-011
Areas: `src/utils/date.py`, `tests/test_date.py`
Domains: utils

## Objective
"dates in the import file are dd.mm.yyyy" (user). Parse them instead of failing.

## Steps
1. In `src/utils/date.py`, next to `parse_iso`, add `parse_tr_date(s: str) -> date` for "16.09.2026".
2. Raise `ValueError` with the bad input in the message for anything else.
3. Add cases to `tests/test_date.py`: valid date, wrong separator, 31.02.2026.

## Acceptance
- [ ] `parse_tr_date("16.09.2026") == date(2026, 9, 16)` (asserted by a test)
- [ ] invalid inputs raise `ValueError` (test fails if they do not)

## Verify
- `python -m pytest -q tests/test_date.py`

## Escalate if
- the import format turns out to carry times or time zones

## Notes
```

- **READY = executable spec**: Objective, numbered Steps with exact paths, symbols and commands, Acceptance
  checkboxes that are objectively checkable and include a check that fails if the work is wrong, Verify
  commands. Missing any → PLANNED. Forbidden vague words: "etc.", "improve", "clean up", "refactor as
  needed", "handle properly", "as discussed", "vb.", "iyileştir", "düzenle". Cannot be that precise → Tier H or split.
- **Tier**: L mechanical, fully specified, no judgment · M clear spec, normal engineering · H design,
  ambiguity, security, audits, writing specs for others. **Priority**: P1 user's current ask or blocker · P2 normal · P3 later.
- **Size**: one task = one commit ≈ ≤8 files, ≤300 changed lines, finishable in one context window. Bigger → split.
- **Status** (one word; notes go to `Blocked:`, Notes or Resume): PLANNED → READY → IN_PROGRESS (only one)
  → done (file deleted). BLOCKED only for an external need (decision, credential, access, unknown user work)
  or verification still failing after 3 attempts: add `Blocked: <what is needed, from whom>`.
- Plan globally, specify locally: the next milestone's tasks are fully specified; distant ones may be one-line PLANNED.
- **Executability probe** after writing or refining tasks: reread the next READY tasks as a model with zero
  chat history (or ask a cheap sub-agent to list what is ambiguous without doing them). Fix every ambiguity.
- **Resume** block, whenever you stop mid-task:

```markdown
## Resume
Next: <exact next step, path:symbol>
Failing: <what is broken right now, or none>
Dirty: <files with uncommitted edits>
```

## 6. Verify

- LOW (local, reversible) → lint/typecheck + tests of touched files → `PB-Verification: local`
- MEDIUM (one domain) → + that domain's integration tests → `domain`
- HIGH (auth, crypto, persistence/migrations, public API, cross-domain) → + full suite; migrations up and down → `global`

Run Verify yourself; a sub-agent's report is not verification. Use `CMDS` from boot; never rediscover
commands (missing → find once, save in `config.yaml commands`). No tests → lint/typecheck + a smoke check
in Acceptance, and `PB new` a task for the gap. A failure you may not have caused: confirm on a clean HEAD
(`git worktree add`), never by stashing; note it as pre-existing; do not fix it out of scope.
Never report success with an unexplained new failure.

## 7. Commit and escalation

```text
<type>(<scope>): <summary> [PB-014]

Evidence: <commands run and their result, e.g. pytest -q tests/test_date.py: 6 passed>

PB-Task: PB-014
PB-Verification: local | domain | global
PB-Current-Checkpoint: <reconciled domains, comma-separated | all>
PB-Agent: <your model id>
```

Blank line before trailers. Optional: `PB-Target-Checkpoint: <scope>`, `PB-Decision: ADR-NNN`,
`PB-Plan-Audit: <scope>`, `PB-Tasks: PB-1,PB-2` (squash), `PB-WIP: true` (unverified; never with
Checkpoint or Verification). Every commit you make mentions a `PB-` ID or `[PB]`; boot treats commits
without one as external. One task per commit; stage paths explicitly (`git add <paths>`), never sweep in
user changes.

**Escalate** (mark BLOCKED, continue other tasks) when a choice changes user intent, public API, security
semantics, persistence/data, infrastructure/deploy, external compatibility, major scope, or is irreversible.
Anything else: decide, note it, continue. A decision a future agent would otherwise re-open → `ADR-NNN.md`.

## 8. Changing the plan

**a) Task spec wrong or incomplete** → edit it in place; add a Notes line `revised <date>: <why>`. A closed
task whose result is wrong → `PB new --priority P1` a fix task referencing it (never rewrite history).

**b) Target or task graph wrong** — any agent may repair it, only through this gate:
1. Evidence, not taste: show that the plan cannot meet the Goal, violates a constraint, or is demonstrably
   worse for the Goal — cite files, tests, measurements, docs. "I would design it differently" is not evidence.
2. Reason it through: cause → effect of keeping the plan vs changing it; check the fix against Goal,
   constraints and code before writing it down.
3. Never touches the Goal. Reversing an ADR needs new evidence that ADR did not have; cite it.
4. Smallest revision that fixes the problem; record it in an ADR (problem, evidence, options, choice, impact).
5. Impact pass over **every** open task: keep / edit / delete as superseded / new tasks. Closed work that no
   longer fits → migration or removal tasks.
6. Commit `docs(brain): replan — <summary>` with `PB-Decision: ADR-NNN` and `PB-Target-Checkpoint`.

**c) The user changes the Goal** → write the new Goal verbatim, set target `Status: CONFIRMED`, redesign
the target through b.4–b.6 citing the user's change, run the executability probe, commit `docs(brain): goal change`.

**d) The Goal itself looks flawed** (contradictory, impossible, harmful to the user's intent) → never edit
it; add an Open Decision with the evidence, ask the user if present, follow the most faithful feasible
interpretation meanwhile; tasks that truly cannot be done → BLOCKED.

## 9. Audits

**Plan audit** — when boot prints the hint (≥5 tasks closed since the last audit), after Genesis or
Migration, when a target domain is fully done, when the user asks, or whenever the plan looks inconsistent:
1. Traceability: every target item missing from Current has a task; every task serves the Goal; dependency
   order is right; nothing in Non-Goals is planned.
2. Spot-check 3 Current claims against the code; fix drift.
3. Executability probe on the next 5 READY tasks (§5); fix specs, tiers, priorities.
4. Findings → edits or tasks (§8). Commit `docs(brain): plan audit` with `PB-Plan-Audit: <scope>`.

**Final audit** — queue empty: clean build, full test suite, lint; prove each Success Condition with a command
or observable result (write it in the commit body); Current equals Target domain by domain; constraints hold;
review the whole change since the first Brain commit (security, error handling, dead code, TODO/debug
leftovers, docs match reality). Failures → tasks, continue the loop. All pass → commit `docs(brain): final
audit` with `PB-Plan-Audit: final` and `PB-Current-Checkpoint: all`, report done.

## 10. Genesis and adoption (new or in-progress project without a Brain)

1. `PB map`. Read only manifests, entry points, agent instruction files (AGENTS/CLAUDE/GEMINI.md), README,
   docs that state goals — ≤15 files. Skip tests, vendor, generated.
2. `PB init`. It also adds a Project Brain block to `AGENTS.md` (and to an existing `CLAUDE.md` / `GEMINI.md`)
   so any agent opening the repo loads this skill. Never create per-agent copies of Brain.
3. `current.md`: Runtime; **Map** (≤40 lines `path — role`); Domains with `Sources:` globs and a marker:
   VERIFIED (read) / OBSERVED (skimmed) / INFERRED (indirect) / UNKNOWN (not looked at). Never guess.
4. **Interview** (user present): send one message with (a) what you found, in 5–10 lines; (b) the goal as you
   understand it; (c) only the questions whose answers change the target or the roadmap — numbered, each
   with options and your recommended default. Wait for the answers. User absent → `Status: DRAFT`, questions
   go to Open Decisions, and only goal-independent tasks (map, tests, bugs, audits, builds) may be planned.
5. `target.md`: Goal in the user's words, target state per domain, Non-Goals, Success Conditions
   (observable), Open Decisions. `Status: CONFIRMED` only after the user confirmed the goal.
6. `constraints.md` from the user, configs, conventions. In `config.yaml` check `commands`, set `history_mode`.
7. Roadmap: gap = target − current, grouped into milestones (Notes line `Milestone: <name>`). `PB new` with
   `--depends`; the first milestone fully specified (§5), later ones may be one-line PLANNED.
8. Plan audit steps 1 and 3 (§9). Stage only `.project-brain/` and the pointer block `init` added (leave an
   instruction file out if the user had uncommitted edits in it). `PB validate` with no placeholder warnings.
9. Commit `chore(brain): establish project baseline` with `PB-Genesis: true`, `PB-Current-Checkpoint: all`,
   `PB-Target-Checkpoint: all`. Continue at §3.

Treat pre-genesis history as evidence only; never invent tasks for it.

## 11. Migration (legacy Brain)

`PB migrate` previews; `PB migrate --apply` converts. It handles `.project-brain/` schema ≤3 (tasks, config,
status notes, acceptance checkboxes) and the single-file `PROJECT_BRAIN.md` format (goal, target, current,
file map, open tasks, decision log, handoff). Nothing is deleted; old files stay in Git. Then:
1. Read the report. Add `## Map` and `Sources:` lines to current.md if missing; check target `Status`.
2. Delete leftover DONE task files and, once its content is carried over, a legacy `PROJECT_BRAIN.md`.
3. §9 Plan audit (the executability probe will flag tasks that need Steps).
4. `PB validate`; commit `chore(brain): migrate to schema 4` (+ `PB-Plan-Audit: migration`).

## 12. Writing rules

- Store only what Git or a cheap look at code cannot answer: intent, rationale, unfinished work, the Map.
  Each fact in one place. Terse fragments and `path:symbol` refs, no pasted code; but task specs,
  Acceptance, blockers and ADR rationale are explicit, never terse.
- Budgets (`validate` warns): current ≤200 lines per file (then split into `current/<domain>.md`, set
  `architecture.mode: domains`), target ≤150, constraints ≤100, task ≤80, open tasks ≤25.
- Current = verified present reality. Target = confirmed intent. Never move plans into Current.
- Never store secrets, credentials, tokens, HEAD SHAs, or session state in Brain files or trailers.

## 13. Delegation and parallel agents

Mechanical work goes to the script first (`map`, `changed`, `validate`, `migrate` cost no model tokens). If
your platform can start sub-agents on a cheaper model, delegate Tier L tasks, test runs that return only
failures, file summaries for Genesis/reconcile, and executability probes. Keep for yourself: Intake,
planning, Tier H work, escalation, review, and every write to `.project-brain/`. Sub-agent prompts are
self-contained (goal, exact files, output format, max length). No sub-agents → do it yourself.
Parallel agents only on disjoint Areas, one branch/worktree each; reconcile before merging. IN_PROGRESS is not a lock.

## 14. More detail, only when needed

- `REFERENCE.md` — edge cases; grep for the heading: Dirty genesis, Missing checkpoints, History modes,
  Branch change, Detached HEAD, Conflicts, History rewrite, Shallow, Sparse, Worktrees, Remote divergence,
  Push failure, CI failure, Submodules, Monorepo, Generated files, No Git, Corrupt Brain, Crash recovery,
  Migrations, Security, Unknown situation.
- `SCHEMAS.md` — file formats, trailer meanings, validator rules, migration mapping.
