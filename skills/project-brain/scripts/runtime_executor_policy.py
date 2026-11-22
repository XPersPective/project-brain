"""Durable executor bounds and session confirmation; stdlib, Python 3.8+.

Imports only runtime_core and runtime_security (strictly acyclic).
Includes relay policy schema validation and lightweight read-only baton
authority checks so higher layers never create circular imports.
"""
import copy
import hashlib
import json
import os
import re
import secrets
import uuid

import runtime_core as Core
from runtime_security import require_clean

LIMIT = 65536
SOURCES = (
    "solo",
    "native",
    "native-cheap",
    "native-pinned",
    "cap-category",
    "cap-catalog",
    "cap-pinned",
    "mixed",
)
# Legacy optional "speed" key is tolerated on read for backward compatibility
# with v3.11/v3.12 executor-policy.json files; new policies omit it.
LEGACY_SPEEDS = ("balanced", "turbo")
ORIGINS = ("user", "defaults")

_RELAY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,199}$")
_RELAY_HASH = re.compile(r"^[0-9a-f]{64}$")
_RELAY_TOKEN = re.compile(r"^[0-9a-f]{32}$")
_RELAY_TOKEN_ENV = "PB_RELAY_TOKEN"
_RELAY_STATES = {"ACTIVE", "HANDOFF_PENDING", "STOPPING", "STOPPED", "COMPLETED", "EXHAUSTED"}
_RELAY_BLOCKING = {"ACTIVE", "HANDOFF_PENDING", "STOPPING"}


def _path(B, root, session=False):
    name = "/.cache/executor-session.json" if session else "/executor-policy.json"
    return Core.public_path(root, B.BRAIN_DIR + name)


def _keys(value, required, optional=()):
    if (
        not isinstance(value, dict)
        or not set(required).issubset(value)
        or set(value) - set(required) - set(optional)
    ):
        raise ValueError("Malformed executor policy or unsupported constraint")


def _text(value, limit=256, exact=False):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or value != value.strip()
        or any(ord(c) < 32 for c in value)
        or (exact and any(c in value for c in "*?[]"))
    ):
        raise ValueError("Executor policy requires bounded nonempty exact text")
    return value


def _items(value, exact=False):
    if not isinstance(value, list) or not 1 <= len(value) <= 128:
        raise ValueError("Executor policy requires a nonempty bounded list")
    result = [_text(item, exact=exact) for item in value]
    if len(set(result)) != len(result):
        raise ValueError("Duplicate executor policy entries")
    return result


def _relay_name(value, label):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not _RELAY_NAME.fullmatch(value):
        raise ValueError(label + " must be a bounded route/model/effort name")
    return value


def validate_relay_policy(value):
    """Validate the optional executor-policy `relay` block; return a normalized copy."""
    if not isinstance(value, dict):
        raise ValueError("Relay policy must be an object")
    allowed = {"enabled", "threshold_percent", "candidates", "max_handoffs", "director_category", "takeover_minutes"}
    if set(value) - allowed or not {"enabled", "threshold_percent"} <= set(value):
        raise ValueError(
            "Relay requires enabled and threshold_percent; optional candidates or director_category, "
            "max_handoffs, takeover_minutes"
        )
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
        entry = {"route": _relay_name(item["route"], "Relay route")}
        if entry["route"] is None:
            raise ValueError("Relay candidate route is required")
        for name in ("model", "effort"):
            if item.get(name):
                entry[name] = _relay_name(item[name], "Relay " + name)
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
        parsed_cat = _relay_name(category, "Relay director_category")
        if parsed_cat is None:
            raise ValueError("Relay director_category must be nonempty")
        result["director_category"] = parsed_cat
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


def _native_pin(value):
    if isinstance(value, str):
        host, sep, model = value.partition("/")
        if not sep:
            raise ValueError("Native pin requires host/model")
        value = {"host": host, "model": model}
    _keys(value, ("host", "model"))
    return {key: _text(value[key], exact=True) for key in ("host", "model")}


