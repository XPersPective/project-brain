"""Baton Relay Policy (BRP): unattended director circulation across CLI Agent Pool accounts.

When the director's quota reaches the user's threshold it checkpoints, picks the
next ready candidate, starts it through CLI Agent Pool (CAP) and stops. The old
director stays the record's holder until the successor confirms `takeover`.
`recover` is the single idempotent reconciler: CAP's onExit watchdog runs it when
any director task ends. Cross-repository contract: references/director-contract.md.

The record lives in the ignored Brain cache; tokens are stored only as hashes.
Python 3.8+, standard library only.
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

import runtime_agent_pool as AP
import runtime_core as Core
import runtime_executor_policy as E
import runtime_protocol as R
import runtime_security as S

SCHEMA = 2
MAX_RECORD = 262144
MAX_HISTORY = 200
HASH = re.compile(r"^[0-9a-f]{64}$")
TOKEN = re.compile(r"^[0-9a-f]{32}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,199}$")
STATES = {"ACTIVE", "HANDOFF_PENDING", "STOPPING", "STOPPED", "COMPLETED", "EXHAUSTED"}
LIVE = {"ACTIVE", "HANDOFF_PENDING"}
BLOCKING = LIVE | {"STOPPING"}
STOP_GRACE = 120
STOP_SLICE = 60
PREPARE_MARGIN = 5
ACTIVE_TASK = {"queued", "starting", "running", "cancelling"}
TERMINAL_TASK = {"succeeded", "failed", "timed_out", "cancelled", "needs_review"}
FEATURES = {
    "preflight", "onExit", "ack", "idle", "secretEnv", "resolve",
    "releaseLockOnFailure", "directorProfile", "quotaBarrier", "wakeAt", "supersede",
}
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

# Single source of truth for relay policy validation lives in runtime_executor_policy.
validate_policy = E.validate_relay_policy


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


def _policy(policy):
    relay = policy.get("relay") if isinstance(policy, dict) else None
    if not isinstance(relay, dict) or relay.get("enabled") is not True:
        raise ValueError("RELAY_DISABLED: save an enabled relay block in the executor policy first")
    return validate_policy(relay), digest(policy)


def _v1_hash(relay):
    keep = {k: relay[k] for k in ("enabled", "threshold_percent", "candidates", "max_handoffs") if k in relay}
    return _hash(_canonical(keep))


# ---------------------------------------------------------------- record

def _path(B, root):
    return Core.public_path(root, B.BRAIN_DIR + "/.cache/relay.json")


def _entry_ok(entry):
    return isinstance(entry, dict) and isinstance(entry.get("route"), str) and bool(HASH.fullmatch(entry.get("token_hash") or ""))


def read(B, root):
    path = _path(B, root)
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_RECORD:
        raise ValueError("Relay record exceeds its bound; authority withheld")
    try:
        state = json.loads(path.read_text(encoding="utf-8-sig"))
        valid = (
            isinstance(state, dict)
            and state.get("schema") in (1, SCHEMA)
            and state.get("status") in STATES
            and HASH.fullmatch(state.get("policy_hash", ""))
            and type(state.get("generation")) is int
            and state["generation"] >= 1
            and _entry_ok(state.get("director"))
            and _number(state["director"].get("since"))
            and isinstance(state.get("history"), list)
            and (state.get("pending") is None or _entry_ok(state["pending"]))
            and (state["status"] != "HANDOFF_PENDING" or state.get("pending") is not None)
        )
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("Invalid relay record; authority withheld")
    if state["schema"] == 1:
        state.update(
            schema=SCHEMA,
            policy_mode="relay-v1",
            inherited=None,
            candidates=None,
            health={},
            features=[],
            skill_version=None,
            brain_script=None,
            unplanned=0,
            announced=False,
            owned=[t for t in (state["director"].get("task_id"), (state.get("pending") or {}).get("task_id")) if t],
            handoffs=sum(1 for row in state["history"] if row.get("event") == "HANDOFF"),
        )
    for name, default in (
        ("health", {}),
        ("features", []),
        ("unplanned", 0),
        ("handoffs", 0),
        ("owned", []),
        ("announced", False),
        ("readiness", "unverified"),
    ):
        state.setdefault(name, copy.deepcopy(default))
    return state


def _write(B, root, state):
    state["schema"] = SCHEMA
    state["history"] = state["history"][-MAX_HISTORY:]
    state["owned"] = state["owned"][-50:]
    Core.write_atomic(_path(B, root), json.dumps(state, sort_keys=True, indent=2, allow_nan=False))


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
    result = {
        "status": state["status"],
        "generation": state["generation"],
        "director": {k: director.get(k) for k in ("route", "model", "effort", "task_id")},
        "director_since": _iso(director["since"]),
        "handoffs": state["handoffs"],
        "unplanned_in_a_row": state["unplanned"],
        "readiness": state["readiness"],
        "features": state["features"],
        "guarantees": guarantees(state["features"], state["readiness"]),
        "health": {
            k: {
                "status": v.get("status"),
                "checked_at": _iso(v.get("checked_at")),
                "failures": v.get("failures", 0),
                "reason": v.get("reason"),
            }
            for k, v in sorted(state["health"].items())
        },
    }
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
    if isinstance(last, dict):
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
        last = state["history"][-1] if state["history"] and isinstance(state["history"][-1], dict) else {}
        return (
            "RELAY: EXHAUSTED since %s (%s). No director runs; user decides: `relay start` again or work normally."
            % (_iso(last.get("at")) or "?", state.get("reason") or "no ready candidate")
        )
    if state["status"] == "STOPPING":
        d = state["director"]
        return (
            "RELAY: STOPPING gen %d director %s%s; stop requested by %s. "
            "No new work; `relay stop` waits or forces after deadline."
            % (
                state["generation"],
                d["route"],
                "/" + d["model"] if d.get("model") else "",
                _iso(state.get("stop_deadline")) or "?",
            )
        )
    if state["status"] not in LIVE:
        return None
    d = state["director"]
    text = "RELAY: %s gen %d director %s%s since %s%s" % (
        state["status"],
        state["generation"],
        d["route"],
        "/" + d["model"] if d.get("model") else "",
        _iso(d["since"]),
        " (pool task " + d["task_id"] + ")" if d.get("task_id") else "",
    )
    if state.get("pending"):
        text += " -> pending " + state["pending"]["route"]
    return text + ". Another session must not run this project; use `relay stop` to end circulation."


# ---------------------------------------------------------------- authority

def _token_ok(token_hash, token=None):
    token = token if token is not None else os.environ.get(TOKEN_ENV, "")
    return bool(token_hash) and bool(TOKEN.fullmatch(token or "")) and secrets.compare_digest(_hash(token), token_hash)


def _holds(entry, token=None):
    return bool(entry) and _token_ok(entry.get("token_hash"), token)


def authorized(B, root, token=None):
    try:
        state = read(B, root)
    except ValueError:
        return False
    return bool(state and state["status"] == "ACTIVE" and _holds(state["director"], token))


def stopping_holder(B, root, token=None):
    try:
        state = read(B, root)
    except ValueError:
        return False
    return bool(state and state["status"] == "STOPPING" and _holds(state["director"], token))


def require_free_or_director(B, root, allow_stopping=False):
    """Single-director gate used before mutating or implementation work."""
    state = read(B, root)
    if state and state["status"] == "STOPPING":
        if _holds(state["director"]):
            if allow_stopping:
                return
            raise ValueError(
                "RELAY_STOP_REQUESTED: save Resume/next step now, "
                'then run `relay complete --note "stopped by user"` before %s and end.'
                % (_iso(state.get("stop_deadline")) or "the deadline")
            )
        raise ValueError("RELAY_ACTIVE: " + (boot_line(B, root) or "a relay director is stopping"))
    if state and state["status"] in LIVE and not _holds(state["director"]):
        raise ValueError("RELAY_ACTIVE: " + (boot_line(B, root) or "a relay director owns this project"))


def worker_reserve(B, root, policy):
    return E.relay_worker_reserve(policy)


# ---------------------------------------------------------------- quota

def _scope_matches(scope, model):
    """Token-boundary model scope matcher (prevents false matches like 'pro' in 'project-model')."""
    if not isinstance(scope, str) or not isinstance(model, str):
        return False
    s = scope.strip().lower()
    m = model.strip().lower()
    if not s or not m:
        return False
    if s == m:
        return True
    if s == "gemini-flash" and m.startswith("gemini") and re.search(r"(?:^|[-_/.])flash(?:$|[-_/.])", m):
        return True
    if s == "gemini-pro" and m.startswith("gemini") and re.search(r"(?:^|[-_/.])pro(?:$|[-_/.])", m):
        return True
    if re.search(r"(?:^|[-_/.])" + re.escape(s) + r"(?:$|[-_/.])", m):
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
            return {
                "status": "HANDOFF_REQUIRED",
                "remaining_percent": 0,
                "threshold_percent": relay["threshold_percent"],
                "reason": snapshot.get("status"),
            }
        if snapshot.get("offline") or snapshot.get("networkError"):
            return {
                "status": "UNKNOWN",
                "threshold_percent": relay["threshold_percent"],
                "offline": True,
                "reason": "network offline; continue carefully and re-check later",
            }
    value = remaining(snapshot, model)
    if value is None:
        return {
            "status": "UNKNOWN",
            "threshold_percent": relay["threshold_percent"],
            "reason": "no applicable quota window; continue carefully and re-check later",
        }
    threshold = relay["threshold_percent"]
    result = {
        "status": "HANDOFF_REQUIRED" if value <= threshold else "READY",
        "remaining_percent": value,
        "threshold_percent": threshold,
    }
    if threshold < value <= threshold + PREPARE_MARGIN:
        result["prepare_checkpoint"] = True
    return result


def fetch_quotas(rpc, candidates):
    quotas = {}
    for route in sorted({c["route"] for c in candidates}):
        try:
            quotas[route] = rpc("pool_get_quotas", {"routeId": route})
        except (ValueError, OSError):
            quotas[route] = None
    return quotas


def choose(policy, quotas, current_route, candidates=None, health=None, current_model=None, allow_current=False, exclude=()):
    """Next ready candidate after the current one with quota above the threshold."""
    relay, _ = _policy(policy)
    candidates = relay.get("candidates", []) if candidates is None else candidates
    health = health or {}
    current = next(
        (
            i
            for i, c in enumerate(candidates)
            if c["route"] == current_route and (current_model is None or c.get("model") == current_model)
        ),
        None,
    )
    if current is None:
        current = next((i for i, c in enumerate(candidates) if c["route"] == current_route), -1)
    ordered = candidates[current + 1 :] + candidates[: max(current, 0)]
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
    return {
        "status": "EXHAUSTED",
        "skipped": skipped,
        "advice": "No ready candidate has quota above the threshold; wait (QRP if enabled) or stop the relay.",
    }


# ---------------------------------------------------------------- CAP discovery and tiers

def features(rpc):
    try:
        caps = rpc("pool_capabilities", {})
    except (ValueError, OSError):
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
    return [
        m
        for m in rows
        if isinstance(m.get("routeId"), str)
        and isinstance(m.get("modelId"), str)
        and "write" in (m.get("kinds") or ["write"])
    ]


def resolve_candidates(relay, route, model, rpc):
    """Concrete {route, model, effort} director candidates, resolved once and frozen."""
    if relay.get("candidates"):
        return copy.deepcopy(relay["candidates"])
    category = relay.get("director_category", "same")
    if rpc is None:
        raise ValueError("RELAY_TIER_UNRESOLVED: a director category needs CLI Agent Pool")
    groups = (
        [category]
        if category != "same"
        else [c["id"] for c in (rpc("pool_list_pools", {}) or {}).get("categories") or [] if isinstance(c, dict) and c.get("id")]
    )
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
        raise ValueError(
            "RELAY_TIER_UNRESOLVED: %s matches no CAP category model; name a category or list candidates"
            % ("the launcher " + route + ("/" + model if model else "") if category == "same" else "category " + category)
        )
    return result


# ---------------------------------------------------------------- readiness

def _preflight_request(root, candidate, script):
    skill_root = str(Path(script).resolve().parent.parent)
    request = {
        "routeId": candidate["route"],
        "workspace": str(Path(root).resolve()),
        "readPaths": [skill_root],
        "capabilities": list(CAPABILITIES),
    }
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
    return {
        "status": "ready" if ready else "unhealthy",
        "checked_at": now,
        "reason": None if ready else ("NOT_READY " + "; ".join(problems or ["not ready"]))[:300],
    }


def preflight(B, root, candidate, rpc, feats, script, now=None, sleep=time.sleep, status_only=False):
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
                result = (
                    task.get("preflight")
                    if isinstance(task.get("preflight"), dict)
                    else {"ready": False, "error": "preflight ended %s %s" % (task.get("state"), task.get("error") or "")}
                )
                break
            if time.monotonic() > deadline:
                result = {"ready": False, "error": "preflight did not finish in time"}
                break
            sleep(5)
    except (ValueError, OSError) as exc:
        return {"status": "unhealthy", "checked_at": now, "reason": "PREFLIGHT " + str(exc)[:250]}
    return _health_from(result, now)


def _merge_health(state, name, record):
    old = state["health"].get(name, {})
    merged = dict(old, **record)
    if record.get("status") == "unhealthy":
        merged["failures"] = old.get("failures", 0) + 1
    state["health"][name] = merged


def _failure(state, candidate, reason):
    name = key(candidate)
    old = state["health"].get(name, {})
    failures = old.get("failures", 0) + 1
    hard = any(word in (reason or "").upper() for word in HARD)
    state["health"][name] = dict(
        old,
        failures=failures,
        reason=(reason or "failed")[:300],
        status="unhealthy" if hard or failures >= 2 else old.get("status", "unknown"),
    )


def _progress(state, now):
    state["unplanned"] = 0
    state["director"]["progress_at"] = now
    candidate = {"route": state["director"]["route"], "model": state["director"].get("model")}
    entry = state["health"].get(key(candidate))
    if entry:
        entry["failures"] = 0


# ---------------------------------------------------------------- policy adoption (RPCs outside lock)

def _prepare_adoption_candidates(B, root, state, policy, rpc):
    """Pre-resolve new candidates OUTSIDE checkout_lock when a confirmed policy edit changed relay."""
    if not state or policy is None:
        return None
    if digest(policy) == state["policy_hash"] or not E.receipt_matches_file(B, root):
        return None
    relay = policy.get("relay") if isinstance(policy, dict) else None
    if not isinstance(relay, dict) or relay.get("enabled") is not True:
        return None
    old_relay = (state.get("inherited") or {}).get("relay")
    if validate_policy(relay) == (validate_policy(old_relay) if isinstance(old_relay, dict) else None):
        return None
    director = state["director"]
    try:
        return resolve_candidates(validate_policy(relay), director["route"], director.get("model"), rpc)
    except (ValueError, OSError) as exc:
        return ("ERROR", str(exc)[:200])


def _adopt(B, root, state, policy, rpc, now, resolved_candidates=None):
    """Apply confirmed mid-relay policy edits inside checkout_lock (no network RPCs inside)."""
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
        if isinstance(resolved_candidates, tuple) and len(resolved_candidates) == 2 and resolved_candidates[0] == "ERROR":
            _event(state, "POLICY_ADOPTED", now, note="candidates kept: " + resolved_candidates[1])
            return []
        if resolved_candidates is not None:
            state["candidates"] = resolved_candidates
        elif relay.get("candidates"):
            state["candidates"] = copy.deepcopy(relay["candidates"])
    _event(state, "POLICY_ADOPTED", now)
    return []


def _cancel_all(rpc, task_ids):
    done = []
    for task_id in task_ids:
        try:
            rpc("pool_cancel_task", {"taskId": task_id})
            done.append(task_id)
        except (ValueError, OSError):
            pass
    return done


# ---------------------------------------------------------------- start

def _checkpoint(B, root, task, next_step):
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
    except OSError:
        return None
    return value if isinstance(value, dict) else None


def guarantees(feats, readiness):
    return {
        "readiness": readiness,
        "watchdog": "on (needs the CAP service running)" if "onExit" in feats else "unavailable: a dead director is not restarted automatically",
        "takeover_deadline": "CAP-enforced" if "ack" in feats else "checked when recover runs",
        "lock_release": "automatic" if "releaseLockOnFailure" in feats else ("resolved by recover" if "resolve" in feats else "manual `cli-agent-pool resolve`"),
        "hang_detection": "CAP idle timeout" if "idle" in feats else "12 h task timeout only",
        "authority": "token via CAP secretEnv" if "secretEnv" in feats else "baton token in prompt",
        "quota_barrier": "CAP-enforced" if "quotaBarrier" in feats else "relay assess only",
        "wake_schedule": "CAP wakeAt" if "wakeAt" in feats else "timer/cron polling",
        "predecessor_cleanup": "CAP supersede" if "supersede" in feats else "takeover cancellation",
    }


def start(
    B,
    root,
    policy,
    route,
    model=None,
    effort=None,
    task_id=None,
    rpc=None,
    brain_script=None,
    now=None,
    unverified=False,
    sleep=time.sleep,
    version=None,
):
    relay, policy_hash = _policy(policy)
    now = time.time() if now is None else now
    route = _name(route, "Relay route")
    if route is None:
        raise ValueError("The current director route is required")
    state = read(B, root)
    if state and state["status"] in BLOCKING:
        orig_gen = state["generation"]
        orig_dir_hash = state["director"]["token_hash"]
        orig_pending_hash = (state.get("pending") or {}).get("token_hash")
        holder = _task(rpc, state["director"].get("task_id")) if rpc else None
        pending = state.get("pending")
        pending_task = _task(rpc, pending.get("task_id")) if rpc and pending else None
        if not (
            holder
            and holder.get("state") in TERMINAL_TASK | {"not_found"}
            and (not pending or (pending_task and pending_task.get("state") in TERMINAL_TASK | {"not_found"}))
        ):
            raise ValueError("RELAY_ACTIVE: a live director owns this project; use `relay recover` or `relay stop`")
        with B.checkout_lock(root):
            stale = read(B, root)
            if (
                stale
                and stale["status"] in BLOCKING
                and stale["generation"] == orig_gen
                and stale["director"]["token_hash"] == orig_dir_hash
                and (stale.get("pending") or {}).get("token_hash") == orig_pending_hash
            ):
                stale.update(status="STOPPED", pending=None)
                _event(stale, "STALE_RESET", now, note="holder and pending tasks had ended")
                _write(B, root, stale)
            elif stale and stale["status"] in BLOCKING:
                raise ValueError("RELAY_ACTIVE: another director started meanwhile")
    feats = features(rpc) if rpc else []
    if "preflight" not in feats and not unverified:
        raise ValueError(
            "RELAY_NOT_READY: CLI Agent Pool has no director preflight (pb-director/1); "
            "update CAP, or start with --unverified to accept unchecked candidates"
        )
    candidates = resolve_candidates(relay, route, model, rpc)
    script = brain_script or str(Path(__file__).resolve().parent / "brain.py")
    version = version or getattr(B, "VERSION", None)
    health = {key(c): preflight(B, root, c, rpc, feats, script, now, sleep) for c in candidates}
    table = [{"candidate": key(c), "status": health[key(c)]["status"], "reason": health[key(c)].get("reason")} for c in candidates]
    if "preflight" in feats and not any(h["status"] == "ready" for h in health.values()):
        raise ValueError("RELAY_NOT_READY: no candidate passed preflight: " + json.dumps(table, ensure_ascii=False))
    token = secrets.token_hex(16)
    with B.checkout_lock(root):
        if (read(B, root) or {}).get("status") in BLOCKING:
            raise ValueError("RELAY_ACTIVE: another director started meanwhile")
        new = {
            "schema": SCHEMA,
            "status": "ACTIVE",
            "policy_hash": policy_hash,
            "inherited": copy.deepcopy(policy),
            "generation": 1,
            "handoffs": 0,
            "unplanned": 0,
            "announced": False,
            "readiness": "verified" if "preflight" in feats else "unverified",
            "skill_version": version,
            "brain_script": script,
            "candidates": candidates,
            "health": health,
            "features": feats,
            "owned": [task_id] if task_id else [],
            "director": {
                "route": route,
                "model": _name(model, "Relay model"),
                "effort": _name(effort, "Relay effort"),
                "task_id": _name(task_id, "Pool task id"),
                "token_hash": _hash(token),
                "since": now,
            },
            "pending": None,
            "history": [],
        }
        _event(new, "START", now, route=route, model=model, threshold=relay["threshold_percent"])
        _write(B, root, new)
    return dict(
        view(new),
        token=token,
        token_env=TOKEN_ENV,
        preflight=table,
        guarantees=guarantees(feats, new["readiness"]),
        usage="Set %s=<token> (preferred) or pass --relay-token <token>." % TOKEN_ENV,
    )


# ---------------------------------------------------------------- successor launch

def successor_prompt(root, brain_script, token, generation, checkpoint, candidate, kind="HANDOFF"):
    pb = 'python "%s" <command> "%s"%s' % (brain_script, root, " --relay-token " + token if token else "")
    why = {
        "HANDOFF": "The previous director handed off at its quota threshold.",
        "FAILOVER": "The previously chosen successor failed; you are the next candidate.",
        "RECOVER": "The previous director stopped without a handoff; continue from the last checkpoint and classify any uncommitted changes before editing.",
    }[kind]
    where = ("the handoff checkpoint " + checkpoint) if checkpoint else "the active task Resume under .project-brain/tasks/"
    return (
        "Project Brain Baton Relay (BRP): you are the director, generation %d, for workspace %s. %s\n"
        "Run Project Brain as: %s\n"
        '1. First run `relay takeover`. Continue only if it returns "status": "ACTIVE". On any error do '
        "nothing else and end with a completed report saying takeover failed.\n"
        "2. Settings (ESP/SP, workers, thresholds) are inherited: do NOT ask setup questions, run boot "
        "--new-session, or repeat orientation, discovery or verification that the checkpoint and evidence record.\n"
        "3. Read %s, run `boot`, and continue the saved next step as director: plan, delegate through CLI Agent "
        "Pool per policy, verify, accept, commit as the project allows.\n"
        "4. At meaningful checkpoints run `relay assess`. On HANDOFF_REQUIRED run `relay handoff --task <id> "
        '--next "<actual next step>"`, then stop at once and end with a completed report "handed off".\n'
        "5. When every task is accepted run `relay complete`.\n"
        "Never log out, switch accounts, edit Pool/CLI credentials or start another director."
        % (generation, root, why, pb, where)
    )


def _commit_pending(
    B, root, expect, candidate, kind, checkpoint_fn, now, selection, health, planned, count=True, checkpoint_override=None
):
    with B.checkout_lock(root, timeout=90):
        state = read(B, root)
        if (
            not state
            or state["status"] not in LIVE
            or state["generation"] != expect["generation"]
            or (state.get("pending") or {}).get("token_hash") != expect["pending_hash"]
        ):
            raise ValueError("RELAY_CHANGED: the relay changed meanwhile; read it back with relay status")
        for name, record in health.items():
            _merge_health(state, name, record)
        old = state.get("pending") or {}
        checkpoint = (
            checkpoint_override
            if checkpoint_override is not None
            else (old.get("checkpoint") if kind == "FAILOVER" else state.get("last_checkpoint") if kind == "RECOVER" else None)
        )
        if kind == "RECOVER" and checkpoint:
            cp_file = Core.public_path(root, checkpoint["path"])
            if not cp_file.is_file():
                checkpoint = None
            else:
                checkpoint = {"path": checkpoint["path"], "sha256": Core.sha256_file(cp_file)}
        if checkpoint_fn:
            path = checkpoint_fn()
            checkpoint = {"path": path.relative_to(root).as_posix(), "sha256": Core.sha256_file(path)}
            state["last_checkpoint"] = checkpoint
        token = secrets.token_hex(16)
        suffix = secrets.token_hex(8)
        pending = {
            "candidate": candidate,
            "route": candidate["route"],
            "model": candidate.get("model"),
            "effort": candidate.get("effort"),
            "token_hash": _hash(token),
            "requested_at": now,
            "checkpoint": checkpoint,
            "task_id": None,
            "kind": kind,
            "idempotency_key": "pb-relay-%d-%s" % (state["generation"] + 1, suffix),
            "label": LABEL % (state["generation"] + 1, suffix),
            "running_seen_at": None,
            "quota_unknown": bool(selection.get("quota_unknown")),
            "from_generation": state["generation"],
        }
        state["pending"], state["status"] = pending, "HANDOFF_PENDING"
        if planned:
            state["handoffs"] += 1
        elif count:
            state["unplanned"] += 1
        _event(
            state,
            kind,
            now,
            route=candidate["route"],
            model=candidate.get("model"),
            quota_unknown=True if selection.get("quota_unknown") else None,
        )
        _write(B, root, state)
    return state, pending, token


def _send(B, root, state, pending, token, rpc, script):
    relay = validate_policy(state["inherited"]["relay"]) if state.get("inherited") else {"threshold_percent": 10}
    feats = state["features"]
    root_text = str(Path(root).resolve())
    prompt = successor_prompt(
        root_text,
        script,
        None if "secretEnv" in feats else token,
        state["generation"] + 1,
        (pending.get("checkpoint") or {}).get("path"),
        pending["candidate"],
        pending["kind"],
    )
    request = {
        "prompt": prompt,
        "workspace": root_text,
        "kind": "write",
        "mode": "execute",
        "routeId": pending["route"],
        "idempotencyKey": pending["idempotency_key"],
        "timeoutSeconds": DIRECTOR_TIMEOUT,
        "clientLabel": pending["label"],
    }
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
        request["onExit"] = {"argv": [sys.executable, script, "relay", "recover", root_text, "--from-hook"], "timeoutSeconds": 300}
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
            current["director"]["task_id"] = _name(task_id, "Pool task id")
            if task_id not in current["owned"]:
                current["owned"].append(task_id)
            _write(B, root, current)
    return task_id


def _select(B, root, state, policy, rpc, script, now, sleep, quotas=None, allow_current=False, planned=False, extra_exclude=None):
    candidates = _candidates(state, validate_policy(policy["relay"]))
    quotas = quotas if quotas is not None else fetch_quotas(rpc, candidates)
    health, exclude = copy.deepcopy(state["health"]), set(extra_exclude or ())
    updates = {}
    while True:
        selection = choose(
            policy,
            quotas,
            state["director"]["route"],
            candidates,
            health,
            state["director"].get("model"),
            allow_current,
            exclude,
        )
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


def _is_uncertain_submit_error(exc):
    msg = str(exc).lower()
    return any(w in msg for w in ("timed out", "timeout", "did not return json", "connection", "broken pipe"))


def handoff(
    B,
    root,
    policy,
    task,
    next_step,
    brain_script,
    rpc,
    candidate=None,
    quotas=None,
    now=None,
    token=None,
    write_checkpoint=_checkpoint,
    sleep=time.sleep,
    version=None,
):
    """Planned handoff: select, preflight, checkpoint, start the successor, record it."""
    now = time.time() if now is None else now
    if not isinstance(next_step, str) or not next_step.strip():
        raise ValueError("Save the actual next action before handing off")
    pre_state = read(B, root)
    resolved_cands = (
        _prepare_adoption_candidates(B, root, pre_state, policy, rpc)
        if pre_state and pre_state.get("status") in LIVE and _holds(pre_state.get("director"), token)
        else None
    )
    with B.checkout_lock(root, timeout=90):
        state = read(B, root)
        if not state or state["status"] not in LIVE:
            raise ValueError("RELAY_NOT_ACTIVE: start the relay first")
        if not _holds(state["director"], token):
            raise ValueError("RELAY_NOT_DIRECTOR: only the current baton holder can hand off")
        cancel = _adopt(B, root, state, policy, rpc, now, resolved_candidates=resolved_cands)
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
        # Reconcile an earlier uncertain submit via pool_list_tasks before creating a replacement successor.
        found_tasks, _ = _strays(state, rpc, root)
        matched = next(
            (r for r in found_tasks if r.get("clientLabel") == state["pending"].get("label") and r.get("id")),
            None,
        )
        if matched:
            found_id = _name(matched["id"], "Pool task id")
            with B.checkout_lock(root, timeout=90):
                cur = read(B, root)
                if cur and (cur.get("pending") or {}).get("token_hash") == state["pending"]["token_hash"]:
                    cur["pending"]["task_id"] = found_id
                    if found_id not in cur["owned"]:
                        cur["owned"].append(found_id)
                    _write(B, root, cur)
            return {
                "status": "HANDED_OFF",
                "successor": state["pending"]["candidate"],
                "pool_task": found_id,
                "checkpoint": (state["pending"].get("checkpoint") or {}).get("path"),
                "instruction": 'Stop working now and end your task with a completed report "handed off". '
                "You stay the holder until the successor confirms takeover.",
            }
        candidate = state["pending"]["candidate"]
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
    saved_cp = (state.get("pending") or {}).get("checkpoint")
    checkpoint_fn = None if state.get("pending") else (lambda: write_checkpoint(B, root, task, next_step))
    state, pending, successor = _commit_pending(
        B, root, expect, candidate, "HANDOFF", checkpoint_fn, now, selection, updates, planned=not expect["pending_hash"],
        checkpoint_override=saved_cp,
    )
    try:
        task_id = _send(B, root, state, pending, successor, rpc, brain_script)
    except (ValueError, OSError) as exc:
        if not _is_uncertain_submit_error(exc):
            with B.checkout_lock(root, timeout=90):
                cur = read(B, root)
                if cur and (cur.get("pending") or {}).get("token_hash") == pending["token_hash"] and not cur["pending"].get("task_id"):
                    _failure(cur, candidate, "SUBMISSION_REJECTED: " + str(exc)[:200])
                    cur["pending"] = None
                    cur["status"] = "ACTIVE"
                    if not expect["pending_hash"] and cur["handoffs"] > 0:
                        cur["handoffs"] -= 1
                    _write(B, root, cur)
        raise
    return {
        "status": "HANDED_OFF",
        "successor": candidate,
        "pool_task": task_id,
        "checkpoint": (pending.get("checkpoint") or {}).get("path"),
        "instruction": 'Stop working now and end your task with a completed report "handed off". '
        "You stay the holder until the successor confirms takeover.",
    }


# ---------------------------------------------------------------- takeover

def _version(text):
    return tuple(int(p) for p in re.findall(r"\d+", text or "")[:3]) or (0,)


def takeover(B, root, policy, rpc, token=None, now=None, version=None):
    """Successor confirms the baton; stops the previous director task if still live."""
    now = time.time() if now is None else now
    version = version or getattr(B, "VERSION", None)
    pre_state = read(B, root)
    resolved_cands = (
        _prepare_adoption_candidates(B, root, pre_state, policy, rpc)
        if pre_state and pre_state.get("status") == "HANDOFF_PENDING" and _holds(pre_state.get("pending"), token)
        else None
    )
    cancel_on_stop = []
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
        cancel_on_stop = _adopt(B, root, state, policy, rpc, now, resolved_candidates=resolved_cands)
        if state["status"] not in LIVE:
            _write(B, root, state)
        else:
            if state.get("skill_version") and _version(version) < _version(state["skill_version"]):
                _failure(state, pending["candidate"], "RELAY_SKILL_OLD running %s < %s" % (version, state["skill_version"]))
                _write(B, root, state)
                raise ValueError("RELAY_SKILL_OLD: this Project Brain is older than the relay's; do no work")
            if pending.get("checkpoint"):
                checkpoint = Core.public_path(root, pending["checkpoint"]["path"])
                if not checkpoint.is_file() or Core.sha256_file(checkpoint) != pending["checkpoint"]["sha256"]:
                    if pending.get("kind") in ("RECOVER", "FAILOVER"):
                        _event(state, "CHECKPOINT_DEVIATION", now, path=pending["checkpoint"]["path"])
                        pending["checkpoint"] = None
                    else:
                        raise ValueError("RELAY_CHECKPOINT_CHANGED: handoff checkpoint changed; ask the user")
            previous = state["director"]
            state["director"] = {
                "route": pending["route"],
                "model": pending.get("model"),
                "effort": pending.get("effort"),
                "task_id": pending.get("task_id"),
                "token_hash": pending["token_hash"],
                "since": now,
            }
            if version and _version(version) > _version(state.get("skill_version")):
                state["skill_version"] = version
            state["generation"] += 1
            state["pending"], state["status"], state["announced"] = None, "ACTIVE", False
            state.pop("reason", None)
            state["health"].setdefault(key(pending["candidate"]), {}).update(status="ready", reason=None)
            _event(
                state,
                "TAKEOVER",
                now,
                route=pending["route"],
                model=pending.get("model"),
                previous_route=previous["route"],
                previous_task=previous.get("task_id"),
            )
            _write(B, root, state)
    if state["status"] not in LIVE:
        if cancel_on_stop:
            _cancel_all(rpc, cancel_on_stop)
        raise ValueError("RELAY_STOPPED: the user disabled the relay; do no work")
    if "ack" in state["features"] and pending.get("task_id"):
        try:
            rpc("pool_ack_task", {"taskId": pending["task_id"]})
        except (ValueError, OSError):
            pass
    cancelled = False
    previous_task = previous.get("task_id")
    if previous_task:
        observed = _task(rpc, previous_task)
        if observed and observed.get("state") in ("queued", "starting", "running"):
            cancelled = bool(_cancel_all(rpc, [previous_task]))
    return dict(
        view(state),
        previous_director_cancelled=cancelled,
        checkpoint=(pending.get("checkpoint") or {}).get("path"),
    )


# ---------------------------------------------------------------- recover

def _notify(state):
    return "CAP_NOTIFY Project Brain relay EXHAUSTED for %s: %s" % (
        state.get("workspace") or "this project",
        state.get("reason") or "no ready candidate",
    )


def _resolve_owned(state, rpc, observed):
    actions = []
    for task_id in state["owned"]:
        info = observed.get(task_id) if task_id in observed else _task(rpc, task_id)
        if not info or info.get("state") != "needs_review":
            continue
        if "resolve" in state["features"]:
            try:
                rpc(
                    "pool_resolve_task",
                    {
                        "taskId": task_id,
                        "reviewed": True,
                        "note": "Project Brain relay: next director classifies the dirty tree at boot",
                    },
                )
                actions.append("resolved " + task_id)
                continue
            except (ValueError, OSError):
                pass
        actions.append("run: cli-agent-pool resolve " + task_id)
    return actions


def _relay_owned(state, rpc, task_id):
    if task_id in state["owned"]:
        return True
    info = _task(rpc, task_id)
    return bool(info and info.get("parentTaskId") in state["owned"])


def _strays(state, rpc, root):
    try:
        rows = rpc("pool_list_tasks", {"limit": 100})
    except (ValueError, OSError):
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
        if row.get("state") in ACTIVE_TASK and row.get("id") not in keep and row.get("clientLabel") != pending_label:
            strays.append(row["id"])
    return found, strays


def _earliest_limiting_reset(state, policy, rpc, now, allow_current=True):
    """Earliest future reset across selectable HEALTHY candidates: max(limiting windows) per candidate, min across candidates."""
    pol = state.get("inherited") or policy
    if not isinstance(pol, dict) or not isinstance(pol.get("relay"), dict):
        return None
    relay = validate_policy(pol["relay"])
    threshold = relay["threshold_percent"]
    cur_dir = state.get("director") or {}
    cur_key = (cur_dir.get("route"), cur_dir.get("model"))
    candidates = [
        c for c in _candidates(state, relay)
        if state["health"].get(key(c), {}).get("status") != "unhealthy"
        and (allow_current or (c.get("route"), c.get("model")) != cur_key)
    ]
    if not candidates:
        return None
    quotas = fetch_quotas(rpc, candidates)
    earliest = None
    for cand in candidates:
        q_data = quotas.get(cand["route"])
        if not isinstance(q_data, dict):
            continue
        if q_data.get("status") in ("auth_required", "subscription_required", "credits_required"):
            continue
        cand_max = None
        valid_cand = True
        for w in q_data.get("windows") or []:
            if not isinstance(w, dict) or not _number(w.get("remainingPercent")):
                continue
            scopes = w.get("models")
            if cand.get("model") and isinstance(scopes, list) and scopes and not any(_scope_matches(s, cand["model"]) for s in scopes):
                continue
            if w["remainingPercent"] > threshold:
                continue
            raw_reset = w.get("resetAt")
            if not raw_reset:
                valid_cand = False
                break
            try:
                t_epoch = Core.parse_iso_utc(raw_reset) if isinstance(raw_reset, str) else float(raw_reset)
            except (ValueError, TypeError):
                valid_cand = False
                break
            if t_epoch <= now:
                valid_cand = False
                break
            cand_max = max(cand_max, t_epoch) if cand_max is not None else t_epoch
        if valid_cand and cand_max is not None:
            earliest = min(earliest, cand_max) if earliest is not None else cand_max
    return earliest


def recover(B, root, policy, rpc, brain_script=None, now=None, sleep=time.sleep, version=None, from_hook=False):
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
            announced_now = False
            with B.checkout_lock(root, timeout=90):
                current = read(B, root)
                if current and current["status"] == "EXHAUSTED" and not current["announced"]:
                    current["announced"] = True
                    _write(B, root, current)
                    announced_now = True
                    state = current
            if announced_now:
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
                    if current and (current.get("pending") or {}).get("token_hash") == pending["token_hash"]:
                        current["pending"]["task_id"] = match["id"]
                        current["owned"].append(match["id"])
                        _write(B, root, current)
                        state = current
                        pending = current["pending"]
                actions.append("found successor task " + match["id"])
                info = match
                observed[match["id"]] = match
                if match.get("state") in TERMINAL_TASK | {"not_found"}:
                    error = str(match.get("error") or match.get("state"))
                    if not any(w in error.upper() for w in ("START_TIMEOUT", "QUOTA_BARRIER", "QUOTA_EXHAUSTED", "SUPERSEDED_BY_HANDOFF")):
                        failure = (pending["candidate"], "successor ended without takeover: " + error)
                    holder = observed.get(director.get("task_id")) if director.get("task_id") else None
                    if holder and holder.get("state") in ACTIVE_TASK:
                        cancel.append(director["task_id"])
                    plan = "FAILOVER"
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
                cancel.append(director["task_id"])
            plan = "FAILOVER"
        elif info.get("state") in ("starting", "running"):
            seen = pending.get("running_seen_at")
            minutes = (
                validate_policy(state["inherited"]["relay"]).get("takeover_minutes", TAKEOVER_MINUTES)
                if state.get("inherited")
                else TAKEOVER_MINUTES
            )
            if seen is None:
                with B.checkout_lock(root, timeout=90):
                    current = read(B, root)
                    if current and (current.get("pending") or {}).get("token_hash") == pending["token_hash"]:
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
                        if current and blocker not in current["owned"]:
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
    elif str(state.get("reason") or "").startswith("waiting quota renewal until "):
        # Resume gen-1 host handoff that rolled back and scheduled a wakeAt retry.
        plan = "RECOVER"
    actions += ["cancelled " + t for t in _cancel_all(rpc, cancel)]
    actions += _resolve_owned(state, rpc, observed)
    if plan is None:
        return dict(view(state), actions=actions, notify=None)
    resolved_cands = _prepare_adoption_candidates(B, root, state, policy, rpc)
    expect = {"generation": state["generation"], "pending_hash": (pending or {}).get("token_hash")}
    with B.checkout_lock(root, timeout=90):
        current = read(B, root)
        if (
            not current
            or current["status"] not in LIVE
            or current["generation"] != expect["generation"]
            or (current.get("pending") or {}).get("token_hash") != expect["pending_hash"]
        ):
            return dict(view(current), actions=actions + ["relay changed meanwhile; nothing to do"], notify=None)
        stop = _adopt(B, root, current, policy, rpc, now, resolved_candidates=resolved_cands)
        holder_tid_lock = director.get("task_id")
        holder_info_lock = observed.get(holder_tid_lock) if holder_tid_lock else None
        if failure:
            _failure(current, failure[0], failure[1])
        if (
            plan == "FAILOVER"
            and holder_info_lock
            and holder_info_lock.get("state") in TERMINAL_TASK | {"not_found"}
        ):
            h_err = str(holder_info_lock.get("error") or holder_info_lock.get("state") or "")
            if any(word in h_err.upper() for word in HARD):
                _failure(
                    current,
                    {"route": director["route"], "model": director.get("model")},
                    "director ended: " + h_err,
                )
        reason = state.get("reason") if plan == "EXHAUSTED" else None
        recent_recovers = 0
        for ev in reversed(current.get("history", [])):
            if ev.get("event") in ("FAILOVER", "RECOVER"):
                recent_recovers += 1
            else:
                break
        if current["status"] in LIVE and plan != "EXHAUSTED" and current["unplanned"] >= UNPLANNED_LIMIT:
            plan, reason = "EXHAUSTED", "%d unplanned transfers in a row without progress" % current["unplanned"]
        elif current["status"] in LIVE and plan != "EXHAUSTED" and recent_recovers >= 12:
            plan, reason = "EXHAUSTED", "%d consecutive recovery transfers without takeover or progress" % recent_recovers
        _write(B, root, current)
        state = current
    actions += ["cancelled " + t for t in _cancel_all(rpc, stop)]
    if state["status"] not in LIVE:
        return dict(view(state), actions=actions, notify=None)
    if plan != "EXHAUSTED":
        hard = bool(failure and any(word in failure[1].upper() for word in HARD))
        holder_tid = director.get("task_id")
        holder_info = observed.get(holder_tid) if holder_tid else None
        holder_terminal = (not holder_tid) or bool(holder_info and holder_info.get("state") in TERMINAL_TASK | {"not_found"})
        holder_error = str((holder_info or {}).get("error") or (holder_info or {}).get("state") or "")
        holder_failed_hard = bool(
            holder_info
            and holder_info.get("state") in TERMINAL_TASK | {"not_found"}
            and any(word in holder_error.upper() for word in HARD)
        )
        director_failed_hard = holder_failed_hard or bool(hard and failure and failure[0].get("route") == director.get("route"))
        allow_cur = (plan == "RECOVER" and not hard) or (plan == "FAILOVER" and holder_terminal and not director_failed_hard)
        selection, updates = _select(
            B, root, state, state.get("inherited") or policy, rpc, script, now, sleep, allow_current=allow_cur
        )
        attempts = 0
        tried = set()
        saved_checkpoint = (pending or {}).get("checkpoint") if plan == "FAILOVER" else state.get("last_checkpoint")
        while selection["status"] == "SELECTED" and attempts < 32:
            attempts += 1
            if state["unplanned"] >= UNPLANNED_LIMIT:
                reason = "%d unplanned transfers in a row without progress" % state["unplanned"]
                break
            cand = selection["candidate"]
            tried.add(key(cand))
            counted_this_attempt = bool(failure)
            try:
                state, new_pending, token = _commit_pending(
                    B, root, expect, cand, plan, None, now, selection, updates, planned=False, count=counted_this_attempt,
                    checkpoint_override=saved_checkpoint,
                )
            except ValueError as exc:
                actions.append("relay changed during commit: " + str(exc)[:120])
                return dict(view(read(B, root)), actions=actions, notify=None)
            try:
                task_id = _send(B, root, state, new_pending, token, rpc, script)
                return dict(
                    view(read(B, root)),
                    actions=actions + ["%s to %s (task %s)" % (plan, key(cand), task_id)],
                    notify=None,
                )
            except (ValueError, OSError) as exc:
                if _is_uncertain_submit_error(exc):
                    # Preserve pending + label/idempotency_key so a subsequent recover reconciles via pool_list_tasks.
                    actions.append("uncertain submit for %s: %s (preserved for reconciliation)" % (key(cand), str(exc)[:120]))
                    return dict(view(read(B, root)), actions=actions, notify=None)
                actions.append("rejected %s: %s" % (key(cand), str(exc)[:120]))
                with B.checkout_lock(root, timeout=90):
                    cur = read(B, root)
                    if cur and (cur.get("pending") or {}).get("token_hash") == new_pending["token_hash"]:
                        _failure(cur, cand, "SUBMISSION_REJECTED: " + str(exc)[:200])
                        cur["pending"] = None
                        cur["status"] = "ACTIVE"
                        if counted_this_attempt and cur["unplanned"] > 0:
                            cur["unplanned"] -= 1
                        _write(B, root, cur)
                        state = cur
                        expect = {"generation": cur["generation"], "pending_hash": None}
                    else:
                        return dict(view(cur), actions=actions + ["relay changed during rollback"], notify=None)
                selection, updates = _select(
                    B, root, state, state.get("inherited") or policy, rpc, script, now, sleep, allow_current=False, extra_exclude=tried
                )
        else:
            reason = reason or "no ready candidate has quota above the threshold"
        if "wakeAt" in state["features"] and from_hook and not (state["unplanned"] >= UNPLANNED_LIMIT):
            earliest_reset = _earliest_limiting_reset(state, policy, rpc, now, allow_current=allow_cur)
            if earliest_reset:
                wake_seconds = max(60, min(3600, int(earliest_reset - now + 15)))
                wake_iso = _iso(now + wake_seconds)
                with B.checkout_lock(root, timeout=90):
                    cur = read(B, root)
                    if (
                        cur
                        and cur["generation"] == expect["generation"]
                        and cur["status"] in LIVE
                        and (cur.get("pending") or {}).get("token_hash") == expect["pending_hash"]
                    ):
                        cur["reason"] = "waiting quota renewal until " + wake_iso
                        _write(B, root, cur)
                    else:
                        return dict(view(cur), actions=actions + ["relay changed before wake scheduling"], notify=None)
                return dict(
                    view(read(B, root)),
                    actions=actions + ["waiting quota renewal until " + wake_iso],
                    wake_at=wake_iso,
                    retry_after=wake_seconds,
                    exit_code=75,
                )
    to_cancel = []
    exhausted_now = False
    with B.checkout_lock(root, timeout=90):
        current = read(B, root)
        if (
            current
            and current["generation"] == expect["generation"]
            and current["status"] in LIVE
            and (current.get("pending") or {}).get("token_hash") == expect["pending_hash"]
        ):
            pend_tid = (current.get("pending") or {}).get("task_id")
            if pend_tid and pend_tid not in cancel and (observed.get(pend_tid) or {}).get("state") in ACTIVE_TASK:
                to_cancel.append(pend_tid)
            current.update(status="EXHAUSTED", pending=None, reason=reason, announced=True)
            _event(current, "EXHAUSTED", now, note=reason)
            _write(B, root, current)
            exhausted_now = True
        state = current
    if to_cancel:
        _cancel_all(rpc, to_cancel)
    if not exhausted_now:
        return dict(view(state), actions=actions + ["relay changed before exhaustion; nothing to do"], notify=None)
    return dict(view(state), actions=actions, notify=_notify(dict(state, workspace=str(Path(root).resolve()))))


# ---------------------------------------------------------------- finish

def finish(B, root, event, note, rpc=None, token=None, now=None, expected_gen=None):
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
        if expected_gen is not None and state["generation"] != expected_gen:
            return None
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
    use_wall = now is None
    now = clock() if use_wall else now
    note = (note or "User stopped the relay")[:500]
    S.require_public(note, "relay note")
    state = read(B, root)
    if not state or state["status"] not in BLOCKING or force:
        return finish(B, root, "STOP", note, rpc=rpc, now=now)
    observed_gen = state["generation"]
    holder = _task(rpc, state["director"].get("task_id")) if rpc and state["director"].get("task_id") else None
    if holder and holder.get("state") in TERMINAL_TASK | {"not_found"}:
        done = finish(B, root, "STOP", note + " (director already ended)", rpc=rpc, now=now, expected_gen=observed_gen)
        if done is not None:
            return done
        state = read(B, root) or state
    cancel = []
    if state["status"] != "STOPPING":
        transitioned = False
        with B.checkout_lock(root, timeout=90):
            state = read(B, root)
            if not state or state["status"] not in BLOCKING:
                return view(state)
            if state["status"] in LIVE:
                pending = state.get("pending") or {}
                cancel = [pending["task_id"]] if pending.get("task_id") else []
                state.update(status="STOPPING", pending=None, stop_deadline=now + STOP_GRACE)
                _event(state, "STOP_REQUESTED", now, note=note)
                _write(B, root, state)
                transitioned = True
        if rpc and cancel:
            _cancel_all(rpc, cancel)
        if transitioned:
            return dict(
                view(state),
                seconds_left=STOP_GRACE,
                cancelled=cancel,
                next="run `relay stop` again to wait (at most 60 s per call); it forces after the deadline",
            )
    slice_start = now
    waited = 0
    while True:
        cur_time = clock() if (use_wall or clock is not time.time) else (slice_start + waited)
        left = (state.get("stop_deadline") or 0) - cur_time
        if left <= 0:
            return finish(B, root, "STOP", note + " (grace period elapsed)", rpc=rpc, now=cur_time)
        if (cur_time - slice_start) >= STOP_SLICE or waited >= STOP_SLICE:
            return dict(view(state), seconds_left=int(left))
        step = min(5, left, STOP_SLICE - waited)
        sleep(step)
        waited += step
        state = read(B, root)
        if not state or state["status"] != "STOPPING":
            return view(state)
        if rpc and state["director"].get("task_id"):
            holder = _task(rpc, state["director"]["task_id"])
            if holder and holder.get("state") in TERMINAL_TASK | {"not_found"}:
                return finish(B, root, "STOP", note + " (director ended during grace)", rpc=rpc, now=cur_time + step)


def mark_progress(B, root, policy, rpc, now=None):
    now = time.time() if now is None else now
    pre_state = read(B, root)
    resolved_cands = (
        _prepare_adoption_candidates(B, root, pre_state, policy, rpc)
        if pre_state and pre_state.get("status") == "ACTIVE" and _holds(pre_state.get("director"))
        else None
    )
    with B.checkout_lock(root, timeout=90):
        state = read(B, root)
        if not state or state["status"] != "ACTIVE" or not _holds(state["director"]):
            return state
        cancel = _adopt(B, root, state, policy, rpc, now, resolved_candidates=resolved_cands)
        _progress(state, now)
        _write(B, root, state)
    if cancel:
        _cancel_all(rpc, cancel)
    return state


# ---------------------------------------------------------------- CLI

def add_parser(sub):
    p = sub.add_parser("relay", help="Baton Relay Policy: director circulation across CAP accounts")
    p.add_argument("action", choices=("status", "start", "assess", "next", "handoff", "takeover", "complete", "stop", "recover"))
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


def _read_local_json(root, name):
    return Core.read_json(Core.public_path(root, name), max_bytes=65536, strict_constants=True, unique_keys=True)


def command(B, args, pool=None):
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise ValueError("Project directory required")
    if args.action == "status":
        return status(B, root)
    pool = pool or AP
    rpc = pool.rpc
    if args.action == "stop":
        if Core.worker_env_active() and not (authorized(B, root) or stopping_holder(B, root)):
            raise ValueError("Workers cannot stop another director's relay")
        return request_stop(B, root, args.note or "User stopped the relay", rpc=rpc, force=getattr(args, "force", False))
    policy = E.load(B, root)
    script = str(Path(__file__).resolve().parent / "brain.py")
    if args.action == "recover":
        if Core.worker_env_active() and not authorized(B, root):
            raise ValueError("Workers cannot invoke relay recover directly")
        try:
            res = recover(B, root, policy, rpc, script, from_hook=bool(args.from_hook))
            if args.from_hook and res.get("wake_at") and res.get("retry_after"):
                print("CAP_WAKE_AT " + res["wake_at"])
                print("CAP_RETRY_AFTER %d" % int(res["retry_after"]))
            return res
        except ValueError as exc:
            if args.from_hook:
                print("CAP_RETRY_AFTER 30")
                return {"status": "RETRY", "error": str(exc)[:300], "exit_code": 75}
            raise
    if args.action == "takeover":
        return takeover(B, root, policy, rpc)
    E.require_confirmed(B, root)
    if args.action == "assess":
        if Core.worker_env_active() and not (authorized(B, root) or stopping_holder(B, root)):
            raise ValueError("Workers cannot assess director relay quota")
        state = mark_progress(B, root, policy, rpc)
        if state and state["status"] == "STOPPING":
            return {
                "status": "STOP_REQUESTED",
                "stop_deadline": _iso(state.get("stop_deadline")),
                "next": 'save Resume/next step, then `relay complete --note "stopped by user"` and end',
            }
        policy = E.load(B, root)
        if args.snapshot:
            snapshot = _read_local_json(root, args.snapshot)
        else:
            if not state or state["status"] not in LIVE:
                raise ValueError("RELAY_NOT_ACTIVE: no relay director to assess")
            try:
                snapshot = rpc("pool_get_quotas", {"routeId": state["director"]["route"]})
            except (ValueError, OSError, KeyError, RuntimeError) as exc:
                snapshot = {"status": "UNKNOWN", "offline": True, "reason": str(exc)}
        return assess(snapshot, policy, args.model or (state or {}).get("director", {}).get("model"))
    if args.action == "next":
        if Core.worker_env_active() and not authorized(B, root):
            raise ValueError("Workers cannot inspect relay routing")
        state = read(B, root)
        current = state["director"]["route"] if state else args.route
        candidates = _candidates(state, _policy(policy)[0]) if state else None
        quotas = _read_local_json(root, args.quotas) if args.quotas else fetch_quotas(rpc, candidates or _policy(policy)[0]["candidates"])
        return choose(policy, quotas, current, candidates, (state or {}).get("health"))
    if args.action == "complete":
        if Core.worker_env_active() and not (authorized(B, root) or stopping_holder(B, root)):
            raise ValueError("RELAY_NOT_DIRECTOR: only the active baton holder can complete the relay")
        return finish(B, root, "COMPLETE", args.note, rpc=rpc)
    if args.action == "start":
        if Core.worker_env_active():
            raise ValueError("A Pool worker cannot start a relay; the host director starts it")
        if B.get_session_modes(root)["task_mode"] != "execute":
            raise ValueError("Relay circulation requires an execute session")
        return start(
            B,
            root,
            policy,
            args.route,
            args.model or None,
            args.effort or None,
            args.pool_task or None,
            rpc=rpc,
            brain_script=script,
            unverified=args.unverified,
        )
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
    quotas = _read_local_json(root, args.quotas) if args.quotas else None
    return handoff(B, root, policy, task, args.next_step, script, rpc, candidate=candidate, quotas=quotas)
