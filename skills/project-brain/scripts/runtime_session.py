"""Bounded orientation and durable user-intake continuity, without model calls."""
import contextlib
import io
import json
from pathlib import Path
import re

import runtime_verify as V


def ledger_path(B, root):
    return V.public_path(root, B.BRAIN_DIR + "/requests.json")


def ledger(B, root):
    file = ledger_path(B, root)
    if not file.exists():
        return {"schema": 1, "requests": []}
    data = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("requests"), list) or len(data["requests"]) > 100:
        raise ValueError("Malformed request ledger; preserve and inspect it")
    for row in data["requests"]:
        if (not isinstance(row, dict) or not re.fullmatch(r"RQ-\d{3,}", str(row.get("id", "")))
                or row.get("status") not in ("open", "linked", "answered")
                or row.get("relation") not in ("related", "question", "new-work", "cancel")
                or not isinstance(row.get("items"), list) or not 1 <= len(row["items"]) <= 32
                or any(not isinstance(item, str) or not 1 <= len(item) <= 500 for item in row["items"])):
            raise ValueError("Malformed request ledger entry")
    return data


def focus(B, root):
    tasks = B.list_tasks(root)
    active = next((task for task in tasks if task["status"] in ("IN_PROGRESS", "REVIEW")), None)
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
            raise ValueError("Request ledger full; reconcile/archive answered records, never discard unresolved work")
        from runtime_security import require_clean
        require_clean("\n".join(items), "request intake")
        number = max([int(row["id"].split("-")[1]) for row in data["requests"]] + [0]) + 1
        row = {"id": "RQ-%03d" % number, "items": [item.strip() for item in items],
               "relation": relation, "status": "linked" if task else "open", "task": task,
               "resume_task": focus(B, root)}
        data["requests"].append(row)
    B.write_atomic(ledger_path(B, root), json.dumps(data, ensure_ascii=False, indent=2))
    return {"request": row, "resume_task": row.get("resume_task", ""),
            "next": "Answer the question, then resume the saved task/Resume; only explicit cancellation replaces it"}


def boot_summary(B, root):
    data = ledger(B, root)
    pending = [row for row in data["requests"] if row["status"] == "open"]
    if pending:
        print("INTAKE_PENDING: " + ", ".join(row["id"] + " (" + str(len(row["items"])) + " items)" for row in pending[:8]))
        print("INTAKE_LOAD: .project-brain/requests.json; map every requirement to a task or an answer; retain active FOCUS")


def orient(B, root):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        B.cmd_map(root)
    lines = output.getvalue().splitlines()
    selected = [line for line in lines if line.startswith(("FILES:", "ROOT FILES:", "EXTENSIONS:", "INSTRUCTION/DOC FILES:", "CMDS:"))]
    selected.extend(line for line in lines if line.startswith("  ") and not line.startswith("    "))
    modes = B.get_session_modes(root)
    result = {"orientation": [line[:240] for line in selected[:15]], "focus": focus(B, root) if B.brain_exists(root) else "",
              "session": {key: modes[key] for key in ("exec", "rev", "schedule", "max_parallel", "task_mode")}, "implementation_gate": "ready" if modes["exec"] and modes["rev"] else "ask-user",
              "next": "Metadata only. Inspect at most 5 relevant manifests/entrypoints, then ask once for EXEC, REV, serial/parallel and response/execute. No model/provider call was made."}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0
