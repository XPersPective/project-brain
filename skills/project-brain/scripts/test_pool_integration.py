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
        fake.write_text("import{appendFileSync,writeFileSync}from'node:fs';import{spawnSync}from'node:child_process';process.stdin.resume();process.stdin.on('end',()=>{if(process.env.CLI_AGENT_POOL_WORKER!=='1')process.exit(9);" + nested + "appendFileSync('runs.txt','one\\n');writeFileSync('src/a.py','verified = True\\n');console.log('effort='+process.argv[2]);});", encoding="utf-8")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        config = {"port": port, "workspaceRoots": [str(project)], "selectionMode": "manual", "routes": [{
            "id": "synthetic", "adapter": "custom", "executable": node, "enabled": True,
            "billing": "free", "trustedSettings": True, "promptStdin": True,
            "argsTemplate": [str(fake), "{effort}"], "models": [{
                "id": "synthetic-1.0", "alias": "Synthetic test", "group": "unassigned",
                "efforts": ["low", "medium", "high"], "kinds": ["write"],
                "memberships": [{"group": "low", "effort": "medium"}]}]}]}
        (state / "config.json").write_text(json.dumps(config), encoding="utf-8")
        env = {"CLI_AGENT_POOL_HOME": str(state), "PB_AGENTS_REGISTRY": str(root / "brain-registry" / "agents.json"),
               "PB_AGENT_POOL_COMMAND": json.dumps([node, str(Path(entry).resolve())])}
        try:
            with patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()) as output:
                assert AP.rpc("pool_get_policy")["selectionMode"] == "manual"  # Starts from stopped.
                assert (state / "daemon.pid").is_file()
                time.sleep(0.3)
                assert AP.rpc("pool_list_pools")["pools"][2]["members"][0]["id"] == "synthetic-1.0"  # Survives caller exit.
                selected = AP.select("L")
                assert selected["request"]["effort"] == "medium"
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
        finally:
            pidfile = state / "daemon.pid"
            if pidfile.is_file():
                os.kill(int(pidfile.read_text()), signal.SIGTERM)
                time.sleep(0.5)
    print("PASS: real daemon auto-start survives RPC exit; Brain -> MCP -> native worker -> evidence; fixed effort and no replay")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool-entry", required=True)
    main(parser.parse_args().pool_entry)
