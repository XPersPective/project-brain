# Project Brain ↔ CLI Agent Pool director contract (pb-director/1)

Owner: Project Brain. Consumer: CLI Agent Pool (CAP). This is the single
cross-repository contract for unattended Baton Relay (BRP) directors.

Division of work: **Project Brain owns the relay** (baton record, candidates,
two-phase handoff, failover and restart decisions, user notification). **CAP owns
mechanisms**: readiness probes, lock release, deadlines, an exit hook and secret
delivery. CAP keeps no relay table and never chooses a successor, so there is
exactly one relay brain and no duplicate directors.

Every feature is optional. Project Brain sends a field only when
`pool_capabilities` lists its feature and prints the guarantees that are missing.

Authority: owner CLI RPC may use preflight, resolve and director submission.
CAP task leases identify the actual task and profile: a director lease may submit
its successor with director lifecycle options and acknowledge its own takeover;
an ordinary worker lease may not. Successors are not linked workers; delegated
workers carry their director's `parentTaskId`. Worker-marker-only callers cannot
claim owner authority. Project Brain preserves the scoped task lease and worker
marker in its RPC subprocess environment. Exit hooks run in the owner service
environment without a task lease or worker marker.

## 1. Discovery — `pool_capabilities {}`

```json
{"contracts": ["pb-director/1"],
 "features": ["preflight", "onExit", "ack", "idle", "secretEnv", "resolve", "releaseLockOnFailure", "directorProfile"]}
```

An unknown-tool error means no features.

## 2. Readiness — `pool_preflight` and `pool_preflight_status` (feature `preflight`)

CAP's design (cli-agent-pool `docs/director-tasks.md` §2): a fixed probe prompt
run with the director profile (same native permissions, project selection,
sandbox and network as a real director), verified by CAP itself (HMAC probe
files, native tool events, a random line read with the native read tool, an MCP
ack, a loopback POST, `git hash-object -w`, `git ls-remote`), never by the
model's report. It takes the normal workspace lock and is cached under a key of
Pool version, route, model, workspace, capabilities, read paths, CLI version and
native settings-file hashes.

Request (both calls):

```json
{"routeId": "agy-local", "modelId": "gemini-4-argon", "effort": "high",
 "workspace": "D:/abs/project", "readPaths": ["C:/Users/u/.skills-manager/skills/project-brain"],
 "capabilities": ["shell", "poolMcp", "readOutside", "gitCommit", "gitRemote", "poolService"]}
```

- `pool_preflight` (owner surface: refused when `CLI_AGENT_POOL_WORKER=1`) runs
  or refreshes the probe. It may return the result directly or `{id, state}`;
  Project Brain then polls `pool_get_task {taskId}` until terminal and reads its
  `preflight` field.
- `pool_preflight_status` is read-only and lock-free; it returns the cached
  result for the current key.

Result:

```json
{"current": true, "ready": false, "checkedAt": "2026-11-05T10:00:00Z", "retryAfter": null,
 "capabilities": {"shell": {"status": "failed", "fix": "add command(*) to permissionGrants.allow in <file>"},
                  "poolMcp": {"status": "passed"}, "gitRemote": {"status": "not_applicable"}},
 "error": "PROJECT_AMBIGUOUS"}
```

