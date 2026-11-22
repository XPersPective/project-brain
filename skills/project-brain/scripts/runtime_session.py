"""Bounded orientation, brief continuity, and durable user-intake ledger. No model calls."""
import contextlib
import io
import json
from pathlib import Path

import runtime_core as Core
import runtime_executor_policy as E
import runtime_protocol as R
import runtime_quota_recovery as Q
import runtime_relay as RL
import runtime_runs as runs
import runtime_security as S

# Single source of truth for requests.json lives in runtime_protocol.
ledger_path = R.ledger_path
ledger = R.ledger


def active_task(tasks):
    """Match boot: an implementation in progress takes precedence over review."""
    return next((t for status in ("IN_PROGRESS", "REVIEW") for t in tasks if t["status"] == status), None)


def focus(B, root):
    tasks = B.list_tasks(root)
    active = active_task(tasks)
    return active["id"] if active else ""


def intake(B, root, items, relation="related", task="", resolve=""):
    if not B.brain_exists(root):
        raise ValueError("Initialize Brain before recording durable intake")
    data = ledger(B, root)
    task = B.norm_id("PB", task) if task else ""
    if task and not B.find_task(root, task):
        raise ValueError("Linked task not found")
    if resolve:
        row = next((row for row in data["requests"] if row["id"] == resolve), None)
        if row is None or items:
            raise ValueError("Resolve one existing request without adding new items")
        if not task and row["relation"] != "question":
            raise ValueError("A directive needs a task link; it cannot be silently marked answered")
        row.update(status="linked" if task else "answered", task=task)
    else:
        if relation not in ("related", "question", "new-work", "cancel") or not 1 <= len(items) <= 32:
            raise ValueError("Record 1..32 separate requirement items and a valid relation")
        if any(not isinstance(item, str) or not 1 <= len(item.strip()) <= 500 or any(ord(ch) < 32 for ch in item) for item in items):
            raise ValueError("Each intake item must be 1..500 characters without control characters")
        if len(data["requests"]) >= 100:
            answered = [r for r in data["requests"] if r.get("status") in ("answered", "linked")]
            if answered:
                to_remove = set(r["id"] for r in answered[: max(1, len(data["requests"]) - 90)])
                data["requests"] = [r for r in data["requests"] if r["id"] not in to_remove]
            if len(data["requests"]) >= 100:
                raise ValueError("Request ledger full; reconcile/archive answered records, never discard unresolved work")
        S.require_clean("\n".join(items), "request intake")
        number = max([int(row["id"].split("-")[1]) for row in data["requests"]] + [0]) + 1
        row = {
            "id": "RQ-%03d" % number,
            "items": [item.strip() for item in items],
            "relation": relation,
            "status": "linked" if task else "open",
            "task": task,
            "resume_task": focus(B, root),
        }
        data["requests"].append(row)
    Core.write_atomic(ledger_path(B, root), json.dumps(data, ensure_ascii=False, indent=2))
    return {
        "request": row,
        "resume_task": row.get("resume_task", ""),
        "next": "Answer the question, then resume saved task/Resume; only explicit cancellation replaces it",
    }


