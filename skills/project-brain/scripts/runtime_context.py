"""Read-only, source-bound worker context. Python 3.8+, standard library only."""
import hashlib
import json
from pathlib import Path
import re

import runtime_security as S
import runtime_verify as V


def files(B, root):
    for name in sorted(set(B.repo_files(root, B.git(root, "rev-parse", "--is-inside-work-tree") == "true"))):
        if name.startswith((B.BRAIN_DIR + "/", ".git/")) or V.PRIVATE.search(name):
            continue
        try:
            path = V.public_path(root, name)
            if path.is_file():
                yield name, path
        except ValueError:
            continue


def discover(B, root, query="", offset=0, limit=30, tests=False, start_file="", max_bytes=64 * 1024 * 1024):
    """Literal search, never a claimed semantic call graph; no project code runs."""
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("offset must be nonnegative and limit 1..100")
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("query must be at most 200 characters")
    rows, digest, total, scanned, next_file = [], hashlib.sha256(), 0, 0, None
    for name, path in files(B, root):
        if name < start_file:
            continue
        if path.stat().st_size > 1024 * 1024:
            continue
        if scanned + path.stat().st_size > max_bytes:
            next_file = name
            break
        raw = path.read_bytes()
        scanned += len(raw)
        digest.update(name.encode("utf-8") + b"\0" + hashlib.sha256(raw).digest())
        if tests and not re.search(r"(^|/)(tests?|__tests__)(/|$)|(^|/)(test_|.*[._](test|spec)\.)", name):
            continue
        if not query:
            if offset <= total < offset + limit:
                rows.append({"path": name})
            total += 1
            continue
        try:
            lines = raw.decode("utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(lines, 1):
            if query in line:
                if offset <= total < offset + limit:
                    rows.append({"path": name, "line": n, "text": S.sanitize(line[:300])})
                total += 1
    return {"source": digest.hexdigest(), "method": "literal", "results": rows,
            "next": offset + limit if total > offset + limit else None, "total": total,
            "scan_truncated": next_file is not None, "next_file": next_file, "scanned_bytes": scanned,
            "source_scope": "scanned files"}


def packet(B, root, task, kind="EXECUTE"):
    if kind not in ("EXECUTE", "REVIEW"):
        raise ValueError("kind must be EXECUTE or REVIEW")
    if task.get("secrets", "none") != "none":
        raise ValueError("Secret-bearing tasks cannot be exported to workers")
    import runtime_protocol as R
    R.guard(B, root, task)
    related = []
    for name, _ in files(B, root):
        if any(B.matches(name, a) for a in R.inputs(task)):
            related.append(name)
    constraints = B.read(B.bp(root) / "constraints.md") or ""
    current = B.bp(root) / "current.md"
    text = B.read(current) or ""
    _, ranges = B.current_slices(current, task.get("domains", [])) if current.exists() else ("", None)
    slices = text
    if ranges:
        lines = text.splitlines()
        slices = "\n".join(line for span in ranges.split(", ")
                           for line in lines[int(span.split("-")[0]) - 1:int(span.split("-")[1])])
    adrs = {}
    for number in re.findall(r"ADR-(\d+)", task.get("text", "")):
        name = B.BRAIN_DIR + "/decisions/ADR-" + number + ".md"
        adrs[name] = B.read(V.public_path(root, name)) or "MISSING: request clarification"
    value = {"schema": 1, "task": task["id"], "kind": kind, "contract": B.contract(task),
             "source": R.task_digest(B, root, task)[0], "base": B.git(root, "rev-parse", "HEAD"),
             "intent": R.intent(B, root, task),
             "objective": task.get("sections", {}).get("objective", []),
             "spec": {k: v for k, v in B.sections(task.get("text", "")).items()
                      if k in ("objective", "steps", "acceptance", "verify")},
             "areas": task["areas"], "inputs": task.get("inputs", []),
             "files": related, "constraints": constraints, "architecture": slices, "decisions": adrs,
             "rules": ["Read applicable repository instructions. Request named missing context; never guess.",
                       "Worker role inherits the director session; do not boot Brain or repeat its session interview.",
                       "No Brain state/procedure changes, nested delegation, commit, push or publishing.",
                       "Preserve user work; use only the assigned workspace and Areas for writes.",
                       "Use the existing human Git identity; never add AI/bot attribution.",
                       "REVIEW is read-only; return findings bound to this source." if kind == "REVIEW" else
                       "Perform the task and relevant tests; return actual results and blockers, never invented PASS."]}
    S.require_clean(json.dumps(value, ensure_ascii=False), "worker packet")
    return value


def prompt(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
