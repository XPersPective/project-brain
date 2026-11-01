"""Confirmed policy admission and native identity binding, without provider calls."""
import ast
from contextlib import contextmanager
import json
from pathlib import Path
from unittest.mock import patch

import brain as B
import runtime_agent_pool as P
import runtime_context as C
import runtime_executor_policy as E
import runtime_orchestration as O
from test_executor_policy import policy
from test_orchestration import denied, report
from test_orchestration_production import fixture


@contextmanager
def integrated_session():
    """Exercise the parent's settings/confirmation overlay before it is integrated."""
    original_get, original_require, original_packet = B.get_session_modes, B.require_session, C.packet

    def get(root):
        value = original_get(root)
        value.update(E.settings(B, root))
        # Mirror the parent's price/quality correction while the isolated policy
        # module retains the first delivered revision.
        for role, key in (("exec", "exec"), ("review", "rev")):
            selected = E.selector(B, root, role)
            if selected and selected["source"] == "native-cheap":
                value[key] = "self_mixed"
        return value

    def require(root, implementation=False):
        E.require_confirmed(B, root)
        return original_require(root, implementation=implementation)

    def packet(brain, root, value, kind="EXECUTE"):
        E.require_confirmed(brain, root)
        return original_packet(brain, root, value, kind)

    with patch.object(B, "get_session_modes", get), patch.object(B, "require_session", require), \
            patch.object(C, "packet", packet):
        yield


def choices(root, source="native-pinned", scheduling=None, **bounds):
    if source == "native-pinned" and "models" not in bounds:
        bounds["models"] = ["fixture-host/pinned-model"]
    value = policy(source, **bounds)
    value["scheduling"] = scheduling or {"mode": "parallel", "max_parallel": 3}
    E.save(B, root, value, "Explicit test executor, scheduling and recovery choices")
    E.confirm(B, root, "Keep saved choices for this test session")
    return value


def native_receipt(db, row, **extra):
    value = {"request_key": row["spec"]["idempotencyKey"], "host": "fixture-host", "model": "pinned-model",
             "tier": row["spec"]["tier"], "job_id": "job-" + row["id"], "state": "RUNNING"}
    value.update(extra)
    return O.native_receipt(db, row["id"], value)


