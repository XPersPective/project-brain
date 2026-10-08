#!/usr/bin/env python3
"""Self-check for brain.py: builds a throwaway Git repo and walks the main states.

  python scripts/test_brain.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BRAIN = Path(__file__).resolve().parent / "brain.py"


def run(root, *args):
    r = subprocess.run([sys.executable, str(BRAIN), *args, str(root)] if args[0] != "new"
                       else [sys.executable, str(BRAIN), "new", str(root), *args[1:]],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def edit(root, rel, old, new):
    p = root / rel
    p.write_text(p.read_text(encoding="utf-8").replace(old, new), encoding="utf-8", newline="\n")


def commit(root, msg):
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", msg)


def main():
    root = Path(tempfile.mkdtemp(prefix="pb-test-"))
    try:
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@t")
        git(root, "config", "user.name", "t")
        write(root, "src/auth/a.py", "a = 1\n")
        write(root, "src/billing/b.py", "b = 1\n")
        write(root, "package.json", json.dumps({"scripts": {"test": "jest"}}))
        commit(root, "initial")

        assert run(root, "boot")[1].startswith("STATE: NO_BRAIN")
        assert "test=npm run test" in run(root, "map")[1]
        write(root, "CLAUDE.md", "# rules\n")
        out = run(root, "init")[1]
        assert "POINTER AGENTS.md (created)" in out and "POINTER CLAUDE.md (appended)" in out, out
        assert "GEMINI.md" not in out and not (root / "GEMINI.md").exists()
        assert "POINTER" not in run(root, "init")[1]  # idempotent
        assert '"npm run test"' in (root / ".project-brain/config.yaml").read_text(encoding="utf-8")

        write(root, ".project-brain/current.md",
              "# Current Architecture\n\n## Map\n- `src/auth/a.py` — auth\n\n## Domains\n\n"
              "### Auth\nStatus: VERIFIED\nSources: `src/auth/**`\n\n"
              "### Billing\nStatus: OBSERVED\nSources: `src/billing/**`\n")
        assert run(root, "new", "Auth task")[1].startswith("CREATED .project-brain/tasks/PB-001.md (READY)")
        assert "(PLANNED)" in run(root, "new", "Billing task", "--depends", "PB-001")[1]
        edit(root, ".project-brain/tasks/PB-001.md", "Areas: <`src/x/**`, `tests/x/**`>", "Areas: `src/auth/**`")
        commit(root, "chore(brain): establish project baseline\n\nPB-Genesis: true\nPB-Current-Checkpoint: all")

        out = run(root, "boot")[1]
        assert "STATE: RESUME" in out and "FOCUS PB-001" in out and "CMDS: test=npm run test" in out, out

        # interrupted: active task, dirty file inside its Areas
        edit(root, ".project-brain/tasks/PB-001.md", "Status: READY", "Status: IN_PROGRESS")
        with open(root / ".project-brain/tasks/PB-001.md", "a", encoding="utf-8") as f:
            f.write("\n## Resume\nNext: fix token expiry\n")
        write(root, "src/auth/a.py", "a = 2\n")
        out = run(root, "boot")[1]
        assert "STATE: INTERRUPTED" in out and "next: fix token expiry" in out, out

        # dirty outside the active task's Areas
        write(root, "src/billing/b.py", "b = 2\n")
        out = run(root, "boot")[1]
        assert "STATE: DIRTY" in out and "src/billing/b.py" in out, out
        git(root, "checkout", "--", "src/billing/b.py")

        # complete PB-001: delete task file, checkpoint auth
        (root / ".project-brain/tasks/PB-001.md").unlink()
        commit(root, "feat(auth): x [PB-001]\n\nPB-Task: PB-001\nPB-Verification: local\nPB-Current-Checkpoint: auth")
        out = run(root, "boot")[1]
        assert "STATE: RESUME" in out and "1 open, 1 done" in out and "hint: deps done" in out, out

        # IDs are never reused, even after every task file is gone
        (root / ".project-brain/tasks/PB-002.md").unlink()
        assert "PB-002.md" in run(root, "new", "Next")[1]
        (root / ".project-brain/tasks/PB-002.md").unlink()
        commit(root, "chore: drop")
        # checkpoint-less brain commit above keeps billing/auth fresh; external source commit makes billing stale
        write(root, "src/billing/b.py", "b = 3\n")
        commit(root, "external change")
        out = run(root, "boot")[1]
        assert "STATE: ADVANCED" in out and "STALE billing: src/billing/b.py" in out and "STALE auth" not in out, out
        assert "STALE billing" in run(root, "changed")[1]

        # tolerant reader: notes on the Status line, a kept DONE file, partial commits of an open task
        write(root, ".project-brain/tasks/PB-020.md", "# PB-020 — x\nStatus: READY — waiting on design\n")
        write(root, ".project-brain/tasks/PB-021.md", "# PB-021 — y\n\n## Status\n\nDONE (2026-09-29) — commit abc\n")
        commit(root, "wip part 1\n\nPB-Task: PB-020")
        out = run(root, "boot")[1]
        assert "PB-020 READY" in out and "PB-021" not in out.split("PLAN:")[1].split("FOCUS")[0], out
        assert "finished task files still present: PB-021" in out and "1 open, 1 done" in out, out
        val = run(root, "validate")[1]
        assert "PB-020: notes on the Status line" in val and "PB-021: finished task file kept" in val, val
        (root / ".project-brain/tasks/PB-020.md").unlink()
        (root / ".project-brain/tasks/PB-021.md").unlink()

        # validate: dependency cycle is a FAIL
        write(root, ".project-brain/tasks/PB-010.md", "# PB-010 — a\nStatus: PLANNED\nDepends: PB-011\n")
        write(root, ".project-brain/tasks/PB-011.md", "# PB-011 — b\nStatus: PLANNED\nDepends: PB-010\n")
        code, out = run(root, "validate")
        assert code == 2 and "dependency cycle" in out, out

        # long current.md: LOAD names only Map + the focus task's domain lines
        filler = "".join(f"- line {i}\n" for i in range(150))
        write(root, ".project-brain/current.md", "# Current\n\n## Map\n- `src` — code\n\n## Domains\n\n"
              "### Billing\nSources: `src/billing/**`\n" + filler + "\n### Auth\nSources: `src/auth/**`\n- x\n")
        write(root, ".project-brain/tasks/PB-030.md", "# PB-030 — z\nStatus: READY\nDomains: auth\n")
        out = run(root, "boot")[1]
        assert "current.md (lines 3-5, 161-163)" in out and "PB-030 is not an executable spec" in out, out

        # priority beats ID order; a full spec is accepted
        spec = ("# PB-031 — urgent\nStatus: READY\nPriority: P1\nTier: L\n\n## Objective\nx\n\n## Steps\n"
                "1. edit `a.py`\n\n## Acceptance\n- [ ] test passes\n\n## Verify\n- `pytest -q`\n")
        write(root, ".project-brain/tasks/PB-031.md", spec)
        out = run(root, "boot")[1]
        assert "FOCUS PB-031 (READY, P1, tier L" in out and "PB-031 is not an executable spec" not in out, out
        print("OK: brain.py checks passed")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    migrate_checks()


V3_TASK = """# PB-004 — Old style task

