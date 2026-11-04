"""Baton Relay Policy (BRP): director circulation across pre-authorized CLI accounts.

When the director's quota reaches the user's threshold it checkpoints, picks the
next listed CAP route that still has quota, starts that route as the new director
through CLI Agent Pool and stops. The successor takes the baton with a one-time
token, cancels the previous director task if it is still running, and continues.
Logins are never touched: every account was signed in once in the Pool.

The relay record lives in the ignored Brain cache so worktrees never inherit it.
Tokens are stored only as hashes. Python 3.8+, standard library only.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import time

import runtime_security as S
import runtime_verify as V

MAX_RECORD = 65536
MAX_HISTORY = 200
HASH = re.compile(r"^[0-9a-f]{64}$")
TOKEN = re.compile(r"^[0-9a-f]{32}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,199}$")
STATES = {"ACTIVE", "HANDOFF_PENDING", "STOPPED", "COMPLETED"}
LIVE = {"ACTIVE", "HANDOFF_PENDING"}
TOKEN_ENV = "PB_RELAY_TOKEN"
DEFAULT_THRESHOLD = 10
DIRECTOR_TIMEOUT = 6 * 3600


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _name(value, label):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError(label + " must be a bounded route/model/effort name")
    return value


def validate_policy(value):
    """Validates the optional executor-policy `relay` block; returns a normalized copy."""
    if not isinstance(value, dict):
        raise ValueError("Relay policy must be an object")
    allowed = {"enabled", "threshold_percent", "candidates", "max_handoffs"}
    if set(value) - allowed or not {"enabled", "threshold_percent"} <= set(value):
        raise ValueError("Relay requires enabled and threshold_percent; optional candidates, max_handoffs")
    if type(value["enabled"]) is not bool:
        raise ValueError("Relay enabled must be true or false")
    threshold = value["threshold_percent"]
    if type(threshold) is not int or not 1 <= threshold <= 50:
        raise ValueError("Relay threshold_percent must be an integer 1..50")
    result = {"enabled": value["enabled"], "threshold_percent": threshold}
    candidates = value.get("candidates", [])
    if not isinstance(candidates, list) or len(candidates) > 32 or (value["enabled"] and not candidates):
        raise ValueError("An enabled relay needs 1..32 candidate routes")
    normalized, seen = [], set()
    for item in candidates:
        if not isinstance(item, dict) or set(item) - {"route", "model", "effort"} or "route" not in item:
            raise ValueError("Relay candidates are {route, model?, effort?}")
        entry = {"route": _name(item["route"], "Relay route")}
        if entry["route"] is None:
            raise ValueError("Relay candidate route is required")
        for key in ("model", "effort"):
            if item.get(key):
                entry[key] = _name(item[key], "Relay " + key)
        key = (entry["route"], entry.get("model"), entry.get("effort"))
        if key in seen:
            raise ValueError("Relay candidates must be unique")
        seen.add(key)
        normalized.append(entry)
    result["candidates"] = normalized
    limit = value.get("max_handoffs", 50)
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("Relay max_handoffs must be an integer 1..500")
    result["max_handoffs"] = limit
    return result


def _policy(policy):
    relay = policy.get("relay") if isinstance(policy, dict) else None
    if not isinstance(relay, dict) or relay.get("enabled") is not True:
        raise ValueError("RELAY_DISABLED: save an enabled relay block in the executor policy first")
    relay = validate_policy(relay)
    raw = json.dumps(relay, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return relay, _hash(raw)


def _path(B, root):
    return V.public_path(root, B.BRAIN_DIR + "/.cache/relay.json")


def read(B, root):
    path = _path(B, root)
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_RECORD:
        raise ValueError("Relay record exceeds its bound; authority withheld")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        director = state.get("director")
        valid = (isinstance(state, dict) and state.get("schema") == 1 and state.get("status") in STATES
                 and HASH.fullmatch(state.get("policy_hash", "")) and type(state.get("generation")) is int
                 and state["generation"] >= 1 and isinstance(director, dict)
                 and isinstance(director.get("route"), str) and HASH.fullmatch(director.get("token_hash", ""))
                 and _number(director.get("since")) and isinstance(state.get("history"), list)
                 and (state.get("pending") is None or (isinstance(state["pending"], dict)
                      and HASH.fullmatch(state["pending"].get("token_hash", ""))))
                 and (state["status"] != "HANDOFF_PENDING" or state.get("pending") is not None))
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("Invalid relay record; authority withheld")
    return state


def _write(B, root, state):
    state["history"] = state["history"][-MAX_HISTORY:]
    B.write_atomic(_path(B, root), json.dumps(state, sort_keys=True, indent=2, allow_nan=False))


def _event(state, event, now, **extra):
    row = {"event": event, "at": now, "generation": state["generation"]}
    row.update({k: v for k, v in extra.items() if v is not None})
    state["history"].append(row)


def _iso(value):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value)) if _number(value) else None


def view(state):
    if state is None:
        return {"status": "NONE"}
    director = state["director"]
    result = {"status": state["status"], "generation": state["generation"],
              "director": {k: director.get(k) for k in ("route", "model", "effort", "task_id", "worker")},
              "director_since": _iso(director["since"]), "handoffs": sum(1 for r in state["history"] if r.get("event") == "HANDOFF")}
    if state.get("pending"):
        pending = state["pending"]
        result["pending"] = {k: pending.get(k) for k in ("route", "model", "effort", "task_id")}
        result["pending"]["requested_at"] = _iso(pending.get("requested_at"))
        if pending.get("checkpoint"):
            result["pending"]["checkpoint"] = pending["checkpoint"]["path"]
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
    if state is None or state["status"] not in LIVE:
        return None
    d = state["director"]
    text = ("RELAY: %s gen %d director %s%s since %s%s" % (
        state["status"], state["generation"], d["route"], "/" + d["model"] if d.get("model") else "",
        _iso(d["since"]), " (pool task " + d["task_id"] + ")" if d.get("task_id") else ""))
    if state.get("pending"):
        text += " -> pending " + state["pending"]["route"]
    return text + ". Another session must not run this project; use `relay stop` to end circulation."


def _token_ok(token_hash, token=None):
    token = token if token is not None else os.environ.get(TOKEN_ENV, "")
    return bool(TOKEN.fullmatch(token or "")) and secrets.compare_digest(_hash(token), token_hash)


def authorized(B, root, token=None):
    """True when this process holds the live director baton."""
    try:
        state = read(B, root)
    except ValueError:
        return False
    return bool(state and state["status"] == "ACTIVE" and _token_ok(state["director"]["token_hash"], token))


def require_free_or_director(B, root):
    """Single-director gate used before implementation work."""
    state = read(B, root)
    if state and state["status"] in LIVE and not _token_ok(state["director"]["token_hash"]):
        raise ValueError("RELAY_ACTIVE: " + (boot_line(B, root) or "a relay director owns this project"))


def worker_reserve(B, root, policy):
    """Minimum remaining quota for Pool workers while relay is enabled."""
    relay = policy.get("relay") if isinstance(policy, dict) else None
    return relay["threshold_percent"] if isinstance(relay, dict) and relay.get("enabled") is True else 0


def remaining(snapshot, model=None):
    """Lowest known remaining percentage that applies to the model, else None."""
    if not isinstance(snapshot, dict) or snapshot.get("status") == "auth_required":
        return None
    values = []
    for window in snapshot.get("windows") or []:
        if not isinstance(window, dict) or not _number(window.get("remainingPercent")):
            continue
        scopes = window.get("models")
        if model and isinstance(scopes, list) and scopes and not any(isinstance(s, str) and s.lower() in model.lower() for s in scopes):
            continue
        values.append(max(0, min(100, window["remainingPercent"])))
    return min(values) if values else None


def assess(snapshot, policy, model=None):
    relay, _ = _policy(policy)
    value = remaining(snapshot, model)
    if value is None:
        return {"status": "UNKNOWN", "threshold_percent": relay["threshold_percent"],
                "reason": "no applicable quota window; continue carefully and re-check later"}
    return {"status": "HANDOFF_REQUIRED" if value <= relay["threshold_percent"] else "READY",
            "remaining_percent": value, "threshold_percent": relay["threshold_percent"]}


def choose(policy, quotas, current_route):
    """Next candidate in circulation order after the current route with known quota above threshold."""
    relay, _ = _policy(policy)
    candidates = relay["candidates"]
    start = next((i + 1 for i, c in enumerate(candidates) if c["route"] == current_route), 0)
    ordered = candidates[start:] + candidates[:start]
    skipped = []
    for candidate in ordered:
        if candidate["route"] == current_route:
            continue
        value = remaining((quotas or {}).get(candidate["route"]), candidate.get("model"))
        if value is not None and value > relay["threshold_percent"]:
            return {"status": "SELECTED", "candidate": candidate, "remaining_percent": value}
        skipped.append({"route": candidate["route"], "remaining_percent": value})
    return {"status": "EXHAUSTED", "skipped": skipped,
            "advice": "No listed account has quota above the threshold; wait (QRP if enabled) or stop the relay."}


def _new_token():
    return secrets.token_hex(16)


def start(B, root, policy, route, model=None, effort=None, task_id=None, worker=False, now=None):
    relay, policy_hash = _policy(policy)
    now = time.time() if now is None else now
    with B.checkout_lock(root):
        state = read(B, root)
        if state and state["status"] in LIVE:
            raise ValueError("RELAY_ACTIVE: stop the running relay before starting another director")
        token = _new_token()
        new = {"schema": 1, "status": "ACTIVE", "policy_hash": policy_hash, "generation": 1,
               "director": {"route": _name(route, "Relay route"), "model": _name(model, "Relay model"),
                            "effort": _name(effort, "Relay effort"), "task_id": _name(task_id, "Pool task id"),
                            "worker": bool(worker), "token_hash": _hash(token), "since": now},
               "pending": None, "history": []}
        if new["director"]["route"] is None:
            raise ValueError("The current director route is required")
        _event(new, "START", now, route=route, model=model, threshold=relay["threshold_percent"])
        _write(B, root, new)
    return dict(view(new), token=token, token_env=TOKEN_ENV)


def successor_prompt(root, brain_script, token, generation, checkpoint, candidate):
    # Sent to CLI Agent Pool as the new director's task; not executed by Python.
    return ("Project Brain Baton Relay (BRP) director takeover, generation %d.\n"
            "Workspace: %s\n"
            "1. Set the environment variable %s=%s for every Project Brain command you run.\n"
            "2. First run: python \"%s\" relay takeover \"%s\". Continue only if it returns ACTIVE.\n"
            "3. Read the handoff checkpoint %s, run boot, and continue the saved task and Resume under the "
            "confirmed ESP/SP. You are the director: plan, delegate through CLI Agent Pool per policy, verify, accept.\n"
            "4. At meaningful checkpoints read your own route quota (cli-agent-pool pool_get_quotas routeId %s) "
            "and run `relay assess --snapshot <file>`. On HANDOFF_REQUIRED save the next step, read all candidate "
            "quotas, run `relay next --quotas <file>` and `relay handoff`, then stop working immediately.\n"
            "5. When every task is accepted run `relay complete`.\n"
            "Never log out, switch accounts, edit Pool/CLI credentials or start a second director." % (
                generation, root, TOKEN_ENV, token, brain_script, root, checkpoint, candidate["route"]))


def _checkpoint(B, root, task, next_step):
    import runtime_protocol as R
    R.progress(B, root, task, next_step)
    task = B.find_task(root, task["id"])
    R.handoff(B, root, task)
    return R.record_path(B, root, task["id"], "handoff")


def handoff(B, root, policy, task, next_step, candidate, brain_script, submit, now=None, token=None,
            write_checkpoint=_checkpoint):
    """Checkpoint, start the chosen successor through the Pool once, and record it."""
    relay, policy_hash = _policy(policy)
    now = time.time() if now is None else now
    if not isinstance(next_step, str) or not next_step.strip():
        raise ValueError("Save the actual next action before handing off")
    with B.checkout_lock(root):
        state = read(B, root)
        if not state or state["status"] not in LIVE:
            raise ValueError("RELAY_NOT_ACTIVE: start the relay first")
        if not _token_ok(state["director"]["token_hash"], token):
            raise ValueError("RELAY_NOT_DIRECTOR: only the current baton holder can hand off")
        if state["policy_hash"] != policy_hash:
            raise ValueError("RELAY_POLICY_CHANGED: confirm the policy and restart the relay")
        if not any(c == candidate for c in relay["candidates"]):
            raise ValueError("Successor must be a listed relay candidate")
        if sum(1 for r in state["history"] if r.get("event") == "HANDOFF") >= relay["max_handoffs"]:
            raise ValueError("RELAY_LIMIT: max_handoffs reached; the user must restart the relay")
        pending = state.get("pending")
        if pending and (pending.get("candidate") != candidate or pending.get("task_id")):
            raise ValueError("HANDOFF_PENDING: a successor was already started; read it back with relay status")
        successor_token = _new_token()
        if pending:
            # The earlier submit was not acknowledged. A fresh token and key make any
            # late duplicate of that submit unable to take the baton.
            pending.update(token_hash=_hash(successor_token), requested_at=now,
                           idempotency_key="pb-relay-%d-%s" % (state["generation"] + 1, secrets.token_hex(8)))
            _event(state, "HANDOFF_RETRY", now, route=candidate["route"])
        else:
            path = write_checkpoint(B, root, task, next_step)
            checkpoint = {"path": path.relative_to(root).as_posix(),
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            pending = {"candidate": candidate, "route": candidate["route"], "model": candidate.get("model"),
                       "effort": candidate.get("effort"), "token_hash": _hash(successor_token),
                       "requested_at": now, "checkpoint": checkpoint, "task_id": None,
                       "idempotency_key": "pb-relay-%d-%s" % (state["generation"] + 1, secrets.token_hex(8)),
                       "from_generation": state["generation"]}
            state["pending"], state["status"] = pending, "HANDOFF_PENDING"
            _event(state, "HANDOFF", now, route=candidate["route"], model=candidate.get("model"), task=task["id"])
        _write(B, root, state)
    prompt = successor_prompt(str(Path(root).resolve()), brain_script, successor_token,
                              state["generation"] + 1, pending["checkpoint"]["path"], candidate)
    request = {"prompt": prompt, "workspace": str(Path(root).resolve()), "kind": "write", "mode": "execute",
               "routeId": candidate["route"], "idempotencyKey": pending["idempotency_key"],
               "timeoutSeconds": DIRECTOR_TIMEOUT, "minRemainingPercent": relay["threshold_percent"],
               "clientLabel": "Project Brain relay director gen %d" % (state["generation"] + 1)}
    if candidate.get("model"):
        request["modelId"] = candidate["model"]
    if candidate.get("effort"):
        request["effort"] = candidate["effort"]
    submitted = submit(request)
    task_id = submitted.get("id") or submitted.get("taskId") if isinstance(submitted, dict) else None
    with B.checkout_lock(root):
        state = read(B, root)
        if state and state.get("pending") and state["pending"]["token_hash"] == pending["token_hash"]:
            state["pending"]["task_id"] = _name(task_id, "Pool task id") if task_id else None
            _write(B, root, state)
    return {"status": "HANDED_OFF", "successor": candidate, "pool_task": task_id,
            "checkpoint": pending["checkpoint"]["path"],
            "instruction": "Stop working now. The successor director takes over after this task ends."}


def takeover(B, root, policy, cancel, task_state, token=None, now=None):
    """Successor accepts the baton; stops the previous director task if still live."""
    relay, policy_hash = _policy(policy)
    now = time.time() if now is None else now
    with B.checkout_lock(root):
        state = read(B, root)
        if not state or state["status"] != "HANDOFF_PENDING" or not state.get("pending"):
            raise ValueError("RELAY_NO_HANDOFF: no pending baton for this project")
        pending = state["pending"]
        if not _token_ok(pending["token_hash"], token):
            raise ValueError("RELAY_TOKEN_MISMATCH: this process does not hold the pending baton")
        if state["policy_hash"] != policy_hash:
            raise ValueError("RELAY_POLICY_CHANGED: the user changed the policy; do no work")
        checkpoint = V.public_path(root, pending["checkpoint"]["path"])
        if not checkpoint.is_file() or hashlib.sha256(checkpoint.read_bytes()).hexdigest() != pending["checkpoint"]["sha256"]:
            raise ValueError("RELAY_CHECKPOINT_CHANGED: handoff checkpoint changed; ask the user")
        previous = state["director"]
        state["director"] = {"route": pending["route"], "model": pending.get("model"), "effort": pending.get("effort"),
                             "task_id": pending.get("task_id"), "worker": True,
                             "token_hash": pending["token_hash"], "since": now}
        state["generation"] += 1
        state["pending"], state["status"] = None, "ACTIVE"
        _event(state, "TAKEOVER", now, route=pending["route"], model=pending.get("model"),
               previous_route=previous["route"], previous_task=previous.get("task_id"))
        _write(B, root, state)
    cancelled = False
    previous_task = previous.get("task_id")
    if previous_task:
        try:
            if task_state(previous_task) in ("queued", "starting", "running"):
                cancel(previous_task)
                cancelled = True
        except ValueError:
            cancelled = False
    return dict(view(state), previous_director_cancelled=cancelled, checkpoint=pending["checkpoint"]["path"])


def finish(B, root, event, note, cancel=None, token=None, now=None):
    """COMPLETE (director) or STOP (user). Stop also cancels live director tasks."""
    now = time.time() if now is None else now
    note = (note or "")[:500]
    S.require_public(note, "relay note")
    with B.checkout_lock(root):
        state = read(B, root)
        if not state or state["status"] not in LIVE:
            return {"status": state["status"] if state else "NONE"}
        if event == "COMPLETE" and not _token_ok(state["director"]["token_hash"], token):
            raise ValueError("RELAY_NOT_DIRECTOR: only the baton holder can complete the relay")
        tasks = [t for t in (state["director"].get("task_id"), (state.get("pending") or {}).get("task_id")) if t]
        state["status"] = "COMPLETED" if event == "COMPLETE" else "STOPPED"
        state["pending"] = None
        _event(state, event, now, note=note or None)
        _write(B, root, state)
    cancelled = []
    if event == "STOP" and cancel:
        for task_id in tasks:
            try:
                cancel(task_id)
                cancelled.append(task_id)
            except ValueError:
                pass
    return dict(view(state), cancelled=cancelled)


def add_parser(sub):
    p = sub.add_parser("relay", help="Baton Relay Policy: director circulation across CAP accounts")
    p.add_argument("action", choices=("status", "start", "assess", "next", "handoff", "takeover", "complete", "stop"))
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
    if args.action == "stop":
        if os.environ.get("CLI_AGENT_POOL_WORKER") and not authorized(B, root):
            raise ValueError("Workers cannot stop another director's relay")
        return finish(B, root, "STOP", args.note or "User stopped the relay",
                      cancel=lambda task_id: pool.rpc("pool_cancel_task", {"taskId": task_id}))
    policy = E.load(B, root)
    if args.action == "takeover":
        return takeover(B, root, policy, cancel=lambda task_id: pool.rpc("pool_cancel_task", {"taskId": task_id}),
                        task_state=lambda task_id: (pool.rpc("pool_get_task", {"taskId": task_id}) or {}).get("state"))
    E.require_confirmed(B, root)
    if args.action == "assess":
        return assess(CT.read_input(root, args.snapshot) if args.snapshot else None, policy, args.model or None)
    if args.action == "next":
        state = read(B, root)
        current = state["director"]["route"] if state else args.route
        return choose(policy, CT.read_input(root, args.quotas) if args.quotas else {}, current)
    if args.action == "complete":
        return finish(B, root, "COMPLETE", args.note)
    if args.action == "start":
        if os.environ.get("CLI_AGENT_POOL_WORKER"):
            raise ValueError("A Pool worker cannot start a relay; the host director starts it")
        if B.get_session_modes(root)["task_mode"] != "execute":
            raise ValueError("Relay circulation requires an execute session")
        return start(B, root, policy, args.route, args.model or None, args.effort or None, args.pool_task or None)
    # handoff
    task = B.find_task(root, args.task) if args.task else None
    if not task:
        raise ValueError("Handoff needs the active --task")
    candidate = {"route": _name(args.route, "Relay route")}
    if candidate["route"] is None:
        raise ValueError("Handoff needs the successor --route")
    if args.model:
        candidate["model"] = _name(args.model, "Relay model")
    if args.effort:
        candidate["effort"] = _name(args.effort, "Relay effort")
    script = str(Path(__file__).resolve().parent / "brain.py")
    return handoff(B, root, policy, task, args.next_step, candidate, script,
                   submit=lambda request: pool.rpc("pool_submit", request))
