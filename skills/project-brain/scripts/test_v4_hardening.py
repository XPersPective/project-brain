"""Project Brain 4.0 hardening, acyclicity, security, UX and orchestration regression suite."""
import ast
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import brain as B
import migrate as M
import runtime_agent_pool as AP
import runtime_context as C
import runtime_core as Core
import runtime_executor_policy as E
import runtime_orchestration as O
import runtime_protocol as R
import runtime_quota_recovery as QR
import runtime_relay as RL
import runtime_runs as L
import runtime_security as S
import runtime_session as RS
import runtime_setup as SU
import runtime_verify as V
from test_helpers import make_project, run_cli, scrub_environ


def check_architecture_invariants():
    scripts_dir = Path(__file__).resolve().parent
    all_py = sorted(scripts_dir.glob("*.py"))
    runtime_files = [p for p in all_py if not p.name.startswith("test_")]
    internal = {p.stem for p in runtime_files}
    graph = {}
    for p in all_py:
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(p), feature_version=(3, 8))
        if p.name.startswith("test_"):
            continue
        top_nodes = set(tree.body)
        top_deps = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in internal:
                        if node not in top_nodes:
                            raise AssertionError(f"Non-top-level internal import in {p.name}: {alias.name}")
                        top_deps.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module in internal:
                if node not in top_nodes:
                    raise AssertionError(f"Non-top-level internal import in {p.name}: {node.module}")
                top_deps.add(node.module)
        graph[p.stem] = top_deps
    assert graph["runtime_core"] == set(), f"runtime_core must have 0 internal deps: {graph['runtime_core']}"
    visiting, visited = set(), set()

    def dfs(node, trail):
        visiting.add(node)
        for nxt in graph.get(node, ()):
            if nxt in visiting:
                raise AssertionError(f"Import cycle detected: {trail + [nxt]}")
            if nxt not in visited:
                dfs(nxt, trail + [nxt])
        visiting.remove(node)
        visited.add(node)

    for mod in sorted(graph):
        if mod not in visited:
            dfs(mod, [mod])


def check_security_iso_and_paths():
    # Expanded secret redaction: JWT, Google API key, Slack token, URL credentials, --relay-token, longest-first env
    jwt = ".".join(["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", "eyJzdWIiOiIxMjM0NTY3ODkwIn0", "abcdefghijk1234567890"])
    aiza = "AIza" + "SyA1234567890abcdefghijkLMNOPQRSTUV"
    slack = "-".join(["xoxb", "1234567890", "1234567890", "abcdefghijklmnopqrst"])
    url = "https://alice:" + "SuperSecretPass123" + "@example.invalid/repo.git"
    rtok = "0123456789abcdef" * 2
    with patch.dict(os.environ, {"SHORT_TOKEN": "abcd1234", "LONG_TOKEN": "abcd1234extra9999"}):
        text = f"jwt={jwt} key={aiza} slack={slack} url={url} --relay-token {rtok} env=abcd1234extra9999"
        clean = S.sanitize(text)
        for secret in (jwt, aiza, slack, "SuperSecretPass123", rtok, "abcd1234extra9999"):
            assert secret not in clean, (secret, clean)
    # require_public rejects /private/tmp, UNC (both \\ and //), Git-Bash /c/Users/...
    for bad in ("/private/tmp/secret.txt", "//server/share/file", r"\\server\share\file", "/c/Users/someone/file.txt", "C:/Users/someone/file.txt"):
        try:
            S.require_public(bad, "test")
            raise AssertionError(f"Private path allowed: {bad}")
        except ValueError:
            pass
    # Python 3.8-safe UTC ISO timestamp parser (Z, fractional seconds, offsets)
    assert abs(Core.parse_iso_utc("2030-01-01T00:00:00Z") - 1893456000.0) < 1e-3
    assert abs(Core.parse_iso_utc("2030-01-01T00:00:00.123456789Z") - 1893456000.123456) < 1e-3
    assert abs(Core.parse_iso_utc("2030-01-01T03:00:00+03:00") - 1893456000.0) < 1e-3
    # public_path refuses "." itself
    with tempfile.TemporaryDirectory(prefix="pb-pub-") as tmp:
        try:
            Core.public_path(Path(tmp), ".")
            raise AssertionError("public_path allowed root '.'")
        except ValueError:
            pass


