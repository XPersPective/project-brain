"""Policy and director recovery CLI. Host scheduling remains an explicit tool call."""
import json
import os
from pathlib import Path

import runtime_executor_policy as E
import runtime_quota_recovery as Q
import runtime_verify as V


def add_parser(sub):
    p = sub.add_parser("policy", help="View/save/confirm ESP, SP and QRP")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--file", default="")
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--note", default="")
    p.add_argument("--full", action="store_true")
    p = sub.add_parser("qualify", help="Record exact model task-fit assessment, not acceptance evidence")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--route", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--tier", choices=("L", "M", "H"), required=True)
    p.add_argument("--note", required=True)
    p = sub.add_parser("quota", help="Director quota checkpoint and host wake guards")
    p.add_argument("action", choices=("status", "assess", "prepare", "arm", "resume", "cancel"))
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--snapshot", default="")
    p.add_argument("--checkpoint", default="")
    p.add_argument("--task", default="")
    p.add_argument("--next", dest="next_step", default="")
    p.add_argument("--nonce", default="")
    p.add_argument("--automation-id", default="")
    p.add_argument("--note", default="")
    p.add_argument("--rearm", action="store_true")


def read_input(root, name):
    path = V.public_path(root, name)
    if not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("A bounded project-local JSON input is required")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=E._pairs)


def wake_prompt(root, nonce):
    # This prompt is sent through the host automation tool, not executed by Python.
    return ("Project Brain quota recovery for the same chat and workspace. Before any coding, "
            "read the saved QRP state and obtain the CURRENT director account/quota snapshot "
            "using the host usage tool. Save only this metadata in the ignored Brain cache. "
            "Run PB quota resume --nonce " + nonce + " --snapshot <cache snapshot>. "
            "Proceed only on RESUMED: this verifies account, policy, checkpoint and renewal. "
            "On account change/cancellation/stale policy, delete this heartbeat and do no work. "
            "On WAIT, do no coding and wait for a later observation; do not replay tasks. "
            "On success delete this heartbeat before resuming the saved task/Resume under "
            "unchanged confirmed ESP/SP, then monitor director quota at meaningful checkpoints "
            "and prepare a fresh wake only if opted-in QRP reaches its threshold again. "
            "Never redeem reset credits, change accounts, probe worker quotas or send messages. "
            "Stay quiet on unchanged/non-actionable states; notify only completion, failure, "
            "meaningful change or required user action. Workspace: " + str(Path(root).resolve()))


def command(B, args):
    import runtime_relay as RL
    root = Path(args.root).resolve()
    if os.environ.get("CLI_AGENT_POOL_WORKER") and not RL.authorized(B, root):
        raise ValueError("Workers cannot change director policy or quota recovery")
    if not root.is_dir():
        raise ValueError("Project directory required")
    if args.cmd == "policy":
        if args.file or args.confirm:
            with B.checkout_lock(root):
                if args.file:
                    E.save(B, root, read_input(root, args.file), args.note)
                if args.confirm:
                    E.confirm(B, root, args.note)
        return E.load(B, root) if args.full else E.summary(B, root)
    if args.cmd == "qualify":
        import runtime_agent_pool as P
        E.require_confirmed(B, root)
        return P.qualify(B, root, args.route, args.model, args.tier, args.note)
    if args.action == "status":
        return Q.status(B, root)
    policy = E.load(B, root)
    if args.action == "cancel":
        # Revoke locally first even if the host cannot remove its timer.
        was_confirmed = E.confirmed(B, root)
        result = Q.cancel(B, root, args.note or "User cancelled quota recovery")
        if policy:
            with B.checkout_lock(root):
                policy["quota_recovery"]["enabled"] = False
                E.save(B, root, policy, args.note or "User disabled QRP")
                if was_confirmed:
                    E.confirm(B, root, args.note or "User disabled QRP; confirmed ESP/SP retained")
        return dict(result, qrp_enabled=False)
    snapshot = read_input(root, args.snapshot) if args.snapshot else None
    if args.action == "assess":
        return Q.assess(snapshot, policy)
    if args.action == "resume":
        # This guard must precede any new-session confirmation or code execution.
        result = Q.check_resume(B, root, snapshot, policy, args.nonce)
        if result["status"] == "RESUMED":
            E.confirm(B, root, "Opted-in same-account QRP wake; saved ESP/SP unchanged")
        return result
    E.require_confirmed(B, root)
    if args.action == "arm":
        return Q.arm(B, root, args.nonce, args.automation_id)
    if B.get_session_modes(root)["task_mode"] != "execute":
        raise ValueError("Automatic coding recovery requires an execute session")
    checkpoint = args.checkpoint
    if args.task:
        import runtime_protocol as R
        if not args.next_step:
            raise ValueError("Save the actual next action before quota waiting")
        task = B.find_task(root, args.task)
        if not task:
            raise ValueError("Checkpoint task not found")
        R.progress(B, root, task, args.next_step)
        task = B.find_task(root, args.task)
        R.handoff(B, root, task)
        checkpoint = R.record_path(B, root, task["id"], "handoff").relative_to(root).as_posix()
    result = Q.prepare(B, root, snapshot, policy, checkpoint, allow_rearm=args.rearm)
    if result.get("host_action") == "CREATE_AUTOMATION":
        result["prompt"] = wake_prompt(root, result["nonce"])
        result["host_instructions"] = ("Create a same-chat heartbeat through the host automation tool "
            "for wake_at; record its returned ID with quota arm. If acknowledgement is lost, "
            "read back the existing heartbeat by name/nonce, never create a duplicate.")
    return result
