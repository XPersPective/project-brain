"""Real Pool daemon/JSON/MCP/worker check using only a synthetic local CLI.

python -B test_pool_integration.py --pool-entry <install>/bin/pool.js
No provider inference, real account data or user workspace writes.
"""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import sys
import tempfile
import time
from unittest.mock import patch

import brain as B
import runtime_agents as A
import runtime_agent_pool as AP
import runtime_verify as V
from test_routing import _project


def main(entry):
    node = shutil.which("node")
    assert node and Path(entry).is_file(), "Node and Pool entry are required"
    with tempfile.TemporaryDirectory(prefix="pb-pool-integration-") as directory:
        root = Path(directory)
        project, state = root / "project", root / "pool"
        project.mkdir()
        state.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            _project(project)
        fake = root / "worker.mjs"
        nested = "const nested=spawnSync(" + json.dumps(sys.executable) + "," + json.dumps([str(Path(B.__file__).resolve()), "delegate", "PB-001", "--backend", "direct"]) + ",{encoding:'utf8'});if(nested.status!==2||!(nested.stdout+nested.stderr).includes('recursively'))process.exit(10);"
        report = {"status": "completed", "summary": "effort=medium", "files": [
            {"path": "src/a.py", "change": "Updated"}, {"path": "runs.txt", "change": "Created"}],
            "checks": [], "research": [], "blockers": []}
        fake.write_text("import{appendFileSync,writeFileSync}from'node:fs';import{spawnSync}from'node:child_process';"
                        "if(process.argv.includes('login')){console.log('Logged in using ChatGPT')}else{let input='';process.stdin.on('data',c=>input+=c);process.stdin.on('end',()=>{"
                        "if(process.env.CLI_AGENT_POOL_WORKER!=='1'||!input.includes('Pool subagent protocol v1')||!process.argv.includes('model_reasoning_effort=\"medium\"'))process.exit(9);" + nested +
                        "appendFileSync('runs.txt','one\\n');writeFileSync('src/a.py','verified = True\\n');"
                        "console.log(JSON.stringify({type:'item.completed',item:{type:'agent_message',text:" + json.dumps(json.dumps(report)) + "}}));"
                        "console.log(JSON.stringify({type:'turn.completed'}));});}", encoding="utf-8")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        config = {"port": port, "workspaceRoots": [str(project)], "selectionMode": "manual", "routes": [{
            "id": "synthetic", "adapter": "codex", "executable": str(fake), "enabled": True,
            "billing": "subscription", "trustedSettings": True, "promptStdin": True, "models": [{
                "id": "synthetic-1.0", "alias": "Synthetic test", "group": "unassigned",
                "efforts": ["low", "medium", "high"], "kinds": ["write"],
                "memberships": [{"group": "low", "effort": "medium"}]}]}]}
        (state / "config.json").write_text(json.dumps(config), encoding="utf-8")
        env = {"CLI_AGENT_POOL_HOME": str(state), "PB_AGENTS_REGISTRY": str(root / "brain-registry" / "agents.json"),
               "PB_AGENT_POOL_COMMAND": json.dumps([node, str(Path(entry).resolve())])}
        try:
            with patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()) as output:
                B.set_session_modes(project, "P-ALL", "P-ALL", new=True)
                assert AP.rpc("pool_get_policy")["selectionMode"] == "manual"  # Starts from stopped.
                assert (state / "daemon.pid").is_file()
                time.sleep(0.3)
                assert AP.rpc("pool_list_pools")["pools"][2]["members"][0]["id"] == "synthetic-1.0"  # Survives caller exit.
                selected = AP.select("L")
                assert selected["request"]["effort"] == "medium"
                assert selected["request"]["mode"] == "execute"
                args = argparse.Namespace(force=False, timeout=15, cli="", model="", effort="", group="", dry_run=False)
                task = B.find_task(project, "PB-001")
                score = A.score_task(B, project, task)
                assert AP.delegate(B, project, task, score, args) == 0, output.getvalue()
                task = B.find_task(project, "PB-001")
                assert AP.delegate(B, project, task, score, args) == 0, output.getvalue()
                assert (project / "runs.txt").read_text() == "one\n", "worker replayed"
                assert (project / "src/a.py").read_text() == "verified = True\n"
                assert "effort=medium" in output.getvalue()
                assert "[machine]" in task["text"] and "check `" in task["text"], output.getvalue()
                # New opt-in runs use the unchanged real Pool RPC schema and an
                # isolated workspace; no live model/provider is involved.
                import runtime_orchestration as O
                import runtime_runs as L
                isolated = root / "orchestrated"
                isolated.mkdir()
                _project(isolated, legacy=False)
                import runtime_protocol as R
                B.write_atomic(B.bp(isolated) / "target.md", "# Target\nStatus: CONFIRMED\n\n## Goal\nValidate default-protocol Pool execution and acceptance.\n")
                fixture_task = B.find_task(isolated, "PB-001")
                B.write_atomic(fixture_task["file"], B.read(fixture_task["file"]).replace("Areas: `src/**`", "Areas: `src/**`, `runs.txt`"))
                B.set_session_modes(isolated, "pool-all", "pool-all")
                R.reconcile(B, isolated, B.find_task(isolated, "PB-001"), "Synthetic Pool default-protocol fixture")
                O.git(isolated, "init")
                O.git(isolated, "config", "user.name", "Fixture Human")
                O.git(isolated, "config", "user.email", "human@example.invalid")
                O.git(isolated, "add", ".")
                O.git(isolated, "commit", "-m", "Synthetic integration fixture")
                B.set_session_modes(isolated, "pool-all", "pool-all")
                directory = L.directory(B, isolated)
                ledger = L.Ledger(directory / "runs.sqlite3")
                try:
                    run = O.prepare(B, isolated, ledger, directory, "PB-001", "EXECUTE", "pool")
                    O.submit(B, isolated, ledger, directory, run["id"])
                    deadline = time.monotonic() + 30
                    while ledger.get(run["id"])["state"] in L.ACTIVE and time.monotonic() < deadline:
                        time.sleep(.1)
                        O.observe(B, isolated, ledger, directory, run["id"])
                    assert ledger.get(run["id"])["state"] == "SUCCEEDED", O.summary(ledger.get(run["id"]))
                    workspace = O.workspace(run, directory)
                    assert (workspace / "src/a.py").read_text() == "verified = True\n"
                    assert not (isolated / "runs.txt").exists()
                    assert ledger.get(run["id"])["verification"] == "PENDING"
                    checked = O.verify(B, isolated, ledger, directory, run["id"], "")
                    assert checked["exit"] == 0, checked
                    candidate = Path(checked["candidate"])
                    candidate_task = B.find_task(candidate, "PB-001")
                    assert candidate_task["owner"] == AP.alias(selected["selected"])
                    B.write_atomic(candidate_task["file"], B.read(candidate_task["file"]).replace("- [ ] [machine]", "- [x] [machine]"))
                    accepted, lines = V.accept(B, candidate, "PB-001", actor=candidate_task["owner"])
                    assert accepted == 0, lines
                    assert O.integrate(B, isolated, ledger, directory, run["id"])["integration"] == "MERGED"
                    assert (isolated / "runs.txt").read_text() == "one\n"
                finally:
                    ledger.close()
        finally:
            pidfile = state / "daemon.pid"
            if pidfile.is_file():
                os.kill(int(pidfile.read_text()), signal.SIGTERM)
                time.sleep(0.5)
    print("PASS: real daemon auto-start survives RPC exit; Brain -> execute -> MCP -> native worker -> compact report -> evidence; fixed effort and no replay")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool-entry", required=True)
    main(parser.parse_args().pool_entry)
