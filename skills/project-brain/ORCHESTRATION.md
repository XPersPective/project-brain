# Durable orchestration (opt-in)

`PB` is `python <skill directory>/scripts/brain.py`. Requires Git, Python 3.8+,
standard-library SQLite, and existing human Git identity. No new daemon or paid
provider is required by Brain. Pool and native hosts remain external execution
authorities; capability declarations are not filesystem/network sandboxes.

## Session and task contract

Select EXEC/REV and serial/parallel as described in SKILL.md. `solo` means no
workers. `native` means host subagents; `pool-*` means CLI Agent Pool. Do not mix
worker backend and selected resource. `--tiers MH` narrows worker model selection to
those strength tiers within the selected resource cap; it never widens the cap.
A LOW task may use MEDIUM when LOW is excluded; a HIGH task cannot use MEDIUM.
Review strength/independence floors are still enforced by existing review gates.
Actual implementation identity comes from the immutable Pool selection or native
receipt, not an arbitrary `--actor` string. Registry model updates are serialized
across projects. Native independence compares immutable normalized model identities
even when an implementation registry entry is missing.

Refine and reconcile tasks first. Areas define writes; Inputs define additional
verification scope. Product source must be clean before preparing an isolated run.
One task can have multiple REVIEW runs and distinct EXECUTE attempts. An uncertain
attempt is read back before any new attempt; retries do not overwrite old records.

## Commands

```text
PB runs context <root> --task PB-001 --kind EXECUTE
PB runs search <root> --query exact_symbol
PB runs plan <root>
PB runs prepare <root> --task PB-001 --kind EXECUTE --backend pool --tiers LM
PB runs submit <root> --run run-<id>
PB runs observe <root> --run run-<id>
PB runs wait <root> --run run-<id> --seconds 30
PB runs status <root> --after <cursor>
PB runs report <root> --run run-<id>
PB runs verify <root> --run run-<id> --actor <actual-implementer>
PB runs integrate <root> --run run-<id>
PB runs cancel <root> --run run-<id>
PB runs cleanup <root> --run run-<id>
PB runs rebuild <root> --run run-<id>
PB runs reject <root> --run run-<id> --note "Actual inspection reason"
PB runs export <root>
PB runs backup <root>
PB runs restore <new-clean-checkout> --file <private-backup.sqlite3>
PB runs metrics <root> --file <private-measurements.json>
```

`advance --backend pool` performs one bounded scheduling tick: observes acknowledged
Pool jobs, derives ready tasks, and admits independent new jobs within capacity.
Native advance emits one host launch request. It does not invent host execution or
silently retry failed/uncertain jobs. Repeated calls belong in a host/backend wait
loop, not repeated LLM turns. `plan` is a derived view, never a second task board.
Future dependencies are not considered complete merely because a wave is planned.

The origin checkout is the sole session-policy authority. Stale candidate session
files cannot widen its current resource/capacity policy. Prepared but unlaunched
jobs recheck current intent, tier and executing-job capacity before first launch.

Run admission includes active jobs, UNKNOWN jobs, completed unintegrated writer
ownership, conservative glob overlap, and explicit shared resources within the project ledger. Machine-wide resources still require the
host to honor their shared ownership rules across projects. Use
`--resource android-emulator` for exclusive device access; only the existing
`Medium_Phone_API_36.0` AVD may be used on the development machine. Disjoint paths
alone do not prove semantic independence: record shared contract dependencies.

## Pool contract and recovery

Brain uses existing Pool `pool_get_policy`, `pool_select`, `pool_submit`,
`pool_get_task` and `pool_cancel_task` RPCs. Pool retains model selection, native
authentication, effort, billing, quota and process containment. No Pool schema or
source modification is required. Legacy delegate journals are not rewritten.

Before submit, the exact Pool request and key are stored transactionally outside
the repository. Lost acknowledgement leaves UNKNOWN; `submit` reuses the identical
saved request/key to recover the backend ID, not a fresh job. Once acknowledged,
use observe/wait. Cancel requests do not prove the process has stopped.

