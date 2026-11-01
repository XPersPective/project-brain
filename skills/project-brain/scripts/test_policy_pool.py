"""Offline checks for ESP bounded CAP selection and qualification."""
import contextlib
import io
from pathlib import Path
import tempfile
from unittest.mock import patch

import brain as B
import runtime_agent_pool as AP
import runtime_executor_policy as E
from test_routing import _project


def save_policy(B, root, source, **extra):
    execution = dict({"source": source}, **extra)
    value = {"schema": 1, "execution": execution,
             "review": dict(execution),
             "scheduling": {"mode": "serial", "max_parallel": 1},
             "quota_recovery": {"enabled": False, "threshold_percent": 10}}
    E.save(B, root, value, "bounded test policy")
    E.begin_session(B, root)
    E.confirm(B, root, "confirmed test policy")


def main():
    with tempfile.TemporaryDirectory(prefix="pb-policy-pool-") as directory:
        root = Path(directory)
        _project(root, legacy=False)
        save_policy(B, root, "cap-catalog")
        rows = [
            {"routeId": "free", "modelId": "model-a", "enabled": True, "kinds": ["write"],
             "effort": "medium", "efforts": ["low", "medium", "high"], "billing": "free"},
            {"routeId": "paid", "modelId": "model-b", "enabled": True, "kinds": ["write"],
             "effort": "high", "efforts": ["high"], "billing": "subscription"},
            {"routeId": "hidden", "modelId": "model-c", "enabled": True, "hidden": True,
             "kinds": ["write"], "efforts": ["medium"]},
        ]
        calls = []
        def catalog_rpc(tool, args=None):
            calls.append((tool, args))
            if tool == "pool_catalog":
                return {"models": rows, "nextOffset": None}
            raise AssertionError(tool)
        with patch.object(AP, "rpc", side_effect=catalog_rpc):
            for row, tier, note in [(rows[0], "L", "fits low tier"), (rows[1], "H", "fits high tier")]:
                AP.qualify(B, root, row["routeId"], row["modelId"], tier, note)
            selected = AP.select_policy(B, root, "L", mode="execute")
            assert selected["selected"]["id"] == "model-a"
            assert "group" not in selected["request"]  # Category is not a quality strength.
            assert all(args["kind"] == "write" for tool, args in calls if tool == "pool_catalog")
            try:
                AP.select_policy(B, root, "M", model="model-a", mode="execute")
                raise AssertionError("low-qualified model passed medium floor")
            except ValueError as exc:
                assert "qualification" in str(exc).lower()
            high = AP.select_policy(B, root, "H", mode="execute")
            assert high["selected"]["id"] == "model-b"
            assert high["strength"] == "high"

        save_policy(B, root, "cap-pinned", models=[{"routeId": "free", "modelId": "model-a"}],
                    effort={"selector": "user", "value": "medium", "allowed": ["medium"]})
        def pin_rpc(tool, args=None):
            if tool == "pool_catalog":
                assert args["routeId"] == "free" and args["query"] == "model-a"
                return {"models": [dict(rows[0], categories=[])], "nextOffset": None}
            raise AssertionError(tool)
        with patch.object(AP, "rpc", side_effect=pin_rpc):
            pinned = AP.select_policy(B, root, "L", mode="execute")
            assert pinned["request"]["routeId"] == "free" and "group" not in pinned["request"]
            assert pinned["request"]["effort"] == "medium"
            task = B.find_task(root, "PB-001")
            task["owner"] = pinned["alias"]
            try:
                AP.gate(B, task, {"pool_route": "free", "model_id": "model-a",
                                  "pool_effort": "medium"}, pinned["alias"], "review", root)
                raise AssertionError("same-model reviewer admitted")
            except ValueError as exc:
                assert "different" in str(exc)
            try:
                AP.select_policy(B, root, "L", effort="low", mode="execute")
                raise AssertionError("effort outside policy accepted")
            except ValueError as exc:
                assert "Effort" in str(exc)

        save_policy(B, root, "cap-category", categories=["experimental"])
        category_row = dict(rows[0], categories=["experimental"])
        def category_rpc(tool, args=None):
            if tool == "pool_list_pools":
                assert args["group"] == "experimental"
                return {"models": [category_row], "nextOffset": None}
            raise AssertionError(tool)
        with patch.object(AP, "rpc", side_effect=category_rpc):
            selected = AP.select_policy(B, root, "L", mode="execute")
            assert selected["request"]["group"] == "experimental"

        E.load  # malformed registry must fail closed on lookup
        path = AP._qualification_path(B, root)
        path.write_text("{bad", encoding="utf-8")
        try:
            AP.model_qualification(B, root, "free", "model-a")
            raise AssertionError("malformed qualification registry accepted")
        except ValueError:
            pass
    print("PASS: ESP CAP selection, exact pins, effort/category bounds, qualification floors and inactive filtering")


if __name__ == "__main__":
    main()
