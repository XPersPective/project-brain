"""Versioned intent, verification inputs, check-log freshness and bounded continuity.

Python 3.8+, stdlib only. Strictly acyclic: imports runtime_core, runtime_security,
runtime_scoring, runtime_actors, and runtime_executor_policy.
"""
import json
import math
from pathlib import Path
import platform
import re
import shutil
import sys

import runtime_actors as A
import runtime_core as Core
import runtime_executor_policy as E
import runtime_scoring as SC
import runtime_security as S

PROTOCOL = 1
DEFAULT_INPUTS = (
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb",
    "pyproject.toml", "requirements*.txt", "pytest.ini", "setup.cfg", "tox.ini", ".python-version",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "pubspec.yaml", "pubspec.lock",
    "AGENTS.md", "CLAUDE.md", "GEMINI.md", "tsconfig*.json", "vite.config.*", "vitest.config.*", "jest.config.*", "gradle.properties",
)
CHECK_RE = re.compile(
    r"^- \[machine\] check `(?P<cmd>[^`]+)` \| (?P<result>PASS|FAIL) \| exit=(?P<exit>-?\d+) \| "
    r"[0-9.]+s \| by=(?P<by>[^|]*?) "
    r"\| digest=(?P<digest>[0-9a-f]+) \| contract=(?P<contract>[0-9a-f]+) "
    r"\| log=(?P<log>\S+)@(?P<hash>[0-9a-f]+)$"
)
EVIDENCE_RE = re.compile(
    r"^- \[(?P<kind>[a-z_]+)\] (?!check `)(?P<note>[^|]*?) \| criterion=(?P<criteria>[0-9a-f,]+)"
    r"(?: \| files=(?P<files>[^|]+))? \| by=(?P<by>[^|]*?) \| digest=(?P<digest>[0-9a-f]+) "
    r"\| contract=(?P<contract>[0-9a-f]+)$"
)
REVIEW_RE = re.compile(
    r"^- review by (.+?) \| (PASS|BLOCKED) \| digest=([0-9a-f]+) \| contract=([0-9a-f]+)$"
)
FINDING_RE = re.compile(
    r"^- finding (BLOCKER|MAJOR|QUALITY|MINOR): (.+?)(?: \| accepted: (.+?) \| owner: (.+))?$"
)
LOG_FOOTER = "[project-brain check]"


def fingerprint(value):
    return Core.fingerprint(value)


def enabled(B, root):
    value = str(B.parse_config(root).get("protocol_version", "0"))
    if value not in ("0", str(PROTOCOL)):
        raise ValueError("Unsupported protocol_version; upgrade the skill")
    return value == str(PROTOCOL)


def record_path(B, root, tid, name):
    tid = B.norm_id("PB", tid)
    return Core.public_path(root, B.BRAIN_DIR + "/evidence/" + tid + "/" + name + ".json")


def read_json(path):
    return Core.read_json(path, max_bytes=1024 * 1024, strict_constants=True)


def ledger_path(B, root):
    return Core.public_path(root, B.BRAIN_DIR + "/requests.json")


def ledger(B, root):
    file = ledger_path(B, root)
    if not file.exists():
        return {"schema": 1, "requests": []}
    data = Core.read_json(file, max_bytes=1024 * 1024, strict_constants=True)
    if (
        not isinstance(data, dict)
        or data.get("schema") != 1
        or not isinstance(data.get("requests"), list)
        or len(data["requests"]) > 100
    ):
        raise ValueError("Malformed request ledger; preserve and inspect it")
    for row in data["requests"]:
        if (
            not isinstance(row, dict)
            or not re.fullmatch(r"RQ-\d{3,}", str(row.get("id", "")))
            or row.get("status") not in ("open", "linked", "answered")
            or row.get("relation") not in ("related", "question", "new-work", "cancel")
            or not isinstance(row.get("items"), list)
            or not 1 <= len(row["items"]) <= 32
            or any(not isinstance(item, str) or not 1 <= len(item) <= 500 for item in row["items"])
        ):
            raise ValueError("Malformed request ledger entry")
    return data


