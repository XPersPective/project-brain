# Baton Relay Policy (BRP)

Optional director circulation across accounts the user already signed in once in
CLI Agent Pool (CAP), safe to leave running for hours or days. When the director's
quota reaches the user's threshold it checkpoints, starts the next ready candidate
as director and stops. BRP never logs in, logs out or edits credentials. QRP
(same-account wait) is separate. Design: ADR-006; CAP contract:
[references/director-contract.md](references/director-contract.md).

## Setup (opt-in power feature)

BRP is disabled by default in the safe core profile. Enable it explicitly via
`PB policy --source mixed --relay on --relay-threshold 10 --confirm` (or a
project-relative policy JSON file with `--file`). New sessions show a single
confirmation line (`PB setup ask` → `PB setup confirm`); relay successors and
workers inherit confirmed settings without prompts.

```json
"relay": {"enabled": true, "threshold_percent": 10, "director_category": "same"}
```

`director_category` is a CAP category id (e.g. `high`) or `same` (default: the
categories that contain the launcher's route/model). Or list exact routes instead:
`"candidates": [{"route": "codex-acc2"}, {"route": "agy-local", "model": "gemini-4-argon"}]`.
Optional `max_handoffs` (planned handoffs, default 50; `0` = unlimited) and
`takeover_minutes` (default 15). Worker tier is the ESP (`cap-category`, `mixed`,
pins or native). While enabled, CAP workers also need quota above the threshold.
If BRP is on, checkpoint preparation begins at `threshold + 5%` (`prepare_checkpoint`)
and handoff triggers at `threshold`.

When all candidates are quota-limited and CAP supports `wakeAt`, `relay recover
--from-hook` emits `CAP_WAKE_AT` / `CAP_RETRY_AFTER` (exit 75) to schedule
autonomous resume upon quota renewal. When CAP supports `quotaBarrier` and
`supersede`, director submissions pass `stopOnQuotaBarrierPercent` and
`supersedesTaskId`. `PB relay stop --note "<reason>"` requests a 2-minute
graceful save-and-withdraw (`STOPPING`); the holder saves Resume and runs
`relay complete`, or `relay stop` forces termination after 120 s.

## Start (launcher, execute session)

`PB relay start --route <own CAP route> [--model <id>]` resolves the candidates,
runs a short readiness probe on each through CAP `pool_preflight` (compound and
multi-line shell, MCP pool access, reading this skill outside the workspace, Git
commit/push permission, reaching the local CAP service) and prints a table plus
the unattended guarantees CAP provides. It refuses when no candidate is ready and
starts with the ready ones otherwise. Show the table to the user before they
leave. Without CAP preflight it refuses unless `--unverified`.

It returns a one-time `token`. Append `--relay-token <token>` to every Project
Brain command (works in every shell), or set `PB_RELAY_TOKEN`. A launcher that
will be left alone should hand off at once (step 2 below works at any quota),
because a host session's death cannot be observed.

## Director loop (every director)

1. At meaningful checkpoints: `PB relay assess` (reads own quota through CAP).
   `READY`/`UNKNOWN`: continue.
2. On `HANDOFF_REQUIRED`: `PB relay handoff --task <id> --next "<actual next step>"`.
   It selects, re-probes when stale, checkpoints and starts the successor. On
   `HANDED_OFF` stop at once and, inside CAP, end with a completed report
   "handed off". On `EXHAUSTED` no candidate has quota: use QRP if enabled, else
   continue carefully; the relay is unchanged.
3. When every task is accepted: `PB relay complete`.

A successor's prompt tells it to run `PB relay takeover` first and work only on
`ACTIVE`. It inherits the launcher's confirmed settings: it never asks setup
questions, never runs `boot --new-session` setup, and does not repeat discovery or
verification the checkpoint and evidence record. Takeover verifies authority,
the checkpoint and the skill version, adopts a confirmed policy edit, acks its
CAP task and cancels a still-running previous director task.

## Automatic recovery

`PB relay recover` is the reconciler. CAP's watchdog runs it when any director
task ends; `relay start` runs it; a person may run it. It never needs a token. Before a
planned handoff only CAP's cached readiness is read (the live director holds the
workspace lock); recovery after a dead director runs fresh probes.

- Successor ended without takeover, or no takeover within `takeover_minutes` →
  candidate marked unhealthy, next healthy candidate started (`FAILOVER`).
- Director task ended without a handoff (crash, timeout, quota) → next candidate
  started from the last checkpoint (`RECOVER`).
- Relay-owned `needs_review` locks (recorded director tasks and workers linked
  through `parentTaskId`) are resolved; stray duplicate director tasks are cancelled.
- A workspace locked by an older task needing review, no ready candidate, or
  three unplanned transfers without progress → `EXHAUSTED`: the only time the user
  is notified (boot, status, CAP dashboard notice).

## One director at a time

Only the holder of the baton token (delivered by CAP `secretEnv` where available)
may implement, delegate or
orchestrate; others get `RELAY_ACTIVE`. `boot` shows the holder, pending
successor and `EXHAUSTED`; it and `relay status` never start tasks.
`PB relay stop --note "<reason>"` ends circulation, cancels relay tasks and
releases relay locks. A record whose CAP holder already ended is replaced by the
next `relay start`; a host holder needs `relay stop`.

Unconfirmed policy edits never take effect mid-relay; confirmed ones are adopted
at the next relay command (a disabled relay stops). The record is
`.project-brain/.cache/relay.json` (ignored; hashes only). Quota readings are
provider reports, not reservations; BRP does not guarantee uninterrupted work,
provider-term compliance or billed-token savings.
