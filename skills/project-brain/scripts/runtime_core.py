"""Acyclic low-level primitives for Project Brain. Python 3.8+, standard library only.

This module has ZERO internal Project Brain imports so every higher-level runtime
module can share crash-safe atomic I/O, OS-released file locks, bounded JSON
parsing, Python 3.8-safe UTC timestamps, path containment, secret-scrubbed Git
execution, and ProcessTree containment without circular dependencies.
"""

from contextlib import contextmanager
import ctypes
from datetime import datetime, timedelta, timezone
import hashlib
import json
import ntpath
import os
from pathlib import Path, PureWindowsPath
import re
import shlex
import stat
import subprocess
import tempfile
import threading
import time
import uuid

_LOCK_TLS = threading.local()

VERSION = "4.0.2"
SCHEMA = 4
BRAIN_DIR = ".project-brain"
LEGACY_FILE = "PROJECT_BRAIN.md"

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
BATCH_META = re.compile(r'[&|<>^%!"()\r\n]')
_ISO_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})"
    r"(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$"
)


def now_iso():
    """Return current UTC timestamp in canonical ISO-8601 Z format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_utc(value):
    """Parse ISO-8601 UTC/offset timestamps safely on Python 3.8 through 3.13+.

    Python 3.8-3.10 datetime.fromisoformat rejects 'Z' and non-3/6-digit
    fractional seconds; this parser handles 0..9 fractional digits consistently.
    Returns POSIX epoch seconds (float) or raises ValueError.
    """
    if not isinstance(value, str):
        raise ValueError("Timestamp must be text")
    m = _ISO_RE.fullmatch(value.strip())
    if not m:
        raise ValueError("Invalid ISO-8601 timestamp")
    year, month, day, hour, minute, second = (int(m.group(i)) for i in range(1, 7))
    frac = m.group(7) or ""
    micro = int((frac + "000000")[:6])
    tz_raw = m.group(8)
    if not tz_raw or tz_raw == "Z":
        tz = timezone.utc
    else:
        sign = 1 if tz_raw[0] == "+" else -1
        digits = tz_raw[1:].replace(":", "")
        off_h, off_m = int(digits[:2]), int(digits[2:4])
        if off_h > 23 or off_m > 59:
            raise ValueError("Invalid timezone offset")
        tz = timezone(timedelta(minutes=sign * (off_h * 60 + off_m)))
    dt = datetime(year, month, day, hour, minute, second, micro, tzinfo=tz)
    return dt.timestamp()


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()[:16]


def norm_key(value):
    s = re.sub(r"[^a-z0-9.+-]+", "-", str(value or "").strip().lower()).strip("-")
    for prefix in ("openai-", "anthropic-", "google-", "opencode-", "alibaba-", "moonshot-"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s


def worker_env_active():
    return bool(os.environ.get("CLI_AGENT_POOL_WORKER"))


def clean_env(extra=None, keep_task_token=False):
    """Return environment with secrets scrubbed for child processes."""
    env = {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}
    if keep_task_token and os.environ.get("CLI_AGENT_POOL_TASK_TOKEN"):
        env["CLI_AGENT_POOL_TASK_TOKEN"] = os.environ["CLI_AGENT_POOL_TASK_TOKEN"]
    if extra:
        env.update(extra)
    return env


def run_git(root, *args, timeout=60, env=None, check=False):
    """Run git with secret-scrubbed env, DEVNULL stdin, and CREATE_NO_WINDOW."""
    proc_env = clean_env(env if isinstance(env, dict) else None)
    kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "stdin": subprocess.DEVNULL,
        "env": proc_env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        res = subprocess.run(["git", "-C", str(root), *args], **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        if check:
            raise ValueError("git %s failed: %s" % (args[0] if args else "", exc)) from exc
        return None
    if res.returncode != 0:
        if check:
            raise ValueError((res.stderr or res.stdout or "git failed").strip())
        return None
    return res.stdout.rstrip()


def _replace_with_retry(src, dst):
    """Atomic os.replace with bounded retry for transient Windows PermissionError."""
    attempts = 10 if os.name == "nt" else 1
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt + 1 >= attempts:
                raise
            time.sleep(0.02 * (attempt + 1))


def write_atomic_bytes(path, raw):
    """Crash-safe atomic binary replacement with fsync and BaseException cleanup."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        try:
            stream = os.fdopen(fd, "wb")
        except BaseException:
            os.close(fd)
            raise
        with stream as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        _replace_with_retry(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_atomic(path, content):
    """Crash-safe LF-normalized atomic UTF-8 text replacement."""
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    write_atomic_bytes(path, text.encode("utf-8"))


def _reserved(part):
    return ntpath.isreserved(part) if hasattr(ntpath, "isreserved") else PureWindowsPath(part).is_reserved()


def is_link(path):
    """Detect symlinks and Windows junctions safely on Python 3.8+."""
    try:
        info = Path(path).lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    if os.name == "nt":
        tag = getattr(info, "st_reparse_tag", 0)
        return tag == getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003) or (
            tag == getattr(stat, "IO_REPARSE_TAG_SYMLINK", 0xA000000C)
        )
    return False


