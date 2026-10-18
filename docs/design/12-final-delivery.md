# Project Brain 3.1 delivery record

Date: 2026-10-18. Source branch: `codex/project-brain-v3-audit`.

## Completed implementation

- Session proposal/approval/revocation and user-selected model/CLI/roles/efforts/billing;
  approved aliases only, excluded models cannot dispatch, configuration changes require
  reapproval, dynamic catalogs and configured argv/stdin adapters support additional CLIs.
- Native-host action packets include exact model/effort/project/registry/session context;
  CLI children inherit the session. A packet is pending work, not claimed execution.
- Low/mid discovery and bounded context; cached inventory plus dated/unknown quota is
  visible. Known 10%/25% floors remain blocking even if stale; unknown/stale high quota
  needs explicit attempt caps. Configured API billing cannot be relabeled free/local.
- Durable reservation UUIDs bind expected session and prepared/current execution config
  under a native lock; crash/uncertain results block retry until actual readback settlement.
- Foreign import preserves original content before task creation, recovers untouched
  partial scaffolds, and distinguishes same titles with different source intent.
- Explicit reviewed source/destination/drop-reason trace, public Brain destinations,
  outside-project verified ZIP, phase journal and repeat-safe removal of obsolete trackers.
  Code/assets/private/linked paths, changed targets/sources and oversized instruction
  removals are refused. Semantically unfamiliar trackers require host reconciliation;
  there is no claim that a generic parser understands every vendor format.
- Frontend and backend share an explicit quality/verification scenario protocol; risk
  probe → real first journey → remaining scope, existing design/architecture reuse,
  UI Triad, state/error/auth/retry/persistence/migration cases and independent review.

## Verification

The full runnable entry point is `python skills/project-brain/scripts/test_brain.py`.
It includes baseline/migration/history recovery, protocol/CLI approval flows, process
containment/quoting/log integrity, pool/routing tests and adoption safety/retry checks.
Independent review re-ran concrete API-label, stale-quota, session/adapter race, HTML
deletion, instruction-loss, rewrite-retry and interrupted-import reproductions. Repairs
passed those reproductions; source-bound check/review records are retained in the
development checkpoint commit before its temporary `.project-brain/` is removed.

This host is Windows/Python 3.11.15; all Python source was also parsed with Python-3.8
grammar. That is not runtime proof on Python 3.8/POSIX. Native Windows JobObject and
file-lock behavior were exercised with harmless local subprocesses and temporary roots.

## Actual worker use and limits

Low-cost native workers performed discovery and disjoint implementation; high-model
work was architecture and independent security review. A bounded read-only OpenCode
`opencode/big-pickle` CLI job read the protocol and returned three acceptance risks
(dispatch binding, reservation identity, archive completeness); the protocol now names
their exact implemented checks. MiniMax managed CLI attempts returned intention-only
output without producing files, so no implementation was accepted from them. Unsupported
MiniMax-M3 effort flags were removed/rejected rather than silently upgraded. External
Codex/Claude/Antigravity inference was excluded as requested. No automatic paid fallback,
store upload/publication, AWS service or global skill installation was performed.

Session approval is a declared record of the actual user's decision, not authenticated
identity. Task digests prove freshness, not the truth of visual observations. A fresh
quota snapshot cannot reserve tokens against another client or cap in-flight spending.
Provider APIs that do not expose quota remain unknown; the explicit user cap governs
their approved jobs. CLI process containment is not a filesystem/network sandbox.

## Final repository cleanup

Once implementation acceptance and checkpointing finish, remove only this repository's
temporary `.project-brain/` and self-boot pointer, preserving source, tests, this delivery
record, requirements, architecture decisions and Git history. Historical PB-006 directory
submission was outside scope and is not resumed; its provider-wait record stays in Git.
The distributed skill still creates/uses `.project-brain/` in consumer projects normally.

Final checks after removal: full test entry point, version/manifests `3.1.0`, `boot` gives
NO_BRAIN on this source repository, no stale self-boot instructions, clean worktree and
remote branch HEAD matches local HEAD. The ordered overview records the final ticks.
