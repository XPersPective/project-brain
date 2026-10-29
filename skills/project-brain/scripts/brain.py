#!/usr/bin/env python3
"""project-brain 3.0 helper. Stdlib only, Python 3.8+.

  boot     [root]   State, target, plan, focus, recent work, files to load, next action. Run first.
  map      [root]   Compact repository overview (genesis; replaces manual exploration).
  init     [root]   Create .project-brain/ skeleton. Never overwrites.
  new      <root> "title" [--priority P1|P2|P3] [--tier L|M|H] [--risk LOW|MEDIUM|HIGH] [--depends PB-001]
                    Create the next task file. IDs are never reused (Git history checked).
  start    <task> [root] [--agent <alias>] [--takeover "<reason>"]
                    Start or resume a task, recording Owner, Risk, and source/contract digests.
  check    <task> [root] [--timeout <sec>] [--as <alias>]
                    Run task Verify commands inside ProcessTree and record digest-bound machine evidence.
  evidence <task> [root] --kind <kind> --note "<text>" [--criterion <id>] [--file <relpath>] [--as <alias>]
                    Record digest-bound non-machine evidence (visual, interaction, accessibility, etc.).
  review   <task> [root] --reviewer <alias> --verdict PASS|BLOCKED [--finding "SEVERITY: text"]
                    Record independent review bound to current source and contract digests.
  accept   <task> [root] [--as <alias>]
                    Verify all acceptance criteria, machine checks, evidence, and review; mark DONE.
  score    [task] [root] [--write] [--json]
                    Measure task complexity (0-100), computed Tier (L/M/H), effort, risk floor & delegation eligibility.
  agents   <scan|list|quota|select|merge> ...
                    Discover installed CLI coding agents, read live subscription quotas, and select optimal models.
  delegate <task> [root] [--cli <cli>] [--model <alias>] [--effort <effort>] [--dry-run] [--force]
                    Dispatch a READY/IN_PROGRESS Tier L/M task to a CLI worker agent in ProcessTree + auto-check.
  changed  [root]   Domains changed since their Current checkpoints.
  validate [root]   Structural checks, executable-spec checks, UI/Backend quality checks, size budgets.
  migrate  [root] [--apply]   Convert a legacy Brain (schema <=3 or PROJECT_BRAIN.md); preview by default.
  legacy   [root] [--apply]   Detect and adopt foreign planning systems (.taskmaster, .planning, etc.).
  doctor   [root]   Verify Python runtime, ProcessTree containment, Git, and CLI agent readiness.

Exit: 0 ok, 1 warnings / pending review or user feedback, 2 errors / blocked, 3 no Project Brain.
"""

import argparse
from contextlib import contextmanager
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

VERSION = "3.5.1"
SCHEMA = 4
BRAIN_DIR = ".project-brain"
LEGACY_FILE = "PROJECT_BRAIN.md"
STATUS_VALUES = ("IN_PROGRESS", "REVIEW", "READY", "PLANNED", "BLOCKED")
RISK_VALUES = ("LOW", "MEDIUM", "HIGH")
PRIORITY_VALUES = ("P1", "P2", "P3")
TIER_VALUES = ("L", "M", "H")
EXEC_MODES = ("pool_mixed", "pool_med_low", "pool_low", "self_mixed", "self_and_lower", "solo")
REV_MODES = EXEC_MODES
MODE_ALIASES = {
    "p-all": "pool_mixed", "pool_all": "pool_mixed", "pool-mixed": "pool_mixed", "pool_mixed": "pool_mixed",
    "p-ml": "pool_med_low", "pool_ml": "pool_med_low", "pool-med-low": "pool_med_low", "pool_med_low": "pool_med_low",
    "p-l": "pool_low", "pool-low": "pool_low", "pool_low": "pool_low",
    "s-all": "self_mixed", "n-all": "self_mixed", "self-mixed": "self_mixed", "self_mixed": "self_mixed",
    "s-ml": "self_and_lower", "n-ml": "self_and_lower", "self-and-lower": "self_and_lower", "self_and_lower": "self_and_lower",
    "s-l": "self_and_lower", "n-l": "self_and_lower", "self_low": "self_and_lower",
    "solo": "solo", "self_only": "solo", "self-only": "solo",
}
KINDS = (
    "machine",
    "visual",
    "interaction",
    "accessibility",
    "security",
    "integration",
    "architecture",
    "user_feedback",
)
KIND_ALIASES = {
    "a11y": "accessibility",
    "ui": "visual",
    "ux": "interaction",
    "sec": "security",
    "arch": "architecture",
    "user": "user_feedback",
    "manual": "interaction",
}

VAGUE_RE = re.compile(
    r"\b(etc\.|improve|clean ?up|refactor as needed|handle properly|as discussed|"
    r"vb\.|iyileştir\w*|düzenle\w*)",
    re.I,
)
TASK_FILE_RE = re.compile(r"^PB-(\d+)\.md$")
ADR_FILE_RE = re.compile(r"^ADR-(\d+)\.md$")
HEADER_RE = re.compile(
    r"^\**(status|priority|tier|risk|owner|depends|dependencies|areas|affected areas|domains|blocked|inputs|purpose|secrets)\**:\s*(.*)$",
    re.I,
)
HEADER_ALIAS = {"dependencies": "depends", "affected areas": "areas"}
STATUS_RE = re.compile(
    r"^\W*(IN[_ -]PROGRESS|REVIEW|READY|PLANNED|BLOCKED|DONE|COMPLETED?)(?![A-Z_])",
    re.I,
)
ITEM_RE = re.compile(r"^\s*-\s*\[([ xX])\]\s*(?:\[([a-zA-Z0-9_-]+)\]\s*)?(.+?)\s*$")
START_RE = re.compile(
    r"^- start: IN_PROGRESS \| owner=(?P<owner>[^|]+?) \| risk=(?P<risk>LOW|MEDIUM|HIGH) "
    r"\| digest=(?P<digest>[0-9a-f]+) \| contract=(?P<contract>[0-9a-f]+)"
    r"(?: \| strength=(?P<strength>low|medium|high))?"
    r"(?: \| takeover=(?P<takeover>.+))?$"
)
EXT_RE = re.compile(
    r"^\s*-\s*(?:(?P<op>[A-Za-z0-9_.:/-]+)\s*(?:\||:)\s*)?(?P<state>not_started|prepared|sent|response_unknown|confirmed|failed)\b(?P<rest>.*)$",
    re.I,
)
PLACEHOLDERS = (
    "<observable condition>",
    "<what and why",
    "<command>",
    "<the user's goal",
    "`<path>`",
    "<exact path",
    "<intended end state>",
)
BUDGETS = {"current": 200, "target": 150, "constraints": 100, "task": 80, "open_tasks": 25}

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "target", "coverage", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".turbo", ".cache", ".idea", ".gradle",
    "bin", "obj", ".dart_tool", ".pub-cache", BRAIN_DIR,
}

CURRENT_TMPL = """# Current Architecture

Verified present reality only. Markers: VERIFIED | OBSERVED | INFERRED | STALE | UNKNOWN.

## Runtime
- <language, framework, entry points>

## Map
<!-- path — role. Orientation index: read this instead of exploring. <=40 lines. -->
- `<path>` — <role>

## Domains

### <domain>
Status: UNKNOWN
Sources: `<src/domain/**>`, `<tests/domain/**>`
- <components, data flow, boundaries; terse, path:symbol refs>

## Known Unknowns
- <only unknowns that can change future work>
"""

TARGET_TMPL = """# Target Architecture
Status: DRAFT

Confirmed intent only. DRAFT until the user confirms the Goal. Never invent: unknown -> Open Decisions.

## Goal
<the user's goal, in their words; only the user changes it>

## Target State
### <domain>
- <intended end state>

## Non-Goals
- <what will not be built>

## Open Decisions
- TD-001 OPEN: <question> -> blocks <task/area>

## Success Conditions
- <observable condition>
"""

CONSTRAINTS_TMPL = """# Constraints

Only rules that change decisions. One line each, with source.

- C-001: <rule> (source: user | config | convention)
"""

TASK_TMPL = """# {id} — {title}
Status: {status}
Priority: {priority}
Tier: {tier}
Risk: {risk}
Owner:
Depends: {deps}
Areas: <`src/x/**`, `tests/x/**`>
Inputs:
Purpose: implementation
Secrets: none
Domains: <domain, ...>

## Objective
<what and why, in the user's words>

## Steps
1. <exact path, symbol and change; one action per step>

## Acceptance
- [ ] <observable condition>

## Verify
- `<command>`

## Escalate if
- <change that needs a user decision>

## Evidence

## Review

## Notes
"""

POINTER_MARK = "<!-- project-brain -->"
POINTER = f"""{POINTER_MARK}
## Project Brain
This project keeps its state in `.project-brain/` (current architecture, target, open tasks).
Before any work, load the `project-brain` skill and run its boot step; follow it for all work here.
"""


# ── small helpers & atomic I/O ────────────────────────────────────────────

def git(root, *args, timeout=60):
    """Run git; return stdout (right-stripped) or None on failure."""
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.rstrip() if r.returncode == 0 else None


def git_paths(root, *args):
    """Run a -z git command that lists paths; None on failure."""
    out = git(root, args[0], "-z", *args[1:])
    return None if out is None else [p for p in out.split("\0") if p]


