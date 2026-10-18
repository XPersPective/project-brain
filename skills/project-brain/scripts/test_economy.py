"""Offline routing, usage, quota and seeded malformed-input checks. Stdlib only."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import tempfile
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import runtime_agents as A
import runtime_pool as P
import brain as B


def denied(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return
    raise AssertionError("malformed input accepted: " + repr(args))


def main():
    with patch.object(A, "_run_probe", return_value=(0, 'log\n[{"id":"x","provider":"p","api_key":"hidden"}]', "")):
        assert A.probe_catalog(["tool", "models"]) == ([{"model_id": "x", "provider": "p"}], "ok")
    with patch.object(A, "_run_probe", return_value=(0, '{"models":[{"fullModel":"glm/glm-5.3-high","provider":"glm"}]}', "")):
        assert A.probe_catalog(["omniroute", "api", "models", "get-api-models", "--output", "json"]) == (
            [{"model_id": "glm/glm-5.3-high", "provider": "glm"}], "ok"
        )
    for output, status in (('[{"id":"x"}]\n... and 40 more', "partial"),
                           ('[{"id":"x"}] TRUNCATED', "partial"),
                           ('[{"id":true}]', "invalid"), ('{}', "invalid")):
        with patch.object(A, "_run_probe", return_value=(0, output, "")):
            assert A.probe_catalog(["tool"])[1] == status
    with patch.object(A, "_run_probe", return_value=(1, "server offline", "")):
        assert A.probe_catalog(["tool"]) == ([], "unavailable")
    denied(A.probe_catalog, [None])
    old_stamp = "2020-01-01T00:00:00Z"
    data = {"pools": {"p": {"quota_argv": ["tool"], "weekly_7d_remaining_pct": 5,
                             "remaining_pct": 5, "updated_at": old_stamp}}}
    with patch.object(A, "_run_probe", return_value=(0, json.dumps({"remaining_pct": 80,
                      "updated_at": datetime.now(timezone.utc).isoformat()}), "")):
        A._refresh_configured_quotas(data)
    assert data["pools"]["p"]["updated_at"] == old_stamp
    assert data["pools"]["p"]["quota_status"] == "invalid"
    # A successful but incomplete response must not erase a known low window.
    fresh_stamp = datetime.now(timezone.utc).isoformat()
    for window in ({"weekly_7d_remaining_pct": None}, {"quota_windows": []},
                   {"quota_windows": [{"name": "weekly", "remaining_pct": None}]},
                   {"quota_windows": [{"name": "short", "remaining_pct": 80}]}):
        old = {"remaining_pct": 5, "updated_at": old_stamp, "quota_argv": ["tool"]}
        if "quota_windows" in window:
            old["quota_windows"] = [{"name": "weekly", "remaining_pct": 5}]
        else:
            old["weekly_7d_remaining_pct"] = 5
        snapshot = dict(window, remaining_pct=80, updated_at=fresh_stamp)
        for codex in (False, True):
            data = {"pools": {"codex": copy.deepcopy(old)}, "cli_agents": {"codex": {"binary": "tool"}}}
            with patch.object(A, "load", return_value=data), patch.object(A, "save"), \
                    patch.object(A, "probe_codex_quota", return_value=snapshot if codex else None), \
                    patch.object(A, "_run_probe", return_value=(0, json.dumps(snapshot), "")):
                A.refresh_quota()
            assert data["pools"]["codex"]["quota_status"] == "invalid"
            assert P._quota(data, {"pool": "codex"}) == (5.0, False)
    pool = {"quota_windows": [{"name": "weekly", "remaining_pct": 5}]}
    A._update_quota(pool, {"remaining_pct": 80, "updated_at": fresh_stamp,
                          "quota_windows": [{"name": "weekly", "remaining_pct": 70}]})
    assert pool["quota_status"] == "fresh" and P._quota({"pools": {"p": pool}}, {"pool": "p"}) == (70.0, True)

    # One budget covers health checks, daemon launch, wait and polling.
    clock = [0.0]
    def elapse(seconds):
        clock[0] += seconds
    def unhealthy(timeout):
        elapse(timeout)
        return False
    def waiting(timeout):
        elapse(timeout)
        raise subprocess.TimeoutExpired("fake daemon", timeout)
    with patch.object(A.time, "monotonic", side_effect=lambda: clock[0]), \
            patch.object(A.time, "sleep", side_effect=elapse), \
            patch.object(A, "omniroute_server_up", side_effect=unhealthy), \
            patch.object(A.Path, "is_file", return_value=True), \
            patch.object(A.subprocess, "Popen", return_value=SimpleNamespace(wait=waiting)):
        assert not A.ensure_omniroute_server("fake.exe", timeout=3)
    assert clock[0] <= 3, clock
    registry = {"cli_agents": {"zcode": {"discovered_at": old_stamp, "available": True},
                               "gemini": {"discovered_at": old_stamp, "available": True}},
                "models": {"z": {"cli": "zcode", "available": True},
                           "g": {"cli": "gemini", "available": True}},
                "pools": {"gemini": {"remaining_pct": None}}}
    with patch.object(A, "load", return_value=registry), patch.object(A, "which_cli", return_value=None), \
            patch.object(A, "installed_ai_apps", return_value=[]):
        scanned = A.scan_agents(probe_quota=False, persist=False)
    assert scanned["models"]["z"]["available"] is False
    assert "gemini" not in scanned["cli_agents"] and "gemini" not in scanned["pools"] and "g" not in scanned["models"]
    registry = {"cli_agents": {"custom": {"catalog_argv": ["tool"]}}, "models": {}, "pools": {}}
    with patch.object(A, "load", return_value=registry), patch.object(A, "which_cli", return_value=None), \
            patch.object(A, "installed_ai_apps", return_value=[]):
        with patch.object(A, "probe_catalog", return_value=([{"model_id": "x", "provider": "p"}], "ok")):
            A.scan_agents(probe_quota=False, persist=False)
        with patch.object(A, "probe_catalog", return_value=([], "partial")):
            A.scan_agents(probe_quota=False, persist=False)
        assert registry["models"]["custom:x"]["catalog_missing"] is False
        with patch.object(A, "probe_catalog", return_value=([], "ok")):
            A.scan_agents(probe_quota=False, persist=False)
    assert registry["models"]["custom:x"]["catalog_missing"] is True
    denied(P._validate_selection, registry, {"models": {"custom:x": {
        "roles": ["worker"], "efforts": ["default"], "billing": "free", "max_jobs": 1}}})
    apps = A.classify_apps([{"DisplayName": "ZCode 3.15.3"}, {"DisplayName": "MiniMax Code"},
                           {"DisplayName": "Qwen"}, {"DisplayName": "Other editor"},
                           {"DisplayName": "ZCode 3.15.3"}])
    assert len(apps) == 3
    assert next(a for a in apps if a["cli"] == "zcode")["subscription_group"] == "Z.AI"
    # Initial 300-case loop produced by an actual OpenCode/big-pickle worker;
    # inspected here and extended to nested shapes, routing and provider readback.
    rng = random.Random(1831)
    keys = ("models", "pools", "cli_agents", "benchmarks")
    values = (None, [], 7, True, "bad")
    for _ in range(300):
        denied(A._validate_registry, {rng.choice(keys): rng.choice(values)})
    for bad_apps in (None, {}, 7, [None], ["bad"]):
        denied(A._validate_registry, {"installed_apps": bad_apps})
    for bad_win in ("bad", [None], [{"remaining_pct": True}], [{"remaining_pct": 105}]):
        denied(A._validate_registry, {"pools": {"p": {"quota_windows": bad_win}}})
    A._validate_registry({})
    quota = {"remaining_pct": 90, "updated_at": datetime.now(timezone.utc).isoformat(),
             "quota_windows": [{"name": "short", "remaining_pct": 80}, {"name": "weekly", "remaining_pct": 5}]}
    assert P._quota({"pools": {"p": quota}}, {"pool": "p"}) == (5.0, True)
    assert P._inventory({"pools": {"p": quota}, "models": {"m": {"pool": "p"}}})["models"]["m"]["remaining_pct"] == 5.0
    assert not A._pool_status({"pools": {"p": quota}}, {"pool": "p"}, "worker", "L")[0]
    denied(P._quota, {"pools": {"p": dict(quota, quota_windows=[{"remaining_pct": True}])}}, {"pool": "p"})
    for field in ("roles", "tiers", "efforts", "worker_argv", "quota_argv"):
        for value in ("worker", 7, True, [None], [[]], [{}]):
            denied(A._validate_registry, {"models": {"bad": {field: value}}})
    for field in ("cli", "model_id", "pool", "benchmark_key", "binary"):
        for value in ([], {}, 7, True):
            denied(A._validate_registry, {"models": {"bad": {field: value}}})
    for field in ("quality", "coding", "cost_weight", "remaining_pct", "reserve_pct",
                  "primary_5h_remaining_pct", "weekly_7d_remaining_pct"):
        for value in (float("nan"), float("inf"), -1, True, [], {}):
            denied(A._validate_registry, {"models": {"bad": {field: value}}})
    prompt = '{"name":"Türkçe 東京", "shell":"$() & | % !"}'
    argv, stdin = A._worker_command("custom", "tool.exe", ".", "m", "default", prompt,
                                    {"worker_argv": ["{binary}", "{prompt}"]})
    assert argv == ["tool.exe", prompt] and stdin is None
    argv, _ = A._worker_command("custom", "tool.exe", ".", "chosen", "default", "Keep {model} literal",
                                {"worker_argv": ["{binary}", "{prompt} / {model}"]})
    assert argv[1] == "Keep {model} literal / chosen"
    denied(A._worker_command, "omniroute", "omniroute", ".", "glm/glm-5.3-high", "medium", prompt)
    denied(A._worker_command, "qwen", "qwen", ".", "m", "high", prompt)
    denied(A._worker_command, "omniroute", "omniroute", ".", "m", "xhigh", prompt)
    denied(A._worker_command, "gemini", "gemini", ".", "m", "default", prompt)
    for template in (["x", "{unknown}"], ["x", "{"], ["x", ""], ["x", "\x00"]):
        denied(A._worker_command, "custom", "x", ".", "m", "default", prompt, {"worker_argv": template})

    base = {"available": True, "user_approved": True, "quality": 50,
            "roles": ["worker"], "efforts": ["default"], "cost_weight": 1}
    data = {"models": {"host": dict(base, cli="host"), "external": dict(base, cli="opencode"),
                       "weak": dict(base, quality=1, cost_weight=0),
                       "unknown": dict(base, quality=None, cost_weight=0)}, "pools": {}}
    assert [x["alias"] for x in A.candidates(data, tier="M", risk="MEDIUM")] == ["external", "host"]
    assert A.candidates(data, tier="L", risk="LOW")[0]["alias"] == "unknown"
    data["models"]["host"]["cost_weight"] = 0.5
    assert A.candidates(data, tier="M", risk="MEDIUM")[0]["alias"] == "host"
    data["models"]["router"] = dict(base, cli="omniroute", cost_weight=0)
    assert "router" not in [r["alias"] for r in A.candidates(data, tier="M", risk="MEDIUM")]
    data["cli_agents"] = {"omniroute": {"worker_argv": ["coding-agent", "{model}"], "prompt_stdin": True}}
    assert A.candidates(data, tier="M", risk="MEDIUM")[0]["alias"] == "router"
    assert A._worker_command("omniroute", "router", ".", "m", "default", prompt,
                             data["cli_agents"]["omniroute"]) == (["coding-agent", "m"], prompt)

    with tempfile.TemporaryDirectory(prefix="pb-economy-") as td:
        root = Path(td)
        log = root / "usage.log"
        event = {"type": "step_finish", "part": {"id": "one", "reason": "stop", "cost": 0,
                 "tokens": {"total": 20, "input": 3, "output": 2, "reasoning": 5,
                            "cache": {"read": 10, "write": 0}}}}
        log.write_text("header\n" + json.dumps(event) + "\n" + json.dumps(event), encoding="utf-8")
        usage = A.worker_usage(log, "opencode")
        assert usage["tokens"]["total"] == 20 and usage["steps"] == 1 and usage["complete"]
        P._validate_usage(usage)
        assert A.worker_usage(log, "other") is None
        for bad in (None, [], True, -1, float("nan")):
            broken = copy.deepcopy(event)
            broken["part"]["tokens"]["total"] = bad
            log.write_text(json.dumps(broken), encoding="utf-8")
            assert A.worker_usage(log, "opencode") is None
        event["part"]["reason"] = "tool-calls"
        log.write_text(json.dumps(event), encoding="utf-8")
        assert A.worker_usage(log, "opencode")["complete"] is False
        log.write_text("no counters\n", encoding="utf-8")
        assert A.worker_usage(log, "opencode") is None
        denied(P._validate_usage, dict(usage, reported_cost=True))

        registry = root / "agents.json"
        old = {"remaining_pct": 5, "updated_at": "2020-01-01T00:00:00Z", "quota_argv": ["metadata-tool", "quota"]}
        A.save({"pools": {"zai": old}, "cli_agents": {"custom": {"binary": "metadata-tool"}}}, registry)
        for result in ((1, "", "offline"), (0, "[]", ""), (0, '{"remaining_pct": 100}', "")):
            with patch.object(A, "_run_probe", return_value=result):
                refreshed = A.refresh_quota(registry)
            assert refreshed["pools"]["zai"]["remaining_pct"] == 5
        fresh = {"remaining_pct": 72, "updated_at": datetime.now(timezone.utc).isoformat(), "untrusted_extra": "discard"}
        with patch.object(A, "_run_probe", return_value=(0, json.dumps(fresh), "")):
            refreshed = A.refresh_quota(registry)
        assert refreshed["pools"]["zai"]["remaining_pct"] == 72
        assert refreshed["pools"]["zai"]["quota_status"] == "fresh"
        assert "untrusted_extra" not in refreshed["pools"]["zai"]

    # Session proposals must stay cheap: no CLI may be launched while proposing a pool.
    with tempfile.TemporaryDirectory(prefix="pb-propose-") as td:
        root = Path(td)
        reg = root / "agents.json"
        A.save({"models": {"host-worker": {"cli": "host", "model_id": "fake-native", "pool": "local",
                                           "roles": ["worker"], "efforts": ["low"]}},
                "pools": {"local": {}}, "cli_agents": {}}, reg)
        probes = []
        with patch.object(A, "_run_probe", side_effect=lambda *a, **k: probes.append(a) or (124, "", "blocked")):
            session = P.propose(B, root, reg, new=True)
            cached = P.propose(B, root, reg)
        assert session["status"] == "PROPOSED" and not probes
        assert "host-worker" in session["inventory"]["models"]
        assert cached["session_id"] == session["session_id"]
        snap = A.snapshot_agents(reg, persist=False)
        assert "host-worker" in snap["models"]
        assert all(entry.get("discovery_status") != "budget_exhausted" for entry in snap["cli_agents"].values())
    print("PASS: 300 seeded trials, 80 nested malformed cases, routing, adapters, usage and quota readback")


if __name__ == "__main__":
    main()
