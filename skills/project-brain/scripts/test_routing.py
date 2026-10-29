"""Offline checks for approved model routing and worker launch boundaries."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import brain as B
import runtime_agents as A
import runtime_pool as P


def _project(root, legacy=True):
    with contextlib.redirect_stdout(io.StringIO()):
        B.cmd_init(root)
    if legacy:
        cfg = B.parse_config(root)
        cfg["protocol_version"] = "0"  # This fixture exercises legacy routing compatibility.
        B.write_atomic(B.bp(root) / "config.yaml", B.config_text(root, cfg))
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "a.py").write_text("pass\n", encoding="utf-8")
    task = root / ".project-brain" / "tasks" / "PB-001.md"
    task.write_text(
        "# PB-001 — Routing smoke check\nStatus: READY\nPriority: P2\nTier: L\nRisk: LOW\n"
        "Owner:\nDepends: -\nAreas: `src/**`\nDomains: core\n\n"
        "## Objective\nRun one local worker.\n\n## Steps\n1. Read the source.\n\n"
        "## Acceptance\n- [ ] [machine] Worker completed.\n\n"
        "## Verify\n- `python -c \"assert True\"`\n",
        encoding="utf-8",
    )


def _registry(path, cli="dummy", worker_argv=None):
    data = {
        "models": {"worker": {
            "cli": cli, "model_id": "default", "pool": "local", "available": True,
            "roles": ["worker"], "tiers": ["L", "M", "H"], "efforts": ["default"],
            "quality": None,
        }, "excluded": {
            "cli": cli, "model_id": "unused", "pool": "local", "available": True,
            "roles": ["worker"], "tiers": ["L", "M", "H"], "efforts": ["default"],
            "quality": 100,
        }},
        "pools": {"local": {"plan_type": "local", "remaining_pct": None}},
        "cli_agents": {},
    }
    if cli != "host":
        data["cli_agents"][cli] = {
            "binary": sys.executable,
            "generic_worker_argv": worker_argv or ["{binary}", "-c", "import os, sys; from pathlib import Path; Path('worker-ran').write_text(sys.stdin.read() + os.environ.get('PB_SESSION_ID', ''))"],
            "prompt_stdin": True,
        }
    A.save(data, path)
    return data


def _approve(root, registry, selection):
    proposed = P.propose(B, root, registry)
    return P.approve(B, root, selection, proposed["session_id"], registry,
                     confirmed=True, note="User selected this test route.")


def main():
    assert {name for name, _, _ in A.CLI_SPECS} >= {"hermes", "lmstudio", "ollama"}
    data = {"models": {
        "picked": {"user_approved": True, "roles": ["worker"], "tiers": ["L"],
                   "efforts": ["low"], "quality": None, "available": True},
        "excluded": {"user_approved": True, "roles": ["worker"], "tiers": ["L"],
                     "efforts": ["low"], "quality": 100, "available": True},
        "wrong-role": {"user_approved": True, "roles": ["reviewer"], "tiers": ["L"],
                       "efforts": ["low"], "available": True},
    }, "pools": {}}
    # Candidate selection honors the explicit roles and lets the selected unrated route through.
    rows = A.candidates(data, role="worker", tier="L", risk="LOW")
    assert [row["alias"] for row in rows] == ["excluded", "picked"]
    assert next(row for row in rows if row["alias"] == "picked")["quality"] is None
    assert all(row["alias"] != "wrong-role" for row in rows)
    assert A._effort_for({"efforts": ["default"]}, "M", "LOW") == "default"
    argv, _ = A._worker_command("codex", "codex", ".", "default", "default", "prompt")
    assert "-m" not in argv and "model_reasoning_effort" not in " ".join(argv)
    argv, stdin_text = A._worker_command("mcode", "mcode", ".", "default", "default", "prompt")
    assert argv[1:] == ["exec", "--input", "-", "--cwd", str(Path(".").resolve()),
                        "--prompt-mode", "coding", "--permission", "full", "--mode", "lightweight"]
    assert stdin_text == "prompt"
    argv, _ = A._worker_command("mcode", "mcode", ".", "MiniMax-M2.5", "high", "prompt")
    assert argv[-2:] == ["--effort", "high"]
    try:
        A._worker_command("mcode", "mcode", ".", "MiniMax-M3", "low", "prompt")
    except ValueError as exc:
        assert "does not support" in str(exc)
    else:
        raise AssertionError("M3 must reject unsupported effort before a reservation can be made")
    try:
        A._worker_command("custom", "custom", ".", "m", "low", "p", {"worker_argv": ["x", "{oops}"]})
    except ValueError as exc:
        assert "placeholder" in str(exc)
    else:
        raise AssertionError("unknown argv placeholders must fail before job reservation")
    try:
        A._check_batch_args([r"C:\tools\worker.bat", "safe", "line1\nline2"])
    except ValueError:
        pass
    else:
        raise AssertionError("batch wrappers must reject multiline arguments")

    with tempfile.TemporaryDirectory(prefix="pb-cli-metadata-") as folder:
        registry = Path(folder) / "agents.json"
        _registry(registry)
        data = A.load(registry)
        data["models"]["worker"]["model_id"] = "custom-model-id"
        data["cli_agents"]["tester"] = {"binary": "custom-agent", "adapter": "kept",
                                          "generic_worker_argv": ["{binary}", "--stdin"],
                                          "prompt_stdin": True}
        A.save(data, registry)
        with patch.object(A, "CLI_SPECS", (("tester", ("tester",), "Test CLI"),)), \
             patch.object(A, "which_cli", return_value="detected-agent"), \
             patch.object(A, "_run_probe", return_value=(0, "test-version", "")):
            scanned = A.scan_agents(registry, probe_quota=False, persist=False)
        assert scanned["cli_agents"]["tester"]["binary"] == "custom-agent"
        assert scanned["cli_agents"]["tester"]["adapter"] == "kept"
        assert scanned["models"]["worker"]["model_id"] == "custom-model-id"

    with tempfile.TemporaryDirectory(prefix="pb-routing-") as folder:
        root = Path(folder) / "no-approval"
        root.mkdir()
        _project(root)
        registry = root.parent / "agents.json"
        _registry(registry)
        with patch.object(B, "cmd_start", side_effect=AssertionError("unapproved route must not start")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                rc = A.delegate_task(B, root, "PB-001", model_override="worker", reg_path=registry)
        assert rc == 2 and "approved pool session" in output.getvalue()
        assert not (root / "worker-ran").exists()
        preview_data = A.load(registry)
        preview_data["models"]["worker"]["quality"] = 50
        A.save(preview_data, registry)
        with contextlib.redirect_stdout(io.StringIO()) as preview:
            rc = A.delegate_task(B, root, "PB-001", model_override="worker", dry_run=True, reg_path=registry)
        assert rc == 0 and "PREVIEW ONLY" in preview.getvalue(), (rc, preview.getvalue())
        assert not (root / "worker-ran").exists()

    with tempfile.TemporaryDirectory(prefix="pb-host-routing-") as folder:
        root = Path(folder)
        _project(root)
        registry = root / "agents.json"
        _registry(registry, cli="host")
        session = _approve(root, registry, {"models": {"worker": {
            "roles": ["worker"], "efforts": ["default"], "billing": "local", "max_jobs": 1,
        }}, "exclude": ["excluded"]})
        with patch.object(B, "cmd_start", return_value=0), patch.object(A.V, "check", side_effect=AssertionError("host handoff is not a check")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                rc = A.delegate_task(B, root, "PB-001", model_override="worker", reg_path=registry)
        assert rc == 0 and "HOST_ACTION_PENDING" in output.getvalue()
        action = json.loads(output.getvalue().split("HOST_ACTION_PENDING ", 1)[1])
        assert action["alias"] == "worker" and action["job_id"]
        assert action["session_id"] == session["session_id"]
        assert action["root"] == str(root.resolve()) and action["registry"] == str(registry.resolve())
        assert action["environment"] == {"PB_SESSION_ID": session["session_id"]}
        pending = P.load_session(root, registry)
        assert pending["jobs"][action["job_id"]]["state"] == "reserved"
        try:
            P.authorize(B, root, A.load(registry), "worker", "default", registry)
        except ValueError as exc:
            assert "unsettled" in str(exc)
        else:
            raise AssertionError("a pending host action must block another dispatch")
        P.settle(B, root, action["job_id"], "failed", "Host handoff was not launched.", registry)
        try:
            P.authorize(B, root, A.load(registry), "worker", "default", registry)
        except ValueError as exc:
            assert "cap" in str(exc)
        else:
            raise AssertionError("settlement must preserve the consumed job cap")

    with tempfile.TemporaryDirectory(prefix="pb-run-routing-") as folder:
        root = Path(folder)
        _project(root)
        registry = root / "agents.json"
        _registry(registry)
        _approve(root, registry, {"models": {"worker": {
            "roles": ["worker"], "efforts": ["default"], "billing": "local", "max_jobs": 1,
        }}, "exclude": ["excluded"]})
        approved, _ = P.approved_data(B, root, A.load(registry), registry)
        assert set(approved["models"]) == {"worker"}
        assert A.candidates(approved, role="worker", tier="L", risk="LOW")[0]["quality"] is None
        try:
            P.authorize(B, root, A.load(registry), "worker", "high", registry)
        except ValueError as exc:
            assert "effort" in str(exc)
        else:
            raise AssertionError("unapproved efforts must be rejected exactly")
        with patch.object(B, "cmd_start", side_effect=AssertionError("excluded alias must not start")):
            with contextlib.redirect_stdout(io.StringIO()):
                rc = A.delegate_task(B, root, "PB-001", model_override="excluded", reg_path=registry)
        assert rc == 2
        data = A.load(registry)
        data["pools"]["local"].update(remaining_pct=80, updated_at="2020-01-01T00:00:00Z")
        A.save(data, registry)  # Quota-only change does not revoke the approved route.
        # Stale quota is admitted by the user-approved per-session cap; reserve remains authoritative.
        with patch.object(A.V, "check", return_value=(0, ["CHECK_OK"])):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                rc = A.delegate_task(B, root, "PB-001", model_override="worker", reg_path=registry)
        assert rc == 0 and "WORKER_DONE" in output.getvalue() and "CHECK_OK" in output.getvalue()
        assert (root / "worker-ran").exists()
        assert P.load_session(root, registry)["session_id"] in (root / "worker-ran").read_text(encoding="utf-8")
        worker_prompt = (root / "worker-ran").read_text(encoding="utf-8")
        assert "human Git identity" in worker_prompt and "Co-authored-by" in worker_prompt  # no AI credit rule
        session = P.load_session(root, registry)
        job = next(iter(session["jobs"].values()))
        assert job["state"] == "completed" and job["exit_code"] == 0
        try:
            P.authorize(B, root, A.load(registry), "worker", "default", registry)
        except ValueError as exc:
            assert "cap" in str(exc)
        else:
            raise AssertionError("completed attempts still consume the approved session cap")

    print("OK: approved routing, adapters, host handoff and contained worker completion")


if __name__ == "__main__":
    main()
