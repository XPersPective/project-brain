#!/usr/bin/env python3
"""Evidence, verification, process containment and acceptance for Project Brain 4.0.

Stdlib only, Python 3.8+. Strictly acyclic: imports runtime_core, runtime_security,
runtime_actors, and runtime_protocol.
"""

from contextlib import nullcontext
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

import runtime_actors as A
import runtime_core as Core
import runtime_protocol as R
import runtime_security as S

# Re-export core primitives for backward compatibility with callers and tests.
PRIVATE = Core.PRIVATE
SECRET_ENV = Core.SECRET_ENV
BATCH_META = Core.BATCH_META
ContainmentError = Core.ContainmentError
ProcessTree = Core.ProcessTree
is_link = Core.is_link
public_path = Core.public_path
command_argv = Core.command_argv
digest = R.digest
check_log_valid = R.check_log_valid
current_checks = R.current_checks
CHECK_RE = R.CHECK_RE
EVIDENCE_RE = R.EVIDENCE_RE
REVIEW_RE = R.REVIEW_RE
FINDING_RE = R.FINDING_RE
LOG_FOOTER = R.LOG_FOOTER

BINARY_SHOT_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".webm", ".mp4", ".mov", ".pdf")
SHOT_SUFFIXES = BINARY_SHOT_SUFFIXES + (".svg",)
RUNS_KEEP_DAYS, RUNS_KEEP_FILES = 14, 200


def _hash(path):
    return Core.sha256_file(path)[:16]


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
        if not os.path.isabs(executable):
            cand = public_path(root, executable.replace("\\", "/"))
            if cand.exists():
                executable = str(cand)
            elif os.name == "nt":
                for ext in (".exe", ".cmd", ".bat"):
                    c_ext = Path(str(cand) + ext)
                    if c_ext.exists():
                        executable = str(c_ext)
                        break
        elif os.name == "nt" and not Path(executable).exists():
            for ext in (".exe", ".cmd", ".bat"):
                if Path(executable + ext).exists():
                    executable = executable + ext
                    break
    elif os.name == "nt":
        executable = shutil.which(executable) or executable
    if Path(executable).suffix.lower() in (".cmd", ".bat"):
        injected = [s for s in argv[1:] if BATCH_META.search(s)]
        if injected:
            raise ValueError(
                'Batch arguments must not contain & | < > ^ % ! " ( ) (cmd.exe injection): ' + injected[0]
            )
    env = Core.clean_env() if strip_secrets else dict(os.environ)
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
        log.seek(0)
        raw = log.read(4 * 1024 * 1024 + 1)
        exceeded = exceeded or len(raw) > 4 * 1024 * 1024
        blocked = False
        if output_guard is not None:
            try:
                output_guard(raw)
            except ValueError:
                blocked = True
        safe = (
            "[output withheld: scanner rejected output]\n"
            if blocked
            else S.sanitize(raw[: 4 * 1024 * 1024].decode("utf-8", errors="replace"))
        )
        if exceeded:
            safe += "\n[output limit exceeded; result is not PASS]\n"
        Core.write_atomic(log_path, safe)
    return {
        "exit_code": 125 if exceeded or blocked else 124 if timed_out else (proc.returncode if proc is not None else 1),
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - started, 3),
        "containment": "Windows JobObject" if os.name == "nt" else "POSIX process group",
    }


def task_digest(B, root, task, check_session=True):
    return R.task_digest(B, root, task, check_session=check_session)


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
    entries = []
    for p in runs.glob("*.log"):
        if p.name in cited:
            continue
        try:
            entries.append((p.stat().st_mtime, p))
        except OSError:
            continue
    entries.sort(key=lambda item: item[0])
    cutoff = datetime.now(timezone.utc).timestamp() - RUNS_KEEP_DAYS * 86400
    for n, (mtime, path) in enumerate(entries):
        if mtime < cutoff or len(entries) - n > RUNS_KEEP_FILES:
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
        check_m = CHECK_RE.match(line)
        typed = EVIDENCE_RE.match(line)
        if check_m and index not in keep:
            continue
        if (
            typed
            and value
            and contract
            and typed.group("kind") != "user_feedback"
            and (typed.group("digest") != value or typed.group("contract") != contract)
        ):
            continue
        compact.append(line)
    text = B.read(task["file"]) or ""
    if compact != lines:
        replacement = "## Evidence\n" + "\n".join(compact) + "\n\n"
        text = re.sub(r"^## Evidence\s*\n.*?(?=^## |\Z)", lambda _: replacement, text, count=1, flags=re.M | re.S)
        Core.write_atomic(task["file"], text)


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
    return set(A.implementers(B, task))


