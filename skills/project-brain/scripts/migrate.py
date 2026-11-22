"""Convert a legacy Project Brain to schema 4. Called by `brain.py migrate [--apply]`; preview by default.

Handles two legacy shapes:
  v1-v3  .project-brain/ with config schema < 4: "## Status" sections, inline "Objective:" tasks,
         plain acceptance bullets, statuses carrying notes.
  v0     a single PROJECT_BRAIN.md with numbered sections (GOAL, TARGET, CURRENT, FILE MAP, TASKS,
         DECISION LOG, HANDOFF) and "- [ ] T12 [L] title" task items.
Nothing is deleted. The model finishes the semantic part (Map, Sources, Steps) via WORKFLOW.md.
"""

import contextlib
import hashlib
import io
from pathlib import Path
import re
import sys

import runtime_core as Core

# Bound by brain.py on import via bind(B) so migrate.py has zero circular imports.
B = None


def bind(brain_module):
    global B
    B = brain_module


def _brain():
    if B is not None:
        return B
    mod = sys.modules.get("brain")
    if mod is not None:
        return mod
    raise RuntimeError("migrate module requires brain.bind() before standalone use")


SECTION_KEYS = {
    "status", "objective", "steps", "dependencies", "depends", "affected areas", "areas",
    "acceptance criteria", "acceptance", "verification", "verify", "architecture impact",
    "decision boundary", "escalate if", "discoveries", "resume", "notes", "blocker",
    "needed resolution", "safe work remaining", "context", "risk", "domains", "priority", "tier", "blocked",
    "owner", "handoff", "external", "evidence", "review", "inputs", "purpose", "secrets",
}
HEADER_ONLY = {
    "status", "dependencies", "depends", "affected areas", "areas", "risk", "domains",
    "priority", "tier", "blocked", "owner", "inputs", "purpose", "secrets",
}
PATH_RE = re.compile(r"(?<![\w`/])((?:[\w.-]+/)+[\w.*-]*)")
LEVELS = ("LOW", "MEDIUM", "HIGH")


def split_sections(text):
    """(title, [(name, lines)]) from '## X' sections and v3-inline 'X: value' paragraphs."""
    title, secs, resume_to = "", [("", [])], None
    for line in text.splitlines():
        if not title and line.startswith("# "):
            title = line[2:].strip()
            continue
        m2 = re.match(r"^##\s+(.+?)\s*$", line)
        mi = re.match(r"^\**([A-Za-z][A-Za-z ]*?)\**:\s*(.*)$", line)
        if resume_to is not None and not line.strip():
            secs.append((resume_to, [line]))
            resume_to = None
        elif m2:
            secs.append((m2.group(1), []))
            resume_to = None
        elif mi and mi.group(1).strip().lower() in SECTION_KEYS:
            key = mi.group(1).strip()
            if key.lower() not in HEADER_ONLY:
                resume_to = None
            elif resume_to is None:
                resume_to = secs[-1][0]
            secs.append((key, [mi.group(2)] if mi.group(2).strip() else []))
        else:
            secs[-1][1].append(line)
    return title, secs


def get(secs, *names):
    out = []
    for name, lines in secs:
        if name.lower() in names:
            out += lines
    return out


def trim(lines):
    lines = list(lines)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def checkboxes(lines):
    out = []
    for l in lines:
        m = re.match(r"^(\s*)[-*]\s+(?!\[[ xX]\])(.*)$", l)
        out.append(f"{m.group(1)}- [ ] {m.group(2)}" if m and not m.group(1) else l)
    return out


