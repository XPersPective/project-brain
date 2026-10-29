"""Production protocol integration/negative scenarios; no real credentials/providers."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import brain as B
import runtime_agents as A
import runtime_agent_pool as AP
import runtime_protocol as R
import runtime_security as S
import runtime_verify as V
from test_routing import _project
from test_brain import git


def denied(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError:
        return
    raise AssertionError("unsafe/stale action was allowed")


def main():
    with tempfile.TemporaryDirectory(prefix="pb-production-") as directory:
        root = Path(directory) / "project"
        root.mkdir()
        _project(root, legacy=False)
        assert R.enabled(B, root)
        file = B.bp(root) / "tasks/PB-001.md"
        task = B.find_task(root, "PB-001")
        registry = Path(directory) / "no-registry.json"
        with patch.object(A, "DEFAULT_REGISTRY", registry), contextlib.redirect_stdout(io.StringIO()):
            # DRAFT implementation cannot start; explicitly bounded discovery can.
            denied(B.cmd_start, root, task["id"])
            denied(R.reconcile, B, root, task, "confirmed scope")
            file.write_text(B.read(file).replace("Risk: LOW", "Purpose: discovery\nRisk: LOW"), encoding="utf-8")
            task = B.find_task(root, task["id"])
            R.reconcile(B, root, task, "Inspect source without choosing a product direction", independent=True)
            # Corrupt records fail as controlled errors, never KeyError/tracebacks.
            intent_path = R.record_path(B, root, task["id"], "intent")
            valid_intent = intent_path.read_text(encoding="utf-8")
            malformed = json.loads(valid_intent)
            malformed.pop("epoch")
            intent_path.write_text(json.dumps(malformed), encoding="utf-8")
            denied(B.cmd_start, root, task["id"])
            intent_path.write_text(valid_intent, encoding="utf-8")
            assert B.cmd_start(root, task["id"]) == 0
            assert V.check(B, root, task["id"])[0] == 0
            task = B.find_task(root, task["id"])
            with patch.object(V, "run_command", side_effect=AssertionError("cached proof must not execute")):
                assert V.check(B, root, task["id"])[0] == 0

            # Goal revision requires task impact reconciliation; proof can be kept
            # only by an explicit unchanged-outcome decision on an unchanged spec.
            target = B.bp(root) / "target.md"
            target.write_text("# Target\nStatus: CONFIRMED\n\n## Goal\nDeliver the agreed journey\n", encoding="utf-8")
            denied(V.check, B, root, task["id"])
            R.reconcile(B, root, task, "Only clarify wording; discovery outcome unchanged", independent=True, keep_evidence=True)
            assert "CACHED" in " ".join(V.check(B, root, task["id"])[1])
            R.reconcile(B, root, task, "Product scope now confirmed; refresh proof")
            assert V.check(B, root, task["id"])[0] == 0

            # Domain-specific Target state participates in reconciliation.
            domain = B.bp(root) / "target/core.md"
            domain.parent.mkdir(exist_ok=True)
            domain.write_text("# Core target\nPreserve invoice precision\n", encoding="utf-8")
            denied(V.check, B, root, task["id"])
            R.reconcile(B, root, task, "Core target added and task impact reviewed")
            assert V.check(B, root, task["id"])[0] == 0

            # Referenced architectural decisions are verification inputs too.
            file.write_text(B.read(file) + "\n## Notes\nFollow ADR-001.\n", encoding="utf-8")
            task = B.find_task(root, task["id"])
            before_adr = V.task_digest(B, root, task)[0]
            (B.bp(root) / "decisions/ADR-001.md").write_text("# ADR-001\nUse the existing persistence boundary\n", encoding="utf-8")
            assert before_adr != V.task_digest(B, root, task)[0]

            # Ownership does not expand when explicit or default verification input changes.
            before = V.task_digest(B, root, B.find_task(root, task["id"]))[0]
            (root / "package-lock.json").write_text('{"version":1}', encoding="utf-8")
            assert before != V.task_digest(B, root, B.find_task(root, task["id"]))[0]
            assert B.find_task(root, task["id"])["areas"] == ["src/**"]
            file.write_text(B.read(file).replace("Areas:", "Inputs: `shared.txt`\nAreas:"), encoding="utf-8")
            (root / "shared.txt").write_text("one", encoding="utf-8")
            task = B.find_task(root, task["id"])
            R.reconcile(B, root, task, "Shared contract input identified")
            before = V.task_digest(B, root, task)[0]
            (root / "shared.txt").write_text("two", encoding="utf-8")
            assert before != V.task_digest(B, root, task)[0]
            assert V.check(B, root, task["id"])[0] == 0
            task = B.find_task(root, task["id"])
            before = V.task_digest(B, root, task)[0]
            cfg = B.parse_config(root)
            cfg["verification"] = {"environment": "toolchain-v2"}
            B.write_atomic(B.bp(root) / "config.yaml", B.config_text(root, cfg))
            assert before != V.task_digest(B, root, task)[0]
            assert V.check(B, root, task["id"])[0] == 0

            # Explicit private/escaping Inputs fail, including ignored public inputs
            # which must contribute bytes rather than silently vanish from the digest.
            for pattern in (".env", "../outside.json", "C:/private/config.json"):
                invalid = dict(task, inputs=[pattern])
                R.reconcile(B, root, invalid, "Negative input fixture")
                denied(V.task_digest, B, root, invalid)
            R.reconcile(B, root, task, "Restore real public verification inputs")
            assert V.check(B, root, task["id"])[0] == 0
            journal = Path(directory) / "pool-receipt.json"
            journal.write_text(json.dumps({"taskId": "synthetic-complete", "contract": B.contract(task), "actor": "lead", "request": {}}), encoding="utf-8")
            args = SimpleNamespace(force=False, timeout=5, cli="", model="", effort="", group="", dry_run=False, readback=False)
            B.set_session_modes(root, "P-ALL", "P-ALL", new=True)
            with patch.object(AP, "journal_path", return_value=journal), patch.object(AP, "rpc", return_value={"id": "synthetic-complete", "state": "succeeded", "result": "ok"}) as rpc:
                assert AP.delegate(B, root, task, A.score_task(B, root, task), args) == 0
                assert AP.delegate(B, root, task, A.score_task(B, root, task), args) == 0
                assert rpc.call_count == 1  # second readback transfers neither result nor commands
                original_target = target.read_text(encoding="utf-8")
                target.write_text(original_target + "\n## Target State\nRevised outcome\n", encoding="utf-8")
                args.readback = True
                assert AP.delegate(B, root, task, A.score_task(B, root, task), args) == 0
                assert all(call.args[0] == "pool_get_task" for call in rpc.call_args_list)
                target.write_text(original_target, encoding="utf-8")
            # Explicit budget can stop new check work without blocking cached proof.
            state = R.progress_data(R.record_path(B, root, task["id"], "progress"))
            cfg = B.parse_config(root)
            cfg["execution"] = {"max_check_runs": state["usage"]["checks"]}
            B.write_atomic(B.bp(root) / "config.yaml", B.config_text(root, cfg))
            assert V.check(B, root, task["id"])[0] == 0
            denied(V.check, B, root, task["id"], rerun=True)
            cfg["execution"] = {"max_check_runs": 0}
            B.write_atomic(B.bp(root) / "config.yaml", B.config_text(root, cfg))

            # An explicit time budget clips the actual command timeout.
            original_spec = B.read(file)
            file.write_text(original_spec.replace('python -c "assert True"', 'python -c "import time; time.sleep(2)"'), encoding="utf-8")
            task = B.find_task(root, task["id"])
            R.reconcile(B, root, task, "Bounded timeout fixture")
            prior_seconds = R.progress_data(R.record_path(B, root, task["id"], "progress"))["usage"]["seconds"]
            cfg["execution"] = {"max_check_seconds": prior_seconds + 0.1}
            B.write_atomic(B.bp(root) / "config.yaml", B.config_text(root, cfg))
            assert V.check(B, root, task["id"])[0] == 1
            cfg["execution"] = {"max_check_seconds": 0}
            B.write_atomic(B.bp(root) / "config.yaml", B.config_text(root, cfg))
            file.write_text(original_spec, encoding="utf-8")
            task = B.find_task(root, task["id"])
            R.reconcile(B, root, task, "Return to fixture task")

            # Resume is compact and durable. Unchanged repeated failure stops the
            # third blind attempt; a changed source or strategy is not a blind retry.
            R.progress(B, root, task, "Fix the reproduced failure", "same failure", strategy="approach-a")
            R.progress(B, root, task, "Fix the reproduced failure", "same failure", strategy="approach-a")
            denied(R.attempt_guard, B, root, task)
            (root / "src/a.py").write_text("x = 2\n", encoding="utf-8")
            R.attempt_guard(B, root, task)
            R.progress(B, root, task, "Review current changes", strategy="approach-b")
            assert len(B.find_task(root, task["id"])["resume_lines"]) == 3
            assert "src/a.py" in " ".join(B.find_task(root, task["id"])["resume_lines"])
            denied(R.progress, B, root, task, "next", dirty="C:\\Users\\private-vault\\key.json")
            bad_progress = R.record_path(B, root, task["id"], "progress")
            saved_progress = bad_progress.read_text(encoding="utf-8")
            bad_progress.write_text('{"repeats":"two"}', encoding="utf-8")
            denied(R.attempt_guard, B, root, task)
            bad_progress.write_text(saved_progress, encoding="utf-8")


            # Host paths/raw logs never enter a handoff. A fresh clone without its
            # private logs honestly reports that verification is not reusable.
            assert V.check(B, root, task["id"])[0] == 0
            bundle = R.handoff(B, root, B.find_task(root, task["id"]))
            assert bundle["checks_reusable_here"] is True
            many = dict(B.find_task(root, task["id"]), external=[{"op": "save-" + str(n), "state": "response_unknown", "rest": "readback: approved-service"} for n in range(11)])
            assert len(R.handoff(B, root, many)["external"]) == 11
            private_summary = dict(many, resume_lines=["Dirty: C:\\Users\\private-store\\binding.json"])
            denied(R.handoff, B, root, private_summary)

            assert "PB_PRIVATE_BINDING" not in json.dumps(bundle)
            shutil.rmtree(B.bp(root) / ".cache/runs")
            bundle = R.handoff(B, root, B.find_task(root, task["id"]))
            assert bundle["checks_reusable_here"] is False
            assert V.check(B, root, task["id"])[0] == 0

            # SOLO still requires a distinct recorded audit action.
            B.set_session_modes(root, "SOLO", "SOLO", new=True)
            file.write_text(B.read(file).replace("Purpose: discovery", "Purpose: implementation").replace("Risk: LOW", "Risk: MEDIUM").replace("- [ ]", "- [x]"), encoding="utf-8")
            task = B.find_task(root, task["id"])
            R.reconcile(B, root, task, "Confirm implementation and its completion criteria")
            assert V.check(B, root, task["id"])[0] == 0
            assert V.accept(B, root, task["id"])[0] == 1
            assert V.review(B, root, task["id"], "lead", "PASS", self_review=True)[0] == 0
            proof = R.read_json(R.record_path(B, root, task["id"], "review-provenance"))
            assert proof["assurance"] == "self-audit"
            assert V.accept(B, root, task["id"])[0] == 0

            # Reviewer policy must still be present and identical at acceptance.
            B.set_header(file, "Status", "IN_PROGRESS")
            reviewer_registry = Path(directory) / "reviewers.json"
            A.save({"models": {"lead": {"model_id": "lead-model", "roles": ["lead"], "tiers": ["L", "M", "H"], "quality": 100}, "independent": {"model_id": "review-model", "roles": ["reviewer"], "tiers": ["L", "M", "H"], "quality": 100}}}, reviewer_registry)
            B.set_session_modes(root, "SOLO", "S-ALL")
            assert V.review(B, root, task["id"], "independent", "PASS", agents_path=reviewer_registry)[0] == 0
            registered = reviewer_registry.read_text(encoding="utf-8")
            reviewer_registry.unlink()
            assert V.accept(B, root, task["id"], agents_path=reviewer_registry)[0] == 2
            reviewer_registry.write_text(registered, encoding="utf-8")
            assert V.accept(B, root, task["id"], agents_path=reviewer_registry)[0] == 0

            B.set_header(file, "Status", "READY")
            file.write_text(B.read(file).replace("Risk: MEDIUM", "Risk: LOW").replace("Domains: core", "Domains: backend"), encoding="utf-8")
            task = B.find_task(root, task["id"])
            R.reconcile(B, root, task, "Normalize risk before binding the spec")
            assert task["risk"] != "LOW"
            assert B.cmd_start(root, task["id"]) == 0
            assert V.check(B, root, task["id"])[0] == 0

            # Generated history does not turn a small task into a split-required spec.
            current_task = B.find_task(root, task["id"])
            bloated = B.parse_task(file, B.read(file) + "\n## Review\n" + "historical observation\n" * 100)
            assert bloated["lines"] > 80 and bloated["spec_lines"] < 80
            assert A.score_task(B, root, bloated)["must_split"] == A.score_task(B, root, current_task)["must_split"]
            current_value = V.task_digest(B, root, current_task)[0]
            current_contract = B.contract(current_task)
            B.append_section(file, "Evidence", "- [visual] superseded fixture | criterion=deadbeef | by=lead | digest=" + "0" * 16 + " | contract=" + current_contract)
            B.append_section(file, "Evidence", "- [user_feedback] actual earlier decision | criterion=deadbeef | by=lead | digest=" + "0" * 16 + " | contract=" + current_contract)
            V.compact_machine_records(B, B.find_task(root, task["id"]), current_value, current_contract)
            compacted = B.read(file)
            assert "superseded fixture" not in compacted and "actual earlier decision" in compacted
            checks = [line for line in current_task["evidence_lines"] if V.CHECK_RE.match(line)]
            assert len(checks) == len(current_task["verify_cmds"])

            # Secret-bearing work cannot fall through to an ordinary child or Pool.
            B.set_header(file, "Status", "IN_PROGRESS")
            file.write_text(B.read(file).replace("Inputs:", "Secrets: vault-alias\nInputs:"), encoding="utf-8")
            task = B.find_task(root, task["id"])
            R.reconcile(B, root, task, "Secret-dependent integration isolated from fixture implementation")
            denied(V.check, B, root, task["id"])
            S.configure(B, root, "vault-alias", "User approved an external project-specific store")
            denied(V.check, B, root, task["id"])
            score = A.score_task(B, root, task)
            with patch.object(AP, "rpc", side_effect=AssertionError("secret task never sent")):
                denied(AP.delegate, B, root, task, score, object())

            # Approved host adapter/scanner contract. This fixture tests invocation
            # and output withholding, not a claim to install kernel isolation.
            adapter = Path(directory) / "adapter.py"
            adapter.write_text("import subprocess,sys\nsys.exit(subprocess.call(sys.argv[1:]))\n", encoding="utf-8")
            scanner = Path(directory) / "scanner.py"
            scanner.write_text("import sys\nsys.exit(1 if b'CANARY' in sys.stdin.buffer.read() else 0)\n", encoding="utf-8")
            private = Path(directory) / "binding.json"
            cmd = task["verify_cmds"][0]
            config = {"project": str(root.resolve()), "reference": "vault-alias",
                      "capabilities": ["credential_broker", "filesystem_isolation"],
                      "commands": {cmd: [sys.executable, str(adapter)]},
                      "scanner_argv": [sys.executable, str(scanner)]}
            private.write_text(json.dumps(config), encoding="utf-8")
            with patch.dict(os.environ, {"PB_PRIVATE_BINDING": str(private)}):
                assert V.check(B, root, task["id"])[0] == 0
                before_adapter_change = V.task_digest(B, root, task)[0]
                scanner.write_text(scanner.read_text(encoding="utf-8") + "# revised scanner\n", encoding="utf-8")
                assert before_adapter_change != V.task_digest(B, root, task)[0]
                assert V.check(B, root, task["id"])[0] == 0
                log = B.bp(root) / ".cache/runs/output-probe.log"
                result = V.run_command(root, [sys.executable, "-c", "print('CANARY')"], log,
                                       output_guard=lambda raw: S.scan_output(B, root, task, raw))
                assert result["exit_code"] == 125 and "CANARY" not in log.read_text()
                assert "withheld" in log.read_text()
                denied(S.configure, B, root, "D:/personal/location", "should never be embedded")
            # Generic sanitization before the log hash, plus fail-closed output cap.
            log = B.bp(root) / ".cache/runs/redaction.log"
            fake = "synthetic-long-secret-value"
            result = V.run_command(root, [sys.executable, "-c", "print('api_key=' + 'synthetic-long-secret-value')"], log)
            assert result["exit_code"] == 0 and fake not in log.read_text()
            result = V.run_command(root, [sys.executable, "-c", "print('x' * (5 * 1024 * 1024))"], log)
            assert result["exit_code"] == 125 and log.stat().st_size < 4 * 1024 * 1024 + 100
            (root / "private_build.json").write_text('{"api_key":"' + fake + '"}', encoding="utf-8")
            denied(S.scan_artifacts, B, root, ["private_build.json"])
            denied(S.require_clean, "api_key=" + fake, "outbound note")

    with tempfile.TemporaryDirectory(prefix="pb-staged-security-") as directory:
        root = Path(directory)
        _project(root, legacy=False)
        git(root, "init", "-q", "-b", "main")
        secret_file = root / "build-config.json"
        secret_file.write_text('{"api_key":"synthetic-staged-secret-value"}', encoding="utf-8")
        git(root, "add", "build-config.json")
        secret_file.write_text('{"public": true}', encoding="utf-8")
        denied(S.scan_staged, B, root)  # Safe worktree must not hide unsafe staged bytes.
        git(root, "add", "build-config.json")
        assert S.scan_staged(B, root) == 1
        (root / ".gitignore").write_text("local-fixture.json\n", encoding="utf-8")
        ignored = root / "local-fixture.json"
        ignored.write_text('{"value":1}', encoding="utf-8")
        file = B.bp(root) / "tasks/PB-001.md"
        file.write_text(B.read(file).replace("Areas:", "Inputs: `local-fixture.json`\nAreas:"), encoding="utf-8")
        (B.bp(root) / "target.md").write_text("# Target\nStatus: CONFIRMED\n\n## Goal\nVerify local fixture changes\n", encoding="utf-8")
        task = B.find_task(root, "PB-001")
        R.reconcile(B, root, task, "Explicit ignored public input remains a verification dependency")
        before = V.task_digest(B, root, task)[0]
        ignored.write_text('{"value":2}', encoding="utf-8")
        assert before != V.task_digest(B, root, task)[0]

    print("PASS: strict intent/revisions, dependency/environment inputs, dedup, progress, handoff, SOLO, secret preflight, adapter/scanner, redaction and output limits")


if __name__ == "__main__":
    main()