def finding_accepted(B, root, severity, reason, owner):
    owner_clean = (owner or "").strip()
    if not (reason or "").strip() or not owner_clean:
        return False
    if severity == "QUALITY":
        return owner_clean == "user"
    if severity == "MINOR":
        return owner_clean == "user" or (
            bool(re.fullmatch(r"PB-\d{3,}", owner_clean))
            and (B.bp(root) / "tasks" / (owner_clean + ".md")).is_file()
        )
    return False


def effective_risk(B, task):
    return R.effective_risk(B, task)


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
    if timeout is None:
        timeout = float(cfg.get("check_timeout", 900) or 900)
    elif type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 3600:
        raise ValueError("Timeout must be in (0, 3600] seconds")
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
            Core.write_atomic(path, "Explicit check execution budget reached; command not launched")
            result = {"exit_code": 125, "duration_seconds": 0}
        else:
            result = run_command(
                root,
                S.command(B, root, task, cmd),
                path,
                min(timeout, remaining) if remaining is not None else timeout,
                output_guard=lambda raw: S.scan_output(B, root, task, raw),
            )
        results.append((cmd, result, path, log_rel))
    after, _ = task_digest(B, root, task)
    out = []
    for cmd, r, path, log_rel in results:
        ok = r["exit_code"] == 0 and before == after
        existing_body = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        footer = (
            f"\n{LOG_FOOTER} {'PASS' if ok else 'FAIL'} exit={r['exit_code']} "
            f"digest={after} contract={contract}\n"
        )
        Core.write_atomic(path, existing_body + footer)
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
        R.progress(
            B,
            root,
            task,
            "Tick proven criteria, verify remaining behavior, then review and accept"
            if passed
            else "Inspect the failed check; change approach before repeating",
            failing="" if passed else "Verify failed: " + ",".join(str(r["exit_code"]) for _, r, _, _ in results),
            strategy="check",
        )
    return (0 if passed else 1), out


