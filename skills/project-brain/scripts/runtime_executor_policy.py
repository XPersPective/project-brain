"""Durable executor bounds and session confirmation; stdlib, Python 3.8+."""
import copy
import hashlib
import json
import os
import uuid

import runtime_verify as V
from runtime_security import require_clean


LIMIT = 65536
SOURCES = ("solo", "native", "native-cheap", "native-pinned",
           "cap-category", "cap-catalog", "cap-pinned")


def _path(B, root, session=False):
    name = "/.cache/executor-session.json" if session else "/executor-policy.json"
    return V.public_path(root, B.BRAIN_DIR + name)


def _keys(value, required, optional=()):
    if (not isinstance(value, dict) or not set(required).issubset(value)
            or set(value) - set(required) - set(optional)):
        raise ValueError("Malformed executor policy or unsupported constraint")


def _text(value, limit=256, exact=False):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or value != value.strip() or any(ord(c) < 32 for c in value)
            or (exact and any(c in value for c in "*?[]"))):
        raise ValueError("Executor policy requires bounded nonempty exact text")
    return value


def _items(value, exact=False):
    if not isinstance(value, list) or not 1 <= len(value) <= 128:
        raise ValueError("Executor policy requires a nonempty bounded list")
    result = [_text(item, exact=exact) for item in value]
    if len(set(result)) != len(result):
        raise ValueError("Duplicate executor policy entries")
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
    if source == "cap-category":
        result["categories"] = _items(value.get("categories"))
    elif "categories" in value:
        raise ValueError("Categories require cap-category")
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
    _keys(value, ("schema", "execution", "scheduling", "quota_recovery"), ("review", "note"))
    if type(value["schema"]) is not int or value["schema"] != 1:
        raise ValueError("Unsupported executor policy schema")
    result = {"schema": 1, "execution": _selector(value["execution"])}
    result["review"] = _selector(value["review"]) if "review" in value else copy.deepcopy(result["execution"])
    schedule = value["scheduling"]
    _keys(schedule, ("mode", "max_parallel"))
    if (schedule["mode"] not in ("serial", "parallel")
            or type(schedule["max_parallel"]) is not int or not 1 <= schedule["max_parallel"] <= 32
            or (schedule["mode"] == "serial" and schedule["max_parallel"] != 1)):
        raise ValueError("Scheduling requires serial/1 or parallel/1..32")
    result["scheduling"] = dict(schedule)
    recovery = value["quota_recovery"]
    _keys(recovery, ("enabled", "threshold_percent"))
    if (type(recovery["enabled"]) is not bool or type(recovery["threshold_percent"]) is not int
            or not 1 <= recovery["threshold_percent"] <= 50):
        raise ValueError("Quota recovery requires explicit enabled and threshold_percent 1..50")
    result["quota_recovery"] = dict(recovery)
    if "note" in value:
        result["note"] = _text(value["note"], 1000)
    require_clean(_canonical(result), "executor policy")
    return result


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("Duplicate executor JSON keys")
        value[key] = item
    return value


def _read(path):
    if not path.exists():
        return None, None
    with path.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("Executor JSON exceeds 64 KiB")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON")))
    except (UnicodeError, RecursionError) as error:
        raise ValueError("Malformed executor JSON") from error
    return value, hashlib.sha256(raw).hexdigest()


def load(B, root):
    """Read/validate without confirmation, migration, or writes."""
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
    B.write_atomic(_path(B, root), raw)
    return value


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
    # Validate guarded paths even when replacing an old confirmation.
    path = _path(B, root, session=True)
    value = {"schema": 1, "nonce": uuid.uuid4().hex}
    B.write_atomic(path, json.dumps(value, indent=2))
    return value


def confirm(B, root, note):
    if not B.brain_exists(root):
        raise ValueError("Initialize Brain before confirming executor policy")
    value = load(B, root)
    if value is None:
        raise ValueError("Save explicit executor, scheduling and quota recovery choices before confirmation")
    note = _text(note, 1000)
    require_clean(note, "executor confirmation note")
    session = _session(B, root) or begin_session(B, root)
    # Read again to bind the actual bytes as well as the normalized policy.
    current, file_hash = _read(_path(B, root))
    if _validate(current) != value:
        raise ValueError("Executor policy changed during confirmation")
    session["confirmation"] = {"nonce": session["nonce"], "policy_hash": hashlib.sha256(
        _canonical(value).encode("utf-8")).hexdigest(), "file_hash": file_hash,
        "session_id": os.environ.get("PB_SESSION_ID", ""), "note": note}
    B.write_atomic(_path(B, root, session=True), json.dumps(session, ensure_ascii=False, indent=2))
    return session


def confirmed(B, root):
    """Freshness observation, not authenticated user/model identity."""
    try:
        value, file_hash = _read(_path(B, root))
        if file_hash is None:
            return False
        value = _validate(value)
        session = _session(B, root)
        receipt = session.get("confirmation") if session else None
        if not isinstance(receipt, dict):
            return False
        return (receipt.get("nonce") == session["nonce"]
                and receipt.get("policy_hash") == hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()
                and receipt.get("file_hash") == file_hash
                and receipt.get("session_id") == os.environ.get("PB_SESSION_ID", ""))
    except (ValueError, OSError, TypeError):
        return False


def require_confirmed(B, root):
    value = load(B, root)
    marker = _path(B, root, session=True).exists()
    if value is None and not marker:
        return None
    if value is None or not confirmed(B, root):
        raise ValueError("EXECUTOR_POLICY_PENDING: confirm saved ESP, SP and quota recovery for this session")
    return value


def settings(B, root):
    value = load(B, root)
    if value is None:
        return {}
    modes = {"solo": "solo", "native": "self_mixed", "native-pinned": "self_mixed",
             "native-cheap": "self_mixed"}
    return {"exec": modes.get(value["execution"]["source"], "pool_mixed"),
            "rev": modes.get(value["review"]["source"], "pool_mixed"),
            "schedule": value["scheduling"]["mode"], "max_parallel": value["scheduling"]["max_parallel"]}


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
    expected = "pool" if source.startswith("cap-") else "native"
    if source == "solo" or backend != expected:
        raise ValueError("Worker backend is outside saved executor source")
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
        if source == "cap-category" and category not in selected["categories"]:
            raise ValueError("Category is outside saved executor bounds")
    if model is None:
        return selected  # Exact identity and effective effort are checked after selection.
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
    elif source == "cap-category":
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
    return {"schema": 1, "execution": {"source": value["execution"]["source"]},
            "review": {"source": value["review"]["source"]},
            "scheduling": value["scheduling"], "quota_recovery": value["quota_recovery"],
            "confirmed": confirmed(B, root)}
