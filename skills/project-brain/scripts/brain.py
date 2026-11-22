#!/usr/bin/env python3
"""project-brain 4.0 helper. Stdlib only, Python 3.8+.

  orient   [root]   Bounded metadata orientation + automatic safe state upgrade.
  boot     [root]   State, target, plan, focus, policy gate, files to load, next action.
  board    [root] [on|off|status] [--force]
                    Default-on zero-token Progress Board (İlerleme Panosu).
  brief    [root]   Read-only <=4 KiB continuity summary for intervening questions.
  watch    [root]   Token-thrifty 1-line status for timers/observers.
  setup    <ask|confirm|defaults|wait|recover-cap> [root]
                    Default-safe single-line session policy setup and CAP fallback.
  policy   [root]   View, quick-set, save, or confirm ESP, SP, QRP, and BRP.
  qualify  [root]   Optional advisory model task-fit override (non-blocking).
  quota    <status|assess|prepare|arm|resume|cancel> [root]
                    Opt-in director quota checkpoint and host wake guards (QRP).
  relay    <status|start|assess|next|handoff|takeover|complete|stop|recover> [root]
                    Opt-in Baton Relay Policy (BRP) director circulation via CAP.
  runs     <status|plan|prepare|submit|observe|wait|receipt|report|verify|integrate|cancel|...> [root]
                    Opt-in durable worker orchestration with isolated Git worktrees.
  map      [root]   Compact repository overview (genesis; replaces manual exploration).
  init     [root]   Create .project-brain/ skeleton. Never overwrites.
  new      [root] "title" [--priority P1|P2|P3] [--tier L|M|H] [--risk LOW|MEDIUM|HIGH] [--depends PB-001]
  intake   [root]   Record durable multi-item user directives or questions.
  reconcile/progress/handoff <task> [root]   Protocol 1 intent reconciliation and checkpoints.
  start    <task> [root] [--agent <alias>] [--takeover "<reason>"]
  check    <task> [root] [--timeout <sec>] [--as <alias>] [--rerun]
  evidence <task> [root] --kind <kind> --note "<text>" [--criterion <id>] [--file <relpath>]
  review   <task> [root] --reviewer <alias> --verdict PASS|BLOCKED [--finding "SEVERITY: text"]
  accept   <task> [root] [--as <alias>]
  score    [task] [root] [--write] [--json]
  agents   <scan|list|quota|select|mode> ...   CLI Agent Pool (CAP) discovery & session modes.
  delegate <task> [root] [--readback] ...      Legacy CAP readback/compatibility path.
  protocol/security [root]   Protocol 1 toggle and secret-reference / staged-byte scanning.
  changed  [root]   Domains changed since their Current checkpoints.
  validate [root]   Structural, executable-spec, UI/Backend quality, and size-budget checks.
  migrate  [root] [--apply]   Convert legacy Brain (schema <=3 or PROJECT_BRAIN.md).
  legacy   [root] [--apply|--prepare|--verify|--cleanup]   Foreign tracker adoption.
  doctor   [root]   Verify Python runtime, ProcessTree containment, Git, and CAP readiness.

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
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import migrate as M
import runtime_actors as A
import runtime_adopt as D
import runtime_agent_pool as AP
import runtime_control as CT
import runtime_core as Core
import runtime_executor_policy as E
import runtime_orchestration as O
import runtime_protocol as R
import runtime_quota_recovery as Q
import runtime_relay as RL
import runtime_scoring as SC
import runtime_security as S
import runtime_session as RS
import runtime_setup as SU
import runtime_verify as V

M.bind(sys.modules[__name__])

VERSION = Core.VERSION
SCHEMA = Core.SCHEMA
BRAIN_DIR = Core.BRAIN_DIR
LEGACY_FILE = Core.LEGACY_FILE
STATUS_VALUES = ("IN_PROGRESS", "REVIEW", "READY", "PLANNED", "BLOCKED")
RISK_VALUES = ("LOW", "MEDIUM", "HIGH")
PRIORITY_VALUES = ("P1", "P2", "P3")
TIER_VALUES = ("L", "M", "H")
EXEC_MODES = ("mixed", "pool_mixed", "pool_med_low", "pool_low", "self_mixed", "self_and_lower", "solo")
REV_MODES = EXEC_MODES
MODE_ALIASES = {
    "mixed": "mixed",
    "pool": "pool_mixed", "pool-all": "pool_mixed", "pool-medium": "pool_med_low",
    "native": "self_mixed", "native-low": "self_and_lower",
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
    """Run git with secret-scrubbed env; return stdout (right-stripped) or None on failure."""
    return Core.run_git(root, *args, timeout=timeout)


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
    Core.write_atomic(path, content)


@contextmanager
def checkout_lock(root, timeout=15.0, name="writer.lock"):
    """OS-released lock; serializes operations even before .project-brain/ exists."""
    with Core.project_lock(root, timeout=timeout, name=name):
        yield


@contextmanager
def startup_lock(root):
    """Lock BEFORE validating or creating .project-brain/ during startup upgrades."""
    M.require_supported(root)
    if merge_op(root):
        yield
        return
    kind = legacy_kind(root)
    needs_upgrade = bool(kind)
    if not needs_upgrade and brain_exists(root):
        cfg = parse_config(root)
        needs_upgrade = cfg.get("skill_version", "") != VERSION or M.has_pending_upgrade(root, force_all=False)
    if not needs_upgrade:
        yield
        return
    with checkout_lock(root):
        M.require_supported(root)
        M.require_known_legacy(root)
        if legacy_kind(root) == "v0":
            Core.public_path(root, BRAIN_DIR).mkdir(parents=True, exist_ok=True)
        yield


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
    return Core.public_path(root, BRAIN_DIR + "/.cache/session_modes.json")


def get_session_modes(root):
    out = {"exec": "", "rev": "", "note": "", "schedule": "serial", "max_parallel": 1, "task_mode": "execute"}
    if os.environ.get("PB_EXEC_MODE"):
        out["exec"] = normalize_mode(os.environ["PB_EXEC_MODE"], "exec")
    if os.environ.get("PB_REV_MODE"):
        out["rev"] = normalize_mode(os.environ["PB_REV_MODE"], "rev")
    if brain_exists(root):
        try:
            p = session_modes_file(root)
            if p.is_file():
                data = Core.read_json(p, max_bytes=65536, strict_constants=True)
                if isinstance(data, dict) and (not os.environ.get("PB_SESSION_ID") or data.get("session_id") == os.environ["PB_SESSION_ID"]):
                    if not out["exec"] and data.get("exec"):
                        out["exec"] = normalize_mode(str(data["exec"]), "exec")
                    if not out["rev"] and data.get("rev"):
                        out["rev"] = normalize_mode(str(data["rev"]), "rev")
                    out["note"] = str(data.get("note", ""))
                    if data.get("schedule") in ("serial", "parallel"):
                        out["schedule"] = data["schedule"]
                    if type(data.get("max_parallel")) is int and 1 <= data["max_parallel"] <= 32:
                        out["max_parallel"] = data["max_parallel"]
                    if data.get("task_mode") in ("response", "execute"):
                        out["task_mode"] = data["task_mode"]
        except (ValueError, OSError):
            pass
    out.update(E.settings(sys.modules[__name__], root))
    return out


def set_session_modes(root, exec_mode="", rev_mode="", note="", new=False, schedule=None, max_parallel=None, task_mode=None):
    cur = {"exec": "", "rev": "", "note": "", "schedule": "serial", "max_parallel": 1, "task_mode": "execute"} if new else get_session_modes(root)
    cur["session_id"] = os.environ.get("PB_SESSION_ID", "")
    if exec_mode:
        cur["exec"] = normalize_mode(exec_mode, "exec")
    if rev_mode:
        cur["rev"] = normalize_mode(rev_mode, "rev")
    elif exec_mode:
        cur["rev"] = cur["exec"]
    if note:
        cur["note"] = note.strip()
    if schedule is not None:
        if schedule not in ("serial", "parallel"):
            raise ValueError("schedule must be serial or parallel")
        cur["schedule"] = schedule
    if max_parallel is not None:
        if type(max_parallel) is not int or not 1 <= max_parallel <= 32:
            raise ValueError("max_parallel must be 1..32")
        cur["max_parallel"] = max_parallel
    if cur["schedule"] == "serial":
        cur["max_parallel"] = 1
    elif schedule == "parallel" and max_parallel is None and cur["max_parallel"] == 1:
        cur["max_parallel"] = 4
    if task_mode is not None:
        if task_mode not in ("response", "execute"):
            raise ValueError("task_mode must be response or execute")
        cur["task_mode"] = task_mode
    p = session_modes_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    if bp(root).is_dir() and not (bp(root) / ".gitignore").exists():
        write_atomic(bp(root) / ".gitignore", ".cache/\n")
    write_atomic(p, json.dumps(cur, indent=2, ensure_ascii=False))
    return cur


def require_session(root, implementation=False, allow_stopping=False):
    E.require_confirmed(sys.modules[__name__], root)
    if Q.status(sys.modules[__name__], root)["status"] in ("PREPARED", "ARMED"):
        raise ValueError("QRP_WAIT: read back/resume or cancel director recovery before new work")
    RL.require_free_or_director(sys.modules[__name__], root, allow_stopping=allow_stopping)
    modes = get_session_modes(root)
    if not modes["exec"] or not modes["rev"]:
        hint = "`setup confirm` / `policy --confirm`" if E.load(sys.modules[__name__], root) else "`setup confirm` or `agents mode`"
        raise ValueError(f"SESSION_CHOICE_REQUIRED: confirm session policy before implementation; use {hint}")
    if implementation and modes["task_mode"] == "response":
        raise ValueError("RESPONSE_ONLY: session permits analysis; switch task-mode to execute before implementation")
    return modes


ACCEPT_RE = re.compile(r"^- accept: DONE \| digest=(?P<digest>[0-9a-f]+) \| contract=(?P<contract>[0-9a-f]+)$")


def _is_generated_noise(path):
    return Core.is_generated_noise(str(path or ""))


def _cached_task_digest(root, task, digest_cache=None):
    """Compute read-only task_digest at most once per task within a single command."""
    tid = task["id"]
    if digest_cache is not None and tid in digest_cache:
        val = digest_cache[tid]
        if isinstance(val, Exception):
            raise val
        return val
    try:
        res = V.task_digest(sys.modules[__name__], root, task, check_session=False)
    except ValueError as exc:
        if digest_cache is not None:
            digest_cache[tid] = exc
        raise
    if digest_cache is not None:
        digest_cache[tid] = res
    return res


def _done_task_intact(root, task, digest_cache=None):
    """True only when an uncommitted DONE task's current digest and contract still match its recorded `accept`."""
    if task.get("status") != "DONE" or not task.get("areas"):
        return False
    accepted = None
    for line in task.get("evidence_lines", []):
        m = ACCEPT_RE.match(line)
        if m:
            accepted = m
    if not accepted or accepted.group("contract") != contract(task):
        return False
    try:
        cur_dig, _ = _cached_task_digest(root, task, digest_cache=digest_cache)
    except ValueError:
        return False
    return cur_dig == accepted.group("digest")


