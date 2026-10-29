# Project Brain 3.5.1 — Session Pool, CLI Discovery and Delegation

Load this file when measuring task complexity, scanning installed CLI coding agents, managing subscription token quotas, or delegating `Tier L` / `Tier M` tasks to CLI worker sub-agents.

Normal discovery and delegation use the separate CLI Agent Pool backend when the user
selects a `Pool` (`P-ALL` / `pool_mixed`, `P-ML` / `pool_med_low`, `P-L` / `pool_low`)
session mode: see [POOL.md](POOL.md). When the user selects `Self` (`S-ALL` /
`self_mixed`, `S-ML` / `self_and_lower`) or `Solo` (`SOLO` / `solo`) via
`PB agents mode --new --exec <mode> --rev <mode>`, do not connect to CLI Agent Pool. The
session/approval and direct CLI contracts below apply to explicit `--backend direct`
or `--registry` operation. They do not require a second approval for owner-configured
Pool models.

## 0. Standalone session authority

Models have no immutable H/M/L group: the user assigns director, worker, reviewer and
discovery roles for the session. Task scores describe work complexity; seeded model
ratings are advice. The lead designs architecture/specs and reviews; low/mid workers
perform bounded implementation/inventory. No fallback spends the director's account.

The supported verification target for this source project is Windows. Do not spend
the user's budget establishing Linux/macOS coverage unless they request it.

`agents session --new` / `--refresh` take a deterministic presence snapshot (Windows
uninstall metadata, per-user Programs directories, PATH and verified bundled CLI entry
points) without launching any CLI process, then create the proposal; last-known
version/auth/quota values carry their original timestamps. Live metadata probes
(versions, login state, quotas, catalogs) belong to the deadline-bounded `agents scan`
and `agents quota` commands. Have a cheap approved worker perform discovery; if none is
available collect metadata deterministically without inference. Include host-native
models when the platform supplies their IDs/efforts. A catalog does not prove access.

At every new top-level human session, refresh dated access/quota metadata and present
a fresh pool for confirmation. Previous choices are suggestions, not current consent.
Show exclusions and let the user change them. Nested workers and crash recovery in
the same human session inherit that approved pool; they do not ask again or rotate it.
Unsettled work must be read back before any replacement session is proposed.

### Bootstrap, missing tools and login

1. Use deterministic binary/version/account metadata commands first: discovery itself
   does not need model inference. Cache the raw inventory locally and return a compact
   summary. If interpreting it would consume substantial director context and no
   external route is known yet, use the host's smallest suitable authorized discovery
   model with bounded context/output. This bootstrap exception is not a license for
   the director to do routine scans or to choose expensive native workers.
2. Discover installed Windows applications as well as PATH commands and bundled CLIs.
   Prefer each installed provider's own supported CLI and existing account. Include
   newly discovered tools, host-native models and router catalogs such as OmniRoute
   in the proposal. Classify access as subscription, free allowance, metered API,
   local or unknown; absence of a subscription does not imply absence of free access.
   Never infer billing or usable access from a model name. Group routes sharing an
   account/quota together, so a router does not create a second allowance. Prefer
   OpenCode's free routes; do not reconnect existing native subscriptions through it
   merely to discover them. Discovery does not grant permission to run those models.
3. Present missing CLIs for the user's setup selection. If a selected route has no usable CLI, use current official Windows
   install instructions, inspect the package identity/version and install the minimum
   missing tool within the user's setup authorization. Respect exclusions; do not
   install every catalog entry, replace working global settings or buy a subscription.
   Verify the installed version/help before configuring its adapter.
4. Launch that tool's official login/connect flow. If it needs browser/device login
   or a key entered by the human, make that action visible and wait for completion;
   never ask for a secret in chat or mark authentication successful without readback.
   Preserve other provider profiles. Prefer the subscription endpoint over the
   separately metered API route. Login is an explicit setup step, not a hidden retry.
5. Read account/access metadata and supported quota windows; then run one approved,
   bounded smoke task. Only verified routes become eligible. Missing tools, required
   login, unknown quota and failed smoke each remain distinct visible states.

For example, check an installed ZCode application's bundled CLI before proposing
another installation or routing its subscription through OpenCode. Check the actual
CLI help and supported account interface; do not manufacture a quota from its model
catalog or install an unreviewed scraper. Show newly found routes and changed access
in the next proposal; never silently extend the approved session selection.

Show the full proposal and let the user approve, add/remove or promote roles. Persist
only the actual decision, e.g. this fictional selection (aliases must already exist):

```json
{
  "models": {
    "my-director": {"roles": ["lead", "reviewer"], "efforts": ["high"], "billing": "subscription", "max_jobs": 2},
    "my-cli-worker": {"roles": ["worker", "discovery"], "efforts": ["low", "default"], "billing": "free", "max_jobs": 5},
    "my-host-worker": {"roles": ["worker"], "efforts": ["low"], "billing": "subscription", "max_jobs": 3}
  },
  "exclude": ["expensive-route"]
}
```