def paths_in(text):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        bullet = re.match(r"^[-*]\s+`?([^`\s,;)]+)`?", s)
        if bullet:
            out.append(bullet.group(1))
            continue
        parts = [p.strip().strip("`") for p in s.split(",") if p.strip()]
        if parts and all(re.fullmatch(r"[\w.*/-]+", p) for p in parts):
            out.extend(parts)
            continue
        ticks = re.findall(r"`([^`]+)`", s)
        if ticks:
            out.extend(ticks)
        else:
            out.extend(PATH_RE.findall(s))
    seen = []
    for x in (p.rstrip(".,;)") for p in out):
        if x and x not in seen:
            seen.append(x)
    return seen


def squash(text):
    return re.sub(r"[\s`,*\-.;:()]+", "", text).lower()


def keep_raw(notes, label, raw_lines, rendered):
    """Lossless rule: a header value that cannot hold its whole source keeps the source in Notes."""
    raw = " ".join(x.strip() for x in raw_lines if x.strip())
    if raw and squash(raw) != squash(rendered):
        notes.append(f"- {label} (migrated, original): {raw}")


def highest_level(text):
    found = [lv for lv in LEVELS if re.search(rf"\b{lv}\b", text, re.I)]
    return found[-1] if found else ""


def task_text(tid, title, head, body):
    """Render a schema-4 task. head: ordered dict of header lines; body: [(section, lines)]."""
    out = (
        [f"# {tid} — {title}"]
        + [f"{k}: {v}" if v != "" else f"{k}:" for k, v in head.items() if v or k == "Owner"]
        + [""]
    )
    for name, lines in body:
        lines = trim(lines)
        if lines or name in ("Acceptance", "Evidence", "Review", "Notes"):
            out += [f"## {name}"] + lines + [""]
    return "\n".join(out).rstrip() + "\n"


