# Project Brain integration audit

Date: 2026-10-18

## Assigned prompt

Read Project Brain's actual implementation, callers, tests and instructions end to end.
Compare the non-publishing mechanisms in `D:/repositories/store-otomaston` with this
integration. Preserve Project Brain's identity, dependency-free runtime and user work.
Store uploads, release workflows, listing submissions and distribution automation are
excluded. Do not run external model jobs merely to test discovery.

Trace a new project, adoption, interruption, handoff, small worker task, UI task,
backend/state task, stale evidence, failed review, quota exhaustion and unknown access.
Reproduce defects before fixing shared causes. Check source/contract binding, actor
independence, command containment, privacy, lossless adoption and model eligibility.
Do not equate installed CLIs with authenticated access, unknown quota with capacity,
or a checklist with verified product quality. Prefer existing helpers and stdlib.

Make workflow guidance proportionate: reuse an existing design system and architecture;
require only applicable states and evidence, and keep worker context bounded. Record
observable findings, minimal fixes and runnable regression checks. Independently review
the final diff and report remaining limits honestly; never claim perfect output or a
guaranteed token/quota budget from heuristics.

## Results

The user's subsequent Master Prompt is the acceptance basis: UI foundation/Triad,
backend/state boundaries, bound verification and cold handoff, complexity/CLI/quota
orchestration, and explicit exclusion of store publishing/distribution.

| Source mechanism | Integration decision and verification |
| --- | --- |
| Store Automation plan/product quality | Reuse design/architecture, compare new directions, risk probe → real first journey → breadth; concrete applicable Acceptance in existing Target/tasks, no extra product database |
| Evidence and review | Preserve source/contract hashes; close model-alias self-review, reviewer-quality, current-scope risk and HIGH full-test bypasses; test stale source and changed reviewer policy |
| Process containment | Native Windows argv; bounded stdin and RPC waits; refuse linked log paths; native mutation/delegation lifetime locks, tested with real harmless subprocesses |
| Cold handoff | Both External formats parsed; READBACK_FIRST precedes starting/retrying work; explicit Resume guidance; waiting-user remains BLOCKED with a reason |
| Discovery/routing | Deterministic heuristic score and model floor; overrides obey normal eligibility, ownership and task-status checks; actual dispatch refuses stale/unknown quota and director-reserve fallback |
| Adoption | Preserve full original task detail for manual refinement; filter publication in SA, Taskmaster and flat checklists; retain originals and keep imports PLANNED, idempotent |
| Publishing/distribution | No upload, release, signing, store material or listing workflow imported or executed |

Concrete defects fixed include premature RPC stdin EOF (live quota was unavailable),
unbounded probe reads, timeout-bypassing stdin writes, stale/live lock theft after 120s,
duplicate same-owner worker dispatch, weak reviewer acceptance, Windows argument loss,
linked-log data loss, unknown-quota-as-full defaults, untyped UI criteria bypass and
discarded foreign task descriptions. New assertions live in `test_protocol_audit.py`,
`test_verify_audit.py`, `test_agents_audit.py` and run through `test_brain.py`.

## Validation and limits

- PB-008 contains tool-written source/contract-bound command results and independent
  review; no manual PASS/hash claims substitute for that evidence.
- Native doctor verified Windows JobObject containment. An isolated discovery registry
  found nine installed CLIs; a read-only live Codex metadata probe returned subscription
  quota after the handshake fix. No model inference job or paid API was started.
- Live remaining-quota probing currently supports Codex. Other providers need explicit
  access/quota metadata; installed CLI, cache or credential-file existence is not proof.
  Discovery supports more CLIs than the current dispatch adapters (Codex, Claude,
  Gemini, OpenCode, Antigravity and Qwen). Do not claim the others execute tasks yet.
- Imported foreign goals/ADRs and unsupported formats require manual reconciliation;
  the runtime detects them but only automatically extracts supported task sources.
  Mixed engineering/publication tasks may be skipped by conservative keyword filtering;
  split them manually. Existing Brain migration preserves intent instead of silently
  deleting historical publication tasks, which remain outside this audit's work.
- Wire schema remains 4. Earlier schema-5/FIX claims were design proposals. SHA-256
  digests check freshness; they are not signed attestations. Identity/waiver records
  are declared and trusted agents must inspect actual evidence.
- Model ratings/costs and complexity scores are heuristics, not measurements of current
  models. Native locks serialize one delegated worker per checkout; separate worktrees
  are needed for concurrent writers. Containment is not an OS permissions sandbox.
- A fresh quota snapshot cannot reserve tokens against unrelated concurrent clients or
  cap a model's in-flight spend. Stop dispatching below reserve; do not promise zero
  exhaustion. There is no automatic paid fallback.
- Tests ran on Windows/Python 3.11.15. Python-3.8 grammar was parsed, but Python 3.8
  execution and POSIX process-group behavior require those hosts. Real UI quality and
  backend correctness need the project's own observations, not this skill's self-tests.
- This work changes the repository source only; publication and global agent installation
  are separate operations and were not performed.
