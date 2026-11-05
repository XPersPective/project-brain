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
    # CAP's scoped lease is transport authority, not a provider credential.
    # Preserve it so linked workers and director successors retain their role;
    # the service validates the lease and enforces owner-only operations.
    if os.environ.get("CLI_AGENT_POOL_TASK_TOKEN"):
        env["CLI_AGENT_POOL_TASK_TOKEN"] = os.environ["CLI_AGENT_POOL_TASK_TOKEN"]
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


def status(policy=None):
    return {"backend": "cli-agent-pool", "policy": policy if policy is not None else rpc("pool_get_policy"),
            "pools": rpc("pool_list_pools"), "connections": rpc("pool_list_connections"),
            "models": rpc("pool_list_models")}


def modern(policy):
    return isinstance(policy, dict) and isinstance(policy.get("entries"), dict) and "run" in policy


def normalize_model(model):
    """Map compact CAP metadata onto the stable Brain registry vocabulary."""
    value = dict(model)
    if "id" not in value and "modelId" in value:
        value["id"] = value["modelId"]
    if "group" not in value and "category" in value:
        value["group"] = value["category"]
    if "defaultEffort" not in value and "effort" in value:
        value["defaultEffort"] = value["effort"]
    if "enabled" not in value:
        value["enabled"] = not value.get("disabled", False)
    if value.get("disabled") or value.get("hidden"):
        value["enabled"] = False
    return value


def alternatives_count(value):
    alternatives = value.get("alternatives", [])
    return alternatives if isinstance(alternatives, int) else len(alternatives)


def modern_status(policy=None, full=False):
    policy = policy if policy is not None else rpc("pool_get_policy")
    pools = rpc("pool_list_pools")
    catalog = rpc("pool_catalog", {"view": "models", "limit": 12} if full else {})
    return {"backend": "cli-agent-pool", "policy": policy, "pools": pools,
            "catalog": catalog, "models": [], "connections": []}


def compact_catalog(value):
    if value.get("catalog") is not None:
        return {"backend": "cli-agent-pool", "policy": value["policy"],
                "pools": value["pools"], "catalog": value["catalog"],
                "next": "Use agents select --task for admission; catalog is a summary, not a login or execution check"}
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
    if model.get("pool_effort"):
        data["models"][key]["pool_effort"] = model["pool_effort"]
    if model.get("pool_category"):
        data["models"][key]["pool_category"] = model["pool_category"]
    if persist:
        A.register_model(key, data["models"][key])
    return key


def select(tier="M", role="worker", route="", model="", effort="", group="", mode=None):
    mode = mode or ("response" if role in ("reviewer", "discovery") else "execute")
    if mode not in ("response", "execute"):
        raise ValueError("Pool mode must be response or execute")
    policy = rpc("pool_get_policy")
    is_modern = modern(policy)
    if not is_modern and mode not in policy.get("taskModes", []):
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
        if is_modern or "NO_ROUTE" not in str(exc) or policy.get("selectionMode") != "auto":
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
    chosen = normalize_model(result["selected"])
    result["selected"] = chosen
    # Fixed effort wins. Otherwise pick the task effort only if the CLI supports it.
    explicit_supported = effort not in ("", "default") and effort in chosen.get("efforts", [])
    if is_modern:
        requested = effort if explicit_supported else chosen.get("defaultEffort")
    else:
        requested = chosen.get("fixedEffort") or (None if effort == "default" else effort) or chosen.get("defaultEffort")
    if requested and chosen.get("efforts") and requested not in chosen["efforts"]:
        if chosen.get("fixedEffort"):
            raise ValueError("Pool returned an unsupported fixed effort")
        requested = None
    if not requested and effort != "default":
        preferred = {"low": "low", "medium": "medium", "high": "high"}[group]
        requested = preferred if preferred in chosen.get("efforts", []) else None
    supported_efforts = chosen.get("efforts", []) if is_modern else chosen.get("efforts", [effort])
    if effort not in ("", "default") and effort not in supported_efforts and (is_modern or not chosen.get("fixedEffort")):
        raise ValueError("Requested effort is not supported by the selected Pool model")
    request.update(routeId=chosen["routeId"], modelId=chosen["id"])
    if requested:
        request["effort"] = requested
    result.update(request=request, alias=alias(chosen), strength=group)
    return result


