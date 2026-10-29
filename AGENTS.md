# Developing Project Brain

Read `docs/PROJECT-OVERVIEW.md` and `docs/VERIFICATION.md` for current scope, verification and practical limits.
Use `skills/project-brain/` as the source under review; installed copies may be older.
This source repository has completed its temporary development plan. Do not recreate it merely because the distributed skill describes consumer-project tracking.

Keep the runtime dependency-free and Python 3.8+ compatible. Trace callers, reuse existing helpers, preserve user work, and leave a runnable check for non-trivial changes.
Run `python skills/project-brain/scripts/test_brain.py` after runtime changes. Store publishing/distribution remains outside scope.

Use the existing human Git identity. Never add AI/model/provider/bot author or
co-author credit, generated-by signatures, contributors entries or PR attribution.
Never rewrite history merely to alter attribution. Keep current source knowledge in
the overview, verification guide and accepted ADRs; do not accumulate audit reports.