def convert_task(path):
    bm = _brain()
    text = bm.read(path) or ""
    title, secs = split_sections(text)
    title = re.sub(r"^PB-\d+\s*[—–-]\s*", "", title) or path.stem
    tid = bm.norm_id("PB", bm.TASK_FILE_RE.match(path.name).group(1))
    raw = " ".join(get(secs, "status")).strip()
    m = bm.STATUS_RE.match(raw)
    status = re.sub(r"[ -]", "_", m.group(1).upper()) if m else "?"
    note = raw[m.end():].strip(" -—–:.()") if m else raw
    if status.startswith("COMPLETE") or status == "DONE":
        return None, f"{tid}: DONE file kept; confirm its commit exists, then delete it"
    notes = trim(get(secs, "notes"))
    if status == "?":
        status = "PLANNED"
        notes.append(f"- Status (migrated): missing or unreadable in the legacy file{': ' + note if note else ''}")
        note = ""
    blocked = " ".join(trim(get(secs, "blocked", "blocker"))[:1]).strip() or (note if status == "BLOCKED" else "")
    if note and not (status == "BLOCKED" and note == blocked):
        notes.append(f"- Status note (migrated): {note}")
    deps_raw = get(secs, "dependencies", "depends")
    deps = [bm.norm_id("PB", n) for n in re.findall(r"PB-(\d+)", "\n".join(deps_raw))]
    keep_raw(notes, "Dependencies", deps_raw, ", ".join(deps) or "None")
    areas_raw = get(secs, "affected areas", "areas")
    areas = paths_in("\n".join(areas_raw))
    keep_raw(notes, "Areas", areas_raw, " ".join(areas))
    verify = get(secs, "verification", "verify")
    level_lines = [l for l in verify if re.fullmatch(r"\s*(LOW|MEDIUM|HIGH)([ -]+(LOW|MEDIUM|HIGH))*\.?\s*", l, re.I)]
    risk_raw = get(secs, "risk") + level_lines
    risk = highest_level("\n".join(risk_raw)) or "MEDIUM"
    keep_raw(notes, "Risk", risk_raw, risk)
    verify = [l for l in verify if l not in level_lines and not re.match(r"^\s*required\s*:?\s*$", l, re.I)]
    domains_raw = get(secs, "domains")
    impact = get(secs, "architecture impact")
    for l in impact:
        dm = re.match(r"^\s*domains\s*:\s*(.+)$", l, re.I)
        if dm and not domains_raw:
            domains_raw = [dm.group(1)]
    domains_src = " ".join(domains_raw)
    keep_raw(notes, "Domains", domains_raw, " ".join(bm.split_list(domains_src)))
    impact_rest = [
        l
        for l in impact
        if l.strip()
        and not re.match(r"^\s*domains\s*:", l, re.I)
        and not re.fullmatch(r"\s*expected\s*:\s*(yes|no)\.?\s*", l, re.I)
    ]
    if impact_rest:
        notes.append("- Architecture impact (migrated): " + " ".join(x.strip() for x in impact_rest))
    for extra_sec, label in (
        ("discoveries", "Discoveries"),
        ("needed resolution", "Needed resolution"),
        ("safe work remaining", "Safe work remaining"),
    ):
        extra_lines = trim(get(secs, extra_sec))
        if extra_lines:
            notes.append(f"- {label} (migrated): " + " ".join(x.strip() for x in extra_lines if x.strip()))
    owner = " ".join(trim(get(secs, "owner"))).strip()
    priority = " ".join(trim(get(secs, "priority"))).strip().upper() or "P2"
    tier = " ".join(trim(get(secs, "tier"))).strip().upper() or "M"
    head = {
        "Status": status,
        "Priority": priority,
        "Tier": tier,
        "Risk": risk,
        "Owner": owner,
        "Depends": ", ".join(deps) or "-",
        "Areas": ", ".join(f"`{a}`" for a in areas),
        "Domains": ", ".join(bm.split_list(domains_src)) if domains_src else "",
        "Blocked": blocked if status == "BLOCKED" else "",
    }
    for name in ("Inputs", "Purpose", "Secrets"):
        value = " ".join(trim(get(secs, name.lower())))
        if value:
            head[name] = value
    body = [
        ("Objective", get(secs, "objective", "context") or get(secs, "")),
        ("Steps", get(secs, "steps")),
        ("Acceptance", checkboxes(get(secs, "acceptance criteria", "acceptance"))),
        ("Verify", verify),
        ("Escalate if", get(secs, "decision boundary", "escalate if")),
        ("Resume", get(secs, "resume", "handoff")),
        ("External", get(secs, "external")),
        ("Evidence", get(secs, "evidence")),
        ("Review", get(secs, "review")),
    ]
    known = {
        "objective", "context", "", "steps", "acceptance criteria", "acceptance", "verification", "verify",
        "decision boundary", "escalate if", "notes", "architecture impact", "discoveries",
        "needed resolution", "safe work remaining", "resume", "handoff", "external", "evidence", "review",
    } | HEADER_ONLY
    body += [(name, lines) for name, lines in secs if name.lower() not in known]
    body.append(("Notes", notes))
    return task_text(tid, title, head, body), None


