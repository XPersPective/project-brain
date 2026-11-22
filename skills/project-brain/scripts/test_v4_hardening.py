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

    # Zero broad/bare `except Exception` and 100% BOOLEAN_FLAGS vs argparse parity across all runtime modules
    bool_flags_used = set()
    for p in runtime_files:
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=p.name, feature_version=(3, 8))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None or (isinstance(node.type, ast.Name) and node.type.id == "Exception"):
                    raise AssertionError(f"Broad/bare except in {p.name}:{node.lineno}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
                if any(
                    kw.arg == "action" and isinstance(kw.value, ast.Constant) and kw.value.value in ("store_true", "store_false")
                    for kw in node.keywords
                ):
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("-"):
                            bool_flags_used.add(arg.value)
    missing_bool = sorted(bool_flags_used - set(B.BOOLEAN_FLAGS))
    assert not missing_bool, f"Boolean CLI flags missing from brain.BOOLEAN_FLAGS: {missing_bool}"


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

        # 10. 4.0.4 regressions: fence-aware sections/append_section, validate shell-op warning, optional-root `new`,
        #     REVIEW_PENDING progress.next, live SQLite board_summary, and Core native lead->independent review flow!
        fenced_md = (
            "# PB-001 — Doc\nStatus: READY\nPriority: P2\nTier: L\nRisk: LOW\nAreas: `docs/a.md`\n\n"
            "## Objective\nExample:\n```markdown\n## Evidence\n- fake\n## Acceptance\n- [x] fake\n```\n\n"
            "## Steps\n1. Write `docs/a.md`.\n\n## Acceptance\n- [ ] [machine] Real\n\n"
            "## Verify\n- `pytest -q && ruff check .`\n\n## Evidence\n\n## Review\n"
        )
        parsed_secs = B.sections(fenced_md)
        assert not any("fake" in l for l in parsed_secs.get("evidence", [])), parsed_secs
        assert not any("fake" in l for l in parsed_secs.get("acceptance", [])), parsed_secs
        assert list(Core.iter_markdown_headings("## A\n```inline```\n## B\nok\n".splitlines())) == [(0, "A"), (2, "B")]
        fenced_file = B.bp(arch_root) / "tasks/PB-001.md"
        B.write_atomic(fenced_file, fenced_md)
        B.append_section(fenced_file, "Evidence", "- real proof line")
        after_app = B.sections(B.read(fenced_file))
        assert [l for l in after_app.get("evidence", []) if l.strip()] == ["- real proof line"], after_app
        code, val_out = run_cli(arch_root, "validate")
        assert "shell operators/builtins" in val_out, val_out

        # Optional-root `PB new "Title"` works from repo cwd
        import subprocess as _sub, sys as _sys
        from test_helpers import BRAIN as _BRAIN, clean_env as _clean_env
        r_new = _sub.run(
            [_sys.executable, "-B", str(_BRAIN), "new", "Task from cwd"],
            cwd=str(arch_root), capture_output=True, text=True, encoding="utf-8", env=_clean_env(),
        )
        assert r_new.returncode == 0 and "CREATED .project-brain/tasks/PB-002.md" in r_new.stdout, r_new.stdout + r_new.stderr

        # Core native flow: concrete lead model (`claude-sonnet-4`) -> REVIEW_PENDING updates progress.next ->
        # `PB runs` native review shows live SQLite worker on `PB board` -> independent `claude-opus-4-6` PASS -> DONE!
        nat_root = Path(tmp) / "native-core"
        nat_root.mkdir()
        O.git(nat_root, "init", "-q")
        O.git(nat_root, "config", "user.name", "Test Human")
        O.git(nat_root, "config", "user.email", "human@example.com")
        run_cli(nat_root, "init")
        (nat_root / "src").mkdir()
        (nat_root / "src/app.py").write_text("x = 1\n", encoding="utf-8")
        B.write_atomic(B.bp(nat_root) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nNative core flow.\n")
        B.write_atomic(
            B.bp(nat_root) / "tasks/PB-001.md",
            "# PB-001 — Core feature\nStatus: READY\nPriority: P1\nTier: M\nRisk: MEDIUM\nOwner:\nDepends: -\n"
            "Areas: `src/app.py`\nDomains: core\n\n## Objective\nAdd core.\n\n## Steps\n1. Edit `src/app.py`.\n\n"
            "## Acceptance\n- [x] [machine] Works\n\n## Verify\n- `python -c \"assert True\"`\n\n## Evidence\n\n## Review\n",
        )
        O.git(nat_root, "add", "-A")
        O.git(nat_root, "commit", "-qm", "genesis\n\nPB-Genesis: true\nPB-Current-Checkpoint: all")
        assert run_cli(nat_root, "boot", "--new-session")[0] == 0
        assert run_cli(nat_root, "setup", "confirm")[0] == 0
        assert run_cli(nat_root, "reconcile", "PB-001", "--note", "ok")[0] == 0
        assert run_cli(nat_root, "start", "PB-001", "--agent", "claude-sonnet-4")[0] == 0
        assert run_cli(nat_root, "check", "PB-001", "--as", "claude-sonnet-4")[0] == 0
        rc_acc1, out_acc1 = run_cli(nat_root, "accept", "PB-001", "--as", "claude-sonnet-4")
        assert rc_acc1 == 1 and "REVIEW_PENDING PB-001" in out_acc1, out_acc1
        assert "next=Independent review -> accept" in out_acc1, out_acc1
        rc_prep, out_prep = run_cli(
            nat_root, "runs", "prepare", "--task", "PB-001", "--kind", "REVIEW",
            "--backend", "native", "--host", "host", "--model", "claude-opus-4-6",
        )
        assert rc_prep == 0, out_prep
        rid = json.loads(out_prep)["run"]
        rc_bd, out_bd = run_cli(nat_root, "board")
        assert rc_bd == 0 and "@host/claude-opus-4-6[REVIEW:PREPARED]" in out_bd, out_bd
        rc_sub, out_sub = run_cli(nat_root, "runs", "submit", "--run", rid)
        assert rc_sub == 0, out_sub
        req_key = json.loads(out_sub)["request_key"]
        rec_path = Path(tmp) / "native-review-receipt.json"
        rec_path.write_text(
            json.dumps({
                "host": "host", "model": "claude-opus-4-6", "tier": "M", "state": "SUCCEEDED",
                "request_key": req_key, "job_id": "job-rev-1",
                "report": {
                    "status": "completed", "summary": "Audited",
                    "files": [], "checks": [], "research": [], "blockers": [],
                    "verdict": "PASS", "findings": [],
                },
            }),
            encoding="utf-8",
        )
        rc_rec, out_rec = run_cli(nat_root, "runs", "receipt", "--run", rid, "--file", str(rec_path))
        assert rc_rec == 0, out_rec
        rev_actor = json.loads(out_rec)["actor"]
        rc_rev, out_rev = run_cli(nat_root, "review", "PB-001", "--reviewer", rev_actor, "--verdict", "PASS")
        assert rc_rev == 0, out_rev
        # Cold boot --new-session recognizes the valid native review on current digest!
        rc_cb, out_cb = run_cli(nat_root, "boot", "--new-session")
        assert rc_cb == 0 and "review: PASS valid on current digest=" in out_cb, out_cb
        assert run_cli(nat_root, "setup", "confirm")[0] == 0
        # Negative checks on native_gate: prefixed generic `host/lead` and receipt-less `pool/<24hex>` are refused!
        for bad_imp in ("host/lead", "anthropic/claude-opus-4-6", "pool/" + "a" * 24):
            fake_task = dict(B.find_task(nat_root, "PB-001"))
            fake_task["owner"] = bad_imp
            fake_task["evidence_lines"] = [f"- start: IN_PROGRESS | owner={bad_imp} | risk=MEDIUM | digest=1 | contract=1"]
            try:
                O.native_gate(B, nat_root, fake_task, rev_actor, "review")
                raise AssertionError(f"native_gate should have refused implementer {bad_imp}")
            except ValueError:
                pass
        rc_done, out_done = run_cli(nat_root, "accept", "PB-001", "--as", rev_actor)
        assert rc_done == 0 and "DONE PB-001" in out_done, out_done

        # 11. 4.0.5 permanent regressions: `_is_locally_done` forged DONE refusal, H-1 concurrent boot/gc,
        #     H-2 bystander boot --new-session active-relay protection, and H-4 staged Git submodule (160000)
        forge_root = Path(tmp) / "forge-done"
        forge_root.mkdir()
        make_project(forge_root, legacy=False)
        B.write_atomic(B.bp(forge_root) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nForge check.\n")
        assert run_cli(forge_root, "policy", "--source", "solo", "--schedule", "serial", "--confirm")[0] == 0
        assert run_cli(forge_root, "reconcile", "PB-001", "--note", "ok")[0] == 0
        assert run_cli(forge_root, "start", "PB-001")[0] == 0
        # Hand-edit Status: DONE after start without accept -> must NOT count as done!
        t_f1 = B.bp(forge_root) / "tasks/PB-001.md"
        B.write_atomic(t_f1, B.read(t_f1).replace("Status: IN_PROGRESS", "Status: DONE"))
        assert not B._is_locally_done(forge_root, B.find_task(forge_root, "PB-001"))
        rc_val_f, out_val_f = run_cli(forge_root, "validate")
        assert "finished task file kept without valid accept/Evidence" in out_val_f, out_val_f
        B.write_atomic(
            B.bp(forge_root) / "tasks/PB-002.md",
            "# PB-002 — Dependent\nStatus: READY\nPriority: P2\nTier: L\nRisk: LOW\nDepends: PB-001\nAreas: `src/a.py`\n\n"
            "## Objective\nDep.\n\n## Steps\n1. Edit `src/a.py`.\n\n## Acceptance\n- [ ] [machine] ok\n\n## Verify\n- `python -c \"assert True\"`\n",
        )
        assert run_cli(forge_root, "reconcile", "PB-002", "--note", "ok")[0] == 0
        rc_st2, out_st2 = run_cli(forge_root, "start", "PB-002")
        assert rc_st2 == 2 and "unmet dependencies: PB-001" in out_st2, out_st2

        # H-1: 4 concurrent `boot` processes with 6 committed DONE tasks -> all exit 0
        import concurrent.futures as _cf
        h1_root = Path(tmp) / "h1-conc"
        h1_root.mkdir()
        O.git(h1_root, "init", "-q")
        O.git(h1_root, "config", "user.name", "Test Human")
        O.git(h1_root, "config", "user.email", "human@example.com")
        make_project(h1_root, legacy=False)
        for i in range(1, 7):
            tid = f"PB-{i:03d}"
            (B.bp(h1_root) / "tasks" / f"{tid}.md").write_text(
                f"# {tid} — Task {i}\nStatus: DONE\nRisk: LOW\nAreas: src/a.py\n\n## Evidence\n- check: PASS\n",
                encoding="utf-8",
            )
        O.git(h1_root, "add", "-A")
        trailers = "\n".join(f"PB-Task: PB-{i:03d}" for i in range(1, 7))
        O.git(h1_root, "commit", "-qm", f"complete 6 tasks\n\n{trailers}\nPB-Verification: local")
        with _cf.ThreadPoolExecutor(max_workers=4) as ex:
            results = [f.result() for f in [ex.submit(run_cli, h1_root, "boot") for _ in range(4)]]
        for idx, (rc_c, out_c) in enumerate(results):
            assert rc_c == 0, f"H-1 concurrent boot thread {idx} failed: {out_c}"

        # H-2: Bystander boot --new-session during active Relay preserves policy receipt & session modes
        h2_root = Path(tmp) / "h2-relay-prot"
        h2_root.mkdir()
        O.git(h2_root, "init", "-q")
        O.git(h2_root, "config", "user.name", "Test Human")
        O.git(h2_root, "config", "user.email", "human@example.com")
        make_project(h2_root, legacy=False)
        assert run_cli(h2_root, "policy", "--source", "solo", "--schedule", "serial", "--confirm")[0] == 0
        assert E.receipt_matches_file(B, h2_root)
        rpath = RL._path(B, h2_root)
        rpath.parent.mkdir(parents=True, exist_ok=True)
        rpath.write_text(
            json.dumps({
                "schema": RL.SCHEMA, "status": "ACTIVE", "generation": 1,
                "director": {"route": "r1", "model": "m1", "task_id": "t1", "token_hash": "a" * 64, "since": 1},
                "pending": None, "owned": ["t1"], "history": [], "health": {}, "features": [], "unplanned": 0,
                "policy_hash": "b" * 64, "candidates": [{"route": "r1", "model": "m1"}], "inherited": {},
            }),
            encoding="utf-8",
        )
        rc_h2, out_h2 = run_cli(h2_root, "boot", "--new-session")
        assert rc_h2 == 0 and "RELAY_ACTIVE_PROTECTED" in out_h2, out_h2
        assert E.receipt_matches_file(B, h2_root) and B.get_session_modes(h2_root)["exec"] == "solo"

        # H-4: Staged Git submodule (mode 160000) passes security --scan cleanly
        sub_dir = Path(tmp) / "h4-sub"
        sub_dir.mkdir()
        O.git(sub_dir, "init", "-q")
        O.git(sub_dir, "config", "user.name", "Test Human")
        O.git(sub_dir, "config", "user.email", "human@example.com")
        (sub_dir / "x.txt").write_text("ok\n", encoding="utf-8")
        O.git(sub_dir, "add", "x.txt")
        O.git(sub_dir, "commit", "-qm", "sub init")
        sub_sha = O.git(sub_dir, "rev-parse", "HEAD")
        O.git(h1_root, "update-index", "--add", "--cacheinfo", f"160000,{sub_sha},libs/sub")
        rc_h4, out_h4 = run_cli(h1_root, "security", "--scan")
        assert rc_h4 == 0 and "SCAN PASS:" in out_h4, out_h4


def check_v406_redteam_regressions():
    """Permanent regression suite covering all 22 Red-Team findings fixed in 4.0.6."""
    import runtime_adopt as AD

    with tempfile.TemporaryDirectory(prefix="pb-v406-rt-") as tmp:
        # 1. Typo'd Areas must fail task_digest even when DEFAULT_INPUTS (AGENTS.md) exists
        r1 = Path(tmp) / "rt-areas"
        r1.mkdir()
        make_project(r1, legacy=False)
        B.write_atomic(B.bp(r1) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nReturn Result<T, E> and render <Modal>.\n")
        assert run_cli(r1, "policy", "--source", "solo", "--schedule", "serial", "--confirm")[0] == 0
        # Finding #18: Technical angle brackets in Goal work; --keep-evidence validates BEFORE mutating Risk
        t1_path = B.bp(r1) / "tasks/PB-001.md"
        orig_t1 = B.read(t1_path)
        B.write_atomic(t1_path, orig_t1.replace("Areas: `src/**`", "Areas: `src/typo_nonexistent/**`"))
        assert run_cli(r1, "reconcile", "PB-001", "--note", "Generic Result<T, E> goal allowed")[0] == 0
        try:
            R.task_digest(B, r1, B.find_task(r1, "PB-001"))
            raise AssertionError("Typo'd Areas should fail task_digest even when AGENTS.md exists")
        except ValueError as exc:
            assert "Areas match no files" in str(exc), exc
        # Verify --keep-evidence fails WITHOUT mutating Risk on disk
        B.write_atomic(t1_path, orig_t1.replace("1. Read the source.", "1. Edit `src/a.py` auth migration."))
        before_raw = B.read(t1_path)
        try:
            R.reconcile(B, r1, B.find_task(r1, "PB-001"), "keep check", keep_evidence=True)
            raise AssertionError("keep_evidence should fail when contract changed")
        except ValueError:
            pass
        assert B.read(t1_path) == before_raw, "Failed reconcile --keep-evidence mutated task file!"

        # 2. ADR-001 in Evidence/Review notes must NOT self-invalidate task_digest (#8)
        #    AND evidence defaults actor, enforces status, rejects comma in --file (#12)
        #    AND --self-review checks reviewer == owner at review time (#13)
        #    AND Inputs glob skips .env (#21)
        #    AND R.intent normalizes domain filenames (#14)
        r2 = Path(tmp) / "rt-verify"
        r2.mkdir()
        make_project(r2, legacy=False)
        B.write_atomic(r2 / "config/app.txt", "ok\n")
        B.write_atomic(r2 / "config/.env", "SECRET=1\n")
        B.write_atomic(B.bp(r2) / "decisions/ADR-001.md", "# ADR-001\nUse tokens.\n")
        B.write_atomic(B.bp(r2) / "target/User_Auth.md", "# User Auth\nStrong auth.\n")
        B.write_atomic(B.bp(r2) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nDeliver <Modal> flow.\n")
        t2_path = B.bp(r2) / "tasks/PB-001.md"
        B.write_atomic(
            t2_path,
            "# PB-001 — Verify Flow\nStatus: READY\nPriority: P2\nTier: L\nRisk: MEDIUM\nOwner:\nDepends: -\n"
            "Areas: `src/a.py`\nInputs: `config/**`\nDomains: `user-auth`\n\n"
            "## Objective\nCheck flow.\n\n## Steps\n1. Edit `src/a.py`.\n\n"
            "## Acceptance\n- [ ] [machine] unit test passes\n- [ ] [integration] workflow step succeeds\n\n"
            "## Verify\n- `python -c \"assert True\"`\n\n## Evidence\n\n## Review\n",
        )
        assert run_cli(r2, "policy", "--source", "solo", "--schedule", "serial", "--confirm")[0] == 0
        # Domain stem User_Auth normalized to user-auth -> included in R.intent
        i_before = R.intent(B, r2, B.find_task(r2, "PB-001"))
        B.write_atomic(B.bp(r2) / "target/User_Auth.md", "# User Auth\nChanged requirement.\n")
        i_after = R.intent(B, r2, B.find_task(r2, "PB-001"))
        assert i_before != i_after, "R.intent failed to normalize target/User_Auth.md"
        assert run_cli(r2, "reconcile", "PB-001", "--note", "Confirmed")[0] == 0
        # Evidence refused before start (status=READY)
        rc_pre_ev, _ = run_cli(r2, "evidence", "PB-001", "--kind", "integration", "--note", "service ok")
        assert rc_pre_ev != 0
        rc_st2, out_st2 = run_cli(r2, "start", "PB-001", "--agent", "lead")
        assert rc_st2 == 0, out_st2
        dig_before, _ = R.task_digest(B, r2, B.find_task(r2, "PB-001"))
        # Evidence without --as defaults to Owner; mentioning ADR-001 does NOT change digest
        rc_ev, out_ev = run_cli(r2, "evidence", "PB-001", "--kind", "integration", "--note", "matches ADR-001 boundary")
        assert rc_ev == 0, out_ev
        dig_after, _ = R.task_digest(B, r2, B.find_task(r2, "PB-001"))
        assert dig_before == dig_after, "Mentioning ADR-001 in Evidence self-invalidated task_digest!"
        # Evidence rejects comma in --file
        B.write_atomic(r2 / "shot,1.txt", "trace\n")
        rc_comma, out_comma = run_cli(r2, "evidence", "PB-001", "--kind", "integration", "--note", "ok", "--file", "shot,1.txt")
        assert rc_comma != 0 and "," in out_comma, out_comma
        # --self-review rejects mismatched reviewer alias at review time (#13)
        rc_sr_bad, out_sr_bad = run_cli(r2, "review", "PB-001", "--reviewer", "other-alias", "--verdict", "PASS", "--self-review")
        assert rc_sr_bad == 2 and "match Owner" in out_sr_bad, out_sr_bad
        # Matching owner succeeds and mentioning ADR-001 in review finding does not change digest
        assert run_cli(r2, "check", "PB-001")[0] == 0
        rc_sr_ok, out_sr_ok = run_cli(r2, "review", "PB-001", "--reviewer", "lead", "--verdict", "PASS", "--self-review", "--finding", "MINOR: see ADR-001 | accepted: tracked | owner: user")
        assert rc_sr_ok == 0, out_sr_ok
        assert R.task_digest(B, r2, B.find_task(r2, "PB-001"))[0] == dig_before
        # Complete acceptance + accept, then tamper source -> ALL views must agree PB-001 is NOT done (#9)
        B.write_atomic(t2_path, B.read(t2_path).replace("- [ ]", "- [x]"))
        rc_acc, out_acc = run_cli(r2, "accept", "PB-001", "--self-review")
        assert rc_acc == 0 and "DONE PB-001" in out_acc, out_acc
        B.write_atomic(
            B.bp(r2) / "tasks/PB-002.md",
            "# PB-002 — Downstream\nStatus: READY\nPriority: P2\nTier: L\nRisk: LOW\nDepends: PB-001\nAreas: `src/a.py`\n\n"
            "## Objective\nNext.\n\n## Steps\n1. Edit `src/a.py`.\n\n## Acceptance\n- [ ] [machine] ok\n\n## Verify\n- `python -c \"assert True\"`\n",
        )
        assert run_cli(r2, "reconcile", "PB-002", "--note", "ok")[0] == 0
        # Tamper src/a.py after PB-001 accept
        B.write_atomic(r2 / "src/a.py", "x = 999\n")
        assert not B._is_locally_done(r2, B.find_task(r2, "PB-001"))
        rc_b, out_b = run_cli(r2, "boot")
        assert rc_b == 0 and "PLAN: 2 open, 0 done" in out_b and "DONE modified after accept" in out_b, out_b
        rc_v, out_v = run_cli(r2, "validate")
        assert "no longer matches its recorded accept" in out_v, out_v
        rc_s2, out_s2 = run_cli(r2, "start", "PB-002")
        assert rc_s2 == 2 and "unmet dependencies: PB-001" in out_s2, out_s2
        assert "rem:100%(2/2)" in B.watch_status(r2), B.watch_status(r2)

        # 3. Migration bugs (#2, #3, #7): v3 + leftover migration-backup/PROJECT_BRAIN.md, stale backup tasks, fenced code blocks
        r3 = Path(tmp) / "rt-mig"
        r3.mkdir()
        B.write_atomic(B.bp(r3) / "config.yaml", "schema_version: 3\n")
        B.write_atomic(B.bp(r3) / "current.md", "# Current\n## Map\n- a.py\nSources: `a.py`\n")
        B.write_atomic(B.bp(r3) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nLive real goal.\n")
        B.write_atomic(B.bp(r3) / "migration-backup/PROJECT_BRAIN.md", "# Old v0\n")
        B.write_atomic(B.bp(r3) / "migration-backup/target.md", "# Stale backup target\n")
        B.write_atomic(B.bp(r3) / "migration-backup/tasks/PB-099.md", "# PB-099 — Deleted ghost\nStatus: READY\n")
        B.write_atomic(
            B.bp(r3) / "tasks/PB-001.md",
            "# PB-001 — HTTP spec\nStatus: READY\n\n## Objective\nExample:\n```http\nStatus: 200 OK\n## Fake Heading\n```\n",
        )
        assert B.legacy_kind(r3) == "v3", B.legacy_kind(r3)
        rc_m, out_m = run_cli(r3, "migrate", "--apply")
        assert rc_m == 0, out_m
        assert "Live real goal." in B.read(B.bp(r3) / "target.md")
        assert not (B.bp(r3) / "tasks/PB-099.md").exists(), "migrate_dir resurrected deleted task from backup!"
        migrated_t1 = B.read(B.bp(r3) / "tasks/PB-001.md")
        assert "```http\nStatus: 200 OK\n## Fake Heading\n```" in migrated_t1, migrated_t1

        # 4. Unaccepted committed DONE task with - start: must NOT be closed or GC'd (#6)
        #    AND gc_brain works with relative Path(".") (#20)
        r4 = Path(tmp) / "rt-gc"
        r4.mkdir()
        O.git(r4, "init", "-q")
        O.git(r4, "config", "user.name", "Test Human")
        O.git(r4, "config", "user.email", "human@example.com")
        make_project(r4, legacy=False)
        B.write_atomic(B.bp(r4) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nGC check.\n")
        assert run_cli(r4, "policy", "--source", "solo", "--schedule", "serial", "--confirm")[0] == 0
        assert run_cli(r4, "reconcile", "PB-001", "--note", "ok")[0] == 0
        assert run_cli(r4, "start", "PB-001")[0] == 0
        t4_p = B.bp(r4) / "tasks/PB-001.md"
        B.write_atomic(t4_p, B.read(t4_p).replace("Status: IN_PROGRESS", "Status: DONE"))
        O.git(r4, "add", "-A")
        O.git(r4, "commit", "-qm", "forged done\n\nPB-Task: PB-001\nPB-Verification: local")
        _, comp = B.history_task_ids(r4)
        assert "PB-001" not in comp, "Unaccepted started Protocol-1 task should not count in closed_ids!"
        B.gc_brain(r4)
        assert t4_p.exists(), "Unaccepted started Protocol-1 task must never be deleted by gc_brain!"

        # 5. Relay FAILOVER must not re-dispatch to a director that failed with HARD error (#4)
        r5 = Path(tmp) / "rt-relay"
        r5.mkdir()
        O.git(r5, "init", "-q")
        O.git(r5, "config", "user.name", "Test Human")
        O.git(r5, "config", "user.email", "human@example.com")
        make_project(r5, legacy=False)
        assert run_cli(r5, "policy", "--source", "solo", "--schedule", "serial", "--confirm")[0] == 0
        st5 = {
            "schema": RL.SCHEMA, "status": "HANDOFF_PENDING", "generation": 1,
            "director": {"route": "r1", "model": "m1", "task_id": "t-dir", "token_hash": "a" * 64, "since": 1},
            "pending": {
                "route": "r2",
                "model": "m2",
                "candidate": {"route": "r2", "model": "m2"},
                "task_id": "t-succ",
                "label": "pb-relay-2",
                "token_hash": "b" * 64,
                "requested_at": 10,
                "reason": "HANDOFF",
            },
            "owned": ["t-dir", "t-succ"], "history": [], "health": {}, "features": [], "unplanned": 0,
            "policy_hash": "c" * 64,
            "candidates": [{"route": "r1", "model": "m1"}, {"route": "r2", "model": "m2"}],
            "inherited": {"relay": {"enabled": True, "threshold_percent": 15}},
            "announced": False,
        }
        RL._write(B, r5, st5)
        submitted = []
        class _FakeRPC:
            def __call__(self, tool, args):
                if tool == "pool_get_task":
                    tid = args["taskId"]
                    if tid == "t-dir":
                        return {"id": "t-dir", "state": "failed", "error": "AUTH_REQUIRED: token expired"}
                    if tid == "t-succ":
                        return {"id": "t-succ", "state": "failed", "error": "QUOTA_BARRIER"}
                if tool == "pool_list_tasks":
                    return {"tasks": []}
                if tool == "pool_get_quotas":
                    return {"quotas": [
                        {"route": "r1", "model": "m1", "remainingPercent": 90, "status": "ok"},
                        {"route": "r2", "model": "m2", "remainingPercent": 0, "status": "exhausted", "resetAt": "2099-01-01T00:00:00Z"},
                    ]}
                if tool == "pool_submit":
                    submitted.append(args)
                    return {"id": "t-new"}
                return {}
        res5 = RL.recover(B, r5, {"relay": {"enabled": True, "threshold_percent": 15}}, _FakeRPC(), "brain.py", now=100)
        assert not any(s.get("route") == "r1" for s in submitted), f"Dispatched back to AUTH_REQUIRED director r1: {submitted}"
        assert res5.get("status") != "HANDING_OFF" or "r1" not in str(res5.get("actions")), res5

        # 6. Orchestration changed_paths ignores generated noise (.pytest_cache / __pycache__) (#5)
        r6 = Path(tmp) / "rt-orch-noise"
        r6.mkdir()
        O.git(r6, "init", "-q")
        O.git(r6, "config", "user.name", "Test Human")
        O.git(r6, "config", "user.email", "human@example.com")
        B.write_atomic(r6 / "src/a.py", "x = 1\n")
        O.git(r6, "add", "-A")
        O.git(r6, "commit", "-qm", "init")
        B.write_atomic(r6 / "src/a.py", "x = 2\n")
        B.write_atomic(r6 / ".pytest_cache/v/cache/stepwise", "[]\n")
        B.write_atomic(r6 / "src/__pycache__/a.cpython-312.pyc", "bin")
        assert O.changed_paths(B, r6) == ["src/a.py"], O.changed_paths(B, r6)

        # 7. Adoption: SKIP_DIRS subfolder in .planning/build does not wedge cleanup (#10) & null JSON values in tasks.json (#15)
        r7 = Path(tmp) / "rt-adopt"
        r7.mkdir()
        make_project(r7, legacy=False)
        B.write_atomic(r7 / ".planning/notes.md", "# Notes\nKeep this.\n")
        B.write_atomic(r7 / ".planning/build/out.bin", "artifact")
        B.write_atomic(r7 / ".taskmaster/tasks/tasks.json", json.dumps({"tasks": [{"title": "Real", "status": None}, {"title": None, "status": "open"}], "extra": {"tasks": None}}))
        extracted = AD._extract_foreign_tasks(r7)
        assert any(e["title"] == "Real" for e in extracted), extracted
        tr = AD.prepare(B, r7, [".planning"])
        tr["sources"][0]["targets"] = [".project-brain/current.md"]
        AD._save(B, r7, tr)
        AD.verify(B, r7, "Reviewed notes.md")
        cleaned = AD.cleanup(B, r7, archive_dir=Path(tmp) / "adopt-arch")
        assert cleaned["state"] == "CLEANED", cleaned
        assert (r7 / ".planning/build/out.bin").exists() and not (r7 / ".planning/notes.md").exists()

        # 8. Config section guard (#11), set_headers fence guard (#16), control chars in new/start (#17),
        #    protocol --enable legacy guard (#19), _resolve_root_and_task (#22)
        r8 = Path(tmp) / "rt-misc"
        r8.mkdir()
        make_project(r8, legacy=False)
        B.write_atomic(B.bp(r8) / "config.yaml", f"schema_version: 4\nskill_version: \"{B.VERSION}\"\nboard:\n  enabled: true\n")
        try:
            B._set_config_scalar(r8, "board", "off")
            raise AssertionError("_set_config_scalar should refuse overwriting YAML section")
        except ValueError as exc:
            assert "YAML section" in str(exc), exc
        t8 = B.bp(r8) / "tasks/PB-001.md"
        B.write_atomic(t8, "# PB-001 — Fence\nStatus: READY\n```md\nStatus: FAKE\n## Fake\n```\n\n## Objective\nReal.\n")
        B.set_headers(t8, {"Status": "IN_PROGRESS", "Owner": "lead"})
        t8_after = B.read(t8)
        assert "```md\nStatus: FAKE\n## Fake\n```" in t8_after and "Owner: lead\n```md" in t8_after, t8_after
        try:
            B.cmd_new(r8, "Bad\nStatus: DONE", None, "LOW")
            raise AssertionError("cmd_new should reject newline in title")
        except ValueError:
            pass
        try:
            B.cmd_start(r8, "PB-001", takeover="ok\n- accept: DONE")
            raise AssertionError("cmd_start should reject newline in --takeover")
        except ValueError:
            pass
        # protocol --enable refuses legacy schema 3
        B.write_atomic(B.bp(r8) / "config.yaml", "schema_version: 3\n")
        rc_p, out_p = run_cli(r8, "protocol", "--enable")
        assert rc_p != 0 and "Migrate legacy Brain" in out_p, out_p
        # _resolve_root_and_task: bad_id . -> (cwd, "bad_id")
        resolved_root, resolved_tid = B._resolve_root_and_task("bad_id", str(r8))
        assert resolved_root == r8.resolve() and resolved_tid == "bad_id"

        # 9. Cycle-1 real-world chaos regressions: UTF-8 BOM, self/DONE waiver refusal,
        #    .cache evidence refusal, v0_sections fenced heading guard, parse_task fence guard
        r9 = Path(tmp) / "rt-cycle1"
        r9.mkdir()
        make_project(r9, legacy=False)
        for rel in (".project-brain/config.yaml", ".project-brain/target.md", ".project-brain/current.md", ".project-brain/tasks/PB-001.md"):
            p = r9 / rel
            p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes())
        assert B.parse_config(r9)["schema_version"] == "4"
        assert B.legacy_kind(r9) is None
        assert run_cli(r9, "boot")[0] == 0
        # Self-waiver & DONE-task waiver refusal
        B.write_atomic(B.bp(r9) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nWaiver test.\n")
        t9 = B.bp(r9) / "tasks/PB-001.md"
        B.write_atomic(t9, B.read(t9).replace("Risk: LOW", "Risk: MEDIUM").replace("- [ ] [machine] Worker completed.", "- [ ] [machine] Worker completed.\n- [ ] [integration] ok"))
        B.write_atomic(B.bp(r9) / "tasks/PB-002.md", "# PB-002 — Closed\nStatus: DONE\n\n## Evidence\n- accept: DONE | digest=0000000000000000 | contract=0000000000000000\n")
        assert run_cli(r9, "policy", "--source", "solo", "--schedule", "serial", "--confirm")[0] == 0
        assert run_cli(r9, "reconcile", "PB-001", "--note", "ok")[0] == 0
        assert run_cli(r9, "start", "PB-001", "--agent", "lead")[0] == 0
        assert run_cli(r9, "check", "PB-001")[0] == 0
        # .cache file refused as evidence
        B.write_atomic(B.bp(r9) / ".cache/ephemeral.txt", "private\n")
        rc_c_ev, out_c_ev = run_cli(r9, "evidence", "PB-001", "--kind", "integration", "--note", "ok", "--file", ".project-brain/.cache/ephemeral.txt")
        assert rc_c_ev != 0 and "cache" in out_c_ev.lower(), out_c_ev
        # Self-owned waiver refused
        rc_sw, _ = run_cli(r9, "review", "PB-001", "--reviewer", "lead", "--verdict", "PASS", "--self-review", "--finding", "MINOR: x | accepted: later | owner: PB-001")
        assert rc_sw != 0, "Self-owned MINOR waiver must be refused!"
        # Already-DONE owner waiver refused
        rc_dw, _ = run_cli(r9, "review", "PB-001", "--reviewer", "lead", "--verdict", "PASS", "--self-review", "--finding", "MINOR: x | accepted: later | owner: PB-002")
        assert rc_dw != 0, "Already-DONE task MINOR waiver must be refused!"
        # parse_task fence-aware header scan
        pf = B.bp(r9) / "tasks/PB-003.md"
        B.write_atomic(pf, "# PB-003 — Fence\n```http\nStatus: DONE\nOwner: forged\n```\nStatus: READY\n\n## Objective\nTest.\n")
        pt = B.parse_task(pf)
        assert pt["status"] == "READY" and pt["owner"] == "", pt
        # v0_sections ignores fenced `## 5. TASKS` after real `## 5. TASKS`
        r10 = Path(tmp) / "rt-v0-fence"
        r10.mkdir()
        (r10 / "PROJECT_BRAIN.md").write_text(
            "# Project Brain\nGoal status: CONFIRMED\n\n## 1. GOAL\nApp.\n\n## 2. TARGET\nGood.\n\n"
            "## 3. CURRENT\nEmpty.\n\n## 4. FILE MAP\n- a.py\n\n"
            "## 5. TASKS\n- [ ] T1 [L] Real task\n  - Where: `a.py`\n\n"
            "## 6. DECISION LOG\n```md\n## 5. TASKS\n- [ ] T99 Fake\n```\n\n## 7. HANDOFF\nNone.\n",
            encoding="utf-8",
        )
        assert run_cli(r10, "migrate", "--apply")[0] == 0
        assert (B.bp(r10) / "tasks/PB-001.md").exists() and not (B.bp(r10) / "tasks/PB-099.md").exists()


def main():
    check_architecture_invariants()
    check_security_iso_and_paths()
    check_mixed_policy_quick_flags_and_legacy_speed()
    check_orchestration_commits_deletions_secrets_and_cancel()
    check_context_watch_cli_and_worker_boundaries()
    check_cycle2_authority_and_security_regressions()
    check_v406_redteam_regressions()
    print("PASS: v4.0 acyclicity, security, ISO, mixed ESP, quick policy, worker commits/deletions, INVALID_REPORT, watch, SVG scan and worker gates")


if __name__ == "__main__":
    main()