def takeover_status(root, active, has_git, dirty_other, done_tasks=(), intact_done=None, digest_cache=None):
    """Determine whether the takeover test suite must run or can be skipped to save tokens."""
    if not has_git:
        return "REQUIRED (no git baseline)"
    real_dirty = [p for p in dirty_other if not _is_generated_noise(p)]
    if intact_done is None:
        intact_done = [dt for dt in done_tasks if _done_task_intact(root, dt, digest_cache=digest_cache)]
    done_areas = [a for dt in intact_done for a in dt.get("areas", [])]
    outside = [
        p
        for p in real_dirty
        if not (active and any(matches(p, a) for a in active.get("areas", [])))
        and not any(matches(p, a) for a in done_areas)
    ]
    if outside:
        return "REQUIRED (source edits outside active Areas)"
    if active and active.get("areas"):
        try:
            cur_dig, _ = _cached_task_digest(root, active, digest_cache=digest_cache)
            cur_con = contract(active)
            if active.get("verify_cmds"):
                if V.current_checks(sys.modules[__name__], root, active, cur_dig, cur_con):
                    done_note = (
                        f"; uncommitted DONE pending commit: {','.join(dt['id'] for dt in intact_done)}"
                        if intact_done
                        else ""
                    )
                    return f"SKIP ({active['id']} Verify logs valid on current digest={cur_dig}; scoped checks reusable{done_note})"
        except ValueError:
            pass
    if real_dirty:
        if intact_done and not active:
            return f"SKIP (uncommitted DONE task edits present: {','.join(dt['id'] for dt in intact_done)}; commit or inspect)"
        return "REQUIRED (uncommitted source edits present)"
    head_body = git(root, "log", "-1", "--format=%B", "HEAD") or ""
    if not active and not is_wip(head_body) and "global" in trailer_values(head_body, "PB-Verification"):
        return "SKIP (clean tree at verified checkpoint HEAD; do not re-run test suite)"
    return "REQUIRED (run once before new edits)"


def proven_criteria_ids(root, task, digest_cache=None):
    """Return set of criterion IDs already proven on current source digest and contract."""
    if not task or not task.get("areas"):
        return set()
    if not any(it.get("kind") != "machine" for it in task.get("items", [])):
        return set()
    ev_lines = task.get("evidence_lines", [])
    if not ev_lines or not any(V.EVIDENCE_RE.match(l) for l in ev_lines):
        return set()
    try:
        cur_dig, _ = _cached_task_digest(root, task, digest_cache=digest_cache)
    except ValueError:
        return set()
    cur_con = contract(task)
    return V.current_criteria(task, root, cur_dig, cur_con)


def sections(text):
    """{'': lines before first '## ', 'heading lower': lines}, ignoring headings inside fenced code blocks."""
    lines = text.splitlines()
    headings = list(Core.iter_markdown_headings(lines))
    out = {"": lines[: headings[0][0]] if headings else lines}
    for pos, (idx, name) in enumerate(headings):
        end = headings[pos + 1][0] if pos + 1 < len(headings) else len(lines)
        out.setdefault(name.lower(), []).extend(lines[idx + 1 : end])
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
    """Append a bullet line to `## <heading>` outside fenced code blocks, creating it before `## Notes` if absent."""
    text = read(path) or ""
    lines = text.splitlines()
    headings = list(Core.iter_markdown_headings(lines))
    target_h = heading.strip().lower()
    pos = next((p for p, (_, name) in enumerate(headings) if name.lower() == target_h), None)
    if pos is None:
        notes_idx = next((idx for idx, name in headings if name.lower() == "notes"), None)
        block = ["", f"## {heading}", line]
        if notes_idx is not None:
            lines = lines[:notes_idx] + block + [""] + lines[notes_idx:]
        else:
            lines = lines + block
    else:
        idx = headings[pos][0]
        next_h = headings[pos + 1][0] if pos + 1 < len(headings) else len(lines)
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
    if SC.task_surface(task)["ui"]:
        kinds = {item["kind"] for item in task.get("items", [])}
        missing = [k for k in ("visual", "interaction", "accessibility") if k not in kinds]
        if missing:
            errs.append("UI task missing Triad tag(s): " + ", ".join(f"[{k}]" for k in missing))
    return errs


def list_tasks(root):
    d = bp(root) / "tasks"
    if not d.is_dir() or Core.is_link(d):
        return []
    tasks = []
    for f in d.iterdir():
        if TASK_FILE_RE.match(f.name) and not Core.is_link(f):
            parsed = parse_task(f)
            if parsed:
                tasks.append(parsed)
    return sorted(tasks, key=lambda t: int(t["id"][3:]))


def load_task(root, task_id):
    try:
        tid = norm_id("PB", task_id)
        p = Core.public_path(root, BRAIN_DIR + "/tasks/" + tid + ".md")
    except ValueError:
        return None
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
            if not p.startswith(BRAIN_DIR + "/") and not _is_generated_noise(p)
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
    for dp, dns, fns in os.walk(root, followlinks=False):
        base = Path(dp)
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not Core.is_link(base / d)]
        rel = os.path.relpath(dp, root).replace(os.sep, "/")
        files += [fn if rel == "." else f"{rel}/{fn}" for fn in fns if not Core.is_link(base / fn)]
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
    try:
        rel = Path(path).relative_to(root).as_posix()
        file = Core.public_path(root, rel)
        if not file.is_file():
            return False
        head = git(root, "rev-parse", "--verify", "HEAD:" + rel)
        index = git(root, "rev-parse", "--verify", ":" + rel)
        actual = git(root, "hash-object", "--path=" + rel, rel)
        return bool(head and head == index == actual)
    except (ValueError, OSError):
        return False