def migrate_dir(root, plan, todo):
    bm = _brain()
    b = bm.bp(root)
    plan.append((b / "config.yaml", bm.config_text(root, bm.parse_config(root)), "schema 4 (old values kept)"))
    backup = b / "migration-backup"
    target_source = backup / "target.md" if (backup / "target.md").exists() else b / "target.md"
    target = bm.read(target_source)
    if target is not None and not re.search(r"^Status:\s*(DRAFT|CONFIRMED)\b", target, re.M | re.I):
        lines = target.splitlines()
        i = next((k + 1 for k, l in enumerate(lines) if l.startswith("# ")), 0)
        lines.insert(i, "Status: DRAFT")
        text = "\n".join(lines) + "\n"
        if "## Goal" not in text:
            text = re.sub(r"^## (Objective)\s*$", "## Goal", text, count=1, flags=re.M)
        plan.append((b / "target.md", text, "Status: DRAFT (approval absent; verify user intent)"))
    cur = "\n".join(bm.read(f) or "" for f, _ in bm.current_files(root))
    if "## Map" not in cur:
        todo.append("current.md has no `## Map` (path -> role): write it from the code (<=40 lines)")
    if not re.search(r"^\W*sources\W*:", cur, re.I | re.M):
        todo.append("current.md has no `Sources:` lines: add globs per domain")
    if not (b / ".gitignore").exists():
        plan.append((b / ".gitignore", ".cache/\n", "ignore cache"))
    tdir = b / "tasks"
    tasks = bm.list_tasks(root)
    ip = [t["id"] for t in tasks if t["status"] == "IN_PROGRESS"]
    if len(ip) > 1:
        todo.append(f"several IN_PROGRESS ({', '.join(ip)}): keep the one really active, set the rest READY")
    files = {f.name: f for f in tdir.glob("PB-*.md") if bm.TASK_FILE_RE.match(f.name)}
    files.update({f.name: f for f in (backup / "tasks").glob("PB-*.md") if bm.TASK_FILE_RE.match(f.name)})
    for name, source in sorted(files.items()):
        f = tdir / name
        new, issue = convert_task(source)
        if issue:
            todo.append(issue)
        elif new != bm.read(f):
            plan.append((f, new, "task -> schema 4"))


ITEM_RE = re.compile(r"^- \[( |~|x|X|!|-)\]\s+T(\d+)(?:\.(\d+))?\s*(?:\[(L|M|H)\])?\s*(.*)$")
FIELD_RE = re.compile(r"^\s+-\s+(Where|Do|Done when|Needs|Note)\s*:\s*(.*)$", re.I)


def v0_sections(text):
    secs, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^## (\d+(?:\.\d+)?)\.?\s+(.+?)\s*$", line)
        if m:
            cur = m.group(1)
            secs[cur] = {"title": m.group(2), "lines": []}
        elif cur:
            secs[cur]["lines"].append(line)
    return secs


def v0_tasks(lines):
    items, milestone = [], ""
    for line in lines:
        h = re.match(r"^###\s+(.+)$", line)
        m = ITEM_RE.match(line)
        f = FIELD_RE.match(line)
        if h:
            milestone = h.group(1).strip()
        elif m:
            items.append({
                "mark": m.group(1),
                "num": int(m.group(2)),
                "sub": m.group(3),
                "tier": m.group(4) or "",
                "title": re.sub(r"\s*\((claimed|\d{4}-\d\d-\d\d)[^)]*\)\s*$", "", m.group(5)).strip(),
                "milestone": milestone,
                "fields": {},
                "last": None,
            })
        elif f and items:
            key = f.group(1).lower()
            items[-1]["fields"][key] = items[-1]["fields"].get(key, "") + f.group(2)
            items[-1]["last"] = key
        elif items and items[-1]["last"] and line.startswith("    ") and line.strip():
            k = items[-1]["last"]
            items[-1]["fields"][k] += " " + line.strip()
    return items


