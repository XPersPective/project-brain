#!/usr/bin/env python3
"""project-brain helper. Stdlib only, Python 3.8+.

  boot     <root>   State, target, plan, focus, recent work, files to load, next action. Run first.
  map      <root>   Compact repository overview (genesis; replaces manual exploration).
  init     <root>   Create .project-brain/ skeleton. Never overwrites.
  new      <root> "title" [--priority P1|P2|P3] [--tier L|M|H] [--risk LOW|MEDIUM|HIGH] [--depends PB-001]
                    Create the next task file. IDs are never reused (Git history checked).
  changed  <root>   Domains touched by commits made outside the protocol (after the last PB commit).
  validate <root>   Structural checks, executable-spec checks, size budgets.
  migrate  <root> [--apply]   Convert a legacy Brain (schema <=3 or PROJECT_BRAIN.md); preview by default.

Exit: 0 ok, 1 warnings, 2 errors, 3 no Project Brain.
"""

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

VERSION = "2.0.1"
SCHEMA = 4
BRAIN_DIR = ".project-brain"
LEGACY_FILE = "PROJECT_BRAIN.md"
STATUS_VALUES = ("IN_PROGRESS", "READY", "PLANNED", "BLOCKED")
RISK_VALUES = ("LOW", "MEDIUM", "HIGH")
PRIORITY_VALUES = ("P1", "P2", "P3")
TIER_VALUES = ("L", "M", "H")
VAGUE_RE = re.compile(r"\b(etc\.|improve|clean ?up|refactor as needed|handle properly|as discussed|"
                      r"vb\.|iyileştir\w*|düzenle\w*)", re.I)
TASK_FILE_RE = re.compile(r"^PB-(\d+)\.md$")
ADR_FILE_RE = re.compile(r"^ADR-(\d+)\.md$")
HEADER_RE = re.compile(r"^\**(status|priority|tier|risk|depends|dependencies|areas|affected areas|domains|blocked)\**:\s*(.*)$", re.I)
HEADER_ALIAS = {"dependencies": "depends", "affected areas": "areas"}
STATUS_RE = re.compile(r"^\W*(IN[_ -]PROGRESS|READY|PLANNED|BLOCKED|DONE|COMPLETED?)(?![A-Z_])", re.I)
PLACEHOLDERS = ("<observable condition>", "<what and why", "<command>", "<the user's goal", "`<path>`",
                "<exact path", "<intended end state>")
BUDGETS = {"current": 200, "target": 150, "constraints": 100, "task": 80, "open_tasks": 25}

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "target", "coverage", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".turbo", ".cache", ".idea", ".gradle",
    "bin", "obj", ".dart_tool", ".pub-cache", BRAIN_DIR,
}

CONFIG_TMPL = """schema_version: 4

architecture:
  mode: single          # single: current.md/target.md | domains: current/<d>.md, target/<d>.md

git:
  history_mode: unknown # preserve | squash | rewrite-prone | unknown
  commit: auto          # auto: commit each checkpoint | ask: prepare the commit, ask the user
  push: manual          # every-task | milestone | session-end | manual

commands:               # exact commands; boot prints them so nobody rediscovers them
  test: {test}
  lint: {lint}
  build: {build}
"""

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
Depends: {deps}
Areas: <`src/x/**`, `tests/x/**`>
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