## Status

READY — waiting on a design note

## Objective

Do the thing.

## Dependencies

- PB-002

## Affected Areas

- `lib/a.dart`
- credentials.py

## Acceptance Criteria

- first condition
- second condition

## Verification

Risk: HIGH — irreversible store upload

Required:
- `flutter test`

## Architecture Impact

Expected: YES

Domains: publishing
"""

V0_FILE = """<!-- project-brain:v1 -->
# PROJECT BRAIN — demo
> **Goal:** v1 #abc · **Goal status:** DRAFT

## 0. PROTOCOL
### 0.1 What this file is
standard text

## 1. GOAL
Ship the demo app.

## 2. TARGET ARCHITECTURE
Flutter app with offline cache.

## 3. CURRENT ARCHITECTURE
### Storage
Hive boxes in `lib/data/`.

## 4. FILE MAP
- `lib/main.dart` — entry

## 5. TASKS
### Faz 1 — Core
- [x] T1 [L] Setup
  - Done when: `flutter test` passes
- [ ] T2 [M] Add cache
  - Where: `lib/data/cache.dart`
  - Do: 1) add `Cache` class; 2) wire it in `main.dart`
  - Done when: `flutter test test/cache_test.dart` passes
  - Needs: T1
- [~] T3 [H] Sync
  - Where: `lib/sync/`
  - Do: 1) design sync
  - Done when: two devices converge
  - Needs: T2
