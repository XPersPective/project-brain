"""Offline contract checks for the separate CLI Agent Pool backend."""
import argparse
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
import runtime_agents as A
import runtime_agent_pool as AP
import runtime_verify as V
from test_routing import _project


def main():
    model = {"id": "versioned-sol-9.1", "routeId": "test", "enabled": True,
             "group": "low", "fixedEffort": "high", "efforts": ["low", "medium", "high"],
             "billing": "subscription", "suggestedGroup": "medium", "kinds": ["write"]}
    calls = []

    def rpc(tool, arguments=None):
        calls.append((tool, arguments))
        if tool == "pool_select":
            return {"selected": dict(model), "alternatives": []}
        if tool == "pool_get_policy":
            return {"selectionMode": "manual", "taskModes": ["response", "execute"]}
        if tool == "pool_list_models":
            return [dict(model)]
        if tool == "pool_submit":
            return {"id": "task-123"}
        if tool == "pool_get_task":
            return {"id": "task-123", "state": "succeeded", "result": "checked", "report": {"status": "completed", "summary": "Checked", "files": [], "checks": [], "research": [], "blockers": []}, "effort": "high"}
        raise AssertionError(tool)

    with tempfile.TemporaryDirectory(prefix="pb-agent-pool-") as directory:
        root = Path(directory)
        registry = root / "external" / "agents.json"
        with patch.object(A, "DEFAULT_REGISTRY", registry), patch.object(AP, "rpc", side_effect=rpc), contextlib.redirect_stdout(io.StringIO()):
            selected = AP.select("L")
            assert selected["request"]["group"] == "low"
            assert selected["request"]["effort"] == "high"  # Owner effort beats task heuristic.
            assert selected["request"]["minRemainingPercent"] == 10
            assert AP.select("H", "reviewer")["request"]["minRemainingPercent"] == 25
            _project(root)
            B.set_session_modes(root, "P-ALL", "P-ALL", new=True)
            task = B.find_task(root, "PB-001")
            args = argparse.Namespace(force=False, timeout=5, cli="", model="", effort="", group="", dry_run=True)
            score = A.score_task(B, root, task)
            assert AP.delegate(B, root, task, score, args) == 0
            assert not AP.journal_path(root, task["id"]).exists()
            args.dry_run = False
            with patch.object(V, "check", return_value=(0, ["PASS"])) as check:
                assert AP.delegate(B, root, task, score, args) == 0
                entry = json.loads(AP.journal_path(root, task["id"]).read_text(encoding="utf-8"))
                assert entry["taskId"] == "task-123" and entry["request"]["effort"] == "high"
                assert entry["strength"] == "low"
                task = B.find_task(root, "PB-001")
                assert AP.delegate(B, root, task, score, args) == 0
                assert len([x for x in calls if x[0] == "pool_submit"]) == 1
                assert check.call_count == 2
                # A lost submit acknowledgement reuses the exact saved request/key.
                entry.pop("taskId")
                B.write_atomic(AP.journal_path(root, task["id"]), json.dumps(entry))
                assert AP.delegate(B, root, task, score, args) == 0
                submissions = [x[1] for x in calls if x[0] == "pool_submit"]
                assert submissions[0] == submissions[1]
                # Failed writes never start another job, even after another invocation.
                def failed(tool, arguments=None):
                    return {"id": "task-123", "state": "needs_review", "error": "TIMEOUT"} if tool == "pool_get_task" else rpc(tool, arguments)
                with patch.object(AP, "rpc", side_effect=failed):
                    assert AP.delegate(B, root, task, score, args) == 2
                assert len([x for x in calls if x[0] == "pool_submit"]) == 2
            args.dry_run = True
            high_score = dict(score, effective_tier="H")
            args.force = True
            other = dict(task, id="PB-002")
            assert AP.delegate(B, root, other, high_score, args) == 0
            assert [x[1] for x in calls if x[0] == "pool_select"][-1]["minRemainingPercent"] == 25
            args.force, args.dry_run = False, False
            with patch.dict(os.environ, {"CLI_AGENT_POOL_WORKER": "1"}):
                try:
                    AP.delegate(B, root, task, score, args)
                    raise AssertionError("recursive worker admitted")
                except ValueError as exc:
                    assert "recursively" in str(exc)
            B.set_session_modes(root, "P-ALL", "P-L")  # Review caps never weaken model floors.
            model["enabled"] = False
            try:
                AP.gate(B, task, A.load()["models"][AP.alias(model)], AP.alias(model), "start")
                raise AssertionError("disabled model admitted")
            except ValueError:
                pass
            model["enabled"] = True
            try:
                AP.gate(B, task, A.load()["models"][AP.alias(model)], AP.alias(model), "review")
                raise AssertionError("self-review admitted")
            except ValueError as exc:
                assert "different" in str(exc)
            # Review reads immutable dispatch strength, not the model's latest selection.
            entry["taskId"], entry["strength"] = "task-123", "high"
            B.write_atomic(AP.journal_path(root, task["id"]), json.dumps(entry))
            reviewer = dict(model, id="reviewer-9.1", group="medium")
            def review_rpc(tool, arguments=None):
                return [model, reviewer] if tool == "pool_list_models" else rpc(tool, arguments)
            with patch.object(AP, "rpc", side_effect=review_rpc):
                AP.remember(reviewer)
                AP.remember(model)  # Later discovery must not reduce historical strength.
                # Ordinary PB start/check work has source-bound strength, no delegate journal.
                AP.journal_path(root, task["id"]).unlink()
                AP.gate(B, task, A.load()["models"][AP.alias(reviewer)], AP.alias(reviewer), "review", root)
                B.write_atomic(AP.journal_path(root, task["id"]), json.dumps(entry))
                try:
                    AP.gate(B, task, A.load()["models"][AP.alias(reviewer)], AP.alias(reviewer), "review", root)
                    raise AssertionError("weaker reviewer admitted")
                except ValueError as exc:
                    assert "below" in str(exc)
            registry_data = A.load()
            registry_data["models"]["direct-reviewer"] = {"model_id": "direct-9.1", "quality": 100, "roles": ["reviewer"], "tiers": ["H"]}
            A.save(registry_data)
            try:
                A.gate(B, task, "direct-reviewer", "review", root=root)
                raise AssertionError("mixed backend bypassed Pool strength")
            except ValueError as exc:
                assert "mixed-backend" in str(exc)
            try:
                A.gate(B, task, "direct-reviewer", "review", path=root / "missing-registry.json", root=root)
                raise AssertionError("missing registry bypassed Pool strength")
            except ValueError as exc:
                assert "registry" in str(exc)
            task["objective"] += "changed"
            try:
                AP.delegate(B, root, task, score, args)
                raise AssertionError("changed contract admitted")
            except ValueError:
                pass

    def missing(tool, arguments=None):
        if tool == "pool_select":
            raise ValueError("Pool NO_ROUTE: empty")
        if tool == "pool_get_policy":
            return {"selectionMode": "manual", "taskModes": ["response", "execute"]}
        raise AssertionError("manual selection must never inspect an outside model")
    with patch.object(AP, "rpc", side_effect=missing):
        try:
            AP.select("L")
            raise AssertionError("empty strict pool admitted")
        except ValueError as exc:
            assert "NO_ROUTE" in str(exc)

    # Real stdin/argv transport, not shell interpolation; JSON errors stay actionable.
    with tempfile.TemporaryDirectory(prefix="pb-pool-rpc-") as directory:
        script = Path(directory) / "fake.py"
        script.write_text("import json,sys\nr=json.load(sys.stdin)\nprint(json.dumps(r))\n", encoding="utf-8")
        with patch.dict(os.environ, {"PB_AGENT_POOL_COMMAND": json.dumps([sys.executable, str(script)])}):
            assert AP.rpc("pool_select", {"prompt": "Türkçe & $(literal) 🎤"})["arguments"]["prompt"] == "Türkçe & $(literal) 🎤"
        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("rpc", 45)), patch.object(AP, "command", return_value=[sys.executable]):
            try:
                AP.rpc("pool_submit")
                raise AssertionError("RPC timeout ignored")
            except ValueError as exc:
                assert "read back" in str(exc)
    print("PASS: Pool routing, fixed effort, reserves, journal recovery, no replay, review and shell-free RPC")


if __name__ == "__main__":
    main()
