"""Streamlined default-safe session setup with sharp Core vs Power separation.

Core product defaults: native host agents, parallel (auto), QRP off, BRP off.
New sessions present a single-line confirmation summary; power features (CAP,
QRP, BRP) are strictly opt-in via `--advanced` or `PB policy`.
Relay successors and workers inherit confirmed settings without prompts.
Python 3.8+, standard library only.
"""
import copy
import json
from pathlib import Path
import time

import runtime_core as Core
import runtime_executor_policy as E
import runtime_quota_recovery as Q
import runtime_relay as RL

TIMEOUT = 300
SLICE = 60

# Safe core defaults: no power features (CAP/QRP/BRP) are silently armed.
BUILTIN = {
    "schema": 1,
    "execution": {"source": "native"},
    "scheduling": {"mode": "parallel", "max_parallel": 32, "auto": True},
    "quota_recovery": {"enabled": False, "threshold_percent": 10},
    "relay": {"enabled": False, "threshold_percent": 10, "candidates": []},
}


def _path(B, root):
    return Core.public_path(root, B.BRAIN_DIR + "/.cache/setup.json")


def defaults(B, root):
    """Saved confirmed policy when one exists, else the safe core default."""
    saved = E.load(B, root)
    value = copy.deepcopy(saved) if saved and E.last_confirmed(B, root) else copy.deepcopy(BUILTIN)
    value.pop("note", None)
    value.pop("origin", None)
    value.pop("speed", None)
    if saved and E.last_confirmed(B, root) and saved.get("origin") != "defaults":
        if any(value.get(role, value["execution"])["source"].startswith("cap-") for role in ("execution", "review")):
            value.setdefault("cap_fallback", "wait")
    return value


def _detail(selector):
    if selector.get("categories"):
        return " [" + ", ".join(selector["categories"]) + "]"
    if selector.get("models"):
        return " [" + ", ".join(
            m.get("routeId", m.get("host", "")) + "/" + m.get("modelId", m.get("model", ""))
            for m in selector["models"][:4]
        ) + "]"
    return ""


def summary_line(value):
    """Single-line language-neutral session policy summary for low-friction confirmation."""
    src = value["execution"]["source"] + _detail(value["execution"])
    rev_src = value.get("review", value["execution"])["source"]
    sched = value["scheduling"]
    sched_text = (
        "parallel (auto)"
        if sched["mode"] == "parallel" and (sched.get("auto") or sched["max_parallel"] == 32)
        else ("parallel (max %d)" % sched["max_parallel"] if sched["mode"] == "parallel" else "serial")
    )
    q = value["quota_recovery"]
    qrp_text = ("QRP on @%d%%" % q["threshold_percent"]) if q.get("enabled") else "QRP off"
    relay = value.get("relay") or {}
    brp_text = ("BRP on @%d%%" % relay.get("threshold_percent", 10)) if relay.get("enabled") else "BRP off"
    rev_part = (" · review=" + rev_src) if rev_src != value["execution"]["source"] else ""
    return f"Session policy: {src}{rev_part} · {sched_text} · {qrp_text} · {brp_text}"


def render(value, advanced=False):
    lines = [
        summary_line(value),
        "Reply 'ok' to confirm (`PB setup confirm`), or override via `PB policy --source solo|native|mixed|cap-catalog|cap-category --schedule parallel|serial --confirm`.",
    ]
    if advanced:
        lines.extend([
            "Core sources: solo | native | native-cheap | native-pinned",
            "Power features (opt-in): mixed | cap-catalog | cap-category | cap-pinned | --qrp on|off [--qrp-threshold N] | --relay on|off [--relay-threshold N]",
        ])
    return lines


def _render_relay_active(state, line):
    d = state["director"]
    who = d["route"] + ("/" + d["model"] if d.get("model") else "")
    return [
        "Background relay is %s (gen %d, director %s)." % (state["status"], state["generation"], who),
        line,
        "Choose: 1. Continue in background [default] | 2. Graceful stop (2 min save) | 3. Stop and take over",
    ]


def _render_quota_waiting(recovery):
    return [
        "Background quota recovery is %s (checkpoint: %s, wake_at: %s)."
        % (recovery["status"], recovery.get("checkpoint") or "?", recovery.get("wake_at") or "?"),
        "Choose: 1. Keep waiting [default] | 2. Cancel wait and take over | 3. Stop completely",
    ]