def watch_status(root, heal=False):
    """Token-thrifty, lightweight 1-line status for observers/watchdogs (zero full-file hashing)."""
    root = Path(root).resolve()
    now_iso = Core.now_iso()
    tasks = list_tasks(root)
    total_tasks = len(tasks)
    # Match boot & brief: IN_PROGRESS takes precedence over REVIEW.
    active = next((t for st in ("IN_PROGRESS", "REVIEW") for t in tasks if t["status"] == st), None)
    done_count = sum(1 for t in tasks if t["status"] == "DONE")
    left_count = total_tasks - done_count
    rem_pct = int(round((left_count / total_tasks * 100))) if total_tasks > 0 else 0
    cur_str = "none"
    if active:
        tid = active["id"]
        items = active.get("items", [])
        if items:
            done_items = sum(1 for it in items if it.get("done"))
            stage_pct = int(round((done_items / len(items)) * 100))
        else:
            stage_pct = 50 if active["status"] == "REVIEW" else 25
        cur_str = "%s(%s,%d%%)" % (tid, active["status"], stage_pct)
    modes = get_session_modes(root)
    mode_str = modes.get("exec") or "unset"
    route_str = "host"
    quota_str = "?"
    if mode_str == "mixed" or mode_str.startswith("pool_"):
        pool_str = "pool"
    elif mode_str in ("solo", "unset"):
        pool_str = mode_str
    else:
        pool_str = "native"
    relay_st = None
    try:
        relay_st = RL.read(sys.modules[__name__], root)
    except Exception:
        pass
    if relay_st and relay_st.get("status") in RL.BLOCKING and relay_st.get("director"):
        d = relay_st["director"]
        route_str = d.get("route", "route")
        if d.get("model"):
            route_str += "/" + d["model"].split("/")[-1]
        pool_str = "relay:" + relay_st["status"].lower()
    heal_note = ""
    if heal:
        # Never unlink OS lock inodes; only report active runs needing readback.
        try:
            pending_runs = O.L.peek(sys.modules[__name__], root)
            if pending_runs:
                heal_note = " | runs:%d" % len(pending_runs)
        except Exception:
            pass
    return "%s | %s/%s/%s/%s | cur:%s | rem:%d%%(%d/%d)%s" % (
        now_iso, mode_str, route_str, quota_str, pool_str, cur_str, rem_pct, left_count, total_tasks, heal_note
    )


def gc_brain(root, has_git=None, completed=None):
    """Collect only recoverable closed work; preserve unknown/active recovery inputs."""
    root = Path(root)
    b = Core.public_path(root, BRAIN_DIR)
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
        if task["status"] == "DONE" and task["has_evidence"] and task["id"] in completed and committed_exact(root, task["file"]):
            try:
                task["file"].unlink()
                removed.append(f"tasks/{task['id']}.md")
            except FileNotFoundError:
                pass
    retained = {t["id"] for t in list_tasks(root)}
    closed = completed - retained
    active_checkpoints = set()
    try:
        st = RL.read(sys.modules[__name__], root)
        if st:
            for cp in ((st.get("pending") or {}).get("checkpoint"), st.get("last_checkpoint")):
                if cp and cp.get("path"):
                    parts = Path(cp["path"]).parts
                    if len(parts) >= 3 and parts[0] == BRAIN_DIR and parts[1] == "evidence":
                        active_checkpoints.add(parts[2])
    except Exception:
        pass
    root_abs = Path(root).resolve()
    ev_root = Core.public_path(root_abs, BRAIN_DIR + "/evidence")
    if ev_root.is_dir():
        for directory in sorted(ev_root.iterdir()):
            if not re.fullmatch(r"PB-\d{3,}", directory.name) or directory.name not in closed or directory.name in active_checkpoints:
                continue
            if (directory / "handoff.json").exists():
                continue
            try:
                Core.public_path(root_abs, directory.relative_to(root_abs).as_posix())
                if not directory.is_dir():
                    continue
                files = Core.iter_files(directory)
                has_link = False
                for dp, dns, fns in os.walk(str(directory), topdown=True, followlinks=False):
                    base_d = Path(dp)
                    if any(Core.is_link(base_d / entry) for entry in dns + fns):
                        has_link = True
                        break
                if has_link:
                    continue
                if all(committed_exact(root, f) for f in files):
                    shutil.rmtree(directory)
                    removed.append(f"evidence/{directory.name}/")
            except (ValueError, OSError):
                continue
    runs = Core.public_path(root, BRAIN_DIR + "/.cache/runs")
    if runs.is_dir():
        for file in sorted(runs.iterdir()):
            match = re.match(r"^(PB-\d{3,})-", file.name)
            if match and match.group(1) in closed and file.is_file() and not Core.is_link(file):
                try:
                    file.unlink()
                    removed.append(".cache/runs/" + file.name)
                except FileNotFoundError:
                    pass
    V.prune_runs(sys.modules[__name__], root)
    return removed


BOARD_ON_TOKENS = {"on", "show", "true", "1", "yes", "enable", "enabled", "goster", "göster", "ac", "aç"}
BOARD_OFF_TOKENS = {"off", "hide", "false", "0", "no", "disable", "disabled", "gosterme", "gösterme", "gizle", "kapat"}
BOARD_ACTIONS = BOARD_ON_TOKENS | BOARD_OFF_TOKENS | {"status"}


def board_enabled(root):
    if not brain_exists(root):
        return False
    try:
        raw = str(parse_config(root).get("board", "on")).strip().lower()
    except ValueError:
        return True
    return raw not in BOARD_OFF_TOKENS


def _set_config_scalar(root, key, value):
    """Update or insert a top-level scalar in config.yaml without stripping comments or rewriting other keys."""
    cfg_path = Core.public_path(root, BRAIN_DIR + "/config.yaml")
    if not cfg_path.exists():
        cfg = parse_config(root)
        cfg[key] = value
        write_atomic(cfg_path, config_text(root, cfg))
        return
    raw = read(cfg_path) or ""
    rendered = f"{key}: {json.dumps(value, ensure_ascii=False)}"
    lines = raw.splitlines()
    pat = re.compile(rf"^{re.escape(key)}:\s*.*$")
    for idx, line in enumerate(lines):
        if pat.match(line):
            lines[idx] = rendered
            write_atomic(cfg_path, "\n".join(lines) + "\n")
            return
    insert_at = 0
    for idx, line in enumerate(lines):
        if re.match(r"^(?:schema_version|skill_version|protocol_version):", line):
            insert_at = idx + 1
    lines.insert(insert_at, rendered)
    write_atomic(cfg_path, "\n".join(lines) + "\n")


def _compact_owner(owner_str):
    s = (owner_str or "").strip()
    if not s or s == "-":
        return ""
    if re.fullmatch(r"pool/[0-9a-f]{24}", s):
        return s[:13]
    return s[:28]


