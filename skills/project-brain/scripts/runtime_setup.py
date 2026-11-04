"""One batched new-session setup question with a 5-minute default; stdlib, Python 3.8+.

`setup ask` prints numbered plain-language questions with the default under each
and records when they were asked. Explicit answers are saved with `policy --file
--confirm`. Without an answer, `setup wait` sleeps in short slices (so the host can
deliver a reply between them) and `setup defaults` saves and confirms the shown
defaults once 5 minutes have passed, or at once when the user said "use defaults".
A relay successor inherits the launcher's confirmed settings and is never asked.
"""
import copy
import json
import os
import time

import runtime_executor_policy as E
import runtime_verify as V

TIMEOUT = 300
SLICE = 60
LABELS = {"solo": "Solo (I work alone with tools)", "native": "Native (host models)",
          "native-cheap": "Native Cheapest", "native-pinned": "Native Pinned",
          "cap-category": "CAP Categories", "cap-catalog": "CAP Catalog", "cap-pinned": "CAP Pinned"}
BUILTIN = {"schema": 1, "execution": {"source": "solo"}, "scheduling": {"mode": "serial", "max_parallel": 1},
           "quota_recovery": {"enabled": False, "threshold_percent": 10}}


def _path(B, root):
    return V.public_path(root, B.BRAIN_DIR + "/.cache/setup.json")


def defaults(B, root):
    """Saved policy when one exists, else the built-in conservative choice."""
    saved = E.load(B, root)
    value = copy.deepcopy(saved) if saved and E.last_confirmed(B, root) else copy.deepcopy(BUILTIN)
    value.pop("note", None)
    return value


def _source(selector):
    text = LABELS.get(selector["source"], selector["source"])
    if selector.get("categories"):
        text += ": " + ", ".join(selector["categories"])
    if selector.get("models"):
        text += ": " + ", ".join(m.get("routeId", m.get("host", "")) + "/" + m.get("modelId", m.get("model", ""))
                                 for m in selector["models"])
    return text


def questions(value):
    s, q = value["scheduling"], value["quota_recovery"]
    relay = value.get("relay") or {"enabled": False, "threshold_percent": 10}
    director = ("routes " + ", ".join(c["route"] + ("/" + c["model"] if c.get("model") else "")
                                      for c in relay.get("candidates", []))
                if relay.get("candidates") else "same tier as this director"
                if relay.get("director_category", "same") == "same" else "CAP category " + relay["director_category"])
    on = lambda flag, pct: ("On, at %d%% remaining" % pct) if flag else "Off"
    return [
        ("Who does the work? Solo, Native, Native Cheapest, Native Pinned, or CLI Agent Pool "
         "(CAP) Categories/Catalog/Pinned. For CAP Categories name the worker tier, e.g. high, medium, low.",
         _source(value["execution"])),
        ("Run jobs one at a time (Serial) or in parallel? If parallel, how many at most?",
         "Parallel (%d)" % s["max_parallel"] if s["mode"] == "parallel" else "Serial (1)"),
        ("Quota Recovery (QRP): when my quota runs low, stop and wait for it to renew on this same account?",
         on(q["enabled"], q["threshold_percent"])),
        ("Baton Relay (BRP): when my quota runs low, hand the director role to another signed-in CAP account?",
         on(relay.get("enabled"), relay["threshold_percent"])),
        ("Director tier for relay successors: a CAP category, the same tier as me, or exact routes?", director),
    ]


def render(value):
    lines = ["Setup for this session (answer once; reply with numbers to change, e.g. \"2: parallel 4\"):"]
    for number, (question, default) in enumerate(questions(value), 1):
        lines += ["%d. %s" % (number, question), "   Default: " + default]
    lines.append("No reply within 5 minutes = I continue with these defaults.")
    return lines


def ask(B, root, now=None):
    import runtime_relay as RL
    if RL.authorized(B, root):
        return {"status": "RELAY_SUCCESSOR", "lines": ["Settings inherited from the relay launcher; ask no setup questions."]}
    line = RL.boot_line(B, root)
    if line and line.startswith("RELAY: ACTIVE") or line and line.startswith("RELAY: HANDOFF_PENDING"):
        return {"status": "RELAY_ACTIVE", "lines": [line, "Ask setup questions only if the user wants to change the policy."]}
    value = defaults(B, root)
    now = time.time() if now is None else now
    B.write_atomic(_path(B, root), json.dumps({"schema": 1, "asked_at": now, "defaults": value}, indent=2))
    return {"status": "ASKED", "timeout_seconds": TIMEOUT, "lines": render(value)}


def _record(B, root):
    path = _path(B, root)
    if not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("SETUP_NOT_ASKED: run `setup ask` first")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != 1 or not isinstance(value.get("asked_at"), (int, float)):
        raise ValueError("Malformed setup record; run `setup ask` again")
    return value


def wait(B, root, now=None, sleep=time.sleep):
    """Sleeps at most one slice; returns the seconds left before defaults apply."""
    record = _record(B, root)
    now = time.time() if now is None else now
    left = max(0, TIMEOUT - (now - record["asked_at"]))
    if left > 0:
        sleep(min(SLICE, left))
        left = max(0, left - SLICE)
    return {"status": "TIMEOUT_REACHED" if left <= 0 else "WAITING", "seconds_left": int(left),
            "next": "setup defaults" if left <= 0 else "check for a user reply, then setup wait again"}


def apply_defaults(B, root, accepted=False, now=None):
    record = _record(B, root)
    now = time.time() if now is None else now
    if not accepted and now - record["asked_at"] < TIMEOUT:
        raise ValueError("SETUP_WAIT: %d seconds remain before defaults apply; use --accepted only if the user said so"
                         % int(TIMEOUT - (now - record["asked_at"])))
    if E.load(B, root) is not None and E.confirmed(B, root):
        return {"status": "ALREADY_CONFIRMED", "policy": E.summary(B, root)}
    note = "User accepted the shown defaults" if accepted else "Defaults after 5-minute setup timeout (no reply)"
    with B.checkout_lock(root):
        E.save(B, root, record["defaults"], note)
        E.confirm(B, root, note)
    return {"status": "DEFAULTS_CONFIRMED", "note": note, "policy": E.summary(B, root)}


def add_parser(sub):
    p = sub.add_parser("setup", help="One batched new-session setup question with a 5-minute default")
    p.add_argument("action", choices=("ask", "wait", "defaults"))
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--accepted", action="store_true")


def command(B, args):
    from pathlib import Path
    if os.environ.get("CLI_AGENT_POOL_WORKER"):
        if args.action == "ask":
            return {"status": "INHERITED", "lines": ["Workers inherit settings; ask no setup questions."]}
        raise ValueError("Workers inherit settings; they never answer setup questions")
    root = Path(args.root).resolve()
    if not B.brain_exists(root):
        raise ValueError("Initialize Brain before session setup")
    if args.action == "ask":
        return ask(B, root)
    if args.action == "wait":
        return wait(B, root)
    return apply_defaults(B, root, accepted=args.accepted)
