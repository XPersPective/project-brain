"""Offline contract checks for explicit model-pool approval and job accounting."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from unittest.mock import patch

import brain as B
import runtime_agents as A
import runtime_pool as P


def denied(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def main():
    with tempfile.TemporaryDirectory(prefix="pb-pool-") as td:
        base = Path(td)
        root, reg = base / "one", base / "agents.json"
        root.mkdir()
        try:
            linked_registry = base / "linked"
            linked_registry.symlink_to(base, target_is_directory=True)
        except (OSError, NotImplementedError):
            pass
        else:
            denied(P.session_file, root, linked_registry / "agents.json")
        models = {
            "unrated": {"model_id": "dummy-a", "cli": "host", "pool": "p",
                        "roles": [], "efforts": ["low", "medium"], "available": False},
            "other": {"model_id": "dummy-b", "cli": "fake", "pool": "p", "roles": ["worker"],
                      "efforts": ["low"], "available": True},
        }
        data = {"models": models, "cli_agents": {"host": {"binary": "native-host"}},
                "pools": {"p": {"remaining_pct": None}}}
        A.save(data, reg)
        session = P.propose(B, root, reg)
        assert session["status"] == "PROPOSED" and set(session["inventory"]["models"]) == set(models)
        denied(P.authorize, B, root, A.load(reg), "unrated", "low", reg)
        denied(P._validate_selection, A.load(reg), {"models": {1: {}}})
        denied(P._validate_selection, A.load(reg), {"models": {"unrated": {"roles": [[]], "efforts": ["low"], "billing": "local"}}})
        api_route = A.load(reg)
        api_route["models"]["unrated"]["billing"] = "api"
        denied(P._validate_selection, api_route, {"models": {"unrated": {"roles": ["worker"], "efforts": ["low"], "billing": "free", "max_jobs": 1}}})
        denied(P.approve, B, root, {"models": {"unrated": {"roles": ["worker"], "efforts": ["low"], "billing": "local", "max_jobs": 2}}}, session["session_id"], reg)
        choice = {"models": {"unrated": {"roles": ["worker", "discovery"], "efforts": ["low", "default"],
                                             "billing": "local", "max_jobs": 2}}, "exclude": ["other"]}
        approved = P.approve(B, root, choice, session["session_id"], reg, confirmed=True, note="Choose local host route")
        filtered, _ = P.approved_data(B, root, A.load(reg), reg)
        assert set(filtered["models"]) == {"unrated"} and filtered["models"]["unrated"]["user_approved"]
        assert filtered["models"]["unrated"]["roles"] == ["discovery", "worker"]
        denied(P.authorize, B, root, A.load(reg), "unrated", "medium", reg)
        assert P.authorize(B, root, A.load(reg), "unrated", "default", reg, "discovery")["cli"] == "host"
        missing_cli = A.load(reg)
        missing_cli["cli_agents"]["host"]["discovery_status"] = "not_found"
        denied(P.authorize, B, root, missing_cli, "unrated", "default", reg, "discovery")
        with patch.dict("os.environ", {"PB_SESSION_ID": "different-session"}):
            denied(P.approved_data, B, root, A.load(reg), reg)
        changed = A.load(reg)
        changed["cli_agents"]["host"]["generic_worker_argv"] = ["run", "{prompt}"]
        changed["pools"]["p"].update(remaining_pct=71, updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        A.save(changed, reg)
        assert "REAPPROVAL_REQUIRED" in P.summary(B, root, reg)[0]
        A.save(data, reg)

        # Configuration changes revoke approval, while live quota changes do not.
        fresh = A.load(reg)
        fresh["pools"]["p"]["remaining_pct"] = 70
        fresh["pools"]["p"]["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        P.approved_data(B, root, fresh, reg)
        fresh["cli_agents"]["host"]["worker_argv"] = ["invoke", "--model", "{model}"]
        denied(P.approved_data, B, root, fresh, reg)
        del fresh["cli_agents"]["host"]["worker_argv"]
        fresh["models"]["unrated"]["model_id"] = "changed-model"
        denied(P.approved_data, B, root, fresh, reg)

        # Unknown quota needs a cap; a known fresh quota obeys both reserve floors.
        no_cap = {"models": {"unrated": {"roles": ["worker"], "efforts": ["low"], "billing": "local"}}}
        proposal = P.propose(B, root, reg, new=True)
        P.approve(B, root, no_cap, proposal["session_id"], reg, confirmed=True, note="No cap route")
        denied(P.authorize, B, root, A.load(reg), "unrated", "low", reg)
        capped = P.propose(B, root, reg, new=True)
        P.approve(B, root, choice, capped["session_id"], reg, confirmed=True, note="Bounded route")
        d = A.load(reg)
        changed_dispatch = A.load(reg)
        changed_dispatch["models"]["unrated"]["adapter"] = {"mode": "changed-after-command-build"}
        denied(P.reserve, B, root, changed_dispatch, "unrated", "low", reg,
               expected_session_id=capped["session_id"])
        for invalid in (float("nan"), True):
            d["pools"]["p"].update(remaining_pct=invalid, updated_at=datetime.now(timezone.utc).isoformat())
            denied(P.authorize, B, root, d, "unrated", "low", reg)
        d["pools"]["p"].update(remaining_pct=25, updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        denied(P.authorize, B, root, d, "unrated", "low", reg)
        d["pools"]["p"]["remaining_pct"] = 10
        denied(P.authorize, B, root, d, "unrated", "low", reg)
        d["pools"]["p"].update(remaining_pct=5, updated_at="2020-01-01T00:00:00Z")
        denied(P.authorize, B, root, d, "unrated", "low", reg)  # explicit cap cannot override known-low stale quota
        d["pools"]["p"].update(remaining_pct=20, updated_at="2020-01-01T00:00:00Z")
        denied(P.authorize, B, root, d, "unrated", "low", reg)
        assert P._quota({"pools": {"p": {"remaining_pct": 60, "updated_at": "2026-10-18T10:00:00"}}}, models["unrated"])[1] is False

        # A reservation survives a crash and blocks all aliases until readback.
        d["pools"]["p"]["remaining_pct"] = None
        jid = P.reserve(B, root, d, "unrated", "low", reg, expected_session_id=capped["session_id"])
        denied(P.authorize, B, root, d, "unrated", "low", reg)
        denied(P.propose, B, root, reg, new=True)
        denied(P.propose, B, root, reg, refresh=True)
        P.finish(B, root, jid, None, reg)
        denied(P.reserve, B, root, d, "unrated", "low", reg)
        P.settle(B, root, jid, "completed", "confirmed response", reg)
        jid2 = P.reserve(B, root, d, "unrated", "low", reg)
        P.finish(B, root, jid2, 0, reg)
        denied(P.reserve, B, root, d, "unrated", "low", reg)

        revoked_session = P.propose(B, root, reg, new=True)
        P.approve(B, root, choice, revoked_session["session_id"], reg, confirmed=True, note="Second bounded route")
        jid3 = P.reserve(B, root, d, "unrated", "low", reg)
        P.finish(B, root, jid3, None, reg)
        P.revoke(B, root, reg)
        denied(P.propose, B, root, reg, new=True)
        P.settle(B, root, jid3, "failed", "confirmed no response", reg)

        # A new project gets a separate session; a new session resets approval.
        second = base / "two"
        second.mkdir()
        assert not P.load_session(second, reg)
        replacement = P.propose(B, root, reg, new=True)
        assert replacement["session_id"] != approved["session_id"]
        assert replacement["status"] == "PROPOSED"
        denied(P.reserve, B, root, d, "unrated", "low", reg,
               expected_session_id=capped["session_id"])

        # Failed atomic writes are retriable and do not corrupt the prior session.
        original = B.write_atomic
        calls = [0]
        def fail_once(path, content):
            calls[0] += 1
            if calls[0] == 1:
                raise OSError("simulated write failure")
            return original(path, content)
        with patch.object(B, "write_atomic", side_effect=fail_once):
            try:
                P.propose(B, root, reg, new=True)
            except OSError:
                pass
            else:
                raise AssertionError("simulated atomic write failure was swallowed")
            retry = P.propose(B, root, reg, new=True)
        assert retry["status"] == "PROPOSED"
        # Summary is cached metadata only; it never starts a discovery scan.
        with patch.object(A, "scan_agents", side_effect=AssertionError("unexpected probe")):
            lines = P.summary(B, root, reg)
            assert "PROPOSED" in lines[0]
            assert any("quota_now=unknown" in line for line in lines)
        many = {"models": {f"dummy-{i}": {"model_id": f"model-{i}", "cli": f"cli-{i % 20}"} for i in range(30)},
                "cli_agents": {f"cli-{i}": {"binary": f"tool-{i}"} for i in range(20)}, "pools": {}}
        large_reg = base / "large.json"
        A.save(many, large_reg)
        large_session = P.propose(B, second, large_reg)
        large_lines = P.summary(B, second, large_reg)
        assert sum(line.startswith("  dummy-") for line in large_lines) <= 12
        assert sum(line.startswith("  CLI ") for line in large_lines) <= 16
        assert any("30 models" in line and "by CLI" in line for line in large_lines)
        assert "APPROVAL_REQUIRED" not in large_lines[0] and large_session["status"] == "PROPOSED"
        assert P.summary(B, base / "three", large_reg)[0].startswith("MODEL_POOL: APPROVAL_REQUIRED")
        print("PASS pool approval, quota, isolation, recovery and cached summary")


if __name__ == "__main__":
    main()
