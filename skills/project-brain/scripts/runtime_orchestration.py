"""Opt-in orchestration director. External effects are prepared, then read back."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import runtime_context as C
import runtime_executor_policy as E
import runtime_reports as Q
import runtime_runs as L
import runtime_security as S
import runtime_verify as V


def git(root, *args, env=None):
    result = subprocess.run(["git"] + list(args), cwd=str(root), env=env, capture_output=True,
                            encoding="utf-8", errors="replace", timeout=120,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if result.returncode:
        raise ValueError("Git operation failed: " + S.sanitize(result.stderr[:600]))
    return result.stdout.strip()


def human_env(root):
    name, email = git(root, "config", "user.name"), git(root, "config", "user.email")
    if not name or not email:
        raise ValueError("Existing human Git identity required")
    return dict(os.environ, GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email,
                GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email)


def changed_paths(B, root):
    """Expand untracked directories so nested files cannot evade scope checks."""
    tracked = B.git_paths(root, "diff", "HEAD", "--name-only")
    untracked = B.git_paths(root, "ls-files", "--others", "--exclude-standard")
    if tracked is None or untracked is None:
        raise ValueError("Cannot enumerate all changed paths safely")
    return sorted(set(tracked + untracked))


@contextmanager
def effect_lock(directory):
    """One external-effect writer shared by all linked worktrees; not age-based."""
    import brain as B
    # Reuse the OS locking implementation against a private synthetic lock root.
    lockroot = Path(directory) / "locks"
    (lockroot / B.BRAIN_DIR).mkdir(parents=True, exist_ok=True)
    with B.checkout_lock(lockroot, name="orchestration.lock"):
        yield


def task(B, root, row):
    value = B.find_task(root, row["task"])
    if not value or B.contract(value) != row["spec"]["contract"]:
        raise ValueError("Task contract changed; inspect old run, never replay it")
    return value


def current_intent(B, root, row):
    import runtime_protocol as R
    value = task(B, root, row)
    R.guard(B, root, value)
    if row["spec"]["packet"].get("intent") != R.intent(B, root, value):
        raise ValueError("STALE_INTENT: reconcile this run explicitly; its original task context cannot be changed")
    return value


def candidate_contract(B, root, candidate, row):
    import runtime_protocol as R
    original = current_intent(B, root, row)
    value = task(B, candidate, row)
    if R.intent(B, root, original) != R.intent(B, candidate, value):
        raise ValueError("Candidate target/constraints differ from current project intent")
    return value


def modes(B, root, kind, backend):
    B.require_session(root, implementation=kind == "EXECUTE")
    E.guard(B, root, "review" if kind == "REVIEW" else "exec", backend)
    value = B.get_session_modes(root)
    mode = value["rev" if kind == "REVIEW" else "exec"]
    if mode == "solo" or (backend == "pool") != mode.startswith("pool_"):
        raise ValueError("Worker backend is outside the selected session resource")
    return value, mode


def session_modes(B, root, db, kind, backend):
    origin = db.origin(root)
    if not origin.is_dir() or L.canonical(B, origin) != L.canonical(B, root):
        raise ValueError("Origin session is unavailable; explicitly rebind after recovery")
    return modes(B, origin, kind, backend)


def inherit_session(B, origin, candidate, db, settings):
    """Internal worktrees inherit confirmed choices, never exported control authority."""
    origin, candidate = Path(origin).resolve(), Path(candidate).resolve()
    if (db.origin(origin).resolve() != origin or not origin.is_dir()
            or L.canonical(B, origin) != L.canonical(B, candidate)
            or db.path.resolve().parent != L.directory(B, origin, create=False).resolve()):
        raise ValueError("Policy inheritance requires the authoritative same-repository origin")
    policy = E.require_confirmed(B, origin)
    if origin == candidate:
        return
    if policy is not None:
        name = B.BRAIN_DIR + "/executor-policy.json"
        source, target = V.public_path(origin, name), V.public_path(candidate, name)
        raw = source.read_text(encoding="utf-8")
        # The policy has just been validated; retain all exact selected values.
        B.write_atomic(target, raw)
        E.require_confirmed(B, origin)
        E.confirm(B, candidate, "Inherited confirmed origin choices for internal verification")
    # Routing assessments are not evidence/acceptance. Copy only from the same
    # validated origin; do not leave stale child assessments when origin has none.
    name = B.BRAIN_DIR + "/.cache/model-qualifications.json"
    source, target = V.public_path(origin, name), V.public_path(candidate, name)
    if source.exists():
        with source.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError("Model qualifications exceed 64 KiB")
        try:
            text = raw.decode("utf-8")
            json.loads(text)
        except (UnicodeError, ValueError, RecursionError) as error:
            raise ValueError("Malformed model qualifications") from error
        S.require_clean(text, "model qualifications")
        E.require_confirmed(B, origin)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".model-qualifications.", suffix=".tmp", dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    elif target.exists():
        target.unlink()
    B.set_session_modes(candidate, settings["exec"], settings["rev"], schedule=settings["schedule"],
                        max_parallel=settings["max_parallel"], task_mode=settings.get("task_mode", "execute"))


def native_candidate(B, origin, kind, candidate):
    role = "review" if kind == "REVIEW" else "exec"
    selected = E.selector(B, origin, role)
    bounded = selected and (selected["source"] in ("native-pinned", "native-cheap")
                           or selected.get("effort", {}).get("selector") == "user"
                           or "allowed" in selected.get("effort", {}))
    if candidate is None:
        if bounded:
            raise ValueError("Known native host/model candidate required before launch")
        E.guard(B, origin, role, "native")
        return None
    if (not isinstance(candidate, dict) or set(candidate) - {"host", "model", "effort", "cheaper"}
            or any(not isinstance(candidate.get(key), str) or not candidate[key].strip()
                   or candidate[key] != candidate[key].strip() or len(candidate[key]) > 256
                   or candidate[key].lower() == "unknown" or any(ord(c) < 32 or c in "*?[]" for c in candidate[key])
                   for key in ("host", "model"))):
        raise ValueError("Native candidate requires exact known host/model identity")
    if "effort" in candidate and (not isinstance(candidate["effort"], str) or not candidate["effort"].strip()
                                  or len(candidate["effort"]) > 256 or any(ord(c) < 32 for c in candidate["effort"])):
        raise ValueError("Native candidate effort must be bounded nonempty text")
    if "cheaper" in candidate and type(candidate["cheaper"]) is not bool:
        raise ValueError("Native candidate cheaper observation must be boolean")
    S.require_clean(json.dumps(candidate), "native candidate")
    E.guard(B, origin, role, "native", model=candidate, effort=candidate.get("effort"),
            cheaper=candidate.get("cheaper"))
    return dict(candidate)


def tier_cap(B, origin, kind, mode):
    selected = E.selector(B, origin, "review" if kind == "REVIEW" else "exec")
    if selected and selected["source"] == "native-cheap":
        return "H"  # A cheaper observation never lowers the task quality floor.
    return {"pool_low": "L", "pool_med_low": "M", "self_and_lower": "L"}.get(mode, "H")


def native_actor(host, model):
    return "native/" + hashlib.sha256(json.dumps([host, model], ensure_ascii=False).encode("utf-8")).hexdigest()[:24]


def actor_record(db, row):
    for entry in db.db.execute("SELECT data FROM events WHERE run=? ORDER BY seq", (row["id"],)):
        value = json.loads(entry[0])
        if value.get("actor"):
            return value
    raise ValueError("Actual worker identity is missing; obtain host/backend readback")


def require_control(db, rid):
    restored = db.db.execute("SELECT value FROM settings WHERE key='restored_runs'").fetchone()
    if restored and rid in json.loads(restored[0]):
        raise ValueError("RESTORED_READBACK_ONLY: observe/settle at the original host; copied state cannot control or integrate old jobs")


def native_gate(B, root, task_value, actor, action):
    """Declared host identity tied to a real run, never a free-form director alias."""
    directory = L.directory(B, root, create=False)
    if not (directory / "runs.sqlite3").exists():
        raise ValueError("Native actor has no project execution receipt")
    db = L.Ledger(directory / "runs.sqlite3")
    try:
        matches = []
        related = db.select("task=? AND state='SUCCEEDED' AND integration!='REJECTED'", (task_value["id"],))
        for row in related:
            if row["spec"]["backend"] != "native":
                continue
            try:
                identity = actor_record(db, row)
            except ValueError:
                continue
            if identity["actor"] == actor and row["state"] == "SUCCEEDED":
                matches.append((row, identity))
        kind = "REVIEW" if action == "review" else "EXECUTE"
        matches = [(r, i) for r, i in matches if r["kind"] == kind and B.contract(task_value) == r["spec"]["contract"]]
        if not matches:
            raise ValueError("Native actor lacks a completed task-bound " + kind + " receipt")
        row, identity = matches[-1]
        if action == "review":
            report = row["report"]
            if (not report or report["status"] != "completed" or report["blockers"] or
                    report.get("verdict") not in ("PASS", "BLOCKED") or not isinstance(report.get("findings"), list)):
                raise ValueError("Native review needs a complete typed verdict/findings report without execution blockers")
            import runtime_protocol as R
            if row["spec"]["source"] != R.task_digest(B, root, task_value)[0]:
                raise ValueError("Native review receipt is stale for current source")
            if identity.get("model") == "unknown":
                raise ValueError("Unknown native model cannot prove review independence")
            import runtime_agents as A
            for implementer in V.implementers(B, task_value):
                identities = [actor_record(db, r) for r in related if r["kind"] == "EXECUTE" and
                              actor_record(db, r)["actor"] == implementer]
                normalize = lambda m: A.norm_key(str(m).replace(":", "/").rsplit("/", 1)[-1])
                if not identities or any(i.get("model") in (None, "unknown") or
                                         normalize(i["model"]) == normalize(identity["model"]) for i in identities):
                    raise ValueError("Reviewer model implemented this task or implementation identity is missing")
            floors = [r.get("strength") for r in B.start_records(task_value) if r.get("strength")]
            if any(["low", "medium", "high"].index(s) > "LMH".index(identity["tier"]) for s in floors):
                raise ValueError("Native reviewer is weaker than the actual implementer")
        result = {"poolStrength": {"L": "low", "M": "medium", "H": "high"}[identity["tier"]]}
        if action == "review":
            result["review_report"] = row["report"]
        return result
    finally:
        db.close()


def prepare(B, root, db, directory, tid, kind, backend, resources=(), tiers=None, candidate=None):
    value = B.find_task(root, tid)
    if not value or B.task_errors(value):
        raise ValueError("Executable task required")
    settings, mode = session_modes(B, root, db, kind, backend)
    if backend != "native" and candidate is not None:
        raise ValueError("Host candidates require the native backend")
    origin = db.origin(root)
    if Path(root).resolve() != origin.resolve():
        inherit_session(B, origin, root, db, settings)
    candidate = native_candidate(B, origin, kind, candidate) if backend == "native" else None
    import runtime_agents as A
    tier = A.score_task(B, root, value)["effective_tier"]
    cap = tier_cap(B, origin, kind, mode)
    eligible = tiers or list("LMH"[:"LMH".index(cap) + 1])
    if not eligible or any(x not in "LMH" or len(x) != 1 or "LMH".index(x) > "LMH".index(cap) for x in eligible):
        raise ValueError("Task tier is outside the explicit permitted tier set")
    sufficient = sorted(set(x for x in eligible if "LMH".index(x) >= "LMH".index(tier)), key="LMH".index)
    if not sufficient:
        raise ValueError("No permitted model tier meets task quality floor")
    selected_tier = sufficient[0]
    if kind == "EXECUTE":
        _, completed = B.history_task_ids(root)
        completed |= {t["id"] for t in B.list_tasks(root) if t["status"] == "DONE" and t["has_evidence"]
                      and B.committed_exact(root, t["file"])}
        if any(dep not in completed for dep in value.get("deps", [])):
            raise ValueError("Dependencies must be accepted and integrated before dispatch")
        if value["status"] not in ("READY", "IN_PROGRESS"):
            raise ValueError("Task is not ready for implementation")
    packet = C.packet(B, root, value, kind)
    # A clean product tree is necessary for a reproducible base. Brain bookkeeping
    # may be dirty; it is supplied as immutable context, not silently committed.
    dirty = [p for p in B.dirty_paths(root) if not p.startswith(B.BRAIN_DIR + "/")]
    if dirty and kind == "EXECUTE":
        raise ValueError("Preserve/checkpoint product edits before isolated dispatch")
    db.configure(settings["schedule"], settings["max_parallel"])
    common = L.canonical(B, root)
    spec = {"task": tid, "kind": kind, "backend": backend, "areas": value["areas"],
            "resources": list(resources), "contract": B.contract(value), "source": packet["source"],
            "base": packet["base"], "workspace": str(Path(root).resolve()), "packet": packet,
            "tier": selected_tier, "task_tier": tier, "tiers": eligible, "mode": mode, "session": settings,
            "common": str(common), "isolation": "worktree, procedural access boundary"}
    if candidate is not None:
        spec["native_candidate"] = candidate
    row = db.prepare(spec)
    workspace = Path(directory) / "workspaces" / row["id"]
    if kind == "EXECUTE":
        branch = "codex/pb-" + row["id"]
        # Intent precedes creation. Path/branch are deterministic from immutable ID.
        db.event(row["id"], "WORKSPACE_INTENT", {"branch": branch})
        workspace.parent.mkdir(exist_ok=True)
        git(root, "worktree", "add", "-b", branch, str(workspace), spec["base"])
    return db.get(row["id"])


def workspace(row, directory):
    return Path(directory) / "workspaces" / row["id"] if row["kind"] == "EXECUTE" else Path(row["spec"]["workspace"])


def submit(B, root, db, directory, rid):
    import runtime_agent_pool as P
    row = db.get(rid)
    require_control(db, rid)
    value = task(B, root, row)
    if row["state"] == "PREPARED":
        current_intent(B, root, row)
        settings, mode = session_modes(B, root, db, row["kind"], row["spec"]["backend"])
        db.configure(settings["schedule"], settings["max_parallel"])
        executing = db.db.execute("SELECT COUNT(*) FROM runs WHERE id!=? AND state IN ('SUBMITTING','RUNNING','CANCEL_REQUESTED','UNKNOWN')", (rid,)).fetchone()[0]
        if executing >= db.policy()["cap"]:
            raise ValueError("CAPACITY: drain dispatched jobs before launching a prepared run")
        cap = tier_cap(B, db.origin(root), row["kind"], mode)
        if "LMH".index(row["spec"]["tier"]) > "LMH".index(cap):
            raise ValueError("Prepared run exceeds the current session tier cap")
        if row["spec"]["backend"] == "native":
            native_candidate(B, db.origin(root), row["kind"], row["spec"].get("native_candidate"))
    elif row["state"] not in ("SUBMITTING", "UNKNOWN"):
        return observe(B, root, db, directory, rid)
    path = workspace(row, directory)
    if row["state"] == "PREPARED" and row["kind"] == "REVIEW" and (git(path, "rev-parse", "HEAD") != row["spec"]["base"] or
            C.packet(B, path, value, "REVIEW")["source"] != row["spec"]["source"]):
        raise ValueError("REVIEW requires the exact prepared content snapshot")
    if not path.is_dir():
        raise ValueError("WORKSPACE_RECOVERY_REQUIRED: inspect creation intent")
    if row["state"] not in ("PREPARED", "SUBMITTING", "UNKNOWN"):
        return observe(B, root, db, directory, rid)
    if row["spec"]["backend"] == "native":
        if row["state"] != "PREPARED":
            raise ValueError("Native receipt/readback required; do not launch again")
        row = db.transition(rid, "SUBMITTING", row["version"])
        return {"run": rid, "host_action": "launch_once", "workspace": str(path),
                "request_key": row["spec"]["idempotencyKey"], "packet": row["spec"]["packet"],
                "model_tier": row["spec"]["tier"], "permitted_tiers": row["spec"]["tiers"],
                "candidate": row["spec"].get("native_candidate"),
                "policy_bounds": E.selector(B, db.origin(root), "review" if row["kind"] == "REVIEW" else "exec"),
                "capabilities": {"automatic_launch": False, "attach": "host-dependent", "token_counter": "unknown"}}
    saved = db.db.execute("SELECT payload FROM requests WHERE run=?", (rid,)).fetchone()
    if saved:
        request = json.loads(saved[0])
        if row["state"] == "PREPARED":
            E.guard(B, db.origin(root), "review" if row["kind"] == "REVIEW" else "exec", "pool",
                    model=dict(request, categories=[request["group"]] if request.get("group") else []),
                    category=request.get("group"), effort=request.get("effort"))
    else:
        if row["state"] != "PREPARED":
            raise ValueError("Missing immutable request; recover backend before any resend")
        selected = P.select_policy(B, db.origin(root), row["spec"]["tier"],
                                   role="reviewer" if row["kind"] == "REVIEW" else "worker")
        actor = P.remember(selected["selected"])
        request = dict(selected["request"], prompt=C.prompt(row["spec"]["packet"]), workspace=str(path),
                       timeoutSeconds=300, idempotencyKey=row["spec"]["idempotencyKey"])
        with db.transaction():
            db.db.execute("INSERT INTO requests VALUES(?,?)", (rid, json.dumps(request, ensure_ascii=False)))
            db.event(rid, "REQUEST_SAVED", {"route": request.get("routeId"), "model": request.get("modelId"),
                                           "actor": actor, "tier": row["spec"]["tier"]})
    if row["state"] == "PREPARED":
        row = db.transition(rid, "SUBMITTING", row["version"])
    try:
        result = P.rpc("pool_submit", request)
        row = db.transition(rid, "RUNNING", row["version"], backend_id=result["id"])
    except (ValueError, OSError, KeyError):
        live = db.get(rid)
        if live["state"] == "SUBMITTING":
            db.transition(rid, "UNKNOWN", live["version"])
        raise
    return observe(B, root, db, directory, rid)


def observe(B, root, db, directory, rid):
    import runtime_agent_pool as P
    row = db.get(rid)
    if row["state"] not in L.ACTIVE:
        return summary(row)
    if row["spec"]["backend"] == "native":
        return {"run": rid, "state": row["state"], "action": "Host readback/receipt required; no replay"}
    if not row["backend_id"]:
        return {"run": rid, "state": row["state"], "action": "submit reuses the saved exact request/key"}
    current = P.rpc("pool_get_task", {"taskId": row["backend_id"], "after": 0, "compact": True})
    states = {"queued": "RUNNING", "starting": "RUNNING", "running": "RUNNING", "cancelling": "CANCEL_REQUESTED",
              "succeeded": "SUCCEEDED", "failed": "FAILED", "cancelled": "CANCELLED", "needs_review": "FAILED"}
    state = states.get(current.get("state"), "UNKNOWN")
    report = current.get("report")
    if state == "SUCCEEDED" and report is None and row["kind"] == "REVIEW":
        report = {"status": "completed", "summary": "Review response retained; director must inspect findings",
                  "files": [], "checks": [], "research": [], "blockers": [],
                  "findings": [current.get("result") or "Missing review response"], "decision_required": True}
    if state == "SUCCEEDED":
        try:
            Q.validate(report)
        except ValueError:
            state, report = "UNKNOWN", None
    if state == "RUNNING" and row["state"] == "CANCEL_REQUESTED":
        state = "CANCEL_REQUESTED"
    if state != row["state"]:
        row = db.transition(rid, state, row["version"], report=report,
                            observation={"selected_model": current.get("modelId"),
                                         "reported_model": current.get("reportedModel"), "effort": current.get("effort")})
    return summary(row)


def native_receipt(db, rid, receipt):
    row = db.get(rid)
    if row["spec"]["backend"] != "native" or receipt.get("request_key") != row["spec"]["idempotencyKey"]:
        raise ValueError("Host receipt does not match immutable native request")
    if not isinstance(receipt.get("host"), str) or not receipt["host"].strip():
        raise ValueError("Real host identity required")
    state = receipt.get("state")
    if state not in ("RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"):
        raise ValueError("Invalid host process state")
    if receipt.get("tier") is not None and receipt["tier"] not in row["spec"]["tiers"]:
        raise ValueError("Host model tier is outside the selected resource set")
    if receipt.get("tier") is not None and "LMH".index(receipt["tier"]) < "LMH".index(row["spec"]["tier"]):
        raise ValueError("Host model tier is below the required quality floor")
    model = receipt.get("model")
    if not isinstance(model, str) or not model.strip() or receipt.get("tier") is None:
        raise ValueError("Host receipt requires actual model (or unknown) and classified tier")
    candidate = row["spec"].get("native_candidate")
    if candidate and any(receipt.get(key) != expected or type(receipt.get(key)) is not type(expected)
                         for key, expected in candidate.items()):
        raise ValueError("Host receipt differs from immutable native candidate")
    actor = native_actor(receipt["host"], model)
    previous = [json.loads(v[0]) for v in db.db.execute("SELECT data FROM events WHERE run=?", (rid,))]
    if any(v.get("actor") and (v["actor"] != actor or v.get("host") != receipt["host"] or
                              v.get("model") != model or v.get("tier") != receipt["tier"]) for v in previous):
        raise ValueError("Native worker identity/strength cannot change within a run")
    S.require_clean(json.dumps(receipt, ensure_ascii=False), "host receipt")
    observation = {"host": receipt["host"], "model": model, "actor": actor, "tier": receipt["tier"],
                   "usage": Q.usage(receipt.get("usage"))}
    if candidate:
        observation.update({key: candidate[key] for key in ("effort", "cheaper") if key in candidate})
    import runtime_agents as A
    A.register_model(actor, {"model_id": model, "cli": "native-host", "native_orchestration": True,
                             "available": True, "roles": ["worker", "lead", "reviewer"], "tiers": ["L", "M", "H"]})
    result = db.transition(rid, state, row["version"], backend_id=receipt.get("job_id"),
                           report=receipt.get("report"), observation=observation)
    return dict(summary(result), actor=actor)


def summary(row):
    result = {"run": row["id"], "task": row["task"], "kind": row["kind"], "state": row["state"],
              "verification": row["verification"], "integration": row["integration"]}
    if row["report"]:
        result["result"] = Q.compact(row["report"], "runs report " + row["id"], limit=650)
    return result


def snapshot(B, root, db, directory, rid):
    require_control(db, rid)
    row = db.get(rid)
    current_intent(B, root, row)
    B.require_session(root, implementation=True)
    if row["kind"] != "EXECUTE" or row["state"] != "SUCCEEDED":
        raise ValueError("Only completed EXECUTE can be snapshotted")
    if row["integration"] == "REJECTED":
        raise ValueError("Rejected result is closed; explicitly prepare a new attempt")
    if (row["report"]["status"] != "completed" or row["report"]["blockers"] or
            any(c["outcome"] == "failed" for c in row["report"]["checks"])):
        raise ValueError("Resolve partial/blocked/failed execution before snapshot")
    if row["output"]:
        return row["output"]
    path = workspace(row, directory)
    if git(path, "rev-parse", "HEAD") != row["spec"]["base"]:
        raise ValueError("Unexpected worker commit; inspect before continuing")
    changed = changed_paths(B, path)
    if not changed or any(not any(B.matches(p, a) for a in row["spec"]["areas"]) or
                          p.startswith(B.BRAIN_DIR + "/") or V.PRIVATE.search(p) for p in changed):
        raise ValueError("No changes or changes outside assigned Areas")
    for p in changed:
        V.public_path(path, p)
    # Uses a temporary index, leaving worker and user indexes untouched.
    fd, index = tempfile.mkstemp(prefix="pb-index-", dir=str(directory))
    os.close(fd)
    os.unlink(index)
    env = dict(human_env(root), GIT_INDEX_FILE=index)
    try:
        if B.parse_config(root).get("git", {}).get("commit") == "ask":
            raise ValueError("COMMIT_APPROVAL_REQUIRED: snapshot creates a Git object")
        name, email = git(root, "config", "user.name"), git(root, "config", "user.email")
        if not name or not email:
            raise ValueError("Existing human Git identity required")
        git(path, "read-tree", row["spec"]["base"], env=env)
        git(path, "add", "--", *changed, env=env)
        git(path, "diff", "--cached", "--check", env=env)
        # Scan staged content through existing secret guard using the same index.
        diff = git(path, "diff", "--cached", env=env)
        S.require_clean(diff, "snapshot diff")
        tree = git(path, "write-tree", env=env)
        output = git(path, "commit-tree", tree, "-p", row["spec"]["base"], "-m", "Checkpoint " + row["task"], env=env)
        # Keep the snapshot reachable during long interruptions, independently of
        # private database retention and Git's unreachable-object pruning.
        git(path, "update-ref", "refs/project-brain/" + rid, output)
        db.annotate(rid, "SNAPSHOT", output=output)
        return output
    finally:
        if Path(index).exists():
            Path(index).unlink()


def verify(B, root, db, directory, rid, actor):
    row = db.get(rid)
    value = current_intent(B, root, row)
    if row["state"] != "SUCCEEDED":
        raise ValueError("Completed run required")
    actual = actor_record(db, row)["actor"]
    if actor and actor != actual:
        raise ValueError("Verifier cannot replace the actual implementer identity")
    actor = actual
    if row["kind"] == "REVIEW":
        if C.packet(B, root, value, "REVIEW")["source"] != row["spec"]["source"]:
            raise ValueError("STALE: review source changed")
        db.annotate(rid, "REVIEW_COLLECTED", verification="PASS")
        return {"run": rid, "collected": True, "note": "Collection is not task acceptance; use PB review with actual findings"}
    output = snapshot(B, root, db, directory, rid)
    candidate = Path(directory) / "candidates" / (rid + "-" + git(root, "rev-parse", "HEAD")[:12])
    if not candidate.exists():
        db.event(rid, "CANDIDATE_INTENT", {"head": git(root, "rev-parse", "HEAD")})
        candidate.parent.mkdir(exist_ok=True)
        git(root, "worktree", "add", "--detach", str(candidate), git(root, "rev-parse", "HEAD"))
        # A conflict leaves a recoverable candidate. Never resolve it by an LLM-free
        # guess or silently reset the user's original tree.
        git(candidate, "merge", "--no-commit", "--no-ff", output)
        source = B.bp(root)
        for entry in source.rglob("*"):
            if entry.is_file() and ".cache" not in entry.relative_to(source).parts:
                rel = entry.relative_to(root).as_posix()
                src, dest = V.public_path(root, rel), V.public_path(candidate, rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dest))
        settings = B.get_session_modes(root)
        inherit_session(B, db.origin(root), candidate, db, settings)
    if git(candidate, "diff", "--name-only", "--diff-filter=U"):
        raise ValueError("Candidate has unresolved merge conflicts; repair and recheck")
    live = candidate_contract(B, root, candidate, row)
    if not live:
        raise ValueError("CANDIDATE_RECOVERY_REQUIRED: initialization interrupted; preserve candidate and restore director context")
    if live["owner"] and live["owner"] != actor:
        raise ValueError("Candidate owner differs; use actual implementer identity")
    if live["status"] == "READY":
        if B.cmd_start(candidate, row["task"], agent=actor):
            raise ValueError("Candidate start failed; preserve workspace for inspection")
    with B.checkout_lock(candidate):
        rc, lines = V.check(B, candidate, row["task"], actor=actor)
    db.event(rid, "CANDIDATE_CHECK", {"exit": rc})
    return {"run": rid, "candidate": str(candidate), "checks": lines, "exit": rc,
            "next": "Use existing PB evidence/review/accept in candidate, then runs integrate. Machine checks alone do not accept the task."}


def integrate(B, root, db, directory, rid):
    require_control(db, rid)
    if Path(root).resolve() != db.origin(root).resolve():
        raise ValueError("Integrate from the authoritative origin checkout, not a worker/candidate")
    row = db.get(rid)
    if not row["output"] or row["state"] != "SUCCEEDED" or row["kind"] != "EXECUTE":
        raise ValueError("Completed snapshot required")
    if row["integration"] == "REJECTED":
        raise ValueError("Rejected result cannot be integrated")
    if B.dirty_paths(root):
        raise ValueError("Checkpoint existing user/Brain work before integration")
    if any(r["state"] in L.ACTIVE and r["kind"] == "REVIEW" for r in db.all()):
        raise ValueError("Wait for snapshot readers before moving their target")
    head = git(root, "rev-parse", "HEAD")
    intents = [json.loads(e[0]) for e in db.db.execute("SELECT data FROM events WHERE run=? AND event='INTEGRATION_INTENT' ORDER BY seq", (rid,))]
    if intents:
        probe = subprocess.run(["git", "merge-base", "--is-ancestor", intents[-1]["output"], head],
                               cwd=str(root), capture_output=True)
        if probe.returncode == 0:
            target_observation(B, root, db, row, intents[-1]["output"])
            db.annotate(rid, "INTEGRATION_READBACK", verification="PASS", integration="MERGED")
            return summary(db.get(rid))
    current_intent(B, root, row)
    settings = B.require_session(db.origin(root), implementation=True)
    candidate = Path(directory) / "candidates" / (rid + "-" + head[:12])
    if not candidate.is_dir():
        raise ValueError("Run verify to construct and check an integration candidate first")
    candidate_head = git(candidate, "rev-parse", "HEAD")
    if candidate_head != head:
        pending = db.db.execute("SELECT data FROM events WHERE run=? AND event='COMMIT_INTENT' ORDER BY seq DESC LIMIT 1", (rid,)).fetchone()
        if (pending and json.loads(pending[0]).get("base") == head and
                git(candidate, "rev-parse", "HEAD^1") == head and not changed_paths(B, candidate) and
                git(candidate, "rev-parse", "HEAD^{tree}") == json.loads(pending[0]).get("tree")):
            db.event(rid, "INTEGRATION_INTENT", {"base": head, "output": candidate_head})
            git(root, "merge", "--ff-only", candidate_head)
            target_observation(B, root, db, row, candidate_head)
            db.annotate(rid, "INTEGRATION_COMMIT_READBACK", verification="PASS", integration="MERGED")
            return summary(db.get(rid))
        raise ValueError("TARGET_ADVANCED: preserve candidate and rebuild with fresh evidence")
    live = candidate_contract(B, root, candidate, row)
    inherit_session(B, db.origin(root), candidate, db, settings)
    if live["status"] != "DONE":
        raise ValueError("Candidate must pass existing PB evidence/review/accept before merge")
    # Re-run the authoritative acceptance gate against current candidate source,
    # logs, reviewer and environment. Never manufacture Evidence/Review records.
    import runtime_protocol as R
    accepted_digest = R.task_digest(B, candidate, live)[0]
    B.set_header(live["file"], "Status", "REVIEW")
    with B.checkout_lock(candidate):
        rc, lines = V.accept(B, candidate, row["task"], actor=live["owner"])
    if rc:
        db.annotate(rid, "STALE_CANDIDATE", verification="STALE")
        raise ValueError("Candidate no longer accepted: " + "; ".join(lines))
    if B.parse_config(root).get("git", {}).get("commit") == "ask":
        raise ValueError("COMMIT_APPROVAL_REQUIRED: integration moves the target branch")
    # Commit only the assigned code plus task/receipt state; preserve unrelated
    # product changes made in the candidate by a mistaken test or reviewer.
    changed = changed_paths(B, candidate)
    brain_allowed = (B.BRAIN_DIR + "/tasks/" + row["task"] + ".md", B.BRAIN_DIR + "/evidence/" + row["task"] + "/")
    allowed = [p for p in changed if p == brain_allowed[0] or p.startswith(brain_allowed[1]) or
               any(B.matches(p, a) for a in row["spec"]["areas"])]
    if set(changed) != set(allowed):
        raise ValueError("Candidate changed files outside task Areas")
    git(candidate, "add", "--", *allowed)
    S.scan_staged(B, candidate)
    if R.task_digest(B, candidate, B.find_task(candidate, row["task"]))[0] != accepted_digest:
        raise ValueError("Candidate changed while acceptance/staging ran; reverify")
    accepted_tree = git(candidate, "write-tree")
    db.event(rid, "COMMIT_INTENT", {"base": head, "tree": accepted_tree})
    level = {"LOW": "local", "MEDIUM": "domain", "HIGH": "global"}[V.effective_risk(B, B.find_task(candidate, row["task"]))]
    git(candidate, "commit", "-m", "Integrate " + row["task"] + "\n\nPB-Task: " + row["task"] +
        "\nPB-Verification: " + level, env=human_env(root))
    integrated = git(candidate, "rev-parse", "HEAD")
    post_tree = git(candidate, "rev-parse", "HEAD^{tree}")
    post_digest = R.task_digest(B, candidate, B.find_task(candidate, row["task"]))[0]
    post_dirty = changed_paths(B, candidate)
    if post_tree != accepted_tree or post_digest != accepted_digest or post_dirty:
        db.annotate(rid, "POST_COMMIT_MUTATION", verification="STALE")
        raise ValueError("Commit hooks or concurrent edits changed the accepted candidate; inspect and reverify " +
                         str({"tree_changed": post_tree != accepted_tree, "inputs_changed": post_digest != accepted_digest,
                              "dirty": post_dirty[:10]}))
    db.event(rid, "INTEGRATION_INTENT", {"base": head, "output": integrated})
    # External Git writers do not participate in our lock. ff-only refuses a
    # divergent target; readback handles a lost acknowledgement.
    git(root, "merge", "--ff-only", integrated)
    target_observation(B, root, db, row, integrated)
    db.annotate(rid, "CANDIDATE_ACCEPTED", verification="PASS")
    db.annotate(rid, "INTEGRATED_PENDING_ACCEPTANCE", integration="MERGED")
    return summary(db.get(rid))


def target_observation(B, root, db, row, expected):
    """Observe the destination after hooks; preserve unexpected files on failure."""
    dirty = changed_paths(B, root)
    changed = B.git_paths(root, "diff", expected, "HEAD", "--name-only")
    if changed is None:
        raise ValueError("Cannot verify integrated destination")
    product_changes = [p for p in changed if not p.startswith(B.BRAIN_DIR + "/")]
    if dirty or product_changes:
        db.annotate(row["id"], "TARGET_CHANGED_AFTER_MERGE", verification="STALE", integration="MERGED")
        raise ValueError("Target changed after the accepted merge; preserve edits and reverify destination")
    # Preserve the actual cited machine logs in the receiving checkout so a
    # normal restart need not re-run intact checks merely because of integration.
    candidate = Path(db.path).parent / "candidates"
    value = next((t for t in B.list_tasks(root) if t["id"] == row["task"]), None)
    if value:
        for line in value.get("evidence_lines", []):
            match = V.CHECK_RE.match(line)
            if not match:
                continue
            rel = B.BRAIN_DIR + "/" + match.group("log")
            destination = V.public_path(root, rel)
            if destination.exists():
                if V._hash(destination) != match.group("hash"):
                    raise ValueError("Destination check log differs; preserve both and recheck")
                continue
            for folder in candidate.glob(row["id"] + "-*"):
                source = V.public_path(folder, rel)
                if source.is_file() and V._hash(source) == match.group("hash"):
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open("xb") as output:
                        output.write(source.read_bytes())
                    break


def restore(B, root, directory, source):
    """Relocate private observations safely; never transfer process control by copy."""
    import sqlite3
    source = L.private(source)
    destination = L.private(Path(directory) / "runs.sqlite3")
    if destination.exists():
        raise ValueError("Restore requires a new project ledger; existing state is never overwritten")
    if changed_paths(B, root):
        raise ValueError("Restore requires a clean destination checkout")
    connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    temporary = destination.with_name("restore-" + str(time.time_ns()) + ".sqlite3")
    target = None
    try:
        if connection.execute("PRAGMA user_version").fetchone()[0] != L.SCHEMA or connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Unsupported or damaged backup; preserve original")
        if connection.execute("SELECT name FROM sqlite_master WHERE type IN ('view','trigger')").fetchone():
            raise ValueError("Unexpected executable backup schema")
        required = {"runs", "events", "requests", "settings"}
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required.issubset(tables) or tables - required - {"sqlite_sequence"}:
            raise ValueError("Unexpected backup tables")
        for tid, spec in connection.execute("SELECT task,spec FROM runs"):
            value = json.loads(spec)
            git(root, "cat-file", "-e", value["base"] + "^{commit}")
            current = next((t for t in B.list_tasks(root) if t["id"] == tid), None)
            if current is not None and B.contract(current) != value["contract"]:
                raise ValueError("Destination task contract differs from backed-up work")
        target = sqlite3.connect(str(temporary))
        connection.backup(target)
        target.close()
        target = None
        restored = L.Ledger(temporary)
        try:
            ids = [r[0] for r in restored.db.execute("SELECT id FROM runs")]
            with restored.transaction():
                restored.db.execute("INSERT OR REPLACE INTO settings VALUES('origin',?)", (str(Path(root).resolve()),))
                restored.db.execute("INSERT OR REPLACE INTO settings VALUES('restored_runs',?)", (json.dumps(ids),))
            for row in restored.select("state IN ('SUBMITTING','RUNNING','CANCEL_REQUESTED')"):
                restored.transition(row["id"], "UNKNOWN", row["version"], observation={"reason": "relocated; original host readback required"})
        finally:
            restored.close()
        # Never replace a concurrently created ledger. The project effect lock
        # serializes command writers; exclusive link also refuses a new target.
        os.link(str(temporary), str(destination))
        return {"restored": len(ids), "authority": "readback only for imported runs; original processes may still be alive"}
    finally:
        connection.close()
        if target is not None:
            target.close()
        if temporary.exists():
            temporary.unlink()


def view(db, after=0):
    events, size = [], 0
    for event in db.events(after):
        item = {"seq": event["seq"], "run": event["run"], "event": event["event"]}
        n = len(json.dumps(item).encode("utf-8"))
        if size + n > 3000:
            break
        events.append(item)
        size += n
    active = db.db.execute("SELECT COUNT(*) FROM runs WHERE state IN ('PREPARED','SUBMITTING','RUNNING','CANCEL_REQUESTED','UNKNOWN')").fetchone()[0]
    pending = db.db.execute("SELECT COUNT(*) FROM runs WHERE state='SUCCEEDED' AND verification!='PASS' AND integration!='REJECTED'").fetchone()[0]
    return {"policy": db.policy(), "events": events, "cursor": events[-1]["seq"] if events else after,
            "active": active, "verification_pending": pending}


def export(db):
    """Portable observations, not credentials, local paths or execution authority."""
    rows = []
    for r in db.all():
        rows.append({"run": r["id"], "task": r["task"], "kind": r["kind"], "state": r["state"],
                     "contract": r["spec"]["contract"], "base": r["spec"]["base"],
                     "output": r["output"], "verification": r["verification"], "integration": r["integration"],
                     "readback_required": r["state"] in L.ACTIVE,
                     "report_available_at_origin": r["report"] is not None})
    return {"schema": 1, "runs": rows, "authority": "observations only; attach at origin before takeover",
            "evidence": "private receipts/logs not transferred; recheck in a new environment"}


def cleanup(B, root, db, directory, rid):
    require_control(db, rid)
    if db.db.execute("SELECT 1 FROM runs WHERE kind='REVIEW' AND state IN ('PREPARED','SUBMITTING','RUNNING','UNKNOWN','CANCEL_REQUESTED')").fetchone():
        raise ValueError("Settle snapshot readers before cleanup")
    row = db.get(rid)
    if row["state"] in L.ACTIVE or row["kind"] == "EXECUTE" and row["state"] == "SUCCEEDED" and row["integration"] not in ("MERGED", "REJECTED"):
        raise ValueError("Unresolved run cannot be cleaned")
    removed, retained = [], []
    paths = [workspace(row, directory)] if row["kind"] == "EXECUTE" else []
    paths += list((Path(directory) / "candidates").glob(rid + "-*"))
    for path in paths:
        resolved = L.private(path).resolve()
        base = Path(directory).resolve()
        if base not in resolved.parents or not path.exists():
            continue
        if B.dirty_paths(path):
            retained.append(path.name + ": dirty; preserve artifacts")
            continue
        db.event(rid, "CLEANUP_INTENT", {"workspace": path.name})
        git(root, "worktree", "remove", str(resolved))
        removed.append(path.name)
    # Never delete the ledger/request keys: they are the recovery/dedup tombstone.
    db.event(rid, "CLEANUP_RESULT", {"removed": removed, "retained": retained})
    return {"removed": removed, "retained": retained, "ledger": "preserved"}


def rebuild(B, root, db, directory, rid):
    """Explicitly preserve a failed candidate before building a new one."""
    require_control(db, rid)
    row = db.get(rid)
    if row["state"] != "SUCCEEDED" or row["kind"] != "EXECUTE":
        raise ValueError("Only completed implementation candidates can be rebuilt")
    if db.db.execute("SELECT 1 FROM runs WHERE kind='REVIEW' AND state IN ('PREPARED','SUBMITTING','RUNNING','UNKNOWN','CANCEL_REQUESTED')").fetchone():
        raise ValueError("Settle snapshot readers before rebuilding")
    base = Path(directory).resolve()
    path = L.private(base / "candidates" / (rid + "-" + git(root, "rev-parse", "HEAD")[:12])).resolve()
    destination = L.private(base / "recovery" / (rid + "-" + str(time.time_ns()))).resolve()
    if base not in path.parents or base not in destination.parents:
        raise ValueError("Candidate move escapes managed workspace")
    if path.exists():
        destination.parent.mkdir(exist_ok=True)
        db.event(rid, "CANDIDATE_ARCHIVE_INTENT", {"from": path.name, "to": destination.name})
        git(root, "worktree", "move", str(path), str(destination))
        db.event(rid, "CANDIDATE_ARCHIVED", {"artifact": destination.name})
    return {"run": rid, "next": "runs verify creates a fresh candidate; archived edits are retained for inspection"}


def reject(B, root, db, rid, note):
    require_control(db, rid)
    row = db.get(rid)
    if row["kind"] != "EXECUTE" or row["state"] != "SUCCEEDED" or row["integration"] != "PENDING":
        raise ValueError("Only completed unintegrated results may be rejected")
    if not isinstance(note, str) or not note.strip() or len(note) > 500:
        raise ValueError("Reject requires the actual inspection reason, at most 500 characters")
    S.require_public(note, "rejection reason")
    origin = db.origin(root)
    if not origin.is_dir() or L.canonical(B, origin) != L.canonical(B, root):
        raise ValueError("Authoritative origin is unavailable; resolve integration there before rejecting")
    for data, in db.db.execute("SELECT data FROM events WHERE run=? AND event='INTEGRATION_INTENT'", (rid,)):
        output = json.loads(data)["output"]
        observed = subprocess.run(["git", "merge-base", "--is-ancestor", output, "HEAD"], cwd=str(origin), capture_output=True)
        if observed.returncode == 0:
            target_observation(B, origin, db, row, output)
            db.annotate(rid, "REJECTION_READBACK_ALREADY_MERGED", verification="PASS", integration="MERGED")
            raise ValueError("Result is already integrated; rejection cannot undo Git history")
        if observed.returncode != 1:
            raise ValueError("Read back the pending integration before rejecting; Git state is uncertain")
    db.annotate(rid, "RESULT_REJECTED: " + note, verification="FAIL", integration="REJECTED")
    return {"run": rid, "integration": "REJECTED", "artifacts": "preserved",
            "next": "Explicit prepare may create a new attempt; advance never retries rejected work"}


def advance(B, root, db, directory, backend, tiers, candidate=None):
    """One bounded scheduling tick. No LLM calls for unchanged process status."""
    rows = db.select("state IN ('PREPARED','SUBMITTING','RUNNING','CANCEL_REQUESTED','UNKNOWN')")
    for r in rows:
        if r["state"] in L.ACTIVE and r["backend_id"] and r["spec"]["backend"] == "pool":
            observe(B, root, db, directory, r["id"])
    rows = db.select("state IN ('PREPARED','SUBMITTING','RUNNING','CANCEL_REQUESTED','UNKNOWN') OR (kind='EXECUTE' AND integration!='MERGED')")
    _, completed = B.history_task_ids(root)
    # A failed/cancelled attempt is not permission to dispatch the still-READY
    # Markdown task again. Only an explicit prepare after inspection starts a new
    # attempt; scheduling ticks never replay a failed write automatically.
    held = {r["task"] for r in rows if r["state"] in L.ACTIVE or
            r["kind"] == "EXECUTE" and r["integration"] != "MERGED"}
    candidates = L.ready(B.list_tasks(root), completed, held)
    started, blocked = [], []
    for tid in candidates:
        try:
            r = prepare(B, root, db, directory, tid, "EXECUTE", backend, tiers=tiers, candidate=candidate)
            result = submit(B, root, db, directory, r["id"])
            started.append(result)
            # A native host needs exactly one launch request at a time to avoid
            # pretending a queued tool request is an already running worker.
            if backend == "native":
                break
        except ValueError as e:
            blocked.append({"task": tid, "reason": S.sanitize(str(e))[:250]})
            if str(e).startswith("CAPACITY"):
                break
    return {"started": started, "blocked": blocked[:10], "status": view(db)}


def add_parser(sub):
    parser = sub.add_parser("runs", help="Opt-in durable worker runs; legacy delegate is unchanged")
    parser.add_argument("action", choices=("status", "plan", "prepare", "submit", "observe", "wait", "receipt",
                                           "report", "verify", "integrate", "cancel", "context", "search",
                                           "export", "cleanup", "advance", "backup", "metrics", "restore", "rebuild", "reject"))
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--task", default="")
    parser.add_argument("--run", default="")
    parser.add_argument("--kind", choices=("EXECUTE", "REVIEW"), default="EXECUTE")
    parser.add_argument("--backend", choices=("pool", "native"), default="native")
    parser.add_argument("--resource", action="append", default=[])
    parser.add_argument("--tiers", default="")
    parser.add_argument("--host", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--effort", default="")
    parser.add_argument("--cheaper", action="store_const", const=True, default=None)
    parser.add_argument("--after", type=int, default=0)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--file", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--start-file", default="")
    parser.add_argument("--actor", default="")


def command(B, args):
    if os.environ.get("CLI_AGENT_POOL_WORKER"):
        raise ValueError("Workers cannot manage orchestration")
    root = Path(args.root).resolve()
    if args.action == "metrics":
        file = L.private(args.file)
        if file.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("Measurement input exceeds 4 MiB")
        result = Q.compare(json.loads(file.read_text(encoding="utf-8")))
        S.require_public(json.dumps(result), "measurement summary")
        return result
    if args.action == "search":
        return C.discover(B, root, args.query, args.after, start_file=args.start_file)
    if args.action == "context":
        value = B.find_task(root, args.task)
        if not value:
            raise ValueError("Task not found")
        return C.packet(B, root, value, args.kind)
    directory = L.directory(B, root)
    if args.action == "restore":
        with effect_lock(directory):
            return restore(B, root, directory, args.file)
    db = L.Ledger(directory / "runs.sqlite3")
    try:
        if args.action == "status":
            return view(db, args.after)
        if args.action == "report":
            return db.get(args.run)["report"]
        if args.action == "export":
            result = export(db)
            S.require_public(json.dumps(result), "portable run manifest")
            return result
        if args.action == "backup":
            target = L.private(args.file) if args.file else directory / ("backup-" + str(time.time_ns()) + ".sqlite3")
            if root == target.resolve() or root in target.resolve().parents:
                raise ValueError("Private backup must stay outside the repository")
            return {"backup": str(db.backup(target))}
        if args.action == "plan":
            _, completed = B.history_task_ids(root)
            rows = db.all()
            return {"ready": L.ready(B.list_tasks(root), completed,
                                     {r["task"] for r in rows if r["state"] in L.ACTIVE or
                                      r["kind"] == "EXECUTE" and r["integration"] != "MERGED"}), "policy": db.policy()}
        if args.action == "wait":
            if not 1 <= args.seconds <= 60:
                raise ValueError("Wait must be 1..60 seconds")
            until = time.monotonic() + args.seconds
            while time.monotonic() < until:
                with effect_lock(directory):
                    result = observe(B, root, db, directory, args.run)
                if db.get(args.run)["state"] not in L.ACTIVE:
                    return result
                time.sleep(min(1, max(0, until - time.monotonic())))
            return dict(result, wait_expired=True)
        with effect_lock(directory):
            candidate = {key: getattr(args, key) for key in ("host", "model", "effort", "cheaper")
                         if getattr(args, key, None) not in (None, "")}
            if args.action == "advance":
                return advance(B, root, db, directory, args.backend, list(args.tiers) if args.tiers else None,
                               candidate=candidate or None)
            if args.action == "cleanup":
                return cleanup(B, root, db, directory, args.run)
            if args.action == "rebuild":
                return rebuild(B, root, db, directory, args.run)
            if args.action == "reject":
                return reject(B, root, db, args.run, args.note)
            if args.action == "prepare":
                return summary(prepare(B, root, db, directory, args.task, args.kind, args.backend,
                                       args.resource, list(args.tiers) if args.tiers else None, candidate=candidate or None))
            if args.action == "submit":
                return submit(B, root, db, directory, args.run)
            if args.action == "observe":
                return observe(B, root, db, directory, args.run)
            if args.action == "receipt":
                file = L.private(args.file)
                if file.stat().st_size > 1024 * 1024:
                    raise ValueError("Receipt exceeds 1 MiB")
                return native_receipt(db, args.run, json.loads(file.read_text(encoding="utf-8")))
            if args.action == "verify":
                return verify(B, root, db, directory, args.run, args.actor)
            if args.action == "integrate":
                return integrate(B, root, db, directory, args.run)
            if args.action == "cancel":
                require_control(db, args.run)
                row = db.get(args.run)
                if row["state"] == "PREPARED":
                    return summary(db.transition(args.run, "CANCELLED", row["version"]))
                if row["spec"]["backend"] == "native" and row["backend_id"] and row["state"] in ("RUNNING", "UNKNOWN", "CANCEL_REQUESTED"):
                    if row["state"] != "CANCEL_REQUESTED":
                        row = db.transition(args.run, "CANCEL_REQUESTED", row["version"])
                    return {"run": args.run, "host_action": "request_cancel", "job_id": row["backend_id"],
                            "state": row["state"], "next": "Host must observe stopped/interrupted before receipt CANCELLED; do not replay"}
                if row["spec"]["backend"] == "pool" and row["backend_id"]:
                    import runtime_agent_pool as P
                    if row["state"] in ("RUNNING", "UNKNOWN"):
                        row = db.transition(args.run, "CANCEL_REQUESTED", row["version"])
                    P.rpc("pool_cancel_task", {"taskId": row["backend_id"]})
                    return observe(B, root, db, directory, args.run)
                raise ValueError("Native host must confirm cancellation; no process state inferred")
    finally:
        db.close()