def digest(B, root, areas):
    """Content digest of every tracked/untracked public file matched by Areas (CRLF hashed as LF)."""
    if not areas:
        raise ValueError("Task has no Areas; evidence cannot be bound to source")
    root = Path(root)
    has_git = B.git(root, "rev-parse", "--is-inside-work-tree") == "true"
    files = sorted(
        f
        for f in B.repo_files(root, has_git)
        if any(B.matches(f, a) for a in areas)
        and not Core.PRIVATE.search(f)
        and not Core.is_generated_noise(f)
        and (root / f).is_file()
    )
    if not files:
        raise ValueError("Areas match no files: " + ", ".join(areas))
    return B.areas_digest([(f, Core.public_path(root, f).read_bytes()) for f in files]), len(files)


def _short_hash(path):
    return Core.sha256_file(path)[:16]


def check_log_valid(B, root, match):
    try:
        log = Core.public_path(root, B.BRAIN_DIR + "/" + match.group("log"))
        footer = (
            f"{LOG_FOOTER} {match.group('result')} exit={match.group('exit')} "
            f"digest={match.group('digest')} contract={match.group('contract')}"
        )
        return (
            log.is_file()
            and _short_hash(log) == match.group("hash")
            and log.read_text(encoding="utf-8", errors="replace").rstrip().endswith(footer)
        )
    except (ValueError, OSError):
        return False


def current_checks(B, root, task, value, contract):
    latest = {}
    for line in task.get("evidence_lines", []):
        match = CHECK_RE.match(line)
        if match:
            latest[match.group("cmd")] = match
    return bool(task.get("verify_cmds")) and all(
        cmd in latest
        and latest[cmd].group("result") == "PASS"
        and latest[cmd].group("exit") == "0"
        and latest[cmd].group("digest") == value
        and latest[cmd].group("contract") == contract
        and check_log_valid(B, root, latest[cmd])
        for cmd in task["verify_cmds"]
    )


def resolve_adr_files(B, root, number):
    """Find ADR files matching ADR-<number> (padded or unpadded, with optional slug)."""
    dec_dir = Path(root) / B.BRAIN_DIR / "decisions"
    if not dec_dir.is_dir() or Core.is_link(dec_dir):
        return []
    candidates = []
    padded = f"ADR-{int(number):03d}"
    raw_prefix = f"ADR-{number}"
    seen = set()
    for prefix in (padded, raw_prefix):
        for p in sorted(dec_dir.glob(prefix + "*.md")):
            rel = p.relative_to(Path(root)).as_posix()
            if rel in seen:
                continue
            if re.fullmatch(re.escape(prefix) + r"(?:-.*)?\.md", p.name):
                seen.add(rel)
                candidates.append(Core.public_path(root, rel))
    return candidates


def intent(B, root, task=None):
    """Whitespace and checkbox changes are editorial; changed words require impact review."""
    target = B.read(B.bp(root) / "target.md") or ""
    sections = B.sections(target)
    names = ("goal", "success conditions", "success criteria", "non-goals", "target state")
    selected = {n: " ".join(sections.get(n, [])) for n in names if n in sections}
    if not selected:
        selected = {"target": target}
    selected["constraints"] = B.read(B.bp(root) / "constraints.md") or ""
    root_abs = Path(root).resolve()
    directory = Core.public_path(root_abs, B.BRAIN_DIR + "/target")
    if directory.is_dir():
        domains = {B.norm_domain(d) for d in task.get("domains", [])} if task else set()
        for path in sorted(directory.glob("*.md")):
            Core.public_path(root_abs, path.relative_to(root_abs).as_posix())
            if not domains or B.norm_domain(path.stem) in domains:
                selected["domain:" + path.stem] = B.read(path) or ""
    return fingerprint(
        {k: re.sub(r"\s+", " ", re.sub(r"\[[ xX]\]", "[]", v)).strip() for k, v in selected.items()}
    )


