"""Verified, recoverable cleanup for foreign planning state. Stdlib only."""

import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import uuid
import zipfile

import runtime_verify as V

TRACE_SCHEMA = 1
STATES = ("PREPARED", "VERIFIED", "ARCHIVED", "CLEANING", "CLEANED")
SKIP_DIRS = {".git", ".hg", ".svn", ".project-brain", "node_modules", ".venv", "venv",
             "__pycache__", "dist", "build", "target", "bin", "obj"}
TRACKING_EXTENSIONS = {".md", ".json", ".yaml", ".yml", ".txt", ".toml"}
INSTRUCTION_FILES = {"AGENTS.md", "CLAUDE.md", "GEMINI.md"}
UNRESOLVED = re.compile(r"^\s*-\s*(?:(?P<op>[A-Za-z0-9_.:/-]+)\s*(?:\||:)\s*)?(?P<state>sent|response_unknown)\b", re.I | re.M)
POINTER_CUE = re.compile(r"\b(load|read|use|follow|see|check|start with|continue in)\b", re.I)
POINTER_RISK = re.compile(r"\b(security|credential|secret|token|permission|authorization|password|private key|must not|never|do not|don't)\b", re.I)
TRACKER_NAMES = (".taskmaster", "memory-bank", ".kiro", ".factory", "_bmad", "openspec", ".planning")


def trace_file(B, root):
    return V.public_path(root, ".project-brain/adoption.json")


def status(B, root):
    p = trace_file(B, root)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("adoption trace is unreadable or malformed") from exc
    if not isinstance(data, dict) or data.get("schema") != TRACE_SCHEMA:
        raise ValueError("unsupported adoption trace")
    if data.get("state") not in STATES or not isinstance(data.get("id"), str) or not isinstance(data.get("sources"), list):
        raise ValueError("invalid adoption trace state or shape")
    return data


def _save(B, root, data):
    B.write_atomic(trace_file(B, root), json.dumps(data, ensure_ascii=False, indent=2))


def _hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


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
    path = V.public_path(root, rel)
    if path.exists() and not (path.is_file() or path.is_dir()):
        raise ValueError("unsupported filesystem object: " + rel)
    return path


def _target_safe(root, rel):
    if isinstance(rel, str) and rel.startswith(".project-brain/"):
        parts = PureWindowsPath(rel).parts
        if len(parts) < 2 or any(part.lower() in {".cache", "migration-backup", "adoption.json"} for part in parts):
            raise ValueError("private Project Brain destination refused: " + rel)
        path = V.public_path(root, rel)
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
                if V.is_link(child):
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
    import runtime_agents as A
    found = []
    for _name, paths in A.detect_foreign(root):
        for path in paths:
            if path == "PROJECT_BRAIN.md":
                continue
            if path in ("TODO.md", "TASKS.md"):
                text = (Path(root) / path).read_text(encoding="utf-8", errors="replace")
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
    prior = status(B, root)
    if prior and prior.get("state") not in ("CLEANED",):
        raise ValueError("adoption already has pending work; resume its exact trace")
    selected = _roots(list(paths) if paths else _default_paths(root))
    if not selected:
        raise ValueError("no foreign planning sources selected")
    files = {}
    for rel in selected:
        _safe(root, rel)
        for item in _enumerate(root, rel):
            files[item["path"]] = item
    files = [files[key] for key in sorted(files)]
    data = {"schema": TRACE_SCHEMA, "id": str(uuid.uuid4()), "state": "PREPARED",
            "roots": selected, "sources": files, "reviewed_note": "",
            "instruction_removals": [], "source_snapshot": {}, "target_snapshot": {},
            "instruction_snapshot": {}, "instruction_after_snapshot": {},
            "ignore_snapshot": {}, "ignore_after_snapshot": {}, "archive": {}}
    _save(B, root, data)
    return data


def _source_snapshot(root, roots):
    found = {}
    for rel in roots:
        for item in _enumerate(root, rel):
            found[item["path"]] = item["sha256"]
    return found


def _validate_targets(B, root, data):
    removed = set(data["source_snapshot"] or {s["path"]: s["sha256"] for s in data["sources"]})
    targets = {}
    for source in data["sources"]:
        mapped = source.get("targets")
        dropped = str(source.get("drop_reason", "")).strip()
        if bool(mapped) == bool(dropped):
            raise ValueError("every source needs targets or a drop reason, exclusively: " + source["path"])
        if mapped:
            if not isinstance(mapped, list):
                raise ValueError("targets must be a list: " + source["path"])
            for item in mapped:
                rel = item.get("path") if isinstance(item, dict) else item
                path = _target_safe(root, rel)
                if not path.is_file():
                    raise ValueError("adoption target must be an existing file: " + str(rel))
                target_abs = path.resolve()
                for source_rel in removed:
                    source_abs = _safe(root, source_rel).resolve()
                    if target_abs == source_abs or source_abs in target_abs.parents:
                        raise ValueError("adoption target is inside a removed source: " + rel)
                targets[rel] = _hash_file(path)
        elif _has_unresolved(root, source["path"]):
            raise ValueError("unresolved external operation cannot be dropped: " + source["path"])
    # Each unresolved operation must survive in at least one mapped target.
    for source in data["sources"]:
        unresolved = _unresolved_lines(root, source["path"])
        if unresolved:
            target_paths = [t.get("path") if isinstance(t, dict) else t for t in (source.get("targets") or [])]
            target_text = "\n".join(_read_text(_target_safe(root, p)) for p in target_paths)
            for op, state in unresolved:
                if state.lower() not in target_text.lower() or (op and op.lower() not in target_text.lower()):
                    raise ValueError("mapped target does not preserve unresolved operation from " + source["path"])
    return targets