def public_path(root, name):
    """Refuse private, escaping, dot-only, or linked paths before anything is opened."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("relative path must be nonempty text")
    root = Path(root).absolute()
    parts = PureWindowsPath(name)
    if (
        not parts.parts
        or parts.anchor
        or "\\" in name
        or ".." in parts.parts
        or "." in parts.parts
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


def safe_private_path(path, stop_at=None):
    """Refuse linked private state paths without breaking OS-level temp symlinks."""
    path = Path(path).absolute()
    stop = Path(stop_at).absolute() if stop_at is not None else None
    stop_res = stop.resolve() if stop is not None else None
    for entry in (path, *path.parents):
        if is_link(entry):
            raise ValueError("Linked private state refused: " + str(entry))
        if stop is not None and (entry == stop or entry.resolve() == stop_res):
            break
    return path


def iter_files(root, skip_dirs=()):
    """Walk files under root without descending into symlinks or Windows NTFS junctions."""
    root = Path(root)
    if not root.is_dir() or is_link(root):
        return []
    skip = set(skip_dirs)
    found = []
    for dp, dns, fns in os.walk(str(root), topdown=True, followlinks=False):
        base = Path(dp)
        dns[:] = sorted(d for d in dns if d not in skip and not is_link(base / d))
        for fn in sorted(fns):
            p = base / fn
            if not is_link(p):
                found.append(p)
    return found


def _unique_pairs(items):
    out = {}
    for key, val in items:
        if key in out:
            raise ValueError("Duplicate JSON key: " + str(key))
        out[key] = val
    return out


def _reject_constant(token):
    raise ValueError("Non-finite JSON constant refused: " + str(token))


def read_json(path, max_bytes=1024 * 1024, strict_constants=True, unique_keys=False, expect_dict=True):
    """Bounded, strict JSON reader. Returns {} when missing and expect_dict=True, else None."""
    path = Path(path)
    if not path.exists():
        return {} if expect_dict else None
    if not path.is_file():
        raise ValueError("JSON path is not a regular file: " + str(path.name))
    with path.open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("JSON file exceeds %d byte limit" % max_bytes)
    kwargs = {}
    if strict_constants:
        kwargs["parse_constant"] = _reject_constant
    if unique_keys:
        kwargs["object_pairs_hook"] = _unique_pairs
    try:
        data = json.loads(raw.decode("utf-8"), **kwargs)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Malformed JSON in %s: %s" % (path.name, exc)) from exc
    if expect_dict and not isinstance(data, dict):
        raise ValueError("JSON root must be an object: " + path.name)
    return data


def _tls_map(attr):
    mapping = getattr(_LOCK_TLS, attr, None)
    if mapping is None:
        mapping = {}
        setattr(_LOCK_TLS, attr, mapping)
    return mapping


@contextmanager
def file_lock(lock_file, timeout=15.0):
    """OS-released exclusive file lock (thread-reentrant); never unlinks the inode."""
    lock_file = Path(lock_file)
    if is_link(lock_file):
        raise ValueError("Linked lock file refused")
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    key = os.path.normcase(str(lock_file.resolve()))
    held = _tls_map("file_locks")
    if held.get(key, 0) > 0:
        held[key] += 1
        try:
            yield
        finally:
            held[key] -= 1
        return
    deadline = time.monotonic() + timeout
    with lock_file.open("a+b") as stream:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ValueError(
                        f"Timed out waiting for {lock_file}; another Project Brain command may be running"
                    )
                time.sleep(0.05)
        held[key] = 1
        try:
            yield
        finally:
            held.pop(key, None)
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def state_root():
    """Machine-local Project Brain state directory (outside project repos)."""
    env = os.environ.get("PB_AGENTS_REGISTRY")
    if env:
        return Path(env).parent
    return Path.home() / BRAIN_DIR


@contextmanager
def project_lock(root, timeout=15.0, name="writer.lock"):
    """Project-scoped OS lock (thread-reentrant); serializes even before .project-brain/ exists."""
    root = Path(root).absolute()
    proj_key = (os.path.normcase(str(root.resolve())), name)
    proj_held = _tls_map("project_locks")
    if proj_held.get(proj_key, 0) > 0:
        proj_held[proj_key] += 1
        try:
            yield
        finally:
            proj_held[proj_key] -= 1
        return
    brain_dir = root / BRAIN_DIR
    if brain_dir.is_dir() and not is_link(brain_dir):
        cache = public_path(root, BRAIN_DIR + "/.cache")
        cache.mkdir(parents=True, exist_ok=True)
        lock_file = public_path(root, BRAIN_DIR + "/.cache/" + name)
    else:
        key = hashlib.sha256(os.path.normcase(str(root.resolve())).encode("utf-8")).hexdigest()[:24]
        base = state_root() / "project-locks"
        lock_file = safe_private_path(base / (key + "-" + name), stop_at=state_root())
    with file_lock(lock_file, timeout=timeout):
        proj_held[proj_key] = 1
        try:
            yield
        finally:
            proj_held.pop(proj_key, None)


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
            job = self.job
            try:
                if not k.TerminateJobObject(job, 1):
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
                        job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None
                    ):
                        raise OSError("Cannot verify owned process-tree termination")
                    if accounting.active == 0:
                        return
                    time.sleep(0.1)
                raise RuntimeError("Owned descendants remain; reconciliation required")
            finally:
                k.CloseHandle(job)
                self.job = None
        elif os.name != "nt" and self.proc:
            import signal

            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            finally:
                self.proc = None


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
