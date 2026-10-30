"""Versioned intent, verification inputs and bounded continuity. Python 3.8+."""
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import time

import runtime_verify as V

PROTOCOL = 1
DEFAULT_INPUTS = (
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb",
    "pyproject.toml", "requirements*.txt", "pytest.ini", "setup.cfg", "tox.ini", ".python-version",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "pubspec.yaml", "pubspec.lock",
    "AGENTS.md", "CLAUDE.md", "GEMINI.md", "tsconfig*.json", "vite.config.*", "vitest.config.*", "jest.config.*", "gradle.properties",
)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                      separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def enabled(B, root):
    value = str(B.parse_config(root).get("protocol_version", "0"))
    if value not in ("0", str(PROTOCOL)):
        raise ValueError("Unsupported protocol_version; upgrade the skill")
    return value == str(PROTOCOL)


def record_path(B, root, tid, name):
    tid = B.norm_id("PB", tid)
    return V.public_path(root, B.BRAIN_DIR + "/evidence/" + tid + "/" + name + ".json")


def read_json(path):
    if not path.exists():
        return {}
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Protocol record exceeds 1 MiB")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Protocol record must be an object")
    return data


def intent(B, root, task=None):
    """Whitespace and checkbox changes are editorial; changed words require impact review."""
    target = B.read(B.bp(root) / "target.md") or ""
    sections = B.sections(target)
    names = ("goal", "success conditions", "success criteria", "non-goals", "target state")
    selected = {n: " ".join(sections.get(n, [])) for n in names if n in sections}
    if not selected:
        selected = {"target": target}
    selected["constraints"] = B.read(B.bp(root) / "constraints.md") or ""
    directory = V.public_path(root, B.BRAIN_DIR + "/target")
    if directory.is_dir():
        domains = set(task.get("domains", [])) if task else set()
        for path in sorted(directory.glob("*.md")):
            V.public_path(root, path.relative_to(root).as_posix())
            if not domains or path.stem in domains:
                selected["domain:" + path.stem] = B.read(path) or ""
    return fingerprint({k: re.sub(r"\s+", " ", re.sub(r"\[[ xX]\]", "[]", v)).strip()
                        for k, v in selected.items()})


def reconcile(B, root, task, note, independent=False, keep_evidence=False):
    import runtime_security as S
    if not note.strip() or len(note) > 2000:
        raise ValueError("Reconciliation requires the actual impact decision --note")
    S.require_public(note, "reconciliation note")
    if independent and task.get("purpose", "implementation") != "discovery":
        raise ValueError("Goal-independent work requires Purpose: discovery in the task contract")
    if not independent and B.target_status(root) != "CONFIRMED":
        raise ValueError("Confirm Target before reconciling implementation work")
    if not independent:
        goal = " ".join(B.sections(B.read(B.bp(root) / "target.md") or "").get("goal", [])).strip()
        if not goal or re.search(r"<[^>]+>", goal):
            raise ValueError("Implementation requires the actual user Goal, not an empty/scaffold target")
    # Normalize the deterministic risk floor before binding the executable spec;
    # start must not succeed by immediately making its own reconciliation stale.
    risk = V.effective_risk(B, task)
    if task.get("risk") != risk:
        B.set_header(task["file"], "Risk", risk)
        task.update(B.find_task(root, task["id"]))
    path = record_path(B, root, task["id"], "intent")
    old = read_json(path)
    con = B.contract(task)
    # A source/spec change still invalidates evidence. keep_evidence only preserves
    # the intent epoch after an explicit unchanged-outcome decision.
    epoch = old.get("epoch") if keep_evidence and old.get("contract") == con else fingerprint([intent(B, root, task), con])
    if keep_evidence and (not old or old.get("contract") != con):
        raise ValueError("--keep-evidence requires an existing unchanged task contract")
    data = {"protocol": PROTOCOL, "intent": intent(B, root, task), "epoch": epoch,
            "contract": con, "independent": bool(independent), "note": note.strip()}
    B.write_atomic(path, json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))
    return data


