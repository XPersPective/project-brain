"""Shared test helpers and environment scrubbing for Project Brain test suite."""
from contextlib import contextmanager
import io
import os
from pathlib import Path
import subprocess
import sys

import brain as B

BRAIN = Path(__file__).resolve().parent / "brain.py"

SCRUB_ENV_KEYS = (
    "CLI_AGENT_POOL_WORKER",
    "CLI_AGENT_POOL_TASK_ID",
    "CLI_AGENT_POOL_TASK_TOKEN",
    "CLI_AGENT_POOL_HOME",
    "PB_RELAY_TOKEN",
    "PB_SESSION_ID",
    "PB_EXEC_MODE",
    "PB_REV_MODE",
    "PB_AGENTS_REGISTRY",
    "PB_PRIVATE_BINDING",
    "PB_AGENT_POOL_COMMAND",
)


def clean_env(extra=None):
    """Return a copy of os.environ with ambient CAP/PB worker variables removed."""
    env = {k: v for k, v in os.environ.items() if k not in SCRUB_ENV_KEYS}
    if extra:
        for k, v in extra.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = str(v)
    return env


@contextmanager
def scrub_environ(extra=None):
    """Temporarily scrub ambient CAP/PB env vars inside the current process."""
    saved = {}
    keys = set(SCRUB_ENV_KEYS) | set((extra or {}).keys())
    for k in keys:
        saved[k] = os.environ.get(k)
        os.environ.pop(k, None)
    if extra:
        for k, v in extra.items():
            if v is not None:
                os.environ[k] = str(v)
    try:
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def make_project(root, legacy=True):
    """Create a minimal initialized Project Brain throwaway project."""
    root = Path(root)
    with _quiet():
        B.cmd_init(root)
    if not legacy:
        B.set_session_modes(root, "SOLO", "SOLO", new=True)
    if legacy:
        cfg = B.parse_config(root)
        cfg["protocol_version"] = "0"
        B.write_atomic(B.bp(root) / "config.yaml", B.config_text(root, cfg))
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "a.py").write_text("pass\n", encoding="utf-8")
    task = root / ".project-brain" / "tasks" / "PB-001.md"
    task.write_text(
        "# PB-001 — Routing smoke check\nStatus: READY\nPriority: P2\nTier: L\nRisk: LOW\n"
        "Owner:\nDepends: -\nAreas: `src/**`\nDomains: core\n\n"
        "## Objective\nRun one local worker.\n\n## Steps\n1. Read the source.\n\n"
        "## Acceptance\n- [ ] [machine] Worker completed.\n\n"
        "## Verify\n- `python -c \"assert True\"`\n",
        encoding="utf-8",
    )


@contextmanager
def _quiet():
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        yield buf
    finally:
        sys.stdout = old


def run_cli(root, *args, extra_env=None):
    """Run brain.py CLI in a scrubbed subprocess environment."""
    cmd = (
        [sys.executable, "-B", str(BRAIN), "new", str(root), *args[1:]]
        if args and args[0] == "new"
        else [sys.executable, "-B", str(BRAIN), *args, str(root)]
    )
    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=clean_env(extra_env),
    )
    return r.returncode, r.stdout + r.stderr