`ready` is true only when every requested capability is `passed` or
`not_applicable`. Project Brain runs `pool_preflight` at `relay start` (no relay
live, owner session) and from the exit hook (service environment, the dead
director's lock released); before a planned handoff it uses only
`pool_preflight_status` and skips candidates whose result is not current.

Capabilities map to the director requirements: multi-line and `;`-compound shell
(`shell`), CAP MCP (`poolMcp`), reading the installed skill outside the workspace
(`readOutside` with `readPaths`), Git commit and push (`gitCommit`, `gitRemote`)
and reaching the local CAP service from shell (`poolService`). An ambiguous native
project (two Antigravity projects for one folder) is a run-level failure.

## 3. Director task options on `pool_submit`

Sent only for relay director tasks (`kind:"write", mode:"execute"`):

| Field | Feature | Meaning |
|---|---|---|
| `profile: "director"`, `readPaths: [...]` | `directorProfile` | Use the same native permissions and external skill paths as preflight. Ordinary workers cannot create director tasks. |
| `onExit: {"argv": [...], "timeoutSeconds": 300}` | `onExit` | §4. |
| `ackDeadlineSeconds` (60..3600) | `ack` | Running this long without `pool_ack_task` → cancel, error `ACK_TIMEOUT`. Queued time does not count. |
| `startDeadlineSeconds` (60..86400) | `ack` | Still queued this long after submission → cancel, error `START_TIMEOUT`. |
| `idleTimeoutSeconds` (300..86400) | `idle` | No native output line and no running linked worker for this long → cancel, error `IDLE_TIMEOUT` (hang detection). |
| `secretEnv: {"PB_RELAY_TOKEN": "<32 hex>"}` | `secretEnv` | Injected into the native process environment (inherited by every shell it starts). Stripped before storage, events and the idempotency fingerprint; memory-only. If the service restarts before the task runs, the task fails with `SECRET_LOST`. Keys must match `^PB_[A-Z_]{1,32}$`. |

CAP injects `CLI_AGENT_POOL_TASK_ID` so takeover can acknowledge its task even
before the submit response reaches its predecessor.

`pool_ack_task {taskId}` marks a running task as having confirmed takeover;
idempotent; `INVALID_STATE` for terminal tasks.

With `releaseLockOnFailure` (CAP §4 fingerprint release), any write task that
ends failed, cancelled, timed out, interrupted, `INVALID_REPORT` or
`WORK_INCOMPLETE` without workspace changes becomes a non-locking terminal state;
with changes it stays `needs_review`. A director that hands off ends with a
`completed` report, so a normal handoff never locks the workspace.

`pool_resolve_task {taskId, reviewed: true, note}` (feature `resolve`, owner
surface) releases a `needs_review` lock that is no longer active; it never deletes
or reverts files. Project Brain uses it only for relay-owned tasks: its director
tasks and tasks linked to them (`parentTaskId`); creation time alone never proves
ownership. The next director classifies the dirty tree at boot.

## 4. Exit hook — `onExit` (feature `onExit`)

- Runs `argv` once after the task reaches any terminal state, including tasks
  reconciled at service start. No shell; `argv[0]` is an absolute existing file;
  `cwd` = task workspace; stdin closed; hidden window; timeout ≤ 600 s.
- Environment: CAP's service environment (no `CLI_AGENT_POOL_WORKER`) plus
  `CAP_TASK_ID`, `CAP_TASK_STATE`, `CAP_TASK_ERROR`.
- Exit code 75 = temporary failure: retry up to 3 times, 30 s apart. Other codes
  are final. The last 2 KB of output is kept as a task event.
- Output lines starting with `CAP_NOTIFY ` are shown to the user (dashboard/tray).
- The hook may call CAP (`pool_submit`, `pool_preflight`, `pool_resolve_task`);
  CAP must not deadlock, and the exiting task's lock state is final first.
- The watchdog exists only while the CAP service runs.

## 5. Task lookup and linking

Project Brain labels director tasks `PB relay g<generation> <suffix>` and, after a
lost `pool_submit` response, finds them through `pool_list_tasks` (`id`, `state`,
`workspace`, `clientLabel`). With `secretEnv` the token is not lost with the
response: an idempotent replay returns the same task. `pool_get_task` exposes
`parentTaskId` for workers linked to a director through CAP's task token.

## Fallbacks in Project Brain

| Missing | Project Brain behavior |
|---|---|
| `preflight` | `relay start` refuses unless `--unverified`; status shows "readiness: unverified". |
| `onExit` | No automatic restart; boot/status show the relay and `relay recover` performs recovery when run. |
| `ack` | `relay recover` cancels a successor running past the takeover deadline. |
| `idle` | A hung director is ended only by its 12 h task timeout. |
| `secretEnv` | The baton token is in the successor prompt (`--relay-token`). |
| `releaseLockOnFailure`, `resolve` | Recover prints the exact `cli-agent-pool resolve` command. |

## Versioning

Additive changes keep `pb-director/1`. A breaking change adds `pb-director/2` to
`contracts`; Project Brain accepts the newest version both sides list.