New sessions never rewrite process observations. Switching to serial drains active
jobs before new admission. A host that no longer knows a job must report UNKNOWN.
UNKNOWN holds capacity/ownership; elapsed time alone does not release it.

## Native host bridge

Native `submit` returns one immutable packet, workspace, request key and
`host_action: launch_once`. The calling host invokes its actual native agent tool
once, preserving the key and returned job ID. Never fork the lead's full history.
Send the task packet, relevant repository rules and named files; workers must not
manage Brain, commit/publish or recursively delegate. They may request missing
technical context and use the read-only search tool through their allowed host.

Persist a host receipt in a private file, then:

```text
PB runs receipt <root> --run run-<id> --file <private-receipt.json>
```

Receipt shape: `request_key`, `host` (real host name), `job_id` where available,
`model` (actual or unknown), `tier` (required declared L/M/H, within allowed tiers
and at least the requested floor), `state` (RUNNING/SUCCEEDED/FAILED/CANCELLED/UNKNOWN),
optional `usage` (provider counters and source), and `report` on success.
Reports use the Pool six-field format: status, summary, files, checks, research,
blockers. Additional findings/decision_required are preserved and force attention.
REVIEW reports additionally require typed `verdict` (PASS/BLOCKED) and `findings`
(string array). Recording PB review cannot upgrade that verdict or discard worker
findings. Partial/blocked execution reports cannot authorize a qualified review.
Receipt claims are host observations, not authenticated identity or review evidence.

Python cannot invoke every application's native tools. Native launch, attach,
cancel, model choice, callbacks and counters are host-dependent. The Codex collaboration host was exercised with an actual read-only worker: launch,
result collection, and a separate running-turn interruption confirmed by host state.
The host did not report exact model identity or token counters; they remain unknown.
Default-protocol write/check/independent-review/accept is additionally covered by
synthetic host fixtures. Other native hosts require their own capability validation.
When attach is unavailable, preserve uncertainty; do not relaunch automatically.

## Validation and single-writer integration

`verify` snapshots a completed worker's assigned code using a separate Git index;
out-of-Areas changes and secret patterns block it. It prepares a detached candidate
against the current target, copies director-owned Brain context and runs existing
machine checks. Its result includes the candidate path. This does not create a
review PASS or accept unobserved UI/interaction evidence.

A REVIEW run can inspect an existing dirty candidate, bound to its exact content
digest and base commit; it creates no new branch/worktree. Changed content makes
the observation stale. The worker is procedurally read-only, subject to host tools.

In that candidate, use the usual PB evidence/review/accept commands and tick only
proven criteria. The candidate contract, target and constraints must match the immutable run and
current origin; weakening candidate acceptance cannot pass integration.
Use the actual implementer and a qualified independent reviewer
unless the user selected REV=solo and a dedicated self-review was performed.
Worker reports remain observations. REVIEW collection itself closes a report run;
only `PB review` can write authoritative task review evidence.

`integrate` requires a clean original tree and a candidate accepted by the existing
gate. It rechecks acceptance, records integration intent and advances the target
through ff-only. A moving/divergent target blocks; `verify` creates a fresh candidate
for a new target. Conflicts remain in a recoverable candidate for explicit repair.
Run a fresh candidate check after any repair. `rebuild` explicitly archives a bad
candidate as a managed recovery worktree before a new `verify`; it never discards
those edits. Commit hooks may run, but changed trees/digests cannot be promoted.
Destination hooks/edits are checked after merge; unexpected target content is
preserved and marked STALE. Cited check logs transfer only with matching hashes. Active readers block target movement.
Readback of a committed integration completes ledger state without another merge.
Only the director owns commits/merge/cleanup; `git.commit: ask` remains a real gate.

## Context, output and retention

Packets carry source/contract IDs, task requirements, constraints, relevant Current
slices and linked ADRs. They do not contain the whole Brain procedure or chat.
Search is literal, source-bound and paginated; it is not a complete call graph.
It never executes project code; secret/link paths and oversized/binary files are
excluded. Search retains only the requested result page and scans at most 64 MiB
per call; `--start-file <next_file>` continues a truncated scan. Its fingerprint
explicitly covers the scanned files, not an unscanned remainder. A dirty source change changes its fingerprint.

