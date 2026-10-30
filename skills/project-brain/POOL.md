# CLI Agent Pool integration (Project Brain 3.6.1)

## Pool 1.7 execution and upgrade contract

New implementation dispatch defaults to `kind: write, mode: execute`. Pool 1.7+
must advertise the mode before Brain creates a new job. Reviewer/discovery
selection defaults to `kind: read, mode: response`; explicit `delegate --mode response`
returns analysis without running implementation checks or inferring completion.
`delegate --mode execute` is explicit implementation. EXEC/REV resource choices
(P-ALL/P-ML/P-L) remain separate from these task modes and still govern access.

Brain polls new jobs with `compact: true`, prints the structured report once
(status, summary, files, checks, research, blockers; at most 6000 characters), then
independently runs task Verify only for successful execution with a completed report.
Reports are untrusted observations, not acceptance evidence. Missing reports and
review quarantine require readback; no native permission, quota or billing bypass.
`--timeout` bounds each worker/check; `--wait` independently bounds caller polling
(default 3600, 1..86400 seconds). A queue/review blocker returns the existing job ID.

Upgrading the installed skill does not rewrite any consumer's saved request/key,
mode, acknowledged task ID or dispatch journal. Existing jobs without mode retain
their original protocol and poll normally, including lost-ack recovery with their
exact original request. An explicit mode change on such a job is refused; use
`delegate --readback`. New tasks use execute. Schema remains 4; normal supported
`migrate`/`upgrade` previews and applies with raw backups; boot upgrades old supported
Git projects. Neither migration nor installation submits/replays a worker, clears
quarantine or installs skills into consumer projects. Skills Manager updates the
shared deployment separately. Do not batch-migrate unrelated projects on release.

One writer per checkout remains mandatory. To execute implementation tasks in
parallel, the director prepares separate worktrees with their own task/journal
context, then reviews and integrates through a single writer. Read-only Pool calls
can share a project. Owner concurrency/route limits remain authoritative.