def effective_risk(B, task):
    """Risk covers current scope and never drops below any recorded `start`."""
    order = {r: i for i, r in enumerate(B.RISK_VALUES)}
    risks = [SC.score_task(B, None, task)["effective_risk"]] + [r["risk"] for r in B.start_records(task)]
    valid = [r for r in risks if r in order]
    return max(valid, key=lambda r: order[r]) if valid else (task.get("risk") or "MEDIUM")


def reconcile(B, root, task, note, independent=False, keep_evidence=False):
    if not note.strip() or len(note) > 2000:
        raise ValueError("Reconciliation requires the actual impact decision --note")
    S.require_public(note, "reconciliation note")
    if independent and task.get("purpose", "implementation") != "discovery":
        raise ValueError("Goal-independent work requires Purpose: discovery in the task contract")
    if not independent and B.target_status(root) != "CONFIRMED":
        raise ValueError("Confirm Target before reconciling implementation work")
    if not independent:
        goal = " ".join(B.sections(B.read(B.bp(root) / "target.md") or "").get("goal", [])).strip()
        if (
            not goal
            or any(p in goal for p in B.PLACEHOLDERS)
            or re.search(r"<(?:todo|tbd|placeholder|fill\b|describe\b|your\b)[^>]*>", goal, re.I)
        ):
            raise ValueError("Implementation requires the actual user Goal, not an empty/scaffold target")
    risk = effective_risk(B, task)
    path = record_path(B, root, task["id"], "intent")
    old = read_json(path)
    projected = dict(task, risk=risk)
    con = B.contract(projected)
    if keep_evidence and (not old or old.get("contract") != con):
        raise ValueError("--keep-evidence requires an existing unchanged task contract")
    if task.get("risk") != risk:
        B.set_header(task["file"], "Risk", risk)
        task.update(B.find_task(root, task["id"]))
        con = B.contract(task)
    epoch = old.get("epoch") if keep_evidence and old.get("contract") == con else fingerprint([intent(B, root, task), con])
    data = {
        "protocol": PROTOCOL,
        "intent": intent(B, root, task),
        "epoch": epoch,
        "contract": con,
        "independent": bool(independent),
        "note": note.strip(),
    }
    Core.write_atomic(path, json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))
    return data


def guard(B, root, task, allow_stopping=False, check_session=True):
    if check_session:
        E.require_confirmed(B, root)
    if not enabled(B, root):
        return
    S.policy_guard(B, root, task)
    data = read_json(record_path(B, root, task["id"], "intent"))
    if data and (
        data.get("protocol") != PROTOCOL
        or type(data.get("independent")) is not bool
        or not all(
            isinstance(data.get(k), str) and re.fullmatch(r"[0-9a-f]{16}", data[k])
            for k in ("intent", "epoch", "contract")
        )
        or not isinstance(data.get("note"), str)
        or not data["note"].strip()
    ):
        raise ValueError("Malformed intent record; reconcile the task explicitly")
    if not data or data.get("contract") != B.contract(task) or data.get("intent") != intent(B, root, task):
        raise ValueError("INTENT_PENDING: reconcile this task against current Target/constraints before execution or closure")
    independent = data.get("independent") is True and task.get("purpose") == "discovery"
    if not independent and B.target_status(root) != "CONFIRMED":
        raise ValueError("TARGET_PENDING: implementation requires CONFIRMED Target")
    if check_session:
        B.require_session(root, allow_stopping=allow_stopping)
    return data


def inputs(task):
    return list(dict.fromkeys(task.get("areas", []) + task.get("inputs", []) + list(DEFAULT_INPUTS)))