def migrate_v0(root, plan, todo):
    bm = _brain()
    b, legacy = bm.bp(root), Path(root) / bm.LEGACY_FILE
    text = bm.read(legacy) or ""
    secs = v0_sections(text)
    sec = lambda key: "\n".join(trim(secs.get(key, {}).get("lines", [])))
    header_and_s1 = text.split("\n## 2", 1)[0]
    gs = re.search(r"^\s*(?:[-*]\s*)?\*{0,2}Goal status:\*{0,2}\s*(\w+)\b", header_and_s1, re.I | re.M)
    tstat = "CONFIRMED" if gs and gs.group(1).upper() == "CONFIRMED" else "DRAFT"
    plan.append((b / "config.yaml", bm.config_text(root), "schema 4"))
    plan.append((b / ".gitignore", ".cache/\n", "ignore cache"))
    plan.append((
        b / "target.md",
        f"# Target Architecture\nStatus: {tstat}\n\n## Goal\n{sec('1')}\n\n"
        f"## Target State\n{sec('2')}\n\n## Non-Goals\n\n## Open Decisions\n\n## Success Conditions\n"
        f"- see Goal acceptance criteria\n",
        f"from sections 1-2 (goal status {tstat})",
    ))
    plan.append((
        b / "current.md",
        f"# Current Architecture\n\n## Map\n{sec('4')}\n\n## Domains\n{sec('3')}\n",
        "from sections 3-4",
    ))
    todo.append("current.md: add `Sources:` globs per domain; check markers against the code")
    items = v0_tasks(secs.get("5", {}).get("lines", []))
    open_marks = {" ", "~", "!"}
    open_nums = {i["num"] for i in items if i["mark"] in open_marks and not i["sub"]}
    parents = {i["num"]: i for i in items if not i["sub"]}
    next_id = max([i["num"] for i in items] + [0]) + 1
    handoff = sec("7")
    for it in items:
        if it["mark"] in open_marks and it["sub"] and it["num"] in open_nums:
            parents[it["num"]].setdefault("subs", []).append(it)
    for it in items:
        if it["mark"] not in open_marks or (it["sub"] and it["num"] in open_nums):
            continue
        num = it["num"]
        if it["sub"]:
            num, next_id = next_id, next_id + 1
        fl = it["fields"]
        needs = [bm.norm_id("PB", n) for n in re.findall(r"T(\d+)", fl.get("needs", "")) if int(n) in open_nums]
        steps = [
            f"{k}. {x.strip()}"
            for k, x in enumerate([x for x in re.split(r"\s*\d+\)\s*", fl.get("do", "")) if x.strip()], 1)
        ]
        if fl.get("where"):
            steps.insert(0, f"Where: {fl['where']}")
        for sub in it.get("subs", []):
            steps.append(
                f"Sub-task T{sub['num']}.{sub['sub']}: {sub['title']} "
                + " ".join(f"{k}: {v}" for k, v in sub["fields"].items())
            )
        done_when = fl.get("done when", "")
        status = {"~": "IN_PROGRESS", "!": "BLOCKED"}.get(it["mark"], "READY")
        if status == "READY" and (needs or not (steps and done_when)):
            status = "PLANNED"
        notes = [f"- Milestone: {it['milestone']}"] if it["milestone"] else []
        notes += [f"- Legacy ID: T{it['num']}{'.' + it['sub'] if it['sub'] else ''}"]
        if fl.get("note"):
            notes.append(f"- {fl['note']}")
        body = [
            ("Objective", [it["title"]]),
            ("Steps", steps),
            ("Acceptance", [f"- [ ] {done_when}"] if done_when else []),
            ("Verify", [f"- `{c}`" for c in re.findall(r"`([^`]+)`", done_when)]),
            ("Evidence", []),
            ("Review", []),
            ("Notes", notes),
        ]
        if status == "IN_PROGRESS" and handoff:
            body.insert(4, ("Resume", ["Next: see handoff below (migrated)"] + handoff.splitlines()))
            handoff = ""
        tid = bm.norm_id("PB", num)
        head = {
            "Status": status,
            "Priority": "P2",
            "Tier": it["tier"] or "M",
            "Risk": "MEDIUM",
            "Owner": "",
            "Depends": ", ".join(needs) or "-",
            "Areas": ", ".join(f"`{a}`" for a in paths_in(fl.get("where", ""))),
            "Blocked": (it["title"] if status == "BLOCKED" else ""),
        }
        plan.append((b / "tasks" / f"{tid}.md", task_text(tid, it["title"][:80], head, body), f"from T{it['num']}"))
    adr = [
        f"# ADR-000 — Legacy decision log\n\n## Status\n\nAccepted\n\n## Context\n\nMigrated verbatim from "
        f"{bm.LEGACY_FILE} section 6.\n\n## Decision\n\n{sec('6')}\n"
    ]
    if handoff:
        adr.append(f"\n## Last handoff (migrated)\n\n{handoff}\n")
    plan.append((b / "decisions" / "ADR-000.md", "".join(adr), "decision log + handoff"))
    extra = [k for k in secs if k not in {"0", "1", "2", "3", "4", "5", "6", "7"}]
    custom0 = "### 0.1 What this file is" not in text and sec("0")
    legacy_notes = ([f"## Legacy protocol notes (review)\n{sec('0')}\n"] if custom0 else []) + [
        f"## Legacy: {secs[k]['title']} (review)\n{sec(k)}\n" for k in extra
    ]
    plan.append((
        b / "constraints.md",
        "# Constraints\n\nOnly rules that change decisions.\n\n" + "\n".join(legacy_notes),
        "legacy extra sections kept for review" if legacy_notes else "empty",
    ))
    if legacy_notes:
        todo.append("constraints.md: turn the legacy sections into one-line rules or delete them")
    todo.append(f"{bm.LEGACY_FILE}: delete it after reviewing the migration (Git keeps it)")
    todo.append("closed legacy tasks remain in migration-backup/PROJECT_BRAIN.md; review them before claiming completion")


