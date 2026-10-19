# CLI Agent Pool integration (Project Brain 3.3.0)

Project Brain and CLI Agent Pool are separate products and skills. Brain owns task
specifications, local research, source evidence, review and recovery. Pool owns CLI
discovery, native authentication, model catalogs, owner memberships, efforts,
quota-based admission and process execution. Neither is copied into the other.

## Normal use from any editor or agent

Install CLI Agent Pool 1.1.0+ locally, then use the existing Brain commands:

```text
python <skill>/scripts/brain.py agents scan --json
python <skill>/scripts/brain.py agents select --task PB-001 --json
python <skill>/scripts/brain.py delegate PB-001 --dry-run
python <skill>/scripts/brain.py delegate PB-001
```

These commands wake the shared local daemon when needed. They do not open a browser,
ask for tokens, enable disabled routes, grant trust, alter owner groups or expand
workspace roots. Add the project using Pool's folder picker if WORKSPACE_DENIED is
returned. Configure models once in Pool, then use the same memberships from every
agent/editor. Scans are deterministic metadata operations, not model inference.

`agents list` reads the current Pool catalog and owner settings; `agents quota`
additionally asks each route for live quota, leaving unsupported readings unknown.
Pool caches and quota observation timestamps remain authoritative. A scan does not
grant execution access or prove login. `agents scan` reads Pool's imported inventory;
use Pool's **Modelleri tara** or `cli-agent-pool scan-import` for newly installed CLIs.

## Selection authority

- Task tier L/M/H requests low/medium/high. An explicit `--group` can choose a
  stronger pool; a weaker pool cannot satisfy the task quality tier. Risk and task
  splitting checks still apply. Tier H delegation requires explicit `--force`.
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
