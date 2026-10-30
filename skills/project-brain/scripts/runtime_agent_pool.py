"""CLI Agent Pool transport. Brain owns plans/evidence; Pool owns execution/policy."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

import runtime_verify as V

GROUPS = {"L": "low", "M": "medium", "H": "high"}
ACTIVE = {"queued", "starting", "running", "cancelling"}


def command():
    """Resolve a shell-free entry point, including npm's Windows shim target."""
    override = os.environ.get("PB_AGENT_POOL_COMMAND")
    if override:
        argv = json.loads(override)
        if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x or "\x00" in x for x in argv):
            raise ValueError("PB_AGENT_POOL_COMMAND must be a JSON argv array")
        if Path(argv[0]).suffix.lower() in (".cmd", ".bat", ".ps1"):
            raise ValueError("Pool entry point must not be a shell shim")
        return argv
    node = shutil.which("node")
    if os.name == "nt" and node:
        entry = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "npm/node_modules/cli-agent-pool/bin/pool.js"
        if entry.is_file():
            return [node, str(entry)]
    binary = shutil.which("cli-agent-pool")
    if binary and Path(binary).suffix.lower() not in (".cmd", ".bat", ".ps1"):
        return [binary]
    raise ValueError("CLI Agent Pool is not installed; install it or explicitly use --backend direct")


