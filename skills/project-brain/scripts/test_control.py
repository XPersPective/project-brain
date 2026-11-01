"""Policy CLI and director-wait integration regressions, no provider calls."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

import brain as B
import runtime_agent_pool as P
import runtime_agents as A
import runtime_control as C
import runtime_executor_policy as E
import runtime_quota_recovery as Q
from test_routing import _project


def main():
    with tempfile.TemporaryDirectory(prefix="pb-control-") as directory:
        root = Path(directory)
        with contextlib.redirect_stdout(io.StringIO()):
            _project(root)
        policy = {"schema": 1, "execution": {"source": "cap-catalog"},
                  "scheduling": {"mode": "serial", "max_parallel": 1},
                  "quota_recovery": {"enabled": True, "threshold_percent": 10}}
        source = B.bp(root) / ".cache/choice.json"
        source.parent.mkdir(exist_ok=True)
        source.write_text(json.dumps(policy), encoding="utf-8")
        with patch.object(__import__("sys"), "argv", ["brain.py", "policy", str(root), "--file",
                ".project-brain/.cache/choice.json", "--confirm", "--note", "User choices"]), \
                contextlib.redirect_stdout(io.StringIO()):
            assert B.main() == 0
        assert E.confirmed(B, root)
        B.set_session_modes(root, "solo", "solo", schedule="parallel", max_parallel=20)
        assert B.get_session_modes(root)["exec"] == "pool_mixed"
        assert B.get_session_modes(root)["schedule"] == "serial"
        observation = {"accountId": "test-account", "ordinaryUsageAllowed": True,
                       "rateLimits": {"limitId": "director", "primary": {
                           "usedPercent": 95, "resetsAt": time.time()+3600, "windowDurationMins": 300}}}
        checkpoint = B.bp(root) / "evidence/PB-001/handoff.json"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text('{"task":"PB-001","resume":"Continue actual task"}', encoding="utf-8")
        prepared = Q.prepare(B, root, observation, E.load(B, root), checkpoint.relative_to(root).as_posix())
        assert prepared["host_action"] == "CREATE_AUTOMATION"
        args = argparse.Namespace(force=False, timeout=5, wait=1, mode="response", cli="", model="",
                                  effort="", group="", dry_run=False)
        task = B.find_task(root, "PB-001")
        with patch.object(P, "select_policy", side_effect=AssertionError("dispatch during quota wait")), \
                patch.object(A, "DEFAULT_REGISTRY", root/"private-registry.json"):
            try:
                P.delegate(B, root, task, A.score_task(B, root, task), args)
                raise AssertionError("response discovery escaped quota wait")
            except ValueError as exc:
                assert "QRP_WAIT" in str(exc)
        # Cancelling an alarm does not approve a pending/new ESP/SP session.
        E.begin_session(B, root)
        cancel_args = argparse.Namespace(cmd="quota", root=str(root), action="cancel", note="User cancelled")
        result = C.command(B, cancel_args)
        assert result["status"] == "CANCELLED"
        assert not E.load(B, root)["quota_recovery"]["enabled"]
        assert not E.confirmed(B, root)
        assert Q.check_resume(B, root, observation, E.load(B, root), prepared["nonce"])["status"] == "CANCELLED"
        # Confirmed policy cancellation preserves already confirmed ESP/SP only.
        E.confirm(B, root, "User confirmed unchanged ESP/SP and disabled QRP")
        C.command(B, cancel_args)
        assert E.confirmed(B, root)
    print("PASS: policy CLI, authoritative bounds, response quota wait and cancellation confirmation isolation")


if __name__ == "__main__":
    main()
