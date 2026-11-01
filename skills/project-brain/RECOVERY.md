# Quota Recovery Policy (QRP)

Ask once in every new implementation session together with ESP/SP: enabled or
disabled, and threshold if enabled (suggest 10%; user may select 5% or 2%). Keep
current-session answers; normal questions do not reopen choices. Only the main
director's provider quota is relevant. Context size/reasoning-token capacity is
different and must not be estimated from subscription percentages.

## Host contract

The runtime deliberately does not install a background service or private timer.
The host must supply current account identity, quota percentages/reset times and
a same-chat wake tool. Use the host's supported API, never copied credentials.
Codex provides `get_usage_limits` and `automation_update`; this was checked with
real metadata and creation/deletion of a **paused** same-thread heartbeat. No test
alarm remains active. Other hosts require their own supported adapter. Without
these capabilities, save progress and report automatic recovery unavailable.

At meaningful task/checkpoint boundaries read current quota (not every thought,
poll or small question). Save only needed metadata in ignored
`.project-brain/.cache/director-usage.json`, not credentials/transcripts. The input
shape has accountId, ordinaryUsageAllowed and rateLimits with an opaque limitId,
primary and optional secondary {usedPercent,resetsAt,windowDurationMins}. Times are
UTC Unix seconds. Unknown/stale observations never authorize automatic work.

```text
PB quota assess --snapshot .project-brain/.cache/director-usage.json
PB quota prepare --task PB-001 --next "Exact remaining action" --snapshot .project-brain/.cache/director-usage.json
```

Prepare saves actual task Resume and handoff, then one PREPARED wake intent. It
binds account/limit hashes, complete policy, handoff bytes and limiting windows.
Use the returned name/nonce, wake_at and prompt with the host automation tool:

1. Schedule a same-chat heartbeat no earlier than reset (a short grace period is
   suitable). Use the host's supported one-time schedule; do not emit raw schedule
   directives, install cron jobs or open another coding chat. Remain quiet while
   nothing actionable changes; notify only meaningful change/completion/failure
   or required user action.
2. Record the returned automation ID with
   `PB quota arm --nonce <nonce> --automation-id <id>`.
3. A lost creation acknowledgement leaves PREPARED. Read back the host alarm by
   name/nonce, then arm it; never create duplicates. PREPARED/ARMED blocks new work.
4. At wake, read **current** account and quota before any coding, then
   `PB quota resume --nonce <nonce> --snapshot <fresh ignored JSON>`.
5. Only RESUMED permits continuation and refreshes saved ESP/SP confirmation under
   the opted-in unchanged QRP. Delete that heartbeat before coding. WAIT means no
   coding until an actual renewed-window observation; stale/missing/cancelled
   authority never resumes. Do not keep replaying successful callbacks.

Save another checkpoint and a fresh nonce for a later quota cycle; consumed wakes
are never reused. Required model-fit, review, source/evidence and task readback
checks still apply. A crash after consuming a wake but before continuing needs an
explicit interactive resume, rather than replaying authority blindly.

## Cancellation and account changes

"Cancel alarm", "disable QRP" and local-language equivalents run `PB quota cancel`:
local authority is revoked **before** asking the host to delete/pause its alarm.
If acknowledgement was lost, read back by name/nonce and remove it. Cancellation
also disables the durable QRP choice; it does not confirm unrelated pending ESP/SP.
Delete failure cannot restore authority. Re-enabling needs explicit fresh consent;
`quota prepare --rearm` is only for that consent, never an automatic retry.

At callback an account change immediately revokes the old wake even if quota is
available. Never switch accounts or reuse a wake on a different account. Readings
without stable account identity cannot support automatic recovery. The user may
cancel and switch accounts manually. Worker failures/quotas follow ESP; QRP does
not change their routing or cancel/replay their jobs.

## Practical limit

Local receipts are declared observations, not authenticated user identity or an
OS sandbox. The host/app/machine must remain capable of waking the chat. Offline
or sleeping machines, quota that does not renew, unavailable model identity and
unsupported hosts can interrupt coding. Never spend reset credits or purchase
quota. A skill cannot guarantee uninterrupted execution or minimum billed tokens.
