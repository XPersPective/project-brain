"""Offline strict executor-policy, session freshness and selection regressions."""
import ast
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import brain as B
import runtime_executor_policy as E


def policy(source="native", **bounds):
    return {"schema": 1, "execution": dict(source=source, **bounds),
            "scheduling": {"mode": "serial", "max_parallel": 1},
            "quota_recovery": {"enabled": False, "threshold_percent": 10}}


def fails(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except (ValueError, OSError):
        return
    raise AssertionError("Expected refusal from " + fn.__name__)


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def checks(root):
    assert E.load(B, root) is None and E.selector(B, root) is None
    assert E.require_confirmed(B, root) is None
    assert E.guard(B, root, "exec", "direct", model={}) is None
    assert E.settings(B, root) == {} and E.summary(B, root)["policy"] is None
    assert snapshot(root) == {}
    fails(E.save, B, root, policy(), "explicit choices")
    assert snapshot(root) == {}
    brain = root / ".project-brain"
    brain.mkdir()
    (brain / "config.yaml").write_text("schema: 4\n", encoding="utf-8")
    path = brain / "executor-policy.json"
    for malformed in ("null", "[]", "{}", '{"schema":1,"schema":1}', "{bad", "NaN", " " * 65537):
        path.write_text(malformed, encoding="utf-8")
        fails(E.load, B, root)
        fails(E.require_confirmed, B, root)
        assert not E.confirmed(B, root)
    path.unlink()

    bad = []
    for key in ("schema", "execution", "scheduling", "quota_recovery"):
        value = policy()
        del value[key]
        bad.append(value)
    for schema in (True, 2, "1"):
        value = policy()
        value["schema"] = schema
        bad.append(value)
    for scheduling in ({"mode": "parallel"}, {"mode": "serial", "max_parallel": 2},
                       {"mode": "parallel", "max_parallel": 33}, {"mode": "parallel", "max_parallel": True}):
        value = policy()
        value["scheduling"] = scheduling
        bad.append(value)
    for recovery in ({"enabled": True}, {"enabled": 1, "threshold_percent": 10},
                     {"enabled": False, "threshold_percent": 0}, {"enabled": True, "threshold_percent": 51}):
        value = policy()
        value["quota_recovery"] = recovery
        bad.append(value)
    for constraints in ({"exclusions": ["x"]}, {"cost_limit": 1}, {"categories": ["x"]},
                        {"models": ["host/x"]}, {"effort": {"selector": "director", "value": "high"}},
                        {"effort": {"selector": "user"}},
                        {"effort": {"selector": "user", "value": "high", "allowed": ["low"]}}):
        bad.append(policy(**constraints))
    for value in bad:
        before = snapshot(root)
        fails(E.save, B, root, value, "explicit choices")
        assert snapshot(root) == before
    fails(E.save, B, root, policy(), "token=sk-" + "x" * 30)
    fails(E.save, B, root, policy("native-pinned", models=["host/sk-" + "x" * 30]), "choices")
    for pins in (["host/*"], ["host"], [{"host": "host", "model": "?"}], [{"model": "x"}], []):
        fails(E.save, B, root, policy("native-pinned", models=pins), "choices")
    for pins in (["route/model"], [{"routeId": "r", "modelId": "*"}], [{"modelId": "m"}]):
        fails(E.save, B, root, policy("cap-pinned", models=pins), "choices")
    for categories in ([], [""], ["a", "a"], "a", ["a" * 257]):
        fails(E.save, B, root, policy("cap-category", categories=categories), "choices")

    # Views expose saved intent without granting session confirmation or writing.
    normalized = E.save(B, root, policy(), "selected native serial; recovery disabled")
    assert normalized["review"] == normalized["execution"]
    before = snapshot(root)
    assert E.load(B, root) == normalized
    assert E.selector(B, root)["source"] == "native"
    assert E.settings(B, root)["exec"] == "self_mixed"
    assert not E.summary(B, root)["confirmed"]
    assert len(json.dumps(E.summary(B, root)).encode("utf-8")) < 2048
    fails(E.guard, B, root, "exec", "native")
    assert snapshot(root) == before

    # Confirm without boot; mutate even whitespace, host identity, or fresh nonce.
    jobs = brain / ".cache/jobs.json"
    jobs.parent.mkdir(exist_ok=True)
    jobs.write_text('{"active":["untouched"]}', encoding="utf-8")
    jobs_raw = jobs.read_bytes()
    with patch.dict(os.environ, {"PB_SESSION_ID": "first"}):
        E.confirm(B, root, "keep saved choices")
        assert E.confirmed(B, root)
        with patch.dict(os.environ, {"PB_SESSION_ID": "second"}):
            assert not E.confirmed(B, root)
            fails(E.require_confirmed, B, root)
        raw = path.read_bytes()
        path.write_bytes(raw + b" ")
        assert not E.confirmed(B, root)
        fails(E.require_confirmed, B, root)
        path.write_bytes(raw)
        assert E.confirmed(B, root)
        old = E.confirm(B, root, "keep")
        marker = E.begin_session(B, root)
        assert marker["nonce"] != old["nonce"] and "confirmation" not in marker
        assert path.read_bytes() == raw and jobs.read_bytes() == jobs_raw
        assert not E.confirmed(B, root)
        fails(E.require_confirmed, B, root)
        E.confirm(B, root, "keep again")
        value = json.loads(path.read_text(encoding="utf-8"))
        value["quota_recovery"]["enabled"] = True
        path.write_text(json.dumps(value), encoding="utf-8")
        assert not E.confirmed(B, root)
    path.unlink()
    fails(E.require_confirmed, B, root)  # Removing policy cannot recover legacy authority.

    examples = {
        "solo": ({}, "native", {}, "solo"),
        "native": ({}, "native", {"host": "h", "model": "m"}, "self_mixed"),
        "native-cheap": ({}, "native", {"host": "h", "model": "m"}, "self_mixed"),
        "native-pinned": ({"models": ["h/m"]}, "native", {"host": "h", "model": "m"}, "self_mixed"),
        "cap-category": ({"categories": ["arbitrary:category"]}, "pool", {"categories": ["arbitrary:category"]}, "pool_mixed"),
        "cap-catalog": ({}, "pool", {"routeId": "r", "modelId": "m"}, "pool_mixed"),
        "cap-pinned": ({"models": [{"routeId": "r", "modelId": "m"}]}, "pool", {"routeId": "r", "modelId": "m"}, "pool_mixed")}
    for source, (bounds, backend, model, legacy) in examples.items():
        value = policy(source, **bounds)
        value["scheduling"] = {"mode": "parallel", "max_parallel": 32}
        E.save(B, root, value, "explicit choices")
        E.confirm(B, root, "confirmed")
        assert E.settings(B, root) == {"exec": legacy, "rev": legacy, "schedule": "parallel", "max_parallel": 32}
        assert E.guard(B, root, "exec", "main")["source"] == source
        fails(E.guard, B, root, "exec", "direct", model=model)
        fails(E.guard, B, root, "exec", "pool" if backend == "native" else "native", model=model)
        if source == "solo":
            fails(E.guard, B, root, "exec", backend, model=model)
            continue
        assert E.guard(B, root, "exec", backend)["source"] == source
        assert E.guard(B, root, "exec", backend, model=model, cheaper=True)["source"] == source
        for unavailable in ({"hidden": True}, {"enabled": False}, {"disabled": True}, {"removed": True}, {"enabled": "true"}):
            candidate = dict(model, **unavailable)
            fails(E.guard, B, root, "exec", backend, model=candidate, cheaper=True)
        if source == "native-cheap":
            for observation in (None, False, 1, "true"):
                fails(E.guard, B, root, "exec", backend, model=model, cheaper=observation)
        if source in ("native-pinned", "cap-pinned"):
            fails(E.guard, B, root, "exec", backend, model={})
            for key in model:
                other = dict(model)
                other[key] = "different"
                fails(E.guard, B, root, "exec", backend, model=other)
        if source == "cap-category":
            fails(E.guard, B, root, "exec", backend, category="unapproved")
            fails(E.guard, B, root, "exec", backend, model={})
            fails(E.guard, B, root, "exec", backend, model={"categories": ["unapproved"]})
            fails(E.guard, B, root, "exec", backend, model={"categories": ["unapproved"]}, category="arbitrary:category")
            fails(E.guard, B, root, "exec", backend, model={}, category="arbitrary:category")

    # Execution and review differ; requested or observed effort cannot escape.
    value = policy("native-pinned", models=[{"host": "h", "model": "m"}],
                   effort={"selector": "user", "value": "medium", "allowed": ["low", "medium"]})
    value["review"] = {"source": "cap-catalog", "effort": {"selector": "director", "allowed": ["high"]}}
    E.save(B, root, value, "different reviewer bounds")
    E.confirm(B, root, "confirmed")
    assert E.selector(B, root, "reviewer")["source"] == "cap-catalog"
    assert E.guard(B, root, "exec", "native", effort="medium")
    fails(E.guard, B, root, "exec", "native", effort="low")
    fails(E.guard, B, root, "exec", "native", model={"host": "h", "model": "m"})
    fails(E.guard, B, root, "exec", "native", model={"host": "h", "model": "m", "effort": "high"}, effort="medium")
    assert E.guard(B, root, "exec", "native", model={"host": "h", "model": "m", "effort": "medium"})
    assert E.guard(B, root, "review", "pool", model={"effort": "high"})
    fails(E.guard, B, root, "review", "pool", model={"effort": "medium"})
    fails(E.guard, B, root, "review", "pool", model={})
    fails(E.selector, B, root, "typo")
    E.save(B, root, policy("cap-catalog", effort={"selector": "default"}), "provider default")
    E.confirm(B, root, "confirmed default effort")
    fails(E.guard, B, root, "exec", "pool", effort="high")
    fails(E.guard, B, root, "exec", "pool", model={"effort": "high", "defaultEffort": "low"})
    assert E.guard(B, root, "exec", "pool", model={"effort": "low", "defaultEffort": "low"})


def linked_paths(root):
    # Windows junctions require no symlink privilege; POSIX uses symlinks.
    real = root / "outside"
    real.mkdir()
    project = root / "linked"
    project.mkdir()
    linked = project / ".project-brain"
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(linked), str(real)], capture_output=True)
        assert result.returncode == 0, result.stderr
    else:
        linked.symlink_to(real, target_is_directory=True)
    try:
        fails(E.load, B, project)
        fails(E.require_confirmed, B, project)
    finally:
        if os.name == "nt":
            linked.rmdir()
        else:
            linked.unlink()


def main():
    with tempfile.TemporaryDirectory(prefix="pb-executor-policy-") as directory:
        root = Path(directory)
        project = root / "project"
        project.mkdir()
        checks(project)
        linked_paths(root)
    for name in ("runtime_executor_policy.py", "test_executor_policy.py"):
        ast.parse(Path(__file__).with_name(name).read_text(encoding="utf-8"), feature_version=(3, 8))
    print("PASS: strict executor policy, seven sources, exact bounds, session freshness and legacy compatibility")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
