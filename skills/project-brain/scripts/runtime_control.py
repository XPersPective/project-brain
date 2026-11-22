"""Policy, advisory model qualification, and director quota recovery CLI."""
from pathlib import Path

import runtime_agent_pool as P
import runtime_core as Core
import runtime_executor_policy as E
import runtime_protocol as R
import runtime_quota_recovery as Q
import runtime_relay as RL


def add_parser(sub):
    p = sub.add_parser("policy", help="View, set, save, and confirm ESP, SP, QRP, and BRP")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--file", default="")
    p.add_argument("--source", choices=E.SOURCES, default="", help="Quick-set execution source without writing JSON")
    p.add_argument("--review-source", choices=E.SOURCES, default="", help="Optional separate review source")
    p.add_argument("--categories", default="", help="Comma-separated CAP categories for cap-category/mixed")
    p.add_argument("--schedule", choices=("serial", "parallel"), default="")
    p.add_argument("--max-parallel", type=int, default=None)
    p.add_argument("--qrp", choices=("on", "off"), default="")
    p.add_argument("--qrp-threshold", type=int, default=None)
    p.add_argument("--relay", choices=("on", "off"), default="")
    p.add_argument("--relay-threshold", type=int, default=None)
    p.add_argument("--relay-category", default=None)
    p.add_argument("--cap-fallback", choices=("native", "wait"), default="")
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--note", default="")
    p.add_argument("--full", action="store_true")

    p = sub.add_parser("qualify", help="Record optional advisory model fit override (not acceptance evidence)")
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
    path = Core.public_path(root, name)
    if not path.is_file():
        raise ValueError("A bounded project-local JSON input is required")
    return Core.read_json(path, max_bytes=65536, strict_constants=True, unique_keys=True)


def wake_prompt(root, nonce):
    return (
        "Project Brain quota recovery for the same chat and workspace. Before any coding, "
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
        "meaningful change or required user action. Workspace: " + str(Path(root).resolve())
    )


def _handle_policy(B, root, args):
    quick = any([
        getattr(args, "source", ""),
        getattr(args, "review_source", ""),
        getattr(args, "categories", ""),
        getattr(args, "schedule", ""),
        getattr(args, "max_parallel", None) is not None,
        getattr(args, "qrp", ""),
        getattr(args, "qrp_threshold", None) is not None,
        getattr(args, "relay", ""),
        getattr(args, "relay_threshold", None) is not None,
        getattr(args, "relay_category", None) is not None,
        getattr(args, "cap_fallback", ""),
    ])
    if args.file and quick:
        raise ValueError("Use either --file or inline policy flags, not both")
    if args.file or quick or args.confirm:
        if Core.worker_env_active():
            raise ValueError("CAP workers and relay directors cannot modify or confirm executor policy")
        with B.checkout_lock(root):
            if args.file:
                E.save(B, root, read_input(root, args.file), args.note)
            elif quick:
                existing = E.load_raw(B, root)
                cats = [c.strip() for c in args.categories.split(",") if c.strip()] if args.categories else None
                built = E.build_policy(
                    source=args.source or None,
                    review_source=args.review_source or None,
                    categories=cats,
                    schedule=args.schedule or None,
                    max_parallel=args.max_parallel,
                    qrp_enabled=(args.qrp == "on") if args.qrp else None,
                    qrp_threshold=args.qrp_threshold,
                    relay_enabled=(args.relay == "on") if args.relay else None,
                    relay_threshold=args.relay_threshold,
                    relay_category=args.relay_category,
                    cap_fallback=args.cap_fallback or None,
                    base=existing,
                )
                built["origin"] = "user"
                E.save(B, root, built, args.note or "Updated session policy via CLI flags")
            if args.confirm:
                E.confirm(B, root, args.note or "Confirmed session policy")
    return E.load(B, root) if args.full else E.summary(B, root)


def _handle_quota(B, root, args):
    if args.action == "status":
        return Q.status(B, root)
    if args.action == "cancel":
        if Core.worker_env_active():
            raise ValueError("CAP workers and relay directors cannot cancel director quota recovery")
        RL.require_free_or_director(B, root)
        result = Q.cancel(B, root, args.note or "User cancelled quota recovery")
        with B.checkout_lock(root):
            raw_policy = E.load_raw(B, root)
            host_confirmed = (
                raw_policy is not None
                and not E.relay_authorized(B, root)
                and not E.relay_stopping_holder(B, root)
                and E.confirmed(B, root)
            )
            if raw_policy and (host_confirmed or raw_policy.get("quota_recovery", {}).get("enabled")):
                raw_policy["quota_recovery"]["enabled"] = False
                E.save(B, root, raw_policy, args.note or "User disabled QRP")
                if host_confirmed:
                    E.confirm(B, root, args.note or "User disabled QRP; confirmed ESP/SP retained")
        return dict(result, qrp_enabled=False)
    policy = E.load(B, root)
    snapshot = read_input(root, args.snapshot) if args.snapshot else None
    if args.action == "assess":
        return Q.assess(snapshot, policy)
    RL.require_free_or_director(B, root)
    if args.action == "resume":
        with B.checkout_lock(root):
            policy = E.load(B, root)
            result = Q.check_resume(
                B,
                root,
                snapshot,
                policy,
                args.nonce,
                on_resumed=lambda: E.confirm(B, root, "Opted-in same-account QRP wake; saved ESP/SP unchanged"),
            )
        return result
    E.require_confirmed(B, root)
    if args.action == "arm":
        return Q.arm(B, root, args.nonce, args.automation_id)
    if B.get_session_modes(root)["task_mode"] != "execute":
        raise ValueError("Automatic coding recovery requires an execute session")
    # Validate low-quota state BEFORE mutating task progress/handoff.
    assessment = Q.assess(snapshot, policy)
    if assessment["status"] != "CHECKPOINT_REQUIRED":
        raise ValueError("Enabled recovery and an actual low-quota observation are required")
    checkpoint = args.checkpoint
    if args.task:
        if not args.next_step:
            raise ValueError("Save the actual next action before quota waiting")
        with B.checkout_lock(root):
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
        result["host_instructions"] = (
            "Create a same-chat heartbeat through the host automation tool "
            "for wake_at; record its returned ID with quota arm. If acknowledgement is lost, "
            "read back the existing heartbeat by name/nonce, never create a duplicate."
        )
    return result


def command(B, args):
    root = Path(args.root).resolve()
    if Core.worker_env_active() and not RL.authorized(B, root):
        raise ValueError("Workers cannot change director policy or quota recovery")
    if not root.is_dir():
        raise ValueError("Project directory required")
    if args.cmd == "policy":
        return _handle_policy(B, root, args)
    if args.cmd == "qualify":
        RL.require_free_or_director(B, root)
        E.require_confirmed(B, root)
        return P.qualify(B, root, args.route, args.model, args.tier, args.note)
    return _handle_quota(B, root, args)