def guard(B, root, task):
    if not enabled(B, root):
        return
    from runtime_security import policy_guard
    policy_guard(B, root, task)
    data = read_json(record_path(B, root, task["id"], "intent"))
    if data and (data.get("protocol") != PROTOCOL or type(data.get("independent")) is not bool
                 or not all(isinstance(data.get(k), str) and re.fullmatch(r"[0-9a-f]{16}", data[k]) for k in ("intent", "epoch", "contract"))
                 or not isinstance(data.get("note"), str) or not data["note"].strip()):
        raise ValueError("Malformed intent record; reconcile the task explicitly")
    if not data or data.get("contract") != B.contract(task) or data.get("intent") != intent(B, root, task):
        raise ValueError("INTENT_PENDING: reconcile this task against current Target/constraints before execution or closure")
    independent = data.get("independent") is True and task.get("purpose") == "discovery"
    if not independent and B.target_status(root) != "CONFIRMED":
        raise ValueError("TARGET_PENDING: implementation requires CONFIRMED Target")
    B.require_session(root)


def inputs(task):
    return list(dict.fromkeys(task.get("areas", []) + task.get("inputs", []) + list(DEFAULT_INPUTS)))


def task_digest(B, root, task):
    if not enabled(B, root):
        return V.digest(B, root, task["areas"])
    guard(B, root, task)
    # Validate literal parts before globbing. Private/escaping declarations must
    # not silently vanish from a fingerprint merely because repo_files omits them.
    explicit = []
    for pattern in task.get("areas", []) + task.get("inputs", []):
        probe = re.sub(r"\[[^]]*\]|[*?]", "glob", pattern)
        V.public_path(root, probe)
        if V.PRIVATE.search(pattern):
            raise ValueError("Private verification input refused; use the approved external binding")
        architecture_input = pattern == B.BRAIN_DIR + "/current.md" or pattern.startswith(B.BRAIN_DIR + "/current/")
        if pattern.startswith(B.BRAIN_DIR + "/") and not pattern.startswith(B.BRAIN_DIR + "/decisions/") and not architecture_input:
            raise ValueError("Brain state is bound separately; do not include mutable evidence/cache as verification input")
    state_inputs = [pattern for pattern in task.get("areas", []) if pattern == B.BRAIN_DIR + "/current.md" or pattern.startswith(B.BRAIN_DIR + "/current/")]
    for pattern in list(dict.fromkeys(task.get("inputs", []) + state_inputs)):
        for candidate in Path(root).glob(pattern):
            V.public_path(root, candidate.relative_to(root).as_posix())
            paths = candidate.rglob("*") if candidate.is_dir() else [candidate]
            for path in paths:
                public = V.public_path(root, path.relative_to(root).as_posix())
                if public.is_file():
                    explicit.append((path.relative_to(root).as_posix(), public.read_bytes()))
    files_digest, count = V.digest(B, root, inputs(task))
    # Commands are identified by executable identity without repeatedly launching
    # version probes. Explicit runtime/container/config inputs cover remote tools.
    tools = []
    for cmd in task.get("verify_cmds", []):
        argv = V.command_argv(cmd)
        executable = shutil.which(argv[0]) or str(Path(root) / argv[0])
        file = Path(executable)
        stat = file.stat() if file.is_file() else None
        tools.append([str(file.resolve()), stat.st_size if stat else None, stat.st_mtime_ns if stat else None])
    env = {"python": sys.version, "platform": platform.system(), "machine": platform.machine(),
           "tools": tools, "configured": B.parse_config(root).get("verification", {})}
    binding = read_json(record_path(B, root, task["id"], "intent"))
    adrs = {}
    for number in re.findall(r"ADR-(\d+)", task.get("text", "")):
        path = V.public_path(root, B.BRAIN_DIR + "/decisions/ADR-" + number + ".md")
        adrs[number] = B.read(path)
    if task.get("secrets", "none") != "none":
        import runtime_security as S
        env["host_binding"] = S.binding_fingerprint(B, root, task)
    return fingerprint([PROTOCOL, files_digest, B.areas_digest(explicit), binding["epoch"], env, adrs]), count