def evidence(B, root, task_id, kind, note, files=(), actor="", criteria=()):
    task = B.find_task(root, task_id)
    actor = _actor(B, task, actor)
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
        # Scan all text/XML artifacts including .svg; only true binary media skip text scan.
        if path.suffix.lower() not in BINARY_SHOT_SUFFIXES:
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
    task = B.find_task(root, task_id)
    reviewer = B.agent_id(reviewer, "--reviewer")
    R.guard(B, root, task)
    for finding in findings:
        S.require_clean(finding, "review finding")
    if task["status"] not in ("IN_PROGRESS", "REVIEW"):
        return 2, [f"FAIL {task['id']} is {task['status']}; nothing to review"]
    modes = B.get_session_modes(root) if hasattr(B, "get_session_modes") else {"rev": ""}
    if self_review and modes.get("rev") != "solo":
        raise ValueError("--self-review requires the upfront REV mode SOLO")
    allow_self = bool(self_review and modes.get("rev") == "solo")
    imps = implementers(B, task)
    if not task.get("owner"):
        return 2, [
            f"FAIL reviewer must be named and must not have implemented {task['id']} "
            "(no Owner); a session never reviews its own work (unless REV mode is solo with --self-review)"
        ]
    if not allow_self:
        identity = A.canonical_identity(reviewer, agents_path)
        if any(identity == A.canonical_identity(imp, agents_path) for imp in imps):
            if modes.get("rev") == "solo":
                return 2, [
                    f"FAIL REV=solo requires explicit --self-review for self-review of {task['id']}"
                ]
            return 2, [
                f"FAIL reviewer must be named and must not have implemented {task['id']} "
                f"({', '.join(sorted(imps)) or 'no Owner'}); a session never reviews its own work (unless REV mode is solo with --self-review)"
            ]
    if verdict not in ("PASS", "BLOCKED"):
        raise ValueError("Verdict must be PASS or BLOCKED")
    if not allow_self:
        if R.enabled(B, root):
            registry = A.registry_path(agents_path)
            models = A.load(registry).get("models", {}) if registry.exists() else {}
            if reviewer not in models:
                raise ValueError("REVIEW_PROVENANCE_PENDING: independent reviewer must be registered; a different alias alone is not evidence")
        policy = A.gate(B, task, reviewer, "review", agents_path, root=root) or {}
        report = policy.get("review_report")
        if report is not None and (report["verdict"] != verdict or not set(report["findings"]).issubset(set(findings))):
            raise ValueError("Review verdict/findings must retain the native worker's actual report")
    for f in findings:
        if any(ord(c) < 32 for c in f):
            raise ValueError("Finding must be one line without control characters")
        m = FINDING_RE.match("- finding " + f.strip())
        if not m:
            raise ValueError(
                'Finding must be "BLOCKER|MAJOR|QUALITY|MINOR: text" with optional '
                '" | accepted: reason | owner: user|PB-NNN" (QUALITY: owner user only)'
            )
        if (m.group(3) is not None or m.group(4) is not None) and not finding_accepted(B, root, m.group(1), m.group(3), m.group(4)):
            raise ValueError(
                'Accepted MINOR owner must be "user" or an open follow-up task PB-NNN (with nonempty reason); '
                "an accepted QUALITY gap is owned by the user only; BLOCKER/MAJOR findings cannot be waived"
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
        blocking_findings = [
            f for f in findings
            if (m := FINDING_RE.match("- finding " + f.strip()))
            and not finding_accepted(B, root, m.group(1), m.group(3), m.group(4))
        ]
        next_step = (
            "Review passed on current digest; run `accept` and commit"
            if verdict == "PASS" and not blocking_findings
            else "Fix review findings, recheck, then re-review"
        )
        R.progress(
            B,
            root,
            B.find_task(root, task["id"]),
            next_step,
            failing="" if verdict == "PASS" and not blocking_findings else f"Review {verdict}: {len(blocking_findings)} unresolved finding(s)",
            strategy="review",
        )
    return 0, [line[2:] for line in lines]


def _file_matches(root, ref):
    name, _, short = ref.strip().rpartition("@")
    try:
        path = public_path(root, name)
        return path.is_file() and _hash(path) == short
    except ValueError:
        return False


def current_criteria(task, root, value, contract):
    proven = set()
    for item in task.get("items", []):
        if item["kind"] == "machine":
            continue
        for line in task.get("evidence_lines", []):
            match = EVIDENCE_RE.match(line)
            if (
                match
                and match.group("kind") == item["kind"]
                and match.group("digest") == value
                and match.group("contract") == contract
                and item["id"] in match.group("criteria").split(",")
                and all(_file_matches(root, ref) for ref in (match.group("files") or "").split(",") if ref.strip())
            ):
                proven.add(item["id"])
                break
    return proven


def accept(B, root, task_id, actor="", agents_path=None, self_review=False):
    task = B.find_task(root, task_id)
    if task["status"] not in ("IN_PROGRESS", "REVIEW"):
        return 2, [f"FAIL {task['id']} is {task['status']}: only IN_PROGRESS or REVIEW tasks are accepted"]
    _actor(B, task, actor or task.get("owner", ""))
    R.guard(B, root, task)
    if R.enabled(B, root):
        S.require_clean(B.read(task["file"]) or "", "task export")
        if B.git(root, "rev-parse", "--is-inside-work-tree") == "true":
            S.scan_staged(B, root)
    modes = B.get_session_modes(root) if hasattr(B, "get_session_modes") else {"rev": ""}
    if self_review and modes.get("rev") != "solo":
        raise ValueError("--self-review requires the upfront REV mode SOLO")
    allow_self = modes.get("rev") == "solo"
    if not allow_self:
        A.gate(B, task, actor or task.get("owner", ""), "accept", agents_path, root=root)
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
                if not allow_self
                else "explicit SOLO review required on current source and spec: run `review --self-review` after the audit"
            )
        else:
            if R.enabled(B, root):
                try:
                    R.review_guard(B, root, task, rev, allow_self, agents_path)
                except ValueError as error:
                    problems.append("review provenance: " + str(error))
            elif not allow_self:
                try:
                    A.gate(B, task, rev["reviewer"], "review", agents_path, root=root)
                except ValueError as error:
                    problems.append("reviewer policy: " + str(error))
            if not allow_self:
                identity = A.canonical_identity(rev["reviewer"], agents_path)
                if any(identity == A.canonical_identity(imp, agents_path) for imp in implementers(B, task)):
                    problems.append(f"reviewer {rev['reviewer']} implemented this task")
    if rev is not None and rev["digest"] == current and rev["contract"] == contract:
        if rev["verdict"] != "PASS":
            problems.append("review verdict BLOCKED")
        for severity, text_, reason, owner in rev["findings"]:
            if not finding_accepted(B, root, severity, reason, owner):
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