The default successful report view is at most 1 KiB; event views are under 4 KiB
and cursor-based. Full reports stay in the private ledger. Findings, missing
reports and uncertainty never disappear into a success summary. Provider counters
remain unknown when unavailable; reasoning/cache subsets are not added to totals.
No measured percentage token saving is claimed from output byte reduction.

The metrics input is an array of records with variant (baseline/candidate), case,
acceptance (same acceptance-contract identity), model, environment, accepted,
seconds and director_usage. Usage is either null or an object with provider source
and optional total/input/output/reasoning/cached counters. Include planning, checks,
reviews and failed attempts in each end-to-end measurement. Counters are observations,
not authenticated billing receipts. Compare reports failures and unknowns; only
three or more fully observed accepted repetitions per variant can meet the proposed
50% director-token pilot target. Subset counters are never added to a provider total.

Ledger schema 1 lives next to the private agent registry, keyed by Git common
directory; linked worktrees share it, separate clones do not. Preserve it across
restarts. Do not copy live SQLite files as a handoff backup. `export` is a portable
observation manifest; it omits prompts/local paths/logs and does not transfer
worker control or reusable verification authority. On another machine, read back
the original job and recheck missing/environment-bound evidence before takeover.

Cleanup removes only closed clean managed worktrees using Git, retaining dirty
worker artifacts and all run/request keys as recovery tombstones. It never performs
recursive force removal or erases UNKNOWN jobs. Branches and dirty worker results
may require explicit inspection; no bounded-history deletion is automatic yet.
Turning off `runs` does not cancel or hide existing jobs. Old runtime versions do
not understand this opt-in ledger; settle jobs before reverting runtime versions.

## Restore and release boundary

Restore requires a new, clean Git checkout and an absent destination ledger. It
checks SQLite integrity/schema and known Git bases, uses a private consistent
backup, and never overwrites existing state. Imported running/submitting jobs
become UNKNOWN; imported requests remain immutable and readback-only. Submit,
cancel, snapshot, integration and cleanup cannot control imported jobs. Observe
and genuine host receipt settlement remain available. Restoring a backup cannot
stop workers on the original host. Uncommitted worktree files and unreachable Git
objects are not copied by the SQLite backup; recover them at the original host.
After settling old work, explicitly prepare a new destination attempt if needed.

For a completed unintegrated EXECUTE result that inspection rejects, use `reject`
with the actual reason. It preserves artifacts/report, forbids integration of that
result and permits an explicit new `prepare` after inspection. A pending merge
intent is read back at the authoritative origin first, even when rejection is
requested from a linked worker checkout; already-integrated work cannot be rejected. Scheduling ticks
do not automatically retry rejected work. This is separate from cancellation of
a still-running worker, and never rejects work already merged into the target.

This is local orchestration with safe observation relocation, not a distributed
process-control service. Real token savings require real host counters and matched
workloads; the release makes no unmeasured percentage guarantee.

## Economy across waves

Wave count (10, 20 or 100) does not change concurrency or resource permissions.
Reuse existing ready-state calculations, packets, cursor/wait/status and evidence.
Advance changed/completed/blocked jobs; do not restart orientation or load every
worker transcript each wave. A status question uses current context or brief,
without new dispatch, session reset or project-wide re-planning. The lead owns
architecture, ambiguity, serious findings, integration and acceptance; sufficient
planning/review effort remains required. SOLO never probes Pool or workers.

## Scheduling Policy (SP) and session continuation

ESP chooses executor resources; SP independently chooses Serial/Parallel and the
maximum active workers. At a new implementation session, including "continue",
read back unfinished jobs and confirm saved ESP/SP together before new dispatch.
Recommend the saved parallel setting for unfinished parallel work. Already
supplied current-session answers count; same-session questions never reopen it.
Keep old jobs immutable and capacity-accounted. Serial changes drain existing
jobs; do not cancel, replay or oversubscribe them just to fit a new choice.
