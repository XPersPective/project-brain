# Baton Relay Policy (BRP)

Optional director circulation across accounts that the user already signed in
once in CLI Agent Pool (CAP). When the director's quota reaches the user's
threshold, it checkpoints, starts the next listed CAP route with quota as the new
director and stops. The successor takes the baton and does the same, until the
project is complete. BRP never logs in, logs out or edits credentials; account
sign-in belongs to CAP. QRP (same-account wait) is unchanged and separate.

## Questions (new session, with ESP/SP/QRP)

Ask once, in the user's language, with English names:

1. Circulate the director with BRP? (default: no)
2. Threshold: hand off when remaining quota is at or below what percent? Suggest 10.
3. Which CAP routes (and optional model/effort), in circulation order? Offer the
   current CAP accounts (each account is its own `routeId`, e.g. `codex-local`,
   `codex-acc2`, `agy-acc2`). Optional `max_handoffs` (default 50).

Save them in the executor policy and confirm as usual:

```json
"relay": {"enabled": true, "threshold_percent": 10, "max_handoffs": 50,
  "candidates": [{"route": "codex-local"}, {"route": "codex-acc2"},
                 {"route": "agy-acc2", "model": "gemini-3-pro"}, {"route": "claude-local", "model": "opus"}]}
```

`relay` is optional; policies without it behave exactly as before. While enabled,
CAP workers also require remaining quota above the threshold.

## Director (baton holder)

1. Start once in an execute session: `PB relay start --route <own CAP route>`
   (add `--model`, `--pool-task <id>` if known). It returns a one-time `token`.
   Keep it only in your context and set `PB_RELAY_TOKEN=<token>` for every Brain
   command (PowerShell `$env:PB_RELAY_TOKEN='<token>'`; POSIX `export PB_RELAY_TOKEN=<token>`).
2. At meaningful checkpoints save your route quota from CAP
   (`pool_get_quotas {routeId}`) to an ignored file under `.project-brain/.cache/`
   and run `PB relay assess --snapshot <file> [--model <id>]`.
   `READY`: continue. `UNKNOWN`: continue carefully and re-check later.
3. On `HANDOFF_REQUIRED`: save all candidate quotas as `{routeId: snapshot}` and run
   `PB relay next --quotas <file>`. On `SELECTED` run
   `PB relay handoff --task <id> --next "<actual next step>" --route <route> [--model <id>] [--effort <e>]`.
   It writes the task handoff checkpoint, starts the successor through CAP (write,
   execute, the same workspace) and returns `HANDED_OFF`. Stop working immediately.
   On `EXHAUSTED` no listed account has quota: use QRP if enabled, else tell the user.
4. When every task is accepted: `PB relay complete`.

The successor's prompt carries its own token and these same steps. It first runs
`PB relay takeover`; only `ACTIVE` authorizes work. Takeover verifies the token,
unchanged policy and the exact handoff checkpoint, then cancels the previous
director's CAP task if it is still running (the process, never its login).

## One director at a time

`boot` prints `RELAY: ACTIVE gen N director <route> since <UTC>` while circulation
runs. Implementation commands from any process without the current token fail
with `RELAY_ACTIVE`, so a later session cannot run the project twice. Only the
baton holder may delegate or run orchestration from inside a CAP worker; ordinary
CAP workers still cannot delegate. `PB relay status` shows director, pending
successor, generation and the last timestamped event (`START`, `HANDOFF`,
`HANDOFF_RETRY`, `TAKEOVER`, `COMPLETE`, `STOP`; the last 200 are kept).
`PB relay stop --note "<reason>"` ends circulation and cancels the director and
pending successor CAP tasks; then the user may start fresh.

The record is `.project-brain/.cache/relay.json` (ignored, never in worktrees);
tokens are stored only as SHA-256 hashes. Handoff checkpoints are normal task
evidence (`.project-brain/evidence/<task>/handoff.json`).

## Recovery and limits

- A lost `handoff` acknowledgement may be retried for the same route: a new token
  and key are issued, so a late duplicate successor cannot take the baton.
- A changed policy or edited checkpoint blocks takeover; ask the user.
- CAP write tasks lock the workspace: a successor queued behind a CAP director
  starts after that task ends. A host director (editor session) must stop at once.
- A director inside CAP needs to reach the local CAP service for quota, delegation
  and handoff. Codex runs workers in its workspace sandbox; verify network access
  to `127.0.0.1` before making a Codex route a relay director, or prefer Claude or
  Antigravity routes for directors and use Codex for workers.
- Quota readings are provider reports, not reservations. BRP does not guarantee
  uninterrupted work, provider-term compliance or billed-token savings; the user
  decides which of their own accounts may circulate.