def _selector(value):
    _keys(value, ("source",), ("categories", "models", "effort"))
    source = value["source"]
    if source not in SOURCES:
        raise ValueError("Unknown executor source")
    result = {"source": source}
    if source == "cap-category" or (source == "mixed" and "categories" in value):
        result["categories"] = _items(value.get("categories"))
    elif "categories" in value:
        raise ValueError("Categories require cap-category or mixed")
    if source in ("native-pinned", "cap-pinned"):
        models = value.get("models")
        if not isinstance(models, list) or not 1 <= len(models) <= 128:
            raise ValueError("Pinned source requires exact model identities")
        pins = []
        for model in models:
            if source == "native-pinned":
                pins.append(_native_pin(model))
            else:
                _keys(model, ("routeId", "modelId"))
                pins.append({k: _text(model[k], exact=True) for k in ("routeId", "modelId")})
        if len({_canonical(pin) for pin in pins}) != len(pins):
            raise ValueError("Duplicate executor model pins")
        result["models"] = pins
    elif "models" in value:
        raise ValueError("Model pins require a pinned source")
    if "effort" in value:
        effort = value["effort"]
        _keys(effort, ("selector",), ("value", "allowed"))
        if effort["selector"] not in ("user", "director", "default"):
            raise ValueError("Unknown effort selector")
        normalized = {"selector": effort["selector"]}
        if effort["selector"] == "user":
            normalized["value"] = _text(effort.get("value"))
        elif "value" in effort:
            raise ValueError("An effort value requires user selection")
        if "allowed" in effort:
            normalized["allowed"] = _items(effort["allowed"])
            if "value" in normalized and normalized["value"] not in normalized["allowed"]:
                raise ValueError("Selected effort is outside allowed efforts")
        result["effort"] = normalized
    return result


def _validate(value):
    _keys(
        value,
        ("schema", "execution", "scheduling", "quota_recovery"),
        ("review", "note", "relay", "speed", "origin", "cap_fallback"),
    )
    if type(value["schema"]) is not int or value["schema"] != 1:
        raise ValueError("Unsupported executor policy schema")
    result = {"schema": 1, "execution": _selector(value["execution"])}
    result["review"] = _selector(value["review"]) if "review" in value else copy.deepcopy(result["execution"])
    schedule = value["scheduling"]
    _keys(schedule, ("mode", "max_parallel"), ("auto",))
    if (
        schedule["mode"] not in ("serial", "parallel")
        or type(schedule["max_parallel"]) is not int
        or not 1 <= schedule["max_parallel"] <= 32
        or (schedule["mode"] == "serial" and schedule["max_parallel"] != 1)
    ):
        raise ValueError("Scheduling requires serial/1 or parallel/1..32")
    if "auto" in schedule and (
        type(schedule["auto"]) is not bool or (schedule["auto"] and schedule["mode"] != "parallel")
    ):
        raise ValueError("Automatic parallel width requires parallel mode and true/false")
    result["scheduling"] = dict(schedule)
    for name, allowed in (("speed", LEGACY_SPEEDS), ("origin", ORIGINS), ("cap_fallback", ("native", "wait"))):
        if name in value:
            if value[name] not in allowed:
                raise ValueError("Executor policy %s must be one of %s" % (name, ", ".join(allowed)))
            if name != "speed":
                result[name] = value[name]
    recovery = value["quota_recovery"]
    _keys(recovery, ("enabled", "threshold_percent"))
    if (
        type(recovery["enabled"]) is not bool
        or type(recovery["threshold_percent"]) is not int
        or not 1 <= recovery["threshold_percent"] <= 50
    ):
        raise ValueError("Quota recovery requires explicit enabled and threshold_percent 1..50")
    result["quota_recovery"] = dict(recovery)
    if "relay" in value:
        result["relay"] = validate_relay_policy(value["relay"])
    if "note" in value:
        result["note"] = _text(value["note"], 1000)
    require_clean(_canonical(result), "executor policy")
    return result


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _read(path):
    if not path.exists():
        return None, None
    with path.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("Executor JSON exceeds 64 KiB")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=Core._unique_pairs,
            parse_constant=Core._reject_constant,
        )
    except (UnicodeError, RecursionError) as error:
        raise ValueError("Malformed executor JSON") from error
    return value, Core.sha256_bytes(raw)


