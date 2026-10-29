#!/usr/bin/env python3
"""Evidence, verification, process containment and acceptance for Project Brain 3.0.

Stdlib only, Python 3.8+.
- Binds machine checks (`check`), non-machine observations (`evidence`), and independent
  reviews (`review`) to LF-normalized `areas_digest` and task `contract` digests.
- Runs Verify commands and delegated CLI workers inside a contained `ProcessTree`
  (Windows JobObject kill-on-close / POSIX process group) with an isolated Python bytecode cache.
- Stores ephemeral logs in `.project-brain/.cache/runs/` (gitignored) and committed
  visual/interaction artifacts in `.project-brain/evidence/<PB-NNN>/`.
"""

import ctypes
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import math
import ntpath
import os
from pathlib import Path, PureWindowsPath
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
import uuid

PRIVATE = re.compile(
    r"(^|/)(?:\.env(?:\.[^/]+)?|auth\.json|credentials?|secrets?|"
    r"service-account[^/]*|key\.properties|id_rsa|id_ed25519)(/|$)|"
    r"\.(?:jks|keystore|p8|p12|pfx|pem)$",
    re.I,
)
SECRET_ENV = re.compile(
    r"API_KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|PRIVATE|_KEY$|^KEY$|_PAT$|DSN$|"
    r"DATABASE_URL|_AUTH|AUTH_|COOKIE",
    re.I,
)
BATCH_META = re.compile(r'[&|<>^%!"\r\n]')

CHECK_RE = re.compile(
    r"^- \[machine\] check `(?P<cmd>[^`]+)` \| (?P<result>PASS|FAIL) \| exit=(?P<exit>-?\d+) \| "
    r"[0-9.]+s \| by=(?P<by>[^|]*?) "
    r"\| digest=(?P<digest>[0-9a-f]+) \| contract=(?P<contract>[0-9a-f]+) "
    r"\| log=(?P<log>\S+)@(?P<hash>[0-9a-f]+)$"
)
EVIDENCE_RE = re.compile(
    r"^- \[(?P<kind>[a-z_]+)\] (?!check `)(?P<note>[^|]*?) \| criterion=(?P<criteria>[0-9a-f,]+)"
    r"(?: \| files=(?P<files>[^|]+))? \| by=(?P<by>[^|]*?) \| digest=(?P<digest>[0-9a-f]+) "
    r"\| contract=(?P<contract>[0-9a-f]+)$"
)
REVIEW_RE = re.compile(
    r"^- review by (.+?) \| (PASS|BLOCKED) \| digest=([0-9a-f]+) \| contract=([0-9a-f]+)$"
)
FINDING_RE = re.compile(
    r"^- finding (BLOCKER|MAJOR|QUALITY|MINOR): (.+?)(?: \| accepted: (.+?) \| owner: (.+))?$"
)
LOG_FOOTER = "[project-brain check]"
SHOT_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".webm", ".mp4", ".mov", ".svg", ".pdf")
RUNS_KEEP_DAYS, RUNS_KEEP_FILES = 14, 200


def _reserved(part):
    return ntpath.isreserved(part) if hasattr(ntpath, "isreserved") else PureWindowsPath(part).is_reserved()


def is_link(path):
    """Include Windows junctions on Python 3.8+, before Path.is_junction existed."""
    try:
        info = Path(path).lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or (
        os.name == "nt" and info.st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT
    )