def brief(B, root):
    """Read-only continuity (<=4 KiB), never a startup, execution or acceptance gate."""
    def clip(value, size=160):
        return S.sanitize(str(value))[:size]

    root = Path(root).resolve()
    value = {
        "schema": 1,
        "observational": True,
        "gate": "not_evaluated",
        "note": "Read-only summary; does not replace boot, verification or acceptance",
    }
    if not B.brain_exists(root):
        value["status"] = "no_brain"
    else:
        tasks = B.list_tasks(root)
        if any(task["status"] == "?" for task in tasks):
            raise ValueError("Malformed task state; inspect tasks before continuing")
        active = active_task(tasks)
        value["focus"] = None
        value["focus_scope"] = "IN_PROGRESS before REVIEW; READY selection not evaluated"
        if active:
            resume = active.get("resume_lines", [])
            view = [clip(line) for line in resume[:4]]
            value["focus"] = {
                "id": active["id"],
                "status": active["status"],
                "resume": view,
                "resume_omitted": view != resume,
                "path": B.BRAIN_DIR + "/tasks/" + active["id"] + ".md",
            }
        modes = B.get_session_modes(root)
        value["session"] = {k: modes[k] for k in ("exec", "rev", "schedule", "max_parallel", "task_mode")}
        pending = [r for r in ledger(B, root)["requests"] if r["status"] == "open"]
        value["intake"] = {
            "pending_total": len(pending),
            "sample_ids": [r["id"] for r in pending[:3]],
            "omitted": max(0, len(pending) - 3),
            "path": B.BRAIN_DIR + "/requests.json",
        }
        external = [
            (t["id"], e)
            for t in tasks
            for e in t.get("external", [])
            if e["state"] in ("sent", "response_unknown")
        ]
        refs = [
            {
                "task": tid,
                "state": e["state"],
                "op": clip(e["op"] or e["line"], 120),
                "op_truncated": len(S.sanitize(e["op"] or e["line"])) > 120,
            }
            for tid, e in external[:3]
        ]
        value["external"] = {
            "unresolved_total": len(external),
            "sample_refs": refs,
            "omitted": max(0, len(external) - 3),
            "path": B.BRAIN_DIR + "/tasks/",
        }
        rows = runs.peek(B, root)
        value["runs"] = {
            "readback_count_lower_bound": len(rows),
            "total_unknown": len(rows) >= 8,
            "sample_runs": [{k: clip(r.get(k, ""), 80) for k in ("run", "task", "state")} for r in rows[:2]],
            "omitted_from_sample": max(0, len(rows) - 2),
            "details": "PB runs status",
        }
        value["readback_required"] = bool(external or rows)
        if E.load(B, root):
            value["policy"] = E.summary(B, root)
        recovery = Q.status(B, root)
        if recovery["status"] != "NONE":
            value["quota_recovery"] = recovery
        try:
            rel = RL.read(B, root)
        except ValueError:
            rel = {"status": "INVALID"}
        if rel and rel.get("status") not in (None, "NONE", "STOPPED", "COMPLETED"):
            value["relay"] = {"status": rel.get("status"), "generation": rel.get("generation")}

    def encode():
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    raw = encode()
    while len(raw.encode("utf-8")) > 4095:
        focus_info = value.get("focus")
        if focus_info and focus_info["resume"]:
            focus_info["resume"].pop()
            focus_info["resume_omitted"] = True
        elif value.get("external", {}).get("sample_refs"):
            value["external"]["sample_refs"].pop()
            value["external"]["omitted"] += 1
        elif value.get("runs", {}).get("sample_runs"):
            value["runs"]["sample_runs"].pop()
            value["runs"]["omitted_from_sample"] += 1
        elif value.get("intake", {}).get("sample_ids"):
            value["intake"]["sample_ids"].pop()
            value["intake"]["omitted"] += 1
        elif isinstance(value.get("policy"), dict) and len(value["policy"]) > 2:
            value["policy"] = {"confirmed": value["policy"].get("confirmed", False), "omitted": True}
        elif isinstance(value.get("quota_recovery"), dict) and len(value["quota_recovery"]) > 1:
            value["quota_recovery"] = {"status": value["quota_recovery"].get("status")}
        else:
            raise ValueError("Continuity references exceed brief budget; inspect Brain state directly")
        raw = encode()
    print(raw)
    return 0


def boot_summary(B, root):
    pol = E.summary(B, root)
    if pol.get("policy") is not None or pol.get("schema"):
        print("POLICY: " + json.dumps(pol, separators=(",", ":")))
    recovery = Q.status(B, root)
    if recovery["status"] != "NONE":
        print("QUOTA_RECOVERY: " + json.dumps(recovery, separators=(",", ":")))
    for row in runs.peek(B, root):
        print(
            "RUN_READBACK: "
            + json.dumps(row, separators=(",", ":"))
            + " | inspect existing backend job before takeover; no replay"
        )
    data = ledger(B, root)
    pending = [row for row in data["requests"] if row["status"] == "open"]
    if pending:
        print("INTAKE_PENDING: " + ", ".join(row["id"] + " (" + str(len(row["items"])) + " items)" for row in pending[:8]))
        print("INTAKE_LOAD: .project-brain/requests.json; map every requirement to a task or answer; retain active FOCUS")


def orient(B, root, maintain=True, startup_fn=None):
    maintenance = startup_fn(root, maintain=maintain) if startup_fn is not None else []
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        B.cmd_map(root)
    lines = output.getvalue().splitlines()
    selected = [line for line in lines if line.startswith(("FILES:", "ROOT FILES:", "EXTENSIONS:", "INSTRUCTION/DOC FILES:", "CMDS:"))]
    selected.extend(line for line in lines if line.startswith("  ") and not line.startswith("    "))
    modes = B.get_session_modes(root)
    try:
        E.require_confirmed(B, root)
        policy_ready = True
    except ValueError:
        policy_ready = False
    gate = "ready" if (policy_ready and modes["exec"] and modes["rev"]) else "confirm-policy"
    result = {
        "orientation": [line[:240] for line in selected[:15]],
        "maintenance": maintenance[:8],
        "focus": focus(B, root) if B.brain_exists(root) else "",
        "session": {key: modes[key] for key in ("exec", "rev", "schedule", "max_parallel", "task_mode")},
        "implementation_gate": gate,
        "next": "Metadata only. Run `boot --new-session` and confirm session policy once; intervening questions use `brief`.",
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0
