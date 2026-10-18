# Project Brain 3.0 — Complexity Scoring, CLI Agent Discovery, Quota Management & Sub-Agent Delegation

Load this file when measuring task complexity, scanning installed CLI coding agents, managing subscription token quotas, or delegating `Tier L` / `Tier M` tasks to CLI worker sub-agents.

---

## 1. Architectural Principle: Lead vs. Worker Separation

To finish large, end-to-end engineering projects without exhausting high-tier model subscription quotas:
1. **High-Tier Lead / Director (`Tier H`, `effort=high`)**:
   - Shapes `current.md`, `target.md`, `constraints.md`, and `decisions/ADR-NNN.md`.
   - Designs the Design System & Token Foundation (ADR + first UI milestone) and Clean Architecture boundaries.
   - Decomposes work into small, self-contained, executable tasks (`PB-NNN.md`, $\le 80$ lines) with exact file paths, symbol names, typed Acceptance criteria, and backticked `Verify` commands.
   - Executes only `Tier H` architectural/security/state-machine tasks and performs independent reviews (`PB review`).
2. **Low/Medium-Tier CLI Workers (`Tier L` at `effort=low`, `Tier M` at `effort=medium`)**:
   - Execute well-specified `READY` tasks via `PB delegate <PB-NNN>`.
   - Receive a compact, zero-history prompt containing only the task contract, domain slices, and quality rubric.
   - Run inside an OS-contained `ProcessTree` (Windows JobObject / POSIX process group) followed by automatic `PB check`.

---

## 2. Mechanical Task Difficulty Scoring (`PB score`)

Never guess task difficulty by intuition alone. Run `PB score [PB-NNN] [--write]` to compute a deterministic `0..100` complexity score:

| Signal | Points | Notes |
| --- | --- | --- |
| `Areas` count | $+4$ per glob (max $20$) | File blast radius |
| `Domains` count | $+4$ base, $+6$ per extra domain (max $15$) | Cross-domain coupling |
| `Steps` count | $+3$ per step (max $16$) | Implementation breadth |
| `Acceptance` items | $+2$ per checkbox (max $14$) | Verification surface |
| `Depends` count | $+4$ per dependency (max $10$) | Integration sequencing |
| `Risk` weight | `LOW`: $+0$, `MEDIUM`: $+10$, `HIGH`: $+22$ | Floor escalated by surface |
| Architecture/Security keywords | $+14$ | `auth`, `migration`, `schema`, `payment`, `crypto`, `state-machine`, `concurrency`, `lock`, `protocol` |
| UI Foundation keywords | $+10$ | `design-system`, `tokens`, `theme`, `typography`, `navigation`, `shell` |

### Tier, Effort & Split Rules
- **Score `0..32` (`Tier L`, `effort=low`, `role=worker`)**: Single-area leaf task, straightforward UI component using existing tokens, unit test addition, or isolated bugfix. Ideal for fast/cheap or free CLI workers (`gpt-5.1-codex-mini`, `gemini-2.5-flash`, `opencode/big-pickle`, `qwen3-coder-plus`).
- **Score `33..64` (`Tier M`, `effort=medium` or `high` if Risk `HIGH`, `role=worker`)**: Multi-file feature screen, repository + endpoint implementation, or state transition wiring. Ideal for capable mid-tier CLI workers (`gpt-5.2-codex`, `gpt-5.3-codex`, `claude-sonnet-4-6`, `gemini-2.5-pro`).
- **Score `65..100` (`Tier H`, `effort=high`, `role=lead`)**: Cross-domain architecture, auth/security boundary, schema migration, or Design System foundation. Handled by the Lead model (`claude-opus-4-6`, `gpt-5.4`, `gemini-3.1-pro`) or split into `Tier L/M` subtasks.
- **Score `> 78` or `> 80` lines (`SPLIT_FIRST`)**: Must be split into smaller tasks before starting.

---

## 3. System CLI Agent Discovery & Live Quota Probing (`PB agents`)

Project Brain stores the machine-local agent and quota registry in `~/.project-brain/agents.json` (override with `--registry <path>` or `PB_AGENTS_REGISTRY`).

### Commands
```bash
# Discover CLI executables and probe supported account metadata (no model jobs)
python "<path-to-brain.py>" agents scan

# Refresh supported live rate limits (currently Codex RPC); other pools need explicit data
python "<path-to-brain.py>" agents quota

# List registered models, benchmark quality, cost weights, and pool remaining %
python "<path-to-brain.py>" agents list

# Select the lowest-cost model meeting the quality floor and quota reserve for a task or role/tier/risk
python "<path-to-brain.py>" agents select --task PB-001
python "<path-to-brain.py>" agents select --role worker --tier L --risk LOW
python "<path-to-brain.py>" agents select --role reviewer --tier H --risk HIGH --exclude codex/gpt-5.3-codex
```

