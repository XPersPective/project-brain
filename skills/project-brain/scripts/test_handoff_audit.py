"""Offline adversarial regressions for economical, recoverable session handoff."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import brain as B
import migrate as M
import runtime_agents as A
import runtime_agent_pool as AP
import runtime_verify as V
from test_brain import commit, git, write
from test_routing import _project


def denied(call, *args, **kwargs):
    try:
        call(*args, **kwargs)
    except ValueError:
        return
    raise AssertionError("operation should have been refused")


def main():
    with tempfile.TemporaryDirectory(prefix="pb-handoff-") as tmp:
        root = Path(tmp)
        _project(root)
        # No-Git orphan evidence and backups are not disposable.
        write(root, ".project-brain/evidence/PB-999/view.png", "uncommitted capture")
        write(root, ".project-brain/migration-backup/facts.md", "unique intent")
        write(root, ".project-brain/.pending.tmp", "live atomic write")
        assert B.gc_brain(root, has_git=False) == []
        assert (B.bp(root) / "evidence/PB-999/view.png").exists()

        # Read-only boot leaves the complete project byte-for-byte unchanged.
        write(root, ".project-brain/config.yaml", "schema_version: 4\nskill_version: 3.3.1\n")
        before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()):
            B.cmd_boot(root, maintain=False)
        assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        raw_task = (B.bp(root) / "tasks/PB-001.md").read_bytes()
        M.auto_upgrade_v34(root)
        assert (B.bp(root) / "migration-backup/tasks/PB-001.md").read_bytes() == raw_task
        assert B.parse_config(root)["skill_version"] == B.VERSION
        # Repeated boot/upgrade is idempotent; future state must never be downgraded.
        upgraded_files = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        assert M.auto_upgrade_v34(root) == []
        assert upgraded_files == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        write(root, ".project-brain/config.yaml", "schema_version: 5\nskill_version: 9.0.0\n")
        denied(M.auto_upgrade_v34, root)
        denied(M.run, root, True)
        # A manual version-only upgrade must finalize its marker too.
        write(root, ".project-brain/config.yaml", B.config_text(root).replace(B.VERSION, "3.3.1"))
        with contextlib.redirect_stdout(io.StringIO()):
            assert M.run(root, True) == 0
        assert B.parse_config(root)["skill_version"] == B.VERSION
        cfg = B.parse_config(root)
        cfg["protocol_version"] = "0"  # Legacy handoff fixture; strict behavior has its own suite.
        write(root, ".project-brain/config.yaml", B.config_text(root, cfg))

        # Modes are resettable and bind to a host session when one is supplied.
        with patch.dict(os.environ, {"PB_SESSION_ID": "first"}):
            B.set_session_modes(root, "SOLO", "SOLO", new=True)
            assert B.get_session_modes(root)["rev"] == "solo"
        with patch.dict(os.environ, {"PB_SESSION_ID": "second"}):
            assert B.get_session_modes(root)["rev"] == ""
            B.set_session_modes(root, new=True)
            assert B.get_session_modes(root)["exec"] == ""
        B.set_session_modes(root, "SOLO", "SOLO", new=True)
        args = SimpleNamespace(root=str(root), agents_cmd="scan")
        with patch.object(AP, "rpc", side_effect=AssertionError("Pool must stay offline")):
            denied(AP.agents, B, args)

        # --force cannot escape P-L, while P-ALL admits a high-tier dry run.
        task = B.find_task(root, "PB-001")
        args = SimpleNamespace(force=True, timeout=5, cli="", model="", effort="", group="", dry_run=True)
        high = dict(A.score_task(B, root, task), effective_tier="H", must_split=False)
        B.set_session_modes(root, "P-L", "P-L")
        with patch.object(AP, "rpc", side_effect=AssertionError("cap checked before RPC")):
            denied(AP.delegate, B, root, task, high, args)
        B.set_session_modes(root, "P-ALL", "P-ALL")
        args.force = False
        selected = {"alias": "high-worker", "strength": "high", "request": {"group": "high"}}
        with patch.object(AP, "select", return_value=selected), contextlib.redirect_stdout(io.StringIO()):
            assert AP.delegate(B, root, task, high, args) == 0

        # Explicit self-review cannot override an independent review selection.
        B.set_session_modes(root, "SOLO", "P-ALL")
        task = B.find_task(root, "PB-001")
        B.set_headers(task["file"], {"Status": "IN_PROGRESS", "Owner": "lead"})
        denied(V.review, B, root, "PB-001", "lead", "PASS", self_review=True)
        denied(V.accept, B, root, "PB-001", self_review=True)

        # A synthetic acceptance PASS must not replace the actual SOLO audit.
        B.set_session_modes(root, "SOLO", "SOLO")
        text = B.read(task["file"]).replace("Risk: LOW", "Risk: MEDIUM").replace("- [ ]", "- [x]")
        B.write_atomic(task["file"], text)
        assert V.check(B, root, "PB-001")[0] == 0
        code, lines = V.accept(B, root, "PB-001")
        assert code == 1 and "REVIEW_PENDING" in "\n".join(lines), lines
        assert V.latest_review(B.find_task(root, "PB-001")["review_lines"]) is None
        assert V.review(B, root, "PB-001", "lead", "PASS", self_review=True)[0] == 0
        assert V.accept(B, root, "PB-001")[0] == 0

        # A valid task check does not cover outside edits or missing/tampered logs.
        B.set_header(task["file"], "Status", "IN_PROGRESS")
        task = B.find_task(root, "PB-001")
        assert B.takeover_status(root, task, True, []).startswith("SKIP")
        assert B.takeover_status(root, task, True, ["package.json"]).startswith("REQUIRED")
        match = next(V.CHECK_RE.match(l) for l in task["evidence_lines"] if V.CHECK_RE.match(l))
        log = B.bp(root) / match.group("log")
        log.write_text("tampered", encoding="utf-8")
        assert not B.takeover_status(root, task, True, []).startswith("SKIP")
        log.unlink()
        assert not B.takeover_status(root, task, True, []).startswith("SKIP")

        # Typed hints require both the right kind and an unchanged artifact.
        task["items"] = [{"kind": "visual", "id": "1234abcd", "text": "render", "done": False}]
        value, _ = V.digest(B, root, task["areas"])
        con = B.contract(task)
        capture = B.bp(root) / "evidence/PB-999/view.png"
        ref = ".project-brain/evidence/PB-999/view.png@" + V._hash(capture)
        task["evidence_lines"] = [f"- [visual] observed | criterion=1234abcd | files={ref} | by=lead | digest={value} | contract={con}"]
        assert B.proven_criteria_ids(root, task) == {"1234abcd"}
        capture.write_text("changed", encoding="utf-8")
        assert B.proven_criteria_ids(root, task) == set()
        task["evidence_lines"] = [f"- [interaction] observed | criterion=1234abcd | by=lead | digest={value} | contract={con}"]
        assert B.proven_criteria_ids(root, task) == set()

        # Preserve all Verify logs for open work, including a fourth command.
        for n in range(4):
            write(root, f".project-brain/.cache/runs/PB-001-{n}.log", "proof")
        assert B.gc_brain(root, has_git=True, completed=set()) == []
        assert len(list((B.bp(root) / ".cache/runs").glob("PB-001-*.log"))) == 4

        # A historical closure cannot authorize deletion of newly edited DONE work.
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@t")
        git(root, "config", "user.name", "t")
        B.set_header(task["file"], "Status", "DONE")
        commit(root, "close\n\nPB-Task: PB-001\nPB-Verification: domain\nPB-Current-Checkpoint: all")
        closed_task = task["file"].read_text(encoding="utf-8")
        task["file"].write_text(closed_task + "\nnew user fact\n", encoding="utf-8")
        B.gc_brain(root)
        assert task["file"].exists()
        task["file"].write_text(closed_task, encoding="utf-8")
        # Staged differences also survive even if worktree matches HEAD.
        write(root, ".project-brain/tasks/PB-001.md", closed_task + "\nstaged fact\n")
        git(root, "add", ".project-brain/tasks/PB-001.md")
        task["file"].write_text(closed_task, encoding="utf-8")
        B.gc_brain(root)
        assert task["file"].exists()
        git(root, "add", ".project-brain/tasks/PB-001.md")
        B.gc_brain(root)
        assert not task["file"].exists()
        assert capture.exists()  # Unknown task's artifacts remain.
        assert (B.bp(root) / "migration-backup/facts.md").exists()
        assert (B.bp(root) / ".pending.tmp").exists()

    print("PASS: handoff integrity, conservative GC, explicit SOLO review, offline modes and migration recovery")


if __name__ == "__main__":
    main()
