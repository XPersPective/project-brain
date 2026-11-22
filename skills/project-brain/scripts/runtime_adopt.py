"""Foreign tracker detection, import, and verified recoverable cleanup. Stdlib only."""

import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import uuid
import zipfile

import runtime_core as Core
import runtime_security as S

TRACE_SCHEMA = 1
STATES = ("PREPARED", "VERIFIED", "ARCHIVED", "CLEANING", "CLEANED")
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".project-brain", "node_modules", ".venv", "venv",
    "__pycache__", "dist", "build", "target", "bin", "obj",
}
TRACKING_EXTENSIONS = {".md", ".json", ".yaml", ".yml", ".txt", ".toml"}
INSTRUCTION_FILES = {"AGENTS.md", "CLAUDE.md", "GEMINI.md"}
UNRESOLVED = re.compile(
    r"^\s*-\s*(?:(?P<op>[A-Za-z0-9_.:/-]+)\s*(?:\||:)\s*)?(?P<state>sent|response_unknown)\b",
    re.I | re.M,
)
POINTER_CUE = re.compile(r"\b(load|read|use|follow|see|check|start with|continue in)\b", re.I)
POINTER_RISK = re.compile(
    r"\b(security|credential|secret|token|permission|authorization|password|private key|must not|never|do not|don't)\b",
    re.I,
)
TRACKER_NAMES = (".taskmaster", "memory-bank", ".kiro", ".factory", "_bmad", "openspec", ".planning")

FOREIGN_SYSTEMS = (
    ("project-brain-v0", ("PROJECT_BRAIN.md",)),
    ("taskmaster", (".taskmaster/tasks/tasks.json", ".taskmaster")),
    ("Spec Kit", (".specify", "specs")),
    ("BMAD", ("_bmad", "_bmad-output", ".bmad-core")),
    ("OpenSpec", ("openspec",)),
    ("GSD", (".planning",)),
    ("Kiro", (".kiro/specs", ".kiro/steering")),
    ("Memory Bank", ("memory-bank", ".cursor/memory-bank")),
    ("Factory", (".factory", "missions")),
    ("Flat file", ("TODO.md", "TASKS.md", "PLAN.md", "ROADMAP.md")),
)

STORE_RELEASE_SKIP_RE = re.compile(
    r"\b(play[- ]store|google[- ]play|app[- ]store|appstore|fastlane|store[- ]listing|testflight|"
    r"publish(?:ing|ed)?|publication|distribution|deploy(?:ment|ing)?|release|yayın\w*|yayımla\w*|dağıtım\w*)\b",
    re.I,
)