def task_digest(B, root, task, allow_stopping=False, check_session=True):
    if not enabled(B, root):
        return digest(B, root, task["areas"])
    binding = guard(B, root, task, allow_stopping=allow_stopping, check_session=check_session)
    if not task.get("areas"):
        raise ValueError("Task has no Areas; evidence cannot be bound to source")
    explicit = []
    for pattern in task.get("areas", []) + task.get("inputs", []):
        probe = re.sub(r"\[[^]]*\]|[*?]", "glob", pattern)
        Core.public_path(root, probe)
        if Core.PRIVATE.search(pattern):
            raise ValueError("Private verification input refused; use the approved external binding")
        pat_low = pattern.replace("\\", "/").lower()
        architecture_input = pat_low == B.BRAIN_DIR + "/current.md" or pat_low.startswith(B.BRAIN_DIR + "/current/")
        if pat_low.startswith(B.BRAIN_DIR + "/") and not pat_low.startswith(B.BRAIN_DIR + "/decisions/") and not architecture_input:
            raise ValueError("Brain state is bound separately; do not include mutable evidence/cache as verification input")
    state_inputs = [
        pattern
        for pattern in task.get("areas", [])
        if pattern.replace("\\", "/").lower() == B.BRAIN_DIR + "/current.md"
        or pattern.replace("\\", "/").lower().startswith(B.BRAIN_DIR + "/current/")
        or pattern.replace("\\", "/").lower().startswith(B.BRAIN_DIR + "/decisions/")
    ]
    state_input_set = set(state_inputs)
    area_state_matched = False
    root_abs = Path(root).resolve()
    for pattern in list(dict.fromkeys(task.get("inputs", []) + state_inputs)):
        from_area_state = pattern in state_input_set
        for candidate in root_abs.glob(pattern):
            rel = candidate.relative_to(root_abs).as_posix()
            if Core.PRIVATE.search(rel) or Core.is_generated_noise(rel):
                continue
            public_cand = Core.public_path(root_abs, rel)
            if public_cand.is_dir():
                for path in Core.iter_files(public_cand):
                    sub_rel = path.relative_to(root_abs).as_posix()
                    if Core.PRIVATE.search(sub_rel) or Core.is_generated_noise(sub_rel):
                        continue
                    pub = Core.public_path(root_abs, sub_rel)
                    if pub.is_file():
                        explicit.append((sub_rel, pub.read_bytes()))
                        if from_area_state:
                            area_state_matched = True
            elif public_cand.is_file():
                explicit.append((rel, public_cand.read_bytes()))
                if from_area_state:
                    area_state_matched = True
    non_brain_areas = [p for p in task.get("areas", []) if not p.startswith(B.BRAIN_DIR + "/")]
    area_repo_matched = False
    if non_brain_areas:
        try:
            digest(B, root, non_brain_areas)
            area_repo_matched = True
        except ValueError:
            area_repo_matched = False
    if not area_repo_matched and not area_state_matched:
        raise ValueError("Areas match no files: " + ", ".join(task["areas"]))
    try:
        files_digest, count = digest(B, root, inputs(task))
    except ValueError:
        if not explicit:
            raise
        files_digest, count = B.areas_digest([]), len(explicit)
    tools = []
    for cmd in task.get("verify_cmds", []):
        argv = Core.command_argv(cmd)
        executable = shutil.which(argv[0]) or str(Path(root) / argv[0])
        file = Path(executable)
        st = file.stat() if file.is_file() else None
        tools.append([str(file.resolve()), st.st_size if st else None, st.st_mtime_ns if st else None])
    env = {
        "python": sys.version,
        "platform": platform.system(),
        "machine": platform.machine(),
        "tools": tools,
        "configured": B.parse_config(root).get("verification", {}),
    }
    spec_secs = B.sections(task.get("text", ""))
    spec_body = "\n".join(
        line
        for sec_name, sec_lines in spec_secs.items()
        if sec_name not in ("evidence", "review", "resume")
        for line in sec_lines
    )
    adrs = {}
    for number in re.findall(r"ADR-(\d+)", spec_body):
        matched = resolve_adr_files(B, root, number)
        adrs[number] = "\n".join(B.read(p) or "" for p in matched) if matched else None
    if task.get("secrets", "none") != "none":
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