```text
PB agents session --new --json
PB agents approve selection.json --session <full-uuid> --user-confirmed --note "<actual user choice>"
PB agents session
PB agents revoke
PB agents settle <job-uuid> --state completed --note "Read CLI output and verified actual result"
```

`default` means the CLI has no effort selector or the user accepts its native default;
never send an unsupported `--effort` or silently substitute a higher effort. API billing
requires `allow_paid: true` as part of actual user approval. Unknown/stale quota requires
explicit `max_jobs`; the runtime counts attempts and refuses unbounded use. Known fresh
quota still enforces reserve floors. New session/configuration invalidates approval;
quota refresh alone does not. Never rotate away an unresolved reserved job: read back
and settle it first. Sessions live beside the machine registry, outside source memory.

Built-ins are conveniences. For another installed CLI configure `cli_agents.<id>.binary`,
`worker_argv` (an argv array, no shell text), and `prompt_stdin`; supported placeholders
are `{binary}`, `{root}`, `{model}`, `{effort}`, `{prompt}`, `{prompt_file}`. Put CLI/model
metadata in `models` with a pool and supported efforts, then propose/approve. The exact
installed CLI help is the authority for its flags. Providers behind a multi-provider CLI
are separate billing routes. No credential content belongs in this registry/selection.

For `cli: host`, delegate prints an explicit host action and reserves its job; the parent
calls its native subagent tool with the approved model/effort, then settles and checks.
The packet alone is not execution. Windows batch adapters receive a safe prompt-file
pointer where needed; unsafe arguments are refused before reservation.

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

## 1.1 Task routing, budgets and quality

Group the discovered routes for the current session by demonstrated capability and
assigned role, not by a permanent list of model names:

| Group | Work | Admission / verification |
| --- | --- | --- |
| Discovery / checks | Inventory summaries, reproductions, deterministic malformed-input tests | Prefer deterministic tools; otherwise a small external CLI worker with exact inputs and checks |
| Leaf implementation | One bounded change with an executable specification | Cheapest eligible external route; unmeasured approved models are limited to LOW-risk L trials |
| Integration | Multiple callers, state/data boundaries | Sufficient quality for the task and explicit scope; strong lead reviews the diff and real checks |
| Director / reviewer | Architecture, escalation, acceptance | Strong model; a reviewer must not be an implementer, including another alias of the same model |
| Host fallback | Work for which external routes cannot be used | Record the concrete reason or explicit user selection; never choose it just because the native tool is convenient |

Every dispatch must have: exact Areas and deliverable, observable acceptance, Verify,
selected CLI/model/effort/billing, max attempts and timeout, expected output size,
and a stop/escalation condition. Reuse the session approval; ask again only for a
new route, paid billing or a larger allowance. Do not repropose to reset a spent cap.
Use one initial attempt plus at most one targeted repair within the approved cap.
After a repeated failure, preserve the failing case and escalate to an approved
stronger route or the director; never keep retrying a cheap model indefinitely.

Before dispatch, show a compact routing reason and budget. Prompt bytes/characters
can be measured; token estimates must be labelled estimates and include an allowance
for tool results, reasoning, output and retries. Context size is not total usage.
A tokenizer estimate, process timeout or max_jobs is not a hard token limit. If a
user requests a hard token/currency cap, require a verified provider-side control;
otherwise disclose the missing control and obtain an alternative bounded allowance.
After dispatch, record provider-reported tokens/cost where the adapter supports it,
with provenance; unavailable usage remains unknown, never zero. Compare the actual
result with the expectation before the next job, including review/repair overhead.
Do not claim to meter the director's chat usage from a child CLI's counters.

Keep prompts to named files/symbols and relevant constraints, not chat history or
whole repository dumps. Large inventories stay local; return model counts and the
few eligible candidates, not hundreds of catalog rows. Request a short final report
(changed files, checks, unresolved risks); read detailed logs only for a concrete
failure. Workers must not spawn nested agents or widen their scope.

Runtime selection checks eligibility before preference/cost. Known quality below
the task floor cannot be waived merely by approving a role. Unmeasured workers
cannot automatically receive MEDIUM/HIGH work. Among eligible L/M workers, external
CLI routes win equal-cost ties against host routes; cheaper eligible host routes
remain visible rather than being hidden for provider preference. --cli/--model can
express a user's explicit choice. A missing/failed route must not silently trigger
a more expensive fallback.
Ratings remain routing hints, not proof of output quality: every result needs actual
diff inspection and current checks. Exit 0, a plausible answer or an intention to
work never substitutes for the requested artifact. The lead may review a worker's
implementation; it cannot call its own implementation independently reviewed.

