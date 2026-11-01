"""Default-protocol release regressions found by independent review."""
from contextlib import contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from types import SimpleNamespace

import brain as B
import runtime_context as C
import runtime_orchestration as O
import runtime_runs as L
import runtime_verify as V
import runtime_protocol as R
import runtime_agents as A
from test_routing import _project
from test_orchestration import denied, report


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(prefix="pb-production-") as tmp:
        root = Path(tmp) / "project"
        root.mkdir()
        with redirect_stdout(io.StringIO()):
            _project(root, legacy=False)
        B.write_atomic(B.bp(root) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nProve the default orchestration lifecycle.\n")
        file = B.bp(root) / "tasks/PB-001.md"
        B.write_atomic(file, B.read(file).replace("Risk: LOW", "Risk: MEDIUM"))
        O.git(root, "init")
        O.git(root, "config", "user.name", "Fixture Human")
        O.git(root, "config", "user.email", "human@example.invalid")
        with patch.dict(os.environ, {"PB_AGENTS_REGISTRY": str(Path(tmp) / "private/agents.json")}):
            B.set_session_modes(root, "native", "native", schedule="parallel", max_parallel=3)
            R.reconcile(B, root, B.find_task(root, "PB-001"), "Fixture goal and scope confirmed")
            O.git(root, "add", ".")
            O.git(root, "commit", "-m", "Protocol one fixture")
            directory = L.directory(B, root)
            db = L.Ledger(directory / "runs.sqlite3")
            try:
                yield root, directory, db
            finally:
                db.close()


def complete(db, run, model, **extra):
    value = {"request_key": run["spec"]["idempotencyKey"], "host": "fixture-host", "model": model,
             "tier": run["spec"]["tier"], "job_id": "job-" + run["id"], "state": "SUCCEEDED", "report": report()}
    value.update(extra)
    return O.native_receipt(db, run["id"], value)["actor"]


def implementation(root, directory, db):
    run = O.prepare(B, root, db, directory, "PB-001", "EXECUTE", "native")
    O.submit(B, root, db, directory, run["id"])
    path = O.workspace(run, directory)
    (path / "src/a.py").write_text("accepted = True\n", encoding="utf-8")
    actor = complete(db, run, "implementation-model")
    denied(lambda: O.verify(B, root, db, directory, run["id"], "invented-director"), "actual implementer")
    checked = O.verify(B, root, db, directory, run["id"], actor)
    assert checked["exit"] == 0, checked
    return run, actor, Path(checked["candidate"])


def review(root, directory, db, candidate):
    run = O.prepare(B, candidate, db, directory, "PB-001", "REVIEW", "native")
    O.submit(B, candidate, db, directory, run["id"])
    actor = complete(db, run, "review-model", report=dict(report(), verdict="PASS", findings=[]))
    rc, lines = V.review(B, candidate, "PB-001", actor, "PASS")
    assert rc == 0, lines
    value = B.find_task(candidate, "PB-001")
    B.write_atomic(value["file"], B.read(value["file"]).replace("- [ ] [machine]", "- [x] [machine]"))
    owner = B.find_task(candidate, "PB-001")["owner"]
    rc, lines = V.accept(B, candidate, "PB-001", actor=owner)
    assert rc == 0, lines
    return actor


def main():
    assert O.native_actor("host", "provider/model") != O.native_actor("host/provider", "model")
    with fixture() as (root, directory, db):
        first = O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native")
        second = O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native")
        B.set_session_modes(root, "native", "native", schedule="serial", max_parallel=1)
        O.submit(B, root, db, directory, first["id"])
        denied(lambda: O.submit(B, root, db, directory, second["id"]), "CAPACITY")
        complete(db, first, "implementation-model", state="RUNNING")
        action = O.command(B, SimpleNamespace(action="cancel", root=str(root), run=first["id"]))
        assert action["host_action"] == "request_cancel" and db.get(first["id"])["state"] == "CANCEL_REQUESTED"
        complete(db, first, "implementation-model", state="CANCELLED")
        assert db.get(first["id"])["state"] == "CANCELLED"
    with fixture() as (root, directory, db):
        # Current permission and intent must be checked before first launch.
        high = O.prepare(B, root, db, directory, "PB-001", "EXECUTE", "native", tiers=["H"])
        B.set_session_modes(root, "native-low", "native")
        denied(lambda: O.submit(B, root, db, directory, high["id"]), "tier cap")
        B.set_session_modes(root, "native", "native")
        O.submit(B, root, db, directory, high["id"])
        denied(lambda: complete(db, high, "wrong-model", tier="L"), "selected resource")
        complete(db, high, "high-model", state="FAILED")
        declared = db.prepare(dict(high["spec"], kind="REVIEW", tiers=list("LMH")))
        declared = db.transition(declared["id"], "SUBMITTING", declared["version"])
        denied(lambda: complete(db, declared, "wrong-model", tier="L"), "quality floor")
        complete(db, declared, "high-model", state="FAILED")

        run, actor, candidate = implementation(root, directory, db)
        assert R.enabled(B, candidate)
        live = B.find_task(candidate, "PB-001")
        saved = B.read(live["file"])
        B.write_atomic(live["file"], saved.replace("Worker completed.", "Weakened acceptance."))
        denied(lambda: O.verify(B, root, db, directory, run["id"], actor), "contract")
        B.write_atomic(live["file"], saved)
        review(root, directory, db, candidate)
        assert O.integrate(B, root, db, directory, run["id"])["integration"] == "MERGED"
        accepted_task = B.find_task(root, "PB-001")
        assert V.current_checks(B, root, accepted_task, R.task_digest(B, root, accepted_task)[0], B.contract(accepted_task))
        # Normal committed task GC must not break integration-intent readback.
        O.git(root, "rm", ".project-brain/tasks/PB-001.md")
        O.git(root, "commit", "-m", "Fixture closed-task collection")
        assert O.integrate(B, root, db, directory, run["id"])["integration"] == "MERGED"

    with fixture() as (root, directory, db):
        run, actor, candidate = implementation(root, directory, db)
        review(root, directory, db, candidate)
        # A normal Git hook may run, but its changed tree must never be promoted.
        hook = L.canonical(B, root) / "hooks/pre-commit"
        hook.write_text("#!/bin/sh\nprintf 'unverified = True\\n' > src/a.py\ngit add src/a.py\n", encoding="utf-8")
        hook.chmod(0o755)
        head = O.git(root, "rev-parse", "HEAD")
        denied(lambda: O.integrate(B, root, db, directory, run["id"]), "Commit hooks")
        assert O.git(root, "rev-parse", "HEAD") == head
        assert (root / "src/a.py").read_text() == "pass\n"
        hook.unlink()
        O.rebuild(B, root, db, directory, run["id"])
        assert list((Path(directory) / "recovery").iterdir())
        checked = O.verify(B, root, db, directory, run["id"], actor)
        assert checked["exit"] == 0

    with fixture() as (root, directory, db):
        run, actor, candidate = implementation(root, directory, db)
        # A stale candidate cannot reopen parallel admission after the lead
        # explicitly switches the authoritative origin to SERIAL.
        B.set_session_modes(root, "native", "native", schedule="serial", max_parallel=1)
        first = O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native")
        denied(lambda: O.prepare(B, candidate, db, directory, "PB-001", "REVIEW", "native"), "CAPACITY")
        assert db.policy() == {"schedule": "serial", "cap": 1}
        db.transition(first["id"], "CANCELLED", first["version"])
        # A different host label cannot make the same model independent, even
        # if the global implementation registry record disappeared.
        reviewer = O.prepare(B, candidate, db, directory, "PB-001", "REVIEW", "native")
        O.submit(B, candidate, db, directory, reviewer["id"])
        reviewer_actor = complete(db, reviewer, "provider/implementation-model", host="second-host",
                                  report=dict(report(), verdict="PASS", findings=[]))
        data = A.load()
        data["models"].pop(actor)
        A.save(data)
        denied(lambda: V.review(B, candidate, "PB-001", reviewer_actor, "PASS"), "implemented")

    with fixture() as (root, directory, db):
        run, actor, candidate = implementation(root, directory, db)
        review(root, directory, db, candidate)
        hook = L.canonical(B, root) / "hooks/post-merge"
        hook.write_text("#!/bin/sh\ncase \"$PWD\" in */project) printf 'unverified = True\\n' > src/a.py;; esac\n", encoding="utf-8")
        hook.chmod(0o755)
        denied(lambda: O.integrate(B, root, db, directory, run["id"]), "Target changed")
        assert db.get(run["id"])["verification"] == "STALE"
        assert db.get(run["id"])["integration"] == "MERGED"
        assert (root / "src/a.py").read_text() == "unverified = True\n"

    with fixture() as (root, directory, db):
        run = O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native")
        O.submit(B, root, db, directory, run["id"])
        O.native_receipt(db, run["id"], {"host": "fixture-host", "model": "implementation-model", "tier": "L",
                                        "state": "RUNNING", "request_key": run["spec"]["idempotencyKey"], "job_id": "original-job"})
        backup = db.backup(Path(directory).parent / "portable.sqlite3")
        clone = root.parent / "relocated"
        O.git(root.parent, "clone", str(root), str(clone))
        destination = L.directory(B, clone)
        result = O.restore(B, clone, destination, backup)
        assert result["restored"] == 1
        restored = L.Ledger(destination / "runs.sqlite3")
        try:
            assert restored.get(run["id"])["state"] == "UNKNOWN"
            denied(lambda: O.submit(B, clone, restored, destination, run["id"]), "RESTORED_READBACK_ONLY")
            denied(lambda: O.command(B, SimpleNamespace(action="cancel", root=str(clone), run=run["id"])), "RESTORED_READBACK_ONLY")
            denied(lambda: O.restore(B, clone, destination, backup), "never overwritten")
            assert db.get(run["id"])["state"] == "RUNNING", "Restore must not stop or mutate the original host"
        finally:
            restored.close()

    with fixture() as (root, directory, db):
        run = O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native")
        B.write_atomic(B.bp(root) / "constraints.md", "# Constraints\nNew mandatory policy\n")
        denied(lambda: O.submit(B, root, db, directory, run["id"]), "INTENT_PENDING")
        # A large number of matches retains only the requested result page.
        (root / "many.py").write_text("needle\n" * 20000, encoding="utf-8")
        result = C.discover(B, root, "needle", limit=2)
        assert result["total"] == 20000 and len(result["results"]) == 2
        result = C.discover(B, root, "needle", max_bytes=1)
        assert result["scan_truncated"] and result["next_file"]
    with fixture() as (root, directory, db):
        run = O.prepare(B, root, db, directory, "PB-001", "EXECUTE", "native")
        O.submit(B, root, db, directory, run["id"])
        complete(db, run, "implementation-model", report=dict(report(), status="partial", blockers=["Missing required behavior"]))
        denied(lambda: O.snapshot(B, root, db, directory, run["id"]), "partial/blocked")
        assert O.reject(B, root, db, run["id"], "Inspected partial output; implementation is incomplete")["integration"] == "REJECTED"
        assert not O.advance(B, root, db, directory, "native", None)["started"]
        fresh = O.prepare(B, root, db, directory, "PB-001", "EXECUTE", "native")
        assert fresh["id"] != run["id"] and db.get(run["id"])["report"]["status"] == "partial"
    print("PASS: protocol1 independent identities, immutable contract, authoritative sessions, hook mutation at both ends, GC readback, safe relocated restore, bounded search")


if __name__ == "__main__":
    main()