def progress_data(path):
    data = read_json(path)
    usage = data.get("usage", {})
    if not isinstance(usage, dict):
        raise ValueError("Malformed progress usage")
    for key in ("repeats",):
        value = data.get(key, 0)
        if type(value) is not int or not 0 <= value <= 1000000:
            raise ValueError("Malformed progress counter")
    for key, value in usage.items():
        if key not in ("checks", "seconds") or type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("Malformed progress usage counter")
        if key == "checks" and type(value) is not int:
            raise ValueError("Check count must be an integer")
    for key in ("next", "failing", "dirty", "strategy", "attempt", "contract"):
        if key in data and not isinstance(data[key], str):
            raise ValueError("Malformed progress text")
    return data


def progress(B, root, task, next_step, failing="", dirty="", strategy=""):
    import runtime_security as S
    for value in (next_step, failing, dirty, strategy):
        S.require_public(value, "progress note")
        if any(ord(c) < 32 for c in value) or len(value) > 500:
            raise ValueError("Progress fields must be single lines <=500 characters")
    if not next_step.strip():
        raise ValueError("--next is required")
    if not dirty:
        has_git = B.git(root, "rev-parse", "--is-inside-work-tree") == "true"
        candidates = B.dirty_paths(root) if has_git else B.repo_files(root, False)
        owned = sorted(p for p in candidates if any(B.matches(p, a) for a in task.get("areas", [])))
        dirty = ", ".join(owned)
        if len(dirty) > 450:
            dirty = ", ".join(owned[:5])[:400] + "; inspect git status for the complete dirty set"
        S.require_public(dirty, "observed dirty paths")
    path = record_path(B, root, task["id"], "progress")
    data = progress_data(path)
    key = fingerprint([B.contract(task), task_digest(B, root, task)[0], failing, strategy])
    repeats = data.get("repeats", 0) + 1 if failing and data.get("attempt") == key else (1 if failing else 0)
    data = {"protocol": PROTOCOL, "next": next_step, "failing": failing, "dirty": dirty,
            "strategy": strategy, "attempt": key, "repeats": repeats, "contract": B.contract(task), "usage": data.get("usage", {})}
    B.write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))
    text = B.read(task["file"]) or ""
    resume = "## Resume\nNext: " + next_step + "\nFailing: " + (failing or "none") + "\nDirty: " + (dirty or "none") + "\n"
    if re.search(r"^## Resume\s*$", text, re.M):
        text = re.sub(r"^## Resume\s*\n.*?(?=^## |\Z)", lambda _: resume + "\n", text, flags=re.M | re.S)
    else:
        text = text.rstrip() + "\n\n" + resume
    B.write_atomic(task["file"], text)
    return data


def attempt_guard(B, root, task):
    if not enabled(B, root):
        return
    data = progress_data(record_path(B, root, task["id"], "progress"))
    cfg = B.parse_config(root).get("execution", {})
    usage = data.get("usage", {})
    for setting, key in (("max_check_runs", "checks"), ("max_check_seconds", "seconds")):
        raw = str(cfg.get(setting, "0"))
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw):
            raise ValueError("execution." + setting + " must be a nonnegative finite number")
        limit = float(raw)
        if limit and usage.get(key, 0) >= limit:
            raise ValueError("EXECUTION_BUDGET: explicit " + setting + " reached; checkpoint and continue independently authorized work")
    cap_raw = str(cfg.get("repeat_limit", 2))
    if not cap_raw.isdigit():
        raise ValueError("execution.repeat_limit must be 1..20")
    cap = int(cap_raw)
    if not 1 <= cap <= 20:
        raise ValueError("execution.repeat_limit must be 1..20")
    if data.get("failing") and data.get("repeats", 0) >= cap:
        current = fingerprint([B.contract(task), task_digest(B, root, task)[0], data["failing"], data.get("strategy", "")])
        if current == data.get("attempt"):
            raise ValueError("NO_PROGRESS: same failure/source/strategy reached repeat_limit; change approach or record a blocker")