def check_mixed_policy_quick_flags_and_legacy_speed():
    with scrub_environ(), tempfile.TemporaryDirectory(prefix="pb-mixed-") as tmp:
        root = Path(tmp) / "project"
        root.mkdir()
        make_project(root, legacy=False)
        # Legacy v3.12 executor-policy.json containing `"speed": "turbo"` is tolerated on load and stripped
        legacy_policy = {
            "schema": 1,
            "execution": {"source": "mixed"},
            "scheduling": {"mode": "parallel", "max_parallel": 3},
            "quota_recovery": {"enabled": False, "threshold_percent": 10},
            "speed": "turbo",
        }
        (B.bp(root) / "executor-policy.json").write_text(json.dumps(legacy_policy), encoding="utf-8")
        loaded = E.load(B, root)
        assert loaded["execution"]["source"] == "mixed"
        assert "speed" not in loaded
        assert E.settings(B, root)["exec"] == "mixed"
        E.confirm(B, root, "Confirmed mixed")
        E.guard(B, root, "exec", "native")
        E.guard(B, root, "exec", "pool")

        # Inline CLI policy flags: --qrp on, --max-parallel without --schedule, --source native --review-source cap-category --categories fast
        code, out = run_cli(root, "policy", "--source", "native", "--review-source", "cap-category", "--categories", "fast", "--qrp", "on", "--qrp-threshold", "15", "--confirm")
        assert code == 0, out
        pol = E.require_confirmed(B, root)
        assert pol["execution"]["source"] == "native" and "categories" not in pol["execution"]
        assert pol["review"] == {"source": "cap-category", "categories": ["fast"]}
        assert pol["quota_recovery"] == {"enabled": True, "threshold_percent": 15}
        code, out = run_cli(root, "policy", "--max-parallel", "4", "--confirm")
        assert code == 0, out
        assert E.require_confirmed(B, root)["scheduling"] == {"mode": "parallel", "max_parallel": 4, "auto": False}
        # setup ask --advanced shows power options without breaking
        code, out = run_cli(root, "setup", "ask", "--advanced")
        assert code == 0 and "--qrp on|off" in out and "PB policy --source" in out, out

        # Mixed ESP admits BOTH --backend native and --backend pool in PB runs!
        code, out = run_cli(root, "policy", "--source", "mixed", "--schedule", "parallel", "--max-parallel", "2", "--confirm")
        assert code == 0, out
        B.write_atomic(B.bp(root) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nTest mixed.\n")
        R.reconcile(B, root, B.find_task(root, "PB-001"), "Mixed target confirmed")
        O.git(root, "init")
        O.git(root, "config", "user.name", "Fixture Human")
        O.git(root, "config", "user.email", "human@example.invalid")
        O.git(root, "add", ".")
        O.git(root, "commit", "-m", "Mixed baseline")
        directory = L.directory(B, root)
        db = L.Ledger(directory / "runs.sqlite3")
        try:
            native_run = O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native")
            pool_run = O.prepare(B, root, db, directory, "PB-001", "REVIEW", "pool")
            assert native_run["spec"]["backend"] == "native"
            assert pool_run["spec"]["backend"] == "pool"
        finally:
            db.close()

        # Explicit lower-tier qualification does NOT crash select_policy with TypeError (blocker regression)
        code, out = run_cli(root, "policy", "--source", "cap-catalog", "--confirm")
        assert code == 0, out
        AP.qualify(B, root, "r1", "weak-model", "L", "Low tier only")
        rows = [
            {"routeId": "r1", "modelId": "weak-model", "enabled": True, "kinds": ["write"], "efforts": ["low"]},
            {"routeId": "r1", "modelId": "strong-model", "enabled": True, "kinds": ["write"], "categories": ["high"], "efforts": ["high"]},
        ]
        with patch.object(AP, "rpc", return_value={"models": rows, "nextOffset": None}):
            chosen = AP.select_policy(B, root, "H", mode="execute")
            assert chosen["selected"]["id"] == "strong-model"
            try:
                AP.select_policy(B, root, "H", model="weak-model", mode="execute")
                raise AssertionError("Weak model should have been blocked")
            except ValueError as exc:
                assert "qualified=L" in str(exc), str(exc)


def check_orchestration_commits_deletions_secrets_and_cancel():
    with scrub_environ(), tempfile.TemporaryDirectory(prefix="pb-orch-v4-") as tmp:
        root = Path(tmp) / "project"
        root.mkdir()
        make_project(root, legacy=False)
        (root / "src/obsolete.py").write_text("old = True\n", encoding="utf-8")
        B.write_atomic(B.bp(root) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nVerify v4 fixes.\n")
        R.reconcile(B, root, B.find_task(root, "PB-001"), "Confirmed")
        O.git(root, "init")
        O.git(root, "config", "user.name", "Fixture Human")
        O.git(root, "config", "user.email", "human@example.invalid")
        O.git(root, "add", ".")
        O.git(root, "commit", "-m", "Baseline")
        B.set_session_modes(root, "native", "native", schedule="parallel", max_parallel=2)
        directory = L.directory(B, root)
        db = L.Ledger(directory / "runs.sqlite3")
        try:
            # 1. Worker commits a secret inside worktree -> snapshot MUST scan against base and REJECT!
            run_sec = O.prepare(B, root, db, directory, "PB-001", "EXECUTE", "native")
            launch_sec = O.submit(B, root, db, directory, run_sec["id"])
            work_sec = O.workspace(run_sec, directory)
            (work_sec / "src/a.py").write_text("api_key = '" + "sk-" + "1234567890abcdefghijklmno'\n", encoding="utf-8")
            O.git(work_sec, "add", "src/a.py")
            O.git(work_sec, "commit", "-m", "Accidental committed secret")
            O.native_receipt(db, run_sec["id"], {
                "request_key": launch_sec["request_key"], "host": "fixture", "model": "m1",
                "tier": "L", "job_id": "j-sec", "state": "SUCCEEDED",
                "report": {"status": "completed", "summary": "Committed", "files": [], "checks": [], "research": [], "blockers": []},
            })
            try:
                O.snapshot(B, root, db, directory, run_sec["id"])
                raise AssertionError("Worker-committed secret bypassed snapshot scan!")
            except ValueError as exc:
                assert "Sensitive" in str(exc), str(exc)
            O.reject(B, root, db, run_sec["id"], "Secret rejected")

            # 2. Worker commits edit AND deletes src/obsolete.py -> snapshot + verify + accept + integrate succeed!
            run = O.prepare(B, root, db, directory, "PB-001", "EXECUTE", "native")
            launch = O.submit(B, root, db, directory, run["id"])
            work = O.workspace(run, directory)
            (work / "src/a.py").write_text("committed_by_worker = True\n", encoding="utf-8")
            (work / "src/obsolete.py").unlink()
            O.git(work, "add", "-A")
            O.git(work, "commit", "-m", "Worker edit and deletion")
            actor = O.native_receipt(db, run["id"], {
                "request_key": launch["request_key"], "host": "fixture", "model": "m2",
                "tier": "L", "job_id": "j1", "state": "SUCCEEDED",
                "report": {"status": "completed", "summary": "Committed", "files": [], "checks": [], "research": [], "blockers": []},
            })["actor"]
            out_rev = O.snapshot(B, root, db, directory, run["id"])
            assert O.git(root, "show", out_rev + ":src/a.py") == "committed_by_worker = True"
            ver = O.verify(B, root, db, directory, run["id"], actor)
            assert ver["exit"] == 0, ver
            cand = Path(ver["candidate"])
            ct = B.find_task(cand, "PB-001")
            B.write_atomic(ct["file"], B.read(ct["file"]).replace("- [ ] [machine]", "- [x] [machine]"))
            assert V.accept(B, cand, "PB-001", actor=actor)[0] == 0
            assert O.integrate(B, root, db, directory, run["id"])["integration"] == "MERGED"
            assert not (root / "src/obsolete.py").exists()

            # 3. INVALID_REPORT on EXECUTE worktree (including worker commits) recovers cleanly
            B.set_session_modes(root, "pool-all", "pool-all", schedule="parallel", max_parallel=2)
            B.set_headers(B.bp(root) / "tasks/PB-001.md", {"Status": "READY"})
            O.git(root, "add", ".project-brain/tasks/PB-001.md")
            O.git(root, "commit", "-m", "Reopen for INVALID_REPORT check")
            R.reconcile(B, root, B.find_task(root, "PB-001"), "Reopened")
            row = O.prepare(B, root, db, directory, "PB-001", "EXECUTE", "pool")
            row = db.transition(row["id"], "SUBMITTING", row["version"])
            row = db.transition(row["id"], "RUNNING", row["version"], backend_id="cap-bad-report")
            (O.workspace(row, directory) / "src/a.py").write_text("recovered_from_invalid_report = True\n", encoding="utf-8")
            with patch.object(O.P, "rpc", return_value={"state": "needs_review", "error": "INVALID_REPORT"}):
                observed = O.observe(B, root, db, directory, row["id"])
            assert observed["state"] == "SUCCEEDED", observed
            assert observed["result"]["decision_required"] is True, observed
            full_report = db.get(row["id"])["report"]
            assert full_report["files"] == [{"path": "src/a.py"}], full_report
            assert full_report["decision_required"] is True, full_report

            # 4. runs cancel without --force refuses SUBMITTING run lacking backend_id; --force records FORCE_CANCELLED
            B.set_session_modes(root, "native", "native", schedule="parallel", max_parallel=2)
            run_sub = O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native")
            O.submit(B, root, db, directory, run_sub["id"])
            try:
                O.cancel(B, root, db, directory, run_sub["id"], force=False)
                raise AssertionError("SUBMITTING without backend_id was cancelled without --force")
            except ValueError as exc:
                assert "backend_id" in str(exc), str(exc)
            forced_sub = O.cancel(B, root, db, directory, run_sub["id"], force=True)
            assert forced_sub["state"] == "CANCELLED", forced_sub

            run2 = O.prepare(B, root, db, directory, "PB-001", "REVIEW", "native")
            launch2 = O.submit(B, root, db, directory, run2["id"])
            O.native_receipt(db, run2["id"], {
                "request_key": launch2["request_key"], "host": "fixture", "model": "m3",
                "tier": "L", "job_id": "j2", "state": "RUNNING",
            })
            forced = O.cancel(B, root, db, directory, run2["id"], force=True)
            assert forced["state"] == "CANCELLED", forced
            # Verify PB-Agent trailer was recorded on integrated commit
            log_msg = O.git(root, "log", "-1", "--format=%B", "HEAD~1")
            assert "PB-Agent:" in log_msg, log_msg
        finally:
            db.close()


def check_context_watch_cli_and_worker_boundaries():
    with scrub_environ(), tempfile.TemporaryDirectory(prefix="pb-ux-v4-") as tmp:
        root = Path(tmp) / "project"
        root.mkdir()
        make_project(root, legacy=False)
        # 1. packet()["objective"] is populated & padded/slug ADRs resolve
        B.set_session_modes(root, "SOLO", "SOLO")
        B.write_atomic(B.bp(root) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nPacket check.\n")
        (B.bp(root) / "decisions/ADR-007-auth.md").write_text("# ADR-007 Auth\nUse OAuth.\n", encoding="utf-8")
        task_file = B.bp(root) / "tasks/PB-001.md"
        task_file.write_text(task_file.read_text(encoding="utf-8") + "\n## Notes\nSee ADR-7.\n", encoding="utf-8")
        R.reconcile(B, root, B.find_task(root, "PB-001"), "Confirmed for packet")
        pkt = C.packet(B, root, B.find_task(root, "PB-001"))
        assert pkt["objective"] == "Run one local worker.", pkt
        assert any("ADR-007-auth.md" in k for k in pkt["decisions"]), pkt["decisions"]

        # 2. watch & watch --heal work cleanly via 2-level _reorder_argv (boolean flag before root)
        B.set_headers(task_file, {"Status": "REVIEW"})
        second = B.bp(root) / "tasks/PB-002.md"
        second.write_text(task_file.read_text(encoding="utf-8").replace("PB-001", "PB-002").replace("Status: REVIEW", "Status: IN_PROGRESS"), encoding="utf-8")
        code, out = run_cli(root, "watch", "--heal")
        assert code == 0, out
        # Compact single-line status: IN_PROGRESS PB-002 beats REVIEW PB-001, progress=0%
        assert "PB-002(IN_PROGRESS,0%)" in out, out

        # 3. CLI_AGENT_POOL_WORKER blocks mutating commands & agents scan/list while allowing read-only brief/watch/boot(ro)
        code, out = run_cli(root, "new", "Blocked by worker", extra_env={"CLI_AGENT_POOL_WORKER": "1"})
        assert code == 2 and "worker" in out.lower(), out
        code, out = run_cli(root, "agents", "list", extra_env={"CLI_AGENT_POOL_WORKER": "1"})
        assert code == 2 and "worker" in out.lower(), out
        code, out = run_cli(root, "brief", extra_env={"CLI_AGENT_POOL_WORKER": "1"})
        assert code == 0, out
        code, out = run_cli(root, "watch", extra_env={"CLI_AGENT_POOL_WORKER": "1"})
        assert code == 0, out

        # 4. -- sentinel preserved by _reorder_argv for leading-dash task titles
        code, out = run_cli(root, "new", "--", "-dash-title")
        assert code == 0 and "CREATED" in out, out

        # 5. Request ledger auto-rotates resolved entries at 100
        for i in range(105):
            r = RS.intake(B, root, [f"Question {i}"], "question")
            RS.intake(B, root, [], resolve=r["request"]["id"])
        assert len(RS.ledger(B, root)["requests"]) <= 100

        # 6. SVG files are scanned for secrets during evidence attachment
        svg = B.bp(root) / "evidence/PB-001/diag.svg"
        svg.parent.mkdir(parents=True, exist_ok=True)
        svg.write_text('<svg>api_key="synthetic-long-secret-value"</svg>', encoding="utf-8")
        try:
            S.scan_artifacts(B, root, [".project-brain/evidence/PB-001/diag.svg"])
            raise AssertionError("Secret in SVG not caught")
        except ValueError:
            pass

        # 7. MINOR finding owner validation + REV=solo explicit --self-review requirement
        B.set_headers(task_file, {"Status": "IN_PROGRESS", "Risk": "MEDIUM", "Owner": "lead"})
        B.write_atomic(task_file, B.read(task_file).replace("- [ ] [machine]", "- [x] [machine]"))
        B.set_session_modes(root, "SOLO", "SOLO")
        B.write_atomic(B.bp(root) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nAccept check.\n")
        R.reconcile(B, root, B.find_task(root, "PB-001"), "Confirmed")
        assert V.check(B, root, "PB-001", actor="lead")[0] == 0
        assert V.review(B, root, "PB-001", "lead", "PASS", self_review=False)[0] == 2
        assert V.review(B, root, "PB-001", "lead", "PASS", findings=["MINOR: polish label | reason=deferred | owner=PB-999"], self_review=True)[0] == 0
        code, lines = V.accept(B, root, "PB-001", actor="lead")
        assert code == 2 and "MINOR" in "\n".join(lines), lines
        # watch_status reports solo as solo (never native)
        assert "/solo |" in B.watch_status(root), B.watch_status(root)


def check_cycle2_authority_and_security_regressions():
    with scrub_environ(), tempfile.TemporaryDirectory(prefix="pb-c2-") as tmp:
        root = Path(tmp) / "project"
        root.mkdir()
        make_project(root, legacy=False)
        O.git(root, "init")
        O.git(root, "config", "user.name", "Fixture Human")
        O.git(root, "config", "user.email", "human@example.invalid")
        O.git(root, "add", ".")
        O.git(root, "commit", "-m", "Baseline")

        # 1. Read-only runs status/export does NOT create runs.sqlite3 on fresh repo
        db_file = L.directory(B, root, create=False) / "runs.sqlite3"
        assert not db_file.exists()
        code, out = run_cli(root, "runs", "status")
        assert code == 0 and '"active": 0' in out and '"cursor": 0' in out, out
        code, out = run_cli(root, "runs", "export")
        assert code == 0 and '"runs": []' in out and '"authority"' in out, out
        assert not db_file.exists(), "Read-only runs status/export created runs.sqlite3"

        # 2. Inline policy threshold updates work independently and reset back to 10
        code, out = run_cli(root, "policy", "--source", "native", "--qrp", "on", "--qrp-threshold", "20", "--confirm")
        assert code == 0, out
        assert E.load(B, root)["quota_recovery"] == {"enabled": True, "threshold_percent": 20}
        code, out = run_cli(root, "policy", "--qrp-threshold", "10", "--confirm")
        assert code == 0, out
        assert E.load(B, root)["quota_recovery"] == {"enabled": True, "threshold_percent": 10}
        # CAP workers (even with a valid relay token) cannot run policy --confirm or quota cancel
        code, out = run_cli(root, "policy", "--source", "cap-catalog", "--confirm", extra_env={"CLI_AGENT_POOL_WORKER": "1"})
        assert code == 2, out
        code, out = run_cli(root, "relay", "recover", "--from-hook", extra_env={"CLI_AGENT_POOL_WORKER": "1"})
        assert code == 2, out

        # 3. QRP binds raw policy_file_hash so disk edits revoke on resume, and Q.cancel works cleanly
        B.write_atomic(B.bp(root) / "evidence/PB-001/handoff.json", json.dumps({"task": "PB-001", "next": "resume"}))
        snap_low = {"accountId": "acc1", "ordinaryUsageAllowed": True,
                    "rateLimits": {"limitId": "lim1", "primary": {"usedPercent": 95, "resetsAt": 5000, "windowDurationMins": 300}}}
        snap_hi = {"accountId": "acc1", "ordinaryUsageAllowed": True,
                   "rateLimits": {"limitId": "lim1", "primary": {"usedPercent": 5, "resetsAt": 9000, "windowDurationMins": 300}}}
        pol = E.load(B, root)
        prep = QR.prepare(B, root, snap_low, pol, ".project-brain/evidence/PB-001/handoff.json", now=1000)
        QR.arm(B, root, prep["nonce"], "auto-1")
        # Tamper raw policy file bytes on disk (even formatting-only or unconfirmed edit) -> check_resume MUST revoke!
        pf = B.bp(root) / "executor-policy.json"
        pf.write_text(pf.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        res = QR.check_resume(B, root, snap_hi, pol, prep["nonce"], now=6000)
        assert res["status"] == "CANCELLED", res
        assert QR.cancel(B, root)["status"] == "CANCELLED"

        # 4. scan_staged catches NUL-byte secrets and Git mode 120000 symlinks
        (root / "src/nul_secret.bin").write_bytes(b"\x00\x01API_KEY=" + b"sk-" + b"1234567890abcdefghijklmno\x00")
        O.git(root, "add", "src/nul_secret.bin")
        try:
            S.scan_staged(B, root)
            raise AssertionError("NUL-byte secret bypassed scan_staged")
        except ValueError as exc:
            assert "Sensitive" in str(exc), str(exc)
        O.git(root, "reset", "HEAD", "src/nul_secret.bin")
        (root / "src/nul_secret.bin").unlink()

        blob = O.git(root, "hash-object", "-w", "--stdin", input_text="/etc/passwd")
        O.git(root, "update-index", "--add", "--cacheinfo", f"120000,{blob},src/evil_link")
        try:
            S.scan_staged(B, root)
            raise AssertionError("Git mode 120000 symlink bypassed scan_staged")
        except ValueError as exc:
            assert "120000" in str(exc), str(exc)
        O.git(root, "reset", "HEAD", "src/evil_link")

        # 5. migrate.require_supported rejects future non-X.Y.Z versions, and migrate_v0 ignores Goal status in task body
        for future_ver in ("4.1", "5.0", f"{Core.VERSION}-rc1", "5.0.0-alpha"):
            B.write_atomic(
                B.bp(root) / "config.yaml",
                f'schema_version: 4\nskill_version: "{future_ver}"\nprotocol_version: 1\n',
            )
            try:
                M.require_supported(root)
                raise AssertionError(f"Future version {future_ver} was not rejected")
            except ValueError:
                pass

        v0_root = Path(tmp) / "v0"
        v0_root.mkdir()
        (v0_root / "PROJECT_BRAIN.md").write_text(
            "# Project Brain\n\n## 1. Goal\nBuild app.\n\n## 2. Target\nDone.\n\n"
            "## 5. Tasks\n- [ ] T1: Mention Goal status: CONFIRMED in a note\n",
            encoding="utf-8",
        )
        plan, todo = [], []
        M.migrate_v0(v0_root, plan, todo)
        target_text = next(t for p, t, _ in plan if p.name == "target.md")
        assert "Status: DRAFT" in target_text, target_text

        # 6. select_policy honors explicit --group under cap-catalog (not only cap-category)
        code, out = run_cli(root, "policy", "--source", "cap-catalog", "--confirm")
        assert code == 0, out
        rows = [
            {"routeId": "r1", "modelId": "fast-m", "enabled": True, "kinds": ["write"], "categories": ["fast"], "efforts": ["medium"]},
            {"routeId": "r1", "modelId": "deep-m", "enabled": True, "kinds": ["write"], "categories": ["high"], "efforts": ["high"]},
        ]
        with patch.object(AP, "rpc", return_value={"models": rows, "nextOffset": None}):
            picked = AP.select_policy(B, root, "M", group="high", mode="execute")
            assert picked["selected"]["id"] == "deep-m", picked
            assert picked["request"].get("group") == "high", picked["request"]

        # 7. Cold boot --new-session preserves TAKEOVER_CHECK: SKIP, review: PASS valid, updated progress.next,
        #    and recognizes uncommitted DONE task Areas + ignores __pycache__/*.pyc noise
        t1 = B.bp(root) / "tasks/PB-001.md"
        B.write_atomic(
            t1,
            "# PB-001 — Task one\nStatus: READY\nRisk: MEDIUM\nPriority: P1\nTier: L\nDepends: -\nDomain: core\n"
            "Areas: src/**\nInputs: src/**\nSecrets: none\n\n## Objective\nUpdate a.py.\n\n"
            "## Steps\n1. Edit a.py.\n\n## Verify\n- `python -c \"print('ok')\"`\n\n"
            "## Acceptance\n- [ ] [machine] Works\n\n## Evidence\n\n## Review\n",
        )
        B.write_atomic(
            B.bp(root) / "config.yaml",
            '# user comment preserved\nschema_version: 4\nskill_version: "' + Core.VERSION + '"\nprotocol_version: 1\n',
        )
        B.write_atomic(B.bp(root) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nCold takeover test.\n")
        code, _ = run_cli(root, "policy", "--source", "solo", "--schedule", "serial", "--confirm")
        assert code == 0
        R.reconcile(B, root, B.find_task(root, "PB-001"), "Confirmed for cold takeover check")
        assert B.cmd_start(root, "PB-001", agent="lead") == 0
        (root / "src/a.py").write_text("x = 42\n", encoding="utf-8")
        B.write_atomic(t1, B.read(t1).replace("- [ ] [machine]", "- [x] [machine]"))
        assert V.check(B, root, "PB-001", actor="lead")[0] == 0
        assert V.review(B, root, "PB-001", "lead", "PASS", self_review=True)[0] == 0
        # Creating __pycache__/*.pyc inside `Areas: src/**` AFTER check/review must NOT invalidate digest!
        (root / "src/__pycache__").mkdir(exist_ok=True)
        (root / "src/__pycache__/a.cpython-311.pyc").write_bytes(b"\x00pyc")
        code, boot_out = run_cli(root, "boot", "--new-session")
        assert code == 0, boot_out
        assert "TAKEOVER_CHECK: SKIP (PB-001 Verify logs valid" in boot_out, boot_out
        assert "review: PASS valid on current digest=" in boot_out, boot_out
        assert "NEXT: Review PASS valid on current digest for PB-001:" in boot_out, boot_out
        assert "next: Review passed on current digest; run `accept` and commit" in boot_out, boot_out
        assert "VERSION_CHECK" not in boot_out, boot_out
        assert "__pycache__" not in boot_out, boot_out

        # Switching to native policy makes SOLO self-audit invalid -> boot must NOT advertise "review: PASS valid"
        code, _ = run_cli(root, "policy", "--source", "native", "--schedule", "serial", "--confirm")
        assert code == 0
        code, boot_native_mismatch = run_cli(root, "boot", "--read-only")
        assert code == 0 and "review: PASS valid" not in boot_native_mismatch, boot_native_mismatch
        assert "REVIEW PB-001: an independent reviewer" in boot_native_mismatch, boot_native_mismatch
        code, _ = run_cli(root, "policy", "--source", "solo", "--schedule", "serial", "--confirm")
        assert code == 0

        # Unresolved MINOR finding on PASS review must NOT advertise "DO NOT re-review; run accept"
        assert V.review(B, root, "PB-001", "lead", "PASS", findings=["MINOR: unowned minor item"], self_review=True)[0] == 0
        code, boot_unres = run_cli(root, "boot", "--read-only")
        assert code == 0 and "review: PASS valid" not in boot_unres, boot_unres
        assert "next: Fix review findings, recheck, then re-review" in boot_unres, boot_unres

        # Re-review clean PASS + accept PB-001 (uncommitted DONE), then tamper src/a.py -> _done_task_intact & board catch it!
        assert V.review(B, root, "PB-001", "lead", "PASS", self_review=True)[0] == 0
        assert V.accept(B, root, "PB-001", actor="lead")[0] == 0
        code, boot_done_ok = run_cli(root, "boot", "--read-only")
        assert code == 0 and "TAKEOVER_CHECK: SKIP (uncommitted DONE task edits present: PB-001" in boot_done_ok, boot_done_ok
        assert "PROGRESS_BOARD:" in boot_done_ok and "100% | COMPLETE | Tasks 1/1" in boot_done_ok, boot_done_ok
        (root / "src/a.py").write_text("x = 999\n", encoding="utf-8")
        code, boot_done_tampered = run_cli(root, "boot", "--read-only")
        assert code == 0 and "STATE: DIRTY" in boot_done_tampered and "TAKEOVER_CHECK: REQUIRED" in boot_done_tampered, boot_done_tampered
        assert "DONE tampered (reverify)" in boot_done_tampered and "100% | COMPLETE" not in boot_done_tampered, boot_done_tampered

        # 8. Default-on Progress Board & persistent Turkish/English toggle (`board on|off|göster|gösterme`) preserving comments
        code, b_default = run_cli(root, "board")
        assert code == 0 and "PROGRESS_BOARD:" in b_default and "DONE tampered (reverify)" in b_default, b_default

        # Hide via Turkish alias `gösterme` — preserves `# user comment preserved` in config.yaml
        code, b_off = run_cli(root, "board", "gösterme")
        assert code == 0 and "BOARD: OFF" in b_off and B.parse_config(root).get("board") == "off", b_off
        assert "# user comment preserved" in (B.bp(root) / "config.yaml").read_text(encoding="utf-8")
        code, boot_hidden = run_cli(root, "boot", "--read-only")
        assert code == 0 and "PROGRESS_BOARD" not in boot_hidden, boot_hidden
        code, b_when_off = run_cli(root, "board")
        assert code == 0 and "BOARD: OFF" in b_when_off and "PROGRESS_BOARD" not in b_when_off, b_when_off
        code, b_forced = run_cli(root, "board", "--force")
        assert code == 0 and "PROGRESS_BOARD:" in b_forced, b_forced

        # Pool worker can read `board` / `board status` but cannot toggle `board on`/`board off`
        code, w_ro = run_cli(root, "board", "--force", extra_env={"CLI_AGENT_POOL_WORKER": "1"})
        assert code == 0 and "PROGRESS_BOARD" in w_ro, w_ro
        code, w_mut = run_cli(root, "board", "on", extra_env={"CLI_AGENT_POOL_WORKER": "1"})
        assert code == 2 and "Pool workers cannot run" in w_mut, w_mut

        # Re-enable via Turkish alias `göster`
        code, b_on = run_cli(root, "board", "göster")
        assert code == 0 and "BOARD: ON" in b_on and "PROGRESS_BOARD:" in b_on, b_on
        assert B.parse_config(root).get("board") == "on"
        assert "# user comment preserved" in (B.bp(root) / "config.yaml").read_text(encoding="utf-8")
        code, boot_restored = run_cli(root, "boot", "--read-only")
        assert code == 0 and "PROGRESS_BOARD:" in boot_restored, boot_restored

        # 9. Read-only protocol/security/migrate must not create .cache/writer.lock, and current.md-only Areas succeed
        ro_root = Path(tmp) / "ro-lock"
        ro_root.mkdir()
        make_project(ro_root, legacy=False)
        import shutil as _shutil
        _shutil.rmtree(B.bp(ro_root) / ".cache", ignore_errors=True)
        for cmd in (("protocol",), ("security",), ("migrate",)):
            code, _ = run_cli(ro_root, *cmd, extra_env={"CLI_AGENT_POOL_WORKER": "1"})
            assert code == 0 and not (B.bp(ro_root) / ".cache/writer.lock").exists(), cmd
        arch_root = Path(tmp) / "arch-only"
        arch_root.mkdir()
        B.cmd_init(arch_root)
        B.write_atomic(B.bp(arch_root) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nDoc task.\n")
        B.write_atomic(
            B.bp(arch_root) / "tasks/PB-001.md",
            "# PB-001 — Update current.md\nStatus: READY\nRisk: LOW\nPriority: P2\nTier: L\nDepends: -\nDomain: core\n"
            "Areas: .project-brain/current.md\n\n## Objective\nDocument arch.\n\n## Steps\n1. Update current.md.\n\n"
            "## Acceptance\n- [ ] [machine] Valid\n\n## Verify\n- `python -c \"assert True\"`\n",
        )
        code, _ = run_cli(arch_root, "policy", "--source", "solo", "--schedule", "serial", "--confirm")
        assert code == 0
        R.reconcile(B, arch_root, B.find_task(arch_root, "PB-001"), "Confirmed arch task")
        dig_arch, cnt_arch = V.task_digest(B, arch_root, B.find_task(arch_root, "PB-001"), check_session=False)
        assert len(dig_arch) == 16 and cnt_arch >= 1


def main():
    check_architecture_invariants()
    check_security_iso_and_paths()
    check_mixed_policy_quick_flags_and_legacy_speed()
    check_orchestration_commits_deletions_secrets_and_cancel()
    check_context_watch_cli_and_worker_boundaries()
    check_cycle2_authority_and_security_regressions()
    print("PASS: v4.0 acyclicity, security, ISO, mixed ESP, quick policy, worker commits/deletions, INVALID_REPORT, watch, SVG scan and worker gates")


if __name__ == "__main__":
    main()