QUALIFICATION_LIMIT = 65536
QUALITY_LEVELS = ("low", "medium", "high")
QUALITY_TIERS = {"L": "low", "M": "medium", "H": "high"}


def _qualification_path(B, root):
    return V.public_path(root, B.BRAIN_DIR + "/.cache/model-qualifications.json")


def _qualification_rows(B, root):
    path = _qualification_path(B, root)
    if not path.exists():
        return []
    with path.open("rb") as stream:
        raw = stream.read(QUALIFICATION_LIMIT + 1)
    if len(raw) > QUALIFICATION_LIMIT:
        raise ValueError("Malformed model qualification registry: exceeds 64 KiB")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Malformed model qualification registry") from exc
    if (not isinstance(value, dict) or set(value) != {"schema", "models"}
            or type(value.get("schema")) is not int or value["schema"] != 1
            or not isinstance(value.get("models"), list) or len(value["models"]) > 128):
        raise ValueError("Malformed model qualification registry")
    seen = set()
    for row in value["models"]:
        if (not isinstance(row, dict) or set(row) != {"routeId", "modelId", "tier", "note"}
                or not all(isinstance(row.get(k), str) and row[k] and row[k] == row[k].strip()
                           and len(row[k]) <= limit and not any(ord(c) < 32 for c in row[k])
                           for k, limit in (("routeId", 256), ("modelId", 256), ("note", 512)))
                or row.get("tier") not in ("L", "M", "H")):
            raise ValueError("Malformed model qualification registry")
        key = (row["routeId"], row["modelId"])
        if key in seen:
            raise ValueError("Malformed model qualification registry: duplicate model")
        seen.add(key)
    return value["models"]


def qualify(B, root, route, model, tier, note):
    """Store a bounded director fit assessment; this is not verification evidence."""
    import runtime_security as S
    if not B.brain_exists(root):
        raise ValueError("Initialize Brain before qualifying a Pool model")
    for label, value, limit in (("route", route, 256), ("model", model, 256), ("note", note, 512)):
        if (not isinstance(value, str) or not value or value != value.strip()
                or len(value) > limit or any(ord(ch) < 32 for ch in value)):
            raise ValueError("Model qualification requires exact IDs and a clean nonempty note")
        S.require_clean(value, "model qualification " + label)
    if tier not in ("L", "M", "H"):
        raise ValueError("Model qualification tier must be L, M, or H")
    rows = _qualification_rows(B, root)
    key = (route, model)
    row = {"routeId": route, "modelId": model, "tier": tier, "note": note}
    replaced = False
    for index, old in enumerate(rows):
        if (old["routeId"], old["modelId"]) == key:
            rows[index] = row
            replaced = True
            break
    if not replaced:
        if len(rows) >= 128:
            raise ValueError("Model qualification registry is full")
        rows.append(row)
    payload = json.dumps({"schema": 1, "models": rows}, ensure_ascii=False, indent=2)
    if len((payload + "\n").encode("utf-8")) > QUALIFICATION_LIMIT:
        raise ValueError("Model qualification registry exceeds 64 KiB")
    B.write_atomic(_qualification_path(B, root), payload)
    return row


def model_qualification(B, root, route, model):
    for row in _qualification_rows(B, root):
        if row["routeId"] == route and row["modelId"] == model:
            return row["tier"]
    return None