def _read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeError, OSError):
        return ""


def _unresolved_lines(root, rel):
    text = _read_text(_safe(root, rel))
    return [(m.group("op") or "", m.group("state")) for m in UNRESOLVED.finditer(text)]


def _has_unresolved(root, rel):
    return bool(_unresolved_lines(root, rel))


def _instruction_data(B, root, data):
    snapshots, results = {}, []
    for entry in data.get("instruction_removals", []):
        rel, text = entry.get("path"), entry.get("text")
        if rel not in INSTRUCTION_FILES or not isinstance(text, str) or not text:
            raise ValueError("instruction removal must name an approved instruction file and exact text")
        path = _target_safe(root, rel)
        if not path.is_file():
            raise ValueError("instruction file missing: " + rel)
        content = _read_text(path)
        if text not in content:
            raise ValueError("reviewed instruction block not found exactly in " + rel)
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
    actual = _source_snapshot(root, data["roots"])
    expected = {item["path"]: item["sha256"] for item in data["sources"]}
    if actual != expected:
        raise ValueError("foreign sources changed since preparation")
    targets = _validate_targets(B, root, data)
    instruction_snapshot, reviewed = _instruction_data(B, root, data)
    ignore_snapshot, _ = _ignore_plan(root, data)
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
        _, remove = _ignore_plan(root, data)
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
    base = base.absolute()
    for p in (base, *base.parents):
        if V.is_link(p):
            raise ValueError("linked archive path refused")
    base = base.resolve()
    if base == Path(root) or Path(root) in base.parents:
        raise ValueError("archive must be outside project root")
    base.mkdir(parents=True, exist_ok=True)
    return base / (Path(root).name + "-" + data["id"] + ".zip")


def _zip_entry_hashes(path):
    with zipfile.ZipFile(path, "r") as zf:
        bad = zf.testzip()
        if bad:
            raise ValueError("archive integrity failure: " + bad)
        return {name: _hash_bytes(zf.read(name)) for name in zf.namelist()}


def _archive(B, root, data, archive_dir):
    # Recovery after archive creation but before journal persistence may reuse only an exact match.
    candidate = _archive_path(root, data, archive_dir)
    expected = dict(data["source_snapshot"])
    backups = set(data.get("instruction_snapshot", {})) | set(data.get("ignore_snapshot", {}))
    expected_entries = {"sources/" + p: h for p, h in expected.items()}
    expected_entries.update({"backups/" + p: _hash_file(_safe(root, p)) for p in backups})
    if candidate.exists():
        if _zip_entry_hashes(candidate) != expected_entries:
            raise ValueError("existing adoption archive does not match verified sources")
        return {"path": str(candidate), "sha256": _hash_file(candidate), "entries": expected_entries}
    target = _archive_path(root, data, archive_dir)
    try:
        with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel in sorted(expected):
                p = _safe(root, rel)
                zf.write(p, "sources/" + rel)
            for rel in sorted(backups):
                zf.write(_safe(root, rel), "backups/" + rel)
        if _zip_entry_hashes(target) != expected_entries:
            raise ValueError("archive contents do not match verified source snapshot")
    except Exception:
        try:
            target.unlink()
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
        if V.is_link(item):
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
            B.write_atomic(path, after)


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
    for line in removal:
        try:
            lines.remove(line)
        except ValueError:
            pass
    B.write_atomic(path, "".join(lines))


def cleanup(B, root, archive_dir=None):
    root = Path(root).resolve()
    data = status(B, root)
    if not data:
        raise ValueError("no adoption trace")
    if data.get("state") == "CLEANED":
        return data
    if data.get("state") not in ("VERIFIED", "ARCHIVED", "CLEANING"):
        raise ValueError("adoption must be verified before cleanup")
    # A cleanup retry may encounter already removed files; only trust a valid archive and CLEANING journal.
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
                for base, dirs, names in os.walk(str(path), followlinks=False):
                    for name in names:
                        candidate = Path(base) / name
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
    # Explicit bottom-up rmdir only; never recursively remove a computed directory tree.
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