def public_path(root, name):
    """Refuse private, escaping or linked paths before anything is opened."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("relative path must be nonempty text")
    root = Path(root).absolute()
    parts = PureWindowsPath(name)
    if (
        parts.anchor
        or "\\" in name
        or ".." in parts.parts
        or ":" in name
        or any(part.endswith((".", " ")) or _reserved(part) for part in parts.parts)
        or PRIVATE.search(name)
        or any(ord(c) < 32 for c in name)
    ):
        raise ValueError("Private or escaping path refused: " + name)
    path = root / name
    for entry in (path, *path.parents):
        if is_link(entry):
            raise ValueError("Linked path refused: " + name)
        if entry == root:
            break
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_root != resolved_path and resolved_root not in resolved_path.parents:
        raise ValueError("Path escapes project: " + name)
    return path


class ContainmentError(RuntimeError):
    """Raised when process-tree termination cannot be verified."""


class ProcessTree:
    """Contain child processes and all descendants (Windows JobObject / POSIX session)."""

    def __init__(self, name=None, existing=False):
        self.name = name or "pb-" + uuid.uuid4().hex
        self.job = None
        self.proc = None
        if os.name != "nt":
            return
        from ctypes import wintypes as w

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        k = self.kernel
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
            "OpenJobObjectW": ([w.DWORD, w.BOOL, w.LPCWSTR], w.HANDLE),
            "SetInformationJobObject": ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
            "QueryInformationJobObject": (
                [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p],
                w.BOOL,
            ),
            "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
            "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
            "CloseHandle": ([w.HANDLE], w.BOOL),
            "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            "CreateToolhelp32Snapshot": ([w.DWORD, w.DWORD], w.HANDLE),
            "Thread32First": ([w.HANDLE, ctypes.c_void_p], w.BOOL),
            "Thread32Next": ([w.HANDLE, ctypes.c_void_p], w.BOOL),
            "OpenThread": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            "ResumeThread": ([w.HANDLE], w.DWORD),
        }
        for fname, (argtypes, restype) in signatures.items():
            fn = getattr(k, fname)
            fn.argtypes, fn.restype = argtypes, restype
        self.job = k.OpenJobObjectW(12, False, self.name) if existing else k.CreateJobObjectW(None, self.name)
        if not self.job:
            raise OSError("Owned process-tree containment unavailable")
        if not existing:

            class Basic(ctypes.Structure):
                _fields_ = [
                    ("user", ctypes.c_longlong),
                    ("job", ctypes.c_longlong),
                    ("flags", w.DWORD),
                    ("min_working", ctypes.c_size_t),
                    ("max_working", ctypes.c_size_t),
                    ("active", w.DWORD),
                    ("affinity", ctypes.c_size_t),
                    ("priority", w.DWORD),
                    ("scheduling", w.DWORD),
                ]

            class Extended(ctypes.Structure):
                _fields_ = [
                    ("basic", Basic),
                    ("io", ctypes.c_ulonglong * 6),
                    ("memory", ctypes.c_size_t * 4),
                ]

            limits = Extended()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                k.CloseHandle(self.job)
                self.job = None
                raise OSError("Cannot enforce process-tree containment")

    def spawn(self, argv, **kwargs):
        before_resume = kwargs.pop("before_resume", None)
        if os.name != "nt":
            self.proc = subprocess.Popen(argv, start_new_session=True, **kwargs)
            if before_resume:
                before_resume(self.proc)
            return self.proc
        from ctypes import wintypes as w

        k = self.kernel
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | 4  # CREATE_SUSPENDED
        self.proc = subprocess.Popen(argv, **kwargs)
        process = k.OpenProcess(0x1141, False, self.proc.pid)
        try:
            if not process or not k.AssignProcessToJobObject(self.job, process):
                raise OSError(ctypes.get_last_error(), "Cannot assign suspended process to owned job")
            if before_resume:
                before_resume(self.proc)

            class ThreadEntry(ctypes.Structure):
                _fields_ = [
                    ("size", w.DWORD),
                    ("usage", w.DWORD),
                    ("thread", w.DWORD),
                    ("owner", w.DWORD),
                    ("base", w.LONG),
                    ("delta", w.LONG),
                    ("flags", w.DWORD),
                ]

            snapshot = k.CreateToolhelp32Snapshot(4, 0)
            if snapshot == ctypes.c_void_p(-1).value:
                raise OSError("Cannot inspect suspended process thread")
            threads = []
            try:
                entry = ThreadEntry()
                entry.size = ctypes.sizeof(entry)
                more = k.Thread32First(snapshot, ctypes.byref(entry))
                while more:
                    if entry.owner == self.proc.pid:
                        threads.append(entry.thread)
                    more = k.Thread32Next(snapshot, ctypes.byref(entry))
            finally:
                k.CloseHandle(snapshot)
            if len(threads) != 1:
                raise OSError("Unexpected suspended process threads; refusing execution")
            thread = k.OpenThread(2, False, threads[0])
            try:
                if not thread or k.ResumeThread(thread) != 1:
                    raise OSError("Cannot resume contained process")
            finally:
                if thread:
                    k.CloseHandle(thread)
            return self.proc
        except BaseException:
            self.proc.kill()
            self.proc.wait(timeout=5)
            self.close()
            for pipe in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
                if pipe:
                    pipe.close()
            raise
        finally:
            if process:
                k.CloseHandle(process)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def close(self):
        try:
            self._close()
        except (OSError, RuntimeError) as error:
            raise ContainmentError("Owned process-tree termination is unverified") from error

    def _close(self):
        if os.name == "nt" and self.job:
            from ctypes import wintypes as w

            k = self.kernel
            if not k.TerminateJobObject(self.job, 1):
                raise OSError("Cannot terminate owned process tree")

            class Accounting(ctypes.Structure):
                _fields_ = [
                    ("times", ctypes.c_longlong * 4),
                    ("faults", w.DWORD),
                    ("total", w.DWORD),
                    ("active", w.DWORD),
                    ("terminated", w.DWORD),
                ]

            accounting = Accounting()
            for _ in range(50):
                if not k.QueryInformationJobObject(
                    self.job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None
                ):
                    raise OSError("Cannot verify owned process-tree termination")
                if accounting.active == 0:
                    k.CloseHandle(self.job)
                    self.job = None
                    return
                time.sleep(0.1)
            raise RuntimeError("Owned descendants remain; reconciliation required")
        elif os.name != "nt" and self.proc:
            import signal

            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.proc = None


def run_command(root, argv, log_path, timeout=900, input_bytes=None, strip_secrets=True, output_guard=None, extra_env=None):
    """Run one argv in a kill-on-close process tree; full output goes to log_path."""
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(s, str) or not s or "\x00" in s for s in argv)
    ):
        raise ValueError("Explicit nonempty argv list required; no shell text")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 3600:
        raise ValueError("Timeout must be in (0, 3600] seconds")
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")
    executable = argv[0]
    if os.path.dirname(executable):
        cand = root / executable
        if cand.exists():
            executable = str(cand)
    elif os.name == "nt":
        executable = shutil.which(executable) or executable
    if Path(executable).suffix.lower() in (".cmd", ".bat"):
        injected = [s for s in argv[1:] if BATCH_META.search(s)]
        if injected:
            raise ValueError(
                'Batch arguments must not contain & | < > ^ % ! " (cmd.exe injection): ' + injected[0]
            )
    env = (
        {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}
        if strip_secrets
        else dict(os.environ)
    )
    if extra_env:
        if set(extra_env) - {"PB_SESSION_ID"}:
            raise ValueError("Only PB_SESSION_ID may be explicitly inherited")
        env.update(extra_env)
    cache = tempfile.mkdtemp(prefix="pb-pycache-")
    env["PYTHONPYCACHEPREFIX"] = cache
    started = time.monotonic()
    tree = ProcessTree()
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    exceeded = False
    with tempfile.TemporaryFile(mode="w+b") as log, (
        tempfile.TemporaryFile() if input_bytes is not None else nullcontext()
    ) as input_stream:
        proc, timed_out = None, False
        try:
            try:
                if input_stream is not None:
                    input_stream.write(input_bytes)
                    input_stream.seek(0)
                proc = tree.spawn(
                    [executable, *argv[1:]],
                    cwd=str(root),
                    env=env,
                    stdin=input_stream if input_stream is not None else subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                try:
                    deadline = time.monotonic() + timeout
                    while proc.poll() is None:
                        if os.fstat(log.fileno()).st_size > 4 * 1024 * 1024:
                            exceeded = True
                            break
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            timed_out = True
                            break
                        try:
                            proc.wait(timeout=min(0.2, remaining))
                        except subprocess.TimeoutExpired:
                            pass
                except subprocess.TimeoutExpired:
                    timed_out = True
            finally:
                tree.close()
                if proc is not None:
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        pass
        finally:
            if cache:
                shutil.rmtree(cache, ignore_errors=True)
        import runtime_security as S
        log.seek(0)
        raw = log.read(4 * 1024 * 1024 + 1)
        exceeded = exceeded or len(raw) > 4 * 1024 * 1024
        blocked = False
        if output_guard is not None:
            try:
                output_guard(raw)
            except ValueError:
                blocked = True
        safe = "[output withheld: scanner rejected output]\n" if blocked else S.sanitize(raw[:4 * 1024 * 1024].decode("utf-8", errors="replace"))
        if exceeded:
            safe += "\n[output limit exceeded; result is not PASS]\n"
        with open(log_path, "w", encoding="utf-8", newline="\n") as final_log:
            final_log.write(safe)
    return {
        "exit_code": 125 if exceeded or blocked else 124 if timed_out else (proc.returncode if proc is not None else 1),
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - started, 3),
        "containment": "Windows JobObject" if os.name == "nt" else "POSIX process group",
    }


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def command_argv(command):
    """Parse Verify text using the platform's native argument quoting rules."""
    if os.name != "nt":
        return shlex.split(command)
    from ctypes import wintypes as w

    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [w.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(w.LPWSTR)
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [ctypes.c_void_p], ctypes.c_void_p
    count = ctypes.c_int()
    args = shell.CommandLineToArgvW(command.strip(), ctypes.byref(count))
    if not args:
        raise ValueError("Invalid Verify command")
    try:
        return [args[i] for i in range(count.value)]
    finally:
        kernel.LocalFree(args)


def digest(B, root, areas):
    """Content digest of every tracked/untracked public file matched by Areas (CRLF hashed as LF)."""
    if not areas:
        raise ValueError("Task has no Areas; evidence cannot be bound to source")
    root = Path(root)
    has_git = B.git(root, "rev-parse", "--is-inside-work-tree") == "true"
    files = sorted(
        f
        for f in B.repo_files(root, has_git)
        if any(B.matches(f, a) for a in areas) and not PRIVATE.search(f) and (root / f).is_file()
    )
    if not files:
        raise ValueError("Areas match no files: " + ", ".join(areas))
    return B.areas_digest([(f, public_path(root, f).read_bytes()) for f in files]), len(files)


def task_digest(B, root, task):
    import runtime_protocol as R
    return R.task_digest(B, root, task)


def prune_runs(B, root):
    """Keep .project-brain/.cache/runs/ bounded while preserving logs cited by open tasks."""
    runs = public_path(root, B.BRAIN_DIR + "/.cache/runs")
    if not runs.is_dir():
        return
    cited = set()
    for t in B.list_tasks(root):
        latest = {}
        for line in t.get("evidence_lines", []):
            match = CHECK_RE.match(line)
            if match:
                latest[match.group("cmd")] = match
        cited.update(m.group("log").split("/")[-1] for m in latest.values())
    logs = sorted((p for p in runs.glob("*.log") if p.name not in cited), key=lambda p: p.stat().st_mtime)
    cutoff = datetime.now(timezone.utc).timestamp() - RUNS_KEEP_DAYS * 86400
    for n, path in enumerate(logs):
        if path.stat().st_mtime < cutoff or len(logs) - n > RUNS_KEEP_FILES:
            try:
                path.unlink()
            except OSError:
                pass


def compact_machine_records(B, task, value=None, contract=None):
    """Keep current proofs and latest checks; retain ownership/user feedback/history notes."""
    lines = task.get("evidence_lines", [])
    latest = {}
    for index, line in enumerate(lines):
        match = CHECK_RE.match(line)
        if match:
            latest[match.group("cmd")] = index
    keep = set(latest[cmd] for cmd in task.get("verify_cmds", []) if cmd in latest)
    compact = []
    for index, line in enumerate(lines):
        check = CHECK_RE.match(line)
        typed = EVIDENCE_RE.match(line)
        if check and index not in keep:
            continue
        if (typed and value and contract and typed.group("kind") != "user_feedback"
                and (typed.group("digest") != value or typed.group("contract") != contract)):
            continue
        compact.append(line)
    text = B.read(task["file"]) or ""
    if compact != lines:
        replacement = "## Evidence\n" + "\n".join(compact) + "\n\n"
        text = re.sub(r"^## Evidence\s*\n.*?(?=^## |\Z)", lambda _: replacement, text, count=1, flags=re.M | re.S)
        B.write_atomic(task["file"], text)


def _log_path(B, root, task_id, n):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runs = public_path(root, B.BRAIN_DIR + "/.cache/runs")
    runs.mkdir(parents=True, exist_ok=True)
    prune_runs(B, root)
    suffix = 1
    while True:
        name = f"{task_id}-{stamp}-{n}{'' if suffix == 1 else f'-{suffix}'}.log"
        path = runs / name
        try:
            os.close(os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return path, f".cache/runs/{name}"
        except FileExistsError:
            suffix += 1


def latest_review(lines):
    block = None
    for line in lines:
        m = REVIEW_RE.match(line)
        if m:
            block = {
                "reviewer": m.group(1),
                "verdict": m.group(2),
                "digest": m.group(3),
                "contract": m.group(4),
                "findings": [],
            }
        elif block:
            f = FINDING_RE.match(line)
            if f:
                block["findings"].append(f.groups())
    return block


def implementers(B, task):
    """Everyone who started (owned) the task; none of them may review it."""
    owners = {r["owner"] for r in B.start_records(task)}
    if task.get("owner"):
        owners.add(task["owner"])
    return owners


def effective_risk(B, task):
    """Risk covers the current scope and never drops below any recorded `start`."""
    import runtime_agents

    order = {r: i for i, r in enumerate(B.RISK_VALUES)}
    risks = [runtime_agents.score_task(B, None, task)["effective_risk"]] + [r["risk"] for r in B.start_records(task)]
    valid = [r for r in risks if r in order]
    return max(valid, key=lambda r: order[r]) if valid else (task.get("risk") or "MEDIUM")


def _actor(B, task, actor, anyone_on_review=False):
    actor = B.agent_id(actor, "--as")
    if task["status"] == "REVIEW" and anyone_on_review:
        return actor
    allowed = {task.get("owner", "")}
    if task["status"] in ("IN_PROGRESS", "REVIEW"):
        rev = latest_review(task.get("review_lines", []))
        if rev:
            allowed.add(rev["reviewer"])
    if not task.get("owner") or actor not in allowed:
        raise ValueError(
            f"{task['id']} is owned by {task.get('owner') or 'nobody'}: `start` it "
            '(with --takeover "<reason>" if that owner stopped) before acting on it'
        )
    return actor


def check(B, root, task_id, timeout=None, actor="", rerun=False):
    task = B.find_task(root, task_id)
    if task["status"] not in ("IN_PROGRESS", "REVIEW"):
        return 2, [f"FAIL {task['id']} is {task['status']}: `start` it first"]
    if any(e["state"] in ("sent", "response_unknown") for e in task.get("external", [])):
        return 2, [f"FAIL {task['id']}: external operation unresolved; readback first before `check`"]
    actor = _actor(B, task, actor or task.get("owner", ""), anyone_on_review=True)
    if not task["verify_cmds"]:
        return 2, [f"FAIL {task['id']} has no backticked Verify command"]
    cfg = B.parse_config(root) if (B.bp(root) / "config.yaml").exists() else {}
    timeout = timeout or float(cfg.get("check_timeout", 900) or 900)
    import runtime_protocol as R
    import runtime_security as S
    R.guard(B, root, task)
    before, count = task_digest(B, root, task)
    contract = B.contract(task)
    if R.enabled(B, root) and not rerun and current_checks(B, root, task, before, contract):
        return 0, [f"PASS CACHED: {task['id']} current inputs/environment/spec and intact logs; no commands repeated"]
    R.attempt_guard(B, root, task)
    results = []
    for n, cmd in enumerate(task["verify_cmds"], 1):
        path, log_rel = _log_path(B, root, task["id"], n)
        remaining = R.remaining_seconds(B, root, task, sum(r["duration_seconds"] for _, r, _, _ in results))
        if remaining is not None and remaining <= 0:
            B.write_atomic(path, "Explicit check execution budget reached; command not launched")
            result = {"exit_code": 125, "duration_seconds": 0}
        else:
            result = run_command(root, S.command(B, root, task, cmd), path,
                                 min(timeout, remaining) if remaining is not None else timeout,
                                 output_guard=lambda raw: S.scan_output(B, root, task, raw))
        results.append((cmd, result, path, log_rel))
    after, _ = task_digest(B, root, task)
    out = []
    for cmd, r, path, log_rel in results:
        ok = r["exit_code"] == 0 and before == after
        with open(path, "a", encoding="utf-8", newline="\n") as stream:
            stream.write(
                f"\n{LOG_FOOTER} {'PASS' if ok else 'FAIL'} exit={r['exit_code']} "
                f"digest={after} contract={contract}\n"
            )
        line = (
            f"- [machine] check `{cmd}` | {'PASS' if ok else 'FAIL'} | exit={r['exit_code']} | "
            f"{r['duration_seconds']}s | by={actor} | digest={after} | contract={contract} | "
            f"log={log_rel}@{_hash(path)}"
        )
        B.append_section(task["file"], "Evidence", line)
        out.append(line[2:])
    if before != after:
        out.append("! Areas changed while checks ran; results are FAIL. Rerun on stable source.")
    passed = all(r["exit_code"] == 0 for _, r, _, _ in results) and before == after
    out.append(f"{'PASS' if passed else 'FAIL'}: {len(results)} command(s) on {count} file(s) in Areas")
    if R.enabled(B, root):
        compact_machine_records(B, B.find_task(root, task["id"]), after, contract)
        R.account_check(B, root, task, sum(r["duration_seconds"] for _, r, _, _ in results))
        R.progress(B, root, task, "Tick proven criteria, verify remaining behavior, then review and accept" if passed else "Inspect the failed check; change approach before repeating",
                   failing="" if passed else "Verify failed: " + ",".join(str(r["exit_code"]) for _, r, _, _ in results), strategy="check")
    return (0 if passed else 1), out


def evidence(B, root, task_id, kind, note, files=(), actor="", criteria=()):
    task = B.find_task(root, task_id)
    actor = _actor(B, task, actor)
    import runtime_security as S
    import runtime_protocol as R
    R.guard(B, root, task)
    S.require_clean(note, "evidence note")
    if kind not in B.KINDS or kind == "machine":
        raise ValueError(
            "Kind must be one of "
            + ", ".join(k for k in B.KINDS if k != "machine")
            + "; machine evidence comes only from `check`"
        )
    if not note.strip() or "|" in note or any(ord(c) < 32 for c in note):
        raise ValueError('Note must be one nonempty line without "|"')
    same_kind = [i["id"] for i in task["items"] if i["kind"] == kind]
    criteria = [c.strip().lower() for c in criteria if c.strip()] or (same_kind if len(same_kind) == 1 else [])
    if not criteria:
        known = ", ".join(same_kind) or f"no [{kind}] item in {task['id']}"
        raise ValueError(
            f"Name the Acceptance item(s) this observation proves: --criterion <id> "
            f"({known}; ids are shown by `boot`)"
        )
    wrong = [c for c in criteria if c not in same_kind]
    if wrong:
        raise ValueError(
            f"criterion {', '.join(wrong)} is no [{kind}] Acceptance item of {task['id']} "
            f"(its [{kind}] items: {', '.join(same_kind) or 'none'})"
        )
    if kind == "visual" and not any(name.lower().endswith(SHOT_SUFFIXES) for name in files):
        raise ValueError(
            "Visual evidence needs the rendered result: --file <screenshot or recording>; "
            "reading source is not visual acceptance"
        )
    if kind == "interaction" and not files and note.count("->") < 2:
        raise ValueError(
            "Interaction evidence needs what was really done: --file <recording or trace>, or a "
            'note listing the steps and the result as "step -> step -> result"'
        )
    hashed = []
    for name in files:
        path = public_path(root, name)
        if not path.is_file():
            raise ValueError("Evidence file missing: " + name)
        if path.suffix.lower() not in SHOT_SUFFIXES:
            S.scan_artifacts(B, root, [name])
        hashed.append(f"{name}@{_hash(path)}")
    value, _ = task_digest(B, root, task)
    line = (
        f"- [{kind}] {note.strip()} | criterion={','.join(criteria)}"
        + (f" | files={','.join(hashed)}" if hashed else "")
        + f" | by={actor} | digest={value} | contract={B.contract(task)}"
    )
    B.append_section(task["file"], "Evidence", line)
    return 0, [line[2:]]


def review(B, root, task_id, reviewer, verdict, findings=(), agents_path=None, self_review=False):
    import runtime_agents

    task = B.find_task(root, task_id)
    reviewer = B.agent_id(reviewer, "--reviewer")
    import runtime_protocol as R
    import runtime_security as S
    R.guard(B, root, task)
    for finding in findings:
        S.require_clean(finding, "review finding")
    if task["status"] not in ("IN_PROGRESS", "REVIEW"):
        return 2, [f"FAIL {task['id']} is {task['status']}; nothing to review"]
    modes = B.get_session_modes(root) if hasattr(B, "get_session_modes") else {"rev": ""}
    if self_review and modes.get("rev") != "solo":
        raise ValueError("--self-review requires the upfront REV mode SOLO")
    allow_self = modes.get("rev") == "solo"
    imps = implementers(B, task)
    identity = runtime_agents.canonical_identity(reviewer, agents_path)
    if not task.get("owner") or (not allow_self and any(
        identity == runtime_agents.canonical_identity(imp, agents_path) for imp in imps
    )):
        return 2, [
            f"FAIL reviewer must be named and must not have implemented {task['id']} "
            f"({', '.join(sorted(imps)) or 'no Owner'}); a session never reviews its own work (unless REV mode is solo / --self-review)"
        ]
    if verdict not in ("PASS", "BLOCKED"):
        raise ValueError("Verdict must be PASS or BLOCKED")
    if not allow_self:
        if R.enabled(B, root):
            registry = runtime_agents.registry_path(agents_path)
            models = runtime_agents.load(registry).get("models", {}) if registry.exists() else {}
            if reviewer not in models:
                raise ValueError("REVIEW_PROVENANCE_PENDING: independent reviewer must be registered; a different alias alone is not evidence")
        runtime_agents.gate(B, task, reviewer, "review", agents_path, root=root)
    for f in findings:
        if any(ord(c) < 32 for c in f):
            raise ValueError("Finding must be one line without control characters")
        m = FINDING_RE.match("- finding " + f.strip())
        if not m:
            raise ValueError(
                'Finding must be "BLOCKER|MAJOR|QUALITY|MINOR: text" with optional '
                '" | accepted: reason | owner: user|PB-NNN" (QUALITY: owner user only)'
            )
        owner = (m.group(4) or "").strip()
        if owner and not (
            owner == "user"
            or (
                m.group(1) == "MINOR"
                and re.fullmatch(r"PB-\d{3,}", owner)
                and (B.bp(root) / "tasks" / (owner + ".md")).is_file()
            )
        ):
            raise ValueError(
                'Accepted MINOR owner must be "user" or an open follow-up task PB-NNN; '
                "an accepted QUALITY gap is owned by the user only"
            )
    value, _ = task_digest(B, root, task)
    lines = [f"- review by {reviewer} | {verdict} | digest={value} | contract={B.contract(task)}"] + [
        f"- finding {f.strip()}" for f in findings
    ]
    for line in lines:
        B.append_section(task["file"], "Review", line)
    if task["status"] == "IN_PROGRESS":
        B.set_header(task["file"], "Status", "REVIEW")
    if R.enabled(B, root):
        assurance = R.provenance(B, root, task, reviewer, allow_self, agents_path)
        lines.append("- assurance: " + assurance["assurance"])
    return 0, [line[2:] for line in lines]


def _file_matches(root, ref):
    name, _, short = ref.strip().rpartition("@")
    try:
        path = public_path(root, name)
        return path.is_file() and _hash(path) == short
    except ValueError:
        return False


def check_log_valid(B, root, match):
    try:
        log = public_path(root, B.BRAIN_DIR + "/" + match.group("log"))
        footer = (f"{LOG_FOOTER} {match.group('result')} exit={match.group('exit')} "
                  f"digest={match.group('digest')} contract={match.group('contract')}")
        return (log.is_file() and _hash(log) == match.group("hash")
                and log.read_text(encoding="utf-8", errors="replace").rstrip().endswith(footer))
    except (ValueError, OSError):
        return False


def current_checks(B, root, task, value, contract):
    latest = {}
    for line in task.get("evidence_lines", []):
        match = CHECK_RE.match(line)
        if match:
            latest[match.group("cmd")] = match
    return bool(task.get("verify_cmds")) and all(
        cmd in latest and latest[cmd].group("result") == "PASS"
        and latest[cmd].group("exit") == "0"
        and latest[cmd].group("digest") == value
        and latest[cmd].group("contract") == contract
        and check_log_valid(B, root, latest[cmd]) for cmd in task["verify_cmds"]
    )


def current_criteria(task, root, value, contract):
    proven = set()
    for item in task.get("items", []):
        if item["kind"] == "machine":
            continue
        for line in task.get("evidence_lines", []):
            match = EVIDENCE_RE.match(line)
            if (match and match.group("kind") == item["kind"]
                    and match.group("digest") == value and match.group("contract") == contract
                    and item["id"] in match.group("criteria").split(",")
                    and all(_file_matches(root, ref) for ref in (match.group("files") or "").split(",") if ref.strip())):
                proven.add(item["id"])
                break
    return proven


def accept(B, root, task_id, actor="", agents_path=None, self_review=False):
    task = B.find_task(root, task_id)
    if task["status"] not in ("IN_PROGRESS", "REVIEW"):
        return 2, [f"FAIL {task['id']} is {task['status']}: only IN_PROGRESS or REVIEW tasks are accepted"]
    _actor(B, task, actor or task.get("owner", ""))
    import runtime_protocol as R
    R.guard(B, root, task)
    if R.enabled(B, root):
        import runtime_security as S
        S.require_clean(B.read(task["file"]) or "", "task export")
        if B.git(root, "rev-parse", "--is-inside-work-tree") == "true":
            S.scan_staged(B, root)
    modes = B.get_session_modes(root) if hasattr(B, "get_session_modes") else {"rev": ""}
    if self_review and modes.get("rev") != "solo":
        raise ValueError("--self-review requires the upfront REV mode SOLO")
    allow_self = modes.get("rev") == "solo"
    import runtime_agents

    runtime_agents.gate(B, task, actor or task.get("owner", ""), "accept", agents_path, root=root)
    if not task.get("owner"):
        return 2, [f"FAIL {task['id']} has no Owner; `start` records who implemented it"]
    errors = B.task_errors(task)
    if errors:
        return 2, [f"BLOCKED {task['id']}"] + [f"  - {e}" for e in errors]
    current, _ = task_digest(B, root, task)
    contract = B.contract(task)
    risk = effective_risk(B, task)
    problems, missing = [], []
    if risk == "HIGH":
        cfg = B.parse_config(root) if (B.bp(root) / "config.yaml").exists() else {}
        full_test = cfg.get("commands", {}).get("test", "").strip()
        if full_test and full_test not in task["verify_cmds"]:
            missing.append(f"HIGH risk requires the configured full test command in Verify: `{full_test}`")
    for item in task["items"]:
        if not item["done"]:
            missing.append(f"open acceptance: [{item['kind']}] {item['text'][:70]} (criterion {item['id']})")
    latest = {}
    for line in task.get("evidence_lines", []):
        m = CHECK_RE.match(line)
        if m:
            latest[m.group("cmd")] = m
    for cmd in task["verify_cmds"]:
        m = latest.get(cmd)
        if m is None or m.group("digest") != current or m.group("contract") != contract:
            missing.append(f"no check on current source and spec for `{cmd}` (run `check`)")
        else:
            log = public_path(root, B.BRAIN_DIR + "/" + m.group("log"))
            if not log.is_file():
                missing.append(f"log of the latest `{cmd}` check is not in this checkout: run `check`")
            elif not check_log_valid(B, root, m):
                problems.append(f"`{cmd}` check line does not match its log: evidence is written only by `check`")
            elif m.group("result") == "FAIL":
                problems.append(f"latest check failed: `{cmd}`")
    for item in task["items"]:
        if not item["done"] or item["kind"] == "machine":
            continue
        found = [
            m
            for line in task.get("evidence_lines", [])
            if (m := EVIDENCE_RE.match(line))
            and m.group("kind") == item["kind"]
            and m.group("digest") == current
            and m.group("contract") == contract
            and item["id"] in m.group("criteria").split(",")
        ]
        if not found:
            missing.append(
                f"no evidence for criterion {item['id']} ([{item['kind']}] {item['text'][:60]}) on "
                f"current source and spec: `evidence --kind {item['kind']} --criterion {item['id']}`"
            )
        elif not any(
            all(_file_matches(root, ref) for ref in (m.group("files") or "").split(",") if ref.strip())
            for m in found
        ):
            problems.append(f"criterion {item['id']} evidence file changed since it was observed")
    for e in task.get("external", []):
        if e["state"] in ("sent", "response_unknown"):
            missing.append(f"external operation unresolved: {e['op'] or e['line']} -> readback first")
    rev = latest_review(task.get("review_lines", []))
    if risk in ("MEDIUM", "HIGH"):
        if rev is None or rev["digest"] != current or rev["contract"] != contract:
            missing.append(
                f"independent review on current source and spec required ({risk} risk)"
                if not allow_self else
                "explicit SOLO review required on current source and spec: run `review --self-review` after the audit"
            )
        else:
            if R.enabled(B, root):
                try:
                    R.review_guard(B, root, task, rev, allow_self, agents_path)
                except ValueError as error:
                    problems.append("review provenance: " + str(error))
            if not allow_self:
                try:
                    runtime_agents.gate(B, task, rev["reviewer"], "review", agents_path, root=root)
                except ValueError as error:
                    problems.append("reviewer policy: " + str(error))
                identity = runtime_agents.canonical_identity(rev["reviewer"], agents_path)
                if any(identity == runtime_agents.canonical_identity(imp, agents_path) for imp in implementers(B, task)):
                    problems.append(f"reviewer {rev['reviewer']} implemented this task")
            if rev["verdict"] != "PASS":
                problems.append("review verdict BLOCKED")
            for severity, text_, reason, owner in rev["findings"]:
                accepted = (
                    (severity == "MINOR" and reason and owner)
                    or (severity == "QUALITY" and reason and (owner or "").strip() == "user")
                )
                if not accepted:
                    problems.append(f"unresolved finding {severity}: {text_[:60]}")
    if problems:
        return 2, [f"BLOCKED {task['id']}"] + [f"  - {p}" for p in problems + missing]
    user_items = [i["text"] for i in task["items"] if not i["done"] and i["kind"] == "user_feedback"]
    rest = [m for m in missing if not m.startswith(("open acceptance: [user_feedback]", "independent review", "explicit SOLO review"))]
    if user_items and not rest:
        B.set_headers(
            task["file"],
            {
                "Status": "BLOCKED",
                "Blocked": "user feedback: " + user_items[0][:120],
                "Owner": "",
            },
        )
        return 1, [
            f"WAITING_USER {task['id']}: everything else is current; BLOCKED with an empty Owner so other "
            "work can start. When the user answers: `start`, `evidence --kind user_feedback`, tick the "
            "item, `accept`. Whoever started it may not review it."
        ]
    review_only = missing and all(m.startswith(("independent review", "explicit SOLO review")) for m in missing)
    if review_only:
        if task["status"] != "REVIEW":
            B.set_header(task["file"], "Status", "REVIEW")
        return 1, [
            f"REVIEW_PENDING {task['id']}: implementation evidence is current; a different, stronger agent "
            f"that did not implement it runs `review {task['id']}` then `accept` (SOLO: explicitly run `review --self-review` after the audit). Commit now with PB-WIP: true if you stop here."
        ]
    if missing:
        return 1, [f"UNVERIFIED {task['id']}"] + [f"  - {m}" for m in missing]
    B.set_header(task["file"], "Status", "DONE")
    B.append_section(task["file"], "Evidence", f"- accept: DONE | digest={current} | contract={contract}")
    ver_map = {"LOW": "local", "MEDIUM": "domain", "HIGH": "global"}
    trailers = [
        f"PB-Task: {task['id']}",
        f"PB-Verification: {ver_map.get(risk, 'domain')}",
        f"PB-Agent: {task['owner']}",
    ] + ([f"PB-Reviewer: {rev['reviewer']}"] if rev else [])
    return (
        0,
        [f"DONE {task['id']}", "Commit code + this task file with these trailers (blank line before them):"]
        + [f"  {t}" for t in trailers]
        + [
            "Add PB-Current-Checkpoint: <domains> if you reconciled current.md. After the commit succeeds, "
            "delete the task file in the next commit (or delete it in the same commit with the trailers above)."
        ],
    )