- [ ] T3.1 [L] Sync retry
  - Do: 1) add retry
- [!] T4 [M] Publish (needs store credentials)

## 6. DECISION LOG
| D1 | Hive over sqlite | speed |

## 7. HANDOFF
Working on T3: conflict policy undecided.
"""


def migrate_checks():
    root = Path(tempfile.mkdtemp(prefix="pb-mig-"))
    try:
        # schema 3 -> 4: header lines, checkboxes, nothing lost
        write(root, ".project-brain/config.yaml", "schema_version: 3\ngit:\n  history_mode: preserve\n  push_policy: every-task\n")
        write(root, ".project-brain/current.md", "# Current\n\n## Domains\n### Publishing\nSources: `lib/**`\n")
        write(root, ".project-brain/target.md", "# Target\n\n## Objective\nship\n")
        write(root, ".project-brain/tasks/PB-004.md", V3_TASK)
        assert "STATE: LEGACY" in run(root, "boot")[1]
        out = run(root, "migrate")[1]
        assert out.startswith("PREVIEW") and "READY — waiting" in (root / ".project-brain/tasks/PB-004.md").read_text(encoding="utf-8")
        run(root, "migrate", "--apply")
        t = (root / ".project-brain/tasks/PB-004.md").read_text(encoding="utf-8")
        for needle in ("Status: READY", "Risk: HIGH", "Depends: PB-002", "Domains: publishing", "- [ ] first condition",
                       "`flutter test`", "irreversible store upload", "credentials.py", "waiting on a design note"):
            assert needle in t, (needle, t)
        cfg = (root / ".project-brain/config.yaml").read_text(encoding="utf-8")
        assert "schema_version: 4" in cfg and "history_mode: preserve" in cfg and "push: every-task" in cfg, cfg
        tgt = (root / ".project-brain/target.md").read_text(encoding="utf-8")
        assert "Status: CONFIRMED" in tgt and "## Goal" in tgt, tgt
        assert "STATE: LEGACY" not in run(root, "boot")[1]
        assert "NOTHING TO MIGRATE" in run(root, "migrate")[1]
    finally:
        shutil.rmtree(root, ignore_errors=True)

    root = Path(tempfile.mkdtemp(prefix="pb-mig0-"))
    try:
        # single-file PROJECT_BRAIN.md -> .project-brain/
        write(root, "PROJECT_BRAIN.md", V0_FILE)
        assert "STATE: LEGACY" in run(root, "boot")[1]
        run(root, "migrate", "--apply")
        b = root / ".project-brain"
        assert not (b / "tasks/PB-001.md").exists()  # closed tasks stay in history
        t2 = (b / "tasks/PB-002.md").read_text(encoding="utf-8")
        assert "Status: READY" in t2 and "Tier: M" in t2 and "1. add `Cache` class" in t2, t2
        assert "- [ ] `flutter test test/cache_test.dart` passes" in t2 and "Milestone: Faz 1 — Core" in t2, t2
        t3 = (b / "tasks/PB-003.md").read_text(encoding="utf-8")
        assert "Status: IN_PROGRESS" in t3 and "Depends: PB-002" in t3 and "Sub-task T3.1" in t3, t3
        assert "conflict policy undecided" in t3, t3  # handoff -> Resume of the active task
        assert "Status: BLOCKED" in (b / "tasks/PB-004.md").read_text(encoding="utf-8")
        assert "Status: DRAFT" in (b / "target.md").read_text(encoding="utf-8")
        assert "`lib/main.dart` — entry" in (b / "current.md").read_text(encoding="utf-8")
        assert "Hive over sqlite" in (b / "decisions/ADR-000.md").read_text(encoding="utf-8")
        assert (root / "PROJECT_BRAIN.md").exists()  # never deleted by the script
        print("OK: migrate checks passed")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