def board_lines(root, focus_id=None, all_tasks=None, hist_done=None, digest_cache=None):
    """Zero-token deterministic Progress Board for all chat & CLI agents."""
    if not brain_exists(root):
        return []
    if all_tasks is None:
        all_tasks = list_tasks(root)
    if hist_done is None:
        has_git = git(root, "rev-parse", "--is-inside-work-tree") == "true"
        _, hist_done = history_task_ids(root) if has_git else (set(), set())
    if digest_cache is None:
        digest_cache = {}
    disk_ids = {t["id"] for t in all_tasks}
    gc_done_ids = sorted(hist_done - disk_ids, key=lambda tid: int(tid[3:]))
    total_tasks = len(gc_done_ids) + len(all_tasks)
    if total_tasks == 0:
        phase = "INTAKE" if target_status(root) != "CONFIRMED" else "PLANNING"
        return [f"PROGRESS_BOARD: [░░░░░░░░░░] 0% | {phase} | Tasks 0/0 | Criteria 0/0"]

    orch_tasks = O.L.board_summary(sys.modules[__name__], root)
    norm_focus = ""
    if focus_id:
        try:
            norm_focus = norm_id("PB", focus_id)
        except ValueError:
            norm_focus = str(focus_id)
    else:
        active = next((t for st in ("IN_PROGRESS", "REVIEW") for t in all_tasks if t["status"] == st), None)
        norm_focus = active["id"] if active else ""

    prio_rank = {"P1": 0, "P2": 1, "P3": 2}
    rows, weights = [], []
    done_tasks = len(gc_done_ids)
    total_c_done, total_c_total = 0, 0
    for t in all_tasks:
        tid = t["id"]
        st = t["status"]
        has_accept = any(ACCEPT_RE.match(l) for l in t.get("evidence_lines", []))
        done_tampered = False
        done_unproven = False
        if st == "DONE":
            if not t["has_evidence"]:
                is_done, done_unproven = False, True
            elif has_accept and not _done_task_intact(root, t, digest_cache=digest_cache):
                is_done, done_tampered = False, True
            else:
                is_done = True
        else:
            is_done = False
        if is_done:
            done_tasks += 1

        proven = set() if is_done else proven_criteria_ids(root, t, digest_cache=digest_cache)
        items = t.get("items", [])
        c_total = len(items)
        c_done = c_total if is_done else sum(1 for it in items if it["done"] or it["id"] in proven)
        total_c_done += c_done
        total_c_total += c_total
        if c_total == 0:
            crit_str = "0/0"
        elif c_total <= 5:
            pills = " ".join(
                f"C{idx}{'✓' if (is_done or it['done'] or it['id'] in proven) else '·'}"
                for idx, it in enumerate(items, 1)
            )
            crit_str = f"{c_done}/{c_total} ({pills})"
        else:
            crit_str = f"{c_done}/{c_total}✓"

        if is_done:
            w = 1.0
        elif done_tampered or done_unproven:
            w = 0.5
        elif st == "REVIEW":
            w = 0.9
        elif c_total > 0:
            w = max((c_done / c_total) * 0.85, 0.15 if st == "IN_PROGRESS" else 0.0)
        else:
            w = 0.25 if st == "IN_PROGRESS" else 0.0
        weights.append(w)

        orec = orch_tasks.get(tid) if isinstance(orch_tasks.get(tid), dict) else {}
        if orec.get("worker"):
            ostate = orec.get("state", "")
            okind = orec.get("kind", "")
            badge = f"{okind}:{ostate}" if okind == "REVIEW" else ostate
            owner_str = _compact_owner(orec["worker"]) + (f"[{badge}]" if badge else "")
        else:
            owner_str = _compact_owner(t.get("owner") or "")

        rev_valid = False
        if not is_done and st in ("IN_PROGRESS", "REVIEW"):
            try:
                dig, _ = _cached_task_digest(root, t, digest_cache=digest_cache)
                rev_valid = V.review_status(sys.modules[__name__], root, t, dig, contract(t))["valid"]
            except ValueError:
                rev_valid = False

        if is_done:
            tail = "accept=DONE" if has_accept else "DONE"
        elif done_tampered:
            tail = "DONE tampered (reverify)"
        elif done_unproven:
            tail = "DONE without evidence"
        elif rev_valid:
            tail = "review=PASS (run accept)"
        elif st == "BLOCKED":
            tail = f"blocked={(t.get('blocked') or 'yes')[:24]}"
        elif st == "?":
            tail = "invalid Status (validate)"
        elif t.get("next"):
            tail = f"next={t['next'][:28]}"
        elif st == "IN_PROGRESS":
            tail = f"next=check ({c_done}/{c_total})" if c_total else "next=check"
        elif st == "REVIEW":
            tail = "next=review"
        elif st == "READY":
            tail = "next=start"
        else:
            tail = f"deps={','.join(t.get('deps') or []) or '-'}"

        if is_done:
            icon, bucket = "✓", 4
        elif done_tampered or done_unproven or st in ("BLOCKED", "?"):
            icon, bucket = "!", 1
        elif tid == norm_focus or st in ("IN_PROGRESS", "REVIEW"):
            icon, bucket = "▶", 0
        elif st == "READY":
            icon, bucket = "○", 2
        else:
            icon, bucket = "○", 3
        title = (t.get("title") or tid)[:24]
        owner_seg = f" | @{owner_str}" if owner_str else ""
        num_id = int(tid[3:])
        p_ord = prio_rank.get(t.get("priority", "P2"), 1)
        rows.append((bucket, p_ord, num_id, f"  {icon} {tid} [{st}] {title} | {crit_str}{owner_seg} | {tail}"))

    earned = float(len(gc_done_ids)) + sum(weights)
    pct = min(100, max(0, int(round((earned / total_tasks) * 100)))) if total_tasks else 0
    filled = min(10, max(0, int(round(pct / 10.0))))
    bar = "█" * filled + "░" * (10 - filled)
    if done_tasks == total_tasks:
        phase = "COMPLETE"
    elif any(t["status"] == "REVIEW" for t in all_tasks):
        phase = "REVIEW"
    elif any(t["status"] == "IN_PROGRESS" for t in all_tasks) or done_tasks > 0:
        phase = "EXECUTION"
    elif any(t["status"] == "READY" for t in all_tasks):
        phase = "READY"
    else:
        phase = "PLANNING"

    crit_hdr = f"Criteria {total_c_done}/{total_c_total}" if total_c_total else (
        f"Closed {len(gc_done_ids)}" if gc_done_ids else "Criteria 0/0"
    )
    lines = [
        f"PROGRESS_BOARD: [{bar}] {pct}% | {phase} | Tasks {done_tasks}/{total_tasks} | {crit_hdr}"
    ]
    if gc_done_ids:
        sample = ", ".join(gc_done_ids[:4]) + (f" (+{len(gc_done_ids) - 4} more)" if len(gc_done_ids) > 4 else "")
        lines.append(f"  ✓ {sample} [DONE] (committed in Git)")
    shown = sorted(rows, key=lambda item: (item[0], item[1], item[2]))[:8]
    for _, _, _, rline in sorted(shown, key=lambda item: item[2]):
        lines.append(rline)
    if len(rows) > 8:
        lines.append(f"  ... (+{len(rows) - 8} more tasks)")
    return lines


def cmd_board(root, action=None, force=False):
    if not brain_exists(root):
        print("NO_BRAIN: run `init` first")
        return 3
    act = (action or "").strip().lower()
    if act in BOARD_ON_TOKENS:
        _require_not_worker(sys.modules[__name__], root, "`board on`")
        with checkout_lock(root):
            M.require_supported(root)
            if legacy_kind(root):
                raise ValueError("Upgrade legacy Brain (`orient`/`boot`) before changing board setting")
            RL.require_free_or_director(sys.modules[__name__], root)
            _set_config_scalar(root, "board", "on")
        print("BOARD: ON (Progress Board enabled by default)")
        for line in board_lines(root):
            print(line)
        return 0
    if act in BOARD_OFF_TOKENS:
        _require_not_worker(sys.modules[__name__], root, "`board off`")
        with checkout_lock(root):
            M.require_supported(root)
            if legacy_kind(root):
                raise ValueError("Upgrade legacy Brain (`orient`/`boot`) before changing board setting")
            RL.require_free_or_director(sys.modules[__name__], root)
            _set_config_scalar(root, "board", "off")
        print("BOARD: OFF (Progress Board hidden; run `brain.py board on` to show)")
        return 0
    if act and act != "status":
        raise ValueError(f"Unknown board action {action!r}; use `on` (`show`/`göster`) or `off` (`hide`/`gösterme`)")
    enabled = board_enabled(root)
    if act == "status":
        print("BOARD: " + ("ON" if enabled else "OFF"))
    if not enabled and not force:
        if act != "status":
            print("BOARD: OFF (Progress Board hidden; run `brain.py board on` to show)")
        return 0
    for line in board_lines(root):
        print(line)
    return 0