# Lightweight read-only relay authority helpers (breaks policy <-> relay cycle).
def _read_relay_state(B, root):
    try:
        path = Core.public_path(root, B.BRAIN_DIR + "/.cache/relay.json")
        if not path.is_file():
            return None
        state = Core.read_json(path, max_bytes=262144, strict_constants=True)
        if state.get("status") not in _RELAY_STATES or not isinstance(state.get("director"), dict):
            return None
        return state
    except (ValueError, OSError):
        return None


def _holds_relay_token(entry, token=None):
    if not isinstance(entry, dict):
        return False
    token_hash = entry.get("token_hash")
    tok = token if token is not None else os.environ.get(_RELAY_TOKEN_ENV, "")
    if not isinstance(token_hash, str) or not _RELAY_HASH.fullmatch(token_hash) or not isinstance(tok, str) or not _RELAY_TOKEN.fullmatch(tok):
        return False
    return secrets.compare_digest(hashlib.sha256(tok.encode("utf-8")).hexdigest(), token_hash)


def relay_authorized(B, root, token=None):
    state = _read_relay_state(B, root)
    return bool(state and state.get("status") == "ACTIVE" and _holds_relay_token(state.get("director"), token))


def relay_stopping_holder(B, root, token=None):
    state = _read_relay_state(B, root)
    return bool(state and state.get("status") == "STOPPING" and _holds_relay_token(state.get("director"), token))


def relay_effective(B, root, value):
    state = _read_relay_state(B, root)
    if (
        not state
        or state.get("status") not in _RELAY_BLOCKING
        or not state.get("inherited")
        or value is None
        or not _holds_relay_token(state.get("director"))
        or hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest() == state.get("policy_hash")
    ):
        return value
    return value if receipt_matches_file(B, root) else copy.deepcopy(state["inherited"])


def load(B, root):
    """Read/validate without confirmation, migration, or writes."""
    value, digest = _read(_path(B, root))
    if value is None and digest is None:
        return None
    return relay_effective(B, root, _validate(value))


def load_raw(B, root):
    """Read and validate the file on disk directly without relay-inherited overlay."""
    value, digest = _read(_path(B, root))
    if value is None and digest is None:
        return None
    return _validate(value)


def save(B, root, value, note):
    if not B.brain_exists(root):
        raise ValueError("Initialize Brain before saving executor policy")
    value = _validate(value)
    value["note"] = _text(note, 1000)
    require_clean(_canonical(value), "executor policy")
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    if len((raw + "\n").encode("utf-8")) > LIMIT:
        raise ValueError("Executor policy exceeds 64 KiB")
    Core.write_atomic(_path(B, root), raw)
    return value


