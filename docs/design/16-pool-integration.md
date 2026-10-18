# Separate Pool integration — 3.3.0

Brain owns planning, local research, risk/scoring, source evidence and independent
review. CLI Agent Pool 1.1.0 owns model catalogs, native authentication, owner
strength memberships/effort, quota admission, worker containment and task recovery.
The integration uses only a standard-library Python client of Pool's agent JSON
stdin transport. Pool does not depend on or embed Brain.

Default `agents scan/list/quota/select` and `delegate` use Pool. An explicit
`--backend direct` or `--registry` preserves the former standalone authority.
There is no silent direct/paid/director fallback. Owner grouping determines
strength; automatic model-name hints are explicitly estimates rather than scores.

The per-project/task dispatch journal is outside the repository. Persist request,
key, actor and selected strength before send, recover the exact same request/key
after a lost acknowledgement, then poll the saved ID. A changed contract or
failed write requires inspection, never a fresh automatic dispatch. Reviewer
strength reads that immutable task record rather than a model's latest selection.
Pool's worker environment identifies nested work and Brain refuses re-delegation.

Repeatable checks:

```text
python -B skills/project-brain/scripts/test_brain.py
python -B skills/project-brain/scripts/test_pool_integration.py --pool-entry <Pool>/bin/pool.js
git diff --check
```

The integration check uses a fresh private data directory, stopped daemon, temp
project, synthetic shell-free worker and real MCP/JSON/SQLite/supervisor/evidence
path. It asserts daemon survival, mandatory effort and one execution across resume.
It consumes no provider quota and touches no user project. Offline checks cover
strict pool failure, reserve floors, transport timeout, immutable review strength,
recovery and recursive dispatch refusal. Provider availability and actual hardware
microphone recognition remain environment-dependent; percentage quotas cannot
guarantee an exact token budget or that another client will not exhaust an account.