def read(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def write_atomic(path, content):
    """Crash-safe LF-normalized atomic file replacement."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextmanager
def checkout_lock(root, timeout=15.0, name="writer.lock"):
    """OS-released lock: a slow/live writer never becomes stale merely with age."""
    import runtime_verify as V

    b = bp(root)
    if not b.is_dir():
        yield
        return
    cache = V.public_path(root, BRAIN_DIR + "/.cache")
    cache.mkdir(parents=True, exist_ok=True)
    lock_file = V.public_path(root, BRAIN_DIR + "/.cache/" + name)
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
                    raise ValueError(f"Timed out waiting for {lock_file}; another Project Brain command may be running")
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        # Keep the inode: unlinking permits two processes to lock different files.


def norm_id(prefix, n):
    m = re.search(r"(\d+)", str(n))
    if not m:
        raise ValueError(f"Invalid ID: {n!r}")
    return f"{prefix}-{int(m.group(1)):03d}"


def norm_domain(s):
    return re.sub(r"[\s_]+", "-", s.strip().strip("`*#").strip().lower())


def agent_id(value, flag="--agent"):
    s = (value or "").strip()
    if not s or "|" in s or any(ord(c) < 32 for c in s) or len(s) > 80:
        raise ValueError(f"{flag} must be a non-empty agent/model identifier (<=80 chars, no '|')")
    return s


def matches(path, pat):
    """Glob (fnmatch, * crosses /) or path/directory prefix match."""
    pat = pat.strip()
    pat = pat[2:] if pat.startswith("./") else pat
    if any(c in pat for c in "*?["):
        return fnmatch.fnmatchcase(path, pat)
    return path == pat or path.startswith(pat.rstrip("/") + "/")


def criterion_id(kind, text):
    norm = re.sub(r"\s+", " ", text.strip())
    return hashlib.sha256(f"{kind}:{norm}".encode("utf-8")).hexdigest()[:8]


def areas_digest(file_bytes_pairs):
    """LF-normalized SHA-256 digest (16 hex chars) over sorted (relpath, bytes) pairs."""
    h = hashlib.sha256()
    for rel, raw in sorted(file_bytes_pairs, key=lambda item: item[0]):
        norm_bytes = raw.replace(b"\r\n", b"\n")
        h.update(rel.encode("utf-8") + b"\0" + str(len(norm_bytes)).encode("ascii") + b"\0" + norm_bytes + b"\0")
    return h.hexdigest()[:16]


def contract(task):
    """16-hex SHA-256 digest of the task's executable specification (Risk, Areas, Objective, Steps, Acceptance, Verify)."""
    h = hashlib.sha256()
    parts = [
        f"risk:{task.get('risk', '')}",
        f"areas:{','.join(sorted(task.get('areas', [])))}",
        f"objective:{task.get('objective', '').strip()}",
        "steps:" + "\n".join(s.strip() for s in task.get("steps", [])),
        "acceptance:" + "\n".join(f"{i['kind']}:{i['text']}" for i in task.get("items", [])),
        "verify:" + "\n".join(task.get("verify_cmds", [])),
    ]
    if task.get("inputs"):
        parts.append("inputs:" + ",".join(sorted(task["inputs"])))
    if task.get("purpose", "implementation") != "implementation":
        parts.append("purpose:" + task["purpose"])
    if task.get("secrets", "none") != "none":
        parts.append("secrets:" + task["secrets"])
    h.update("\n---\n".join(parts).encode("utf-8"))
    return h.hexdigest()[:16]


def parse_config(root):
    """Two-level scalar YAML subset. Reject unsupported syntax instead of dropping data."""
    text = read(Path(root) / BRAIN_DIR / "config.yaml") or ""
    out, section = {}, None
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.fullmatch(r"(  )?([\w-]+):\s*(.*)", line)
        if not m:
            raise ValueError(f"config.yaml:{number}: expected a top-level key or two-space scalar entry")
        indent, key, raw = m.groups()
        if raw.startswith('"'):
            val, end = json.JSONDecoder().raw_decode(raw)
            if raw[end:].strip() and not raw[end:].lstrip().startswith("#"):
                raise ValueError(f"config.yaml:{number}: unexpected text after quoted value")
        elif raw.startswith("'"):
            quoted = re.fullmatch(r"'((?:''|[^'])*)'\s*(?:#.*)?", raw)
            if not quoted:
                raise ValueError(f"config.yaml:{number}: invalid single-quoted value")
            val = quoted.group(1).replace("''", "'")
        else:
            val = re.split(r"\s+#", raw, maxsplit=1)[0].rstrip() if not raw.startswith("#") else ""
            if val.startswith(("|", ">", "[", "{", "&", "*", "!")):
                raise ValueError(f"config.yaml:{number}: use a quoted scalar; YAML collections/blocks are unsupported")
        target = out if not indent else out.get(section)
        if not isinstance(target, dict) or key in target:
            raise ValueError(f"config.yaml:{number}: duplicate key or entry outside a section")
        if not indent:
            section = key if not val and not raw.startswith(('"', "'")) else None
            if section:
                target[key] = {}
            else:
                target[key] = val
        else:
            target[key] = val
    for key in ("architecture", "git", "commands"):
        if key in out and not isinstance(out[key], dict):
            raise ValueError(f"config.yaml: {key} must be a section")
    version = out.get("schema_version", "")
    if not isinstance(version, str) or (version and (not version.isdigit() or int(version) > SCHEMA)):
        raise ValueError(f"config.yaml: unsupported schema_version {version!r}")
    return out


def normalize_mode(val, role="exec"):
    s = (val or "").strip().lower()
    if not s:
        return ""
    canon = MODE_ALIASES.get(s, s)
    allowed = EXEC_MODES if role == "exec" else REV_MODES
    if canon not in allowed:
        raise ValueError(f"Invalid {role} mode {val!r}; allowed: {', '.join(allowed)}")
    return canon


def session_modes_file(root):
    import runtime_verify as V
    return V.public_path(root, BRAIN_DIR + "/.cache/session_modes.json")


def get_session_modes(root):
    out = {"exec": "", "rev": "", "note": ""}
    if os.environ.get("PB_EXEC_MODE"):
        out["exec"] = normalize_mode(os.environ["PB_EXEC_MODE"], "exec")
    if os.environ.get("PB_REV_MODE"):
        out["rev"] = normalize_mode(os.environ["PB_REV_MODE"], "rev")
    if brain_exists(root):
        try:
            p = session_modes_file(root)
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                if isinstance(data, dict) and (not os.environ.get("PB_SESSION_ID") or data.get("session_id") == os.environ["PB_SESSION_ID"]):
                    if not out["exec"] and data.get("exec"):
                        out["exec"] = normalize_mode(str(data["exec"]), "exec")
                    if not out["rev"] and data.get("rev"):
                        out["rev"] = normalize_mode(str(data["rev"]), "rev")
                    out["note"] = str(data.get("note", ""))
        except (ValueError, OSError):
            pass
    return out


def set_session_modes(root, exec_mode="", rev_mode="", note="", new=False):
    cur = {"exec": "", "rev": "", "note": ""} if new else get_session_modes(root)
    cur["session_id"] = os.environ.get("PB_SESSION_ID", "")
    if exec_mode:
        cur["exec"] = normalize_mode(exec_mode, "exec")
    if rev_mode:
        cur["rev"] = normalize_mode(rev_mode, "rev")
    elif exec_mode:
        cur["rev"] = cur["exec"]
    if note:
        cur["note"] = note.strip()
    p = session_modes_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    if bp(root).is_dir() and not (bp(root) / ".gitignore").exists():
        write_atomic(bp(root) / ".gitignore", ".cache/\n")
    write_atomic(p, json.dumps(cur, indent=2, ensure_ascii=False))
    return cur


def takeover_status(root, active, has_git, dirty_other):
    """Determine whether the takeover test suite must run or can be skipped to save tokens."""
    import runtime_verify as V

    if not has_git:
        return "REQUIRED (no git baseline)"
    outside = [p for p in dirty_other if not active or not any(matches(p, a) for a in active.get("areas", []))]
    if outside:
        return "REQUIRED (source edits outside active Areas)"
    if active and active.get("areas"):
        try:
            cur_dig, _ = V.task_digest(sys.modules[__name__], root, active)
            cur_con = contract(active)
            if active.get("verify_cmds"):
                if V.current_checks(sys.modules[__name__], root, active, cur_dig, cur_con):
                    return f"SKIP ({active['id']} Verify logs valid on current digest={cur_dig}; scoped checks reusable)"
        except ValueError:
            pass
    if dirty_other:
        return "REQUIRED (uncommitted source edits present)"
    head_body = git(root, "log", "-1", "--format=%B", "HEAD") or ""
    if not active and not is_wip(head_body) and "global" in trailer_values(head_body, "PB-Verification"):
        return "SKIP (clean tree at verified checkpoint HEAD; do not re-run test suite)"
    return "REQUIRED (run once before new edits)"


def proven_criteria_ids(root, task):
    """Return set of criterion IDs already proven on current source digest and contract."""
    import runtime_verify as V

    if not task or not task.get("areas"):
        return set()
    try:
        cur_dig, _ = V.task_digest(sys.modules[__name__], root, task)
    except ValueError:
        return set()
    cur_con = contract(task)
    return V.current_criteria(task, root, cur_dig, cur_con)


def sections(text):
    """{'': lines before first '## ', 'heading lower': lines}."""
    out, cur = {"": []}, ""
    for line in text.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip().lower()
            out.setdefault(cur, [])
        else:
            out[cur].append(line)
    return out


def first_line(lines):
    return next((l.strip() for l in lines if l.strip()), "")


def split_list(s):
    ticks = re.findall(r"`([^`]+)`", s)
    if ticks:
        return ticks
    return [x.strip() for x in s.split(",") if x.strip() and x.strip() not in ("-", "None", "none")]


# ── Brain files & task manipulation ───────────────────────────────────────

def bp(root):
    return Path(root) / BRAIN_DIR


def brain_exists(root):
    b = bp(root)
    return b.is_dir() and any((b / n).exists() for n in ("config.yaml", "current.md", "current"))


def set_headers(path, updates):
    """Update or insert header fields at the top of a task file atomically."""
    text = read(path) or ""
    lines = text.splitlines()
    end_head = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
    remaining = dict(updates)
    new_head = []
    for line in lines[:end_head]:
        m = HEADER_RE.match(line.strip())
        if m:
            raw_k = m.group(1)
            canon_k = HEADER_ALIAS.get(raw_k.lower(), raw_k.lower())
            matched_key = next((uk for uk in list(remaining) if uk.lower() == canon_k), None)
            if matched_key is not None:
                val = remaining.pop(matched_key)
                new_head.append(f"{matched_key}: {val}".rstrip())
                continue
        new_head.append(line)
    if remaining:
        insert_at = len(new_head)
        while insert_at > 0 and not new_head[insert_at - 1].strip():
            insert_at -= 1
        for k, v in remaining.items():
            new_head.insert(insert_at, f"{k}: {v}".rstrip())
            insert_at += 1
    write_atomic(path, "\n".join(new_head + lines[end_head:]) + "\n")


def set_header(path, key, value):
    set_headers(path, {key: value})


def append_section(path, heading, line):
    """Append a bullet line to `## <heading>`, creating the section before `## Notes` (or at EOF) if absent."""
    text = read(path) or ""
    lines = text.splitlines()
    target_h = f"## {heading}".lower()
    idx = next((i for i, l in enumerate(lines) if l.strip().lower() == target_h), None)
    if idx is None:
        notes_idx = next((i for i, l in enumerate(lines) if l.strip().lower() == "## notes"), None)
        block = ["", f"## {heading}", line]
        if notes_idx is not None:
            lines = lines[:notes_idx] + block + [""] + lines[notes_idx:]
        else:
            lines = lines + block
    else:
        next_h = next((i for i in range(idx + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
        insert_at = next_h
        while insert_at > idx + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, line)
    write_atomic(path, "\n".join(lines) + "\n")


def parse_task(path, text=None):
    text = read(path) if text is None else text
    if text is None:
        return None
    sec = sections(text)
    head = {}
    for line in sec[""]:
        m = HEADER_RE.match(line.strip())
        if m:
            key = m.group(1).lower()
            head.setdefault(HEADER_ALIAS.get(key, key), m.group(2).strip())
    title = next((l[2:].strip() for l in sec[""] if l.startswith("# ")), path.stem)
    title = re.sub(r"^PB-\d+\s*[—–-]\s*", "", title)
    raw = head.get("status") or first_line(sec.get("status", []))
    m = STATUS_RE.match(raw)
    status = re.sub(r"[ -]", "_", m.group(1).upper()) if m else "?"
    status = "DONE" if status.startswith("COMPLETE") else status
    status_note = raw[m.end():].strip(" -—–:.()") if m else raw
    deps_src = head.get("depends") if "depends" in head else "\n".join(sec.get("dependencies", []))
    deps = [norm_id("PB", n) for n in re.findall(r"PB-(\d+)", deps_src or "")]
    areas = split_list(head.get("areas", "")) or [
        a for l in sec.get("affected areas", []) for a in re.findall(r"`([^`]+)`", l)
    ]
    if "domains" not in head:
        dm = re.search(r"^\W*domains\W*:\s*(.+)$", text, re.I | re.M)
        if dm:
            head["domains"] = dm.group(1)
    domains = [norm_domain(d) for d in split_list(head.get("domains", ""))]
    if not domains:
        domains = [
            norm_domain(l.strip()[2:])
            for l in sec.get("architecture impact", [])
            if l.strip().startswith("- ")
        ]
    acc = sec.get("acceptance", sec.get("acceptance criteria", []))
    resume = sec.get("resume", [])
    nxt = ""
    for i, l in enumerate(resume):
        m_nxt = re.match(r"^\s*next(?: action)?:\s*(.*)$", l, re.I)
        if m_nxt:
            nxt = m_nxt.group(1).strip() or first_line(resume[i + 1:]).lstrip("- ")
            break
    if "risk" not in head:
        rm = re.search(r"^\W*risk\W*:?\s*(LOW|MEDIUM|HIGH)", text, re.I | re.M)
        if rm:
            head["risk"] = rm.group(1)
    blocked = head.get("blocked") or first_line(sec.get("blocker", [])) or (status == "BLOCKED" and status_note)
    steps = [l for l in sec.get("steps", []) if l.strip()]
    verify = sec.get("verify", sec.get("verification", []))
    verify_cmds = [ cmd.strip() for l in verify for cmd in re.findall(r"`([^`]+)`", l) if cmd.strip() ]
    spec_text = "\n".join(steps + acc)
    priority = head.get("priority", "").upper()[:2]
    tier = head.get("tier", "").upper()[:1]
    owner = head.get("owner", "").strip()
    if owner in ("-", "None", "none"):
        owner = ""

    items, bad_items = [], []
    for line in acc:
        im = ITEM_RE.match(line)
        if not im:
            continue
        mark, raw_kind, body = im.groups()
        rk = (raw_kind or "").strip().lower()
        rk = KIND_ALIASES.get(rk, rk)
        if rk and rk not in KINDS:
            bad_items.append(raw_kind)
            kind = "machine"
        else:
            kind = rk or "machine"
        items.append({
            "done": mark.lower() == "x",
            "kind": kind,
            "raw_kind": rk,
            "text": body.strip(),
            "id": criterion_id(kind, body),
            "raw": line.strip(),
        })

    ext_lines = sec.get("external", sec.get("external operations", []))
    external = []
    for l in ext_lines:
        em = EXT_RE.match(l)
        if em:
            external.append({
                "op": (em.group("op") or "").strip(),
                "state": em.group("state").lower(),
                "rest": em.group("rest").strip(),
                "line": l.strip(),
            })

    ev_lines = [l.strip() for l in sec.get("evidence", []) if l.strip()]
    rev_lines = [l.strip() for l in sec.get("review", []) if l.strip()]
    obj_lines = [l.strip() for l in sec.get("objective", []) if l.strip()]
    tid_match = TASK_FILE_RE.match(path.name)
    tid = norm_id("PB", tid_match.group(1)) if tid_match else path.stem

    return {
        "id": tid,
        "file": path,
        "title": title,
        "status": status,
        "risk": head.get("risk", "").upper(),
        "owner": owner,
        "deps": deps,
        "areas": areas,
        "inputs": split_list(head.get("inputs", "")) or [v for line in sec.get("verification inputs", []) for v in re.findall(r"`([^`]+)`", line)],
        "purpose": head.get("purpose", "implementation").lower(),
        "secrets": head.get("secrets", "none"),
        "domains": [d for d in domains if d],
        "objective": "\n".join(obj_lines),
        "steps": steps,
        "items": items,
        "acceptance": items,
        "bad_items": bad_items,
        "has_acceptance": any(l.strip() for l in acc) or bool(
            re.search(r"^\W*acceptance( criteria)?\W*:", text, re.I | re.M)
        ),
        "open_items": [l.strip() for l in acc if l.strip().startswith("- [ ]")],
        "checkboxes": len(items),
        "has_verify": any(l.strip() for l in verify) or bool(
            re.search(r"^\W*verif(y|ication)\W*:", text, re.I | re.M)
        ),
        "verify_cmds": verify_cmds,
        "status_note": status_note,
        "priority": priority if priority in PRIORITY_VALUES else "P2",
        "priority_raw": head.get("priority", ""),
        "tier": tier,
        "tier_raw": head.get("tier", ""),
        "has_steps": bool(steps),
        "verify_cmd": bool(verify_cmds),
        "has_evidence": bool(ev_lines),
        "evidence_lines": ev_lines,
        "review_lines": rev_lines,
        "resume_lines": [l.strip() for l in resume if l.strip()],
        "external": external,
        "vague": sorted({m.group(1).lower() for m in VAGUE_RE.finditer(spec_text)}),
        "next": nxt,
        "blocked": blocked,
        "lines": len(text.splitlines()),
        "spec_lines": sum(len(lines) + (1 if name else 0) for name, lines in sec.items() if name not in ("evidence", "review", "resume", "notes", "external", "external operations")),
        "text": text,
        "header_id": re.findall(r"^# (PB-\d+)", text, re.M),
    }


def start_records(task):
    out = []
    for line in task.get("evidence_lines", []):
        m = START_RE.match(line)
        if m:
            out.append(m.groupdict())
    return out


def task_errors(task):
    import runtime_agents as A

    errs = []
    if task.get("purpose", "implementation") not in ("implementation", "discovery"):
        errs.append("Purpose must be implementation or discovery")
    if not task.get("areas"):
        errs.append("missing Areas")
    if not task.get("objective"):
        errs.append("missing Objective")
    if not task.get("has_steps"):
        errs.append("missing Steps")
    if not task.get("checkboxes"):
        errs.append("missing Acceptance checkboxes")
    if not task.get("verify_cmd"):
        errs.append("missing backticked Verify command")
    if task.get("vague"):
        errs.append(f"vague words in Steps/Acceptance: {', '.join(task['vague'])}")
    if task.get("bad_items"):
        errs.append(f"unknown Acceptance kind tag(s): {', '.join(task['bad_items'])} (allowed: {', '.join(KINDS)})")
    if any(p in task.get("text", "") for p in PLACEHOLDERS):
        errs.append("unfilled template placeholders")
    if A.task_surface(task)["ui"]:
        kinds = {item["kind"] for item in task.get("items", [])}
        missing = [k for k in ("visual", "interaction", "accessibility") if k not in kinds]
        if missing:
            errs.append("UI task missing Triad tag(s): " + ", ".join(f"[{k}]" for k in missing))
    return errs


def list_tasks(root):
    d = bp(root) / "tasks"
    if not d.is_dir():
        return []
    tasks = [parse_task(f) for f in d.iterdir() if TASK_FILE_RE.match(f.name)]
    return sorted((t for t in tasks if t), key=lambda t: int(t["id"][3:]))


def load_task(root, task_id):
    try:
        tid = norm_id("PB", task_id)
    except ValueError:
        return None
    p = bp(root) / "tasks" / f"{tid}.md"
    return parse_task(p) if p.is_file() else None


def find_task(root, task_id, required=True):
    t = load_task(root, task_id)
    if t is None and required:
        raise ValueError(f"Unknown task: {task_id}")
    return t


def current_files(root):
    b = bp(root)
    files = [(b / "current.md", None)] if (b / "current.md").exists() else []
    if (b / "current").is_dir():
        files += [(f, norm_domain(f.stem)) for f in sorted((b / "current").glob("*.md"))]
    return files


def domain_sources(root):
    """{domain: [globs]} from 'Sources:' lines (and bullets under them) in Current files."""
    res = {}
    for f, fixed in current_files(root):
        domain, collecting = fixed, False
        for line in (read(f) or "").splitlines():
            s = line.strip()
            if s.startswith("#"):
                collecting = "source" in s.lower()
                if not collecting and fixed is None and re.match(r"^#{2,3} ", s):
                    domain = norm_domain(s.lstrip("#"))
                continue
            m = re.match(r"^[*_]*(?:sources|source areas)[*_:]*\s*(.*)$", s, re.I)
            if m:
                collecting = True
                globs = re.findall(r"`([^`]+)`", m.group(1))
            elif collecting and s.startswith("- "):
                globs = re.findall(r"`([^`]+)`", s)
            elif collecting and s:
                collecting, globs = False, []
            else:
                globs = []
            if domain and globs:
                res.setdefault(domain, []).extend(globs)
    return res


def current_slices(path, domains):
    """'path (lines a-b, c-d)': Runtime + Map + the given domains of a long single current.md; else path."""
    rel = path
    lines = (read(path) or "").splitlines()
    if len(lines) <= 120 or not domains:
        return rel, None
    heads = []
    for i, l in enumerate(lines):
        m = re.match(r"^(#{2,3}) (.*)", l)
        if m:
            heads.append((i, len(m.group(1)), norm_domain(m.group(2))))
    ranges, hit = [], False
    for k, (i, lvl, name) in enumerate(heads):
        end = next((j for j, l2, _ in heads[k + 1:] if l2 <= lvl), len(lines))
        if lvl == 3 and name in domains:
            hit = True
            ranges.append((i + 1, end))
        elif lvl == 2 and name in ("runtime", "map"):
            ranges.append((i + 1, end))
    return (rel, ", ".join(f"{a}-{b}" for a, b in ranges)) if hit else (rel, None)


# ── Git state ─────────────────────────────────────────────────────────────

def git_records(root, grep, *rev):
    """[(sha, body)] newest first for commits (in `rev`, default HEAD) whose message matches grep."""
    out = git(root, "log", *rev, f"--grep={grep}", "--format=%H%x1f%B%x1e")
    recs = []
    for r in (out or "").split("\x1e"):
        if "\x1f" in r:
            sha, body = r.split("\x1f", 1)
            recs.append((sha.strip(), body))
    return recs


def trailer_values(body, key):
    return [m.group(1).strip() for m in re.finditer(rf"^{key}:\s*(.+)$", body, re.M)]


def pb_base(root):
    """Last explicit all-domain checkpoint; legacy fallback is the last Current edit."""
    for sha, body in git_records(root, "PB-Current-Checkpoint:"):
        domains = [norm_domain(d) for v in trailer_values(body, "PB-Current-Checkpoint") for d in v.split(",")]
        if "all" in domains and not is_wip(body):
            return sha
    return git(root, "log", "-1", "--format=%H", "--",
               f"{BRAIN_DIR}/current.md", f"{BRAIN_DIR}/current") or None


def is_wip(body):
    return "true" in [v.lower() for v in trailer_values(body, "PB-WIP")]


def task_ids_in(body):
    return [norm_id("PB", n) for v in trailer_values(body, "PB-Tasks?") for n in re.findall(r"PB-(\d+)", v)]


def closed_ids(root, sha, body):
    """Verified deletion or committed DONE+Evidence, never just absence in today's worktree."""
    if is_wip(body) or not set(trailer_values(body, "PB-Verification")) & {"local", "domain", "global"}:
        return set()
    paths = git_paths(root, "ls-tree", "-r", "--name-only", sha, "--", f"{BRAIN_DIR}/tasks")
    if paths is None:
        return set()
    ids = set(task_ids_in(body))
    present, recorded = set(), set()
    for p in paths:
        m = TASK_FILE_RE.match(Path(p).name)
        if m:
            tid = norm_id("PB", m.group(1))
            present.add(tid)
            if tid in ids:
                task = parse_task(Path(p), git(root, "show", f"{sha}:{p}") or "")
                if task["status"] == "DONE" and task["has_evidence"]:
                    recorded.add(tid)
    return (ids - present) | recorded


def recent_closed(root, open_ids, n=3):
    """[(ids, agent, short sha)] for the newest commits that closed tasks."""
    out = []
    seen = set(open_ids)
    for sha, body in git_records(root, "PB-Task"):
        ids = sorted(closed_ids(root, sha, body) - seen)
        seen.update(ids)
        if ids:
            out.append((",".join(ids), (trailer_values(body, "PB-Agent") or ["?"])[0], sha[:7]))
            if len(out) >= n:
                break
    return out


def closed_since_audit(root, open_ids):
    """Number of tasks closed since the newest commit carrying PB-Plan-Audit (or since the start)."""
    last = git(root, "log", "-1", "--grep=PB-Plan-Audit:", "--format=%H")
    ids = set()
    for sha, body in git_records(root, "PB-Task", *([f"{last}..HEAD"] if last else [])):
        ids |= closed_ids(root, sha, body)
    return len(ids - open_ids)


def target_status(root):
    m = re.search(r"^Status:\s*(DRAFT|CONFIRMED)\b", read(bp(root) / "target.md") or "", re.M | re.I)
    return m.group(1).upper() if m else "UNSET"


def legacy_kind(root):
    """'v0' (only PROJECT_BRAIN.md), 'v<N>' (.project-brain schema < 4), or None."""
    if brain_exists(root):
        v = str(parse_config(root).get("schema_version", "")).strip()
        if (bp(root) / "migration-backup" / LEGACY_FILE).exists() and (not v.isdigit() or int(v) < SCHEMA):
            return "v0"
        return None if v.isdigit() and int(v) >= SCHEMA else f"v{v or '?'}"
    return "v0" if (Path(root) / LEGACY_FILE).exists() else None


def history_task_ids(root):
    """(all ids ever committed incl. WIP, ids durably completed)."""
    every, done = set(), set()
    for sha, body in git_records(root, "PB-Task"):
        ids = set(task_ids_in(body))
        every |= ids
        done |= closed_ids(root, sha, body)
    names = git(root, "log", "--format=", "--name-only", "--", f"{BRAIN_DIR}/tasks") or ""
    every.update(
        norm_id("PB", m.group(1))
        for p in names.splitlines()
        if (m := TASK_FILE_RE.match(Path(p).name))
    )
    return every, done


def staleness(root, base):
    """Changes since each domain's actual checkpoint; unrelated PB commits cannot erase drift."""
    if not base:
        return {}, []
    srcs = domain_sources(root)
    bases = {}
    for sha, body in git_records(root, "PB-Current-Checkpoint:"):
        if is_wip(body):
            continue
        for val in trailer_values(body, "PB-Current-Checkpoint"):
            for domain in (norm_domain(d) for d in val.split(",")):
                for d in (srcs if domain == "all" else [domain]):
                    bases.setdefault(d, sha)
    deltas = {}
    for checkpoint in {base, *bases.values()}:
        deltas[checkpoint] = [
            p for p in (git_paths(root, "diff", "--name-only", f"{checkpoint}..HEAD") or [])
            if not p.startswith(BRAIN_DIR + "/")
        ]
    stale = {}
    for d, globs in srcs.items():
        hit = [p for p in deltas[bases.get(d, base)] if any(matches(p, g) for g in globs)]
        if hit:
            stale[d] = hit
    unmapped = [p for p in deltas[base] if not any(matches(p, g) for gl in srcs.values() for g in gl)]
    return stale, unmapped


def merge_op(root):
    gd = git(root, "rev-parse", "--git-dir")
    if not gd:
        return None
    gd = Path(gd) if Path(gd).is_absolute() else Path(root) / gd
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
        if (gd / marker).exists():
            return marker[:-5].lower()
    if (gd / "rebase-merge").is_dir() or (gd / "rebase-apply").is_dir():
        return "rebase"
    return None


def dirty_paths(root):
    out = git(root, "status", "--porcelain", "-z", "-uall")
    if out is None:
        return []
    paths, entries, i = [], out.split("\0"), 0
    while i < len(entries):
        e = entries[i]
        if len(e) > 3:
            paths.append(e[3:])
            if e[0] in "RC":
                i += 1
        i += 1
    return paths


# ── repository overview ───────────────────────────────────────────────────

def repo_files(root, has_git):
    if has_git:
        files = git_paths(root, "ls-files", "--cached", "--others", "--exclude-standard")
        if files is not None:
            return [f for f in files if not f.startswith(BRAIN_DIR + "/")]
    files = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        rel = os.path.relpath(dp, root).replace(os.sep, "/")
        files += [fn if rel == "." else f"{rel}/{fn}" for fn in fns]
    return files


def detect_commands(root):
    root, cmds = Path(root), {}
    pkg = root / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(read(pkg) or "{}").get("scripts", {})
        except ValueError:
            scripts = {}
        runner = (
            "pnpm" if (root / "pnpm-lock.yaml").exists() else
            "yarn" if (root / "yarn.lock").exists() else
            "bun" if (root / "bun.lockb").exists() else "npm"
        )
        for k in ("test", "lint", "build", "typecheck"):
            if k in scripts:
                cmds.setdefault(k, f"{runner} run {k}")
    if (root / "pubspec.yaml").exists():
        cmds.setdefault("test", "flutter test")
        cmds.setdefault("lint", "flutter analyze")
    pyproject = read(root / "pyproject.toml") or ""
    if pyproject or any((root / f).exists() for f in ("pytest.ini", "setup.cfg", "tox.ini", "setup.py")):
        cmds.setdefault("test", "python -m pytest -q")
        if "ruff" in pyproject:
            cmds.setdefault("lint", "ruff check .")
    for marker, test, lint, build in (
        ("Cargo.toml", "cargo test", "cargo clippy", "cargo build"),
        ("go.mod", "go test ./...", "go vet ./...", "go build ./..."),
        ("pom.xml", "mvn -q test", "", "mvn -q package"),
        ("build.gradle", "./gradlew test", "", "./gradlew build"),
        ("build.gradle.kts", "./gradlew test", "", "./gradlew build"),
    ):
        if (root / marker).exists():
            for k, v in (("test", test), ("lint", lint), ("build", build)):
                if v:
                    cmds.setdefault(k, v)
    if list(root.glob("*.sln")) or list(root.glob("*.csproj")):
        cmds.setdefault("test", "dotnet test")
        cmds.setdefault("build", "dotnet build")
    mk = read(root / "Makefile") or ""
    for k in ("test", "lint", "build"):
        if re.search(rf"^{k}:", mk, re.M):
            cmds.setdefault(k, f"make {k}")
    return cmds


def committed_exact(root, path):
    """Current file and index both match a recoverable HEAD blob (including filters)."""
    import runtime_verify as V
    try:
        rel = Path(path).relative_to(root).as_posix()
        file = V.public_path(root, rel)
        if not file.is_file():
            return False
        head = git(root, "rev-parse", "--verify", "HEAD:" + rel)
        index = git(root, "rev-parse", "--verify", ":" + rel)
        actual = git(root, "hash-object", "--path=" + rel, rel)
        return bool(head and head == index == actual)
    except (ValueError, OSError):
        return False


def gc_brain(root, has_git=None, completed=None):
    """Collect only recoverable closed work; preserve unknown/active recovery inputs."""
    import runtime_verify as V
    root = Path(root)
    b = V.public_path(root, BRAIN_DIR)
    if not b.is_dir():
        return []
    if has_git is None:
        has_git = git(root, "rev-parse", "--is-inside-work-tree") == "true"
    if not has_git:
        return []
    if completed is None:
        _, completed = history_task_ids(root)
    removed = []
    for task in list_tasks(root):
        if (task["status"] == "DONE" and task["has_evidence"]
                and task["id"] in completed and committed_exact(root, task["file"])):
            task["file"].unlink()
            removed.append(f"tasks/{task['id']}.md")
    # A remaining task, including dirty DONE, still owns all its evidence and logs.
    retained = {t["id"] for t in list_tasks(root)}
    closed = completed - retained
    ev_root = V.public_path(root, BRAIN_DIR + "/evidence")
    if ev_root.is_dir():
        for directory in sorted(ev_root.iterdir()):
            if not re.fullmatch(r"PB-\d{3,}", directory.name) or directory.name not in closed:
                continue
            try:
                V.public_path(root, directory.relative_to(root).as_posix())
                if not directory.is_dir():
                    continue
                files = list(directory.rglob("*"))
                if any(V.is_link(f) for f in files):
                    continue
                if all(committed_exact(root, f) for f in files if f.is_file()):
                    # Every resolved target above stays inside the evidence directory.
                    shutil.rmtree(directory)
                    removed.append(f"evidence/{directory.name}/")
            except (ValueError, OSError):
                continue
    runs = V.public_path(root, BRAIN_DIR + "/.cache/runs")
    if runs.is_dir():
        for file in sorted(runs.iterdir()):
            match = re.match(r"^(PB-\d{3,})-", file.name)
            if match and match.group(1) in closed and file.is_file() and not V.is_link(file):
                file.unlink()
                removed.append(".cache/runs/" + file.name)
    # Existing bounded pruning preserves every cited log, unlike a per-task cap.
    V.prune_runs(sys.modules[__name__], root)
    # Backups, legacy originals and atomic-write temp files need reconciliation or
    # writer ownership; a checkpoint/age alone does not authorize their deletion.
    return removed


# ── commands ──────────────────────────────────────────────────────────────

def cmd_boot(root, maintain=True):
    import runtime_agents as A
    import runtime_verify as V
    import migrate as M

    has_git = git(root, "rev-parse", "--is-inside-work-tree") == "true"
    auto_mig_notes = []
    legacy = legacy_kind(root)
    if brain_exists(root):
        M.require_supported(root)
    maintain = maintain and not (has_git and merge_op(root))
    if maintain and legacy and has_git and (git(root, "rev-parse", "--verify", "HEAD") or os.environ.get("PB_AUTO_MIGRATE") == "1"):
        M.run(root, apply=True)
        auto_mig_notes.append(f"VERSION_CHECK: auto-migrated {legacy} -> v{VERSION} (schema {SCHEMA})")
        legacy = legacy_kind(root)
    if legacy == "v0":
        print("STATE: LEGACY")
        print(f"  ! {LEGACY_FILE} (single-file Brain) found")
        print("NEXT: Route the user's request first; questions stay read-only. For authorized migration: `migrate` (preview), then `migrate --apply` (SKILL.md Migration).")
        return 0
    if not brain_exists(root):
        foreign = A.detect_foreign(root)
        print("STATE: NO_BRAIN")
        import runtime_pool as P
        for line in (
            P.summary(sys.modules[__name__], root)
            if os.environ.get("PB_AGENTS_REGISTRY")
            else ["MODEL_POOL: ASK_USER_EVERY_SESSION | EXEC: pool_mixed|pool_med_low|pool_low|self_mixed|self_and_lower|solo | REV: pool_mixed|pool_med_low|pool_low|self_mixed|self_and_lower|solo"]
        ):
            print(line)
        for fname, fpaths in foreign:
            print(f"  ! foreign planning state detected: {fname} ({', '.join(fpaths)}) -> run `legacy` to preview adoption")
        print("NEXT: Substantial work -> SKILL.md Genesis (`map`, then `init`). Small request -> just do it.")
        return 0
    cfg = parse_config(root)
    if maintain and not legacy:
        old_ver = cfg.get("skill_version", "")
        if old_ver != VERSION or M.has_pending_upgrade(root, force_all=False):
            upgraded = M.auto_upgrade_v34(root, force_all=(old_ver != VERSION))
            if upgraded:
                auto_mig_notes.append(f"VERSION_CHECK: auto-upgraded project ({old_ver or 'pre-3.4'} -> v{VERSION}): {', '.join(upgraded[:6])}")
            cfg = parse_config(root)
    every_ids, completed_ids = history_task_ids(root) if has_git else (set(), set())
    gc_removed = gc_brain(root, has_git=has_git, completed=completed_ids) if maintain and not legacy else []
    if gc_removed:
        auto_mig_notes.append(f"GC_CLEANUP: removed {', '.join(gc_removed)}")
    all_tasks = list_tasks(root)
    tasks = [t for t in all_tasks if t["status"] != "DONE" or not t["has_evidence"]]
    open_ids = {t["id"] for t in tasks}
    notes, state = list(auto_mig_notes), None
    other = []

    if not (bp(root) / "current.md").exists() and not (bp(root) / "current").is_dir():
        state = "INVALID"
        notes.append("no current architecture file")
    bad = [t["id"] for t in tasks if t["status"] == "?"]
    ip = [t for t in tasks if t["status"] == "IN_PROGRESS"]
    rev_tasks = [t for t in tasks if t["status"] == "REVIEW"]
    kept = [t["id"] for t in all_tasks if t["status"] == "DONE"]
    if bad:
        notes.append(f"no valid Status line: {', '.join(bad)} (run `validate`)")
    if len(ip) > 1:
        notes.append(f"several IN_PROGRESS: {', '.join(t['id'] for t in ip)}: keep one, set the rest READY")
    if kept:
        notes.append(f"finished task files still present: {', '.join(kept)}: retain until evidence is committed (or while Git is unavailable)")
    unproven = [t["id"] for t in tasks if t["status"] == "DONE"]
    if unproven:
        notes.append(f"DONE without Evidence: {', '.join(unproven)}: verify or reopen; these tasks remain unfinished")
    if legacy:
        state = "LEGACY"
        notes.append(f"schema {legacy[1:]}: run `migrate --apply`")
    elif (Path(root) / LEGACY_FILE).exists():
        notes.append(f"legacy {LEGACY_FILE} still present: carry over anything unique, then delete it")

    unresolved_ext = [
        (t["id"], e["op"] or e["line"])
        for t in all_tasks
        for e in t.get("external", [])
        if e["state"] in ("sent", "response_unknown")
    ]
    if unresolved_ext:
        notes.append("READBACK_FIRST unresolved external operations: " + ", ".join(f"{tid}:{op}" for tid, op in unresolved_ext))

    active = ip[0] if ip else (rev_tasks[0] if rev_tasks else None)

    stale, unmapped, done, recent, since_audit = {}, [], set(), [], 0
    local_done = {t["id"] for t in all_tasks if t["status"] == "DONE" and t["has_evidence"]}
    done.update(local_done)
    if not has_git:
        state = state or "NO_GIT"
        gitline = "git: none (degraded: no checkpoints, no history)"
    else:
        branch = git(root, "symbolic-ref", "--short", "-q", "HEAD")
        head = git(root, "rev-parse", "--short", "HEAD") or "(no commits)"
        if not branch:
            notes.append("detached HEAD: do not commit until a branch exists (REFERENCE: Detached HEAD)")
        if git(root, "rev-parse", "--is-shallow-repository") == "true":
            notes.append("shallow clone: missing history proves nothing (REFERENCE: Shallow)")
        base = pb_base(root)
        cp = git(root, "rev-parse", "--short", base) if base else None
        dirty = dirty_paths(root)
        brain_dirty = [p for p in dirty if p.startswith(BRAIN_DIR + "/")]
        other = [p for p in dirty if not p.startswith(BRAIN_DIR + "/")]
        owned = [p for p in other if active and any(matches(p, a) for a in active["areas"])]
        unowned = [p for p in other if p not in owned]
        every, completed = every_ids, completed_ids
        done = (completed | local_done) - open_ids
        stale, unmapped = staleness(root, base)
        recent = recent_closed(root, open_ids)
        since_audit = closed_since_audit(root, open_ids)
        op = merge_op(root)
        if not state:
            state = (
                "CONFLICTED" if op else
                "DIRTY" if unowned else
                "INTERRUPTED" if ip else
                "ADVANCED" if stale or unmapped else
                "RESUME"
            )
        elif state == "LEGACY" and op:
            state = "CONFLICTED"
        gitline = (
            f"git: {branch or 'DETACHED'} @ {head} | current baseline {cp or 'none'}"
            f"{' (= HEAD)' if cp and cp == head else ''} | dirty {len(other)} (+{len(brain_dirty)} brain)"
        )
        if op:
            notes.append(f"{op} in progress")
        if unowned:
            notes.append("dirty outside active task: " + ", ".join(unowned[:8]) + (" ..." if len(unowned) > 8 else ""))
        if brain_dirty and not active:
            notes.append("uncommitted .project-brain edits: review and commit them")
        if not base:
            notes.append("no PB commit yet: next commit must carry PB trailers")

    if unresolved_ext and state not in ("INVALID", "LEGACY", "CONFLICTED"):
        state = "READBACK_FIRST"
    print(f"STATE: {state}")
    print(gitline)
    import runtime_pool as P
    s_modes = get_session_modes(root)
    if os.environ.get("PB_AGENTS_REGISTRY"):
        for line in P.summary(sys.modules[__name__], root):
            print(line)
    elif s_modes["exec"] or s_modes["rev"]:
        print(f"MODEL_POOL: RECORDED (confirm once for a new top-level session) exec={s_modes['exec'] or s_modes['rev']} rev={s_modes['rev'] or s_modes['exec']}")
    else:
        print("MODEL_POOL: ASK_USER_AT_SESSION_START | Ask user once at session start for EXEC and REV (P-ALL|P-ML|P-L|S-ALL|S-ML|SOLO), then execute and review autonomously without stopping")
    import runtime_protocol as R
    import runtime_security as S
    print("PROTOCOL: " + ("1 (intent/input guards active)" if R.enabled(sys.modules[__name__], root) else "0 (legacy compatibility; run `protocol --enable` before new implementation)"))
    print("SECRETS: " + (S.policy(sys.modules[__name__], root).get("reference") or "ASK_ONCE: choose an external symbolic reference or none"))
    print(f"TAKEOVER_CHECK: {takeover_status(root, active, has_git, other)}")
    for n in notes:
        print(f"  ! {n}")
    tstat = target_status(root)
    print(f"TARGET: {tstat}" + {
        "DRAFT": " (goal not confirmed: plan only goal-independent work; ask the user when present)",
        "UNSET": " (add `Status: DRAFT|CONFIRMED` to target.md)",
    }.get(tstat, ""))

    print(f"PLAN: {len(tasks)} open, {len(done)} done")
    for t in tasks[:BUDGETS["open_tasks"]]:
        extra = []
        od = [d for d in t["deps"] if d in open_ids]
        if od:
            extra.append("deps " + ",".join(od))
        if t.get("owner"):
            extra.append(f"owner={t['owner']}")
        if t["status"] == "BLOCKED" and t["blocked"]:
            extra.append(t["blocked"][:50])
        mark = ">" if t is active else " "
        print(
            f" {mark} {t['id']} {t['status']:<11} {t['priority']} {t['tier'] or '-'} {t['title'][:60]}"
            f"{'  [' + '; '.join(extra) + ']' if extra else ''}"
        )
    if len(tasks) > BUDGETS["open_tasks"]:
        print(f"   ... {len(tasks) - BUDGETS['open_tasks']} more")

    ready = sorted(
        (t for t in tasks if t["status"] == "READY" and set(t["deps"]) <= done),
        key=lambda t: (t["priority"], int(t["id"][3:])),
    )
    promote = [t["id"] for t in tasks if t["status"] == "PLANNED" and set(t["deps"]) <= done]
    for t in tasks:
        unresolved = set(t["deps"]) - open_ids - done
        if unresolved:
            print(f"  ! {t['id']}: dependencies without completion evidence: {', '.join(sorted(unresolved))}")
    focus = active or (ready[0] if ready else None)
    if focus:
        n_open = len(focus["open_items"])
        progress = (
            f"{n_open}/{focus['checkboxes']} acceptance open"
            if focus["checkboxes"]
            else "acceptance has no checkboxes"
        )
        sinfo = A.score_task(sys.modules[__name__], root, focus)
        del_hint = "delegatable->`delegate`" if sinfo["delegatable"] else f"role={sinfo['recommended_role']}"
        print(
            f"FOCUS {focus['id']} ({focus['status']}, {focus['priority']}, tier {focus['tier'] or '?'}->{sinfo['effective_tier']}, "
            f"risk {focus['risk'] or '?'}->{sinfo['effective_risk']}, score {sinfo['score']}/100, effort {sinfo['recommended_effort']}, {del_hint}): {progress}"
        )
        if focus["next"]:
            print(f"  next: {focus['next']}")
        if R.enabled(sys.modules[__name__], root):
            try:
                R.guard(sys.modules[__name__], root, focus)
                print("  intent: reconciled with current target/constraints")
            except ValueError as error:
                print("  intent: " + str(error))
        proven_ids = proven_criteria_ids(root, focus)
        if proven_ids:
            print(f"  proven on current digest (DO NOT repeat): {', '.join(sorted(proven_ids))}")
        open_objs = [it for it in focus["items"] if not it["done"] and it["id"] not in proven_ids]
        for it in open_objs[:5]:
            print(f"  - [ ] [{it['kind']}] {it['text']} (criterion {it['id']})")
    if focus:
        missing = [
            n for n, ok in (
                ("Steps", focus["has_steps"]),
                ("Acceptance checkboxes", focus["checkboxes"]),
                ("Verify command", focus["verify_cmd"]),
            )
            if not ok
        ]
        if missing:
            print(f"  ! {focus['id']} is not an executable spec (missing {', '.join(missing)}): write them first (SKILL.md section 5)")
    if promote:
        print(f"  hint: deps done, write full specs and set READY: {', '.join(promote)}")
    if since_audit >= 5:
        print(f"  hint: {since_audit} tasks closed since the last plan audit -> run Plan audit (SKILL.md section 6)")
    if recent:
        print("RECENT: " + "; ".join(f"{ids} by {agent} ({sha})" for ids, agent, sha in recent))
    if stale or unmapped:
        for d, files in stale.items():
            print(f"STALE {d}: {', '.join(files[:5])}{' ...' if len(files) > 5 else ''}")
        if unmapped:
            print(f"UNMAPPED: {', '.join(unmapped[:8])}{' ...' if len(unmapped) > 8 else ''}")

    load = []
    if focus:
        load.append(focus["file"])
        load += [
            current_slices(f, focus["domains"]) if fixed is None else f
            for f, fixed in current_files(root)
            if fixed is None or not focus["domains"] or fixed in focus["domains"]
        ]
        for n in sorted(set(re.findall(r"ADR-(\d+)", focus["text"]))):
            adr = (
                next((f for f in (bp(root) / "decisions").glob(f"ADR-{int(n):03d}*.md")), None)
                if (bp(root) / "decisions").is_dir()
                else None
            )
            if adr:
                load.append(adr)
    else:
        load += [f for f, _ in current_files(root)]
    load += [f for f in (bp(root) / "target.md",) if f.exists()]
    load += sorted((bp(root) / "target").glob("*.md"))
    if (bp(root) / "constraints.md").exists():
        load.append(bp(root) / "constraints.md")

    def show(item):
        f, rng = item if isinstance(item, tuple) else (item, None)
        name = Path(os.path.relpath(f, root)).as_posix()
        return f"{name} (lines {rng})" if rng else name

    print("LOAD: " + " ".join(show(x) for x in load))
    cmds = {k: v for k, v in cfg.get("commands", {}).items() if v}
    if cmds:
        print("CMDS: " + " | ".join(f"{k}={v}" for k, v in cmds.items()))
    git_cfg = cfg.get("git", {})
    print(f"MODE: commit={git_cfg.get('commit', 'auto')} push={git_cfg.get('push', git_cfg.get('push_policy', 'manual'))}")

    nxt = {
        "READBACK_FIRST": "Inspect unresolved external operations with their readback tool; record confirmed/failed before starting or retrying work.",
        "LEGACY": "Route the user's request first; questions stay read-only. For authorized migration: `migrate` (preview), then `migrate --apply` and Plan audit.",
        "INVALID": "Run `validate`, fix the FAIL lines, then boot again (REFERENCE: Corrupt Brain).",
        "CONFLICTED": "Finish the Git operation first (REFERENCE: Conflicts). Start no task.",
        "DIRTY": "Classify each listed path: mine/user/generated/unknown. Never reset/clean/stash/checkout unknown work. Continue only on non-overlapping files.",
        "INTERRUPTED": f"Resume {active['id'] if active else ''}: check `git status --short` (including untracked files) and `git diff --stat` against Resume, then continue at the first open acceptance item.",
        "ADVANCED": "Route the user's request first. For authorized implementation, inspect relevant STALE/UNMAPPED files and reconcile Current before checkpointing.",
    }.get(state)
    if not nxt:
        if focus and focus["status"] == "REVIEW":
            nxt = f"REVIEW {focus['id']}: an independent reviewer agent that did not implement {focus['id']} runs `review {focus['id']} --reviewer <alias> --verdict PASS|BLOCKED`, then `accept {focus['id']}`."
        elif focus:
            nxt = (
                f"Route the user's request before tests or writes (SKILL.md sections 2-3). If authorized, run the takeover check. 'continue': start "
                f"{focus['id']} (`start {focus['id']}` or `delegate {focus['id']}`) and keep working the queue."
            )
        elif promote:
            nxt = f"Route the user's request first; within its authorized scope, refine {promote[0]} to READY and start it."
        elif tasks and all(t["status"] == "BLOCKED" for t in tasks):
            nxt = "Every open task is BLOCKED: report blockers to the user and stop."
        elif tasks:
            nxt = "No startable task: fix statuses (`validate`) or refine a PLANNED task to READY."
        else:
            nxt = "Queue empty: handle the user's message, or run the Final audit (SKILL.md section 6)."
    print(f"NEXT: {nxt}")
    return 0


def cmd_map(root):
    has_git = git(root, "rev-parse", "--is-inside-work-tree") == "true"
    files = repo_files(root, has_git)
    print(f"FILES: {len(files)}{' (git ls-files, ignored excluded)' if has_git else ''}")
    tops, subs, exts = {}, {}, {}
    for f in files:
        parts = f.split("/")
        if len(parts) > 1:
            tops[parts[0]] = tops.get(parts[0], 0) + 1
            if len(parts) > 2:
                key = f"{parts[0]}/{parts[1]}"
                subs[key] = subs.get(key, 0) + 1
        ext = os.path.splitext(f)[1].lower()
        if ext:
            exts[ext] = exts.get(ext, 0) + 1
    print("TREE (files per dir):")
    for top, n in sorted(tops.items(), key=lambda x: -x[1])[:25]:
        print(f"  {top}/ {n}")
        kids = sorted(((k, v) for k, v in subs.items() if k.startswith(top + "/")), key=lambda x: -x[1])
        for k, v in kids[:8]:
            print(f"    {k}/ {v}")
        if len(kids) > 8:
            print(f"    ... {len(kids) - 8} more dirs")
    root_files = sorted(f for f in files if "/" not in f)
    print("ROOT FILES: " + " ".join(root_files[:40]) + (" ..." if len(root_files) > 40 else ""))
    print("EXTENSIONS: " + " ".join(f"{e}:{n}" for e, n in sorted(exts.items(), key=lambda x: -x[1])[:12]))
    docs = [
        f for f in files
        if f.split("/")[-1].upper() in ("README.MD", "AGENTS.MD", "CLAUDE.MD", "GEMINI.MD", "CONTRIBUTING.MD", "ARCHITECTURE.MD")
    ]
    if docs:
        print("INSTRUCTION/DOC FILES: " + " ".join(docs[:15]))
    cmds = detect_commands(root)
    print("CMDS: " + (" | ".join(f"{k}={v}" for k, v in cmds.items()) if cmds else "none detected"))
    print("NEXT: Read only manifests, entry points and instruction files (<=15 files), then `init`.")
    return 0


def write_new(path, content, created):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as f:
            f.write(content)
        created.append(path)


def ensure_pointers(root, write):
    """Agent-neutral activation: AGENTS.md always; CLAUDE.md/GEMINI.md only if the project already has them."""
    done = []
    for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        path, text = Path(root) / name, read(Path(root) / name)
        if text is None and name != "AGENTS.md":
            continue
        if text is None:
            if write:
                with path.open("x", encoding="utf-8", newline="\n") as f:
                    f.write(POINTER)
            done.append((name, "created"))
        elif POINTER_MARK not in text:
            if write:
                with open(path, "a", encoding="utf-8", newline="\n") as f:
                    f.write(("\n" if text.endswith("\n") else "\n\n") + POINTER)
            done.append((name, "appended"))
    return done


def config_text(root, old=None):
    """Schema-4 config preserving every supported scalar, including empty/custom commands."""
    old = old or {}
    cfg = {
        "schema_version": str(SCHEMA),
        "skill_version": VERSION,
        "protocol_version": old.get("protocol_version", "1"),
        "architecture": {"mode": "single"},
        "git": {
            "history_mode": "unknown",
            "commit": "auto",
            "push": old.get("git", {}).get("push_policy", "manual"),
        },
        "commands": {"test": "", "lint": "", "build": "", **detect_commands(root)},
    }
    for key, val in old.items():
        if key in cfg and isinstance(cfg[key], dict):
            cfg[key].update(val)
        elif key not in ("schema_version", "skill_version"):
            cfg[key] = val
    lines = [f"schema_version: {SCHEMA}", f'skill_version: "{VERSION}"']
    for key, val in cfg.items():
        if key in ("schema_version", "skill_version"):
            continue
        if isinstance(val, dict):
            lines += [f"\n{key}:"] + [f"  {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in val.items()]
        else:
            lines.append(f"{key}: {json.dumps(val, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def cmd_init(root):
    b, created = bp(root), []
    write_new(b / "config.yaml", config_text(root), created)
    write_new(b / "current.md", CURRENT_TMPL, created)
    write_new(b / "target.md", TARGET_TMPL, created)
    write_new(b / "constraints.md", CONSTRAINTS_TMPL, created)
    write_new(b / ".gitignore", ".cache/\n", created)
    (b / "tasks").mkdir(exist_ok=True)
    (b / "decisions").mkdir(exist_ok=True)
    for p in created:
        print(f"CREATED {Path(os.path.relpath(p, root)).as_posix()}")
    if not created:
        print("EXISTS: nothing overwritten")
    for name, action in ensure_pointers(root, write=True):
        print(f"POINTER {name} ({action})")
    print(
        "NEXT: Fill current.md (Runtime, Map, Domains+Sources from code), target.md (user intent; unknown -> "
        "Open Decisions), constraints.md, config commands. Then `new` per gap, then the genesis commit."
    )
    return 0


def cmd_new(root, title, depends, risk, priority=None, tier=None):
    if not brain_exists(root):
        print("NO_BRAIN: run `init` first")
        return 3
    with checkout_lock(root):
        tdir = bp(root) / "tasks"
        tdir.mkdir(exist_ok=True)
        nums = [int(TASK_FILE_RE.match(f.name).group(1)) for f in tdir.iterdir() if TASK_FILE_RE.match(f.name)]
        legacy = read(bp(root) / "migration-backup" / LEGACY_FILE) or ""
        nums += [int(n) for n in re.findall(r"^- \[[ xX~!\-]\]\s+T(\d+)", legacy, re.M)]
        every, _ = history_task_ids(root)
        nums += [int(i[3:]) for i in every]
        tid = norm_id("PB", max(nums, default=0) + 1)
        deps = [norm_id("PB", n) for n in re.findall(r"PB-(\d+)", depends or "")]
        status = "PLANNED"
        risk = risk or "MEDIUM"
        path = tdir / f"{tid}.md"
        with path.open("x", encoding="utf-8", newline="\n") as f:
            f.write(
                TASK_TMPL.format(
                    id=tid,
                    title=title,
                    status=status,
                    risk=risk,
                    priority=priority or "P2",
                    tier=tier or "M",
                    deps=", ".join(deps) or "-",
                )
            )
    print(f"CREATED {Path(os.path.relpath(path, root)).as_posix()} ({status})")
    print(
        "NEXT: Write it for a weaker model (SKILL.md section 3): Objective in the user's words, Areas, Domains, numbered "
        "Steps with exact paths, Acceptance checkboxes, Verify commands. Incomplete -> Status: PLANNED."
    )
    return 0


def cmd_start(root, task_id, agent="lead", takeover="", agents_path=None):
    import runtime_agents as A
    import runtime_verify as V

    if not brain_exists(root):
        print("NO_BRAIN")
        return 3
    with checkout_lock(root):
        task = find_task(root, task_id)
        actor = agent_id(agent, "--agent")
        import runtime_protocol as R
        R.guard(sys.modules[__name__], root, task)
        R.attempt_guard(sys.modules[__name__], root, task)
        policy = A.gate(sys.modules[__name__], task, actor, "start", agents_path, root=root) or {}
        all_tasks = list_tasks(root)
        pending = [t["id"] for t in all_tasks for e in t.get("external", [])
                   if e["state"] in ("sent", "response_unknown")]
        if pending:
            print("FAIL READBACK_FIRST unresolved external operations: " + ", ".join(sorted(set(pending))))
            return 2
        open_tasks = [t for t in all_tasks if t["status"] != "DONE" or not t["has_evidence"]]
        other_ip = [t["id"] for t in open_tasks if t["status"] == "IN_PROGRESS" and t["id"] != task["id"]]
        if other_ip:
            print(f"FAIL another task is already IN_PROGRESS: {', '.join(other_ip)}")
            return 2
        if task["status"] not in ("READY", "IN_PROGRESS", "REVIEW", "BLOCKED"):
            print(f"FAIL {task['id']} is {task['status']}: refine it to READY before starting")
            return 2
        errs = task_errors(task)
        if errs:
            print(f"FAIL {task['id']} is not an executable spec: {'; '.join(errs)}")
            return 2
        has_git = git(root, "rev-parse", "--is-inside-work-tree") == "true"
        local_done = {t["id"] for t in all_tasks if t["status"] == "DONE" and t["has_evidence"]}
        _, completed = history_task_ids(root) if has_git else (set(), set())
        done_ids = (completed | local_done) - {t["id"] for t in open_tasks}
        unmet = [d for d in task["deps"] if d not in done_ids]
        if unmet:
            print(f"FAIL {task['id']} has unmet dependencies: {', '.join(unmet)}")
            return 2
        cur_owner = task.get("owner", "")
        if cur_owner and cur_owner != actor and not takeover.strip():
            print(f'FAIL {task["id"]} is owned by {cur_owner}; pass --takeover "<reason>" to take over')
            return 2
        dig, count = V.task_digest(sys.modules[__name__], root, task)
        risk = max(V.effective_risk(sys.modules[__name__], task),
                   A.score_task(sys.modules[__name__], root, task)["effective_risk"],
                   key=RISK_VALUES.index)
        task["risk"] = risk
        con = contract(task)
        set_headers(task["file"], {"Status": "IN_PROGRESS", "Owner": actor, "Risk": risk})
        line = (
            f"- start: IN_PROGRESS | owner={actor} | risk={risk} | digest={dig} | contract={con}"
            + (f" | strength={policy['poolStrength']}" if policy.get("poolStrength") else "")
            + (f" | takeover={takeover.strip()}" if takeover.strip() else "")
        )
        append_section(task["file"], "Evidence", line)
        print(f"STARTED {task['id']} owner={actor} risk={risk} files={count} digest={dig} contract={con}")
        return 0


def cmd_changed(root):
    if git(root, "rev-parse", "--is-inside-work-tree") != "true":
        print("NO_GIT: cannot compute changes")
        return 1
    base = pb_base(root)
    if not base:
        print("NO_PB_COMMIT: reconcile the domains your task touches, then checkpoint")
        return 1
    stale, unmapped = staleness(root, base)
    if not stale and not unmapped:
        print("NO_CHANGES: no source changes since the applicable Current checkpoints")
        return 0
    for d, files in stale.items():
        print(f"STALE {d} ({len(files)}):")
        for f in files[:15]:
            print(f"  {f}")
        if len(files) > 15:
            print(f"  ... {len(files) - 15} more")
    if unmapped:
        print(f"UNMAPPED ({len(unmapped)}): not covered by any Sources glob")
        for f in unmapped[:20]:
            print(f"  {f}")
    print("NEXT: Inspect only these files; update the matching Current sections; checkpoint those domains.")
    return 0


def cmd_validate(root):
    import runtime_agents as A

    if not brain_exists(root):
        print("NO_BRAIN")
        return 3
    b, fails, warns = bp(root), [], []
    has_git = git(root, "rev-parse", "--is-inside-work-tree") == "true"
    cfg = parse_config(root)
    if not (b / "config.yaml").exists():
        warns.append("config.yaml missing (defaults used)")
    mode = cfg.get("architecture", {}).get("mode", "single")
    if mode == "domains" and not (b / "current").is_dir():
        fails.append("config mode=domains but current/ missing")
    if mode == "single" and (b / "current").is_dir() and not (b / "current.md").exists():
        warns.append("config mode=single but only current/ exists")
    cur = current_files(root)
    if not cur:
        fails.append("no current architecture (current.md or current/*.md)")
    for f, _ in cur:
        n = len((read(f) or "").splitlines())
        if n > BUDGETS["current"]:
            warns.append(f"{f.name}: {n} lines > {BUDGETS['current']} (split by domain or trim)")
    for f in [f for f, _ in cur] + [b / "target.md"]:
        if any(p in (read(f) or "") for p in PLACEHOLDERS):
            warns.append(f"{f.name}: unfilled template placeholders")
    if not (b / "target.md").exists():
        warns.append("target.md missing (global Goal and Status are required, including in domain mode)")
    elif (b / "target.md").exists() and target_status(root) == "UNSET":
        warns.append("target.md has no `Status: DRAFT|CONFIRMED` line")
    legacy = legacy_kind(root)
    if legacy:
        warns.append(f"schema {legacy[1:]}: run `migrate`")
    if (Path(root) / LEGACY_FILE).exists():
        warns.append(f"legacy {LEGACY_FILE} present: carry over anything unique, then delete it")
    for name, key in (("target.md", "target"), ("constraints.md", "constraints")):
        n = len((read(b / name) or "").splitlines())
        if n > BUDGETS[key]:
            warns.append(f"{name}: {n} lines > {BUDGETS[key]}")

    all_tasks = list_tasks(root)
    tasks = [t for t in all_tasks if t["status"] != "DONE" or not t["has_evidence"]]
    ids = {t["id"] for t in tasks}
    every, completed = history_task_ids(root) if has_git else (set(), set())
    completed |= {t["id"] for t in all_tasks if t["status"] == "DONE" and t["has_evidence"]}
    if len({t["id"] for t in all_tasks}) != len(all_tasks):
        fails.append("duplicate task IDs (including differently padded filenames)")
    for t in all_tasks:
        if t["status"] == "DONE" and not t["has_evidence"]:
            warns.append(f"{t['id']}: finished task file kept without Evidence; verify before checkpointing")
    if len(tasks) > BUDGETS["open_tasks"]:
        warns.append(f"{len(tasks)} open tasks > {BUDGETS['open_tasks']} (merge or defer distant work)")
    ip = [t["id"] for t in tasks if t["status"] == "IN_PROGRESS"]
    if len(ip) > 1:
        fails.append(f"multiple IN_PROGRESS: {', '.join(ip)}")
    adrs = set()
    if (b / "decisions").is_dir():
        adrs = {
            int(ADR_FILE_RE.match(f.name).group(1))
            for f in (b / "decisions").iterdir()
            if ADR_FILE_RE.match(f.name)
        }
    for t in tasks:
        tid = t["id"]
        if t["status"] not in STATUS_VALUES and t["status"] != "DONE":
            fails.append(f"{tid}: no valid status (first word must be {'|'.join(STATUS_VALUES)})")
        elif t["status_note"]:
            warns.append(f"{tid}: notes on the Status line; move them to Blocked:/Notes/Resume")
        if t["header_id"] and norm_id("PB", t["header_id"][0][3:]) != tid:
            warns.append(f"{tid}: title says {t['header_id'][0]}")
        if any(p in t["text"] for p in PLACEHOLDERS):
            warns.append(f"{tid}: unfilled template placeholders")
        if t["priority_raw"] and t["priority_raw"].upper()[:2] not in PRIORITY_VALUES:
            warns.append(f"{tid}: Priority must be P1|P2|P3")
        if t["tier_raw"] and t["tier"] not in TIER_VALUES:
            warns.append(f"{tid}: Tier must be L|M|H")
        if t["risk"] not in RISK_VALUES:
            warns.append(f"{tid}: Risk must be LOW|MEDIUM|HIGH")
        if t.get("bad_items"):
            warns.append(f"{tid}: unknown Acceptance kind tag: {', '.join(t['bad_items'])}")
        if t["status"] in ("READY", "IN_PROGRESS", "REVIEW"):
            missing = [
                n for n, ok in (
                    ("Steps", t["has_steps"]),
                    ("Acceptance checkboxes", t["checkboxes"]),
                    ("a backticked Verify command", t["verify_cmd"]),
                )
                if not ok
            ]
            if missing:
                warns.append(f"{tid}: {t['status']} but not an executable spec: missing {', '.join(missing)}")
            if t["vague"]:
                warns.append(f"{tid}: vague words in Steps/Acceptance: {', '.join(t['vague'])}")
            sinfo = A.score_task(sys.modules[__name__], root, t)
            if sinfo["missing_ui_triad"]:
                warns.append(
                    f"{tid}: UI task with typed Acceptance is missing Triad tag(s): "
                    + ", ".join(f"[{k}]" for k in sinfo["missing_ui_triad"])
                )
        if not t["has_acceptance"]:
            warns.append(f"{tid}: no Acceptance")
        if not t["has_verify"]:
            warns.append(f"{tid}: no Verify")
        if t["status"] == "BLOCKED" and not t["blocked"]:
            warns.append(f"{tid}: BLOCKED without 'Blocked:' reason")
        if t["status"] in ("IN_PROGRESS", "REVIEW") and not t["areas"]:
            warns.append(f"{tid}: {t['status']} without Areas (dirty files cannot be attributed)")
        if t.get("spec_lines", t["lines"]) > BUDGETS["task"]:
            warns.append(f"{tid}: executable spec exceeds {BUDGETS['task']} lines (split the task)")
        for d in t["deps"]:
            if d in ids:
                if t["status"] == "READY":
                    warns.append(f"{tid}: READY but depends on open {d}")
            elif d not in completed:
                warns.append(f"{tid}: depends on {d}, no verified completion evidence")
        for n in set(re.findall(r"ADR-(\d+)", t["text"])):
            if int(n) not in adrs:
                warns.append(f"{tid}: references missing ADR-{n}")

    adj, state = {t["id"]: [d for d in t["deps"] if d in ids] for t in tasks}, {}

    def cyclic(n):
        state[n] = 1
        for d in adj[n]:
            if state.get(d) == 1 or (d not in state and cyclic(d)):
                return True
        state[n] = 2
        return False

    for n in adj:
        if n not in state and cyclic(n):
            fails.append(f"dependency cycle involving {n}")
            break

    if has_git and (b / ".cache").is_dir() and git(root, "ls-files", f"{BRAIN_DIR}/.cache"):
        warns.append(".cache/ has tracked files (must be gitignored)")

    for f in fails:
        print(f"FAIL {f}")
    for w in warns:
        print(f"WARN {w}")
    print(
        f"{'OK' if not fails and not warns else 'SUMMARY'}: {len(tasks)} open tasks, "
        f"{len(adrs)} ADRs, {len(fails)} fail, {len(warns)} warn"
    )
    return 2 if fails else 1 if warns else 0


def cmd_doctor(root):
    import runtime_agents as A
    import runtime_verify as V

    print(f"PROJECT_BRAIN {VERSION} (schema {SCHEMA}) | python {sys.version.split()[0]} on {sys.platform}")
    try:
        with V.ProcessTree():
            containment = "Windows JobObject" if os.name == "nt" else "POSIX process group"
        print(f"CONTAINMENT: OK ({containment})")
    except Exception as exc:
        print(f"CONTAINMENT: FAIL ({exc})")
        return 2
    has_git = git(root, "rev-parse", "--is-inside-work-tree") == "true"
    print(f"GIT: {'OK' if has_git else 'NONE'}")
    reg = A.load()
    agents = reg.get("cli_agents") or {}
    print(f"CLI_AGENTS: {len(agents)} registered in {A.registry_path()} (run `agents scan` to refresh)")
    for cid, info in sorted(agents.items()):
        print(f"  - {cid}: {info.get('version', '?')} ({info.get('binary', '?')})")
    return 0


BOOLEAN_FLAGS = {
    "--apply", "--write", "--json", "--dry-run", "--force", "--no-quota", "--new", "--refresh", "--user-confirmed", "--prepare", "--verify", "--cleanup", "--self-review", "--read-only", "--enable", "--goal-independent", "--keep-evidence", "--rerun", "--scan", "--readback", "-h", "--help", "--version"
}


def _reorder_argv(argv):
    """Allow positional arguments (like <root> or <PB-NNN>) to appear either before or after --flags."""
    if not argv or argv[0].startswith("-"):
        return argv
    head_len = 2 if (argv[0] == "agents" and len(argv) > 1 and not argv[1].startswith("-")) else 1
    head = list(argv[:head_len])
    rest = list(argv[head_len:])
    pos, opts = [], []
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok == "--":
            pos.extend(rest[i + 1:])
            break
        if tok.startswith("-"):
            opts.append(tok)
            if "=" not in tok and tok not in BOOLEAN_FLAGS and i + 1 < len(rest):
                opts.append(rest[i + 1])
                i += 2
                continue
        else:
            pos.append(tok)
        i += 1
    return head + pos + opts


def _resolve_root_and_task(pos1, pos2, default_root="."):
    """Allow flexible positional order: `<cmd> <PB-NNN> [root]` OR `<cmd> <root> <PB-NNN>`."""
    if pos1 and re.match(r"^(?:PB-)?\d+$", pos1.strip(), re.I):
        return Path(pos2 or default_root).resolve(), pos1
    if pos2 and re.match(r"^(?:PB-)?\d+$", pos2.strip(), re.I):
        return Path(pos1 or default_root).resolve(), pos2
    if pos1 and Path(pos1).is_dir() and not pos2:
        return Path(pos1).resolve(), None
    if pos1 and not pos2:
        return Path(default_root).resolve(), pos1
    return Path(pos1 or default_root).resolve(), pos2


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import runtime_agents as A
    import runtime_verify as V

    ap = argparse.ArgumentParser(description="Project Brain planning and verification helper", epilog="See SKILL.md.")
    ap.add_argument("--version", action="version", version=f"project-brain {VERSION} (schema {SCHEMA})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("boot", "map", "init", "changed", "validate", "doctor"):
        parser = sub.add_parser(name)
        parser.add_argument("root", nargs="?", default=".")
        if name == "boot":
            parser.add_argument("--read-only", action="store_true")

    for name in ("protocol", "security"):
        p = sub.add_parser(name)
        p.add_argument("root", nargs="?", default=".")
        p.add_argument("--note", default="")
        if name == "protocol":
            p.add_argument("--enable", action="store_true")
        else:
            p.add_argument("--ref", default="")
            p.add_argument("--scan", action="store_true")
    for name in ("reconcile", "progress", "handoff"):
        p = sub.add_parser(name)
        p.add_argument("pos1")
        p.add_argument("pos2", nargs="?", default=".")
        if name == "reconcile":
            p.add_argument("--note", required=True)
            p.add_argument("--goal-independent", action="store_true")
            p.add_argument("--keep-evidence", action="store_true")
        if name == "progress":
            p.add_argument("--next", dest="next_step", required=True)
            p.add_argument("--failing", default="")
            p.add_argument("--dirty", default="")
            p.add_argument("--strategy", default="")

    p = sub.add_parser("new")
    p.add_argument("root")
    p.add_argument("title")
    p.add_argument("--depends", default="")
    p.add_argument("--risk", choices=RISK_VALUES, type=str.upper)
    p.add_argument("--priority", choices=PRIORITY_VALUES, type=str.upper)
    p.add_argument("--tier", choices=TIER_VALUES, type=str.upper)

    for mig_name in ("migrate", "upgrade"):
        p = sub.add_parser(mig_name)
        p.add_argument("root", nargs="?", default=".")
        p.add_argument("--apply", action="store_true")
        p.add_argument("--sync-skills", action="store_true")

    p = sub.add_parser("legacy")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--apply", action="store_true")
    phase = p.add_mutually_exclusive_group()
    phase.add_argument("--prepare", action="store_true")
    phase.add_argument("--verify", action="store_true")
    phase.add_argument("--cleanup", action="store_true")
    p.add_argument("--path", action="append", default=[])
    p.add_argument("--note", default="")
    p.add_argument("--archive-dir", default=None)

    p = sub.add_parser("start")
    p.add_argument("pos1")
    p.add_argument("pos2", nargs="?", default=".")
    p.add_argument("--agent", default="lead")
    p.add_argument("--takeover", default="")
    p.add_argument("--registry", default=None)

    p = sub.add_parser("check")
    p.add_argument("--rerun", action="store_true")
    p.add_argument("pos1")
    p.add_argument("pos2", nargs="?", default=".")
    p.add_argument("--timeout", type=float, default=None)
    p.add_argument("--as", dest="actor", default="")

    p = sub.add_parser("evidence")
    p.add_argument("pos1")
    p.add_argument("pos2", nargs="?", default=".")
    p.add_argument("--kind", required=True, type=str.lower)
    p.add_argument("--note", required=True)
    p.add_argument("--criterion", action="append", default=[])
    p.add_argument("--file", action="append", default=[])
    p.add_argument("--as", dest="actor", default="")

    p = sub.add_parser("review")
    p.add_argument("pos1")
    p.add_argument("pos2", nargs="?", default=".")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--verdict", required=True, type=str.upper)
    p.add_argument("--finding", action="append", default=[])
    p.add_argument("--self-review", action="store_true")
    p.add_argument("--registry", default=None)

    p = sub.add_parser("accept")
    p.add_argument("pos1")
    p.add_argument("pos2", nargs="?", default=".")
    p.add_argument("--as", dest="actor", default="")
    p.add_argument("--self-review", action="store_true")
    p.add_argument("--registry", default=None)

    p = sub.add_parser("score")
    p.add_argument("pos1", nargs="?", default=None)
    p.add_argument("pos2", nargs="?", default=None)
    p.add_argument("--write", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("delegate")
    p.add_argument("--readback", action="store_true")
    p.add_argument("--backend", choices=("pool", "direct"), default=None)
    p.add_argument("--group", choices=("high", "medium", "low"), default="")
    p.add_argument("pos1")
    p.add_argument("pos2", nargs="?", default=".")
    p.add_argument("--cli", default="")
    p.add_argument("--model", default="")
    p.add_argument("--effort", choices=A.EFFORTS, default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--registry", default=None)

    p_ag = sub.add_parser("agents")
    ag_sub = p_ag.add_subparsers(dest="agents_cmd", required=True)
    for pool_cmd in ("session", "approve", "revoke", "settle"):
        sp = ag_sub.add_parser(pool_cmd)
        if pool_cmd == "approve":
            sp.add_argument("file")
            sp.add_argument("--session", dest="session_id", required=True)
            sp.add_argument("--user-confirmed", action="store_true")
            sp.add_argument("--note", required=True)
        if pool_cmd == "settle":
            sp.add_argument("job_id")
            sp.add_argument("--state", choices=("completed", "failed"), required=True)
            sp.add_argument("--note", required=True)
        if pool_cmd == "session":
            sp.add_argument("--new", action="store_true")
            sp.add_argument("--refresh", action="store_true")
        sp.add_argument("root", nargs="?", default=".")
        sp.add_argument("--json", action="store_true")
        sp.add_argument("--registry", default=None)
    for ag_name in ("scan", "list", "quota"):
        sp = ag_sub.add_parser(ag_name)
        sp.add_argument("--backend", choices=("pool", "direct"), default=None)
        sp.add_argument("root", nargs="?", default=".")
        sp.add_argument("--json", action="store_true")
        sp.add_argument("--registry", default=None)
        if ag_name == "scan":
            sp.add_argument("--no-quota", action="store_true")
    sp_sel = ag_sub.add_parser("select")
    sp_sel.add_argument("--backend", choices=("pool", "direct"), default=None)
    sp_sel.add_argument("root", nargs="?", default=".")
    sp_sel.add_argument("--role", choices=A.ROLES, default="worker")
    sp_sel.add_argument("--tier", default="")
    sp_sel.add_argument("--risk", default="")
    sp_sel.add_argument("--task", default="")
    sp_sel.add_argument("--cli", default="")
    sp_sel.add_argument("--exclude", default="")
    sp_sel.add_argument("--json", action="store_true")
    sp_sel.add_argument("--registry", default=None)
    sp_mrg = ag_sub.add_parser("merge")
    sp_mrg.add_argument("file")
    sp_mrg.add_argument("root", nargs="?", default=".")
    sp_mrg.add_argument("--registry", default=None)
    sp_mode = ag_sub.add_parser("mode")
    sp_mode.add_argument("root", nargs="?", default=".")
    sp_mode.add_argument("--new", action="store_true")
    sp_mode.add_argument("--exec", dest="exec_mode", default="")
    sp_mode.add_argument("--rev", dest="rev_mode", default="")
    sp_mode.add_argument("--note", default="")
    sp_mode.add_argument("--json", action="store_true")

    a = ap.parse_args(_reorder_argv(sys.argv[1:]))
    B_mod = sys.modules[__name__]

    if a.cmd == "agents":
        if a.agents_cmd == "mode":
            root = Path(a.root).resolve()
            if a.exec_mode or a.rev_mode or a.note or a.new:
                with checkout_lock(root):
                    modes = set_session_modes(root, a.exec_mode, a.rev_mode, a.note, new=a.new)
            else:
                modes = get_session_modes(root)
            if a.json:
                print(json.dumps(modes, indent=2, ensure_ascii=False))
            else:
                print(f"SESSION_MODES: exec={modes['exec'] or 'ask'} rev={modes['rev'] or 'ask'}" + (f" ({modes['note']})" if modes.get("note") else ""))
            return 0
        if a.agents_cmd in ("scan", "list", "quota", "select") and (a.backend == "pool" or a.backend is None and a.registry is None):
            import runtime_agent_pool as AP
            return AP.agents(B_mod, a)
        return A.run_agents(B_mod, a)

    if a.cmd in ("protocol", "security"):
        import runtime_protocol as R
        import runtime_security as S
        root = Path(a.root).resolve()
        if not brain_exists(root):
            raise ValueError("Initialize Brain before configuring protocol/security")
        with checkout_lock(root):
            if a.cmd == "protocol":
                cfg = parse_config(root)
                if a.enable:
                    cfg["protocol_version"] = "1"
                    write_atomic(bp(root) / "config.yaml", config_text(root, cfg))
                print("PROTOCOL: " + ("1" if R.enabled(B_mod, root) else "0"))
            elif a.ref:
                print(json.dumps(S.configure(B_mod, root, a.ref, a.note), ensure_ascii=False))
            elif a.scan:
                files = git_paths(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR")
                if files is None:
                    raise ValueError("Staged scan requires Git")
                print("SCAN PASS: " + str(S.scan_staged(B_mod, root)) + " staged files; binary artifacts still require private-data inspection")
            else:
                print(json.dumps(S.policy(B_mod, root) or {"reference": "pending"}))
        return 0
    if a.cmd in ("reconcile", "progress", "handoff"):
        import runtime_protocol as R
        root, tid = _resolve_root_and_task(a.pos1, a.pos2)
        task = find_task(root, tid)
        if not task:
            raise ValueError("Task not found")
        with checkout_lock(root):
            if a.cmd == "reconcile":
                result = R.reconcile(B_mod, root, task, a.note, a.goal_independent, a.keep_evidence)
            elif a.cmd == "progress":
                result = R.progress(B_mod, root, task, a.next_step, a.failing, a.dirty, a.strategy)
            else:
                result = R.handoff(B_mod, root, task)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if a.cmd in ("start", "check", "evidence", "review", "accept", "score", "delegate"):
        root, tid = _resolve_root_and_task(a.pos1, a.pos2)
        if not root.is_dir():
            print(f"error: not a directory: {root}", file=sys.stderr)
            return 1
        if a.cmd == "score":
            if a.write:
                with checkout_lock(root):
                    return A.cmd_score(B_mod, root, tid=tid, write=True, as_json=a.json)
            return A.cmd_score(B_mod, root, tid=tid, write=a.write, as_json=a.json)
        if not tid:
            print(f"FAIL {a.cmd} requires a task ID (PB-NNN)", file=sys.stderr)
            return 2
        if a.cmd == "start":
            return cmd_start(root, tid, agent=a.agent, takeover=a.takeover, agents_path=a.registry)
        if a.cmd == "check":
            with checkout_lock(root):
                rc, lines = V.check(B_mod, root, tid, timeout=a.timeout, actor=a.actor, rerun=a.rerun)
            for l in lines:
                print(l)
            return rc
        if a.cmd == "evidence":
            with checkout_lock(root):
                rc, lines = V.evidence(
                    B_mod, root, tid, a.kind, a.note, files=a.file, actor=a.actor, criteria=a.criterion
                )
            for l in lines:
                print(l)
            return rc
        if a.cmd == "review":
            with checkout_lock(root):
                rc, lines = V.review(
                    B_mod, root, tid, a.reviewer, a.verdict, findings=a.finding, agents_path=a.registry, self_review=a.self_review
                )
            for l in lines:
                print(l)
            return rc
        if a.cmd == "accept":
            with checkout_lock(root):
                rc, lines = V.accept(B_mod, root, tid, actor=a.actor, agents_path=a.registry, self_review=a.self_review)
            for l in lines:
                print(l)
            return rc
        if a.cmd == "delegate":
            if os.environ.get("CLI_AGENT_POOL_WORKER"):
                raise ValueError("Pool workers cannot delegate recursively")
            if a.backend == "pool" or a.backend is None and a.registry is None:
                import runtime_agent_pool as AP
                task = find_task(root, tid)
                if not task:
                    raise ValueError("task not found")
                return AP.delegate(B_mod, root, task, A.score_task(B_mod, root, task), a)
            if a.readback:
                raise ValueError("Direct jobs use `agents session` and `agents settle` for readback; no worker launched")
            return A.delegate_task(
                B_mod,
                root,
                tid,
                cli_filter=a.cli,
                model_override=a.model,
                effort_override=a.effort,
                dry_run=a.dry_run,
                force=a.force,
                timeout=a.timeout,
                reg_path=a.registry,
            )

    root = Path(a.root).resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 1
    if a.cmd == "boot":
        if a.read_only:
            return cmd_boot(root, maintain=False)
        with checkout_lock(root):
            return cmd_boot(root)
    if a.cmd == "new":
        return cmd_new(root, a.title, a.depends, a.risk, a.priority, a.tier)
    if a.cmd in ("migrate", "upgrade"):
        import migrate
        with checkout_lock(root):
            return migrate.run(root, a.apply, sync_skills=getattr(a, "sync_skills", False))
    if a.cmd == "legacy":
        if a.prepare or a.verify or a.cleanup:
            import runtime_adopt as D
            if a.apply:
                raise ValueError("use import --apply separately before trace verification/cleanup")
            with checkout_lock(root):
                if a.prepare:
                    result = D.prepare(B_mod, root, a.path)
                elif a.verify:
                    rc = cmd_validate(root)
                    if rc != 0:
                        raise ValueError("adoption verification requires a valid, reconciled Brain")
                    result = D.verify(B_mod, root, a.note)
                else:
                    result = D.cleanup(B_mod, root, a.archive_dir)
            print(f"ADOPTION: {result['state']} trace={D.trace_file(B_mod, root)}")
            if result.get("archive"):
                print("ARCHIVE: " + str(result["archive"]))
            return 0
        return A.cmd_legacy(B_mod, root, apply=a.apply)
    return {
        "boot": cmd_boot,
        "map": cmd_map,
        "init": cmd_init,
        "changed": cmd_changed,
        "validate": cmd_validate,
        "doctor": cmd_doctor,
    }[a.cmd](root)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        sys.exit(2)