def build_policy(
    source="native",
    review_source=None,
    categories=None,
    models=None,
    schedule="parallel",
    max_parallel=None,
    qrp_enabled=None,
    qrp_threshold=None,
    relay_enabled=None,
    relay_threshold=None,
    relay_category=None,
    cap_fallback=None,
    base=None,
):
    """Construct a validated policy dict from ergonomic CLI flags (no manual JSON required)."""
    policy = copy.deepcopy(base) if isinstance(base, dict) else {
        "schema": 1,
        "execution": {"source": "native"},
        "scheduling": {"mode": "parallel", "max_parallel": 32, "auto": True},
        "quota_recovery": {"enabled": False, "threshold_percent": 10},
        "relay": {"enabled": False, "threshold_percent": 10, "candidates": []},
    }
    policy.pop("speed", None)
    policy.pop("note", None)
    if source:
        sel = {"source": source}
        if categories and source in ("cap-category", "mixed"):
            sel["categories"] = list(categories)
        if models:
            sel["models"] = list(models)
        policy["execution"] = sel
        if review_source is None:
            policy["review"] = copy.deepcopy(sel)
    elif categories:
        if policy["execution"]["source"] in ("cap-category", "mixed"):
            policy["execution"]["categories"] = list(categories)
        if policy.get("review", {}).get("source") in ("cap-category", "mixed"):
            policy["review"]["categories"] = list(categories)
    if review_source:
        rsel = {"source": review_source}
        if review_source in ("cap-category", "mixed") and categories:
            rsel["categories"] = list(categories)
        policy["review"] = rsel
    if schedule == "serial":
        policy["scheduling"] = {"mode": "serial", "max_parallel": 1}
    elif schedule == "parallel":
        if max_parallel is not None:
            policy["scheduling"] = {"mode": "parallel", "max_parallel": max_parallel, "auto": False}
        else:
            policy["scheduling"] = {"mode": "parallel", "max_parallel": 32, "auto": True}
    elif max_parallel is not None:
        policy["scheduling"] = {"mode": "parallel", "max_parallel": max_parallel, "auto": False}
    if qrp_enabled is not None or qrp_threshold is not None:
        cur_qrp = policy.get("quota_recovery") if isinstance(policy.get("quota_recovery"), dict) else {}
        policy["quota_recovery"] = {
            "enabled": bool(qrp_enabled) if qrp_enabled is not None else bool(cur_qrp.get("enabled", False)),
            "threshold_percent": int(qrp_threshold) if qrp_threshold is not None else int(cur_qrp.get("threshold_percent", 10)),
        }
    if relay_enabled is not None or relay_threshold is not None or relay_category is not None:
        cur_rel = copy.deepcopy(policy.get("relay")) if isinstance(policy.get("relay"), dict) else {}
        enabled = bool(relay_enabled) if relay_enabled is not None else bool(cur_rel.get("enabled", False))
        threshold = int(relay_threshold) if relay_threshold is not None else int(cur_rel.get("threshold_percent", 10))
        if enabled:
            rel_out = dict(cur_rel, enabled=True, threshold_percent=threshold)
            if relay_category is not None:
                rel_out.pop("candidates", None)
                rel_out["director_category"] = relay_category
            elif not rel_out.get("candidates") and not rel_out.get("director_category"):
                rel_out.pop("candidates", None)
                rel_out["director_category"] = "same"
            policy["relay"] = rel_out
        else:
            policy["relay"] = {"enabled": False, "threshold_percent": threshold, "candidates": []}
    if cap_fallback:
        policy["cap_fallback"] = cap_fallback
    elif any(policy.get(r, policy["execution"])["source"].startswith("cap-") for r in ("execution", "review")):
        policy.setdefault("cap_fallback", "wait")
    return _validate(policy)


def _session(B, root):
    value, digest = _read(_path(B, root, session=True))
    if value is None and digest is None:
        return None
    _keys(value, ("schema", "nonce"), ("confirmation",))
    if type(value["schema"]) is not int or value["schema"] != 1:
        raise ValueError("Malformed executor session")
    _text(value["nonce"], 128)
    return value


def begin_session(B, root):
    """Rotate only this confirmation marker; preserve policy and existing jobs."""
    if not B.brain_exists(root):
        raise ValueError("Initialize Brain before beginning executor session")
    path = _path(B, root, session=True)
    value = {"schema": 1, "nonce": uuid.uuid4().hex}
    Core.write_atomic(path, json.dumps(value, indent=2))
    return value


def _mark_setup_resolved(B, root):
    try:
        sp = Core.public_path(root, B.BRAIN_DIR + "/.cache/setup.json")
        if sp.is_file():
            rec = Core.read_json(sp, max_bytes=65536)
            if rec.get("status") != "resolved":
                rec["status"] = "resolved"
                Core.write_atomic(sp, json.dumps(rec, ensure_ascii=False, indent=2))
    except (ValueError, OSError):
        pass


def confirm(B, root, note):
    if not B.brain_exists(root):
        raise ValueError("Initialize Brain before confirming executor policy")
    current, file_hash = _read(_path(B, root))
    if current is None and file_hash is None:
        raise ValueError("Save explicit executor, scheduling and quota recovery choices before confirmation")
    value = _validate(current)
    note = _text(note, 1000)
    require_clean(note, "executor confirmation note")
    session = _session(B, root) or begin_session(B, root)
    current, file_hash = _read(_path(B, root))
    if _validate(current) != value:
        raise ValueError("Executor policy changed during confirmation")
    session["confirmation"] = {
        "nonce": session["nonce"],
        "policy_hash": hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest(),
        "file_hash": file_hash,
        "session_id": os.environ.get("PB_SESSION_ID", ""),
        "note": note,
    }
    Core.write_atomic(_path(B, root, session=True), json.dumps(session, ensure_ascii=False, indent=2))
    Core.write_atomic(
        Core.public_path(root, B.BRAIN_DIR + "/.cache/policy-confirmed.json"),
        json.dumps({"schema": 1, "file_hash": file_hash}),
    )
    _mark_setup_resolved(B, root)
    return session