def _read_safe(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def detect_foreign(root):
    root = Path(root)
    hits = []
    for name, markers in FOREIGN_SYSTEMS:
        found = [m for m in markers if (root / m).exists()]
        if found:
            hits.append((name, found))
    return hits


def _extract_foreign_tasks(root):
    """Extract candidate tasks from .planning/tasks, .taskmaster, or markdown checklists."""
    root = Path(root)
    extracted = []
    plan_tasks = root / ".planning" / "tasks"
    if plan_tasks.is_dir() and not Core.is_link(plan_tasks):
        for f in sorted(plan_tasks.glob("*.md")):
            text = _read_safe(Core.public_path(root, f.relative_to(root).as_posix())) or ""
            title_m = re.search(r"^#\s+(?:[A-Z]+-\d+\s*[—–-]\s*)?(.+)$", text, re.M)
            title = title_m.group(1).strip() if title_m else f.stem
            if STORE_RELEASE_SKIP_RE.search(title) or STORE_RELEASE_SKIP_RE.search(text):
                continue
            if re.search(r"^Status:\s*(DONE|COMPLETE(?:D)?|CANCELLED|CANCELED)\b", text, re.I | re.M):
                continue
            extracted.append({"source": f.relative_to(root).as_posix(), "title": title, "text": text})
    tm_json = root / ".taskmaster" / "tasks" / "tasks.json"
    if tm_json.exists():
        try:
            tdata = json.loads(_read_safe(Core.public_path(root, tm_json.relative_to(root).as_posix())) or "{}")
            items = tdata.get("tasks", []) if isinstance(tdata, dict) else []
            if isinstance(tdata, dict) and not items:
                items = [item for tag in tdata.values() if isinstance(tag, dict) for item in tag.get("tasks", [])]
            for item in items or []:
                if (
                    isinstance(item, dict)
                    and item.get("title")
                    and item.get("status", "").lower() not in ("done", "completed", "cancelled", "canceled")
                ):
                    text = json.dumps(item, ensure_ascii=False, indent=2)
                    if STORE_RELEASE_SKIP_RE.search(text):
                        continue
                    extracted.append({
                        "source": ".taskmaster/tasks/tasks.json",
                        "title": item["title"],
                        "objective": item.get("description") or item["title"],
                        "text": text,
                    })
        except ValueError:
            pass
    for flat in ("TODO.md", "TASKS.md", "PLAN.md", "ROADMAP.md"):
        fp = root / flat
        if fp.exists():
            for line in (_read_safe(Core.public_path(root, flat)) or "").splitlines():
                m = re.match(r"^\s*-\s*\[\s*\]\s+(.+)$", line)
                if m and not STORE_RELEASE_SKIP_RE.search(m.group(1)):
                    extracted.append({"source": flat, "title": m.group(1).strip(), "text": line})
    return extracted


def cmd_legacy(B, root, apply=False, migrate_fn=None):
    root = Path(root)
    hits = detect_foreign(root)
    if not hits:
        print("NONE: no foreign planning systems detected")
        return 0
    for name, paths in hits:
        print(f"FOREIGN {name}: {', '.join(paths)}")
    candidates_list = _extract_foreign_tasks(root)
    print(f"CANDIDATES: {len(candidates_list)} open tasks (store publishing/distribution tasks filtered out)")
    for c in candidates_list[:15]:
        print(f"  - [{c['source']}] {c['title'][:70]}")
    if not apply:
        print("NEXT: Run `legacy --apply` to initialize `.project-brain/` and import non-publishing tasks as PLANNED.")
        return 0
    if any(name == "project-brain-v0" for name, _ in hits):
        if migrate_fn is not None:
            return migrate_fn(root, apply=True)
        raise ValueError("Run `migrate --apply` to convert PROJECT_BRAIN.md")
    if not B.brain_exists(root):
        B.cmd_init(root)
    created = 0
    for c in candidates_list:
        title = " ".join(str(c["title"]).split())
        raw = c.get("text") or c.get("objective") or title
        source_id = hashlib.sha256((c["source"] + "\0" + raw).encode("utf-8")).hexdigest()[:16]
        source_rel = f".project-brain/migration-backup/imported/{source_id}-source.md"
        source = Core.public_path(root, source_rel)
        source.parent.mkdir(parents=True, exist_ok=True)
        if not source.exists():
            Core.write_atomic(source, raw)
        tasks = B.list_tasks(root)
        if any(source_rel in t["objective"] for t in tasks):
            continue
        partial = [
            t
            for t in tasks
            if t["title"] == title
            and t["status"] == "PLANNED"
            and t["text"].strip()
            == B.TASK_TMPL.format(
                id=t["id"], title=title, status="PLANNED", risk="MEDIUM", priority="P2", tier="M", deps="-"
            ).strip()
        ]
        if partial:
            task = partial[0]
        else:
            before = {t["id"] for t in tasks}
            rc = B.cmd_new(root, title, depends="", risk="MEDIUM", priority="P2", tier="M")
            if rc:
                return rc
            task = next(t for t in B.list_tasks(root) if t["id"] not in before)
            created += 1
        body = B.read(task["file"])
        objective = f"Imported from `{c['source']}`. Read the preserved original at `{source_rel}` before refining this task."
        Core.write_atomic(task["file"], body.replace("<what and why, in the user's words>", objective, 1))
    print(f"ADOPTED: created {created} PLANNED tasks in .project-brain/tasks/")
    return 0


def trace_file(B, root):
    return Core.public_path(root, ".project-brain/adoption.json")


def status(B, root):
    p = trace_file(B, root)
    if not p.exists():
        return {}
    try:
        data = Core.read_json(p, max_bytes=4 * 1024 * 1024, strict_constants=True)
    except (OSError, ValueError) as exc:
        raise ValueError("adoption trace is unreadable or malformed") from exc
    if not isinstance(data, dict) or data.get("schema") != TRACE_SCHEMA:
        raise ValueError("unsupported adoption trace")
    if data.get("state") not in STATES or not isinstance(data.get("id"), str) or not isinstance(data.get("sources"), list):
        raise ValueError("invalid adoption trace state or shape")
    return data


def _save(B, root, data):
    Core.write_atomic(trace_file(B, root), json.dumps(data, ensure_ascii=False, indent=2))


def _hash_bytes(data):
    return Core.sha256_bytes(data)


def _atomic_hash(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return _hash_bytes(text.encode("utf-8"))


def _hash_file(path):
    return _hash_bytes(path.read_bytes())


def _rel(root, path):
    return Path(path).relative_to(Path(root)).as_posix()


def _safe(root, rel):
    if not isinstance(rel, str) or not rel or "\\" in rel:
        raise ValueError("adoption paths must be nonempty project-relative paths")
    pp = PureWindowsPath(rel)
    if pp.anchor or ":" in rel or ".." in pp.parts or rel.startswith(".project-brain/"):
        raise ValueError("private or escaping adoption path refused: " + rel)
    if any(part.lower() in SKIP_DIRS for part in pp.parts):
        raise ValueError("infrastructure path refused: " + rel)
    path = Core.public_path(root, rel)
    if path.exists() and not (path.is_file() or path.is_dir()):
        raise ValueError("unsupported filesystem object: " + rel)
    return path


def _target_safe(root, rel):
    if isinstance(rel, str) and rel.startswith(".project-brain/"):
        parts = PureWindowsPath(rel).parts
        if len(parts) < 2 or any(part.lower() in {".cache", "migration-backup", "adoption.json"} for part in parts):
            raise ValueError("private Project Brain destination refused: " + rel)
        path = Core.public_path(root, rel)
        if path.exists() and not path.is_file():
            raise ValueError("adoption destination must be a file: " + rel)
        return path
    return _safe(root, rel)


def _enumerate(root, rel):
    path = _safe(root, rel)
    if not path.exists():
        raise ValueError("adoption source does not exist: " + rel)
    files = []
    if path.is_file():
        files = [path]
    else:
        for base, dirs, names in os.walk(str(path), topdown=True, followlinks=False):
            basep = Path(base)
            for d in list(dirs):
                child = basep / d
                child_rel = _rel(root, child)
                if d.lower() in SKIP_DIRS:
                    dirs.remove(d)
                    continue
                _safe(root, child_rel)
            for name in names:
                child = basep / name
                child_rel = _rel(root, child)
                _safe(root, child_rel)
                if Core.is_link(child):
                    raise ValueError("linked source refused: " + child_rel)
                _tracking_file(child_rel)
                files.append(child)
    result = []
    for f in sorted(files, key=lambda p: _rel(root, p).casefold()):
        relpath = _rel(root, f)
        _safe(root, relpath)
        _tracking_file(relpath)
        result.append({"path": relpath, "sha256": _hash_file(f), "targets": [], "drop_reason": ""})
    return result


def _tracking_file(rel):
    if Path(rel).suffix.lower() not in TRACKING_EXTENSIONS:
        raise ValueError("unsupported non-tracking file refused: " + rel)


def _roots(paths):
    clean = sorted(set(paths), key=lambda p: (p.count("/"), p.casefold()))
    out = []
    for path in clean:
        if not any(path == parent or path.startswith(parent.rstrip("/") + "/") for parent in out):
            out.append(path)
    return out


def _default_paths(root):
    found = []
    for _name, paths in detect_foreign(root):
        for path in paths:
            if path == "PROJECT_BRAIN.md":
                continue
            if path in ("TODO.md", "TASKS.md"):
                safe_p = Core.public_path(root, path)
                text = safe_p.read_text(encoding="utf-8", errors="replace")
                if re.search(r"^\s*-\s*\[[ xX]\]\s+", text, re.M):
                    found.append(path)
                continue
            if path in ("PLAN.md", "ROADMAP.md", "README.md"):
                continue
            found.append(path)
    return _roots(found)


def _project_exists(B, root):
    if not B.brain_exists(root):
        raise ValueError("initialize Project Brain before preparing adoption")


def prepare(B, root, paths=()):
    root = Path(root).resolve()
    _project_exists(B, root)
    existing = status(B, root)
    if existing and existing.get("state") in ("PREPARED", "VERIFIED", "ARCHIVED", "CLEANING"):
        raise ValueError("adoption trace already has pending work; finish or verify it instead of re-preparing")
    chosen = _roots(list(paths) if paths else _default_paths(root))
    if not chosen:
        raise ValueError("no foreign tracking sources selected")
    sources = []
    for rel in chosen:
        sources.extend(_enumerate(root, rel))
    if not sources:
        raise ValueError("selected foreign sources contain no tracking files")
    data = {
        "schema": TRACE_SCHEMA,
        "id": uuid.uuid4().hex[:12],
        "state": "PREPARED",
        "roots": chosen,
        "sources": sources,
        "instruction_removals": [],
        "source_snapshot": {},
        "target_snapshot": {},
        "instruction_snapshot": {},
        "instruction_after_snapshot": {},
        "ignore_snapshot": {},
        "ignore_after_snapshot": {},
        "reviewed_note": "",
        "archive": {},
    }
    _save(B, root, data)
    return data


def _source_snapshot(root, roots):
    snapshot = {}
    for rel in roots:
        for item in _enumerate(root, rel):
            snapshot[item["path"]] = item["sha256"]
    return snapshot


def _read_text(path):
    return path.read_text(encoding="utf-8", errors="replace")


def _validate_targets(B, root, data):
    targets = {}
    for item in data["sources"]:
        raw_tlist = item.get("targets", [])
        drop = str(item.get("drop_reason", "")).strip()
        if not isinstance(raw_tlist, list):
            raise ValueError("invalid adoption targets for " + item["path"])
        tlist = []
        for entry in raw_tlist:
            if isinstance(entry, str) and entry.strip():
                tlist.append(entry.strip())
            elif isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"].strip():
                tlist.append(entry["path"].strip())
            else:
                raise ValueError("invalid adoption targets for " + item["path"])
        if not tlist and not drop:
            raise ValueError("every source needs targets or drop_reason: " + item["path"])
        if drop and tlist:
            raise ValueError("source cannot have both targets and drop_reason: " + item["path"])
        if drop:
            src_path = _safe(root, item["path"])
            if src_path.is_file() and UNRESOLVED.search(_read_text(src_path)):
                raise ValueError("source with unresolved external operation cannot be dropped: " + item["path"])
        for rel in tlist:
            p = _target_safe(root, rel)
            if not p.is_file() or not p.stat().st_size:
                raise ValueError("adoption destination missing or empty: " + rel)
            text = _read_text(p)
            if UNRESOLVED.search(text):
                raise ValueError("unresolved external operation in destination: " + rel)
            targets[rel] = _hash_file(p)
    return targets


def _instruction_data(B, root, data):
    removals = data.get("instruction_removals", [])
    if not isinstance(removals, list):
        raise ValueError("invalid instruction_removals")
    snapshots, results = {}, []
    for entry in removals:
        if not isinstance(entry, dict):
            raise ValueError("invalid instruction removal entry")
        rel = entry.get("path", "")
        text = entry.get("text", "")
        if rel not in INSTRUCTION_FILES or not isinstance(text, str) or not text.strip():
            raise ValueError("invalid instruction removal target or text")
        path = _safe(root, rel)
        if not path.is_file():
            raise ValueError("instruction file missing: " + rel)
        body = _read_text(path)
        if body.count(text) != 1:
            raise ValueError("instruction removal text must match uniquely in " + rel)
        if not _is_old_pointer(text, data["sources"]):
            raise ValueError("instruction removal is not a recognized tracking pointer")
        snapshots[rel] = _hash_file(path)
        results.append({"path": rel, "text": text, "reason": str(entry.get("reason", ""))})
    return snapshots, results


def _is_old_pointer(text, sources):
    source_names = set(TRACKER_NAMES)
    source_names.update(Path(item["path"]).parts[0] for item in sources)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    for line in lines:
        low = line.lower()
        if low in {f"<!-- {name.strip('.')} -->" for name in source_names}:
            continue
        if re.fullmatch(r"#{1,3}\s+(taskmaster|memory bank|kiro|factory|bmad|openspec|planning)\s*", line, re.I):
            continue
        if POINTER_RISK.search(line) or not POINTER_CUE.search(line):
            return False
        if not any(name.lower() in low for name in source_names):
            return False
    return True


def _ignore_plan(root, data):
    rel = ".gitignore"
    path = _safe(root, rel)
    if not path.is_file():
        return {}, []
    lines = _read_text(path).splitlines(keepends=True)
    chosen = set(data["roots"])
    patterns = chosen | {"/" + x for x in chosen} | {x.rstrip("/") + "/" for x in chosen}
    remove = [line for line in lines if line.strip() in patterns]
    return {rel: _hash_file(path)}, remove


def verify(B, root, note):
    root = Path(root).resolve()
    data = status(B, root)
    if not data or data.get("state") not in ("PREPARED", "VERIFIED"):
        raise ValueError("adoption trace is not prepared")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("reviewed note is required")
    S.require_public(note, "adoption review note")
    actual = _source_snapshot(root, data["roots"])
    expected = {item["path"]: item["sha256"] for item in data["sources"]}
    if actual != expected:
        raise ValueError("foreign sources changed since preparation")
    targets = _validate_targets(B, root, data)
    instruction_snapshot, reviewed = _instruction_data(B, root, data)
    ignore_snapshot, remove = _ignore_plan(root, data)
    instruction_after = {}
    for rel in instruction_snapshot:
        text = _read_text(_safe(root, rel))
        for entry in reviewed:
            if entry["path"] == rel:
                text = text.replace(entry["text"], "", 1)
        instruction_after[rel] = _atomic_hash(text)
    ignore_after = {}
    if ignore_snapshot:
        rel = ".gitignore"
        lines = _read_text(_safe(root, rel)).splitlines(keepends=True)
        for line in remove:
            try:
                lines.remove(line)
            except ValueError:
                pass
        ignore_after[rel] = _atomic_hash("".join(lines))
    data["instruction_removals"] = reviewed
    data["source_snapshot"] = expected
    data["target_snapshot"] = targets
    data["instruction_snapshot"] = instruction_snapshot
    data["instruction_after_snapshot"] = instruction_after
    data["ignore_snapshot"] = ignore_snapshot
    data["ignore_after_snapshot"] = ignore_after
    data["reviewed_note"] = note.strip()
    data["state"] = "VERIFIED"
    _save(B, root, data)
    return data


def _archive_path(root, data, archive_dir):
    base = Path(archive_dir) if archive_dir else Path(root).parent / ".project-brain-archives"
    base = Core.safe_private_path(base)
    resolved = base.resolve()
    if resolved == Path(root) or Path(root) in resolved.parents:
        raise ValueError("archive must be outside project root")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved / (Path(root).name + "-" + data["id"] + ".zip")


def _zip_entry_hashes(path):
    with zipfile.ZipFile(path, "r") as zf:
        bad = zf.testzip()
        if bad:
            raise ValueError("archive integrity failure: " + bad)
        return {name: _hash_bytes(zf.read(name)) for name in zf.namelist()}


def _archive(B, root, data, archive_dir):
    target = _archive_path(root, data, archive_dir)
    expected = dict(data["source_snapshot"])
    backups = set(data.get("instruction_snapshot", {})) | set(data.get("ignore_snapshot", {}))
    expected_entries = {"sources/" + p: h for p, h in expected.items()}
    expected_entries.update({"backups/" + p: _hash_file(_safe(root, p)) for p in backups})
    if target.exists():
        if _zip_entry_hashes(target) != expected_entries:
            raise ValueError("existing adoption archive does not match verified sources")
        return {"path": str(target), "sha256": _hash_file(target), "entries": expected_entries}
    tmp = target.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel in sorted(expected):
                zf.write(_safe(root, rel), "sources/" + rel)
            for rel in sorted(backups):
                zf.write(_safe(root, rel), "backups/" + rel)
        with tmp.open("r+b") as fh:
            os.fsync(fh.fileno())
        if _zip_entry_hashes(tmp) != expected_entries:
            raise ValueError("archive contents do not match verified source snapshot")
        Core._replace_with_retry(str(tmp), str(target))
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return {"path": str(target), "sha256": _hash_file(target), "entries": expected_entries}


def _validate_cleanup_inputs(B, root, data):
    if _source_snapshot(root, data["roots"]) != data["source_snapshot"]:
        raise ValueError("foreign source set or contents changed")
    for rel, digest in data["target_snapshot"].items():
        path = _target_safe(root, rel)
        if not path.is_file() or _hash_file(path) != digest:
            raise ValueError("adoption destination changed: " + rel)
    for rel, digest in data["instruction_snapshot"].items():
        if _hash_file(_safe(root, rel)) != digest:
            raise ValueError("instruction file changed: " + rel)
    for rel, digest in data["ignore_snapshot"].items():
        if _hash_file(_safe(root, rel)) != digest:
            raise ValueError("ignore file changed: " + rel)


def _archive_valid(root, data):
    archive = data.get("archive", {})
    path = Path(archive.get("path", ""))
    root = Path(root).resolve()
    if not path.is_absolute() or root == path.resolve() or root in path.resolve().parents:
        return False
    for item in (path, *path.parents):
        if Core.is_link(item):
            return False
    if not path.is_file() or _hash_file(path) != archive.get("sha256"):
        return False
    return _zip_entry_hashes(path) == archive.get("entries")


def _remove_instruction_blocks(B, root, data):
    for rel, digest in data["instruction_snapshot"].items():
        path = _safe(root, rel)
        current_hash = _hash_file(path)
        if current_hash == data["instruction_after_snapshot"].get(rel):
            continue
        if current_hash != digest:
            raise ValueError("instruction file changed during cleanup: " + rel)
        before = _read_text(path)
        after = before
        for entry in data["instruction_removals"]:
            if entry["path"] == rel:
                after = after.replace(entry["text"], "", 1)
        if after != before:
            Core.write_atomic(path, after)


def _remove_ignore_lines(B, root, data):
    rel = ".gitignore"
    if rel not in data["ignore_snapshot"]:
        return
    path = _safe(root, rel)
    current_hash = _hash_file(path)
    if current_hash == data["ignore_after_snapshot"].get(rel):
        return
    if current_hash != data["ignore_snapshot"][rel]:
        raise ValueError("ignore file changed during cleanup")
    lines = _read_text(path).splitlines(keepends=True)
    _, removal = _ignore_plan(root, data)
    if not removal:
        return
    for line in removal:
        try:
            lines.remove(line)
        except ValueError:
            pass
    Core.write_atomic(path, "".join(lines))


def cleanup(B, root, archive_dir=None):
    root = Path(root).resolve()
    data = status(B, root)
    if not data:
        raise ValueError("no adoption trace")
    if data.get("state") == "CLEANED":
        return data
    if data.get("state") not in ("VERIFIED", "ARCHIVED", "CLEANING"):
        raise ValueError("adoption must be verified before cleanup")
    if data["state"] in ("ARCHIVED", "CLEANING"):
        if not _archive_valid(root, data):
            raise ValueError("verified recovery archive is missing or corrupt")
    if data["state"] in ("VERIFIED", "ARCHIVED"):
        _validate_cleanup_inputs(B, root, data)
    elif data["state"] == "CLEANING":
        for rel, digest in data["target_snapshot"].items():
            path = _target_safe(root, rel)
            if not path.is_file() or _hash_file(path) != digest:
                raise ValueError("adoption destination changed: " + rel)
        present = {}
        for rel in data["source_snapshot"]:
            path = _safe(root, rel)
            if path.exists():
                if not path.is_file():
                    raise ValueError("foreign source changed: " + rel)
                present[rel] = _hash_file(path)
        if any(digest != data["source_snapshot"][rel] for rel, digest in present.items()):
            raise ValueError("foreign source changed during cleanup")
        allowed = set(data["source_snapshot"])
        for rel in data["roots"]:
            path = _safe(root, rel)
            if path.is_file() and rel not in allowed:
                raise ValueError("new foreign file appeared during cleanup: " + rel)
            if path.is_dir():
                for base, _dirs, names in os.walk(str(path), topdown=True, followlinks=False):
                    base_p = Path(base)
                    _dirs[:] = [d for d in _dirs if not Core.is_link(base_p / d)]
                    for name in names:
                        candidate = base_p / name
                        relname = _rel(root, candidate)
                        _safe(root, relname)
                        if relname not in allowed:
                            raise ValueError("new foreign file appeared during cleanup: " + relname)
    if data["state"] == "VERIFIED":
        data["archive"] = _archive(B, root, data, archive_dir)
        data["state"] = "ARCHIVED"
        _save(B, root, data)
    data["state"] = "CLEANING"
    _save(B, root, data)
    for rel, digest in data["source_snapshot"].items():
        for target_rel, target_hash in data["target_snapshot"].items():
            target = _target_safe(root, target_rel)
            if not target.is_file() or _hash_file(target) != target_hash:
                raise ValueError("adoption destination changed: " + target_rel)
        path = _safe(root, rel)
        if not path.exists():
            continue
        if not path.is_file() or _hash_file(path) != digest:
            raise ValueError("foreign source changed before removal: " + rel)
        path.unlink()
    _remove_instruction_blocks(B, root, data)
    _remove_ignore_lines(B, root, data)
    dirs = set()
    for rel in data["roots"]:
        p = _safe(root, rel)
        if p.is_dir():
            for base, children, _names in os.walk(str(p), topdown=True, followlinks=False):
                basep = Path(base)
                dirs.add(basep)
                for child in children:
                    childp = basep / child
                    _safe(root, _rel(root, childp))
                    dirs.add(childp)
    for path in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        rel = _rel(root, path)
        _safe(root, rel)
        try:
            path.rmdir()
        except OSError:
            if path.exists():
                raise ValueError("unexpected content prevents tracking directory removal: " + rel)
    data["state"] = "CLEANED"
    _save(B, root, data)
    return data