### Supported CLI Agents & Non-Interactive Invocations
| CLI ID | Binary | Live Quota / Auth Probe | Non-Interactive Worker Dispatch |
| --- | --- | --- | --- |
| `codex` | `codex` | `codex app-server --stdio` (`account/rateLimits/read`; window duration is provider metadata) | `codex exec -m <model> -c model_reasoning_effort='<effort>' --cd <root> --sandbox workspace-write -c approval_policy='never' -` (prompt on stdin) |
| `opencode` | `opencode` | `opencode --pure models` (free & subscription providers) | `opencode run --pure -m <provider/model> --variant <effort> --dir <root> "<prompt>"` |
| `claude` | `claude` | `claude auth status` (auth metadata, not remaining quota) | `claude -p --model <model> --effort <effort> --permission-mode acceptEdits` (prompt on stdin) |
| `gemini` | `gemini` | Access/quota require explicit registry data | `gemini -p "Execute the task provided on stdin." -m <model> --approval-mode auto_edit` + stdin |
| `agy` | `agy` | `agy --version` | `agy --model <model> --effort <effort> --mode auto --print "<prompt>"` |
| `qwen` | `qwen` | Access/quota require explicit registry data | `qwen -p "Execute the task provided on stdin." -m <model>` + stdin |

### Subscription Quota Reserve Policy
- **Worker Reserve Floor (`10%`)**: A pool at or below 10% is ineligible.
- **Director Reserve Floor (`25%`)**: L/M workers cannot consume a pool at or below 25%, even when no alternative exists. Choose another eligible pool or stop dispatching.
- **Unknown/stale quota**: Never treat it as 100% remaining. Actual delegation requires a fresh reading (5 minutes); an explicitly configured unmetered pool must still have authorized access. `select`/`--dry-run` are planning aids, not a reservation.
- Discovery, authentication, model availability, payment mode and quota are separate facts.
  An installed binary or API-key variable does not authorize paid usage. Do not read
  credential contents or switch to paid APIs automatically.
- A pre-dispatch snapshot cannot cap tokens already spent by a running model or another
  concurrent client. Bound tasks and timeouts, recheck between jobs, and retain Resume
  on failure. No promise of zero quota exhaustion is made.

---

## 4. Delegating Tasks to CLI Workers (`PB delegate`)

```bash
# Preview which CLI agent, model, effort, and command line will run
python "<path-to-brain.py>" delegate PB-002 --dry-run

# Dispatch PB-002 to the optimal CLI worker, stream output to .project-brain/.cache/runs/PB-002-delegate.log, and run `PB check`
python "<path-to-brain.py>" delegate PB-002

# Override CLI, model, or effort explicitly
python "<path-to-brain.py>" delegate PB-002 --cli codex --model gpt-5.2-codex --effort low
```

What `PB delegate` does automatically:
1. Requires READY/IN_PROGRESS and an executable spec, UI Triad where applicable, completed dependencies and no unresolved external operation. Scores task scope and refuses unsplit tasks; H tasks require explicit `--force` and still pass all eligibility gates.
2. Selects the lowest-cost ready CLI worker model meeting the `(tier, risk)` quality floor and quota reserve.
3. Calls `PB start PB-NNN --agent <selected-alias>` to enforce ownership, dependencies and one active writer.
4. Spawns the worker CLI inside `ProcessTree` with a compact zero-history prompt.
5. Runs `PB check PB-NNN --as <selected-alias>` immediately after the worker exits, binding machine verification logs to the current `areas_digest` and `contract`.

Dispatch is process containment, not a filesystem or network sandbox. The worker CLI's
own permissions still apply; task Areas are instructions, not OS access controls.
One delegated worker holds a native lifetime lock per checkout; use separate worktrees
for parallel writers. Mutation locks are released by the OS on process exit; their
files remain in `.cache/` and must not be deleted while commands run.
CLI/version-specific flags must be checked against the installed CLI's help. Unsupported
adapters or unsafe Windows batch arguments are refused, never converted into shell text.

Built-in model names, cost weights and quality scores are illustrative routing seeds,
not measured benchmarks or a current model catalog. Maintain explicit model IDs, efforts,
roles and access in the machine registry using `agents merge`. Same-model aliases do not
provide independent review; declared identities cannot authenticate who actually ran them.