def last_confirmed(B, root):
    """True when the policy file's bytes equal the last confirmed policy (any session)."""
    try:
        _, file_hash = _read(_path(B, root))
        path = Core.public_path(root, B.BRAIN_DIR + "/.cache/policy-confirmed.json")
        return bool(file_hash) and path.is_file() and json.loads(path.read_text(encoding="utf-8")).get("file_hash") == file_hash
    except (ValueError, OSError, AttributeError):
        return False


def receipt_matches_file(B, root):
    """The current session's confirmation covers the current policy bytes (nonce-free check)."""
    try:
        value, file_hash = _read(_path(B, root))
        session = _session(B, root)
        receipt = session.get("confirmation") if session else None
        return (
            isinstance(receipt, dict)
            and file_hash is not None
            and receipt.get("file_hash") == file_hash
            and receipt.get("policy_hash") == hashlib.sha256(_canonical(_validate(value)).encode("utf-8")).hexdigest()
        )
    except (ValueError, OSError, TypeError):
        return False


def confirmed(B, root):
    """Freshness observation, not authenticated user/model identity."""
    if relay_authorized(B, root) or relay_stopping_holder(B, root):
        return True
    try:
        value, file_hash = _read(_path(B, root))
        if file_hash is None:
            return False
        value = _validate(value)
        session = _session(B, root)
        receipt = session.get("confirmation") if session else None
        if not isinstance(receipt, dict):
            return False
        return (
            receipt.get("nonce") == session["nonce"]
            and receipt.get("policy_hash") == hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()
            and receipt.get("file_hash") == file_hash
            and receipt.get("session_id") == os.environ.get("PB_SESSION_ID", "")
        )
    except (ValueError, OSError, TypeError):
        return False


def require_confirmed(B, root):
    value = load(B, root)
    marker = _path(B, root, session=True).exists()
    if value is None and not marker:
        return None
    if value is None or not confirmed(B, root):
        raise ValueError("EXECUTOR_POLICY_PENDING: confirm session policy with `setup confirm` or `policy --confirm`")
    return value


def settings(B, root):
    value = load(B, root)
    if value is None:
        return {}
    modes = {
        "solo": "solo",
        "native": "self_mixed",
        "native-pinned": "self_mixed",
        "native-cheap": "self_mixed",
        "mixed": "mixed",
    }
    return {
        "exec": modes.get(value["execution"]["source"], "pool_mixed"),
        "rev": modes.get(value["review"]["source"], "pool_mixed"),
        "schedule": value["scheduling"]["mode"],
        "max_parallel": value["scheduling"]["max_parallel"],
    }


def _role(role):
    if role in ("rev", "review", "reviewer"):
        return "review"
    if role in ("exec", "execution", "worker", "discovery", "lead"):
        return "execution"
    raise ValueError("Unknown executor policy role")


def selector(B, root, role="exec"):
    role = _role(role)
    value = load(B, root)
    return value[role] if value is not None else None


