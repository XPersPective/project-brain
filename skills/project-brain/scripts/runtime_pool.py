"""Explicit, project-scoped model pool approval and bounded job accounting."""
import hashlib
import json
import math
import os
from pathlib import Path
import uuid
from datetime import datetime, timezone


ROLES = {"lead", "worker", "reviewer", "discovery"}
EFFORTS = {"low", "medium", "high", "xhigh", "default"}
BILLING = {"subscription", "free", "local", "api"}
MAX_ATTEMPTS = 200
QUOTA_FRESH_SECONDS = 300


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _path(root, registry=None):
    import runtime_agents as A
    project = str(Path(root).resolve())
    key = hashlib.sha256(os.path.normcase(project).encode("utf-8")).hexdigest()[:16]
    return A.registry_path(registry).parent / "sessions" / (key + ".json")


def session_file(root, registry=None):
    path = _path(root, registry)
    for parent in path.parents:
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError("linked session path refused")
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise ValueError("linked session file refused")
    return path


def _read(root, registry=None):
    path = session_file(root, registry)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("invalid pool session data") from exc
    if not isinstance(value, dict) or type(value.get("schema")) is not int or value["schema"] != 1:
        raise ValueError("invalid pool session schema")
    if value.get("project") != str(Path(root).resolve()) or not isinstance(value.get("session_id"), str):
        raise ValueError("pool session project or ID mismatch")
    if value.get("status") not in ("PROPOSED", "APPROVED", "REVOKED"):
        raise ValueError("invalid pool session status")
    if not isinstance(value.get("inventory_digest"), str) or len(value["inventory_digest"]) != 64:
        raise ValueError("invalid pool inventory digest")
    if not isinstance(value.get("selection"), dict) or not isinstance(value.get("jobs"), dict):
        raise ValueError("invalid pool session contents")
    try:
        uuid.UUID(value["session_id"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("invalid pool session ID") from exc
    if not isinstance(value.get("inventory"), dict) or not isinstance(value["inventory"].get("models", {}), dict) or not isinstance(value["inventory"].get("cli_agents", {}), dict):
        raise ValueError("invalid pool inventory")
    if len(value["jobs"]) > MAX_ATTEMPTS or any(
        not isinstance(jid, str) or not isinstance(j, dict) or not isinstance(j.get("alias"), str) or
        j.get("state") not in ("reserved", "running", "response_unknown", "completed", "failed")
        for jid, j in value["jobs"].items()
    ):
        raise ValueError("invalid pool job data")
    selection = value["selection"]
    if selection and (not isinstance(selection.get("models"), dict) or not isinstance(selection.get("exclude", []), list)):
        raise ValueError("invalid pool selection")
    if any(not isinstance(x, str) for x in selection.get("exclude", [])):
        raise ValueError("invalid pool exclusions")
    for alias, choice in (selection.get("models") or {}).items():
        if (not isinstance(alias, str) or not isinstance(choice, dict) or
                not isinstance(choice.get("roles"), list) or not choice["roles"] or
                any(not isinstance(x, str) or x not in ROLES for x in choice["roles"]) or
                not isinstance(choice.get("efforts"), list) or not choice["efforts"] or
                any(not isinstance(x, str) or x not in EFFORTS for x in choice["efforts"]) or
                not isinstance(choice.get("billing"), str) or choice["billing"] not in BILLING or
                ("max_jobs" in choice and (type(choice["max_jobs"]) is not int or choice["max_jobs"] < 1)) or
                ("allow_paid" in choice and type(choice["allow_paid"]) is not bool)):
            raise ValueError("invalid approved pool choice")
    raw = json.dumps(value, ensure_ascii=False).lower()
    if any(word in raw for word in ("access_token", "refresh_token", "client_secret", "api_key", "password")):
        raise ValueError("credential-like data refused in pool session")
    return value


def load_session(root, registry=None):
    return _read(root, registry)


def _safe_metadata(value):
    """Keep small scalar metadata only; never persist arbitrary catalog/log fields."""
    if not isinstance(value, dict):
        return {}
    allowed = ("id", "description", "model_id", "cli", "pool", "adapter", "efforts", "roles", "tiers", "available",
               "authenticated", "billing", "remaining_pct", "primary_5h_remaining_pct",
               "weekly_7d_remaining_pct", "resets_at", "updated_at", "binary", "version",
               "generic_worker_argv", "worker_argv", "prompt_stdin", "catalog_argv", "auth_source", "access_source")
    out = {}
    for key in allowed:
        item = value.get(key)
        if isinstance(item, (str, bool, int, float)) or item is None:
            out[key] = item
        elif isinstance(item, list) and len(item) <= 12 and all(isinstance(x, str) for x in item):
            out[key] = item
    return out


def _config(data, selection=None):
    models = data.get("models") or {}
    clis = data.get("cli_agents") or {}
    pools = data.get("pools") or {}
    aliases = sorted((selection or {}).get("models", models))
    rows = {}
    for alias in aliases:
        spec = models.get(alias)
        if not isinstance(spec, dict):
            continue
        cli = spec.get("cli")
        selected = (selection or {}).get("models", {}).get(alias) or {}
        cli_fields = ("binary", "adapter", "generic_worker_argv", "worker_argv", "prompt_stdin", "catalog_argv", "auth_source", "access_source", "billing", "billing_source")
        rows[alias] = {"model_id": spec.get("model_id"), "cli": cli,
                       "cli_config": {k: _execution_value(clis.get(cli, {}).get(k)) for k in cli_fields}
                       if isinstance(clis.get(cli), dict) else {},
                       "model_adapter": _execution_value(spec.get("adapter")),
                       "execution_config": _execution_value(spec.get("execution_config")),
                       "auth_source": _execution_value(spec.get("auth_source")),
                       "access_source": _execution_value(spec.get("access_source")),
                       "pool": spec.get("pool"), "roles": selected.get("roles", spec.get("roles")),
                       "efforts": selected.get("efforts", spec.get("efforts")),
                       "registry_billing": spec.get("billing"), "billing": selected.get("billing")}
        if spec.get("pool") in pools:
            rows[alias]["pool_config"] = {k: pools[spec["pool"]].get(k) for k in ("reserve_pct", "billing", "plan_type", "billing_source")}
    return rows


def _execution_value(value):
    """Canonicalize configured execution data while dropping secret-shaped keys."""
    if isinstance(value, dict):
        return {str(k): _execution_value(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))
                if not any(word in str(k).lower() for word in ("secret", "token", "password", "credential", "api_key", "apikey"))}
    if isinstance(value, (list, tuple)):
        return [_execution_value(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _digest(data, selection=None):
    raw = json.dumps(_config(data, selection), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _inventory(data):
    models = {}
    pools = data.get("pools") or {}
    for alias, spec in sorted((data.get("models") or {}).items()):
        if not isinstance(spec, dict):
            continue
        row = _safe_metadata(spec)
        pool = pools.get(spec.get("pool")) or {}
        for key in ("remaining_pct", "primary_5h_remaining_pct", "weekly_7d_remaining_pct", "resets_at", "updated_at"):
            if isinstance(pool.get(key), (str, int, float)) or pool.get(key) is None:
                row[key] = pool.get(key)
        models[alias] = row
    return {"models": models,
            "cli_agents": {a: _safe_metadata(s) for a, s in sorted((data.get("cli_agents") or {}).items())
                           if isinstance(s, dict)}}


def _save(B, root, session, registry=None):
    path = session_file(root, registry)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise ValueError("linked session directory refused")
    if path.is_symlink():
        raise ValueError("linked session file refused")
    B.write_atomic(path, json.dumps(session, sort_keys=True, indent=2, ensure_ascii=False))


def propose(B, root, registry=None, new=False, refresh=False):
    with B.checkout_lock(root, name="pool.lock"):
        return _propose_locked(B, root, registry, new, refresh)


def _propose_locked(B, root, registry=None, new=False, refresh=False):
    import runtime_agents as A
    root = Path(root).resolve()
    cached = load_session(root, registry)
    if cached and _unsettled(cached) and (new or refresh):
        raise ValueError("cannot replace/refresh a session with unsettled jobs")
    if cached and not new and not refresh:
        return cached
    data = A.scan_agents(registry) if refresh else A.load(registry)
    inventory = _inventory(data)
    session = {"schema": 1, "session_id": str(uuid.uuid4()), "status": "PROPOSED",
               "project": str(root), "inventory_digest": _digest(data), "created_at": _now(),
               "inventory": inventory, "selection": {}, "jobs": {}}
    _save(B, root, session, registry)
    return session


def _validate_selection(data, selection):
    if not isinstance(selection, dict) or not isinstance(selection.get("models"), dict):
        raise ValueError("selection must contain models")
    models = data.get("models") or {}
    excluded = selection.get("exclude", [])
    if not isinstance(excluded, list) or any(not isinstance(a, str) for a in excluded):
        raise ValueError("exclude must be an alias list")
    out = {"models": {}, "exclude": sorted(set(excluded))}
    for alias, choice in selection["models"].items():
        if not isinstance(alias, str) or alias not in models or not isinstance(models[alias], dict):
            raise ValueError("unknown model alias: " + str(alias))
        if alias in out["exclude"]:
            raise ValueError("alias is both selected and excluded: " + alias)
        if not isinstance(choice, dict):
            raise ValueError("model choice must be an object")
        roles, efforts, billing = choice.get("roles"), choice.get("efforts"), choice.get("billing")
        if not isinstance(roles, list) or not roles or any(not isinstance(x, str) or x not in ROLES for x in roles):
            raise ValueError("invalid or empty roles for " + alias)
        if not isinstance(efforts, list) or not efforts or any(not isinstance(x, str) or x not in EFFORTS for x in efforts):
            raise ValueError("invalid or empty efforts for " + alias)
        if not isinstance(billing, str) or billing not in BILLING:
            raise ValueError("invalid billing for " + alias)
        declared = _known_billing(data, models[alias])
        if declared and billing != declared:
            raise ValueError(f"selected billing {billing} contradicts configured {declared} route for {alias}")
        row = {"roles": sorted(set(roles)), "efforts": sorted(set(efforts)), "billing": billing}
        cap = choice.get("max_jobs")
        if cap is not None:
            if type(cap) is not int or cap <= 0:
                raise ValueError("max_jobs must be a positive integer")
            row["max_jobs"] = cap
        if "allow_paid" in choice:
            if type(choice["allow_paid"]) is not bool:
                raise ValueError("allow_paid must be boolean")
            row["allow_paid"] = choice["allow_paid"]
        if billing == "api" and row.get("allow_paid") is not True:
            raise ValueError("API billing requires explicit allow_paid")
        out["models"][alias] = row
    if not out["models"]:
        raise ValueError("at least one model must be selected")
    if set(out["exclude"]) - set(models):
        raise ValueError("unknown excluded alias")
    return out


def _known_billing(data, spec):
    values = [spec.get("billing")]
    cli = (data.get("cli_agents") or {}).get(spec.get("cli")) or {}
    values.extend((cli.get("billing"), cli.get("billing_source")))
    pool = (data.get("pools") or {}).get(spec.get("pool")) or {}
    values.extend((pool.get("billing"), pool.get("plan_type")))
    found = set()
    for value in values:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in BILLING:
                found.add(normalized)
            elif normalized in ("api_key", "api-key", "metered_api", "pay_as_you_go"):
                found.add("api")
            elif normalized in ("subscription", "subscription_login", "oauth"):
                found.add("subscription")
    if len(found) > 1:
        raise ValueError("configured billing metadata conflicts; fix route and repropose")
    return next(iter(found), None)


def approve(B, root, selection, session_id, registry=None, confirmed=False, note=""):
    with B.checkout_lock(root, name="pool.lock"):
        return _approve_locked(B, root, selection, session_id, registry, confirmed, note)


def _approve_locked(B, root, selection, session_id, registry=None, confirmed=False, note=""):
    import runtime_agents as A
    if confirmed is not True or not isinstance(note, str) or not note.strip():
        raise ValueError("approval requires confirmed=True and a nonempty user note")
    session = load_session(root, registry)
    data = A.load(registry)
    if not session or session.get("session_id") != session_id or session["status"] != "PROPOSED":
        raise ValueError("current proposed session ID required")
    if session["inventory_digest"] != _digest(data):
        raise ValueError("proposal configuration changed; refresh/repropose")
    chosen = _validate_selection(data, selection)
    session["inventory_digest"] = _digest(data, chosen)
    session.update(status="APPROVED", selection=chosen, approval_note=note.strip(), approved_at=_now())
    _save(B, root, session, registry)
    return session


def revoke(B, root, registry=None):
    with B.checkout_lock(root, name="pool.lock"):
        return _revoke_locked(B, root, registry)


def _revoke_locked(B, root, registry=None):
    session = load_session(root, registry)
    if not session:
        raise ValueError("no pool session")
    session.update(status="REVOKED", revoked_at=_now())
    _save(B, root, session, registry)
    return session


def approved_data(B, root, data, registry=None):
    session = load_session(root, registry)
    if not session or session.get("status") != "APPROVED":
        raise ValueError("approved pool session required")
    selection = session["selection"]
    host_session = os.environ.get("PB_SESSION_ID")
    if host_session and host_session != session["session_id"]:
        raise ValueError("host action session ID does not match the approved pool session")
    if session.get("project") != str(Path(root).resolve()) or session["inventory_digest"] != _digest(data, selection):
        raise ValueError("approved pool configuration changed; user reapproval required")
    filtered = dict(data)
    filtered["models"] = {}
    excluded = set(selection.get("exclude", []))
    for alias, choice in selection["models"].items():
        if alias in excluded:
            continue
        spec = dict((data.get("models") or {})[alias])
        spec.update(roles=list(choice["roles"]), efforts=list(choice["efforts"]), tiers=["L", "M", "H"],
                    user_approved=True, available=True, billing=choice["billing"])
        filtered["models"][alias] = spec
    return filtered, session


def _quota(data, spec):
    pool = (data.get("pools") or {}).get(spec.get("pool")) or {}
    value = pool.get("remaining_pct")
    if value is None:
        return None, False
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError("invalid quota percent")
    try:
        stamp = datetime.fromisoformat(str(pool.get("updated_at", "")).replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return float(value), False
        age = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
    except (ValueError, TypeError, OverflowError):
        return float(value), False
    return float(value), 0 <= age <= QUOTA_FRESH_SECONDS


def _unsettled(session):
    return [jid for jid, job in session["jobs"].items()
            if job.get("state") in ("reserved", "running", "response_unknown")]


def authorize(B, root, data, alias, effort, registry=None, role="worker"):
    if any(not isinstance(x, str) for x in (alias, effort, role)):
        raise ValueError("model alias, effort and role must be text")
    filtered, session = approved_data(B, root, data, registry)
    choice = session["selection"]["models"].get(alias)
    spec = filtered["models"].get(alias)
    if not spec or role not in choice["roles"] or effort not in choice["efforts"]:
        raise ValueError("model, role or effort is outside the approved selection")
    if choice["billing"] not in BILLING or (choice["billing"] == "api" and choice.get("allow_paid") is not True):
        raise ValueError("billing route is not explicitly authorized")
    declared = _known_billing(data, (data.get("models") or {}).get(alias) or {})
    if declared and choice["billing"] != declared:
        raise ValueError(f"approved billing contradicts configured {declared} route for {alias}; repropose")
    if _unsettled(session):
        raise ValueError("unsettled pool job blocks dispatch/readback: " + ", ".join(_unsettled(session)))
    cap = choice.get("max_jobs")
    if len(session["jobs"]) >= MAX_ATTEMPTS:
        raise ValueError("session attempt cap reached; create a new proposal")
    if cap is not None and sum(j.get("alias") == alias for j in session["jobs"].values()) >= cap:
        raise ValueError("approved per-session job cap reached")
    remaining, fresh = _quota(data, spec)
    pool = (data.get("pools") or {}).get(spec.get("pool")) or {}
    reserve_pct = pool.get("reserve_pct", 10.0)
    if type(reserve_pct) not in (int, float) or not math.isfinite(reserve_pct) or not 0 <= reserve_pct <= 100:
        raise ValueError("invalid configured quota reserve")
    floor = max(10.0, float(reserve_pct))
    worker_floor = max(25.0, floor)
    if remaining is not None and (remaining <= floor or (role == "worker" and remaining <= worker_floor)):
        raise ValueError("known quota is at or below its configured reserve; refresh before dispatch")
    if remaining is None or not fresh:
        if type(cap) is not int or cap <= 0:
            raise ValueError("unknown or stale quota requires an explicit max_jobs cap")
    else:
        pass
    return spec


def reserve(B, root, data, alias, effort, registry=None, role="worker", expected_session_id=None):
    with B.checkout_lock(root, name="pool.lock"):
        current = _load_registry(registry)
        session = load_session(root, registry)
        if not session or session.get("status") != "APPROVED":
            raise ValueError("approved pool session required before reservation")
        if expected_session_id is not None and session.get("session_id") != expected_session_id:
            raise ValueError("pool session changed after dispatch configuration was prepared")
        selection = session.get("selection") or {}
        if _digest(data, selection) != _digest(current, selection):
            raise ValueError("execution configuration changed after dispatch configuration was prepared")
        spec = authorize(B, root, current, alias, effort, registry, role)
        jid = str(uuid.uuid4())
        session["jobs"][jid] = {"alias": alias, "effort": effort, "state": "reserved", "created_at": _now()}
        _save(B, root, session, registry)
        return jid


def _load_registry(registry):
    import runtime_agents as A
    return A.load(registry)


def finish(B, root, job_id, exit_code=None, registry=None):
    if not isinstance(job_id, str):
        raise ValueError("job_id must be text")
    with B.checkout_lock(root, name="pool.lock"):
        session = load_session(root, registry)
        job = session.get("jobs", {}).get(job_id)
        if not job or job.get("state") not in ("reserved", "running"):
            raise ValueError("unsettled reserved job not found")
        if exit_code is not None and type(exit_code) is not int:
            raise ValueError("exit_code must be an integer or None")
        job.update(state=("response_unknown" if exit_code is None else ("completed" if exit_code == 0 else "failed")),
                   exit_code=exit_code, finished_at=_now())
        _save(B, root, session, registry)
        return session


def settle(B, root, job_id, state, note, registry=None):
    if not isinstance(job_id, str) or state not in ("completed", "failed") or not isinstance(note, str) or not note.strip():
        raise ValueError("settlement requires completed/failed and a readback note")
    with B.checkout_lock(root, name="pool.lock"):
        session = load_session(root, registry)
        job = session.get("jobs", {}).get(job_id)
        if not job or job.get("state") not in ("reserved", "running", "response_unknown"):
            raise ValueError("unsettled job not found")
        job.update(state=state, readback_note=note.strip(), settled_at=_now())
        _save(B, root, session, registry)
        return session


def summary(B, root, registry=None):
    import runtime_agents as A
    session = load_session(root, registry)
    if not session:
        return ["MODEL_POOL: APPROVAL_REQUIRED; run agents session --new"]
    data = A.load(registry)  # Registry read only; no CLI/model probes.
    drift = session["inventory_digest"] != _digest(data, session.get("selection") or None)
    state = "REAPPROVAL_REQUIRED" if session["status"] == "APPROVED" and drift else session["status"]
    lines = [f"MODEL_POOL: {state} session={session['session_id'][:8]}"]
    selection = session.get("selection") or {}
    choices = selection.get("models") or {}
    proposed = session.get("inventory", {}).get("models") or {}
    current = _inventory(data)["models"]
    rows = choices or {a: {} for a in proposed}
    by_cli = {}
    for alias in current:
        cli = (current.get(alias) or {}).get("cli") or "unknown"
        by_cli[cli] = by_cli.get(cli, 0) + 1
    lines.append(f"  inventory: proposed={len(proposed)} current={len(current)} models; current by CLI: " + ", ".join(f"{k}={v}" for k, v in sorted(by_cli.items())))
    shown = sorted(rows.items())[:12]
    for alias, choice in shown:
        inventory = current.get(alias) or proposed.get(alias) or {}
        rem = inventory.get("remaining_pct")
        freshness = "unknown"
        if rem is not None:
            try:
                t = datetime.fromisoformat(str(inventory.get("updated_at", "")).replace("Z", "+00:00"))
                freshness = "fresh" if t.tzinfo is not None and t.utcoffset() is not None and 0 <= (datetime.now(timezone.utc)-t.astimezone(timezone.utc)).total_seconds() <= QUOTA_FRESH_SECONDS else "stale"
            except (ValueError, TypeError):
                freshness = "stale"
        model_id = inventory.get("model_id") or "unknown"
        cli = inventory.get("cli") or "unknown"
        auth = "authenticated" if inventory.get("authenticated") is True else ("unauthenticated" if inventory.get("authenticated") is False else "unknown access")
        window = f" 5h={inventory.get('primary_5h_remaining_pct', 'unknown')}% 7d={inventory.get('weekly_7d_remaining_pct', 'unknown')}%"
        reset = f" reset={inventory['resets_at']}" if inventory.get("resets_at") else ""
        proposed_rem = proposed.get(alias, {}).get("remaining_pct")
        quota_delta = f" proposal_quota={proposed_rem if proposed_rem is not None else 'unknown'}" if rem != proposed_rem else ""
        lines.append(f"  {alias}: model={model_id} cli={cli} access={auth} roles={','.join(choice.get('roles', [])) or 'proposed'} efforts={','.join(choice.get('efforts', [])) or 'proposed'} billing={choice.get('billing', inventory.get('billing', 'unknown'))} quota_now={rem if rem is not None else 'unknown'} ({freshness}){window}{reset}{quota_delta}")
    if len(rows) > len(shown):
        lines.append(f"  {len(rows) - len(shown)} additional model rows omitted; use agents session --json for full inventory")
    current_clis = data.get("cli_agents") or {}
    saved_clis = session.get("inventory", {}).get("cli_agents") or {}
    all_clis = sorted(set(current_clis) | set(saved_clis))
    for cli in all_clis[:16]:
        metadata = current_clis.get(cli) or saved_clis.get(cli) or {}
        access = "authenticated" if metadata.get("authenticated") is True else ("unauthenticated" if metadata.get("authenticated") is False else "unknown")
        lines.append(f"  CLI {cli}: {metadata.get('binary', 'unknown binary')} version={metadata.get('version', 'unknown')} access={access}")
    if len(all_clis) > 16:
        lines.append(f"  {len(all_clis) - 16} additional CLI rows omitted; use agents session --json for full inventory")
    pending = _unsettled(session)
    lines.append("  approval needed" if session["status"] != "APPROVED" else ("  approval must be renewed" if drift else "  approved"))
    if pending:
        lines.append("  unresolved jobs: " + ", ".join(pending))
    return lines
