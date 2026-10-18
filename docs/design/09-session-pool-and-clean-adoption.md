# Confirmed follow-up requirements

Source: user, 2026-10-18, after the integration audit. These are requirements for the
next implementation slices, not claims that the current runtime already implements them.
Finish the active verification audit first. Keep this record outside self-hosted Brain
state so it survives the requested final removal of that state.

## Session model pool and user authority

"Oturum başında ... alt ajana verecek ... düşük token az tüketen ajan keşfi o yapacak."
"Hangi ... modelleri ... işleri ona vereceği ... kişiden teyit alması gerekiyor."

- At session start, quickly inspect the prior machine registry and discover installed
  coding CLI/provider resources (Codex, Claude, Antigravity, OpenCode and others).
  Prefer cache and bounded metadata probes; report stale/unknown observations honestly.
  Do not read credential contents or scan arbitrary files for API keys.
- Delegate discovery to an already authorized low/mid-cost lightweight agent, not an
  H model. If none is available, a deterministic local inventory may collect metadata;
  never silently use an expensive/paid model to discover cheap models.
- Present the concrete model pool, CLI/provider, available models/efforts, subscription
  versus API/free/unknown billing, quota windows/remaining/reset and freshness. Unknown
  access, unavailable quota and paid token budgets must not be presented as full quota.
- Propose director/architect, worker and reviewer assignments and model groups. The user
  chooses: approve, exclude/add models, promote/demote roles or change CLI/pool usage.
  Built-in H/M/L ratings are advisory; do not impose a permanent strong/weak grouping.
- Persist the confirmed session selection and routing/reserve policy outside project
  source memory where appropriate; show it on resume. Changes to models/access/billing
  invalidate the affected approval. No worker inference or automatic high-tier fallback
  before the relevant user confirmation; metadata discovery is not inference approval.
- After approval, orchestrate bounded CLI jobs with the selected models, sufficient
  effort, independent review and quota guards. Preserve 10% worker/25% director reserves;
  report remaining capacity without guaranteeing in-flight spend or other clients.

## Clean migration from other tracking skills

"Alınacaklar alındı ve onun bütün dosyaları ... silinir. Projenin temizlenmesi gerekiyor."

- When adopting Project Brain, read the prior planning state (Store Automation or any
  other tracking skill), verify claims against actual code, and carry useful intent,
  unfinished work, constraints, decisions and unresolved operations into one Brain.
- Keep only decision-relevant information. Completed work belongs to Git history; do
  not duplicate notes, logs or unnecessary tasks. Publishing/store scope stays excluded.
- Produce a source-to-destination/drop-reason trace and verify every open item, retained
  dependency and important decision before removing originals. Missing evidence blocks
  cleanup; it must never silently drop user intent or uncertain external operations.
- After successful adoption, remove obsolete project tracking files, their ignore
  entries and agent-instruction pointer blocks. On next boot there must be one source
  of truth, no repeated migration and no old tracking residue in the project.
- Cleanup applies to prior tracking state, not application source, team-owned docs or
  globally installed skills. Preserve unrelated edits and original untracked content in
  a recoverable out-of-project archive until verified; never delete via an unsafe path.

## This skill's own development state

"Proje bittikten sonra ... projeyi geliştirirken ... Project Brain ... dosyaları varsa
onların hepsini kaldır."

- Using the working-tree skill to test its own development is temporary dogfooding,
  not a dependency of the shipped skill. Always test the local source under review.
- Once the project work, including these follow-ups, is complete, remove the development
  `.project-brain/` and its pointer blocks from this repository. Keep skill sources,
  tests, design decisions and this durable requirement record; Git retains history.
- Before cleanup, confirm no unfinished requirement or untracked evidence would be lost;
  transfer necessary remaining records to normal project documentation. Do not ship a
  self-boot instruction that requires a removed development plan.
- Keep source version/manifests consistent with the actual completed feature set. This
  request does not authorize unrelated global skill removal or publishing.

## Interruptions and continuity

"Araya girdiğim zaman ana aksı kaybetme ... onları önce dosyaya yaz ... işler kaybolmasın."

- Treat incoming messages as steering, not an implicit cancellation of the main project.
- First save each new requirement/decision in the appropriate durable task or document;
  retain unresolved questions and explicitly mark what is recorded versus implemented.
- Preserve the main task's actual Next/Failing/Dirty state, incorporate any immediate
  constraint, then resume the same step. Explicit cancellation or incompatible scope is
  the exception. No work item may live only in chat or a forgotten temporary file.