def _candidate_rows(source, selector, kind):
    found = {}
    if source == "cap-pinned":
        for pin in selector["models"]:
            for row in targeted_models(pin["routeId"], pin["modelId"]):
                found[(row["routeId"], row["id"])] = row
        return list(found.values())
    if "categories" in selector:  # cap-category, or mixed bounded to categories
        queries = [("pool_list_pools", {"group": category, "limit": 12, "offset": 0}, category)
                   for category in selector["categories"]]
    else:
        queries = [("pool_catalog", {"view": "models", "kind": kind, "limit": 12, "offset": 0}, None)]
    pages_left = 8
    for tool, initial, category in queries:
        offset = 0
        complete = False
        while pages_left:
            pages_left -= 1
            page = rpc(tool, dict(initial, offset=offset))
            if not isinstance(page, dict):
                raise ValueError("Malformed Pool catalog page; routing is blocked")
            rows = page.get("models", page.get("items", page.get("entries", [])))
            if not isinstance(rows, list):
                raise ValueError("Malformed Pool catalog models; routing is blocked")
            for raw in rows:
                item = normalize_model(raw)
                if category is not None:
                    memberships = raw.get("categories", [])
                    if not isinstance(memberships, list):
                        continue
                    if category not in memberships and raw.get("category") != category:
                        continue
                    item["categories"] = memberships
                    item["selectedCategory"] = category
                found[(item.get("routeId"), item.get("id"))] = item
            next_offset = page.get("nextOffset")
            if next_offset is None:
                complete = True
                break
            if type(next_offset) is not int or next_offset <= offset:
                break
            offset = next_offset
        if not complete:
            raise ValueError("Pool metadata page limit reached; cannot prove eligible model choices")
    return list(found.values())


def select_policy(B, root, tier="M", role="worker", route="", model="", effort="", group="", mode=None):
    """Select locally from the confirmed ESP allowlist; never ask Pool to route around it."""
    import runtime_executor_policy as E
    selector = E.guard(B, root, role, "pool")
    if selector is None:
        return select(tier, role, route=route, model=model, effort=effort, group=group, mode=mode)
    source = selector["source"]
    task_tier = tier.upper() if tier.upper() in QUALITY_TIERS else "M"
    quality_needed = QUALITY_LEVELS.index(QUALITY_TIERS[task_tier])
    selected_effort = effort if effort not in ("", "default") else None
    bounds = selector.get("effort", {})
    if selected_effort is None and bounds.get("selector") == "user":
        selected_effort = bounds["value"]
    capped = "categories" in selector
    category = group if capped and group else None
    if capped and category and category not in selector["categories"]:
        raise ValueError("Category is outside saved executor bounds")
    E.guard(B, root, role, "pool", category=category, effort=selected_effort)
    mode = mode or ("response" if role in ("reviewer", "discovery") else "execute")
    if mode not in ("response", "execute"):
        raise ValueError("Pool mode must be response or execute")
    kind = "write" if mode == "execute" else "read"
    rows = _candidate_rows(source, selector, kind)
    pins = {(p["routeId"], p["modelId"]) for p in selector.get("models", [])}
    candidates = []
    for row in rows:
        row = normalize_model(row)
        identity = (row.get("routeId"), row.get("id"))
        if not all(isinstance(v, str) and v for v in identity):
            continue
        if route and identity[0] != route or model and identity[1] != model:
            continue
        if source == "cap-pinned" and identity not in pins:
            continue
        if row.get("enabled") is not True or row.get("hidden") or row.get("removed"):
            continue
        if row.get("billing") == "paid_api" and source != "cap-pinned":
            continue
        if kind not in row.get("kinds", []):
            continue
        qualification = model_qualification(B, root, *identity)
        if qualification is None or QUALITY_LEVELS.index(QUALITY_TIERS[qualification]) < quality_needed:
            continue
        memberships = row.get("categories", [])
        actual_category = row.get("selectedCategory") if capped else None
        if capped and (not actual_category or actual_category not in selector["categories"]
                                          or actual_category not in memberships):
            continue
        supported = row.get("efforts", [])
        effective_effort = selected_effort
        if effective_effort is None:
            default = row.get("defaultEffort")
            if bounds.get("selector") == "default":
                effective_effort = default
            elif bounds.get("allowed"):
                effective_effort = default if default in bounds["allowed"] else next(
                    (item for item in bounds["allowed"] if item in supported), None)
            else:
                effective_effort = default
        if effective_effort is not None and effective_effort not in supported:
            continue
        actual = dict(row, effort=effective_effort)
        try:
            E.guard(B, root, role, "pool", model=actual,
                    category=actual_category, effort=effective_effort)
        except ValueError:
            continue
        candidates.append((actual, qualification, actual_category))
    if not candidates:
        ids = sorted({row.get("routeId", "") + "/" + row.get("id", "") for row in rows})[:12]
        raise ValueError("MODEL_QUALIFICATION_REQUIRED or no eligible ESP candidate; qualify a suitable exact model. Candidates: " + ", ".join(ids))
    chosen, qualification, actual_category = sorted(candidates, key=lambda item: (item[0]["routeId"], item[0]["id"]))[0]
    import runtime_relay as RL
    # While relay circulation is on, workers also need quota above the relay threshold.
    reserve = max(25 if role in ("lead", "reviewer") else 10, RL.worker_reserve(B, root, E.load(B, root)))
    request = {"kind": kind, "mode": mode, "routeId": chosen["routeId"], "modelId": chosen["id"],
               "minRemainingPercent": reserve}
    if actual_category is not None:
        request["group"] = actual_category
    if chosen.get("effort") is not None:
        request["effort"] = chosen["effort"]
    chosen["pool_effort"] = chosen.get("effort")
    chosen["pool_category"] = actual_category
    chosen["category"] = actual_category
    return {"selected": chosen, "request": request, "alternatives": len(candidates),
            "alias": alias(chosen), "strength": QUALITY_TIERS[qualification]}