def main():
    with integrated_session(), fixture() as (root, directory, db):
        choices(root)
        candidate = {"host": "fixture-host", "model": "pinned-model"}
        denied(lambda: O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native"), "candidate required")
        denied(lambda: O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native",
                                 candidate=dict(candidate, model="other")), "exact pins")
        assert not db.all()
        first = O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native", candidate=candidate)
        candidate["model"] = "mutated-caller-object"
        assert first["spec"]["native_candidate"]["model"] == "pinned-model"
        second = O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native",
                           candidate=first["spec"]["native_candidate"])
        launch = O.submit(B, root, db, directory, first["id"])
        assert launch["host_action"] == "launch_once"
        assert launch["candidate"] == first["spec"]["native_candidate"]
        assert launch["policy_bounds"]["models"] == [{"host": "fixture-host", "model": "pinned-model"}]
        denied(lambda: native_receipt(db, first, model="other"), "immutable native candidate")
        native_receipt(db, first)
        choices(root, scheduling={"mode": "serial", "max_parallel": 1})
        denied(lambda: O.submit(B, root, db, directory, second["id"]), "CAPACITY")
        assert db.policy() == {"schedule": "serial", "cap": 1}
        choices(root, "solo")
        # A policy change never suppresses readback or invalidates an already launched identity.
        assert O.observe(B, root, db, directory, first["id"])["state"] == "RUNNING"
        assert O.submit(B, root, db, directory, first["id"])["state"] == "RUNNING"
        native_receipt(db, first, state="SUCCEEDED", report=report())
        denied(lambda: O.submit(B, root, db, directory, second["id"]), "outside saved executor source")
        assert db.get(second["id"])["state"] == "PREPARED"
        choices(root, models=["fixture-host/replacement-model"])
        denied(lambda: O.submit(B, root, db, directory, second["id"]), "exact pins")
        assert db.get(second["id"])["state"] == "PREPARED"

    with integrated_session(), fixture() as (root, directory, db):
        candidate = {"host": "fixture-host", "model": "pinned-model", "effort": "high", "cheaper": True}
        choices(root, "native-cheap", effort={"selector": "user", "value": "high"})
        denied(lambda: O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native",
                                 candidate=dict(candidate, cheaper=False)), "cheaper-model observation")
        denied(lambda: O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native",
                                 candidate=dict(candidate, model="unknown")), "exact known")
        denied(lambda: O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native",
                                 candidate=dict(candidate, effort="low")), "saved user choice")
        high = O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native", tiers=["H"], candidate=candidate)
        assert high["spec"]["tier"] == "H"  # Cheapest does not mean a lower quality floor.
        O.submit(B, root, db, directory, high["id"])
        denied(lambda: native_receipt(db, high, effort="low", cheaper=True), "immutable native candidate")
        denied(lambda: native_receipt(db, high, effort="high", cheaper=1), "immutable native candidate")
        native_receipt(db, high, effort="high", cheaper=True)

    with integrated_session(), fixture() as (root, directory, db):
        choices(root)
        candidate = {"host": "fixture-host", "model": "pinned-model"}
        run = O.prepare(B, root, db, directory, "PB-001", "EXECUTE", "native", candidate=candidate)
        O.submit(B, root, db, directory, run["id"])
        (O.workspace(run, directory) / "src/a.py").write_text("accepted = True\n", encoding="utf-8")
        actor = native_receipt(db, run, state="SUCCEEDED", report=report())["actor"]
        qualifications = B.bp(root) / ".cache/model-qualifications.json"
        qualifications.write_bytes(b'{"schema":1,"assessments":[]}\r\n')
        checked = O.verify(B, root, db, directory, run["id"], actor)
        assert checked["exit"] == 0, checked
        child = Path(checked["candidate"])
        assert E.load(B, child) == E.load(B, root) and E.confirmed(B, child)
        original = (B.bp(root) / "executor-policy.json").read_bytes()
        assert (B.bp(child) / "executor-policy.json").read_bytes() == original
        assert (B.bp(child) / ".cache/model-qualifications.json").read_bytes() == qualifications.read_bytes()
        qualifications.write_bytes(b" " * 65537)
        denied(lambda: O.inherit_session(B, root, child, db, B.get_session_modes(root)), "64 KiB")
        qualifications.write_bytes(b'{"schema":1,"assessments":[]}\r\n')
        E.begin_session(B, root)
        denied(lambda: O.inherit_session(B, root, child, db, B.get_session_modes(root)), "EXECUTOR_POLICY_PENDING")
        E.confirm(B, root, "Keep choices")
        foreign = root.parent / "foreign"
        foreign.mkdir()
        O.git(foreign, "init")
        denied(lambda: O.inherit_session(B, root, foreign, db, B.get_session_modes(root)), "same-repository origin")

    with integrated_session(), fixture() as (root, directory, db):
        choices(root, "cap-catalog")
        row = O.prepare(B, root, db, directory, "PB-001", "REVIEW", "pool")
        selected = {"selected": {"routeId": "r", "modelId": "m"},
                    "request": {"routeId": "r", "modelId": "m"}}
        def rpc(name, request):
            if name == "pool_submit":
                return {"id": "pool-job"}
            assert name == "pool_get_task"
            return {"state": "running"}
        with patch.object(P, "select_policy", create=True, return_value=selected) as selection, \
                patch.object(P, "select", side_effect=AssertionError("Unbounded Pool selection")), \
                patch.object(P, "remember", return_value="pool/model"), patch.object(P, "rpc", side_effect=rpc):
            O.submit(B, root, db, directory, row["id"])
        assert selection.call_args.args[:3] == (B, root, row["spec"]["tier"])
        assert selection.call_args.kwargs == {"role": "reviewer"}
    for name in ("runtime_orchestration.py", "test_policy_orchestration.py"):
        ast.parse(Path(__file__).with_name(name).read_text(encoding="utf-8"), feature_version=(3, 8))
    print("PASS: policy orchestration admission, immutable native candidates, serial drain and internal inheritance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