def ask(B, root, now=None, advanced=False):
    if E.relay_authorized(B, root) or E.relay_stopping_holder(B, root):
        return {
            "status": "RELAY_SUCCESSOR",
            "lines": ["Settings inherited from previous relay director; no setup prompt required."],
        }
    now = time.time() if now is None else now
    with B.checkout_lock(root):
        session = E._session(B, root) or E.begin_session(B, root)
        line = RL.boot_line(B, root)
        try:
            state = RL.read(B, root)
        except ValueError:
            state = None
        if state and state.get("status") in ("ACTIVE", "HANDOFF_PENDING", "STOPPING", "EXHAUSTED"):
            rec = {
                "schema": 1,
                "nonce": session["nonce"],
                "asked_at": now,
                "mode": "relay_active",
                "defaults": defaults(B, root),
            }
            Core.write_atomic(_path(B, root), json.dumps(rec, indent=2))
            return {"status": "RELAY_ACTIVE", "lines": _render_relay_active(state, line or "")}
        recovery = Q.status(B, root)
        if recovery.get("status") in ("PREPARED", "ARMED"):
            rec = {
                "schema": 1,
                "nonce": session["nonce"],
                "asked_at": now,
                "mode": "quota_waiting",
                "defaults": defaults(B, root),
            }
            Core.write_atomic(_path(B, root), json.dumps(rec, indent=2))
            return {"status": "QUOTA_WAITING", "lines": _render_quota_waiting(recovery)}
        value = defaults(B, root)
        rec = {
            "schema": 1,
            "nonce": session["nonce"],
            "asked_at": now,
            "mode": "setup",
            "defaults": value,
        }
        Core.write_atomic(_path(B, root), json.dumps(rec, indent=2))
    return {"status": "ASKED", "summary": summary_line(value), "defaults": value, "lines": render(value, advanced=advanced)}


def _record(B, root):
    path = _path(B, root)
    if not path.is_file():
        raise ValueError("SETUP_NOT_ASKED: run `setup ask` first")
    value = Core.read_json(path, max_bytes=65536, strict_constants=True)
    if not isinstance(value, dict) or value.get("schema") != 1 or not isinstance(value.get("asked_at"), (int, float)):
        raise ValueError("Malformed setup record; run `setup ask` again")
    session = E._session(B, root)
    if value.get("nonce") != (session or {}).get("nonce"):
        raise ValueError("SETUP_STALE: run `setup ask` in the current session")
    return value


def confirm(B, root, note="User confirmed session policy", now=None):
    """Immediately confirm the active/default policy without a blocking wait loop."""
    with B.checkout_lock(root):
        path = _path(B, root)
        if path.is_file():
            try:
                record = _record(B, root)
            except ValueError:
                record = None
        else:
            record = None
        if record and record.get("mode") in ("relay_active", "quota_waiting"):
            return {
                "status": "CONTINUE_BACKGROUND",
                "mode": record["mode"],
                "note": "Background operation continues untouched",
            }
        try:
            live_relay = RL.read(B, root)
        except ValueError:
            live_relay = None
        if live_relay and live_relay.get("status") in ("ACTIVE", "HANDOFF_PENDING", "STOPPING", "EXHAUSTED"):
            return {
                "status": "CONTINUE_BACKGROUND",
                "mode": "relay_active",
                "note": "Background relay continues untouched; use `PB relay stop` to stop it",
            }
        live_qrp = Q.status(B, root)
        if live_qrp.get("status") in ("PREPARED", "ARMED"):
            return {
                "status": "CONTINUE_BACKGROUND",
                "mode": "quota_waiting",
                "note": "Background quota recovery continues untouched; use `PB quota cancel` to cancel it",
            }
        chosen = copy.deepcopy(record["defaults"]) if record else defaults(B, root)
        chosen["origin"] = "user"
        E.save(B, root, chosen, note)
        E.confirm(B, root, note)
        if record is not None:
            record["status"] = "resolved"
            Core.write_atomic(path, json.dumps(record, ensure_ascii=False, indent=2))
        return {"status": "CONFIRMED", "note": note, "summary": summary_line(chosen), "policy": E.summary(B, root)}