def migrate_v3_upgrade(root, plan, todo, force_all=True):
    bm = _brain()
    b = bm.bp(root)
    target = bm.read(b / "target.md")
    if target is not None and not re.search(r"^Status:\s*(DRAFT|CONFIRMED)\b", target, re.M | re.I):
        lines = target.splitlines()
        i = next((k + 1 for k, l in enumerate(lines) if l.startswith("# ")), 0)
        lines.insert(i, "Status: DRAFT")
        text = "\n".join(lines) + "\n"
        if "## Goal" not in text:
            text = re.sub(r"^## (Objective)\s*$", "## Goal", text, count=1, flags=re.M)
        plan.append((b / "target.md", text, "Status: DRAFT (approval absent; verify user intent)"))
    if not (b / ".gitignore").exists():
        plan.append((b / ".gitignore", ".cache/\n", "ignore cache"))
    tdir = b / "tasks"
    if tdir.is_dir():
        legacy_secs = {
            "status", "acceptance criteria", "verification", "affected areas", "dependencies",
            "architecture impact", "context", "decision boundary", "blocker", "handoff",
            "discoveries", "needed resolution", "safe work remaining",
        }
        for f in sorted(tdir.glob("PB-*.md")):
            if not bm.TASK_FILE_RE.match(f.name):
                continue
            raw = bm.read(f) or ""
            secs = bm.sections(raw)
            parsed = bm.parse_task(f, raw)
            has_full_body = "objective" in secs and ("acceptance" in secs or "acceptance criteria" in secs)
            if not force_all and not has_full_body:
                continue
            missing_v34 = has_full_body and (
                "evidence" not in secs
                or "review" not in secs
                or not re.search(r"^Owner:", raw, re.M | re.I)
                or not re.search(r"^Risk:\s*\S+", raw, re.M | re.I)
                or not re.search(r"^Tier:\s*\S+", raw, re.M | re.I)
                or not re.search(r"^Priority:\s*\S+", raw, re.M | re.I)
            )
            if (set(secs) & legacy_secs) or missing_v34 or (parsed and (parsed.get("status_note") or parsed.get("status") == "?")):
                new, issue = convert_task(f)
                if issue:
                    todo.append(issue)
                elif new and new != raw:
                    plan.append((f, new, "task -> schema 4 (upgrade)"))


def has_pending_upgrade(root, force_all=True):
    bm = _brain()
    if bm.legacy_kind(root):
        return True
    if not bm.brain_exists(root):
        return False
    cfg = bm.parse_config(root)
    if cfg.get("skill_version") != bm.VERSION:
        return True
    plan, todo = [], []
    migrate_v3_upgrade(Path(root), plan, todo, force_all=force_all)
    return bool(plan)