def guard(B, root, role, backend, model=None, category=None, effort=None, cheaper=None):
    value = require_confirmed(B, root)
    if value is None:
        return None
    selected = value[_role(role)]
    source = selected["source"]
    if backend == "main":
        return selected
    expected = ("native", "pool") if source == "mixed" else ("pool",) if source.startswith("cap-") else ("native",)
    if source == "solo" or backend not in expected:
        raise ValueError("Worker backend is outside saved executor source")
    capped = "categories" in selected and backend == "pool"
    bounds = selected.get("effort", {})
    if model is None and bounds.get("selector") == "default" and effort is not None:
        raise ValueError("Saved provider-default effort forbids an explicit override")
    if effort is not None:
        _text(effort)
        if bounds.get("selector") == "user" and effort != bounds["value"]:
            raise ValueError("Effort differs from saved user choice")
        if "allowed" in bounds and effort not in bounds["allowed"]:
            raise ValueError("Effort is outside saved allowed choices")
    if category is not None:
        _text(category)
        if capped and category not in selected["categories"]:
            raise ValueError("Category is outside saved executor bounds")
    if model is None:
        return selected
    if isinstance(model, dict):
        for key, denied in (("enabled", False), ("disabled", True), ("hidden", True), ("removed", True)):
            if key in model and (type(model[key]) is not bool or model[key] is denied):
                raise ValueError("Unavailable or ambiguous executor metadata")
    elif not (source == "native-pinned" and isinstance(model, str)):
        raise ValueError("Executor metadata must be an object")
    actual_effort = model.get("effort") if isinstance(model, dict) else None
    if actual_effort is not None and effort is not None and actual_effort != effort:
        raise ValueError("Requested and actual executor effort disagree")
    effective_effort = effort if effort is not None else actual_effort
    if bounds.get("selector") == "default" and effective_effort is not None:
        if not isinstance(model, dict) or effective_effort != model.get("defaultEffort"):
            raise ValueError("Actual effort does not prove the provider default")
    if bounds.get("selector") == "user" and effective_effort != bounds["value"]:
        raise ValueError("Actual executor effort does not prove saved user choice")
    if "allowed" in bounds and effective_effort not in bounds["allowed"]:
        raise ValueError("Actual executor effort is unknown or outside saved bounds")
    if source == "native-pinned":
        identity = _native_pin(model if isinstance(model, str) else {k: model.get(k) for k in ("host", "model")})
        if identity not in selected["models"]:
            raise ValueError("Native model is outside saved exact pins")
    elif source == "cap-pinned":
        identity = {key: _text(model.get(key), exact=True) for key in ("routeId", "modelId")}
        if identity not in selected["models"]:
            raise ValueError("CAP model is outside saved exact pins")
    elif capped:
        memberships = model.get("categories")
        if memberships is None:
            actual_category = model.get("category", model.get("group"))
            memberships = [actual_category] if actual_category else None
        if memberships is not None:
            memberships = _items(memberships)
            if category is not None and category not in memberships:
                raise ValueError("Actual model does not belong to requested category")
        if memberships is None or not set(memberships).intersection(selected["categories"]):
            raise ValueError("Actual model has no saved category membership")
    if source == "native-cheap" and cheaper is not True:
        raise ValueError("Native Cheapest requires an actual cheaper-model observation")
    return selected


def summary(B, root):
    value = load(B, root)
    if value is None:
        return {"policy": None, "confirmed": False}
    return {
        "schema": 1,
        "execution": {"source": value["execution"]["source"]},
        "review": {"source": value["review"]["source"]},
        "scheduling": value["scheduling"],
        "quota_recovery": value["quota_recovery"],
        **({"relay": {k: value["relay"][k] for k in ("enabled", "threshold_percent")}} if "relay" in value else {}),
        **{k: value[k] for k in ("origin", "cap_fallback") if k in value},
        "confirmed": confirmed(B, root),
    }


def cap_unavailable(value, role="exec"):
    """Language-neutral CAP unavailability guidance.

    Defaults (or explicit cap_fallback='native') fall back to native host agents;
    explicit CAP-only policies wait unless the user switches source.
    """
    if value is None:
        return {"action": "NOT_APPLICABLE"}
    source = value[_role(role)]["source"]
    relay = isinstance(value.get("relay"), dict) and value["relay"].get("enabled") is True
    tail = " Baton relay requires CAP; falling back to quota-wait policy at threshold." if relay else ""
    if source in ("solo", "native", "native-cheap", "native-pinned"):
        return {"action": "CONTINUE", "notify": ("CLI Agent Pool is unreachable." + tail) if relay else None}
    if source == "mixed" or value.get("cap_fallback") == "native" or (
        value.get("origin") == "defaults" and value.get("cap_fallback") != "wait"
    ):
        return {
            "action": "CONTINUE_NATIVE",
            "notify": "CLI Agent Pool is unreachable; continuing with native host agents." + tail,
        }
    return {
        "action": "WAIT",
        "notify": (
            "CLI Agent Pool is unreachable. Policy is CAP-only so no new CAP work is dispatched; "
            "wait for recovery or switch policy to native (`PB policy --source native --confirm`)." + tail
        ),
    }


def relay_worker_reserve(policy):
    """Single source of truth for CAP worker quota reserve when Baton Relay is enabled."""
    relay = policy.get("relay") if isinstance(policy, dict) else None
    return relay["threshold_percent"] if isinstance(relay, dict) and relay.get("enabled") is True else 0
