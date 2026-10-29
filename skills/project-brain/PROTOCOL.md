# Intent, execution and private access (protocol 1)

Read the relevant section when reconciling scope, managing a long run, handing off,
or setting up secret-dependent checks. Python standard library only. These guards
operate on local trusted records; they do not authenticate the human or sandbox a host.

## Setup and migration

New `PB init` projects use `protocol_version: "1"` in schema-4 config. Upgrade enables
it when the old config has no explicit protocol version. Explicit `0` is legacy
compatibility: boot prints a warning; use `PB protocol --enable` before new work.
Migration never invents target confirmation, secret access or review. Old records
remain readable; protocol-1 proof must be produced against the new inputs/intent.

Confirm Target in the user's words; choose EXEC/REV once. Then record one project
secret decision, even when the answer is no secrets:

```text
PB security --ref none --note "User says this project needs no credentials"
PB security --ref project-vault --note "User approved the external project store"
```

Choose one reference, not both. Only a symbolic reference and non-sensitive note
are committed to `.project-brain/security.json`. Never ask for key values in chat.

## Task contract and revisions

Optional headers (defaults shown):

```text
Purpose: implementation
Secrets: none
Inputs: `shared/schema.json`, `tests/invoices/**`
```

Areas is the write/ownership boundary. Inputs adds verification-only dependencies;
root manifests/lockfiles, agent instructions and common test/build configs are added
automatically. Include nested package configuration and external tool inputs explicitly.
Referenced ADRs and matching domain Target files are included. Missing/new/deleted
matched inputs change freshness. `verification.environment` records the approved
toolchain/container identity without launching version probes on each boot.

Before starting a fully specified task (reconcile normalizes its deterministic risk floor before binding):

```text
PB reconcile PB-001 --note "This task implements the confirmed invoice journey"
PB start PB-001 --agent <alias>
```

This records current intent + task contract under its evidence directory. Changed
Target Goal/success/non-goals/target-state, matching domain target or constraints
requires another impact decision before start/check/evidence/review/accept/delegate.
For DRAFT work, only explicitly bounded discovery can start:

```text
Purpose: discovery
PB reconcile PB-001 --goal-independent --note "Only inventory the existing storage contract"
```

For a purely editorial target correction with the same task outcome:

```text
PB reconcile PB-001 --keep-evidence --note "Wording clarified; outcome and task contract unchanged"
```

Never use this to waive an actual scope change. A changed task contract always
invalidates evidence. Genuine revisions reconcile affected open tasks individually;
completed work that needs revision becomes a new task. The runtime cannot decide
whether a human's meaning changed; the recorded impact decision must be truthful.

## Checks, attempts and explicit budgets

`PB delegate <id> --readback` inspects an acknowledged Pool job without dispatch or checks, even if the current task intent changed. An unacknowledged job requires saved-key resolution, never a changed replay.

`PB check` reuses intact current source/input/environment/contract logs. Use
`PB check PB-001 --rerun` for an actual changed premise not represented by local
inputs, or when explicitly requested. A fresh machine without private logs rechecks;
handoff manifests do not authorize replaying unverifiable results as PASS.

Check writes a short Resume and cumulative actual command-run count/time. Superseded
machine records and stale typed proofs are compacted without losing ownership, user
feedback or unresolved operations; generated history does not force task splitting. Optional
stable config, only when authorized by the user:

```yaml
execution:
  repeat_limit: 2
  max_check_runs: 0
  max_check_seconds: 0
```

Zero means no explicit cumulative limit. Check command timeouts are clipped to an explicitly remaining time budget; scheduler/scanner overhead is not a hard wall-clock deadline. These measure local check work, not a hard
provider token cap. Quota/model-job limits remain in the selected backend. Same
source/spec + failure + strategy at repeat_limit blocks another blind attempt.
Changed source or a recorded different strategy permits another approach. Other
authorized independent work continues. Never erase failure state to spend more quota.

```text
PB progress PB-001 --next "Verify recovery behavior" --failing "Lost response case" --strategy "Read back persisted row" --dirty "src/invoices.py"
PB handoff PB-001
```

Progress replaces the task Resume rather than appending parallel reports. Handoff
writes a bounded public manifest in the task evidence directory: open criteria,
Resume, all External records, digests and whether checks are reusable in this checkout.
No private logs, bindings or credentials are copied. Host-private absolute paths and known signed credentials are refused; use project-relative paths and symbolic readback references. Too much essential state causes
an explicit error, never silent dropping of unresolved operations.

## Secret-dependent checks

Keep implementation/testing with synthetic fixtures secret-free. A task needing
real credentials declares `Secrets: project-vault`. It can run checks only after
the approved project policy matches and an external host adapter is available.
Secret-bearing tasks are never sent to Pool/direct workers; split fixture/code work
from the credential-dependent integration check.

`PB_PRIVATE_BINDING` resolves a host-private JSON file outside the repository. Its
project/reference and approved command/scanner identities are checked. Example
shape (paths are placeholders, not a built-in store):

```json
{
  "project": "<absolute project directory>",
  "reference": "project-vault",
  "capabilities": ["credential_broker", "filesystem_isolation"],
  "commands": {
    "python tests/integration.py": ["<absolute approved host launcher>", "--profile", "invoice-check"]
  },
  "scanner_argv": ["<absolute approved scanner>"]
}
```

The launcher receives the parsed Verify argv appended to its prefix. It must
actually provide the named isolation and scoped credential injection. The scanner
receives raw output on stdin and returns 0 only for safe output; its stdout/stderr
is discarded. Shell shims, mismatched/linked/in-project bindings, unapproved commands,
missing capabilities and scanner failures refuse execution/output. Adapter/scanner
file contents contribute to cached-proof freshness.

This trust contract does not install or independently certify a sandbox. Use the
host's approved OS/container/provider controls. A host without that capability runs
secret-free work and reports the blocked integration step. Do not claim a JSON
capability label itself restricts filesystem/network access.

## Output, review and sharing

Check/direct-worker output is captured in a private temporary stream before a
sanitized log is written. Known secret patterns/environment values are masked;
secret-dependent checks additionally require the approved scanner. Output above
4 MiB is bounded and cannot receive PASS. Unknown formats/images still need the
project's appropriate scanner/private-data review; regex is not complete DLP.

`PB security --scan` inspects staged bytes, including staged/worktree differences,
before sharing; protocol-1 accept performs this text scan when Git is available.
Binary contents need rendered/appropriate private-data inspection. Never treat
ignore rules or this scan as a security boundary.

SOLO requires explicit `PB review ... --self-review`. Independent protocol-1 review
requires a registered reviewer and writes its assurance level alongside source/spec
digests. A registration/local record is not authenticated execution identity; do not
claim a host-backed second reviewer unless the host actually ran one. Missing
capabilities/required feedback are blockers, not reasons to fabricate acceptance.
