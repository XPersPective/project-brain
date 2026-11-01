"""Director quota recovery authority; no scheduler, worker or provider operations.

The caller supplies fresh provider observations and explicitly requests prepare.
Host creation is acknowledged separately with arm; uncertain creation must be read
back by nonce/name. This module never grants authority to old worker jobs.
Python 3.8+, standard library only.
"""
import hashlib
import json
import math
from pathlib import PurePosixPath
import re
import time
import uuid

import runtime_security as S
import runtime_verify as V

MAX_RECORD = 16384
MAX_CHECKPOINT = 1024 * 1024
HASH = re.compile(r"^[0-9a-f]{64}$")
NONCE = re.compile(r"^[0-9a-f]{32}$")
STATES = {"PREPARED", "ARMED", "CANCELLED", "RESUMED"}


def _number(value):
    try:
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value))
    except OverflowError:
        return False


def _now(now):
    value = time.time() if now is None else now
    if not _number(value) or value < 0:
        raise ValueError("Invalid observation time")
    return value


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _policy(policy):
    if not isinstance(policy, dict):
        raise ValueError("Quota recovery policy must be an object")
    qrp = policy.get("quota_recovery")
    if not isinstance(qrp, dict) or not isinstance(qrp.get("enabled"), bool):
        raise ValueError("Quota recovery requires an explicit enabled decision")
    threshold = qrp.get("threshold_percent")
    if not _number(threshold) or not 1 <= threshold <= 50:
        raise ValueError("Quota recovery threshold must be finite and between 1 and 50")
    try:
        raw = json.dumps(policy, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise ValueError("Quota recovery policy must be finite JSON")
    if len(raw) > MAX_RECORD:
        raise ValueError("Quota recovery policy exceeds 16 KiB")
    return qrp["enabled"], threshold, _hash(raw)


def _account(snapshot):
    value = snapshot.get("accountId") if isinstance(snapshot, dict) else None
    if not isinstance(value, str) or not value.strip() or len(value) > 1024 or any(ord(c) < 32 for c in value):
        raise ValueError("Stable provider account identity is unavailable")
    return _hash(value.encode("utf-8"))


def _observe(snapshot, now):
    account = _account(snapshot)
    if not isinstance(snapshot.get("ordinaryUsageAllowed"), bool):
        raise ValueError("Ordinary usage availability is unknown")
    limits = snapshot.get("rateLimits")
    if not isinstance(limits, dict):
        raise ValueError("Provider quota windows are unavailable")
    limit_id = limits.get("limitId")
    if not isinstance(limit_id, str) or not limit_id.strip() or len(limit_id) > 256 or any(ord(c) < 32 for c in limit_id):
        raise ValueError("Provider quota identity is unavailable")
    windows = {}
    for key in ("primary", "secondary"):
        window = limits.get(key)
        if key == "secondary" and window is None:
            continue
        if not isinstance(window, dict):
            raise ValueError("Provider quota window is unavailable")
        used, reset, duration = (window.get("usedPercent"), window.get("resetsAt"),
                                 window.get("windowDurationMins"))
        if not _number(used) or not 0 <= used <= 100:
            raise ValueError("Provider quota percentage is invalid")
        if not _number(reset) or reset <= now:
            raise ValueError("Provider quota reset must be in the future")
        if not _number(duration) or duration <= 0:
            raise ValueError("Provider quota window duration is invalid")
        windows[key] = {"remaining_percent": 100 - used, "resets_at": reset}
    return {"account_hash": account, "limit_hash": _hash(limit_id.encode("utf-8")),
            "allowed": snapshot["ordinaryUsageAllowed"], "windows": windows}


def assess(snapshot, policy, now=None):
    """Pure conservative assessment. Unknown observations never imply capacity."""
    if (isinstance(policy, dict) and isinstance(policy.get("quota_recovery"), dict)
            and policy["quota_recovery"].get("enabled") is False):
        return {"status": "DISABLED"}
    try:
        enabled, threshold, _ = _policy(policy)
        if not enabled:
            return {"status": "DISABLED"}
        observation = _observe(snapshot, _now(now))
    except (ValueError, TypeError, OverflowError):
        return {"status": "UNKNOWN", "reason": "policy or provider observation unavailable"}
    blocking = {key: window["resets_at"] for key, window in observation["windows"].items()
                if window["remaining_percent"] <= threshold}
    result = {"status": "CHECKPOINT_REQUIRED" if blocking else "READY",
              "threshold_percent": threshold,
              "remaining_percent": min(w["remaining_percent"] for w in observation["windows"].values())}
    if blocking:
        result.update({"next_reset_at": max(blocking.values()), "limiting_windows": blocking})
    elif not observation["allowed"]:
        return {"status": "UNKNOWN", "reason": "ordinary provider usage is unavailable"}
    return result


def _path(B, root):
    return V.public_path(root, B.BRAIN_DIR + "/.cache/quota-recovery.json")


def _checkpoint(B, root, name):
    if not isinstance(name, str) or len(name) > 512:
        raise ValueError("Checkpoint must be a bounded project-relative path")
    parts = PurePosixPath(name).parts
    if (len(parts) != 4 or parts[:2] != (B.BRAIN_DIR, "evidence")
            or parts[3] != "handoff.json" or not parts[2] or str(PurePosixPath(name)) != name):
        raise ValueError("Checkpoint must be .project-brain/evidence/<task>/handoff.json")
    path = V.public_path(root, name)
    if not path.is_file() or path.stat().st_size > MAX_CHECKPOINT:
        raise ValueError("Existing bounded handoff checkpoint required")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_CHECKPOINT:
        raise ValueError("Existing bounded handoff checkpoint required")
    try:
        content = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise ValueError("Handoff checkpoint must be a JSON object")
    if not isinstance(content, dict) or not content:
        raise ValueError("Handoff checkpoint must be a nonempty JSON object")
    S.require_public(raw.decode("utf-8"), "quota recovery handoff")
    return {"path": name, "sha256": _hash(raw)}


def _read(B, root):
    path = _path(B, root)
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_RECORD:
        raise ValueError("Quota recovery record exceeds its bound")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        valid = (isinstance(state, dict) and state.get("schema") == 1
                 and NONCE.fullmatch(state.get("nonce", ""))
                 and state.get("status") in STATES
                 and all(HASH.fullmatch(state.get(k, "")) for k in ("account_hash", "policy_hash", "limit_hash"))
                 and _number(state.get("observed_reset_at"))
                 and state["observed_reset_at"] > 0
                 and _number(state.get("prepared_at")) and state["prepared_at"] >= 0
                 and isinstance(state.get("limiting_windows"), dict) and state["limiting_windows"]
                 and all(k in ("primary", "secondary") and _number(v) and v > 0
                         for k, v in state["limiting_windows"].items())
                 and max(state["limiting_windows"].values()) == state["observed_reset_at"]
                 and isinstance(state.get("checkpoint"), dict)
                 and HASH.fullmatch(state["checkpoint"].get("sha256", ""))
                 and isinstance(state["checkpoint"].get("path"), str)
                 and (state.get("automation_id") is None or _host_id(state["automation_id"]))
                 and (state["status"] not in ("ARMED", "RESUMED") or _host_id(state["automation_id"]))
                 and (state["status"] != "PREPARED" or state["automation_id"] is None))
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("Invalid quota recovery record; authority withheld")
    return state


def _write(B, root, state):
    B.write_atomic(_path(B, root), json.dumps(state, sort_keys=True, indent=2, allow_nan=False))


def _host_id(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 256 and not any(ord(c) < 32 for c in value)


def _view(state):
    if state is None:
        return {"status": "NONE"}
    return {"status": state["status"], "nonce": state["nonce"],
            "automation_id": state["automation_id"], "wake_at": state["observed_reset_at"],
            "checkpoint": state["checkpoint"]["path"]}


def _request(state, action):
    result = _view(state)
    result.update({"host_action": action, "name": "pb-quota-" + state["nonce"],
                   "instructions": "Use this nonce/name for host readback. Never blindly retry uncertain creation. "
                   "At wake, obtain fresh account/quota readings and call check_resume; code only after RESUMED. "
                   "Stay quiet while waiting; notify on completion, failure or required user action."})
    return result


def prepare(B, root, snapshot, policy, checkpoint, now=None, allow_rearm=False):
    """Persist a deliberate director recovery request, returning a host action.

    A second PREPARED call requests host readback, never another blind create.
    Replacing CANCELLED requires allow_rearm=True after fresh explicit consent.
    """
    if not isinstance(allow_rearm, bool):
        raise ValueError("Rearm must be an explicit boolean decision")
    now = _now(now)
    enabled, _, policy_hash = _policy(policy)
    assessment = assess(snapshot, policy, now)
    if not enabled or assessment["status"] != "CHECKPOINT_REQUIRED":
        raise ValueError("Enabled recovery and an actual low-quota observation are required")
    observation = _observe(snapshot, now)
    checkpoint = _checkpoint(B, root, checkpoint)
    with B.checkout_lock(root, name="quota-recovery.lock"):
        old = _read(B, root)
        if old and old["status"] == "CANCELLED" and not allow_rearm:
            raise ValueError("Cancelled recovery requires fresh explicit consent and allow_rearm=True")
        bindings = {"account_hash": observation["account_hash"], "limit_hash": observation["limit_hash"],
                    "policy_hash": policy_hash, "checkpoint": checkpoint,
                    "observed_reset_at": assessment["next_reset_at"],
                    "limiting_windows": assessment["limiting_windows"]}
        if old and old["status"] in ("PREPARED", "ARMED"):
            if any(old.get(key) != value for key, value in bindings.items()):
                raise ValueError("Existing recovery requires cancellation/readback before replacement")
            return _request(old, "READBACK_AUTOMATION" if old["status"] == "PREPARED" else "ALREADY_ARMED")
        state = dict(bindings, schema=1, nonce=uuid.uuid4().hex, status="PREPARED",
                     automation_id=None, prepared_at=now)
        _write(B, root, state)
        return _request(state, "CREATE_AUTOMATION")


def arm(B, root, nonce, automation_id):
    """Acknowledge exactly one host automation; uncertain ACK stays PREPARED."""
    if not _host_id(automation_id):
        raise ValueError("Bounded nonempty host automation ID required")
    S.require_public(automation_id, "quota recovery automation ID")
    with B.checkout_lock(root, name="quota-recovery.lock"):
        state = _read(B, root)
        if not state or state["nonce"] != nonce or state["status"] not in ("PREPARED", "ARMED"):
            raise ValueError("Exact prepared recovery nonce required")
        if state["automation_id"] not in (None, automation_id):
            raise ValueError("Different host automation already acknowledged; read back before changing")
        state.update(status="ARMED", automation_id=automation_id)
        _write(B, root, state)
        return _view(state)


def _revoke(B, root, state, reason):
    state.update(status="CANCELLED", reason=reason)
    _write(B, root, state)
    result = _view(state)
    result.update(reason=reason, name="pb-quota-" + state["nonce"],
                  host_action="DELETE_AUTOMATION" if state["automation_id"] else "READBACK_AND_DELETE")
    return result


def check_resume(B, root, snapshot, policy, nonce, now=None):
    """Consume one wake authority only after fresh identity/quota/checkpoint checks."""
    now = _now(now)
    with B.checkout_lock(root, name="quota-recovery.lock"):
        state = _read(B, root)
        if not state or state["nonce"] != nonce:
            return {"status": "BLOCKED", "reason": "stale or missing recovery nonce"}
        if state["status"] == "CANCELLED":
            return _view(state)
        if state["status"] == "RESUMED":
            return {"status": "CONSUMED", "reason": "wake authority already consumed"}
        try:
            account_hash = _account(snapshot)
        except ValueError:
            return {"status": "BLOCKED", "reason": "stable account identity unavailable"}
        if account_hash != state["account_hash"]:
            return _revoke(B, root, state, "account changed; explicit reconfirmation required")
        try:
            enabled, _, policy_hash = _policy(policy)
        except ValueError:
            return _revoke(B, root, state, "policy invalid; explicit reconfirmation required")
        if not enabled or policy_hash != state["policy_hash"]:
            return _revoke(B, root, state, "policy changed; explicit reconfirmation required")
        try:
            intact = _checkpoint(B, root, state["checkpoint"]["path"]) == state["checkpoint"]
        except (ValueError, OSError):
            intact = False
        if not intact:
            return _revoke(B, root, state, "checkpoint missing or changed")
        if state["status"] != "ARMED":
            return {"status": "BLOCKED", "reason": "host creation acknowledgement/readback required"}
        if now < state["observed_reset_at"]:
            return {"status": "WAIT", "reason": "recorded reset time has not arrived"}
        assessment = assess(snapshot, policy, now)
        if assessment["status"] != "READY":
            return {"status": "WAIT", "reason": "fresh usable quota has not been demonstrated"}
        observation = _observe(snapshot, now)
        if observation["limit_hash"] != state["limit_hash"]:
            return _revoke(B, root, state, "provider quota identity changed")
        if any(key not in observation["windows"] or observation["windows"][key]["resets_at"] <= reset
               for key, reset in state["limiting_windows"].items()):
            return {"status": "WAIT", "reason": "limiting quota windows have not demonstrably renewed"}
        state.update(status="RESUMED", resumed_at=now)
        _write(B, root, state)
        return dict(_view(state), checkpoint_sha256=state["checkpoint"]["sha256"])


def cancel(B, root, reason="user cancelled"):
    """Revoke locally before returning any host deletion request."""
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 160:
        raise ValueError("Cancellation reason must be bounded nonempty text")
    S.require_public(reason, "quota recovery cancellation reason")
    if not _path(B, root).exists():
        return {"status": "NONE"}
    with B.checkout_lock(root, name="quota-recovery.lock"):
        state = _read(B, root)
        return _revoke(B, root, state, reason) if state else {"status": "NONE"}


def status(B, root):
    """Compact read-only local status, without raw account/provider observations."""
    return _view(_read(B, root))