def cmd_boot(root, maintain=True, new_session=False):
    has_git = git(root, "rev-parse", "--is-inside-work-tree") == "true"
    maintain = maintain and not merge_op(root)
    auto_mig_notes = M.startup(root, maintain=maintain)
    legacy = legacy_kind(root)
    if legacy == "v0":
        print("STATE: LEGACY")
        print(f"  ! {LEGACY_FILE} (single-file Brain) found")
        print("NEXT: Upgrade deferred by read-only startup or Git operation. Normal orient/boot upgrades recognized legacy state automatically when that condition clears.")
        return 0
    if not brain_exists(root):
        foreign = D.detect_foreign(root)
        print("STATE: NO_BRAIN")
        for fname, fpaths in foreign:
            print(f"  ! foreign planning state detected: {fname} ({', '.join(fpaths)}) -> run `legacy` to preview adoption")
        print("NEXT: Substantial work -> WORKFLOW.md §7 Genesis (`map`, then `init`). Small request -> just do it.")
        return 0
    if new_session and maintain and RL.authorized(sys.modules[__name__], root):
        print("RELAY_SUCCESSOR: settings inherited; ask no setup questions and do not repeat recorded discovery/verification.")
    elif new_session and maintain:
        with checkout_lock(root):
            try:
                rel_st = RL.read(sys.modules[__name__], root)
            except ValueError:
                rel_st = None
            qrp_st = Q.status(sys.modules[__name__], root)
            if rel_st and rel_st.get("status") in RL.BLOCKING:
                print(f"RELAY_ACTIVE_PROTECTED: {rel_st.get('status')} relay owns this repository; session modes and policy receipt preserved.")
            elif qrp_st.get("status") in ("PREPARED", "ARMED"):
                print(f"QRP_ACTIVE_PROTECTED: {qrp_st.get('status')} quota recovery active; session modes and policy receipt preserved.")
            else:
                set_session_modes(root, new=True)
                E.begin_session(sys.modules[__name__], root)
    cfg = parse_config(root)
    every_ids, completed_ids = history_task_ids(root) if has_git else (set(), set())
    gc_needed = bool(maintain and not legacy and has_git and (completed_ids or (bp(root) / ".cache/runs").is_dir()))
    if gc_needed:
        with checkout_lock(root):
            gc_removed = gc_brain(root, has_git=has_git, completed=completed_ids)
    else:
        gc_removed = []
    if gc_removed:
        sample = ", ".join(gc_removed[:10])
        suffix = f" (+{len(gc_removed) - 10} more)" if len(gc_removed) > 10 else ""
        auto_mig_notes.append(f"GC_CLEANUP: removed {sample}{suffix}")
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
        notes.append(f"schema {legacy[1:]}: automatic upgrade deferred by read-only startup or Git operation")
    elif (Path(root) / LEGACY_FILE).exists():
        notes.append(f"legacy {LEGACY_FILE} still present: carry over anything unique, then delete it")

    unresolved_ext = [
        (t["id"], e["op"] or e["line"])
        for t in all_tasks
        for e in t.get("external", [])
        if e["state"] in ("sent", "response_unknown")
    ]
    if unresolved_ext:
        ext_sample = ", ".join(f"{tid}:{op}" for tid, op in unresolved_ext[:8])
        ext_more = f" (+{len(unresolved_ext) - 8} more)" if len(unresolved_ext) > 8 else ""
        notes.append("READBACK_FIRST unresolved external operations: " + ext_sample + ext_more)

    active = ip[0] if ip else (rev_tasks[0] if rev_tasks else None)
    done_tasks = [t for t in all_tasks if t["status"] == "DONE" and t["has_evidence"]]
    digest_cache = {}
    intact_done_tasks = []

    stale, unmapped, done, recent, since_audit = {}, [], set(), [], 0
    local_done = {t["id"] for t in done_tasks}
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
        other = [p for p in dirty if not p.startswith(BRAIN_DIR + "/") and not _is_generated_noise(p)]
        intact_done_tasks = [t for t in done_tasks if _done_task_intact(root, t, digest_cache=digest_cache)]
        owned = [p for p in other if active and any(matches(p, a) for a in active["areas"])]
        done_owned = [
            p for p in other
            if p not in owned and any(matches(p, a) for dt in intact_done_tasks for a in dt.get("areas", []))
        ]
        unowned = [p for p in other if p not in owned and p not in done_owned]
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
    s_modes = get_session_modes(root)
    try:
        E.require_confirmed(sys.modules[__name__], root)
        policy_ready = True
    except ValueError:
        policy_ready = False
    gate_ready = bool(s_modes["exec"] and s_modes["rev"] and policy_ready)
    print("SESSION_GATE: " + ("READY" if gate_ready else "CONFIRM_SESSION_POLICY"))
    print(f"WORK: {s_modes['task_mode']} | {s_modes['schedule']} | max_parallel={s_modes['max_parallel']}")
    if not gate_ready:
        print("SETUP_HINT: " + SU.summary_line(SU.defaults(sys.modules[__name__], root)) + " (run `setup ask` or `setup confirm`)")
    relay_line = RL.boot_line(sys.modules[__name__], root)
    if relay_line:
        print(relay_line)
    print("PROTOCOL: " + ("1 (intent/input guards active)" if R.enabled(sys.modules[__name__], root) else "0 (legacy compatibility; run `protocol --enable` before new implementation)"))
    print("SECRETS: " + (S.policy(sys.modules[__name__], root).get("reference") or "ASK_ONCE: choose an external symbolic reference or none"))
    print(f"TAKEOVER_CHECK: {takeover_status(root, active, has_git, other, done_tasks=done_tasks, intact_done=intact_done_tasks, digest_cache=digest_cache)}")
    RS.boot_summary(sys.modules[__name__], root)
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
    focus_rev_valid = False
    if focus:
        n_open = len(focus["open_items"])
        progress = (
            f"{n_open}/{focus['checkboxes']} acceptance open"
            if focus["checkboxes"]
            else "acceptance has no checkboxes"
        )
        sinfo = SC.score_task(sys.modules[__name__], root, focus)
        del_hint = "delegatable->`runs`" if sinfo["delegatable"] else f"role={sinfo['recommended_role']}"
        print(
            f"FOCUS {focus['id']} ({focus['status']}, {focus['priority']}, tier {focus['tier'] or '?'}->{sinfo['effective_tier']}, "
            f"risk {focus['risk'] or '?'}->{sinfo['effective_risk']}, score {sinfo['score']}/100, effort {sinfo['recommended_effort']}, {del_hint}): {progress}"
        )
        if focus["next"]:
            print(f"  next: {focus['next']}")
        if R.enabled(sys.modules[__name__], root):
            try:
                R.guard(sys.modules[__name__], root, focus, check_session=False)
                print(
                    "  intent: reconciled with current target/constraints"
                    + ("" if gate_ready else " (confirm session policy first)")
                )
            except ValueError as error:
                print("  intent: " + str(error))
        try:
            focus_dig, _ = _cached_task_digest(root, focus, digest_cache=digest_cache)
            focus_con = contract(focus)
            rstat = V.review_status(sys.modules[__name__], root, focus, focus_dig, focus_con)
            if rstat["valid"]:
                focus_rev_valid = True
                pol_note = "" if gate_ready else "; confirm session policy first"
                print(f"  review: PASS valid on current digest={focus_dig} (DO NOT re-review; run `accept`{pol_note})")
        except ValueError:
            pass
        proven_ids = proven_criteria_ids(root, focus, digest_cache=digest_cache)
        if proven_ids:
            print(f"  proven on current digest (DO NOT repeat): {', '.join(sorted(proven_ids))}")
        open_objs = [it for it in focus["items"] if not it["done"] and it["id"] not in proven_ids]
        for it in open_objs[:5]:
            print(f"  - [ ] [{it['kind']}] {it['text'][:120]} (criterion {it['id']})")
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
            print(f"  ! {focus['id']} is not an executable spec (missing {', '.join(missing)}): write them first (WORKFLOW.md §3)")
    if promote:
        print(f"  hint: deps done, write full specs and set READY: {', '.join(promote)}")
    if since_audit >= 5:
        print(f"  hint: {since_audit} tasks closed since the last plan audit -> run Plan audit (WORKFLOW.md §6)")
    if board_enabled(root) and state not in ("INVALID", "LEGACY", "CONFLICTED"):
        for bline in board_lines(
            root,
            focus_id=focus["id"] if focus else None,
            all_tasks=all_tasks,
            hist_done=completed_ids,
            digest_cache=digest_cache,
        ):
            print(bline)
    if recent:
        print("RECENT: " + "; ".join(f"{ids} by {agent} ({sha})" for ids, agent, sha in recent))
    if stale or unmapped:
        stale_items = list(stale.items())
        for d, files in stale_items[:8]:
            print(f"STALE {d}: {', '.join(files[:5])}{' ...' if len(files) > 5 else ''}")
        if len(stale_items) > 8:
            print(f"STALE: ... {len(stale_items) - 8} more domains")
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
            matched = R.resolve_adr_files(sys.modules[__name__], root, n)
            if matched:
                load.append(matched[0])
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

    load_shown = [show(x) for x in load[:12]]
    if len(load) > 12:
        load_shown.append(f"(+{len(load) - 12} more)")
    print("LOAD: " + " ".join(load_shown))
    cmds = {k: v for k, v in cfg.get("commands", {}).items() if v}
    if cmds:
        print("CMDS: " + " | ".join(f"{k}={v}" for k, v in cmds.items()))
    git_cfg = cfg.get("git", {})
    print(f"MODE: commit={git_cfg.get('commit', 'auto')} push={git_cfg.get('push', git_cfg.get('push_policy', 'manual'))}")

    nxt = {
        "READBACK_FIRST": "Inspect unresolved external operations with their readback tool; record confirmed/failed before starting or retrying work.",
        "LEGACY": "Normal orient/boot automatically upgrades recognized legacy state after read-only/Git-operation deferral clears. Inspect unknown formats before explicit migration.",
        "INVALID": "Run `validate`, fix the FAIL lines, then boot again (REFERENCE: Corrupt Brain).",
        "CONFLICTED": "Finish the Git operation first (REFERENCE: Conflicts). Start no task.",
        "DIRTY": "Classify each listed path: mine/user/generated/unknown. Never reset/clean/stash/checkout unknown work. Continue only on non-overlapping files.",
        "INTERRUPTED": f"Resume {active['id'] if active else ''}: check `git status --short` (including untracked files) and `git diff --stat` against Resume, then continue at the first open acceptance item.",
        "ADVANCED": "Route the user's request first. For authorized implementation, inspect relevant STALE/UNMAPPED files and reconcile Current before checkpointing.",
    }.get(state)
    if not nxt:
        if focus and focus["status"] == "REVIEW" and focus_rev_valid:
            nxt = (
                f"Review PASS valid on current digest for {focus['id']}: "
                f"{'' if gate_ready else 'confirm session policy (`setup confirm`), then '}"
                f"run `accept {focus['id']}` and commit (DO NOT re-review)."
            )
        elif focus and focus["status"] == "REVIEW":
            nxt = f"REVIEW {focus['id']}: an independent reviewer agent that did not implement {focus['id']} runs `review {focus['id']} --reviewer <alias> --verdict PASS|BLOCKED`, then `accept {focus['id']}`."
        elif focus:
            nxt = (
                f"Confirm session policy if pending (`setup confirm`). For authorized work, start "
                f"{focus['id']} (`start {focus['id']}` or `runs prepare --task {focus['id']}`) and keep working the queue."
            )
        elif promote:
            nxt = f"Route the user's request first; within its authorized scope, refine {promote[0]} to READY and start it."
        elif tasks and all(t["status"] == "BLOCKED" for t in tasks):
            nxt = "Every open task is BLOCKED: report blockers to the user and stop."
        elif tasks:
            nxt = "No startable task: fix statuses (`validate`) or refine a PLANNED task to READY."
        else:
            nxt = "Queue empty: handle the user's message, or run the Final audit (WORKFLOW.md §6)."
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
        Core.write_atomic(path, content)
        created.append(path)