For Windows CLI acceptance, use the exact installed --help/version, explicit model
and supported effort, a throwaway project and a verifiable file-producing task.
Read back the artifact, run its check, inspect structured usage, and verify that a
failure does not silently switch routes. Test batch quoting, Unicode/JSON prompts,
timeouts, invalid inputs and attempt limits offline. Test each new provider route
with a bounded smoke task before promoting it; one working CLI proves only that
route/version, not every installed CLI or every model.

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
# Discover CLI executables and probe supported account metadata (no model jobs).
# Overall wall time is deadline-bounded; CLIs not reached are recorded budget_exhausted.
python "<path-to-brain.py>" agents scan [--no-quota]

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
| `agy` | `agy` | `agy --version` | `agy --model <model> --effort <effort> --mode auto --print "<prompt>"` |
| `omniroute` | `omniroute` | Auto-starts `omniroute serve --daemon --no-open --no-tray` if `/api/health` is down; probes `omniroute api models get-api-models --output json` | Requires an explicitly configured coding-agent `worker_argv` adapter; `omniroute chat` has no repository tools and is excluded from automatic worker selection |
| `qwen` | `qwen` | Access/quota require explicit registry data | `qwen -p "Execute the task provided on stdin." -m <model>` + stdin |

### Subscription Quota Reserve Policy

Subscription allowance and raw token usage are separate measurements. Display each
provider's remaining percentage, window duration, reset time and measurement timestamp.
Use the lowest remaining applicable window for eligibility; a healthy short window
cannot hide an exhausted weekly allowance. Do not convert tokens or API list-price
cost into subscription percentage. Shared CLI routes for the same account must use
the same pool. A provider without a verified quota interface remains
unknown rather than being assigned Codex's window structure.

For a reviewed provider metadata CLI, `pools.<id>.quota_argv` is an explicit argv
array that must output one JSON object: `remaining_pct`, UTC `updated_at`, optional
`resets_at` and `quota_windows` (objects with name, remaining_pct, resets_at,
window_minutes). It must be a read-only account query, never an inference command or
a credential in argv. The runtime bounds the query, validates freshness and numbers,
keeps last-known low quota on failure, and binds command changes to reapproval.
This adapter interface does not claim a working Z.AI account integration by
itself; the installed provider command and live response still need verification.
- **Worker Reserve Floor (`10%`)**: A pool at or below 10% is ineligible.
- **Director Reserve Floor (`25%`)**: L/M workers cannot consume a pool at or below 25%, even when no alternative exists. Choose another eligible pool or stop dispatching.
- **Unknown/stale quota**: Never treat it as 100% remaining. Dispatch requires a fresh reading (5 minutes) or the user's explicit bounded `max_jobs` allowance for the approved route. A last-known value at/below reserve stays blocked until refreshed, even with an allowance. Known API billing cannot be relabeled free/local; paid authorization remains mandatory. `select`/`--dry-run` are planning aids, not a reservation.
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


### Windows discovery readback and catalog adapters

`agents scan` combines Windows uninstall metadata, per-user Programs directories,
Windows Store package metadata, PATH commands and verified bundled CLI entry points.
Unclassified application metadata remains in `installed_apps` for compact discovery
review; it is not a model or a claim that the application is AI software. Known apps
without a CLI appear with `CLI_SETUP_REQUIRED`; the user chooses installation before
setup. A bundled ZCode runtime uses existing Node for metadata discovery; that does
not establish model selection, login or permission to dispatch an unverified adapter.

OmniRoute discovery first checks the local gateway (`http://127.0.0.1:20128/api/health`) and
auto-starts `omniroute serve --daemon --no-open --no-tray` outside `ProcessTree` when offline,
then queries `omniroute api models get-api-models --output json` (falling back to
`models --output json`). If the server still cannot be reached, `catalog_status=unavailable`
is recorded rather than an apparently empty successful pool. Some commands truncate JSON
catalogs (`models --output json` slices at 50); a reported remainder yields `partial`.
No upstream model is invoked by discovery.

`agents scan` finishes within its overall deadline (default 90 s). Probes not started
before the budget runs out are recorded as `budget_exhausted` and pending configured
quota queries as `deferred`; the caller is never stalled. Slow-booting (Node-based)
CLIs can report `version: installed` under the short per-probe cap while presence
stays verified; re-run the scan or raise the deadline when complete metadata matters.
Session proposals never launch these probes at all.

Additional CLIs can provide an explicitly reviewed `cli_agents.<id>.catalog_argv`
array. It must return a JSON array (or an object with `models`/`data`) containing model
ID strings or objects with `id`/`model_id` and optional `provider`. Responses are
bounded; arbitrary credential fields are discarded. New models are proposals with
unknown billing/access and no roles. A catalog is not subscription evidence.

Assign all routes for a verified shared account to the SAME existing `pool` key.
Do not guess account identity from provider/model names. Until identity is verified,
present that uncertainty and avoid approving duplicate routes as independent budgets.
The lowest known quota window gates dispatch; incomplete refresh responses cannot
make retained windows appear fresh. A provider without an official quota interface
remains unknown and requires a user-selected job cap.
