"""Pool task modes, queue recovery and current-skill migration invariants."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import brain as B
import migrate as M
import runtime_agents as A
import runtime_agent_pool as AP
import runtime_verify as V
from test_routing import _project


def main():
    model = {"id": "worker", "routeId": "local", "enabled": True, "group": "low", "fixedEffort": "high", "efforts": ["high"], "billing": "subscription", "kinds": ["read", "write"]}
    completed = {"id": "job", "state": "succeeded", "report": {"status": "completed", "summary": "done", "files": [], "checks": [], "research": [], "blockers": []}}
    for case in ("response", "queue", "blocker", "missing-report", "legacy", "migration"):
        with tempfile.TemporaryDirectory(prefix="pb-pool-mode-") as directory:
            root = Path(directory) / "project"
            root.mkdir()
            registry = Path(directory) / "private" / "agents.json"
            calls = []
            reads = [0]
            def rpc(tool, arguments=None):
                calls.append((tool, arguments))
                if tool == "pool_get_policy":
                    return {"selectionMode": "manual", "taskModes": ["response", "execute"]}
                if tool == "pool_list_models":
                    return [model]
                if tool == "pool_select":
                    return {"selected": model}
                if tool == "pool_submit":
                    return {"id": "job"}
                if tool == "pool_get_task":
                    reads[0] += 1
                    if case == "queue" and reads[0] < 3:
                        return {"id": "job", "state": "queued"}
                    if case == "blocker":
                        return {"id": "job", "state": "queued", "queueReason": "WORKSPACE_REVIEW_REQUIRED", "blockedBy": "prior-job"}
                    if case == "missing-report":
                        return {"id": "job", "state": "succeeded", "result": "claimed completion"}
                    return dict(completed, result="response text")
                raise AssertionError(tool)
            with patch.object(A, "DEFAULT_REGISTRY", registry), patch.object(AP, "rpc", side_effect=rpc), contextlib.redirect_stdout(io.StringIO()) as output:
                _project(root)
                B.set_session_modes(root, "P-ALL", "P-ALL", new=True)
                args = argparse.Namespace(force=False, timeout=5, wait=30, mode="response" if case == "response" else None, cli="", model="", effort="", group="", dry_run=False)
                task = B.find_task(root, "PB-001")
                score = A.score_task(B, root, task)
                if case in ("legacy", "migration"):
                    actor = AP.remember(model)
                    B.cmd_start(root, task["id"], agent=actor)
                    task = B.find_task(root, task["id"])
                    legacy = {"contract": B.contract(task), "actor": actor, "strength": "low", "taskId": "job", "request": {"kind": "write", "prompt": "old immutable prompt", "idempotencyKey": "legacy-original-key"}}
                    journal = AP.journal_path(root, task["id"])
                    B.write_atomic(journal, json.dumps(legacy))
                    before = journal.read_bytes()
                    if case == "migration":
                        config = B.bp(root) / "config.yaml"
                        config.write_text(config.read_text().replace(B.VERSION, "3.5.1"), encoding="utf-8")
                        raw = config.read_bytes()
                        M.run(root, False)
                        assert config.read_bytes() == raw and journal.read_bytes() == before
                        M.run(root, True)
                        assert B.parse_config(root)["skill_version"] == B.VERSION
                        assert (B.bp(root) / "migration-backup/config.yaml").read_bytes() == raw
                        assert journal.read_bytes() == before
                        task = B.find_task(root, task["id"])
                        assert B.contract(task) == legacy["contract"]
                        again = config.read_bytes()
                        M.run(root, True)
                        assert config.read_bytes() == again
                with patch.object(V, "check", return_value=(0, ["PASS fixture"])) as check, patch.object(AP.time, "sleep"), patch.object(AP.time, "monotonic", side_effect=range(100)):
                    result = AP.delegate(B, root, task, score, args)
                    assert result == (2 if case in ("blocker", "missing-report") else 0), output.getvalue()
                    assert check.call_count == (0 if case in ("response", "blocker", "missing-report") else 1)
                saved = json.loads(AP.journal_path(root, task["id"]).read_text())
                if case in ("legacy", "migration"):
                    assert not [x for x in calls if x[0] == "pool_submit"]
                    assert saved["request"] == legacy["request"]
                    assert not any(x[1].get("compact") for x in calls if x[0] == "pool_get_task")
                    args.mode = "execute"
                    try:
                        AP.delegate(B, root, task, score, args)
                        raise AssertionError("legacy request silently changed mode")
                    except ValueError as exc:
                        assert "immutable" in str(exc)
                else:
                    assert saved["request"]["mode"] == ("response" if case == "response" else "execute")
                    assert saved["request"]["kind"] == ("read" if case == "response" else "write")
                    assert all(x[1].get("compact") for x in calls if x[0] == "pool_get_task")
                if case == "queue":
                    assert reads[0] == 3
                if case == "blocker":
                    assert "prior-job" in output.getvalue()
                if case == "response":
                    assert "RESPONSE_ONLY" in output.getvalue()

    # An ordinary failed task's string error is data, not an RPC error envelope.
    with tempfile.TemporaryDirectory(prefix="pb-task-error-") as directory:
        file = Path(directory) / "reply.py"
        file.write_text('import json\nprint(json.dumps({"id":"job","state":"needs_review","error":"TIMEOUT"}))\n', encoding="utf-8")
        with patch.dict(os.environ, {"PB_AGENT_POOL_COMMAND": json.dumps([sys.executable, str(file)])}):
            assert AP.rpc("pool_get_task", {"taskId": "job"})["error"] == "TIMEOUT"
    print("PASS: execute/response, compact reports, queue wait, blockers, immutable legacy readback and 3.5.1 migration")


if __name__ == "__main__":
    main()