def ensure_pointers(root, write):
    """Agent-neutral activation: AGENTS.md always; CLAUDE.md/GEMINI.md only if present."""
    done = []
    for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        path = Core.public_path(root, name)
        text = read(path)
        if text is None and name != "AGENTS.md":
            continue
        if text is None:
            if write:
                Core.write_atomic(path, POINTER)
            done.append((name, "created"))
        elif POINTER_MARK not in text:
            if write:
                sep = "\n" if text.endswith("\n") else "\n\n"
                Core.write_atomic(path, text + sep + POINTER)
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
    with checkout_lock(root):
        if brain_exists(root):
            RL.require_free_or_director(sys.modules[__name__], root)
        b = Core.public_path(root, BRAIN_DIR)
        created = []
        write_new(Core.public_path(root, BRAIN_DIR + "/config.yaml"), config_text(root), created)
        write_new(Core.public_path(root, BRAIN_DIR + "/current.md"), CURRENT_TMPL, created)
        write_new(Core.public_path(root, BRAIN_DIR + "/target.md"), TARGET_TMPL, created)
        write_new(Core.public_path(root, BRAIN_DIR + "/constraints.md"), CONSTRAINTS_TMPL, created)
        write_new(Core.public_path(root, BRAIN_DIR + "/.gitignore"), ".cache/\n", created)
        Core.public_path(root, BRAIN_DIR + "/tasks").mkdir(parents=True, exist_ok=True)
        Core.public_path(root, BRAIN_DIR + "/decisions").mkdir(parents=True, exist_ok=True)
        pointers = ensure_pointers(root, write=True)
    for p in created:
        print(f"CREATED {Path(os.path.relpath(p, root)).as_posix()}")
    if not created:
        print("EXISTS: nothing overwritten")
    for name, action in pointers:
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
        RL.require_free_or_director(sys.modules[__name__], root)
        tdir = Core.public_path(root, BRAIN_DIR + "/tasks")
        tdir.mkdir(parents=True, exist_ok=True)
        nums = [int(TASK_FILE_RE.match(f.name).group(1)) for f in tdir.iterdir() if TASK_FILE_RE.match(f.name)]
        legacy = read(bp(root) / "migration-backup" / LEGACY_FILE) or ""
        nums += [int(n) for n in re.findall(r"^- \[[ xX~!\-]\]\s+T(\d+)", legacy, re.M)]
        every, _ = history_task_ids(root)
        nums += [int(i[3:]) for i in every]
        tid = norm_id("PB", max(nums, default=0) + 1)
        deps = [norm_id("PB", n) for n in re.findall(r"PB-(\d+)", depends or "")]
        status = "PLANNED"
        risk = risk or "MEDIUM"
        path = Core.public_path(root, BRAIN_DIR + "/tasks/" + f"{tid}.md")
        Core.write_atomic(
            path,
            TASK_TMPL.format(
                id=tid,
                title=title,
                status=status,
                risk=risk,
                priority=priority or "P2",
                tier=tier or "M",
                deps=", ".join(deps) or "-",
            ),
        )
    print(f"CREATED {Path(os.path.relpath(path, root)).as_posix()} ({status})")
    print(
        "NEXT: Write Objective in the user's words, Areas, Domains, numbered Steps with exact paths, "
        "Acceptance checkboxes, Verify commands (WORKFLOW.md §3). Incomplete -> Status: PLANNED."
    )
    return 0


def cmd_start(root, task_id, agent="lead", takeover="", agents_path=None):
    if not brain_exists(root):
        print("NO_BRAIN")
        return 3
    with checkout_lock(root):
        task = find_task(root, task_id)
        actor = agent_id(agent, "--agent")
        R.guard(sys.modules[__name__], root, task)
        if R.enabled(sys.modules[__name__], root):
            require_session(root, implementation=task.get("purpose") != "discovery")
        R.attempt_guard(sys.modules[__name__], root, task)
        policy = A.gate(sys.modules[__name__], task, actor, "start", agents_path, root=root) or {}
        all_tasks = list_tasks(root)
        pending = [t["id"] for t in all_tasks for e in t.get("external", []) if e["state"] in ("sent", "response_unknown")]
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
        risk = V.effective_risk(sys.modules[__name__], task)
        task["risk"] = risk
        con = contract(task)
        set_headers(task["file"], {"Status": "IN_PROGRESS", "Owner": actor, "Risk": risk})
        line = (
            f"- start: IN_PROGRESS | owner={actor} | risk={risk} | digest={dig} | contract={con}"
            + (f" | strength={policy['poolStrength']}" if policy.get("poolStrength") else "")
            + (f" | takeover={takeover.strip()}" if takeover.strip() else "")
        )
        append_section(task["file"], "Evidence", line)
        started_id = task["id"]
        print(f"STARTED {started_id} owner={actor} risk={risk} files={count} digest={dig} contract={con}")
        if policy.get("qualification_warning"):
            print("WARN " + policy["qualification_warning"])
        if risk in ("MEDIUM", "HIGH") and actor.lower() == "lead":
            pol_cfg = E.load(sys.modules[__name__], root)
            rev_src = (pol_cfg or {}).get("review", {}).get("source", "")
            if rev_src.startswith("native") and get_session_modes(root).get("rev") != "solo":
                print("HINT: for independent native review, pass your actual model ID (`start <id> --agent <model>`) or switch to `solo` with `--self-review`.")
    if board_enabled(root):
        for bline in board_lines(root, focus_id=started_id):
            print(bline)
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
    if not brain_exists(root):
        print("NO_BRAIN")
        return 3
    b, fails, warns = bp(root), [], []
    has_git = git(root, "rev-parse", "--is-inside-work-tree") == "true"
    cfg = parse_config(root)
    if not (b / "config.yaml").exists():
        warns.append("config.yaml missing (defaults used)")
    if "board" in cfg and str(cfg.get("board", "")).strip().lower() not in (BOARD_ON_TOKENS | BOARD_OFF_TOKENS):
        warns.append("config.yaml: board must be on|off")
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
            int(re.match(r"^ADR-(\d+)", f.name).group(1))
            for f in (b / "decisions").iterdir()
            if re.match(r"^ADR-(\d+)(?:-.*)?\.md$", f.name)
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
            sinfo = SC.score_task(sys.modules[__name__], root, t)
            if sinfo["missing_ui_triad"]:
                warns.append(
                    f"{tid}: UI task with typed Acceptance is missing Triad tag(s): "
                    + ", ".join(f"[{k}]" for k in sinfo["missing_ui_triad"])
                )
        if not t["has_acceptance"]:
            warns.append(f"{tid}: no Acceptance")
        if not t["has_verify"]:
            warns.append(f"{tid}: no Verify")
        for vcmd in t.get("verify_cmds", []):
            try:
                vargv = Core.command_argv(vcmd)
            except ValueError:
                warns.append(f"{tid}: Verify command has invalid quoting: {vcmd}")
                continue
            if (
                any(tok in ("&&", "||", ";", "|", ">", ">>", "<") or (tok.endswith(";") and " " not in tok) for tok in vargv)
                or vargv[0].lower() in ("cd", "export", "set")
                or bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", vargv[0]))
            ):
                warns.append(
                    f"{tid}: Verify command `{vcmd}` uses shell operators/builtins "
                    "(`check` runs without a shell; split into separate `- `<cmd>`` lines)"
                )
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
    print(f"PROJECT_BRAIN {VERSION} (schema {SCHEMA}) | python {sys.version.split()[0]} on {sys.platform}")
    try:
        with Core.ProcessTree():
            containment = "Windows JobObject" if os.name == "nt" else "POSIX process group"
        print(f"CONTAINMENT: OK ({containment})")
    except Exception as exc:
        print(f"CONTAINMENT: FAIL ({exc})")
        return 2
    has_git = git(root, "rev-parse", "--is-inside-work-tree") == "true"
    print(f"GIT: {'OK' if has_git else 'NONE'}")
    try:
        cap_cmd = AP.command()
        print(f"CLI_AGENT_POOL: OK ({' '.join(cap_cmd)})")
    except ValueError as exc:
        print(f"CLI_AGENT_POOL: NOT_FOUND ({exc}; native/solo modes work without CAP)")
    reg = A.load()
    print(f"ACTOR_REGISTRY: {len(reg.get('models', {}))} observed actor(s) in {A.registry_path()}")
    return 0


BOOLEAN_FLAGS = {
    "--confirm", "--rearm", "--full", "--cheaper", "--new-session",
    "--apply", "--write", "--json", "--dry-run", "--force", "--new", "--prepare",
    "--verify", "--cleanup", "--self-review", "--read-only", "--enable",
    "--goal-independent", "--keep-evidence", "--rerun", "--scan", "--readback",
    "--heal", "--sync-skills", "--unverified", "--from-hook", "--accepted", "--advanced",
    "-h", "--help", "--version",
}
TWO_LEVEL_COMMANDS = {"agents", "runs", "relay", "setup", "quota"}


def _reorder_argv(argv):
    """Allow positional arguments (like <root> or <PB-NNN>) to appear either before or after --flags."""
    if not argv or argv[0].startswith("-"):
        return argv
    head_len = 2 if (argv[0] in TWO_LEVEL_COMMANDS and len(argv) > 1 and not argv[1].startswith("-")) else 1
    head = list(argv[:head_len])
    rest = list(argv[head_len:])
    pos, opts, after_dd = [], [], []
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok == "--":
            after_dd = ["--"] + rest[i + 1:]
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
    return head + pos + opts + after_dd


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