def rpc(tool, arguments=None):
    # The detached shared daemon must survive this short-lived RPC client. A worker
    # ProcessTree would also kill a freshly started daemon on Windows JobObject close.
    env = {k: v for k, v in os.environ.items() if not V.SECRET_ENV.search(k)}
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        response = subprocess.run(command() + ["rpc"],
                                  input=json.dumps({"tool": tool, "arguments": arguments or {}}, ensure_ascii=False),
                                  capture_output=True, encoding="utf-8", timeout=45, env=env,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except subprocess.TimeoutExpired:
        raise ValueError("Pool RPC timed out; read back the saved task before retrying")
    if len(response.stdout.encode("utf-8")) > 1024 * 1024:
        raise ValueError("Pool response exceeds 1 MiB")
    try:
        value = json.loads(response.stdout)
    except ValueError:
        raise ValueError("Pool did not return JSON (exit %s); check installation/service" % response.returncode)
    if response.returncode or isinstance(value, dict) and isinstance(value.get("error"), dict):
        error = value.get("error", {}) if isinstance(value, dict) and isinstance(value.get("error"), dict) else {}
        raise ValueError("Pool %s: %s" % (error.get("code", response.returncode), error.get("message", "request failed")))
    return value


def status():
    return {"backend": "cli-agent-pool", "policy": rpc("pool_get_policy"),
            "pools": rpc("pool_list_pools"), "connections": rpc("pool_list_connections"),
            "models": rpc("pool_list_models")}


def compact_catalog(value):
    policy = value["policy"]
    groups = []
    for group in ("low", "medium", "high"):
        members = [model for model in value["models"] if model.get("group") == group]
        groups.append({"group": group, "total": len(members), "members": [
            {key: model.get(key) for key in ("routeId", "id", "enabled", "fixedEffort", "kinds", "executionModes")}
            for model in members[:12]], "omitted": max(0, len(members) - 12)})
    digest = hashlib.sha256(json.dumps(value["models"], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    return {"backend": "cli-agent-pool", "catalog_digest": digest,
            "policy": {key: policy.get(key) for key in ("selectionMode", "concurrency", "taskModes")},
            "pools": groups, "model_count": len(value["models"]), "connection_count": len(value["connections"]),
            "next": "Use agents select --task for admission; --full for omitted catalog details; scan does not prove login or execution"}


def alias(model):
    # Model IDs may exceed Brain's 80-character actor limit; identity stays in registry.
    identity = model["routeId"] + "/" + model["id"]
    return "pool/" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def remember(model, data=None):
    import runtime_agents as A
    persist = data is None
    data = A.load() if persist else data
    key = alias(model)
    data["models"][key] = {"model_id": model["id"], "cli": "cli-agent-pool",
                           "pool_route": model["routeId"], "available": model["enabled"],
                           "roles": ["worker", "lead", "reviewer"], "tiers": ["L", "M", "H"],
                           "efforts": model.get("efforts", [])}
    if persist:
        A.save(data)
    return key


def select(tier="M", role="worker", route="", model="", effort="", group="", mode=None):
    mode = mode or ("response" if role in ("reviewer", "discovery") else "execute")
    if mode not in ("response", "execute"):
        raise ValueError("Pool mode must be response or execute")
    policy = rpc("pool_get_policy")
    if mode not in policy.get("taskModes", []):
        raise ValueError("CLI Agent Pool 1.7+ with response/execute support is required for new dispatch; upgrade Pool, not an existing job request")
    group = group or GROUPS.get(tier, "medium")
    request = {"kind": "write" if mode == "execute" else "read", "mode": mode, "group": group,
               "minRemainingPercent": 25 if role in ("lead", "reviewer") else 10}
    if route:
        request["routeId"] = route
    if model:
        request["modelId"] = model
    if effort and effort != "default":
        request["effort"] = effort
    try:
        result = rpc("pool_select", request)
    except ValueError as exc:
        if "NO_ROUTE" not in str(exc) or policy["selectionMode"] != "auto":
            raise
        # ponytail: owner-unassigned automatic models use Pool's conservative name hints;
        # unknown capability stays unavailable until the owner assigns a strength pool.
        candidates = [m for m in rpc("pool_list_models") if m.get("enabled") and m.get("suggestedGroup") == group
                      and (route or m.get("autoSelect", m.get("billing") != "paid_api"))
                      and (not route or m["routeId"] == route) and (not model or m["id"] == model)
                      and (m.get("billing") != "paid_api" or route or m.get("autoSelect"))]
        result = None
        for candidate in sorted(candidates, key=lambda m: (m.get("billing") == "paid_api", m.get("priority", 100), m["routeId"], m["id"])):
            attempt = dict(request, routeId=candidate["routeId"], modelId=candidate["id"])
            attempt.pop("group")
            try:
                result = rpc("pool_select", attempt)
                request = attempt
                break
            except ValueError as failure:
                if "NO_ROUTE" not in str(failure):
                    raise
        if result is None:
            raise ValueError("No suitable model in %s pool; assign models in CLI Agent Pool" % group)
    chosen = result["selected"]
    # Fixed effort wins. Otherwise pick the task effort only if the CLI supports it.
    requested = chosen.get("fixedEffort") or (None if effort == "default" else effort) or chosen.get("defaultEffort")
    if not requested and effort != "default":
        preferred = {"low": "low", "medium": "medium", "high": "high"}[group]
        requested = preferred if preferred in chosen.get("efforts", []) else None
    request.update(routeId=chosen["routeId"], modelId=chosen["id"])
    if requested:
        request["effort"] = requested
    result.update(request=request, alias=alias(chosen), strength=group)
    return result


def gate(B, task, spec, actor, action, root=None):
    if action == "accept":
        return
    models = rpc("pool_list_models")
    matches = [m for m in models if m["routeId"] == spec["pool_route"] and m["id"] == spec["model_id"]]
    tier = __import__("runtime_agents").score_task(B, None, task)["effective_tier"]
    needed = GROUPS[tier]
    automatic = rpc("pool_get_policy")["selectionMode"] == "auto"
    levels = ["low", "medium", "high"]
    allowed = levels[levels.index(needed):]
    if not any(m.get("enabled") and (m.get("group") in allowed or automatic and m.get("suggestedGroup") in allowed) for m in matches):
        raise ValueError("Pool model no longer meets the task strength/owner policy")
    if action == "start":
        strengths = [m.get("group") for m in matches if m.get("enabled") and m.get("group") in allowed]
        if not strengths and automatic:
            strengths = [m.get("suggestedGroup") for m in matches if m.get("enabled") and m.get("suggestedGroup") in allowed]
        return {"poolStrength": min(strengths, key=levels.index)}
    if action == "review":
        import runtime_agents as A
        implementers = V.implementers(B, task)
        if A.canonical_identity(actor) in {A.canonical_identity(i) for i in implementers}:
            raise ValueError("reviewer must be a different agent/model")
        if root is None:
            raise ValueError("review needs the project root to read the immutable Pool dispatch")
        file = journal_path(root, task["id"])
        entry = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
        records = B.start_records(task)
        worker_groups = [r["strength"] for r in records if r.get("strength")]
        if any(not r.get("strength") for r in records) or not worker_groups:
            raise ValueError("review requires task-bound implementation strength; inspect legacy/mixed-backend work")
        if entry.get("strength"):
            worker_groups.append(entry["strength"])
        reviewer_level = max([levels.index(m["group"]) for m in matches if m.get("enabled") and m.get("group") in levels] +
                             [levels.index(m["suggestedGroup"]) for m in matches if automatic and m.get("enabled") and m.get("suggestedGroup") in levels] + [-1])
        if any(group in levels and reviewer_level < levels.index(group) for group in worker_groups):
            raise ValueError("reviewer strength is below the implementer pool")


def journal_path(root, tid):
    import runtime_agents as A
    key = hashlib.sha256(str(Path(root).resolve()).encode("utf-8")).hexdigest()[:24]
    directory = A.registry_path().parent / "pool-jobs" / key
    for item in [directory] + list(directory.parents):
        if V.is_link(item):
            raise ValueError("linked pool journal path refused")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (tid + ".json")
    if V.is_link(target):
        raise ValueError("linked pool journal refused")
    return target


def get_job(entry):
    arguments = {"taskId": entry["taskId"], "after": 0}
    if entry.get("request", {}).get("mode") in ("response", "execute"):
        arguments["compact"] = True
    return rpc("pool_get_task", arguments)


def print_output(B, root, task, current):
    import runtime_security as S
    report = current.get("report")
    text = json.dumps(report, ensure_ascii=False, separators=(",", ":")) if isinstance(report, dict) else str(current.get("result") or "")
    text = S.sanitize(text)
    limit = 6000 if isinstance(report, dict) else 1500
    if len(text) <= limit:
        print(text)
        return
    log_rel = f".project-brain/.cache/runs/{task['id']}-pool.log"
    log_path = V.public_path(root, log_rel)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    B.write_atomic(log_path, text)
    print(text[:limit] + f"\n[... truncated, full output in {log_rel}]")


def delegate(B, root, task, score, args):
    """Persist one immutable request before send; resume never replays completed work."""
    import runtime_agents as A
    if os.environ.get("CLI_AGENT_POOL_WORKER"):
        raise ValueError("Pool workers cannot delegate recursively")
    if getattr(args, "readback", False):
        import runtime_protocol as R
        import runtime_security as S
        entry = R.read_json(journal_path(root, task["id"]))
        if not isinstance(entry.get("taskId"), str) or not entry["taskId"]:
            raise ValueError("READBACK_FIRST: no acknowledged task ID; resolve the saved idempotency key with Pool, never launch a changed request")
        current = get_job(entry)
        print(S.sanitize(json.dumps({k: current.get(k) for k in ("id", "state", "error")}, ensure_ascii=False)))
        print_output(B, root, task, current)
        print("READBACK ONLY: source/spec were not checked and no work was submitted")
        return 0 if current.get("state") == "succeeded" else 1 if current.get("state") in ACTIVE else 2
    if task["status"] not in ("READY", "IN_PROGRESS") or B.task_errors(task) or score["must_split"]:
        raise ValueError("delegation requires a READY/IN_PROGRESS executable task")
    import runtime_protocol as R
    import runtime_security as S
    R.guard(B, root, task)
    if task.get("secrets", "none") != "none":
        raise ValueError("Secret-bearing work is not sent to Pool; split implementation into secret-free fixtures, then use the approved host check adapter")
    modes = B.get_session_modes(root) if hasattr(B, "get_session_modes") else {"exec": ""}
    exec_mode = modes.get("exec", "")
    if not exec_mode:
        raise ValueError("Select a Pool EXEC mode before delegating to CLI Agent Pool")
    if exec_mode == "solo":
        raise ValueError("session EXEC mode is 'solo' (SOLO); execute directly without delegating")
    if exec_mode in ("self_mixed", "self_and_lower"):
        raise ValueError(f"session EXEC mode is '{exec_mode}'; use native subagents instead of CLI Agent Pool")
    if exec_mode == "pool_low" and score["effective_tier"] != "L":
        raise ValueError("session EXEC mode is 'pool_low' (P-L); only Tier L tasks may be delegated to Pool")
    if exec_mode == "pool_med_low" and score["effective_tier"] == "H":
        raise ValueError("session EXEC mode is 'pool_med_low' (P-ML); only Tier L/M tasks may be delegated to Pool")
    if score["effective_tier"] == "H" and exec_mode != "pool_mixed" and not args.force:
        raise ValueError("Tier H requires the lead; split the task or explicitly pass --force")
    if not 5 <= args.timeout <= 3600:
        raise ValueError("Pool timeout must be 5..3600 seconds")
    wait = getattr(args, "wait", 3600)
    if not 1 <= wait <= 86400:
        raise ValueError("Pool wait must be 1..86400 seconds")
    with B.checkout_lock(root, timeout=0.1, name="delegate.lock"):
        file = journal_path(root, task["id"])
        entry = R.read_json(file) if file.exists() else None
        if entry and (not isinstance(entry.get("contract"), str) or not isinstance(entry.get("actor"), str)
                      or not isinstance(entry.get("request"), dict)):
            raise ValueError("Malformed Pool journal; inspect/read back the existing job before dispatch")
        if entry and entry["contract"] != B.contract(task):
            raise ValueError("task contract changed after dispatch; inspect the existing Pool job before creating another task")
        requested_mode = getattr(args, "mode", None)
        if entry and requested_mode and entry["request"].get("mode") != requested_mode:
            raise ValueError("Existing Pool request is immutable; use --readback to inspect it instead of changing its mode")
        if not entry:
            R.attempt_guard(B, root, task)
            selected = select(score["effective_tier"], role="lead" if score["effective_tier"] == "H" else "worker", route=args.cli, model=args.model,
                              effort=args.effort, group=args.group, mode=requested_mode or modes.get("task_mode", "execute"))
            print("POOL_SELECT " + json.dumps({k: selected[k] for k in ("alias", "strength", "request")}, ensure_ascii=False))
            if args.dry_run:
                return 0
            actor = remember(selected["selected"])
            if selected["request"]["mode"] == "execute" and task.get("owner") and task["owner"] != actor:
                raise ValueError("task is owned by another model; explicit takeover required")
            if selected["request"]["mode"] == "execute":
                rc = B.cmd_start(root, task["id"], agent=actor)
                if rc:
                    return rc
            task = B.find_task(root, task["id"])
            instruction = ("\nPool execute protocol takes precedence for the final response: return the required single JSON report with all changed paths, actual checks, research sources and blockers. Do not commit or publish."
                           if selected["request"]["mode"] == "execute" else
                           "\nRESPONSE ONLY: inspect and return analysis/research with paths, sources and blockers. Do not modify files, run PB check/progress, implement the task or claim completion. The director decides the next action.")
            request = dict(selected["request"], prompt=A.build_worker_prompt(B, root, task, score) + instruction +
                           "\nYou are a Pool worker. Do not delegate or submit nested tasks.",
                           workspace=str(Path(root).resolve()), timeoutSeconds=args.timeout,
                           idempotencyKey="pb-" + str(uuid.uuid4()))
            entry = {"contract": B.contract(task), "actor": actor, "strength": selected["strength"], "request": request}
            B.write_atomic(file, json.dumps(entry, ensure_ascii=False))
        if args.dry_run:
            print("POOL_RESUME " + str(entry.get("taskId", "response_unknown")))
            return 0
        if R.enabled(B, root) and entry.get("verified") and not args.dry_run:
            value, _ = V.task_digest(B, root, task)
            receipt = entry["verified"]
            live_task = B.find_task(root, task["id"])
            if (B.contract(live_task) == B.contract(task) and isinstance(receipt, dict) and receipt.get("digest") == value
                    and receipt.get("contract") == B.contract(task)
                    and receipt.get("taskId") == entry.get("taskId")
                    and V.current_checks(B, root, live_task, value, B.contract(task))):
                print("PASS CACHED: completed Pool job and intact current verification; no RPC or commands repeated")
                return 0
        if not entry.get("taskId"):
            # Same key + exact request recovers a lost acknowledgement safely.
            submitted = rpc("pool_submit", entry["request"])
            entry["taskId"] = submitted["id"]
            B.write_atomic(file, json.dumps(entry, ensure_ascii=False))
        print("POOL_TASK " + entry["taskId"])
        deadline = time.monotonic() + wait
        while True:
            current = get_job(entry)
            if current["state"] not in ACTIVE:
                break
            if current.get("queueReason") == "WORKSPACE_REVIEW_REQUIRED":
                print("READBACK_FIRST: blocked by Pool review task " + str(current.get("blockedBy") or "unknown") + "; no replay or automatic quarantine clearing")
                return 2
            if time.monotonic() >= deadline:
                print("READBACK_FIRST: task still active; rerun delegate to resume polling without replay")
                return 2
            time.sleep(1)
        print("POOL_RESULT " + S.sanitize(json.dumps({k: current.get(k) for k in ("id", "state", "modelId", "reportedModel", "effort", "error")}, ensure_ascii=False)))
        print_output(B, root, task, current)
        if current["state"] != "succeeded":
            print("READBACK_FIRST: inspect the failed/interrupted job; no automatic retry")
            return 2
        mode = entry["request"].get("mode")
        if mode == "response":
            print("RESPONSE_ONLY: no implementation verification or task acceptance inferred")
            return 0
        if mode == "execute" and (not isinstance(current.get("report"), dict) or current["report"].get("status") != "completed"):
            print("READBACK_FIRST: missing completed execution report; inspect the existing job, never replay")
            return 2
        with B.checkout_lock(root):
            rc, lines = V.check(B, root, task["id"], timeout=args.timeout, actor=entry["actor"])
        for line in lines:
            print(line)
        if rc == 0 and R.enabled(B, root):
            current_task = B.find_task(root, task["id"])
            entry["verified"] = {"taskId": entry["taskId"], "digest": V.task_digest(B, root, current_task)[0], "contract": B.contract(current_task)}
            B.write_atomic(file, json.dumps(entry, ensure_ascii=False))
        return rc


def agents(B, args):
    modes = B.get_session_modes(Path(args.root).resolve())
    if not any(modes.get(role, "").startswith("pool_") for role in ("exec", "rev")):
        raise ValueError("Select a Pool EXEC or REV mode before connecting to CLI Agent Pool")
    sub = args.agents_cmd
    if sub == "select":
        tier = (args.tier or ("H" if args.role in ("lead", "reviewer") else "M")).upper()
        if args.task:
            task = B.find_task(Path(args.root).resolve(), args.task)
            if not task:
                raise ValueError("task not found")
            tier = A_score(B, args.root, task)["effective_tier"]
        role_mode = modes.get("rev" if args.role == "reviewer" else "exec", "")
        limit = {"pool_mixed": "H", "pool_med_low": "M", "pool_low": "L"}.get(role_mode)
        if not limit or B.TIER_VALUES.index(tier) > B.TIER_VALUES.index(limit):
            raise ValueError("No eligible Pool role/tier within the selected session mode; retain quality floors")
        if args.exclude:
            raise ValueError("--exclude is available with --backend direct; use Pool owner membership to exclude models")
        task_mode = getattr(args, "mode", None) or ("response" if args.role in ("reviewer", "discovery") else modes.get("task_mode", "execute"))
        value = select(tier, args.role, route=args.cli, mode=task_mode)
        remember(value["selected"])
    else:
        value = status()
        if sub == "quota":
            value["quotas"] = {}
            for route in value["connections"]:
                try:
                    value["quotas"][route["id"]] = rpc("pool_get_quotas", {"routeId": route["id"]})
                except ValueError as exc:
                    value["quotas"][route["id"]] = {"status": "unknown", "error": str(exc)}
        import runtime_agents as A
        data = A.load()
        for model in value["models"]:
            remember(model, data)
        A.save(data)
    if sub in ("scan", "list") and not getattr(args, "full", False):
        value = compact_catalog(value)
    print(json.dumps(value, indent=2 if getattr(args, "full", False) else None, ensure_ascii=False))
    return 0


def A_score(B, root, task):
    import runtime_agents as A
    return A.score_task(B, Path(root).resolve(), task)