def targeted_models(route, model_id):
    """Read a bounded, exact model lookup without enumerating the provider catalog."""
    rows = []
    offset = 0
    complete = False
    for _ in range(4):
        page = rpc("pool_catalog", {"view": "models", "query": model_id,
                                    "routeId": route, "limit": 12, "offset": offset})
        if not isinstance(page, dict) or not isinstance(page.get("models"), list):
            raise ValueError("Malformed Pool catalog page; cannot prove model suitability")
        models = page["models"]
        for raw in models:
            item = normalize_model(raw)
            if item.get("routeId") != route or item.get("id") != model_id:
                continue
            cats = raw.get("categories")
            if isinstance(cats, list):
                if cats:
                    rows.extend(dict(item, group=category) for category in cats)
                else:
                    rows.append(item)
            else:
                rows.append(item)
        next_offset = page.get("nextOffset")
        if next_offset is None:
            complete = True
            break
        if not isinstance(next_offset, int) or next_offset <= offset:
            break
        offset = next_offset
    if not complete:
        raise ValueError("Pool targeted catalog lookup is incomplete; cannot prove model suitability")
    return rows


def gate(B, task, spec, actor, action, root=None):
    if action == "accept":
        return
    import runtime_executor_policy as E
    saved = E.load(B, root) if root is not None else None
    if saved is not None:
        role = "reviewer" if action == "review" else "worker"
        matches = targeted_models(spec["pool_route"], spec["model_id"])
        live = next((m for m in matches if m.get("enabled") is True and not m.get("hidden") and not m.get("removed")), None)
        if live is None:
            raise ValueError("Pool model is unavailable or no longer visible")
        file = journal_path(root, task["id"]) if action == "review" else None
        entry = json.loads(file.read_text(encoding="utf-8")) if file is not None and file.exists() else {}
        category = spec.get("pool_category") or (entry.get("request") or {}).get("group")
        effort = spec.get("pool_effort") or (entry.get("request") or {}).get("effort") or live.get("defaultEffort")
        live["effort"] = effort
        E.guard(B, root, role, "pool", model=live,
                category=category if "categories" in saved["execution"] or "categories" in saved["review"] else None,
                effort=effort)
        tier = __import__("runtime_agents").score_task(B, None, task)["effective_tier"]
        needed = GROUPS[tier]
        levels = ["low", "medium", "high"]
        qualification = model_qualification(B, root, spec["pool_route"], spec["model_id"])
        if qualification is None:
            raise ValueError("MODEL_QUALIFICATION_REQUIRED: qualify this exact model before use")
        strength = QUALITY_TIERS[qualification]
        if action == "start":
            if levels.index(strength) < levels.index(needed):
                raise ValueError("Pool model qualification is below the task strength floor")
            import runtime_runs as runs
            bound = runs.implementation_strength(B, root, task["id"], actor)
            if bound and levels.index(bound) > levels.index(strength):
                strength = bound
            return {"poolStrength": strength}
        if action == "review":
            import runtime_agents as A
            implementers = V.implementers(B, task)
            if A.canonical_identity(actor) in {A.canonical_identity(i) for i in implementers}:
                raise ValueError("reviewer must be a different agent/model")
            records = B.start_records(task)
            worker_groups = [r["strength"] for r in records if r.get("strength")]
            if any(not r.get("strength") for r in records) or not worker_groups:
                raise ValueError("review requires task-bound implementation strength; inspect legacy/mixed-backend work")
            if entry.get("strength"):
                worker_groups.append(entry["strength"])
            if any(group in levels and levels.index(strength) < levels.index(group) for group in worker_groups):
                raise ValueError("reviewer strength is below the implementer pool")
            return
    policy = rpc("pool_get_policy")
    is_modern = modern(policy)
    if is_modern:
        matches = targeted_models(spec["pool_route"], spec["model_id"])
    else:
        models = rpc("pool_list_models")
        matches = [normalize_model(m) for m in models if m["routeId"] == spec["pool_route"] and m["id"] == spec["model_id"]]
    tier = __import__("runtime_agents").score_task(B, None, task)["effective_tier"]
    needed = GROUPS[tier]
    automatic = policy.get("selectionMode") == "auto"
    levels = ["low", "medium", "high"]
    allowed = levels[levels.index(needed):]
    if not any(m.get("enabled") and (m.get("group") in allowed or automatic and m.get("suggestedGroup") in allowed) for m in matches):
        raise ValueError("Pool model no longer meets the task strength/owner policy")
    if action == "start":
        strengths = [m.get("group") for m in matches if m.get("enabled") and m.get("group") in allowed]
        if not strengths and automatic:
            strengths = [m.get("suggestedGroup") for m in matches if m.get("enabled") and m.get("suggestedGroup") in allowed]
        strength = min(strengths, key=levels.index)
        if root is not None:
            import runtime_runs as runs
            bound = runs.implementation_strength(B, root, task["id"], actor)
            if bound and levels.index(bound) > levels.index(strength):
                strength = bound
        return {"poolStrength": strength}
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
    import runtime_relay as RL
    if os.environ.get("CLI_AGENT_POOL_WORKER") and not RL.authorized(B, root):
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
            B.require_session(root, implementation=(requested_mode or modes.get("task_mode", "execute")) == "execute")
            import runtime_executor_policy as E
            if E.load(B, root) is not None:
                raise ValueError("Saved ESP/SP workers require runs prepare/submit for shared capacity enforcement; legacy delegate is readback-only")
            R.attempt_guard(B, root, task)
            selected = select_policy(B, root, score["effective_tier"], role="lead" if score["effective_tier"] == "H" else "worker", route=args.cli, model=args.model,
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
        tier = (args.tier or ("L" if args.role == "discovery" else "H" if args.role in ("lead", "reviewer") else "M")).upper()
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
        value = select_policy(B, args.root, tier, args.role, route=args.cli, mode=task_mode)
        remember(value["selected"])
    else:
        policy = rpc("pool_get_policy")
        value = modern_status(policy, full=getattr(args, "full", False)) if modern(policy) else status(policy)
        if sub == "quota":
            value["quotas"] = {}
            if modern(policy):
                value["quota_note"] = "Use the Pool quota command for a targeted route; no provider-wide quota fan-out was performed"
            else:
                for route in value["connections"]:
                    try:
                        value["quotas"][route["id"]] = rpc("pool_get_quotas", {"routeId": route["id"]})
                    except ValueError as exc:
                        value["quotas"][route["id"]] = {"status": "unknown", "error": str(exc)}
        import runtime_agents as A
        data = A.load()
        for model in value.get("models", []):
            remember(model, data)
        A.save(data)
    if sub in ("scan", "list") and not getattr(args, "full", False):
        value = compact_catalog(value)
    elif sub == "select" and not getattr(args, "full", False):
        value = {"alias": value.get("alias"), "strength": value.get("strength"),
                 "request": value.get("request"),
                 "selected": {key: value["selected"].get(key) for key in
                              ("id", "routeId", "group", "fixedEffort")},
                 "alternatives_count": alternatives_count(value),
                 "next": "--full for candidate details; selection does not submit work"}
    print(json.dumps(value, indent=2 if getattr(args, "full", False) else None, ensure_ascii=False))
    return 0


def A_score(B, root, task):
    import runtime_agents as A
    return A.score_task(B, Path(root).resolve(), task)