def _resolve_root_and_board(pos1, pos2, default_root="."):
    """Allow flexible positional order: `board [root] [action]` OR `board [action] [root]`."""
    p1 = (pos1 or "").strip()
    p2 = (pos2 or "").strip()
    if p1.lower() in BOARD_ACTIONS:
        return Path(p2 or default_root).resolve(), p1
    if p2.lower() in BOARD_ACTIONS:
        return Path(pos1 or default_root).resolve(), p2
    if p1 and Path(p1).is_dir() and not p2:
        return Path(p1).resolve(), ""
    if p1 and not p2:
        return Path(default_root).resolve(), p1
    return Path(p1 or default_root).resolve(), p2


def _relay_token_argv(argv):
    """`--relay-token <t>` works on every command and in shells that drop environment changes."""
    out, i = [], 0
    while i < len(argv):
        item = argv[i]
        if item == "--":
            out.extend(argv[i:])
            break
        if item == "--relay-token" and i + 1 < len(argv):
            os.environ["PB_RELAY_TOKEN"] = argv[i + 1]
            i += 2
            continue
        if item.startswith("--relay-token="):
            os.environ["PB_RELAY_TOKEN"] = item.split("=", 1)[1]
            i += 1
            continue
        out.append(item)
        if item.startswith("-") and "=" not in item and item not in BOOLEAN_FLAGS and i + 1 < len(argv):
            out.append(argv[i + 1])
            i += 2
            continue
        i += 1
    return out


def _require_not_worker(B_mod, root, action_label, allow_stopping=False):
    if Core.worker_env_active():
        if RL.authorized(B_mod, root):
            return
        if allow_stopping and RL.stopping_holder(B_mod, root):
            return
        raise ValueError(f"Pool workers cannot run {action_label}")


_HOOK_ACTIVE = False


