"""Focused offline checks for routing, delegation boundaries and planning adoption."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

import brain as B
import runtime_agents as A
import runtime_pool as P


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        result = fn(*args, **kwargs)
    return result, out.getvalue()


def main():
    # An installed CLI that never answers must not hang the quota probe.
    popen = subprocess.Popen
    with patch.object(A.subprocess, "Popen", side_effect=lambda *a, **kw: popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], **kw
    )):
        started = time.monotonic()
        assert A.probe_codex_quota("offline-fake", timeout=0.1) is None
        assert time.monotonic() - started < 4

    for area, key in (("ui/**", "ui"), ("pages/**", "ui"), ("*.tsx", "ui"),
                      ("backend/**", "backend"), ("*.sql", "backend")):
        assert A.task_surface({"areas": [area]})[key], area
    assert not A.task_surface({"areas": ["build/views_cache/**"]})["ui"]

    with tempfile.TemporaryDirectory(prefix="pb-agent-audit-") as folder:
        root = Path(folder)
        registry = root / "agents.json"
        data = {"models": {
            "worker": {"cli": "claude", "model_id": "gpt-5.2-codex", "pool": "local",
                       "roles": ["worker", "reviewer"], "tiers": ["L", "M", "H"],
                       "available": True, "cost_weight": 1, "efforts": ["low", "medium", "high"]},
            "alternate": {"model_id": "openai/gpt-5.2-codex", "available": False},
        }, "pools": {"local": {"remaining_pct": 20}}}
        A.save(data, registry)
        # Invalid imports must not replace a working registry or lose its model pool.
        original_registry = registry.read_bytes()
        patch_file = root / "patch.json"
        for invalid in ([], {"models": []}, {"pools": None}, {"cli_agents": {"bad": []}},
                        {"benchmarks": {"models": []}}, {"models": {"bad": None}},
                        {"schema_version": True}, {"schema_version": 2}):
            patch_file.write_text(json.dumps(invalid), encoding="utf-8")
            try:
                quiet(A.run_agents, B, SimpleNamespace(registry=registry, agents_cmd="merge", file=patch_file))
            except ValueError:
                pass
            else:
                raise AssertionError("malformed registry merge accepted")
            assert registry.read_bytes() == original_registry
            malformed = root / "malformed.json"
            malformed.write_text(json.dumps(invalid), encoding="utf-8")
            try:
                A.load(malformed)
            except ValueError:
                pass
            else:
                raise AssertionError("malformed registry loaded")
        loaded = A.load(registry)
        assert not A.candidates(loaded, tier="L", risk="LOW")  # Director reserve cannot be fallback.
        loaded["pools"]["local"]["remaining_pct"] = 80
        assert A.candidates(loaded, tier="L", risk="LOW")
        for invalid in (float("nan"), float("inf"), -1, 101, True):
            loaded["pools"]["local"]["remaining_pct"] = invalid
            assert not A.candidates(loaded, tier="L", risk="LOW")
        loaded["pools"]["local"]["remaining_pct"] = 80
        assert A.canonical_identity("worker", registry) == A.canonical_identity("alternate", registry)
        assert A.canonical_identity("worker", registry) == A.canonical_identity("codex/gpt-5.2-codex", registry)
        loaded["models"]["unmeasured"] = {"quality": None, "roles": ["worker"]}
        assert all(c["alias"] != "unmeasured" for c in A.candidates(loaded, tier="L", risk="LOW"))

        quiet(B.cmd_init, root)
        cfg = B.parse_config(root)
        cfg["protocol_version"] = "0"
        B.write_atomic(B.bp(root) / "config.yaml", B.config_text(root, cfg))
        (root / "src").mkdir()
        (root / "src/a.py").write_text("pass\n", encoding="utf-8")
        task_file = root / ".project-brain/tasks/PB-001.md"
        task_text = (
            "# PB-001 — Small maintenance\nStatus: READY\nPriority: P2\nTier: L\nRisk: LOW\n"
            "Owner:\nDepends: -\nAreas: `src/**`\nDomains: core\n\n"
            "## Objective\nAdjust a constant.\n\n## Steps\n1. Edit `src/a.py`.\n\n"
            "## Acceptance\n- [ ] [machine] Constant verified.\n\n"
            "## Verify\n- `python -c \"assert True\"`\n"
        )
        task_file.write_text(task_text, encoding="utf-8")
        loaded["models"].update({
            "strong": {"model_id": "custom-strong", "quality": 65, "roles": ["worker"]},
            "weak-reviewer": {"model_id": "custom-weak", "quality": 60, "roles": ["reviewer"], "tiers": ["H"]},
            "high-reviewer": {"model_id": "custom-high", "quality": 70, "roles": ["reviewer"], "tiers": ["H"]},
        })
        A.save(loaded, registry)
        reviewing = B.parse_task(task_file)
        reviewing["owner"] = "strong"
        try:
            A.gate(B, reviewing, "weak-reviewer", "review", registry)
        except ValueError as exc:
            assert "weaker than implementer" in str(exc), exc
        else:
            raise AssertionError("Explicit model quality cannot bypass relative reviewer floor")
        A.gate(B, reviewing, "high-reviewer", "review", registry)  # H reviewer may review L tasks.
        for status in ("PLANNED", "BLOCKED", "REVIEW", "DONE"):
            task_file.write_text(task_text.replace("Status: READY", "Status: " + status), encoding="utf-8")
            rc, text = quiet(A.delegate_task, B, root, "PB-001", model_override="worker", dry_run=True, reg_path=registry)
            assert rc == 2 and "requires READY" in text, (status, text)
        task_file.write_text(task_text, encoding="utf-8")
        rc, text = quiet(A.delegate_task, B, root, "PB-001", model_override="unknown", dry_run=True, reg_path=registry)
        assert rc == 2 and "eligible registered" in text, text
        rc, text = quiet(A.delegate_task, B, root, "PB-001", model_override="worker", dry_run=True, reg_path=registry)
        assert rc == 0 and "DELEGATE_PLAN" in text, text
        # Explicit role approval alone does not allow unbounded unknown/stale quota.
        proposal = P.propose(B, root, registry)
        P.approve(B, root, {"models": {"worker": {"roles": ["worker"], "efforts": ["low", "medium", "high"],
                                                "billing": "subscription"}}}, proposal["session_id"], registry,
                  confirmed=True, note="User chose this temporary test worker, without an unknown-quota allowance")
        with patch.object(B, "cmd_start", side_effect=AssertionError("must not start")):
            for pool in ({}, {"remaining_pct": 80, "updated_at": "2020-01-01T00:00:00Z"}):
                loaded["pools"]["local"] = pool
                A.save(loaded, registry)
                rc, text = quiet(A.delegate_task, B, root, "PB-001", model_override="worker", reg_path=registry)
                assert rc == 2 and "unknown or stale" in text, text
        task_file.write_text(task_text.replace("Owner:", "Owner: somebody"), encoding="utf-8")
        loaded["pools"]["local"] = {"remaining_pct": 80}
        A.save(loaded, registry)
        rc, text = quiet(A.delegate_task, B, root, "PB-001", model_override="worker", dry_run=True, reg_path=registry)
        assert rc == 2 and "owned by somebody" in text, text
        task_file.write_text(task_text, encoding="utf-8")
        loaded["pools"]["local"] = {"plan_type": "local"}
        loaded["cli_agents"] = {"claude": {"binary": sys.executable}}
        A.save(loaded, registry)
        proposal = P.propose(B, root, registry, new=True)
        P.approve(B, root, {"models": {"worker": {"roles": ["worker"], "efforts": ["low", "medium", "high"],
                                                "billing": "local", "max_jobs": 2}}},
                  proposal["session_id"], registry, confirmed=True, note="User permits two harmless local test workers")
        child = (
            "import sys\n"
            f"sys.path.insert(0, {str(Path(A.__file__).parent)!r})\n"
            "from pathlib import Path\nimport brain as B\nimport runtime_agents as A\n"
            "A._worker_command=lambda *a: ([sys.executable, '-c', "
            "\"import pathlib,time; p=pathlib.Path('worker-started'); p.open('a').write('started\\\\n'); time.sleep(1)\"], None)\n"
            "A.V.check=lambda *a, **kw: (0, ['offline check'])\n"
            "try:\n"
            "    rc=A.delegate_task(B, Path(sys.argv[1]), 'PB-001', model_override='worker', reg_path=Path(sys.argv[2]))\n"
            "except ValueError as exc:\n"
            "    print(exc); rc=2\n"
            "raise SystemExit(rc)\n"
        )
        args = [sys.executable, "-B", "-c", child, str(root), str(registry)]
        first = subprocess.Popen(args, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            deadline = time.monotonic() + 5
            while not (root / "worker-started").exists() and time.monotonic() < deadline:
                if first.poll() is not None:
                    break
                time.sleep(0.02)
            assert (root / "worker-started").exists(), first.communicate(timeout=2)[0]
            second = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=5)
            assert second.returncode == 2 and "delegate.lock" in second.stdout, second.stdout + second.stderr
            output = first.communicate(timeout=5)[0]
            assert first.returncode == 0, output
            assert (root / "worker-started").read_text().count("started") == 1
        finally:
            if first.poll() is None:
                first.kill()
                first.wait()

    with tempfile.TemporaryDirectory(prefix="pb-adopt-audit-") as folder:
        root = Path(folder)
        tasks = root / ".planning/tasks"
        tasks.mkdir(parents=True)
        original = "# SA-001 — Offline repository\nStatus: READY\n\n## Steps\n1. Preserve custom DB semantics.\n"
        (tasks / "SA-001.md").write_text(original, encoding="utf-8")
        (tasks / "SA-002.md").write_text("# SA-002 — Publish Android package\n", encoding="utf-8")
        (tasks / "SA-003.md").write_text("# SA-003 — Completed work\nStatus: DONE\n", encoding="utf-8")
        (root / "TODO.md").write_text("- [ ] Deploy website\n- [ ] Add cache\n- [ ] Add cache\n", encoding="utf-8")
        tm = root / ".taskmaster/tasks/tasks.json"
        tm.parent.mkdir(parents=True)
        tm.write_text(json.dumps({"master": {"tasks": [
            {"id": 1, "title": "Submit package", "description": "Publish marketplace listing"},
            {"id": 2, "title": "Cache invalidation", "description": "Preserve dependency metadata", "dependencies": [4]},
        ]}}), encoding="utf-8")
        extracted = A._extract_foreign_tasks(root)
        assert len(extracted) == 4, extracted  # Duplicate checklist items deduplicated on apply.
        rc, text = quiet(A.cmd_legacy, B, root, apply=True)
        assert rc == 0 and "created 3" in text, text
        imported = B.list_tasks(root)
        assert len(imported) == 3
        assert all(t["status"] == "PLANNED" for t in imported)
        sources = list((root / ".project-brain/migration-backup/imported").glob("*"))
        assert len(sources) == 3
        assert original in [p.read_text(encoding="utf-8") for p in sources]
        assert any('"dependencies": [' in p.read_text(encoding="utf-8") for p in sources)
        rc, text = quiet(A.cmd_legacy, B, root, apply=True)
        assert rc == 0 and "created 0" in text, text

    # Import interrupted after scaffold creation resumes without losing the original spec.
    with tempfile.TemporaryDirectory(prefix="pb-import-retry-") as folder:
        root = Path(folder)
        old = root / ".planning/tasks/SA-001.md"
        old.parent.mkdir(parents=True)
        original = "# SA-001 — Shared title\nStatus: READY\n\n## Objective\nFirst source intent.\n"
        old.write_text(original, encoding="utf-8")
        create = B.cmd_new
        def interrupt(*args, **kwargs):
            create(*args, **kwargs)
            raise OSError("crash after task scaffold")
        with patch.object(B, "cmd_new", side_effect=interrupt):
            try:
                quiet(A.cmd_legacy, B, root, apply=True)
            except OSError:
                pass
            else:
                raise AssertionError("scaffold interruption was not injected")
        quiet(A.cmd_legacy, B, root, apply=True)
        tasks = B.list_tasks(root)
        assert len(tasks) == 1 and "preserved original" in tasks[0]["objective"]
        assert original in [p.read_text(encoding="utf-8") for p in (root / ".project-brain/migration-backup/imported").glob("*")]
        old.with_name("SA-002.md").write_text(original.replace("First source intent", "Different source intent"), encoding="utf-8")
        quiet(A.cmd_legacy, B, root, apply=True)
        assert len(B.list_tasks(root)) == 2, "matching titles must not discard different source intent"
    print("OK: agent routing, bounded probe, delegation guards, lossless scoped adoption")


if __name__ == "__main__":
    main()