def wait(B, root, now=None, sleep=time.sleep, timeout=TIMEOUT):
    """Optional bounded wait slice for unattended headless hosts (never mandatory)."""
    record = _record(B, root)
    start_now = time.time() if now is None else now
    left = max(0.0, timeout - (start_now - record["asked_at"]))
    if left > 0:
        nap = min(SLICE, left)
        sleep(nap)
        after_now = time.time() if now is None else (start_now + nap)
        left = max(0.0, timeout - (after_now - record["asked_at"]))
    done = left <= 0.5
    return {
        "status": "TIMEOUT_REACHED" if done else "WAITING",
        "seconds_left": 0 if done else int(left),
        "next": "setup defaults" if done else "check for user reply, or confirm directly with `setup confirm`",
    }


def apply_defaults(B, root, accepted=False, now=None, timeout=TIMEOUT):
    with B.checkout_lock(root):
        record = _record(B, root)
        now = time.time() if now is None else now
        if not accepted and now - record["asked_at"] < timeout:
            raise ValueError(
                "SETUP_WAIT: %d seconds remain before unattended defaults apply; use `setup confirm` or `--accepted` when confirmed"
                % int(timeout - (now - record["asked_at"]))
            )
        if record.get("mode") in ("relay_active", "quota_waiting"):
            return {
                "status": "CONTINUE_BACKGROUND",
                "mode": record["mode"],
                "note": "Background operation continues untouched",
            }
        if E.load(B, root) is not None and E.confirmed(B, root):
            return {"status": "ALREADY_CONFIRMED", "policy": E.summary(B, root)}
        note = "User accepted shown session policy" if accepted else "Unattended safe core defaults applied"
        chosen = copy.deepcopy(record["defaults"])
        chosen["origin"] = "user" if accepted else "defaults"
        E.save(B, root, chosen, note)
        E.confirm(B, root, note)
        record["status"] = "resolved"
        Core.write_atomic(_path(B, root), json.dumps(record, ensure_ascii=False, indent=2))
        return {"status": "DEFAULTS_CONFIRMED", "note": note, "summary": summary_line(chosen), "policy": E.summary(B, root)}


def recover_cap(B, root, role="exec"):
    """Authorize a new native job when CAP is unavailable; never replay uncertain CAP jobs."""
    with B.checkout_lock(root):
        RL.require_free_or_director(B, root)
        value = E.require_confirmed(B, root)
        result = E.cap_unavailable(value, role)
        if result["action"] == "CONTINUE_NATIVE" and value[E._role(role)]["source"] != "mixed":
            chosen = copy.deepcopy(value)
            chosen[E._role(role)] = {"source": "native"}
            E.save(B, root, chosen, "Authorized native fallback after CAP unavailability")
            E.confirm(B, root, "Native fallback; notify user before new dispatch")
        result["next"] = "Notify user; read back any uncertain CAP job before replacement work"
        return result


def add_parser(sub):
    p = sub.add_parser("setup", help="Default-safe single-line session setup and CAP fallback")
    p.add_argument("action", choices=("ask", "confirm", "defaults", "wait", "recover-cap"))
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--accepted", action="store_true")
    p.add_argument("--advanced", action="store_true", help="Show opt-in power features (CAP/QRP/BRP)")
    p.add_argument("--note", default="")
    p.add_argument("--role", choices=("exec", "rev"), default="exec")


def command(B, args):
    root = Path(args.root).resolve()
    director_recovery = args.action == "recover-cap" and E.relay_authorized(B, root)
    if Core.worker_env_active() and not director_recovery:
        if args.action == "ask":
            return {"status": "INHERITED", "lines": ["Workers inherit session settings; no setup prompt required."]}
        raise ValueError("Workers inherit settings; they never answer setup questions")
    if not B.brain_exists(root):
        raise ValueError("Initialize Brain before session setup")
    if args.action == "ask":
        return ask(B, root, advanced=getattr(args, "advanced", False))
    if args.action == "confirm":
        return confirm(B, root, note=args.note or "User confirmed session policy")
    if args.action == "wait":
        return wait(B, root)
    if args.action == "recover-cap":
        return recover_cap(B, root, args.role)
    return apply_defaults(B, root, accepted=args.accepted)