def main():
    global _HOOK_ACTIVE
    _HOOK_ACTIVE = False
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")

    ap = argparse.ArgumentParser(description="Project Brain planning and verification helper", epilog="See SKILL.md.")
    ap.add_argument("--version", action="version", version=f"project-brain {VERSION} (schema {SCHEMA})")
    sub = ap.add_subparsers(dest="cmd", required=True)
    O.add_parser(sub)
    CT.add_parser(sub)
    RL.add_parser(sub)
    SU.add_parser(sub)

    p_watch = sub.add_parser("watch", help="Token-thrifty 1-line project monitor for observers and timers")
    p_watch.add_argument("root", nargs="?", default=".")
    p_watch.add_argument("--heal", action="store_true", help="Report active runs needing readback (never unlinks OS locks)")

    p_board = sub.add_parser("board", help="Zero-token Progress Board (İlerleme Panosu); default on, toggle with on/off")
    p_board.add_argument("pos1", nargs="?", default=None)
    p_board.add_argument("pos2", nargs="?", default=None)
    p_board.add_argument("--force", action="store_true", help="Print board even when disabled")

    for name in ("boot", "brief", "map", "init", "changed", "validate", "doctor"):
        parser = sub.add_parser(name)
        parser.add_argument("root", nargs="?", default=".")
        if name == "boot":
            parser.add_argument("--read-only", action="store_true")
            parser.add_argument("--new-session", action="store_true")

    p = sub.add_parser("orient")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--read-only", action="store_true")
    p = sub.add_parser("intake")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--item", action="append", default=[])
    p.add_argument("--relation", choices=("related", "question", "new-work", "cancel"), default="related")
    p.add_argument("--task", default="")
    p.add_argument("--resolve", default="")

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
    p.add_argument("pos1")
    p.add_argument("pos2", nargs="?", default=None)
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
    p.add_argument("--mode", choices=("response", "execute"), default=None)
    p.add_argument("--wait", type=int, default=3600)
    p.add_argument("--readback", action="store_true")
    p.add_argument("--backend", choices=("pool", "direct"), default="pool")
    p.add_argument("--group", default="")
    p.add_argument("pos1")
    p.add_argument("pos2", nargs="?", default=".")
    p.add_argument("--cli", default="")
    p.add_argument("--model", default="")
    p.add_argument("--effort", choices=A.EFFORTS, default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--timeout", type=int, default=900)

    p_ag = sub.add_parser("agents")
    ag_sub = p_ag.add_subparsers(dest="agents_cmd", required=True)
    for ag_name in ("scan", "list", "quota"):
        sp = ag_sub.add_parser(ag_name)
        sp.add_argument("--backend", choices=("pool", "direct"), default="pool")
        sp.add_argument("root", nargs="?", default=".")
        sp.add_argument("--json", action="store_true")
        sp.add_argument("--full", action="store_true")
    sp_sel = ag_sub.add_parser("select")
    sp_sel.add_argument("--mode", choices=("response", "execute"), default=None)
    sp_sel.add_argument("--backend", choices=("pool", "direct"), default="pool")
    sp_sel.add_argument("root", nargs="?", default=".")
    sp_sel.add_argument("--role", choices=A.ROLES, default="worker")
    sp_sel.add_argument("--tier", default="")
    sp_sel.add_argument("--task", default="")
    sp_sel.add_argument("--cli", default="")
    sp_sel.add_argument("--group", default="")
    sp_sel.add_argument("--json", action="store_true")
    sp_sel.add_argument("--full", action="store_true")
    sp_mode = ag_sub.add_parser("mode")
    sp_mode.add_argument("root", nargs="?", default=".")
    sp_mode.add_argument("--new", action="store_true")
    sp_mode.add_argument("--exec", dest="exec_mode", default="")
    sp_mode.add_argument("--rev", dest="rev_mode", default="")
    sp_mode.add_argument("--note", default="")
    sp_mode.add_argument("--schedule", choices=("serial", "parallel"), default=None)
    sp_mode.add_argument("--max-parallel", type=int, default=None)
    sp_mode.add_argument("--task-mode", choices=("response", "execute"), default=None)
    sp_mode.add_argument("--json", action="store_true")

    argv = _relay_token_argv(sys.argv[1:])
    a = ap.parse_args(_reorder_argv(argv))
    B_mod = sys.modules[__name__]
    _HOOK_ACTIVE = bool(
        a.cmd == "relay"
        and getattr(a, "action", None) == "recover"
        and getattr(a, "from_hook", False)
        and not Core.worker_env_active()
    )

    if a.cmd == "watch":
        print(watch_status(a.root, getattr(a, "heal", False)))
        return 0
    if a.cmd == "board":
        root, act = _resolve_root_and_board(a.pos1, a.pos2)
        if not root.is_dir():
            print(f"error: not a directory: {root}", file=sys.stderr)
            return 1
        return cmd_board(root, action=act, force=getattr(a, "force", False))
    if a.cmd == "relay":
        result = RL.command(B_mod, a)
        code = result.pop("exit_code", 0) if isinstance(result, dict) else 0
        if isinstance(result, dict) and result.get("notify") and getattr(a, "from_hook", False):
            print(result["notify"])
        print(json.dumps(result, ensure_ascii=False))
        return code
    if a.cmd == "setup":
        result = SU.command(B_mod, a)
        for line in result.pop("lines", []):
            print(line)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if a.cmd in ("policy", "quota", "qualify"):
        print(json.dumps(CT.command(B_mod, a), ensure_ascii=False))
        return 0
    if a.cmd == "runs":
        print(json.dumps(O.command(B_mod, a), ensure_ascii=False))
        return 0

    if a.cmd == "agents":
        if a.agents_cmd == "mode":
            root = Path(a.root).resolve()
            if a.exec_mode or a.rev_mode or a.note or a.new or a.schedule or a.max_parallel is not None or a.task_mode:
                _require_not_worker(B_mod, root, "`agents mode`")
                if E.load(B_mod, root) and (a.exec_mode or a.rev_mode or a.new or a.schedule or a.max_parallel is not None):
                    raise ValueError("Saved ESP/SP is authoritative; update/confirm it with `policy`, not legacy mode overrides")
                with checkout_lock(root):
                    RL.require_free_or_director(B_mod, root)
                    modes = set_session_modes(
                        root, a.exec_mode, a.rev_mode, a.note, new=a.new,
                        schedule=a.schedule, max_parallel=a.max_parallel, task_mode=a.task_mode,
                    )
            else:
                modes = get_session_modes(root)
            if a.json:
                print(json.dumps(modes, indent=2, ensure_ascii=False))
            else:
                print(f"SESSION_MODES: exec={modes['exec'] or 'ask'} rev={modes['rev'] or 'ask'}" + (f" ({modes['note']})" if modes.get("note") else ""))
                print(f"WORK: {modes['task_mode']} | {modes['schedule']} | max_parallel={modes['max_parallel']}")
            return 0
        if getattr(a, "backend", "pool") == "direct":
            raise ValueError("Legacy --backend direct was removed in Project Brain 4.0; external CLI agents are managed exclusively by CLI Agent Pool (CAP), while native/solo work without CAP")
        _require_not_worker(B_mod, Path(a.root).resolve(), f"`agents {a.agents_cmd}`")
        return AP.agents(B_mod, a)

    if a.cmd in ("protocol", "security"):
        root = Path(a.root).resolve()
        if not brain_exists(root):
            raise ValueError("Initialize Brain before configuring protocol/security")
        mutating = (a.cmd == "protocol" and a.enable) or (a.cmd == "security" and bool(a.ref))
        if mutating:
            _require_not_worker(B_mod, root, f"`{a.cmd}`")
            with checkout_lock(root):
                RL.require_free_or_director(B_mod, root)
                if a.cmd == "protocol":
                    _set_config_scalar(root, "protocol_version", "1")
                    print("PROTOCOL: " + ("1" if R.enabled(B_mod, root) else "0"))
                else:
                    print(json.dumps(S.configure(B_mod, root, a.ref, a.note), ensure_ascii=False))
            return 0
        if a.cmd == "protocol":
            print("PROTOCOL: " + ("1" if R.enabled(B_mod, root) else "0"))
        elif a.scan:
            files = git_paths(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR")
            if files is None:
                raise ValueError("Staged scan requires Git")
            print("SCAN PASS: " + str(S.scan_staged(B_mod, root)) + " staged files; binary artifacts still require private-data inspection")
        else:
            print(json.dumps(S.policy(B_mod, root) or {"reference": "pending"}))
        return 0

    if a.cmd in ("reconcile", "progress", "handoff"):
        root, tid = _resolve_root_and_task(a.pos1, a.pos2)
        allow_stop = a.cmd in ("progress", "handoff")
        _require_not_worker(B_mod, root, f"`{a.cmd}`", allow_stopping=allow_stop)
        with checkout_lock(root):
            RL.require_free_or_director(B_mod, root, allow_stopping=allow_stop)
            task = find_task(root, tid)
            if a.cmd == "reconcile":
                result = R.reconcile(B_mod, root, task, a.note, a.goal_independent, a.keep_evidence)
            elif a.cmd == "progress":
                result = R.progress(B_mod, root, task, a.next_step, a.failing, a.dirty, a.strategy, allow_stopping=allow_stop)
            else:
                result = R.handoff(B_mod, root, task, allow_stopping=allow_stop)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if a.cmd in ("start", "check", "evidence", "review", "accept", "score", "delegate"):
        root, tid = _resolve_root_and_task(a.pos1, a.pos2)
        if not root.is_dir():
            print(f"error: not a directory: {root}", file=sys.stderr)
            return 1
        if a.cmd == "score":
            if a.write:
                _require_not_worker(B_mod, root, "`score --write`")
                with checkout_lock(root):
                    RL.require_free_or_director(B_mod, root)
                    return SC.cmd_score(B_mod, root, tid=tid, write=True, as_json=a.json)
            return SC.cmd_score(B_mod, root, tid=tid, write=False, as_json=a.json)
        if not tid:
            print(f"FAIL {a.cmd} requires a task ID (PB-NNN)", file=sys.stderr)
            return 2
        if a.cmd == "start":
            _require_not_worker(B_mod, root, "`start`")
            return cmd_start(root, tid, agent=a.agent, takeover=a.takeover, agents_path=a.registry)
        if a.cmd == "check":
            _require_not_worker(B_mod, root, "`check`")
            with checkout_lock(root):
                RL.require_free_or_director(B_mod, root)
                rc, lines = V.check(B_mod, root, tid, timeout=a.timeout, actor=a.actor, rerun=a.rerun)
            for l in lines:
                print(l)
            if rc == 0 and board_enabled(root):
                for bline in board_lines(root, focus_id=tid):
                    print(bline)
            return rc
        if a.cmd == "evidence":
            _require_not_worker(B_mod, root, "`evidence`")
            with checkout_lock(root):
                RL.require_free_or_director(B_mod, root)
                rc, lines = V.evidence(B_mod, root, tid, a.kind, a.note, files=a.file, actor=a.actor, criteria=a.criterion)
            for l in lines:
                print(l)
            if rc == 0 and board_enabled(root):
                for bline in board_lines(root, focus_id=tid):
                    print(bline)
            return rc
        if a.cmd == "review":
            _require_not_worker(B_mod, root, "`review`")
            with checkout_lock(root):
                RL.require_free_or_director(B_mod, root)
                rc, lines = V.review(
                    B_mod, root, tid, a.reviewer, a.verdict, findings=a.finding, agents_path=a.registry, self_review=a.self_review
                )
            for l in lines:
                print(l)
            if rc == 0 and board_enabled(root):
                for bline in board_lines(root, focus_id=tid):
                    print(bline)
            return rc
        if a.cmd == "accept":
            _require_not_worker(B_mod, root, "`accept`")
            with checkout_lock(root):
                RL.require_free_or_director(B_mod, root)
                rc, lines = V.accept(B_mod, root, tid, actor=a.actor, agents_path=a.registry, self_review=a.self_review)
            for l in lines:
                print(l)
            transitioned = rc == 0 or (rc == 1 and bool(lines) and lines[0].startswith(("REVIEW_PENDING ", "WAITING_USER ")))
            if transitioned and board_enabled(root):
                for bline in board_lines(root, focus_id=tid):
                    print(bline)
            return rc
        if a.cmd == "delegate":
            if Core.worker_env_active() and not RL.authorized(B_mod, root):
                raise ValueError("Pool workers cannot delegate recursively")
            if getattr(a, "backend", "pool") == "direct":
                raise ValueError("Legacy --backend direct was removed in Project Brain 4.0; use CLI Agent Pool (CAP) via `runs` or `delegate`")
            task = find_task(root, tid)
            return AP.delegate(B_mod, root, task, SC.score_task(B_mod, root, task), a)

    if a.cmd == "new":
        if a.pos2 is not None:
            root, title = Path(a.pos1).resolve(), a.pos2
        else:
            root, title = Path(".").resolve(), a.pos1
        if not root.is_dir():
            print(f"error: not a directory: {root}", file=sys.stderr)
            return 1
        _require_not_worker(B_mod, root, "`new`")
        return cmd_new(root, title, a.depends, a.risk, a.priority, a.tier)

    root = Path(a.root).resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 1
    if a.cmd == "brief":
        return RS.brief(B_mod, root)
    if a.cmd == "boot":
        if a.new_session and a.read_only:
            raise ValueError("--new-session writes the session record; omit --read-only")
        if a.new_session:
            _require_not_worker(B_mod, root, "`boot --new-session`")
        worker_ro = Core.worker_env_active() and not RL.authorized(B_mod, root)
        if a.read_only or worker_ro:
            return cmd_boot(root, maintain=False)
        with startup_lock(root):
            return cmd_boot(root, new_session=a.new_session)
    if a.cmd in ("orient", "intake"):
        if a.cmd == "orient":
            worker_ro = Core.worker_env_active() and not RL.authorized(B_mod, root)
            if a.read_only or worker_ro:
                return RS.orient(B_mod, root, maintain=False, startup_fn=M.startup)
            with startup_lock(root):
                return RS.orient(B_mod, root, maintain=True, startup_fn=M.startup)
        _require_not_worker(B_mod, root, "`intake`")
        with checkout_lock(root):
            RL.require_free_or_director(B_mod, root)
            print(json.dumps(RS.intake(B_mod, root, a.item, a.relation, a.task, a.resolve), ensure_ascii=False))
        return 0
    if a.cmd in ("migrate", "upgrade"):
        if a.apply:
            _require_not_worker(B_mod, root, f"`{a.cmd} --apply`")
            with checkout_lock(root):
                RL.require_free_or_director(B_mod, root)
                return M.run(root, True, sync_skills=getattr(a, "sync_skills", False))
        return M.run(root, False, sync_skills=getattr(a, "sync_skills", False))
    if a.cmd == "legacy":
        if a.prepare or a.verify or a.cleanup:
            _require_not_worker(B_mod, root, "`legacy`")
            if a.apply:
                raise ValueError("use import --apply separately before trace verification/cleanup")
            with checkout_lock(root):
                RL.require_free_or_director(B_mod, root)
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
        if a.apply:
            _require_not_worker(B_mod, root, "`legacy --apply`")
            with checkout_lock(root):
                RL.require_free_or_director(B_mod, root)
                return D.cmd_legacy(B_mod, root, apply=True, migrate_fn=M.run)
        return D.cmd_legacy(B_mod, root, apply=False, migrate_fn=M.run)
    if a.cmd == "init":
        _require_not_worker(B_mod, root, "`init`")
    return {
        "map": cmd_map,
        "init": cmd_init,
        "changed": cmd_changed,
        "validate": cmd_validate,
        "doctor": cmd_doctor,
    }[a.cmd](root)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        if _HOOK_ACTIVE:
            print("CAP_RETRY_AFTER 30")
            sys.exit(75)
        sys.exit(2)
