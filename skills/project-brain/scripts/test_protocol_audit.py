"""Small integration checks for cold handoff and executable task quality."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import os
import json
import subprocess
import sys
import tempfile
import time

import brain as B
import runtime_verify as V


def main():
    with tempfile.TemporaryDirectory(prefix="pb-protocol-audit-") as tmp:
        root = Path(tmp)
        with redirect_stdout(StringIO()):
            B.cmd_init(root)
        (root / "app.py").write_text("x = 1\n", encoding="utf-8")
        task = root / ".project-brain/tasks/PB-001.md"
        spec = ("# PB-001 — Recover external write\nStatus: READY\nPriority: P1\nTier: H\n"
                "Risk: LOW\nOwner:\nDepends: -\nAreas: `app.py`\nDomains: core\n"
                "\n## Objective\nTest concurrency recovery.\n\n## Steps\n1. Edit `app.py`.\n"
                "\n## Acceptance\n- [ ] [machine] recovery check passes\n"
                "\n## Verify\n- `python -c \"print(1)\"`\n\n## Evidence\n\n## Review\n")
        task.write_text(spec + "\n## External\n- save | response_unknown | readback: fetch record\n", encoding="utf-8")
        assert B.parse_task(task)["external"][0]["state"] == "response_unknown"
        out = StringIO()
        with redirect_stdout(out):
            B.cmd_boot(root)
            code = B.cmd_start(root, "PB-001", "test-lead")
        assert "STATE: READBACK_FIRST" in out.getvalue(), out.getvalue()
        assert code == 2 and B.parse_task(task)["status"] == "READY"
        task.write_text(spec + "\n## External\n- save: confirmed | readback: fetched\n", encoding="utf-8")
        assert B.parse_task(task)["external"][0]["state"] == "confirmed"
        with redirect_stdout(StringIO()):
            assert B.cmd_start(root, "PB-001", "test-lead") == 0
        started = B.parse_task(task)
        assert started["risk"] == "HIGH"
        assert B.start_records(started)[-1]["contract"] == B.contract(started)
        ui = B.parse_task(task, spec.replace("Domains: core", "Domains: ui"))
        assert "UI task missing Triad" in " ".join(B.task_errors(ui))
        ui = B.parse_task(task, ui["text"].replace("[machine] recovery check passes", "recovery check passes"))
        assert "UI task missing Triad" in " ".join(B.task_errors(ui))
        for actor in ("bad\ractor", "bad\tactor"):
            try:
                B.agent_id(actor)
            except ValueError:
                pass
            else:
                raise AssertionError("control character accepted in actor")

        # A live check can exceed the old 120s lease; age must never steal its lock.
        holder = root / "hold.py"
        holder.write_text("import sys, time\nfrom pathlib import Path\n"
                          f"sys.path.insert(0, {str(Path(B.__file__).parent)!r})\nimport brain as B\n"
                          f"with B.checkout_lock(Path({str(root)!r})):\n"
                          f"    Path({str(root / 'locked')!r}).touch()\n    time.sleep(30)\n", encoding="utf-8")
        proc = subprocess.Popen([sys.executable, str(holder)])
        try:
            deadline = time.monotonic() + 10
            while not (root / "locked").exists() and time.monotonic() < deadline:
                assert proc.poll() is None, "holder exited without acquiring lock"
                time.sleep(.02)
            assert (root / "locked").exists()
            os.utime(root / ".project-brain/.cache/writer.lock", (0, 0))
            try:
                with B.checkout_lock(root, timeout=.05):
                    raise AssertionError("live writer lock was stolen")
            except ValueError as exc:
                assert "Timed out" in str(exc)
        finally:
            proc.kill()
            proc.wait(timeout=5)
        # Process death releases the native lock without deleting its inode.
        with B.checkout_lock(root, timeout=.1):
            pass

    # Exercise the public CLI parser, approval gate and native handoff end to end.
    with tempfile.TemporaryDirectory(prefix="pb-pool-cli-") as tmp:
        root = Path(tmp)
        with redirect_stdout(StringIO()):
            B.cmd_init(root)
        import runtime_agents as A
        registry = root / "agents.json"
        A.save({"models": {"host-worker": {"cli": "host", "model_id": "fake-native", "pool": "local",
                                           "roles": ["worker"], "efforts": ["low"]}},
                "pools": {"local": {}}, "cli_agents": {}}, registry)
        env = dict(os.environ, PB_AGENTS_REGISTRY=str(registry))
        def cli(*args):
            return subprocess.run([sys.executable, B.__file__, *args], cwd=root, env=env,
                                  text=True, encoding="utf-8", capture_output=True, timeout=15)
        proposed = cli("agents", "session", "--new", "--json")
        assert proposed.returncode == 0, proposed.stderr
        session = json.loads(proposed.stdout)
        selection = root / "selection.json"
        selection.write_text(json.dumps({"models": {"host-worker": {"roles": ["worker"], "efforts": ["low"],
                                                                    "billing": "local", "max_jobs": 1}}}), encoding="utf-8")
        args = ("agents", "approve", str(selection), "--session", session["session_id"], "--note", "User selected this test host worker")
        denied = cli(*args)
        assert denied.returncode == 2 and "confirmed" in denied.stderr, denied.stdout + denied.stderr
        approved = cli(*args, "--user-confirmed")
        assert approved.returncode == 0 and "APPROVED" in approved.stdout, approved.stdout + approved.stderr
        boot = cli("boot")
        assert "MODEL_POOL: APPROVED" in boot.stdout, boot.stdout + boot.stderr
        revoked = cli("agents", "revoke")
        assert revoked.returncode == 0 and "REVOKED" in revoked.stdout
        # Repeating session display does not silently approve a revoked pool.
        display = cli("agents", "session", "--json")
        assert json.loads(display.stdout)["status"] == "REVOKED", display.stdout
    print("OK: protocol audit checks passed")


if __name__ == "__main__":
    main()
