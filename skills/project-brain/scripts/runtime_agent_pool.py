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
    if response.returncode or isinstance(value, dict) and value.get("error"):
        error = value.get("error", {}) if isinstance(value, dict) else {}
        raise ValueError("Pool %s: %s" % (error.get("code", response.returncode), error.get("message", "request failed")))
    return value


def status():
    return {"backend": "cli-agent-pool", "policy": rpc("pool_get_policy"),
            "pools": rpc("pool_list_pools"), "connections": rpc("pool_list_connections"),
            "models": rpc("pool_list_models")}


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


def select(tier="M", role="worker", route="", model="", effort="", group=""):
    group = group or GROUPS.get(tier, "medium")
    request = {"kind": "write", "group": group,
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
        if "NO_ROUTE" not in str(exc) or rpc("pool_get_policy")["selectionMode"] != "auto":
            raise
        # ponytail: owner-unassigned automatic models use Pool's conservative name hints;
        # unknown capability stays unavailable until the owner assigns a strength pool.
        candidates = [m for m in rpc("pool_list_models") if m.get("enabled") and m.get("suggestedGroup") == group
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


def delegate(B, root, task, score, args):
    """Persist one immutable request before send; resume never replays completed work."""
    import runtime_agents as A
    if os.environ.get("CLI_AGENT_POOL_WORKER"):
        raise ValueError("Pool workers cannot delegate recursively")
    if task["status"] not in ("READY", "IN_PROGRESS") or B.task_errors(task) or score["must_split"]:
        raise ValueError("delegation requires a READY/IN_PROGRESS executable task")
    if score["effective_tier"] == "H" and not args.force:
        raise ValueError("Tier H requires the lead; split the task or explicitly pass --force")
    if not 5 <= args.timeout <= 3600:
        raise ValueError("Pool timeout must be 5..3600 seconds")
    with B.checkout_lock(root, timeout=0.1, name="delegate.lock"):
        file = journal_path(root, task["id"])
        entry = json.loads(file.read_text(encoding="utf-8")) if file.exists() else None
        if entry and entry["contract"] != B.contract(task):
            raise ValueError("task contract changed after dispatch; inspect the existing Pool job before creating another task")
        if not entry:
            selected = select(score["effective_tier"], role="lead" if score["effective_tier"] == "H" else "worker", route=args.cli, model=args.model,
                              effort=args.effort, group=args.group)
            print("POOL_SELECT " + json.dumps({k: selected[k] for k in ("alias", "strength", "request")}, ensure_ascii=False))
            if args.dry_run:
                return 0
            actor = remember(selected["selected"])
            if task.get("owner") and task["owner"] != actor:
                raise ValueError("task is owned by another model; explicit takeover required")
            rc = B.cmd_start(root, task["id"], agent=actor)
            if rc:
                return rc
            task = B.find_task(root, task["id"])
            request = dict(selected["request"], prompt=A.build_worker_prompt(B, root, task, score) +
                           "\nYou are a Pool worker. Do not delegate or submit nested tasks.",
                           workspace=str(Path(root).resolve()), kind="write", timeoutSeconds=args.timeout,
                           idempotencyKey="pb-" + str(uuid.uuid4()))
            entry = {"contract": B.contract(task), "actor": actor, "strength": selected["strength"], "request": request}
            B.write_atomic(file, json.dumps(entry, ensure_ascii=False))
        if args.dry_run:
            print("POOL_RESUME " + str(entry.get("taskId", "response_unknown")))
            return 0
        if not entry.get("taskId"):
            # Same key + exact request recovers a lost acknowledgement safely.
            submitted = rpc("pool_submit", entry["request"])
            entry["taskId"] = submitted["id"]
            B.write_atomic(file, json.dumps(entry, ensure_ascii=False))
        print("POOL_TASK " + entry["taskId"])
        deadline = time.monotonic() + args.timeout + 15
        while True:
            current = rpc("pool_get_task", {"taskId": entry["taskId"], "after": 0})
            if current["state"] not in ACTIVE:
                break
            if time.monotonic() >= deadline:
                print("READBACK_FIRST: task still active; rerun delegate to resume polling without replay")
                return 2
            time.sleep(1)
        print("POOL_RESULT " + json.dumps({k: current.get(k) for k in ("id", "state", "modelId", "reportedModel", "effort", "error")}, ensure_ascii=False))
        print(str(current.get("result") or "")[:20000])
        if current["state"] != "succeeded":
            print("READBACK_FIRST: inspect the failed/interrupted job; no automatic retry")
            return 2
        with B.checkout_lock(root):
            rc, lines = V.check(B, root, task["id"], timeout=args.timeout, actor=entry["actor"])
        for line in lines:
            print(line)
        return rc


def agents(B, args):
    sub = args.agents_cmd
    if sub == "select":
        tier = (args.tier or ("H" if args.role in ("lead", "reviewer") else "M")).upper()
        if args.task:
            task = B.find_task(Path(args.root).resolve(), args.task)
            if not task:
                raise ValueError("task not found")
            tier = A_score(B, args.root, task)["effective_tier"]
        if args.exclude:
            raise ValueError("--exclude is available with --backend direct; use Pool owner membership to exclude models")
        value = select(tier, args.role, route=args.cli)
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
    print(json.dumps(value, indent=2, ensure_ascii=False))
    return 0


def A_score(B, root, task):
    import runtime_agents as A
    return A.score_task(B, Path(root).resolve(), task)
