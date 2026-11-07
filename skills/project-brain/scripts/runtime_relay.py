"""Baton Relay Policy (BRP): unattended director circulation across CLI Agent Pool accounts.

When the director's quota reaches the user's threshold it checkpoints, picks the
next ready candidate, starts it through CLI Agent Pool (CAP) and stops. The old
director stays the record's holder until the successor confirms `takeover`.
`recover` is the single idempotent reconciler: CAP's onExit watchdog runs it when
any director task ends, and it fails over to the next healthy candidate, restarts
after a dead director and releases relay-owned workspace locks. Only an exhausted
candidate list needs the user. Logins are never touched. Cross-repository
contract: references/director-contract.md (pb-director/1). See ADR-006.

The record lives in the ignored Brain cache; tokens are stored only as
hashes. Python 3.8+, standard library only.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import sys
import time

import runtime_security as S
import runtime_verify as V

SCHEMA = 2
MAX_RECORD = 262144
MAX_HISTORY = 200
HASH = re.compile(r"^[0-9a-f]{64}$")
TOKEN = re.compile(r"^[0-9a-f]{32}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,199}$")
STATES = {"ACTIVE", "HANDOFF_PENDING", "STOPPING", "STOPPED", "COMPLETED", "EXHAUSTED"}
LIVE = {"ACTIVE", "HANDOFF_PENDING"}
# STOPPING: the user asked the director to save and withdraw (ADR-007). No new work,
# no successor; still blocks other sessions until STOPPED or the grace deadline.
BLOCKING = LIVE | {"STOPPING"}
STOP_GRACE = 120
STOP_SLICE = 60
PREPARE_MARGIN = 5
ACTIVE_TASK = {"queued", "starting", "running", "cancelling"}
TERMINAL_TASK = {"succeeded", "failed", "timed_out", "cancelled", "needs_review"}
FEATURES = {"preflight", "onExit", "ack", "idle", "secretEnv", "resolve", "releaseLockOnFailure", "directorProfile", "quotaBarrier", "wakeAt", "supersede"}
CAPABILITIES = ["shell", "poolMcp", "readOutside", "gitCommit", "gitRemote", "poolService"]
CONTRACT = "pb-director/1"
TOKEN_ENV = "PB_RELAY_TOKEN"
DIRECTOR_TIMEOUT = 12 * 3600
START_DEADLINE = 6 * 3600
IDLE_TIMEOUT = 3600
LOST_SUBMIT = 600
PREFLIGHT_WAIT = 300
UNPLANNED_LIMIT = 3
TAKEOVER_MINUTES = 15
LABEL = "PB relay g%d %s"
HARD = ("PERMISSION", "DENIED", "AUTH", "ACK_TIMEOUT", "RELAY_SKILL_OLD", "NOT_READY", "PREFLIGHT")


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(policy):
    """Hash of the whole normalized executor policy (ESP/SP/QRP/BRP) the relay inherits."""
    return _hash(_canonical(policy))


def _name(value, label):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError(label + " must be a bounded route/model/effort name")
    return value


def key(candidate):
    return candidate["route"] + ("/" + candidate["model"] if candidate.get("model") else "")


def _iso(value):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value)) if _number(value) else None


# ---------------------------------------------------------------- policy

def validate_policy(value):
    """Validates the optional executor-policy `relay` block; returns a normalized copy."""
    if not isinstance(value, dict):
        raise ValueError("Relay policy must be an object")
    allowed = {"enabled", "threshold_percent", "candidates", "max_handoffs", "director_category", "takeover_minutes"}
    if set(value) - allowed or not {"enabled", "threshold_percent"} <= set(value):
        raise ValueError("Relay requires enabled and threshold_percent; optional candidates or director_category, "
                         "max_handoffs, takeover_minutes")
    if type(value["enabled"]) is not bool:
        raise ValueError("Relay enabled must be true or false")
    threshold = value["threshold_percent"]
    if type(threshold) is not int or not 1 <= threshold <= 50:
        raise ValueError("Relay threshold_percent must be an integer 1..50")
    result = {"enabled": value["enabled"], "threshold_percent": threshold}
    candidates = value.get("candidates", [])
    if not isinstance(candidates, list) or len(candidates) > 32:
        raise ValueError("Relay candidates must be a list of at most 32 routes")
    normalized, seen = [], set()
    for item in candidates:
        if not isinstance(item, dict) or set(item) - {"route", "model", "effort"} or "route" not in item:
            raise ValueError("Relay candidates are {route, model?, effort?}")
        entry = {"route": _name(item["route"], "Relay route")}
        if entry["route"] is None:
            raise ValueError("Relay candidate route is required")
        for name in ("model", "effort"):
            if item.get(name):
                entry[name] = _name(item[name], "Relay " + name)
        ident = (entry["route"], entry.get("model"), entry.get("effort"))
        if ident in seen:
            raise ValueError("Relay candidates must be unique")
        seen.add(ident)
        normalized.append(entry)
    result["candidates"] = normalized
    category = value.get("director_category")
    if category is not None:
        if normalized:
            raise ValueError("Relay uses either explicit candidates or director_category, not both")
        result["director_category"] = _name(category, "Relay director_category")
    elif value["enabled"] and not normalized:
        result["director_category"] = "same"
    limit = value.get("max_handoffs", 50)
    if type(limit) is not int or not 0 <= limit <= 500:
        raise ValueError("Relay max_handoffs must be an integer 0..500")
    result["max_handoffs"] = limit
    if "takeover_minutes" in value:
        minutes = value["takeover_minutes"]
        if type(minutes) is not int or not 5 <= minutes <= 120:
            raise ValueError("Relay takeover_minutes must be an integer 5..120")
        result["takeover_minutes"] = minutes
    return result


def _policy(policy):
    relay = policy.get("relay") if isinstance(policy, dict) else None
    if not isinstance(relay, dict) or relay.get("enabled") is not True:
        raise ValueError("RELAY_DISABLED: save an enabled relay block in the executor policy first")
    return validate_policy(relay), digest(policy)


def _v1_hash(relay):
    """Project Brain 3.9 hashed only the relay block; recognized for live upgrades."""
    keep = {k: relay[k] for k in ("enabled", "threshold_percent", "candidates", "max_handoffs") if k in relay}
    return _hash(_canonical(keep))


# ---------------------------------------------------------------- record

def _path(B, root):
    return V.public_path(root, B.BRAIN_DIR + "/.cache/relay.json")


def _entry_ok(entry):
    return isinstance(entry, dict) and isinstance(entry.get("route"), str) and bool(HASH.fullmatch(entry.get("token_hash") or ""))


def read(B, root):
    path = _path(B, root)
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_RECORD:
        raise ValueError("Relay record exceeds its bound; authority withheld")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        valid = (isinstance(state, dict) and state.get("schema") in (1, SCHEMA) and state.get("status") in STATES
                 and HASH.fullmatch(state.get("policy_hash", "")) and type(state.get("generation")) is int
                 and state["generation"] >= 1 and _entry_ok(state.get("director"))
                 and _number(state["director"].get("since")) and isinstance(state.get("history"), list)
                 and (state.get("pending") is None or _entry_ok(state["pending"]))
                 and (state["status"] != "HANDOFF_PENDING" or state.get("pending") is not None))
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("Invalid relay record; authority withheld")
    if state["schema"] == 1:
        # A live 3.9 relay keeps its holder token; its relay-only policy hash is
        # replaced by the whole-policy hash on the first adoption (_adopt).
        state.update(schema=SCHEMA, policy_mode="relay-v1", inherited=None, candidates=None, health={},
                     features=[], skill_version=None, brain_script=None, unplanned=0, announced=False,
                     owned=[t for t in (state["director"].get("task_id"), (state.get("pending") or {}).get("task_id")) if t],
                     handoffs=sum(1 for row in state["history"] if row.get("event") == "HANDOFF"))
    for name, default in (("health", {}), ("features", []), ("unplanned", 0), ("handoffs", 0), ("owned", []),
                          ("announced", False), ("readiness", "unverified")):
        state.setdefault(name, copy.deepcopy(default))
    return state


def _write(B, root, state):
    state["schema"] = SCHEMA
    state["history"] = state["history"][-MAX_HISTORY:]
    state["owned"] = state["owned"][-50:]
    B.write_atomic(_path(B, root), json.dumps(state, sort_keys=True, indent=2, allow_nan=False))


def _event(state, event, now, **extra):
    row = {"event": event, "at": now, "generation": state["generation"]}
    row.update({k: v for k, v in extra.items() if v is not None})
    state["history"].append(row)


def _candidates(state, relay):
    return state.get("candidates") if state.get("candidates") is not None else relay.get("candidates", [])


def view(state):
    if state is None:
        return {"status": "NONE"}
    director = state["director"]
    result = {"status": state["status"], "generation": state["generation"],
              "director": {k: director.get(k) for k in ("route", "model", "effort", "task_id")},
              "director_since": _iso(director["since"]), "handoffs": state["handoffs"],
              "unplanned_in_a_row": state["unplanned"], "readiness": state["readiness"],
              "features": state["features"], "guarantees": guarantees(state["features"], state["readiness"]),
              "health": {k: {"status": v.get("status"), "checked_at": _iso(v.get("checked_at")),
                             "failures": v.get("failures", 0), "reason": v.get("reason")}
                         for k, v in sorted(state["health"].items())}}
    if state.get("pending"):
        pending = state["pending"]
        result["pending"] = {k: pending.get(k) for k in ("route", "model", "effort", "task_id", "kind")}
        result["pending"]["requested_at"] = _iso(pending.get("requested_at"))
        if pending.get("checkpoint"):
            result["pending"]["checkpoint"] = pending["checkpoint"]["path"]
    if state.get("reason"):
        result["reason"] = state["reason"]
    if state.get("stop_deadline"):
        result["stop_deadline"] = _iso(state["stop_deadline"])
    last = state["history"][-1] if state["history"] else None
    if last:
        result["last_event"] = dict(last, at=_iso(last.get("at")))
    return result


def status(B, root):
    return view(read(B, root))


def boot_line(B, root):
    """One boot line; never raises so a damaged record cannot hide other state."""
    try:
        state = read(B, root)
    except ValueError as exc:
        return "RELAY: INVALID (" + str(exc) + ")"
    if state is None:
        return None
    if state["status"] == "EXHAUSTED":
        return ("RELAY: EXHAUSTED since %s (%s). No director runs; the user decides: `relay start` "
                "again or work normally." % (_iso(state["history"][-1]["at"]) if state["history"] else "?",
                                              state.get("reason") or "no ready candidate"))
    if state["status"] == "STOPPING":
        d = state["director"]
        return ("RELAY: STOPPING gen %d director %s%s; the user asked it to save and withdraw by %s. "
                "No new work; `relay stop` again waits or forces after the deadline."
                % (state["generation"], d["route"], "/" + d["model"] if d.get("model") else "",
                   _iso(state.get("stop_deadline")) or "?"))
    if state["status"] not in LIVE:
        return None
    d = state["director"]
    text = ("RELAY: %s gen %d director %s%s since %s%s" % (
        state["status"], state["generation"], d["route"], "/" + d["model"] if d.get("model") else "",
        _iso(d["since"]), " (pool task " + d["task_id"] + ")" if d.get("task_id") else ""))
    if state.get("pending"):
        text += " -> pending " + state["pending"]["route"]
    return text + ". Another session must not run this project; use `relay stop` to end circulation."


# ---------------------------------------------------------------- authority

def _token_ok(token_hash, token=None):
    token = token if token is not None else os.environ.get(TOKEN_ENV, "")
    return bool(token_hash) and bool(TOKEN.fullmatch(token or "")) and secrets.compare_digest(_hash(token), token_hash)


def _holds(entry, token=None):
    # The token arrives by --relay-token, PB_RELAY_TOKEN, or CAP secretEnv (never stored in CAP).
    return bool(entry) and _token_ok(entry.get("token_hash"), token)


def authorized(B, root, token=None):
    """True when this process holds the live director baton."""
    try:
        state = read(B, root)
    except ValueError:
        return False
    return bool(state and state["status"] == "ACTIVE" and _holds(state["director"], token))


def stopping_holder(B, root, token=None):
    """True for the baton holder after the user requested a stop: it may save and complete only."""
    try:
        state = read(B, root)
    except ValueError:
        return False
    return bool(state and state["status"] == "STOPPING" and _holds(state["director"], token))


def require_free_or_director(B, root):
    """Single-director gate used before implementation work."""
    state = read(B, root)
    if state and state["status"] == "STOPPING":
        if _holds(state["director"]):
            raise ValueError("RELAY_STOP_REQUESTED: the user asked you to stop. Save Resume/next step now, "
                             "then run `relay complete --note \"stopped by user\"` before %s and end."
                             % (_iso(state.get("stop_deadline")) or "the deadline"))
        raise ValueError("RELAY_ACTIVE: " + (boot_line(B, root) or "a relay director is stopping"))
    if state and state["status"] in LIVE and not _holds(state["director"]):
        raise ValueError("RELAY_ACTIVE: " + (boot_line(B, root) or "a relay director owns this project"))


def effective(B, root, value):
    """Policy the baton holder works under: an unconfirmed mid-relay edit never takes effect."""
    try:
        state = read(B, root)
    except ValueError:
        return value
    if (not state or state["status"] not in BLOCKING or not state.get("inherited") or value is None
            or not _holds(state["director"]) or digest(value) == state["policy_hash"]):
        return value
    import runtime_executor_policy as E
    return value if E.receipt_matches_file(B, root) else copy.deepcopy(state["inherited"])


def worker_reserve(B, root, policy):
    """Minimum remaining quota for Pool workers while relay is enabled."""
    relay = policy.get("relay") if isinstance(policy, dict) else None
    return relay["threshold_percent"] if isinstance(relay, dict) and relay.get("enabled") is True else 0


# ---------------------------------------------------------------- quota

def _scope_matches(scope, model):
    if not isinstance(scope, str) or not isinstance(model, str):
        return False
    s = scope.lower()
    m = model.lower()
    if s in m:
        return True
    if s == "gemini-flash" and m.startswith("gemini") and "flash" in m:
        return True
    if s == "gemini-pro" and m.startswith("gemini") and "pro" in m:
        return True
    return False


def remaining(snapshot, model=None):
    """Lowest known remaining percentage that applies to the model, else None."""
    if not isinstance(snapshot, dict) or snapshot.get("status") == "auth_required":
        return None
    values = []
    for window in snapshot.get("windows") or []:
        if not isinstance(window, dict) or not _number(window.get("remainingPercent")):
            continue
        scopes = window.get("models")
        if model and isinstance(scopes, list) and scopes and not any(_scope_matches(s, model) for s in scopes):
            continue
        values.append(max(0, min(100, window["remainingPercent"])))
    return min(values) if values else None


def assess(snapshot, policy, model=None):
    relay, _ = _policy(policy)
    if isinstance(snapshot, dict):
        if snapshot.get("status") in ("auth_required", "subscription_required", "credits_required"):
            return {"status": "HANDOFF_REQUIRED", "remaining_percent": 0, "threshold_percent": relay["threshold_percent"],
                    "reason": snapshot.get("status")}
        if snapshot.get("offline") or snapshot.get("networkError"):
            return {"status": "UNKNOWN", "threshold_percent": relay["threshold_percent"],
                    "offline": True, "reason": "network offline; continue carefully and re-check later"}
    value = remaining(snapshot, model)
    if value is None:
        return {"status": "UNKNOWN", "threshold_percent": relay["threshold_percent"],
                "reason": "no applicable quota window; continue carefully and re-check later"}
    threshold = relay["threshold_percent"]
    result = {"status": "HANDOFF_REQUIRED" if value <= threshold else "READY",
              "remaining_percent": value, "threshold_percent": threshold}
    if threshold < value <= threshold + PREPARE_MARGIN:
        # ADR-007: save Resume/checkpoint 5 points early so the handoff never races exhaustion.
        result["prepare_checkpoint"] = True
    return result


def fetch_quotas(rpc, candidates):
    quotas = {}
    for route in sorted({c["route"] for c in candidates}):
        try:
            quotas[route] = rpc("pool_get_quotas", {"routeId": route})
        except ValueError:
            quotas[route] = None
    return quotas


def choose(policy, quotas, current_route, candidates=None, health=None, current_model=None,
           allow_current=False, exclude=()):
    """Next ready candidate after the current one with quota above the threshold.

    Quota-unknown candidates are used only when no candidate is known above it."""
    relay, _ = _policy(policy)
    candidates = relay.get("candidates", []) if candidates is None else candidates
    health = health or {}
    current = next((i for i, c in enumerate(candidates) if c["route"] == current_route
                    and (current_model is None or c.get("model") == current_model)), None)
    if current is None:
        current = next((i for i, c in enumerate(candidates) if c["route"] == current_route), -1)
    ordered = candidates[current + 1:] + candidates[:max(current, 0)]
    if allow_current and current >= 0:
        ordered.append(candidates[current])
    skipped, unknown = [], []
    for candidate in ordered:
        if key(candidate) in exclude or health.get(key(candidate), {}).get("status") == "unhealthy":
            skipped.append({"route": candidate["route"], "model": candidate.get("model"), "reason": "unhealthy"})
            continue
        qsnap = (quotas or {}).get(candidate["route"])
        if isinstance(qsnap, dict) and qsnap.get("status") in ("auth_required", "subscription_required", "credits_required"):
            skipped.append({"route": candidate["route"], "model": candidate.get("model"), "reason": qsnap.get("status")})
            continue
        value = remaining(qsnap, candidate.get("model"))
        if value is None:
            unknown.append(candidate)
        elif value > relay["threshold_percent"]:
            return {"status": "SELECTED", "candidate": candidate, "remaining_percent": value}
        else:
            skipped.append({"route": candidate["route"], "model": candidate.get("model"), "remaining_percent": value})
    if unknown:
        return {"status": "SELECTED", "candidate": unknown[0], "remaining_percent": None, "quota_unknown": True}
    return {"status": "EXHAUSTED", "skipped": skipped,
            "advice": "No ready candidate has quota above the threshold; wait (QRP if enabled) or stop the relay."}


# ---------------------------------------------------------------- CAP discovery and tiers

def features(rpc):
    try:
        caps = rpc("pool_capabilities", {})
    except ValueError:
        return []
    if not isinstance(caps, dict) or CONTRACT not in (caps.get("contracts") or []):
        return []
    return sorted(FEATURES.intersection(f for f in caps.get("features") or [] if isinstance(f, str)))


def _category_models(rpc, group):
    rows, offset = [], 0
    for _ in range(10):
        page = rpc("pool_list_pools", dict({"group": group}, **({"offset": offset} if offset else {})))
        rows += [m for m in (page or {}).get("models") or [] if isinstance(m, dict)]
        nxt = (page or {}).get("nextOffset")
        if not isinstance(nxt, int) or nxt <= offset:
            break
        offset = nxt
    return [m for m in rows if isinstance(m.get("routeId"), str) and isinstance(m.get("modelId"), str)
            and "write" in (m.get("kinds") or ["write"])]


def resolve_candidates(relay, route, model, rpc):
    """Concrete {route, model, effort} director candidates, resolved once and frozen."""
    if relay.get("candidates"):
        return copy.deepcopy(relay["candidates"])
    category = relay.get("director_category", "same")
    if rpc is None:
        raise ValueError("RELAY_TIER_UNRESOLVED: a director category needs CLI Agent Pool")
    groups = [category] if category != "same" else [
        c["id"] for c in (rpc("pool_list_pools", {}) or {}).get("categories") or [] if isinstance(c, dict) and c.get("id")]
    result, seen = [], set()
    for group in groups:
        rows = _category_models(rpc, group)
        if category == "same" and not any(m["routeId"] == route and (not model or m["modelId"] == model) for m in rows):
            continue
        for m in rows:
            ident = (m["routeId"], m["modelId"])
            if ident in seen or len(result) >= 32:
                continue
            seen.add(ident)
            entry = {"route": _name(m["routeId"], "Relay route"), "model": _name(m["modelId"], "Relay model")}
            if isinstance(m.get("effort"), str) and NAME.fullmatch(m["effort"]):
                entry["effort"] = m["effort"]
            result.append(entry)
    if not result:
        raise ValueError("RELAY_TIER_UNRESOLVED: %s matches no CAP category model; name a category or list candidates"
                         % ("the launcher " + route + ("/" + model if model else "") if category == "same" else "category " + category))
    return result


# ---------------------------------------------------------------- readiness

def _preflight_request(root, candidate, script):
    skill_root = str(Path(script).resolve().parent.parent)
    request = {"routeId": candidate["route"], "workspace": str(Path(root).resolve()),
               "readPaths": [skill_root], "capabilities": list(CAPABILITIES)}
    for name, field in (("model", "modelId"), ("effort", "effort")):
        if candidate.get(name):
            request[field] = candidate[name]
    return request


def _health_from(result, now):
    if not isinstance(result, dict):
        return {"status": "unhealthy", "checked_at": now, "reason": "PREFLIGHT malformed result"}
    caps = result.get("capabilities") or {}
    problems = []
    for name, row in sorted(caps.items()):
        row = row if isinstance(row, dict) else {}
        if row.get("status") not in ("passed", "not_applicable"):
            problems.append("%s %s%s" % (name, row.get("status"), ": " + str(row["fix"])[:120] if row.get("fix") else ""))
    if result.get("error"):
        problems.insert(0, str(result["error"])[:80])
    ready = result.get("ready") is True and not problems
    return {"status": "ready" if ready else "unhealthy", "checked_at": now,
            "reason": None if ready else ("NOT_READY " + "; ".join(problems or ["not ready"]))[:300]}


def preflight(B, root, candidate, rpc, feats, script, now=None, sleep=time.sleep, status_only=False):
    """Readiness of one candidate for the director profile, verified by CAP; returns a health record.

    `status_only` reads CAP's cached result without a probe (no workspace lock): used
    before a planned handoff while the current director still holds the lock."""
    now = time.time() if now is None else now
    if "preflight" not in feats:
        return {"status": "unknown", "checked_at": now, "reason": "CAP has no preflight; readiness unverified"}
    request = _preflight_request(root, candidate, script)
    try:
        if status_only:
            result = rpc("pool_preflight_status", request)
            if not isinstance(result, dict) or result.get("current") is not True:
                return {"status": "unknown", "checked_at": now, "reason": "no current CAP preflight result"}
            return _health_from(result, now)
        result = rpc("pool_preflight", request)
        deadline = time.monotonic() + PREFLIGHT_WAIT
        while isinstance(result, dict) and "ready" not in result and result.get("id"):
            task = rpc("pool_get_task", {"taskId": result["id"]})
            if isinstance(task, dict) and task.get("state") in TERMINAL_TASK:
                result = task.get("preflight") if isinstance(task.get("preflight"), dict) else {
                    "ready": False, "error": "preflight ended %s %s" % (task.get("state"), task.get("error") or "")}
                break
            if time.monotonic() > deadline:
                result = {"ready": False, "error": "preflight did not finish in time"}
                break
            sleep(5)
    except ValueError as exc:
        return {"status": "unhealthy", "checked_at": now, "reason": "PREFLIGHT " + str(exc)[:250]}
    return _health_from(result, now)


def _merge_health(state, name, record):
    old = state["health"].get(name, {})
    merged = dict(old, **record)
    if record.get("status") == "unhealthy":
        merged["failures"] = old.get("failures", 0) + 1
    state["health"][name] = merged


def _failure(state, candidate, reason):
    """A failed director/successor: unhealthy on hard errors or the second failure."""
    name = key(candidate)
    old = state["health"].get(name, {})
    failures = old.get("failures", 0) + 1
    hard = any(word in (reason or "").upper() for word in HARD)
    state["health"][name] = dict(old, failures=failures, reason=(reason or "failed")[:300],
                                 status="unhealthy" if hard or failures >= 2 else old.get("status", "unknown"))


def _progress(state, now):
    """Real director progress resets failure counters (prevents endless failover)."""
    state["unplanned"] = 0
    state["director"]["progress_at"] = now
    candidate = {"route": state["director"]["route"], "model": state["director"].get("model")}
    entry = state["health"].get(key(candidate))
    if entry:
        entry["failures"] = 0


# ---------------------------------------------------------------- policy adoption

def _adopt(B, root, state, policy, rpc, now):
    """Single adoption point for mid-relay policy edits; returns cancellations to perform."""
    import runtime_executor_policy as E
    if policy is None:
        return []
    if state.get("policy_mode") == "relay-v1":
        relay = policy.get("relay") if isinstance(policy, dict) else None
        if isinstance(relay, dict) and _v1_hash(validate_policy(relay)) == state["policy_hash"]:
            state.update(policy_hash=digest(policy), inherited=copy.deepcopy(policy))
            state.pop("policy_mode", None)
            _event(state, "UPGRADED", now, schema=SCHEMA)
            return []
        if not E.receipt_matches_file(B, root):
            cancel = [t for t in ((state.get("pending") or {}).get("task_id"),) if t]
            state.update(status="STOPPED", pending=None, reason="3.9 relay policy changed without confirmation")
            _event(state, "STOP", now, note="3.9 relay record could not be upgraded: policy edited without confirmation")
            return cancel
    if digest(policy) == state["policy_hash"] or not E.receipt_matches_file(B, root):
        return []
    state.pop("policy_mode", None)
    relay = policy.get("relay") if isinstance(policy, dict) else None
    old_relay = (state.get("inherited") or {}).get("relay")
    state.update(policy_hash=digest(policy), inherited=copy.deepcopy(policy))
    if not isinstance(relay, dict) or relay.get("enabled") is not True:
        cancel = [t for t in ((state.get("pending") or {}).get("task_id"),) if t]
        state.update(status="STOPPED", pending=None)
        _event(state, "POLICY_ADOPTED", now, note="relay disabled by the user; circulation stopped")
        return cancel
    if validate_policy(relay) != (validate_policy(old_relay) if isinstance(old_relay, dict) else None):
        director = state["director"]
        try:
            state["candidates"] = resolve_candidates(validate_policy(relay), director["route"], director.get("model"), rpc)
        except ValueError as exc:
            _event(state, "POLICY_ADOPTED", now, note="candidates kept: " + str(exc)[:200])
            return []
    _event(state, "POLICY_ADOPTED", now)
    return []


def _cancel_all(rpc, task_ids):
    done = []
    for task_id in task_ids:
        try:
            rpc("pool_cancel_task", {"taskId": task_id})
            done.append(task_id)
        except ValueError:
            pass
    return done


# ---------------------------------------------------------------- start

def _checkpoint(B, root, task, next_step):
    import runtime_protocol as R
    R.progress(B, root, task, next_step)
    task = B.find_task(root, task["id"])
    R.handoff(B, root, task)
    return R.record_path(B, root, task["id"], "handoff")


def _task(rpc, task_id):
    if not task_id:
        return None
    try:
        value = rpc("pool_get_task", {"taskId": task_id})
    except ValueError as exc:
        return {"state": "not_found"} if "NOT_FOUND" in str(exc) else None
    return value if isinstance(value, dict) else None


def guarantees(feats, readiness):
    return {"readiness": readiness,
            "watchdog": "on (needs the CAP service running)" if "onExit" in feats else "unavailable: a dead director is not restarted automatically",
            "takeover_deadline": "CAP-enforced" if "ack" in feats else "checked when recover runs",
            "lock_release": "automatic" if "releaseLockOnFailure" in feats else ("resolved by recover" if "resolve" in feats else "manual `cli-agent-pool resolve`"),
            "hang_detection": "CAP idle timeout" if "idle" in feats else "12 h task timeout only",
            "authority": "token via CAP secretEnv" if "secretEnv" in feats else "baton token in prompt",
            "quota_barrier": "CAP-enforced" if "quotaBarrier" in feats else "relay assess only",
            "wake_schedule": "CAP wakeAt" if "wakeAt" in feats else "timer/cron polling",
            "predecessor_cleanup": "CAP supersede" if "supersede" in feats else "takeover cancellation"}


def start(B, root, policy, route, model=None, effort=None, task_id=None, rpc=None, brain_script=None,
          now=None, unverified=False, sleep=time.sleep, version=None):
    relay, policy_hash = _policy(policy)
    now = time.time() if now is None else now
    route = _name(route, "Relay route")
    if route is None:
        raise ValueError("The current director route is required")
    state = read(B, root)
    if state and state["status"] in BLOCKING:
        holder = _task(rpc, state["director"].get("task_id")) if rpc else None
        pending = state.get("pending")
        pending_task = _task(rpc, pending.get("task_id")) if rpc and pending else None
        if not (holder and holder.get("state") in TERMINAL_TASK | {"not_found"}
                and (not pending or (pending_task and pending_task.get("state") in TERMINAL_TASK | {"not_found"}))):
            raise ValueError("RELAY_ACTIVE: a live director owns this project; use `relay recover` or `relay stop`")
        with B.checkout_lock(root):
            stale = read(B, root)
            stale.update(status="STOPPED", pending=None)
            _event(stale, "STALE_RESET", now, note="holder and pending tasks had ended")
            _write(B, root, stale)
    feats = features(rpc) if rpc else []
    if "preflight" not in feats and not unverified:
        raise ValueError("RELAY_NOT_READY: CLI Agent Pool has no director preflight (pb-director/1); "
                         "update CAP, or start with --unverified to accept unchecked candidates")
    candidates = resolve_candidates(relay, route, model, rpc)
    script = brain_script or str(Path(__file__).resolve().parent / "brain.py")
    version = version or getattr(B, "VERSION", None)
    health = {key(c): preflight(B, root, c, rpc, feats, script, now, sleep) for c in candidates}
    table = [{"candidate": key(c), "status": health[key(c)]["status"], "reason": health[key(c)].get("reason")}
             for c in candidates]
    if "preflight" in feats and not any(h["status"] == "ready" for h in health.values()):
        raise ValueError("RELAY_NOT_READY: no candidate passed preflight: " + json.dumps(table, ensure_ascii=False))
    token = secrets.token_hex(16)
    with B.checkout_lock(root):
        if (read(B, root) or {}).get("status") in BLOCKING:
            raise ValueError("RELAY_ACTIVE: another director started meanwhile")
        new = {"schema": SCHEMA, "status": "ACTIVE", "policy_hash": policy_hash, "inherited": copy.deepcopy(policy),
               "generation": 1, "handoffs": 0, "unplanned": 0, "announced": False,
               "readiness": "verified" if "preflight" in feats else "unverified",
               "skill_version": version, "brain_script": script, "candidates": candidates, "health": health,
               "features": feats, "owned": [task_id] if task_id else [],
               "director": {"route": route, "model": _name(model, "Relay model"), "effort": _name(effort, "Relay effort"),
                            "task_id": _name(task_id, "Pool task id"), "token_hash": _hash(token), "since": now},
               "pending": None, "history": []}
        _event(new, "START", now, route=route, model=model, threshold=relay["threshold_percent"])
        _write(B, root, new)
    return dict(view(new), token=token, token_env=TOKEN_ENV, preflight=table, guarantees=guarantees(feats, new["readiness"]),
                usage="Pass --relay-token <token> on every Project Brain command (or set %s)." % TOKEN_ENV)


# ---------------------------------------------------------------- successor launch

def successor_prompt(root, brain_script, token, generation, checkpoint, candidate, kind="HANDOFF"):
    # Sent to CLI Agent Pool as the new director's task; not executed by Python.
    pb = 'python "%s" <command> "%s"%s' % (brain_script, root, " --relay-token " + token if token else "")
    why = {"HANDOFF": "The previous director handed off at its quota threshold.",
           "FAILOVER": "The previously chosen successor failed; you are the next candidate.",
           "RECOVER": "The previous director stopped without a handoff; continue from the last checkpoint and "
                      "classify any uncommitted changes before editing."}[kind]
    where = ("the handoff checkpoint " + checkpoint) if checkpoint else "the active task Resume under .project-brain/tasks/"
    return ("Project Brain Baton Relay (BRP): you are the director, generation %d, for workspace %s. %s\n"
            "Run Project Brain as: %s\n"
            "1. First run `relay takeover`. Continue only if it returns \"status\": \"ACTIVE\". On any error do "
            "nothing else and end with a completed report saying takeover failed.\n"
            "2. Settings (ESP/SP, workers, thresholds) are inherited: do NOT ask setup questions, run boot "
            "--new-session, or repeat orientation, discovery or verification that the checkpoint and evidence record.\n"
            "3. Read %s, run `boot`, and continue the saved next step as director: plan, delegate through CLI Agent "
            "Pool per policy, verify, accept, commit as the project allows.\n"
            "4. At meaningful checkpoints run `relay assess`. On HANDOFF_REQUIRED run `relay handoff --task <id> "
            "--next \"<actual next step>\"`, then stop at once and end with a completed report \"handed off\".\n"
            "5. When every task is accepted run `relay complete`.\n"
            "Never log out, switch accounts, edit Pool/CLI credentials or start another director." % (
                generation, root, why, pb, where))


def _commit_pending(B, root, expect, candidate, kind, checkpoint_fn, now, selection, health, planned, count=True):
    """Writes the pending successor under the lock after re-validating the observed state."""
    with B.checkout_lock(root, timeout=90):
        state = read(B, root)
        if (not state or state["status"] not in LIVE or state["generation"] != expect["generation"]
                or (state.get("pending") or {}).get("token_hash") != expect["pending_hash"]):
            raise ValueError("RELAY_CHANGED: the relay changed meanwhile; read it back with relay status")
        for name, record in health.items():
            _merge_health(state, name, record)
        old = state.get("pending") or {}
        checkpoint = old.get("checkpoint") if kind == "FAILOVER" else state.get("last_checkpoint") if kind == "RECOVER" else None
        if kind == "RECOVER" and checkpoint:
            cp_file = V.public_path(root, checkpoint["path"])
            if not cp_file.is_file():
                checkpoint = None
            else:
                checkpoint = {"path": checkpoint["path"], "sha256": hashlib.sha256(cp_file.read_bytes()).hexdigest()}
        if checkpoint_fn:
            path = checkpoint_fn()
            checkpoint = {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            state["last_checkpoint"] = checkpoint
        token = secrets.token_hex(16)
        suffix = secrets.token_hex(8)
        pending = {"candidate": candidate, "route": candidate["route"], "model": candidate.get("model"),
                   "effort": candidate.get("effort"), "token_hash": _hash(token),
                   "requested_at": now, "checkpoint": checkpoint, "task_id": None, "kind": kind,
                   "idempotency_key": "pb-relay-%d-%s" % (state["generation"] + 1, suffix),
                   "label": LABEL % (state["generation"] + 1, suffix), "running_seen_at": None,
                   "quota_unknown": bool(selection.get("quota_unknown")), "from_generation": state["generation"]}
        state["pending"], state["status"] = pending, "HANDOFF_PENDING"
        if planned:
            state["handoffs"] += 1
        elif count:
            state["unplanned"] += 1
        _event(state, kind, now, route=candidate["route"], model=candidate.get("model"),
               quota_unknown=True if selection.get("quota_unknown") else None)
        _write(B, root, state)
    return state, pending, token


def _send(B, root, state, pending, token, rpc, script):
    relay = validate_policy(state["inherited"]["relay"]) if state.get("inherited") else {"threshold_percent": 10}
    feats = state["features"]
    root_text = str(Path(root).resolve())
    prompt = successor_prompt(root_text, script, None if "secretEnv" in feats else token, state["generation"] + 1,
                              (pending.get("checkpoint") or {}).get("path"), pending["candidate"], pending["kind"])
    request = {"prompt": prompt, "workspace": root_text, "kind": "write", "mode": "execute",
               "routeId": pending["route"], "idempotencyKey": pending["idempotency_key"],
               "timeoutSeconds": DIRECTOR_TIMEOUT, "clientLabel": pending["label"]}
    if not pending.get("quota_unknown"):
        request["minRemainingPercent"] = relay["threshold_percent"]
    if pending.get("model"):
        request["modelId"] = pending["model"]
    if pending.get("effort"):
        request["effort"] = pending["effort"]
    if "directorProfile" in feats:
        request["profile"] = "director"
        request["readPaths"] = _preflight_request(root, pending["candidate"], script)["readPaths"]
    if "ack" in feats:
        request["ackDeadlineSeconds"] = relay.get("takeover_minutes", TAKEOVER_MINUTES) * 60
        request["startDeadlineSeconds"] = START_DEADLINE
    if "idle" in feats:
        request["idleTimeoutSeconds"] = IDLE_TIMEOUT
    if "secretEnv" in feats:
        request["secretEnv"] = {TOKEN_ENV: token}
    if "quotaBarrier" in feats and relay.get("threshold_percent"):
        request["stopOnQuotaBarrierPercent"] = relay["threshold_percent"]
    if "supersede" in feats and state["director"].get("task_id"):
        request["supersedesTaskId"] = state["director"]["task_id"]
    if "onExit" in feats:
        request["onExit"] = {"argv": [sys.executable, script, "relay", "recover", root_text, "--from-hook"],
                             "timeoutSeconds": 300}
    submitted = rpc("pool_submit", request)
    task_id = (submitted.get("id") or submitted.get("taskId")) if isinstance(submitted, dict) else None
    with B.checkout_lock(root, timeout=90):
        current = read(B, root)
        if current and current.get("pending") and current["pending"]["token_hash"] == pending["token_hash"]:
            current["pending"]["task_id"] = _name(task_id, "Pool task id") if task_id else None
            if task_id:
                current["owned"].append(task_id)
            _write(B, root, current)
        elif current and current["director"]["token_hash"] == pending["token_hash"] and task_id:
            # A fast successor can take over before submit returns to this client.
            current["director"]["task_id"] = _name(task_id, "Pool task id")
            if task_id not in current["owned"]:
                current["owned"].append(task_id)
            _write(B, root, current)
    return task_id


def _select(B, root, state, policy, rpc, script, now, sleep, quotas=None, allow_current=False, planned=False):
    """Chooses the next candidate whose CAP readiness holds, outside the lock.

    A planned handoff reads CAP's cached result only (the live director holds the
    workspace lock); recovery after a dead director runs a fresh probe."""
    candidates = _candidates(state, validate_policy(policy["relay"]))
    quotas = quotas if quotas is not None else fetch_quotas(rpc, candidates)
    health, exclude = copy.deepcopy(state["health"]), set()
    updates = {}
    while True:
        selection = choose(policy, quotas, state["director"]["route"], candidates, health,
                           state["director"].get("model"), allow_current, exclude)
        if selection["status"] != "SELECTED":
            return selection, updates
        candidate = selection["candidate"]
        entry = health.get(key(candidate), {})
        if "preflight" in state["features"]:
            record = preflight(B, root, candidate, rpc, state["features"], script, now, sleep, status_only=planned)
            if record["status"] != "unknown":
                updates[key(candidate)] = record
                health[key(candidate)] = dict(entry, **record)
            if record["status"] != "ready":
                exclude.add(key(candidate))
                continue
        return selection, updates


def handoff(B, root, policy, task, next_step, brain_script, rpc, candidate=None, quotas=None, now=None, token=None,
            write_checkpoint=_checkpoint, sleep=time.sleep, version=None):
    """Planned handoff: select, preflight, checkpoint, start the successor, record it."""
    now = time.time() if now is None else now
    if not isinstance(next_step, str) or not next_step.strip():
        raise ValueError("Save the actual next action before handing off")
    with B.checkout_lock(root, timeout=90):
        state = read(B, root)
        if not state or state["status"] not in LIVE:
            raise ValueError("RELAY_NOT_ACTIVE: start the relay first")
        if not _holds(state["director"], token):
            raise ValueError("RELAY_NOT_DIRECTOR: only the current baton holder can hand off")
        cancel = _adopt(B, root, state, policy, rpc, now)
        _progress(state, now)
        _write(B, root, state)
    if cancel:
        _cancel_all(rpc, cancel)
    if state["status"] not in LIVE:
        return view(state)
    relay = validate_policy(state["inherited"]["relay"]) if state.get("inherited") else _policy(policy)[0]
    policy = state.get("inherited") or policy
    if state.get("pending"):
        if state["pending"].get("task_id"):
            raise ValueError("HANDOFF_PENDING: a successor was already started; read it back with relay status")
        candidate = state["pending"]["candidate"]  # an unacknowledged submit is retried with a fresh token
    if relay.get("max_handoffs", 50) > 0 and state["handoffs"] >= relay["max_handoffs"] and not state.get("pending"):
        raise ValueError("RELAY_LIMIT: max_handoffs reached; the user must restart the relay")
    updates, selection = {}, {"status": "SELECTED"}
    if candidate is None:
        selection, updates = _select(B, root, state, policy, rpc, brain_script, now, sleep, quotas, planned=True)
        if selection["status"] != "SELECTED":
            return selection
        candidate = selection["candidate"]
    elif not any(c == candidate for c in _candidates(state, relay)):
        raise ValueError("Successor must be a listed relay candidate")
    expect = {"generation": state["generation"], "pending_hash": (state.get("pending") or {}).get("token_hash")}
    checkpoint_fn = None if state.get("pending") else (lambda: write_checkpoint(B, root, task, next_step))
    kind = "HANDOFF"
    state, pending, successor = _commit_pending(B, root, expect, candidate, kind, checkpoint_fn, now, selection,
                                                updates, planned=not expect["pending_hash"])
    task_id = _send(B, root, state, pending, successor, rpc, brain_script)
    return {"status": "HANDED_OFF", "successor": candidate, "pool_task": task_id,
            "checkpoint": (pending.get("checkpoint") or {}).get("path"),
            "instruction": "Stop working now and end your task with a completed report \"handed off\". "
                           "You stay the holder until the successor confirms takeover."}


# ---------------------------------------------------------------- takeover

def _version(text):
    return tuple(int(p) for p in re.findall(r"\d+", text or "")[:3]) or (0,)


def takeover(B, root, policy, rpc, token=None, now=None, version=None):
    """Successor confirms the baton; stops the previous director task if still live."""
    now = time.time() if now is None else now
    version = version or getattr(B, "VERSION", None)
    with B.checkout_lock(root, timeout=90):
        state = read(B, root)
        if not state or state["status"] != "HANDOFF_PENDING" or not state.get("pending"):
            raise ValueError("RELAY_NO_HANDOFF: no pending baton for this project")
        pending = state["pending"]
        if not _holds(pending, token):
            raise ValueError("RELAY_TOKEN_MISMATCH: this process does not hold the pending baton")
        running_task = os.environ.get("CLI_AGENT_POOL_TASK_ID")
        if running_task:
            running_task = _name(running_task, "Pool task id")
            if pending.get("task_id") and pending["task_id"] != running_task:
                raise ValueError("RELAY_TASK_MISMATCH: pending baton belongs to another CAP task")
            pending["task_id"] = running_task
            if running_task not in state["owned"]:
                state["owned"].append(running_task)
        cancel = _adopt(B, root, state, policy, rpc, now)
        if state["status"] not in LIVE:
            _write(B, root, state)
            _cancel_all(rpc, cancel)
            raise ValueError("RELAY_STOPPED: the user disabled the relay; do no work")
        if state.get("skill_version") and _version(version) < _version(state["skill_version"]):
            _failure(state, pending["candidate"], "RELAY_SKILL_OLD running %s < %s" % (version, state["skill_version"]))
            _write(B, root, state)
            raise ValueError("RELAY_SKILL_OLD: this Project Brain is older than the relay's; do no work")
        if pending.get("checkpoint"):
            checkpoint = V.public_path(root, pending["checkpoint"]["path"])
            if not checkpoint.is_file() or hashlib.sha256(checkpoint.read_bytes()).hexdigest() != pending["checkpoint"]["sha256"]:
                if pending.get("kind") in ("RECOVER", "FAILOVER"):
                    _event(state, "CHECKPOINT_DEVIATION", now, path=pending["checkpoint"]["path"])
                    pending["checkpoint"] = None
                else:
                    raise ValueError("RELAY_CHECKPOINT_CHANGED: handoff checkpoint changed; ask the user")
        previous = state["director"]
        state["director"] = {"route": pending["route"], "model": pending.get("model"), "effort": pending.get("effort"),
                             "task_id": pending.get("task_id"), "token_hash": pending["token_hash"], "since": now}
        if version and _version(version) > _version(state.get("skill_version")):
            state["skill_version"] = version
        state["generation"] += 1
        state["pending"], state["status"], state["announced"] = None, "ACTIVE", False
        state["health"].setdefault(key(pending["candidate"]), {}).update(status="ready", reason=None)
        _event(state, "TAKEOVER", now, route=pending["route"], model=pending.get("model"),
               previous_route=previous["route"], previous_task=previous.get("task_id"))
        _write(B, root, state)
    if "ack" in state["features"] and pending.get("task_id"):
        try:
            rpc("pool_ack_task", {"taskId": pending["task_id"]})
        except ValueError:
            pass
    cancelled = False
    previous_task = previous.get("task_id")
    if previous_task:
        observed = _task(rpc, previous_task)
        if observed and observed.get("state") in ("queued", "starting", "running"):
            cancelled = bool(_cancel_all(rpc, [previous_task]))
    return dict(view(state), previous_director_cancelled=cancelled,
                checkpoint=(pending.get("checkpoint") or {}).get("path"))


# ---------------------------------------------------------------- recover

def _notify(state):
    return "CAP_NOTIFY Project Brain relay EXHAUSTED for %s: %s" % (
        state.get("workspace") or "this project", state.get("reason") or "no ready candidate")


def _resolve_owned(state, rpc, observed):
    """Releases relay-owned needs_review locks (director task ids only)."""
    actions = []
    for task_id in state["owned"]:
        info = observed.get(task_id) if task_id in observed else _task(rpc, task_id)
        if not info or info.get("state") != "needs_review":
            continue
        if "resolve" in state["features"]:
            try:
                rpc("pool_resolve_task", {"taskId": task_id, "reviewed": True,
                                          "note": "Project Brain relay: next director classifies the dirty tree at boot"})
                actions.append("resolved " + task_id)
                continue
            except ValueError:
                pass
        actions.append("run: cli-agent-pool resolve " + task_id)
    return actions


def _relay_owned(state, rpc, task_id):
    """Only recorded directors and their linked workers belong to this relay."""
    if task_id in state["owned"]:
        return True
    info = _task(rpc, task_id)
    return bool(info and info.get("parentTaskId") in state["owned"])


def _strays(state, rpc, root):
    """Active relay-labelled tasks in this workspace that are neither holder nor pending."""
    try:
        rows = rpc("pool_list_tasks", {"limit": 100})
    except ValueError:
        return [], []
    rows = rows.get("tasks", rows) if isinstance(rows, dict) else rows
    keep = {state["director"].get("task_id"), (state.get("pending") or {}).get("task_id")}
    workspace = os.path.normcase(str(Path(root).resolve()))
    found, strays = [], []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not str(row.get("clientLabel") or "").startswith("PB relay g"):
            continue
        if os.path.normcase(str(row.get("workspace") or "")) != workspace:
            continue
        found.append(row)
        pending_label = (state.get("pending") or {}).get("label")
        if (row.get("state") in ACTIVE_TASK and row.get("id") not in keep
                and row.get("clientLabel") != pending_label):
            strays.append(row["id"])
    return found, strays


def recover(B, root, policy, rpc, brain_script=None, now=None, sleep=time.sleep, version=None):
    """Idempotent reconciler; run by CAP's onExit watchdog, relay start, or a person."""
    now = time.time() if now is None else now
    script = brain_script or str(Path(__file__).resolve().parent / "brain.py")
    state = read(B, root)
    if not state:
        return {"status": "NONE", "actions": []}
    observed = {}
    for task_id in (state["director"].get("task_id"), (state.get("pending") or {}).get("task_id")):
        if task_id:
            observed[task_id] = _task(rpc, task_id)
    labelled, strays = _strays(state, rpc, root)
    actions = ["cancelled stray " + t for t in _cancel_all(rpc, strays)]
    if state["status"] == "STOPPING":
        # A requested stop never restarts or fails over; it only finishes the stop.
        holder = observed.get(state["director"].get("task_id")) if state["director"].get("task_id") else None
        ended = holder is not None and holder.get("state") in TERMINAL_TASK | {"not_found"}
        if ended or now >= (state.get("stop_deadline") or 0):
            done = finish(B, root, "STOP", "stop finished by recover", rpc=rpc, now=now)
            return dict(done, actions=actions + done.get("actions", []), notify=None)
        return dict(view(state), actions=actions, notify=None)
    if state["status"] not in LIVE:
        actions += _resolve_owned(state, rpc, observed)
        notify = None
        if state["status"] == "EXHAUSTED" and not state["announced"]:
            with B.checkout_lock(root, timeout=90):
                current = read(B, root)
                current["announced"] = True
                _write(B, root, current)
            notify = _notify(dict(state, workspace=str(Path(root).resolve())))
        return dict(view(state), actions=actions, notify=notify)
    plan, cancel, failure = None, [], None
    pending = state.get("pending")
    director = state["director"]
    if pending:
        info = observed.get(pending.get("task_id")) if pending.get("task_id") else None
        if not pending.get("task_id"):
            match = next((row for row in labelled if row.get("clientLabel") == pending["label"]), None)
            if match:
                with B.checkout_lock(root, timeout=90):
                    current = read(B, root)
                    if (current.get("pending") or {}).get("token_hash") == pending["token_hash"]:
                        current["pending"]["task_id"] = match["id"]
                        current["owned"].append(match["id"])
                        _write(B, root, current)
                actions.append("found successor task " + match["id"])
            elif now - pending["requested_at"] > LOST_SUBMIT:
                plan = "FAILOVER"
        elif info is None:
            actions.append("successor state unknown; CAP unreachable")
        elif info.get("state") in TERMINAL_TASK | {"not_found"}:
            error = str(info.get("error") or info.get("state"))
            if not any(w in error.upper() for w in ("START_TIMEOUT", "QUOTA_BARRIER", "QUOTA_EXHAUSTED", "SUPERSEDED_BY_HANDOFF")):
                failure = (pending["candidate"], "successor ended without takeover: " + error)
            holder = observed.get(director.get("task_id")) if director.get("task_id") else None
            if holder and holder.get("state") in ACTIVE_TASK:
                cancel.append(director["task_id"])  # it already handed off and must not block the successor
            plan = "FAILOVER"
        elif info.get("state") in ("starting", "running"):
            seen = pending.get("running_seen_at")
            minutes = validate_policy(state["inherited"]["relay"]).get("takeover_minutes", TAKEOVER_MINUTES) \
                if state.get("inherited") else TAKEOVER_MINUTES
            if seen is None:
                with B.checkout_lock(root, timeout=90):
                    current = read(B, root)
                    if (current.get("pending") or {}).get("token_hash") == pending["token_hash"]:
                        current["pending"]["running_seen_at"] = now
                        _write(B, root, current)
            elif now - seen > minutes * 60:
                cancel.append(pending["task_id"])
                failure = (pending["candidate"], "ACK_TIMEOUT no takeover within %d minutes" % minutes)
                plan = "FAILOVER"
        elif info.get("state") == "queued":
            blocker = info.get("blockedBy")
            if info.get("queueReason") == "WORKSPACE_REVIEW_REQUIRED" and blocker:
                if _relay_owned(state, rpc, blocker):
                    with B.checkout_lock(root, timeout=90):
                        current = read(B, root)
                        if blocker not in current["owned"]:
                            current["owned"].append(blocker)
                            _write(B, root, current)
                    state["owned"].append(blocker)
                else:
                    plan = "EXHAUSTED"
                    state["reason"] = "workspace locked by CAP task %s that needs the user's review" % blocker
            elif blocker and blocker == director.get("task_id") and now - pending["requested_at"] > START_DEADLINE:
                cancel.append(blocker)
                actions.append("cancelled handed-off director blocking its successor")
    elif director.get("task_id"):
        info = observed.get(director["task_id"])
        if info and info.get("state") in TERMINAL_TASK | {"not_found"}:
            error = str(info.get("error") or info.get("state"))
            is_quota = any(w in error.upper() for w in ("QUOTA_BARRIER", "QUOTA_EXHAUSTED", "SUPERSEDED_BY_HANDOFF"))
            if not is_quota:
                failure = ({"route": director["route"], "model": director.get("model")}, "director ended: " + error)
            plan = "RECOVER"
    actions += ["cancelled " + t for t in _cancel_all(rpc, cancel)]
    actions += _resolve_owned(state, rpc, observed)
    if plan is None:
        return dict(view(state), actions=actions, notify=None)
    expect = {"generation": state["generation"], "pending_hash": (pending or {}).get("token_hash")}
    with B.checkout_lock(root, timeout=90):
        current = read(B, root)
        if (current["status"] not in LIVE or current["generation"] != expect["generation"]
                or (current.get("pending") or {}).get("token_hash") != expect["pending_hash"]):
            return dict(view(current), actions=actions + ["relay changed meanwhile; nothing to do"], notify=None)
        stop = _adopt(B, root, current, policy, rpc, now)
        if failure:
            _failure(current, failure[0], failure[1])
        reason = state.get("reason") if plan == "EXHAUSTED" else None
        if current["status"] in LIVE and plan != "EXHAUSTED" and current["unplanned"] >= UNPLANNED_LIMIT:
            plan, reason = "EXHAUSTED", "%d unplanned transfers in a row without progress" % current["unplanned"]
        _write(B, root, current)
        state = current
    actions += ["cancelled " + t for t in _cancel_all(rpc, stop)]
    if state["status"] not in LIVE:
        return dict(view(state), actions=actions, notify=None)
    selection = {"status": "EXHAUSTED"}
    if plan != "EXHAUSTED":
        hard = failure and any(word in failure[1].upper() for word in HARD)
        selection, updates = _select(B, root, state, state.get("inherited") or policy, rpc, script, now, sleep,
                                     allow_current=plan == "RECOVER" and not hard)
        while selection["status"] == "SELECTED":
            try:
                state, pending, token = _commit_pending(B, root, expect, selection["candidate"], plan, None, now,
                                                        selection, updates, planned=False, count=bool(failure))
                task_id = _send(B, root, state, pending, token, rpc, script)
                return dict(view(read(B, root)), actions=actions + ["%s to %s (task %s)" % (plan, key(selection["candidate"]), task_id)],
                            notify=None)
            except ValueError as exc:
                actions.append("rejected %s: %s" % (key(selection["candidate"]), str(exc)[:120]))
                _failure(state, selection["candidate"], "SUBMISSION_REJECTED: " + str(exc)[:200])
                with B.checkout_lock(root, timeout=90):
                    cur = read(B, root)
                    cur["pending"] = None
                    cur["status"] = "ACTIVE"
                    _write(B, root, cur)
                selection, updates = _select(B, root, state, state.get("inherited") or policy, rpc, script, now, sleep,
                                             allow_current=False)
        reason = "no ready candidate has quota above the threshold"
        earliest_reset = None
        for r_id, q_data in (fetch_quotas(rpc, _candidates(state, validate_policy((state.get("inherited") or policy)["relay"]))) or {}).items():
            if isinstance(q_data, dict):
                for w in q_data.get("windows") or []:
                    if isinstance(w, dict) and w.get("resetAt"):
                        try:
                            import datetime
                            dt = datetime.datetime.fromisoformat(w["resetAt"].replace("Z", "+00:00"))
                            t_epoch = dt.timestamp()
                            if t_epoch > now:
                                earliest_reset = min(earliest_reset or t_epoch, t_epoch)
                        except Exception:
                            pass
        if earliest_reset:
            wake_seconds = max(60, min(3600, int(earliest_reset - now + 15)))
            import datetime
            wake_iso = datetime.datetime.fromtimestamp(now + wake_seconds, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            print("CAP_WAKE_AT " + wake_iso)
            print("CAP_RETRY_AFTER %d" % wake_seconds)
            with B.checkout_lock(root, timeout=90):
                cur = read(B, root)
                cur["reason"] = "waiting quota renewal until " + wake_iso
                _write(B, root, cur)
            return dict(view(read(B, root)), actions=actions + ["waiting quota renewal until " + wake_iso], exit_code=75)
    with B.checkout_lock(root, timeout=90):
        current = read(B, root)
        if current["generation"] == expect["generation"] and current["status"] in LIVE:
            cancel = [t for t in ((current.get("pending") or {}).get("task_id"),) if t and t not in cancel]
            current.update(status="EXHAUSTED", pending=None, reason=reason, announced=True)
            _event(current, "EXHAUSTED", now, note=reason)
            _write(B, root, current)
            _cancel_all(rpc, [t for t in cancel if (observed.get(t) or {}).get("state") in ACTIVE_TASK])
        state = current
    return dict(view(state), actions=actions, notify=_notify(dict(state, workspace=str(Path(root).resolve()))))


# ---------------------------------------------------------------- finish

def finish(B, root, event, note, rpc=None, token=None, now=None):
    """COMPLETE (director) or STOP (user). Stop also cancels live director tasks."""
    now = time.time() if now is None else now
    note = (note or "")[:500]
    S.require_public(note, "relay note")
    with B.checkout_lock(root, timeout=90):
        state = read(B, root)
        if not state or state["status"] not in BLOCKING:
            if state and event == "STOP" and state["status"] == "EXHAUSTED":
                state["status"] = "STOPPED"
                _event(state, event, now, note=note or None)
                _write(B, root, state)
            return {"status": state["status"] if state else "NONE"}
        if event == "COMPLETE" and not _holds(state["director"], token):
            raise ValueError("RELAY_NOT_DIRECTOR: only the baton holder can complete the relay")
        tasks = [t for t in ((state.get("pending") or {}).get("task_id"),) if t]
        if event == "STOP" and state["director"].get("task_id"):
            tasks.insert(0, state["director"]["task_id"])
        acknowledged = event == "COMPLETE" and state["status"] == "STOPPING"
        state["status"] = "STOPPED" if event == "STOP" or acknowledged else "COMPLETED"
        state["pending"] = None
        state.pop("stop_deadline", None)
        _event(state, "STOP_ACK" if acknowledged else event, now, note=note or None)
        _write(B, root, state)
    cancelled = _cancel_all(rpc, tasks) if rpc else []
    actions = _resolve_owned(state, rpc, {}) if rpc and event == "STOP" else []
    return dict(view(state), cancelled=cancelled, actions=actions)


def request_stop(B, root, note, rpc=None, now=None, sleep=time.sleep, force=False, clock=time.time):
    """User stop (ADR-007): ask the director to save and withdraw within STOP_GRACE seconds.

    The first call records STOPPING and cancels a not-yet-confirmed successor. Each
    call waits at most STOP_SLICE seconds for the holder's `relay complete`; at the
    deadline, with `force`, or when the director task already ended, the director
    task is cancelled (finish STOP). A host director without a CAP task cannot be
    cancelled by Brain; it is told at its next Brain command and must stop."""
    now = clock() if now is None else now
    note = (note or "User stopped the relay")[:500]
    S.require_public(note, "relay note")
    state = read(B, root)
    if not state or state["status"] not in BLOCKING or force:
        return finish(B, root, "STOP", note, rpc=rpc, now=now)
    holder = _task(rpc, state["director"].get("task_id")) if rpc and state["director"].get("task_id") else None
    if holder and holder.get("state") in TERMINAL_TASK | {"not_found"}:
        return finish(B, root, "STOP", note + " (director already ended)", rpc=rpc, now=now)
    cancel = []
    if state["status"] != "STOPPING":
        with B.checkout_lock(root, timeout=90):
            state = read(B, root)
            if state["status"] in LIVE:
                pending = state.get("pending") or {}
                cancel = [pending["task_id"]] if pending.get("task_id") else []
                state.update(status="STOPPING", pending=None, stop_deadline=now + STOP_GRACE)
                _event(state, "STOP_REQUESTED", now, note=note)
                _write(B, root, state)
        if rpc:
            _cancel_all(rpc, cancel)
        return dict(view(state), seconds_left=STOP_GRACE, cancelled=cancel,
                    next="run `relay stop` again to wait (at most 60 s per call); it forces after the deadline")
    waited = 0
    while True:
        left = state["stop_deadline"] - (now + waited)
        if left <= 0:
            return finish(B, root, "STOP", note + " (grace period elapsed)", rpc=rpc, now=now + waited)
        if waited >= STOP_SLICE:
            return dict(view(state), seconds_left=int(left))
        step = min(5, left, STOP_SLICE - waited)
        sleep(step)
        waited += step
        state = read(B, root)
        if not state or state["status"] != "STOPPING":
            return view(state)


def mark_progress(B, root, policy, rpc, now=None):
    """Holder progress (assess): resets failure counters and adopts confirmed policy edits."""
    now = time.time() if now is None else now
    with B.checkout_lock(root, timeout=90):
        state = read(B, root)
        if not state or state["status"] != "ACTIVE" or not _holds(state["director"]):
            return state
        cancel = _adopt(B, root, state, policy, rpc, now)
        _progress(state, now)
        _write(B, root, state)
    _cancel_all(rpc, cancel)
    return state


# ---------------------------------------------------------------- CLI

def add_parser(sub):
    p = sub.add_parser("relay", help="Baton Relay Policy: director circulation across CAP accounts")
    p.add_argument("action", choices=("status", "start", "assess", "next", "handoff", "takeover", "complete", "stop",
                                      "recover"))
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--route", default="")
    p.add_argument("--model", default="")
    p.add_argument("--effort", default="")
    p.add_argument("--pool-task", default="")
    p.add_argument("--snapshot", default="")
    p.add_argument("--quotas", default="")
    p.add_argument("--task", default="")
    p.add_argument("--next", dest="next_step", default="")
    p.add_argument("--note", default="")
    p.add_argument("--unverified", action="store_true")
    p.add_argument("--force", action="store_true", help="stop: cancel the director now instead of the 2-minute save")
    p.add_argument("--from-hook", action="store_true")


def _pool():
    import runtime_agent_pool as AP
    return AP


def command(B, args, pool=None):
    import runtime_control as CT
    import runtime_executor_policy as E
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise ValueError("Project directory required")
    if args.action == "status":
        return status(B, root)
    pool = pool or _pool()
    rpc = pool.rpc
    if args.action == "stop":
        if os.environ.get("CLI_AGENT_POOL_WORKER") and not (authorized(B, root) or stopping_holder(B, root)):
            raise ValueError("Workers cannot stop another director's relay")
        return request_stop(B, root, args.note or "User stopped the relay", rpc=rpc,
                            force=getattr(args, "force", False))
    policy = E.load(B, root)
    script = str(Path(__file__).resolve().parent / "brain.py")
    if args.action == "recover":
        try:
            return recover(B, root, policy, rpc, script)
        except ValueError as exc:
            if args.from_hook:
                print("CAP_RETRY_AFTER 30")
                return {"status": "RETRY", "error": str(exc)[:300], "exit_code": 75}
            raise
    if args.action == "takeover":
        return takeover(B, root, policy, rpc)
    E.require_confirmed(B, root)
    if args.action == "assess":
        state = mark_progress(B, root, policy, rpc)
        if state and state["status"] == "STOPPING":
            return {"status": "STOP_REQUESTED", "stop_deadline": _iso(state.get("stop_deadline")),
                    "next": "save Resume/next step, then `relay complete --note \"stopped by user\"` and end"}
        policy = E.load(B, root)
        if args.snapshot:
            snapshot = CT.read_input(root, args.snapshot)
        else:
            if not state or state["status"] not in LIVE:
                raise ValueError("RELAY_NOT_ACTIVE: no relay director to assess")
            try:
                snapshot = rpc("pool_get_quotas", {"routeId": state["director"]["route"]})
            except Exception as exc:
                snapshot = {"status": "UNKNOWN", "offline": True, "reason": str(exc)}
        return assess(snapshot, policy, args.model or (state or {}).get("director", {}).get("model"))
    if args.action == "next":
        state = read(B, root)
        current = state["director"]["route"] if state else args.route
        candidates = _candidates(state, _policy(policy)[0]) if state else None
        quotas = CT.read_input(root, args.quotas) if args.quotas else fetch_quotas(rpc, candidates or _policy(policy)[0]["candidates"])
        return choose(policy, quotas, current, candidates, (state or {}).get("health"))
    if args.action == "complete":
        return finish(B, root, "COMPLETE", args.note, rpc=rpc)
    if args.action == "start":
        if os.environ.get("CLI_AGENT_POOL_WORKER"):
            raise ValueError("A Pool worker cannot start a relay; the host director starts it")
        if B.get_session_modes(root)["task_mode"] != "execute":
            raise ValueError("Relay circulation requires an execute session")
        return start(B, root, policy, args.route, args.model or None, args.effort or None, args.pool_task or None,
                     rpc=rpc, brain_script=script, unverified=args.unverified)
    # handoff
    task = B.find_task(root, args.task) if args.task else None
    if not task:
        raise ValueError("Handoff needs the active --task")
    candidate = None
    if args.route:
        candidate = {"route": _name(args.route, "Relay route")}
        if args.model:
            candidate["model"] = _name(args.model, "Relay model")
        if args.effort:
            candidate["effort"] = _name(args.effort, "Relay effort")
    quotas = CT.read_input(root, args.quotas) if args.quotas else None
    return handoff(B, root, policy, task, args.next_step, script, rpc, candidate=candidate, quotas=quotas)