Project Brain and [CLI Agent Pool](https://github.com/XPersPective/cli-agent-pool) are separate products and skills. Brain owns task
specifications, local research, source evidence, review and recovery. Pool owns CLI
discovery, native authentication, model catalogs, owner memberships, efforts,
quota-based admission and process execution. Neither is copied into the other.

Install CLI Agent Pool (`https://github.com/XPersPective/cli-agent-pool`, [releases](https://github.com/XPersPective/cli-agent-pool/releases/latest)) when using Pool modes (`P-ALL`, `P-ML`, `P-L`):

```text
git clone https://github.com/XPersPective/cli-agent-pool.git
cd cli-agent-pool && npm ci --ignore-scripts && npm run setup
```

Without CLI Agent Pool, use `SOLO`, `NATIVE` or `--backend direct` with no external dependency.

## Normal use from any editor or agent

Choose EXEC/REV once per top-level implementation session using SKILL.md §2.1.
Native/SOLO choices do not connect to Pool. Modes limit resources, never risk or
reviewer strength floors. If a qualified reviewer is unavailable inside the selected
REV boundary, record the blocker and continue independent work; never invent a PASS.
Within existing authorization, dispatch/review continues without repeated permission
questions. User feedback, scope changes and external permissions remain real gates.

Connect only when EXEC or REV is P-ALL/P-ML/P-L. P-ALL permits H dispatch;
P-ML and P-L route above-cap implementation to the main lead. `--force` cannot
bypass the user's selected resource cap. SOLO review needs an explicit audit and
`review --self-review`; acceptance cannot manufacture a review.

```text
python <skill>/scripts/brain.py agents mode --new --exec P-ML --rev P-ML --note "User selected Pool Medium & Low"
python <skill>/scripts/brain.py agents scan --json
python <skill>/scripts/brain.py agents select --task PB-001 --json
python <skill>/scripts/brain.py delegate PB-001 --dry-run
python <skill>/scripts/brain.py delegate PB-001
```

These commands wake the shared local daemon when needed. They do not open a browser,
ask for tokens, enable disabled routes, grant trust or alter owner groups. Any existing
absolute project folder is accepted; Pool keeps no project allowlist. Configure models once in Pool, then use the same memberships from every
agent/editor. Scans are deterministic metadata operations, not model inference.

`agents list` reads the current Pool catalog and owner settings; `agents quota`
additionally asks each route for live quota, leaving unsupported readings unknown.
Pool 1.6.0+ reads vendor quota natively (no cclimits); snapshots may add a readable
`note` (plan, balance) and `windowMinutes`, and only a missing login is `auth_required`.
Pool caches and quota observation timestamps remain authoritative. A scan does not
grant execution access or prove login. `agents scan` reads Pool's imported inventory;
use Pool's **Modelleri tara** or `cli-agent-pool scan-import` for newly installed CLIs.

## Selection authority

- Task tier L/M/H requests low/medium/high. An explicit `--group` can choose a
  stronger pool; a weaker pool cannot satisfy the task quality tier. Risk and task
  splitting checks still apply. P-ALL authorizes Tier H dispatch; legacy direct
  operation otherwise requires explicit `--force`, which never widens a mode cap.
- Manual mode uses only that owner's pool. An empty/exhausted pool fails visibly;
  there is no outside-group, stronger-account or paid-API escape.
- Automatic mode first uses the same strength pool. If none is usable, known
  Pool model-name hints may select a matching strength from the enabled catalog.
  Hints are estimates, never benchmark scores. Unknown capability requires owner
  classification. Metered APIs still require the owner's opt-in or explicit route.
- A fixed membership effort always wins. Otherwise Brain requests low/medium/high
  only when the chosen CLI supports it; unsupported effort stays at CLI default.
  Explicit `--effort default` means do not add a task effort; it does not override a
  fixed owner effort. An incompatible explicit effort fails.
- Known quota windows retain at least 10% for workers and 25% for lead/reviewers;
  a higher owner reserve wins. Unknown quota follows Pool's bounded single-task
  policy, not a fabricated reserve guarantee. No numeric token budget or zero
  exhaustion guarantee can be inferred from percentages or unavailable counters.
- Registered Pool actors retain exact model identity behind a short alias. Start
  and review recheck current owner membership/enabled state. Review must be a
  different model and at least the implementation's selected strength. Owner tiers
  are policy, not independently measured intelligence. Acceptance still requires
  current source evidence and the independent review gate.

Plan the smallest sufficient task, research named local files first, avoid duplicate
full-repository scans and nested delegation, and return compact verified results.
Do not lower acceptance or skip real UI/architecture checks to conserve tokens.

## Recovery and transport

Brain saves one immutable request/key in its external local registry directory
(`pool-jobs/<project-hash>/<task>.json`) before sending. The task's contract and actor
are bound to that job. Lost acknowledgements reuse the same key and exact request.
Once acknowledged, resumes only poll its task ID. A failed/interrupted write remains
in Pool's `needs_review`; Brain never automatically retries it. A changed task
contract requires inspection and a new task, not a silent second execution.
Keep journals private: they contain the task prompt; they never belong in Git.

Pool's `rpc` command accepts `{ "tool": "pool_select", "arguments": {...} }` on
stdin and returns one JSON response. Errors carry `error.code` and `error.message`.
No credential is copied. Windows uses the installed Node entry, not a shell shim.
`PB_AGENT_POOL_COMMAND` may explicitly supply a JSON argv array for another install.
RPC startup runs outside worker ProcessTree containment so Windows does not kill
the shared daemon when the discovery client exits. Pool contains its own workers.

## Standalone compatibility

`--backend direct` explicitly retains Brain's former CLI discovery, approved session
and native-host delegation. An explicit `--registry` also selects that compatibility
path unless `--backend pool` is given. There is no automatic fallback between the
two authorities. The `session/approve/revoke/settle/merge` commands manage only the
standalone backend. See AGENTS_CLI.md for that protocol; do not request a second
session approval for a Pool configuration the owner already authorized.

## Pool 1.4 workspace compatibility

The Pool dashboard can attach an installed or project SKILL.md through its plus/slash
picker. The selected skill's absolute source path accompanies its instructions;
resolve Brain's scripts relative to that source directory, not to the task workspace.
Attaching instructions does not install files or grant worker permission to delegate.
The nested-worker guard and owner high/medium/low/effort/filter rules remain binding.

No agent RPC schema change is needed for this dashboard feature. Keep the Brain
project root equal to the selected work directory. A CLI turn that returns normally
is not proof of edited files: inspect artifacts and run the task Verify commands.
Native Windows Codex writes require its Windows sandbox backend while retaining
workspace-write boundaries. Pool 1.4 selects that backend explicitly when it ignores
unrelated user config; do not work around missing native sandbox setup by removing
sandboxing, changing billing, switching to direct execution or replaying a write.

## Pool 1.8 file access

Use effective catalog kinds/executionModes, not old configuredKinds, to select a
worker. Native coding CLIs now expose their native read/write tools even if an old
catalog stored text-only. Request read/response for inspection and write/execute for
implementation. Owner toolPolicy configured can still explicitly limit scopes.
Native CLI trust/deny rules remain authoritative; a catalog capability is not a
permission grant or proof that every provider model supports the task. Pool chat-only
CLI commands do not become coding agents. No automatic fallback or job replay.
