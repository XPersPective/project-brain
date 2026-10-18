#!/usr/bin/env python3
"""Stdlib regression checks for verification boundaries; uses throwaway projects only."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

import brain as B
import runtime_verify as V
import runtime_pool as P
import runtime_adopt as A


def command(*args):
    return subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)


def main():
    args = [r"C:\Program Files\Python\python.exe", "-c", 'print("quoted")', r"src\check.py"]
    assert V.command_argv(command(*args)) == args
    with tempfile.TemporaryDirectory(prefix="pb-verify-audit-") as folder:
        root = Path(folder)
        source = root / "src" / "sample.py"
        source.parent.mkdir()
        source.write_text("x = 1\n", encoding="utf-8")
        brain = root / ".project-brain"
        (brain / "tasks").mkdir(parents=True)
        (brain / "config.yaml").write_text("schema: 3\n", encoding="utf-8")
        task_file = brain / "tasks" / "PB-001.md"
        registry = root / "agents.json"
        registry.write_text(json.dumps({"models": {"codex/same-model": {
            "cli": "codex", "model_id": "same-model", "roles": ["worker", "reviewer"],
            "tiers": ["L", "M", "H"], "available": True, "quality": 65,
        }}}), encoding="utf-8")
        verify = command(sys.executable, "-c", "pass")
        spec = f"""# PB-001 — Verify runtime
Status: READY
Priority: P1
Tier: M
Risk: MEDIUM
Owner:
Areas: `src/**`
Domains: runtime

## Objective
Verify source and independent review.

## Steps
1. Check `src/sample.py`.

## Acceptance
- [x] [machine] source check passes

## Verify
- `{verify}`

## Evidence

## Review
"""
        task_file.write_text(spec, encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            assert B.cmd_start(root, "PB-001", "same-model", agents_path=registry) == 0
        assert V.check(B, root, "PB-001")[0] == 0
        assert V.review(B, root, "PB-001", "codex/same-model", "PASS", agents_path=registry)[0] == 2
        # A review produced by the former alias loophole must also fail at acceptance.
        task = B.find_task(root, "PB-001")
        grown = dict(task, risk="LOW", domains=["auth"], evidence_lines=[])
        assert V.effective_risk(B, grown) == "HIGH"
        value, _ = V.digest(B, root, task["areas"])
        B.append_section(task_file, "Review", f"- review by codex/same-model | PASS | digest={value} | contract={B.contract(task)}")
        assert V.accept(B, root, "PB-001", agents_path=registry)[0] == 2
        payload = json.loads(registry.read_text(encoding="utf-8"))
        payload["models"]["worker-only"] = {"model_id": "different-model", "roles": ["worker"], "quality": 65}
        registry.write_text(json.dumps(payload), encoding="utf-8")
        B.append_section(task_file, "Review", f"- review by worker-only | PASS | digest={value} | contract={B.contract(task)}")
        assert "reviewer policy" in "\n".join(V.accept(B, root, "PB-001", agents_path=registry)[1])
        source.write_text("x = 2\n", encoding="utf-8")
        assert any("current source" in line for line in V.accept(B, root, "PB-001", agents_path=registry)[1])
        task_file.write_text(task_file.read_text(encoding="utf-8") + "\n## External\n- operation | response_unknown\n", encoding="utf-8")
        assert "readback first" in "\n".join(V.check(B, root, "PB-001")[1])
        assert "external operation unresolved" in "\n".join(V.accept(B, root, "PB-001", agents_path=registry)[1])
        B.set_header(task_file, "Risk", "HIGH")
        (brain / "config.yaml").write_text('schema: 3\ncommands:\n  test: "python full_suite.py"\n', encoding="utf-8")
        assert "configured full test command" in "\n".join(V.accept(B, root, "PB-001", agents_path=registry)[1])
        # A full stdin pipe must never delay the command's deadline.
        started = time.monotonic()
        result = V.run_command(root, [sys.executable, "-c", "import time; time.sleep(5)"], root / "timeout.log", timeout=0.2, input_bytes=b"x" * 1048576)
        assert result["timed_out"] and result["exit_code"] == 124, result
        assert time.monotonic() - started < 4, result
        # Commands still receive the complete input when they do read it.
        result = V.run_command(root, [sys.executable, "-c", "import sys; assert len(sys.stdin.buffer.read()) == 1048576"], root / "input.log", input_bytes=b"x" * 1048576)
        assert result["exit_code"] == 0, result
        # Retention cleanup must refuse linked directories before deleting anything.
        external = root / "external"
        external.mkdir()
        victim = external / "old.log"
        victim.write_text("unrelated data", encoding="utf-8")
        os.utime(victim, (0, 0))
        runs = brain / ".cache" / "runs"
        for log in runs.glob("*.log"):
            log.unlink()
        runs.rmdir()
        if os.name == "nt":
            subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(runs), str(external)], check=True, capture_output=True)
        else:
            runs.symlink_to(external, target_is_directory=True)
        try:
            for operation in (
                lambda: V.prune_runs(B, root),
                lambda: P.session_file(root, runs / "agents.json"),
                lambda: A._archive_path(root / "project", {"id": "test"}, runs),
            ):
                try:
                    operation()
                except ValueError:
                    pass
                else:
                    raise AssertionError("linked directory was accepted")
            assert victim.read_text(encoding="utf-8") == "unrelated data"
        finally:
            if runs.is_symlink():
                runs.unlink()
            else:
                runs.rmdir()
    print("OK: verification identity, readback, quoting, stdin deadline and linked-log checks passed")


if __name__ == "__main__":
    main()
