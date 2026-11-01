"""Offline orchestration invariants; no providers, user projects or credentials."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

import brain as B
import runtime_context as C
import runtime_orchestration as O
import runtime_reports as Q
import runtime_runs as L
import runtime_agent_pool as P
from test_routing import _project


def denied(call, text=""):
    try:
        call()
    except ValueError as e:
        assert text in str(e), str(e)
    else:
        raise AssertionError("Expected rejection: " + text)


def report():
    return {"status": "completed", "summary": "Done", "files": [], "checks": [], "research": [], "blockers": []}


def spec(task="PB-001", areas=None):
    return {"task": task, "kind": "EXECUTE", "backend": "native", "areas": areas or ["src/a.py"],
            "resources": [], "contract": "c", "source": "s", "base": "b", "workspace": "w"}


NATIVE_ACTOR = O.native_actor("fixture", "fixture-worker")


def receipt(db, rid, value):
    value = dict({"model": "fixture-worker", "tier": db.get(rid)["spec"]["tier"]}, **value)
    return O.native_receipt(db, rid, value)


def main():
    assert L.conflict(["src/**/schema.ts"], ["src/db/schema.ts"])
    assert L.conflict(["src/foo*.py"], ["src/foo2.py"])
    assert L.conflict([], ["src/a.py"])
    assert not L.conflict(["src/a.py"], ["src/b.py"])
    tasks = [{"id": "PB-001", "deps": [], "status": "READY"},
             {"id": "PB-002", "deps": ["PB-001"], "status": "READY"}]
    assert L.ready(tasks, set(), set()) == ["PB-001"]
    assert L.ready(tasks, {"PB-001"}, {"PB-001"}) == ["PB-002"]
    denied(lambda: L.ready([dict(tasks[0], deps=["PB-002"]), tasks[1]], set(), set()), "cycle")
    denied(lambda: L.ready([dict(tasks[0], deps=["PB-999"])], set(), set()), "Unknown")
    assert Q.usage(None)["total"] is None
    assert Q.usage({"source": "fixture", "total": 100, "reasoning": 20})["total"] == 100
    denied(lambda: Q.usage({"source": "bad", "total": True}))
    measurements = [dict(case="fixture", acceptance="same", model="fixed", environment="fixed", accepted=True,
                         variant=v, seconds=2, director_usage={"source": "fixture", "total": n})
                    for v, n in (("baseline", 100), ("candidate", 40)) for _ in range(3)]
    assert Q.compare(measurements)["comparisons"][0]["pilot_target_met"]
    measurements[-1]["director_usage"] = None
    assert Q.compare(measurements)["comparisons"][0]["director_reduction_pct"] is None
    measurements[-1]["acceptance"] = "changed"
    denied(lambda: Q.compare(measurements), "Acceptance changed")
    long = dict(report(), summary="ü" * 20000, findings=["MAJOR: inspect"])
    assert len(json.dumps(Q.compact(long, "reference"), ensure_ascii=False).encode("utf-8")) <= 1024
    assert Q.compact(long, "reference")["decision_required"]
    with tempfile.TemporaryDirectory(prefix="pb-runs-") as tmp:
        directory = Path(tmp)
        path = directory / "runs.sqlite3"
        db = L.Ledger(path)
        r = db.prepare(spec())
        denied(lambda: db.prepare(spec("PB-002", ["src/b.py"])), "CAPACITY")
        db.configure("parallel", 2)
        denied(lambda: db.prepare(spec("PB-002")), "OWNERSHIP")
        r = db.transition(r["id"], "SUBMITTING", r["version"])
        r = db.transition(r["id"], "UNKNOWN", r["version"])
        db.configure("serial", 1)
        denied(lambda: db.prepare(spec("PB-002", ["src/b.py"])), "CAPACITY")
        # A new session cannot mutate a live/uncertain process.
        assert db.get(r["id"])["state"] == "UNKNOWN"
        r = db.transition(r["id"], "SUCCEEDED", r["version"], report=report())
        denied(lambda: db.transition(r["id"], "RUNNING", r["version"]), "transition")
        db.close()

        db = L.Ledger(path)
        assert db.get(r["id"])["report"] == report()
        review = dict(spec("PB-001"), kind="REVIEW")
        r2 = db.prepare(review)
        r2 = db.transition(r2["id"], "SUBMITTING", r2["version"])
        r2 = db.transition(r2["id"], "SUCCEEDED", r2["version"], report=report())
        assert r2["integration"] == "NOT_APPLICABLE" and r2["state"] not in L.ACTIVE
        # Process failure between event and state rolls back both.
        before = len(db.events(limit=100))
        try:
            with db.transaction():
                db.event(r2["id"], "SHOULD_ROLL_BACK", {})
                raise RuntimeError("injected")
        except RuntimeError:
            pass
        assert len(db.events(limit=100)) == before
        events = O.view(db)
        assert not O.view(db, events["cursor"])["events"]
        backup = db.backup(directory / "backup.sqlite3")
        restored = L.Ledger(backup)
        assert restored.get(r["id"])["report"] == report()
        restored.close()
        denied(lambda: db.backup(backup), "exists")
        db.db.execute("PRAGMA user_version=999")
        db.close()
        denied(lambda: L.Ledger(path), "Unsupported")

    # Two actual OS clients contend for one capacity slot; SQLite serializes the
    # admission transaction, not just a test's in-process lock.
    with tempfile.TemporaryDirectory(prefix="pb-race-") as tmp:
        path = Path(tmp) / "runs.sqlite3"
        L.Ledger(path).close()
        script = "import json,sys;from runtime_runs import Ledger;d=Ledger(sys.argv[1]);s=json.loads(sys.argv[2]);\ntry:d.prepare(s);print('admitted')\nexcept ValueError:print('blocked')\nfinally:d.close()"
        procs = [subprocess.Popen([sys.executable, "-B", "-c", script, str(path), json.dumps(spec("PB-00" + str(i)))],
                                  cwd=str(Path(__file__).parent), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in (1, 2)]
        outputs = [p.communicate(timeout=20) for p in procs]
        assert sorted(o[0].strip() for o in outputs) == [b"admitted", b"blocked"], outputs

    with tempfile.TemporaryDirectory(prefix="pb-orchestration-") as tmp:
        root = Path(tmp) / "project"
        root.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            _project(root)
        O.git(root, "init")
        O.git(root, "config", "user.name", "Fixture Human")
        O.git(root, "config", "user.email", "human@example.invalid")
        O.git(root, "add", ".")
        O.git(root, "commit", "-m", "Fixture baseline")
        B.set_session_modes(root, "native", "native", schedule="parallel", max_parallel=2)
        registry = Path(tmp) / "private" / "agents.json"
        with patch.dict(os.environ, {"PB_AGENTS_REGISTRY": str(registry)}):
            directory = L.directory(B, root)
            db = L.Ledger(directory / "runs.sqlite3")
            value = B.find_task(root, "PB-001")
            packet = C.packet(B, root, value)
            assert packet["spec"]["objective"] and isinstance(packet["architecture"], str)
            assert C.discover(B, root, "pass")["results"]
            source = C.discover(B, root)["source"]
            (root / "src/a.py").write_text("changed\n", encoding="utf-8")
            assert C.discover(B, root)["source"] != source
            O.git(root, "restore", "src/a.py")
            run = O.prepare(B, root, db, directory, "PB-001", "EXECUTE", "native")
            assert L.peek(B, root)[0]["run"] == run["id"]
            work = O.workspace(run, directory)
            assert L.canonical(B, root) == L.canonical(B, work)
            host = O.submit(B, root, db, directory, run["id"])
            assert host["host_action"] == "launch_once"
            denied(lambda: O.submit(B, root, db, directory, run["id"]), "receipt")
            (work / "src/a.py").write_text("completed = True\n", encoding="utf-8")
            receipt(db, run["id"], {"host": "fixture", "request_key": host["request_key"],
                                            "state": "SUCCEEDED", "report": report()})
            output = O.snapshot(B, root, db, directory, run["id"])
            assert O.git(root, "show", output + ":src/a.py") == "completed = True"
            assert db.get(run["id"])["verification"] == "PENDING"
            denied(lambda: O.integrate(B, root, db, directory, run["id"]), "verify")
            checked = O.verify(B, root, db, directory, run["id"], NATIVE_ACTOR)
            assert checked["exit"] == 0, checked
            candidate = Path(checked["candidate"])
            live = B.find_task(candidate, "PB-001")
            B.write_atomic(live["file"], B.read(live["file"]).replace("- [ ] [machine]", "- [x] [machine]"))
            rc, lines = O.V.accept(B, candidate, "PB-001", actor=NATIVE_ACTOR)
            assert rc == 0, lines
            (candidate / "src/a.py").write_text("unexpected = True\n", encoding="utf-8")
            denied(lambda: O.integrate(B, root, db, directory, run["id"]), "no longer accepted")
            (candidate / "src/a.py").write_text("completed = True\n", encoding="utf-8")
            rc, lines = O.V.accept(B, candidate, "PB-001", actor=NATIVE_ACTOR)
            assert rc == 0, lines
            original = db.annotate
            def crash_after_merge(rid, event, **values):
                if event == "INTEGRATED_PENDING_ACCEPTANCE":
                    raise RuntimeError("Injected crash after Git merge")
                return original(rid, event, **values)
            with patch.object(db, "annotate", side_effect=crash_after_merge):
                try:
                    O.integrate(B, root, db, directory, run["id"])
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Expected injected crash")
            # Idempotent readback after Git already moved; no second merge.
            denied(lambda: O.reject(B, O.workspace(run, directory), db, run["id"], "Attempt to reject after lost merge acknowledgement from worker checkout"), "already integrated")
            assert O.integrate(B, root, db, directory, run["id"])["integration"] == "MERGED"
            assert O.export(db)["runs"][0]["output"] == output
            clean = O.cleanup(B, root, db, directory, run["id"])
            assert clean["retained"] and clean["ledger"] == "preserved"
            db.close()

    with tempfile.TemporaryDirectory(prefix="pb-lost-ack-") as tmp:
        root = Path(tmp) / "project"
        root.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            _project(root)
        O.git(root, "init")
        O.git(root, "config", "user.name", "Fixture Human")
        O.git(root, "config", "user.email", "human@example.invalid")
        O.git(root, "add", ".")
        O.git(root, "commit", "-m", "Fixture")
        B.set_session_modes(root, "pool-all", "pool-all")
        with patch.dict(os.environ, {"PB_AGENTS_REGISTRY": str(Path(tmp) / "private/agents.json")}):
            directory = L.directory(B, root)
            db = L.Ledger(directory / "runs.sqlite3")
            run = O.prepare(B, root, db, directory, "PB-001", "EXECUTE", "pool")
            requests = []
            def rpc(tool, arguments):
                if tool == "pool_submit":
                    requests.append(arguments)
                    if len(requests) == 1:
                        raise ValueError("ACK lost after backend accepted")
                    return {"id": "one-existing-job"}
                if tool == "pool_get_task":
                    return {"state": "succeeded", "report": report()}
                raise AssertionError(tool)
            selected = {"selected": {"id": "fixture", "routeId": "fixture", "enabled": True}, "request": {"mode": "execute", "kind": "write", "routeId": "fixture", "modelId": "fixture"}}
            with patch.object(P, "select", return_value=selected), patch.object(P, "rpc", side_effect=rpc):
                denied(lambda: O.submit(B, root, db, directory, run["id"]), "ACK lost")
                assert db.get(run["id"])["state"] == "UNKNOWN"
                assert O.submit(B, root, db, directory, run["id"])["state"] == "SUCCEEDED"
                assert requests[0] == requests[1]
            db.close()
    with tempfile.TemporaryDirectory(prefix="pb-two-writers-") as tmp:
        root = Path(tmp) / "project"
        root.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            _project(root)
        first = root / ".project-brain/tasks/PB-001.md"
        content = first.read_text(encoding="utf-8").replace("`src/**`", "`src/a.py`")
        first.write_text(content, encoding="utf-8")
        (root / "src/b.py").write_text("pass\n", encoding="utf-8")
        (root / ".project-brain/tasks/PB-002.md").write_text(content.replace("PB-001", "PB-002").replace("src/a.py", "src/b.py"), encoding="utf-8")
        O.git(root, "init")
        O.git(root, "config", "user.name", "Fixture Human")
        O.git(root, "config", "user.email", "human@example.invalid")
        O.git(root, "add", ".")
        O.git(root, "commit", "-m", "Two independent fixture tasks")
        B.set_session_modes(root, "native", "native", schedule="parallel", max_parallel=2)
        with patch.dict(os.environ, {"PB_AGENTS_REGISTRY": str(Path(tmp) / "private/agents.json")}):
            directory = L.directory(B, root)
            db = L.Ledger(directory / "runs.sqlite3")
            runs = [O.prepare(B, root, db, directory, tid, "EXECUTE", "native") for tid in ("PB-001", "PB-002")]
            assert sum(r["state"] in L.ACTIVE for r in db.all()) == 2
            for n, run in enumerate(runs):
                response = O.submit(B, root, db, directory, run["id"])
                (O.workspace(run, directory) / ("src/a.py" if n == 0 else "src/b.py")).write_text("done = True\n", encoding="utf-8")
                receipt(db, run["id"], {"request_key": response["request_key"], "host": "fixture", "state": "SUCCEEDED", "report": report()})
            for run in runs:
                checked = O.verify(B, root, db, directory, run["id"], NATIVE_ACTOR)
                assert checked["exit"] == 0, checked
                candidate = Path(checked["candidate"])
                live = B.find_task(candidate, run["task"])
                B.write_atomic(live["file"], B.read(live["file"]).replace("- [ ] [machine]", "- [x] [machine]"))
                rc, lines = O.V.accept(B, candidate, run["task"], actor=NATIVE_ACTOR)
                assert rc == 0, lines
                O.integrate(B, root, db, directory, run["id"])
            assert (root / "src/a.py").read_text() == (root / "src/b.py").read_text() == "done = True\n"
            assert all(db.get(r["id"])["integration"] == "MERGED" for r in runs)
            # Failed writes remain human/director decisions, not implicit retry
            # candidates on the next scheduling tick.
            third = root / ".project-brain/tasks/PB-003.md"
            third.write_text(content.replace("PB-001", "PB-003"), encoding="utf-8")
            O.git(root, "add", str(third))
            O.git(root, "commit", "-m", "Next fixture task")
            failed = O.prepare(B, root, db, directory, "PB-003", "EXECUTE", "native")
            launch = O.submit(B, root, db, directory, failed["id"])
            receipt(db, failed["id"], {"request_key": launch["request_key"], "host": "fixture", "state": "FAILED"})
            assert not O.advance(B, root, db, directory, "native", None)["started"]
            db.close()
    print("PASS: orchestration packets, bounded views, durable transitions, serial drain, native receipts, isolated snapshot and merge readback")


if __name__ == "__main__":
    main()