def account_check(B, root, task, seconds):
    path = record_path(B, root, task["id"], "progress")
    data = progress_data(path)
    usage = data.get("usage", {})
    usage["checks"] = usage.get("checks", 0) + 1
    usage["seconds"] = round(usage.get("seconds", 0) + seconds, 3)
    data["usage"] = usage
    B.write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))


def remaining_seconds(B, root, task, spent=0):
    """Only an explicitly configured check-work budget limits command time."""
    if not enabled(B, root):
        return None
    value = float(B.parse_config(root).get("execution", {}).get("max_check_seconds", 0))
    if not value:
        return None
    used = progress_data(record_path(B, root, task["id"], "progress")).get("usage", {}).get("seconds", 0)
    return max(0.0, value - used - spent)


def handoff(B, root, task):
    """Public, bounded, reproducible summary. No raw logs or host-private paths."""
    import runtime_security as S
    data = {"protocol": PROTOCOL, "task": task["id"], "status": task["status"],
            "contract": B.contract(task), "areas": task["areas"], "inputs": task.get("inputs", []),
            "resume": task.get("resume_lines", []), "external": task.get("external", []),
            "open_criteria": [i["id"] for i in task["items"] if not i["done"]],
            "readback_required": any(e.get("state") in ("sent", "response_unknown") for e in task.get("external", [])),
            "private_logs": "not exported; new environments must recheck when receipts are unavailable"}
    import runtime_session as RS
    pending = [row for row in RS.ledger(B, root)["requests"] if row["status"] == "open"]
    if pending:
        data["intake"] = {"path": B.BRAIN_DIR + "/requests.json", "pending": [row["id"] for row in pending]}
    try:
        value, count = task_digest(B, root, task)
        data.update(digest=value, files=count, checks_reusable_here=V.current_checks(B, root, task, value, B.contract(task)))
    except ValueError as exc:
        data["blocker"] = str(exc)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    S.require_public(text, "handoff")
    if len(text.encode("utf-8")) > 16384:
        raise ValueError("Handoff exceeds 16 KiB; compact task Resume/External first")
    path = record_path(B, root, task["id"], "handoff")
    B.write_atomic(path, text)
    return data


def review_guard(B, root, task, review, solo, registry=None):
    import runtime_agents as A
    proof = read_json(record_path(B, root, task["id"], "review-provenance"))
    if (not proof or any(proof.get(k) != review.get(k) for k in ("reviewer", "digest", "contract"))):
        raise ValueError("Review provenance missing/stale; run the actual review again")
    if proof.get("assurance") == "self-audit":
        if not solo or review["reviewer"] != task.get("owner"):
            raise ValueError("SOLO audit is not an independent reviewer receipt")
        return
    path = A.registry_path(registry)
    models = A.load(path).get("models", {}) if path.exists() else {}
    spec = models.get(review["reviewer"])
    if not isinstance(spec, dict):
        raise ValueError("Reviewer registry missing/changed; independence cannot be revalidated")
    identity = fingerprint({k: spec.get(k) for k in ("cli", "model_id", "pool_route", "roles", "tiers")})
    if identity != proof.get("model_identity"):
        raise ValueError("Reviewer model identity changed since review")
    A.gate(B, task, review["reviewer"], "review", registry, root=root)


def provenance(B, root, task, reviewer, self_review, registry=None):
    """Preserve the real assurance level; local records are never authenticated identity."""
    import runtime_agents as A
    spec = A.load(registry).get("models", {}).get(reviewer, {}) if A.registry_path(registry).exists() else {}
    if self_review:
        kind = "self-audit"
    elif spec:
        kind = "registered-model; host execution not authenticated"
    else:
        kind = "declared-only; independence not authenticated"
    data = {"reviewer": reviewer, "assurance": kind, "contract": B.contract(task),
            "digest": task_digest(B, root, task)[0],
            "model_identity": fingerprint({k: spec.get(k) for k in ("cli", "model_id", "pool_route", "roles", "tiers")})}
    B.write_atomic(record_path(B, root, task["id"], "review-provenance"), json.dumps(data, indent=2))
    return data