def auto_upgrade_v34(root, force_all=None):
    bm = _brain()
    root = Path(root)
    if not bm.brain_exists(root):
        return []
    require_supported(root)
    cfg_path = bm.bp(root) / "config.yaml"
    old_cfg = bm.parse_config(root) if cfg_path.exists() else {}
    old_ver = old_cfg.get("skill_version", "")
    if force_all is None:
        force_all = old_ver != bm.VERSION
    plan, todo = [], []
    migrate_v3_upgrade(root, plan, todo, force_all=force_all)
    backup_inputs(root, [p for p, _, _ in plan] + ([cfg_path] if old_ver != bm.VERSION else []))
    actions = []
    for path, text, why in plan:
        rel = path.relative_to(root).as_posix()
        Core.write_atomic(path, text)
        actions.append(f"{rel} ({why})")
    if old_ver != bm.VERSION:
        for name, action in bm.ensure_pointers(root, write=True):
            actions.append(f"{name} ({action})")
    if old_ver != bm.VERSION or not cfg_path.exists():
        new_cfg_text = bm.config_text(root, old_cfg)
        if not cfg_path.exists() or bm.read(cfg_path) != new_cfg_text:
            Core.write_atomic(cfg_path, new_cfg_text)
            if old_ver != bm.VERSION:
                actions.append(f"config.yaml (skill_version {old_ver or 'pre-3.4'} -> {bm.VERSION})")
    return actions


def require_known_legacy(root):
    bm = _brain()
    kind = bm.legacy_kind(root)
    if kind == "v0":
        sections = v0_sections(bm.read(Path(root) / bm.LEGACY_FILE) or "")
        expected = {"1": "GOAL", "3": "CURRENT", "5": "TASKS"}
        if not all(key in sections and word in sections[key]["title"].upper() for key, word in expected.items()):
            raise ValueError("Unrecognized legacy PROJECT_BRAIN.md; inspect before explicit migration")
    elif kind:
        schema = str(bm.parse_config(root).get("schema_version", ""))
        if schema not in ("1", "2", "3"):
            raise ValueError("Unrecognized legacy Brain schema; inspect before explicit migration")


def startup(root, maintain=True):
    bm = _brain()
    require_supported(root)
    if not maintain or bm.merge_op(root):
        return []
    kind = bm.legacy_kind(root)
    notes = []
    if kind:
        require_known_legacy(root)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            run(root, apply=True)
        notes.append("VERSION_CHECK: auto-migrated %s -> v%s (schema %s)" % (kind, bm.VERSION, bm.SCHEMA))
        notes.extend(line for line in output.getvalue().splitlines() if line.startswith("TODO "))
    if bm.brain_exists(root) and not bm.legacy_kind(root):
        old = bm.parse_config(root).get("skill_version", "")
        if old != bm.VERSION or has_pending_upgrade(root, force_all=False):
            actions = auto_upgrade_v34(root, force_all=(old != bm.VERSION))
            if actions:
                notes.append(
                    "VERSION_CHECK: auto-upgraded project (%s -> v%s): %s"
                    % (old or "pre-3.4", bm.VERSION, ", ".join(actions[:6]))
                )
    return notes


def require_supported(root):
    bm = _brain()
    cfg = bm.parse_config(root)
    schema = str(cfg.get("schema_version", ""))
    version = str(cfg.get("skill_version", "")).strip()
    current = tuple(int(n) for n in bm.VERSION.split("."))
    if schema.isdigit() and int(schema) > bm.SCHEMA:
        raise ValueError("Newer Brain schema; use a compatible skill before migration")
    if version:
        m = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(.*)$", version)
        if not m:
            raise ValueError("Unsupported Brain skill_version format; refusing automatic downgrade")
        parsed = (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0))
        suffix = (m.group(4) or "").strip()
        if parsed > current or (parsed == current and suffix and not suffix.startswith("+")):
            raise ValueError("Newer Brain skill_version; refusing automatic downgrade")