def progress(B, root, task, next_step, failing="", dirty="", strategy="", allow_stopping=False):
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
    key = fingerprint([B.contract(task), task_digest(B, root, task, allow_stopping=allow_stopping)[0], failing, strategy])
    repeats = data.get("repeats", 0) + 1 if failing and data.get("attempt") == key else (1 if failing else 0)
    data = {
        "protocol": PROTOCOL,
        "next": next_step,
        "failing": failing,
        "dirty": dirty,
        "strategy": strategy,
        "attempt": key,
        "repeats": repeats,
        "contract": B.contract(task),
        "usage": data.get("usage", {}),
    }
    Core.write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))
    text = B.read(task["file"]) or ""
    resume_lines = [
        "Next: " + next_step,
        "Failing: " + (failing or "none"),
        "Dirty: " + (dirty or "none"),
    ]
    text = Core.replace_markdown_section(text, "Resume", resume_lines)
    Core.write_atomic(task["file"], text)
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
    Core.write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))


def remaining_seconds(B, root, task, spent=0):
    """Only an explicitly configured check-work budget limits command time."""
    if not enabled(B, root):
        return None
    raw = str(B.parse_config(root).get("execution", {}).get("max_check_seconds", "0"))
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw):
        raise ValueError("execution.max_check_seconds must be a nonnegative finite number")
    value = float(raw)
    if not value or not math.isfinite(value):
        return None
    used = progress_data(record_path(B, root, task["id"], "progress")).get("usage", {}).get("seconds", 0)
    return max(0.0, value - used - spent)


def handoff(B, root, task, allow_stopping=False):
    """Public, bounded, reproducible summary. No raw logs or host-private paths."""
    data = {
        "protocol": PROTOCOL,
        "task": task["id"],
        "status": task["status"],
        "contract": B.contract(task),
        "areas": task["areas"],
        "inputs": task.get("inputs", []),
        "resume": task.get("resume_lines", []),
        "external": task.get("external", []),
        "open_criteria": [i["id"] for i in task["items"] if not i["done"]],
        "readback_required": any(e.get("state") in ("sent", "response_unknown") for e in task.get("external", [])),
        "private_logs": "not exported; new environments must recheck when receipts are unavailable",
    }
    pending = [row for row in ledger(B, root)["requests"] if row["status"] == "open"]
    if pending:
        data["intake"] = {"path": B.BRAIN_DIR + "/requests.json", "pending": [row["id"] for row in pending]}
    try:
        value, count = task_digest(B, root, task, allow_stopping=allow_stopping)
        data.update(digest=value, files=count, checks_reusable_here=current_checks(B, root, task, value, B.contract(task)))
    except ValueError as exc:
        data["blocker"] = str(exc)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    S.require_public(text, "handoff")
    if len(text.encode("utf-8")) > 16384:
        raise ValueError("Handoff exceeds 16 KiB; compact task Resume/External first")
    path = record_path(B, root, task["id"], "handoff")
    Core.write_atomic(path, text)
    return data


def review_guard(B, root, task, review, solo, registry=None):
    proof = read_json(record_path(B, root, task["id"], "review-provenance"))
    if not proof or any(proof.get(k) != review.get(k) for k in ("reviewer", "digest", "contract")):
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
    path = A.registry_path(registry)
    spec = A.load(path).get("models", {}).get(reviewer, {}) if not self_review and path.exists() else {}
    if self_review:
        kind = "self-audit"
    elif spec:
        kind = "registered-model; host execution not authenticated"
    else:
        kind = "declared-only; independence not authenticated"
    data = {
        "reviewer": reviewer,
        "assurance": kind,
        "contract": B.contract(task),
        "digest": task_digest(B, root, task)[0],
        "model_identity": fingerprint({k: spec.get(k) for k in ("cli", "model_id", "pool_route", "roles", "tiers")}),
    }
    Core.write_atomic(record_path(B, root, task["id"], "review-provenance"), json.dumps(data, indent=2))
    return data