## Notes
"""

POINTER_MARK = "<!-- project-brain -->"
POINTER = f"""{POINTER_MARK}
## Project Brain
This project keeps its state in `.project-brain/` (current architecture, target, open tasks).
Before any work, load the `project-brain` skill and run its boot step; follow it for all work here.
"""


# ── small helpers ─────────────────────────────────────────────────────────

def git(root, *args, timeout=60):
    """Run git; return stdout (right-stripped) or None on failure."""
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.rstrip() if r.returncode == 0 else None


def git_paths(root, *args):
    """Run a -z git command that lists paths; None on failure."""
    out = git(root, *args, "-z")
    return None if out is None else [p for p in out.split("\0") if p]


def read(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def norm_id(prefix, n):
    return f"{prefix}-{int(n):03d}"


def norm_domain(s):
    return re.sub(r"[\s_]+", "-", s.strip().strip("`*#").strip().lower())


def matches(path, pat):
    """Glob (fnmatch, * crosses /) or path/directory prefix match."""
    pat = pat.strip()
    pat = pat[2:] if pat.startswith("./") else pat
    if any(c in pat for c in "*?["):
        return fnmatch.fnmatchcase(path, pat)
    return path == pat or path.startswith(pat.rstrip("/") + "/")


def parse_config(root):
    """Two-level YAML subset: `section:` then `  key: value`."""
    text = read(Path(root) / BRAIN_DIR / "config.yaml") or ""
    out, section = {}, None
    for line in text.splitlines():
        s = line.split(" #", 1)[0].rstrip() if not line.lstrip().startswith("#") else ""
        if not s.strip() or ":" not in s:
            continue
        key, val = (x.strip() for x in s.split(":", 1))
        val = val.strip("\"'") if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'" else val
        if line[0] not in " \t":
            section = key if s.rstrip().endswith(":") else None
            if section:
                out[section] = {}
            else:
                out[key] = val
        elif section:
            out[section][key] = val
    return out


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


# ── Brain files ───────────────────────────────────────────────────────────

def bp(root):
    return Path(root) / BRAIN_DIR


def brain_exists(root):
    b = bp(root)
    return b.is_dir() and any((b / n).exists() for n in ("config.yaml", "current.md", "current"))


def parse_task(path):
    text = read(path)
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
    # v4 header lines, falling back to v3 "## Section" layout
    # Tolerant reader: models write "READY — note" or "DONE (date) — commit x"; keep the token, report the rest.
    raw = head.get("status") or first_line(sec.get("status", []))
    m = STATUS_RE.match(raw)
    status = re.sub(r"[ -]", "_", m.group(1).upper()) if m else "?"
    status = "DONE" if status.startswith("COMPLETE") else status
    status_note = raw[m.end():].strip(" -—–:.()") if m else raw
    deps_src = head.get("depends") if "depends" in head else "\n".join(sec.get("dependencies", []))
    deps = [norm_id("PB", n) for n in re.findall(r"PB-(\d+)", deps_src or "")]
    areas = split_list(head.get("areas", "")) or [
        a for l in sec.get("affected areas", []) for a in re.findall(r"`([^`]+)`", l)]
    if "domains" not in head:
        dm = re.search(r"^\W*domains\W*:\s*(.+)$", text, re.I | re.M)
        if dm:
            head["domains"] = dm.group(1)
    domains = [norm_domain(d) for d in split_list(head.get("domains", ""))]
    if not domains:
        domains = [norm_domain(l.strip()[2:]) for l in sec.get("architecture impact", [])
                   if l.strip().startswith("- ")]
    acc = sec.get("acceptance", sec.get("acceptance criteria", []))
    resume = sec.get("resume", [])
    nxt = ""
    for i, l in enumerate(resume):
        m = re.match(r"^\s*next(?: action)?:\s*(.*)$", l, re.I)
        if m:
            nxt = m.group(1).strip() or first_line(resume[i + 1:]).lstrip("- ")
            break
    if "risk" not in head:
        rm = re.search(r"^\W*risk\W*:?\s*(LOW|MEDIUM|HIGH)", text, re.I | re.M)
        if rm:
            head["risk"] = rm.group(1)
    blocked = head.get("blocked") or first_line(sec.get("blocker", [])) or (status == "BLOCKED" and status_note)
    steps = [l for l in sec.get("steps", []) if l.strip()]
    verify = sec.get("verify", sec.get("verification", []))
    spec_text = "\n".join(steps + acc)
    priority = head.get("priority", "").upper()[:2]
    tier = head.get("tier", "").upper()[:1]
    return {
        "id": norm_id("PB", TASK_FILE_RE.match(path.name).group(1)),
        "file": path, "title": title, "status": status, "risk": head.get("risk", "").upper(),
        "deps": deps, "areas": areas, "domains": [d for d in domains if d],
        "has_acceptance": any(l.strip() for l in acc) or bool(
            re.search(r"^\W*acceptance( criteria)?\W*:", text, re.I | re.M)),
        "open_items": [l.strip() for l in acc if l.strip().startswith("- [ ]")],
        "checkboxes": sum(1 for l in acc if re.match(r"^\s*- \[[ xX]\]", l)),
        "has_verify": any(l.strip() for l in sec.get("verify", sec.get("verification", []))) or bool(
            re.search(r"^\W*verif(y|ication)\W*:", text, re.I | re.M)),
        "status_note": status_note,
        "priority": priority if priority in PRIORITY_VALUES else "P2",
        "priority_raw": head.get("priority", ""), "tier": tier, "tier_raw": head.get("tier", ""),
        "has_steps": bool(steps), "verify_cmd": any("`" in l for l in verify),
        "vague": sorted({m.group(1).lower() for m in VAGUE_RE.finditer(spec_text)}),
        "next": nxt, "blocked": blocked, "lines": len(text.splitlines()), "text": text,
        "header_id": re.findall(r"^# (PB-\d+)", text, re.M),
    }


def list_tasks(root):
    d = bp(root) / "tasks"
    if not d.is_dir():
        return []
    tasks = [parse_task(f) for f in d.iterdir() if TASK_FILE_RE.match(f.name)]
    return sorted((t for t in tasks if t), key=lambda t: int(t["id"][3:]))


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
    """Newest commit made under the protocol (message mentions PB-); commits after it are external.

    ponytail: agents often commit task work without a checkpoint trailer, so "newest checkpoint" would flag
    their own commits as foreign. Upgrade path: per-domain bases once trailer names match heading names.
    """
    return (git(root, "log", "-1", "--grep=PB-", r"--grep=\[PB\]", "--format=%H")
            or git(root, "log", "-1", "--format=%H", "--", BRAIN_DIR) or None)


def is_wip(body):
    return "true" in [v.lower() for v in trailer_values(body, "PB-WIP")]


def task_ids_in(body):
    return [norm_id("PB", n) for v in trailer_values(body, "PB-Tasks?") for n in re.findall(r"PB-(\d+)", v)]


def recent_closed(root, open_ids, n=3):
    """[(ids, agent, short sha)] for the newest commits that closed tasks."""
    out = []
    for sha, body in git_records(root, "PB-Task"):
        ids = [i for i in task_ids_in(body) if i not in open_ids]
        if ids and not is_wip(body):
            out.append((",".join(ids), (trailer_values(body, "PB-Agent") or ["?"])[0], sha[:7]))
            if len(out) >= n:
                break
    return out


def closed_since_audit(root, open_ids):
    """Number of tasks closed since the newest commit carrying PB-Plan-Audit (or since the start)."""
    last = git(root, "log", "-1", "--grep=PB-Plan-Audit:", "--format=%H")
    ids = set()
    for _, body in git_records(root, "PB-Task", *([f"{last}..HEAD"] if last else [])):
        if not is_wip(body):
            ids |= set(task_ids_in(body))
    return len(ids - open_ids)


def target_status(root):
    m = re.search(r"^Status:\s*(DRAFT|CONFIRMED)\b", read(bp(root) / "target.md") or "", re.M | re.I)
    return m.group(1).upper() if m else "UNSET"


def legacy_kind(root):
    """'v0' (only PROJECT_BRAIN.md), 'v<N>' (.project-brain schema < 4), or None."""
    if brain_exists(root):
        v = str(parse_config(root).get("schema_version", "")).strip()
        return None if v.isdigit() and int(v) >= SCHEMA else f"v{v or '?'}"
    return "v0" if (Path(root) / LEGACY_FILE).exists() else None


def history_task_ids(root):
    """(all ids ever committed incl. WIP, ids durably completed)."""
    every, done = set(), set()
    for _, body in git_records(root, "PB-Task"):
        ids = set(task_ids_in(body))
        every |= ids
        if not is_wip(body):
            done |= ids
    return every, done


def staleness(root, base):
    """({domain: [files]}, [unmapped files]) changed by commits after `base`."""
    if not base:
        return {}, []
    srcs = domain_sources(root)
    changed = [p for p in (git_paths(root, "diff", "--name-only", f"{base}..HEAD") or [])
               if not p.startswith(BRAIN_DIR + "/")]
    stale = {}
    for d, globs in srcs.items():
        hit = [p for p in changed if any(matches(p, g) for g in globs)]
        if hit:
            stale[d] = hit
    unmapped = [p for p in changed if not any(matches(p, g) for gl in srcs.values() for g in gl)]
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
                i += 1  # skip rename source
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
        runner = ("pnpm" if (root / "pnpm-lock.yaml").exists() else
                  "yarn" if (root / "yarn.lock").exists() else
                  "bun" if (root / "bun.lockb").exists() else "npm")
        for k in ("test", "lint", "build", "typecheck"):
            if k in scripts:
                cmds.setdefault(k, f"{runner} run {k}")
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
            ("build.gradle.kts", "./gradlew test", "", "./gradlew build")):
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


# ── commands ──────────────────────────────────────────────────────────────

def cmd_boot(root):
    legacy = legacy_kind(root)
    if legacy == "v0":
        print("STATE: LEGACY")
        print(f"  ! {LEGACY_FILE} (single-file Brain) found")
        print("NEXT: `migrate` (preview), then `migrate --apply` (SKILL.md Migration).")
        return 0
    if not brain_exists(root):
        print("STATE: NO_BRAIN")
        print("NEXT: Substantial work -> SKILL.md Genesis (`map`, then `init`). Small request -> just do it.")
        return 0
    has_git = git(root, "rev-parse", "--is-inside-work-tree") == "true"
    all_tasks = list_tasks(root)
    tasks = [t for t in all_tasks if t["status"] != "DONE"]
    open_ids = {t["id"] for t in tasks}
    cfg = parse_config(root)
    notes, state = [], None

    if not (bp(root) / "current.md").exists() and not (bp(root) / "current").is_dir():
        state = "INVALID"
        notes.append("no current architecture file")
    # Format problems are warnings, not a stop: the agent can still work and `validate` lists the fixes.
    bad = [t["id"] for t in tasks if t["status"] == "?"]
    ip = [t for t in tasks if t["status"] == "IN_PROGRESS"]
    kept = [t["id"] for t in all_tasks if t["status"] == "DONE"]
    if bad:
        notes.append(f"no valid Status line: {', '.join(bad)} (run `validate`)")
    if len(ip) > 1:
        notes.append(f"several IN_PROGRESS: {', '.join(t['id'] for t in ip)}: keep one, set the rest READY")
    if kept:
        notes.append(f"finished task files still present: {', '.join(kept)}: delete them in the next commit")
    if legacy:
        state = "LEGACY"
        notes.append(f"schema {legacy[1:]}: run `migrate`")
    elif (Path(root) / LEGACY_FILE).exists():
        notes.append(f"legacy {LEGACY_FILE} still present: carry over anything unique, then delete it")
    active = ip[0] if ip else None

    stale, unmapped, done, recent, since_audit = {}, [], set(), [], 0
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
        every, _ = history_task_ids(root)
        done = every - open_ids
        stale, unmapped = staleness(root, base)
        recent = recent_closed(root, open_ids)
        since_audit = closed_since_audit(root, open_ids)
        op = merge_op(root)
        if not state:
            state = ("CONFLICTED" if op else "DIRTY" if unowned else "INTERRUPTED" if active
                     else "ADVANCED" if stale or unmapped else "RESUME")
        elif state == "LEGACY" and op:
            state = "CONFLICTED"
        gitline = (f"git: {branch or 'DETACHED'} @ {head} | last PB commit {cp or 'none'}"
                   f"{' (= HEAD)' if cp and cp == head else ''} | dirty {len(other)} (+{len(brain_dirty)} brain)")
        if op:
            notes.append(f"{op} in progress")
        if unowned:
            notes.append("dirty outside active task: " + ", ".join(unowned[:8]) + (" ..." if len(unowned) > 8 else ""))
        if brain_dirty and not active:
            notes.append("uncommitted .project-brain edits: review and commit them")
        if not base:
            notes.append("no PB commit yet: next commit must carry PB trailers")

    print(f"STATE: {state}")
    print(gitline)
    for n in notes:
        print(f"  ! {n}")
    tstat = target_status(root)
    print(f"TARGET: {tstat}" + {"DRAFT": " (goal not confirmed: plan only goal-independent work; ask the user when present)",
                                 "UNSET": " (add `Status: DRAFT|CONFIRMED` to target.md)"}.get(tstat, ""))

    print(f"PLAN: {len(tasks)} open, {len(done)} done")
    for t in tasks[:BUDGETS["open_tasks"]]:
        extra = []
        od = [d for d in t["deps"] if d in open_ids]
        if od:
            extra.append("deps " + ",".join(od))
        if t["status"] == "BLOCKED" and t["blocked"]:
            extra.append(t["blocked"][:50])
        mark = ">" if t is active else " "
        print(f" {mark} {t['id']} {t['status']:<11} {t['priority']} {t['tier'] or '-'} {t['title'][:60]}"
              f"{'  [' + '; '.join(extra) + ']' if extra else ''}")
    if len(tasks) > BUDGETS["open_tasks"]:
        print(f"   ... {len(tasks) - BUDGETS['open_tasks']} more")

    ready = sorted((t for t in tasks if t["status"] == "READY" and not [d for d in t["deps"] if d in open_ids]),
                   key=lambda t: (t["priority"], int(t["id"][3:])))
    promote = [t["id"] for t in tasks if t["status"] == "PLANNED" and not [d for d in t["deps"] if d in open_ids]]
    focus = active or (ready[0] if ready else None)
    if focus:
        n_open = len(focus["open_items"])
        progress = (f"{n_open}/{focus['checkboxes']} acceptance open" if focus["checkboxes"]
                    else "acceptance has no checkboxes")
        print(f"FOCUS {focus['id']} ({focus['status']}, {focus['priority']}, tier {focus['tier'] or '?'}, "
              f"risk {focus['risk'] or '?'}): {progress}")
        if focus["next"]:
            print(f"  next: {focus['next']}")
        for item in focus["open_items"][:5]:
            print(f"  {item}")
    if focus:
        missing = [n for n, ok in (("Steps", focus["has_steps"]), ("Acceptance checkboxes", focus["checkboxes"]),
                                   ("Verify command", focus["verify_cmd"])) if not ok]
        if missing:
            print(f"  ! {focus['id']} is not an executable spec (missing {', '.join(missing)}): write them first (SKILL.md section 5)")
    if promote:
        print(f"  hint: deps done, write full specs and set READY: {', '.join(promote)}")
    if since_audit >= 5:
        print(f"  hint: {since_audit} tasks closed since the last plan audit -> run Plan audit (SKILL.md section 9)")
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
        dom_files = [bp(root) / "current" / f"{d}.md" for d in focus["domains"]]
        dom_files = [f for f in dom_files if f.exists()]
        load += dom_files or [current_slices(f, focus["domains"]) for f, fixed in current_files(root) if fixed is None]
        for n in sorted(set(re.findall(r"ADR-(\d+)", focus["text"]))):
            adr = next((f for f in (bp(root) / "decisions").glob(f"ADR-{int(n):03d}*.md")), None) \
                if (bp(root) / "decisions").is_dir() else None
            if adr:
                load.append(adr)
    else:
        load += [f for f, fixed in current_files(root) if fixed is None]
        load += [f for f in (bp(root) / "target.md", bp(root) / "target") if f.exists()]
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
        "LEGACY": "`migrate` (preview), then `migrate --apply` (SKILL.md Migration). Then Plan audit.",
        "INVALID": "Run `validate`, fix the FAIL lines, then boot again (REFERENCE: Corrupt Brain).",
        "CONFLICTED": "Finish the Git operation first (REFERENCE: Conflicts). Start no task.",
        "DIRTY": "Classify each listed path: mine/user/generated/unknown. Never reset/clean/stash/checkout unknown work. Continue only on non-overlapping files.",
        "INTERRUPTED": f"Resume {active['id'] if active else ''}: check `git diff --stat` matches the task's Resume notes, then continue at the first open acceptance item.",
        "ADVANCED": "Reconcile only the STALE/UNMAPPED files above, update Current, commit with PB-Current-Checkpoint for those domains. Then handle the user's message.",
    }.get(state)
    if not nxt:
        if focus:
            nxt = (f"Takeover check (SKILL.md section 2), then the user's message (section 3). 'continue' or empty: start "
                   f"{focus['id']} and keep working the queue.")
        elif promote:
            nxt = f"Refine and promote {promote[0]} to READY, then start it."
        elif tasks and all(t["status"] == "BLOCKED" for t in tasks):
            nxt = "Every open task is BLOCKED: report blockers to the user and stop."
        elif tasks:
            nxt = "No startable task: fix statuses (`validate`) or refine a PLANNED task to READY."
        else:
            nxt = "Queue empty: handle the user's message, or run the Final audit (SKILL.md section 9)."
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
    docs = [f for f in files if f.split("/")[-1].upper() in
            ("README.MD", "AGENTS.MD", "CLAUDE.MD", "GEMINI.MD", "CONTRIBUTING.MD", "ARCHITECTURE.MD")]
    if docs:
        print("INSTRUCTION/DOC FILES: " + " ".join(docs[:15]))
    cmds = detect_commands(root)
    print("CMDS: " + (" | ".join(f"{k}={v}" for k, v in cmds.items()) if cmds else "none detected"))
    print("NEXT: Read only manifests, entry points and instruction files (<=15 files), then `init`.")
    return 0


def write_new(path, content, created):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
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
                path.write_text(POINTER, encoding="utf-8", newline="\n")
            done.append((name, "created"))
        elif POINTER_MARK not in text:
            if write:
                with open(path, "a", encoding="utf-8", newline="\n") as f:
                    f.write(("\n" if text.endswith("\n") else "\n\n") + POINTER)
            done.append((name, "appended"))
    return done


def config_text(root, old=None):
    """schema-4 config.yaml, keeping known values from an older config."""
    old = old or {}
    cmds = dict(detect_commands(root))
    cmds.update({k: v for k, v in old.get("commands", {}).items() if v})
    git_old = old.get("git", {})
    text = CONFIG_TMPL.format(**{k: json.dumps(cmds.get(k, "")) for k in ("test", "lint", "build")})
    for key, val in (("mode: single", f"mode: {old.get('architecture', {}).get('mode', 'single')}"),
                     ("history_mode: unknown", f"history_mode: {git_old.get('history_mode', 'unknown')}"),
                     ("commit: auto", f"commit: {git_old.get('commit', 'auto')}"),
                     ("push: manual", f"push: {git_old.get('push', git_old.get('push_policy', 'manual'))}")):
        text = text.replace(key, val, 1)
    return text


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
    print("NEXT: Fill current.md (Runtime, Map, Domains+Sources from code), target.md (user intent; unknown -> "
          "Open Decisions), constraints.md, config commands. Then `new` per gap, then the genesis commit.")
    return 0


def cmd_new(root, title, depends, risk, priority=None, tier=None):
    if not brain_exists(root):
        print("NO_BRAIN: run `init` first")
        return 3
    tdir = bp(root) / "tasks"
    tdir.mkdir(exist_ok=True)
    nums = [int(TASK_FILE_RE.match(f.name).group(1)) for f in tdir.iterdir() if TASK_FILE_RE.match(f.name)]
    every, _ = history_task_ids(root)
    nums += [int(i[3:]) for i in every]
    tid = norm_id("PB", max(nums, default=0) + 1)
    deps = [norm_id("PB", n) for n in re.findall(r"PB-(\d+)", depends or "")]
    open_ids = {t["id"] for t in list_tasks(root) if t["status"] != "DONE"}
    status = "PLANNED" if any(d in open_ids for d in deps) else "READY"
    risk = risk or "MEDIUM"
    path = tdir / f"{tid}.md"
    path.write_text(TASK_TMPL.format(id=tid, title=title, status=status, risk=risk,
                                     priority=priority or "P2", tier=tier or "M",
                                     deps=", ".join(deps) or "-"), encoding="utf-8", newline="\n")
    print(f"CREATED {Path(os.path.relpath(path, root)).as_posix()} ({status})")
    print("NEXT: Write it for a weaker model (SKILL.md section 5): Objective in the user's words, Areas, Domains, numbered "
          "Steps with exact paths, Acceptance checkboxes, Verify commands. Incomplete -> Status: PLANNED.")
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
        print("NO_CHANGES: no commits outside the protocol since the last PB commit")
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
    if not (b / "target.md").exists() and not (b / "target").is_dir():
        warns.append("no target architecture")
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
    tasks = [t for t in all_tasks if t["status"] != "DONE"]
    ids = {t["id"] for t in tasks}
    every, _ = history_task_ids(root) if has_git else (set(), set())
    for t in all_tasks:
        if t["status"] == "DONE":
            warns.append(f"{t['id']}: finished task file kept; delete it in a commit (Git keeps the history)")
    if len(tasks) > BUDGETS["open_tasks"]:
        warns.append(f"{len(tasks)} open tasks > {BUDGETS['open_tasks']} (merge or defer distant work)")
    ip = [t["id"] for t in tasks if t["status"] == "IN_PROGRESS"]
    if len(ip) > 1:
        fails.append(f"multiple IN_PROGRESS: {', '.join(ip)}")
    adrs = set()
    if (b / "decisions").is_dir():
        adrs = {int(ADR_FILE_RE.match(f.name).group(1)) for f in (b / "decisions").iterdir()
                if ADR_FILE_RE.match(f.name)}
    for t in tasks:
        tid = t["id"]
        if t["status"] not in STATUS_VALUES:
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
        if t["status"] in ("READY", "IN_PROGRESS"):
            missing = [n for n, ok in (("Steps", t["has_steps"]), ("Acceptance checkboxes", t["checkboxes"]),
                                       ("a backticked Verify command", t["verify_cmd"])) if not ok]
            if missing:
                warns.append(f"{tid}: {t['status']} but not an executable spec: missing {', '.join(missing)}")
            if t["vague"]:
                warns.append(f"{tid}: vague words in Steps/Acceptance: {', '.join(t['vague'])}")
        if not t["has_acceptance"]:
            warns.append(f"{tid}: no Acceptance")
        if not t["has_verify"]:
            warns.append(f"{tid}: no Verify")
        if t["status"] == "BLOCKED" and not t["blocked"]:
            warns.append(f"{tid}: BLOCKED without 'Blocked:' reason")
        if t["status"] == "IN_PROGRESS" and not t["areas"]:
            warns.append(f"{tid}: IN_PROGRESS without Areas (dirty files cannot be attributed)")
        if t["lines"] > BUDGETS["task"]:
            warns.append(f"{tid}: {t['lines']} lines > {BUDGETS['task']} (split the task)")
        for d in t["deps"]:
            if d in ids:
                if t["status"] == "READY":
                    warns.append(f"{tid}: READY but depends on open {d}")
            elif has_git and d not in every and d not in {x["id"] for x in all_tasks}:
                warns.append(f"{tid}: depends on {d}, not open and not in Git history")
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
    print(f"{'OK' if not fails and not warns else 'SUMMARY'}: {len(tasks)} open tasks, "
          f"{len(adrs)} ADRs, {len(fails)} fail, {len(warns)} warn")
    return 2 if fails else 1 if warns else 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Project Brain helper", epilog="See SKILL.md.")
    ap.add_argument("--version", action="version", version=f"project-brain {VERSION} (schema {SCHEMA})")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("boot", "map", "init", "changed", "validate"):
        sub.add_parser(name).add_argument("root", nargs="?", default=".")
    p = sub.add_parser("new")
    p.add_argument("root")
    p.add_argument("title")
    p.add_argument("--depends", default="")
    p.add_argument("--risk", choices=RISK_VALUES, type=str.upper)
    p.add_argument("--priority", choices=PRIORITY_VALUES, type=str.upper)
    p.add_argument("--tier", choices=TIER_VALUES, type=str.upper)
    p = sub.add_parser("migrate")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 1
    if a.cmd == "new":
        return cmd_new(root, a.title, a.depends, a.risk, a.priority, a.tier)
    if a.cmd == "migrate":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import migrate
        return migrate.run(root, a.apply)
    return {"boot": cmd_boot, "map": cmd_map, "init": cmd_init,
            "changed": cmd_changed, "validate": cmd_validate}[a.cmd](root)


if __name__ == "__main__":
    sys.exit(main())