def backup_inputs(root, paths):
    """Retain each distinct raw input atomically before conversion; never overwrite an earlier backup."""
    bm = _brain()
    root = Path(root).resolve()
    for source in paths:
        src_abs = Path(source).resolve() if Path(source).is_absolute() else (root / source).resolve()
        rel = src_abs.relative_to(root).as_posix()
        source = Core.public_path(root, rel)
        if not source.is_file():
            continue
        name = source.relative_to(bm.bp(root)) if source != root / bm.LEGACY_FILE else Path(bm.LEGACY_FILE)
        saved_rel = bm.BRAIN_DIR + "/migration-backup/" + name.as_posix()
        saved = Core.public_path(root, saved_rel)
        raw = source.read_bytes()
        if saved.exists() and saved.read_bytes() != raw:
            saved = Core.public_path(root, saved_rel + "." + hashlib.sha256(raw).hexdigest()[:16])
        if not saved.exists():
            Core.write_atomic_bytes(saved, raw)


def run(root, apply, sync_skills=False):
    bm = _brain()
    if sync_skills:
        raise ValueError("Installed skills are managed separately; use Skills Manager to preserve deployment metadata")
    root = Path(root)
    require_supported(root)
    if apply and bm.merge_op(root):
        raise ValueError("Git merge/rebase/cherry-pick in progress; resolve it before `migrate --apply`")
    kind = bm.legacy_kind(root)
    plan, todo = [], []
    if kind == "v0":
        migrate_v0(root, plan, todo)
    elif kind:
        migrate_dir(root, plan, todo)
        if (root / bm.LEGACY_FILE).exists():
            todo.append(f"{bm.LEGACY_FILE} (old pointer/summary): carry over unique facts, then delete it")
    elif bm.brain_exists(root):
        migrate_v3_upgrade(root, plan, todo)
        cfg = bm.parse_config(root)
        if cfg.get("skill_version") != bm.VERSION:
            plan.append((bm.bp(root) / "config.yaml", bm.config_text(root, cfg), "record skill version"))
        if plan:
            kind = "schema-4 upgrade"
        else:
            print("NOTHING TO MIGRATE: .project-brain/ is already schema 4")
            return 0
    else:
        print("NOTHING TO MIGRATE: no legacy Brain found (use `init` for a new one)")
        return 0
    if not apply:
        print(f"PREVIEW ({kind}): nothing written. Run `migrate --apply` to write.")
    else:
        backup_inputs(root, [root / bm.LEGACY_FILE] + [p for p, _, _ in plan])
        print("BACKUP .project-brain/migration-backup/: original input retained; review before removing")
    config = [(p, t, why) for p, t, why in plan if p.name == "config.yaml"]
    plan = [(p, t, why) for p, t, why in plan if p.name != "config.yaml"]
    for path, text, why in plan:
        rel = path.relative_to(root).as_posix()
        verb = ("UPDATE" if path.exists() else "CREATE") if apply else ("would update" if path.exists() else "would create")
        print(f"{verb} {rel}: {why}")
        if apply:
            Core.write_atomic(path, text)
    for name, action in bm.ensure_pointers(root, write=apply):
        print(f"{'POINTER' if apply else 'would add pointer to'} {name} ({action})")
    for path, text, why in config:
        print(f"{'FINALIZE' if apply else 'would finalize'} {path.relative_to(root).as_posix()}: {why}")
        if apply:
            Core.write_atomic(path, text)
    for t in todo:
        print(f"TODO {t}")
    print(
        "NEXT: "
        + (
            "`validate`, finish the TODO lines, Plan audit (WORKFLOW.md §6), commit `chore(brain): migrate to schema 4`."
            if apply
            else "review the preview, then `migrate --apply`."
        )
    )
    return 0
