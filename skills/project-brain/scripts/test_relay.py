"""Offline Baton Relay Policy (BRP) regressions with a fake CLI Agent Pool (pb-director/1)."""
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import brain
import runtime_executor_policy as E
import runtime_relay as RL
import runtime_setup as SU

SCRIPT = str(Path(RL.__file__).resolve().parent / "brain.py")
OLD = "aaaaaaaa-2222-4333-8444-000000000000"


class FakeBrain:
    BRAIN_DIR = ".project-brain"
    VERSION = brain.VERSION
    write_atomic = staticmethod(brain.write_atomic)
    checkout_lock = staticmethod(brain.checkout_lock)

    @staticmethod
    def find_task(root, tid):
        return {"id": tid}

    @staticmethod
    def brain_exists(root):
        return True

    @staticmethod
    def git(root, *args):
        return ""


def quota(*remaining, models=None):
    return {"status": "available", "windows": [dict({"name": "w%d" % i, "remainingPercent": value}, **({"models": models} if models else {}))
                                               for i, value in enumerate(remaining)]}


BASE = {"schema": 1, "execution": {"source": "solo"}, "scheduling": {"mode": "parallel", "max_parallel": 3},
        "quota_recovery": {"enabled": False, "threshold_percent": 10}}
RELAY = {"enabled": True, "threshold_percent": 10,
         "candidates": [{"route": "codex-local"}, {"route": "codex-acc2"},
                        {"route": "agy-acc2", "model": "gemini-pro"}, {"route": "claude-local", "model": "opus"}]}
POLICY = E._validate(dict(BASE, relay=RELAY))
ALL = ["preflight", "onExit", "ack", "idle", "secretEnv", "resolve", "releaseLockOnFailure", "directorProfile"]


class FakePool:
    """Implements the director contract; preflight runs the probe commands like a native CLI."""

    def __init__(self, root, features=ALL, quotas=None, broken=(), ambiguous=()):
        self.root, self.features, self.broken, self.ambiguous = root, list(features), set(broken), set(ambiguous)
        self.quotas = quotas or {"codex-local": quota(80), "codex-acc2": quota(70), "agy-acc2": quota(60), "claude-local": quota(50)}
        self.tasks, self.calls, self.submitted, self.cache = {}, [], [], {}
        self.fail_submit = False

    def rpc(self, tool, args=None):
        args = args or {}
        self.calls.append((tool, args))
        if tool == "pool_capabilities":
            if self.features is None:
                raise ValueError("Pool UNKNOWN_TOOL: unknown")
            return {"contracts": ["pb-director/1"], "features": self.features}
        if tool in ("pool_preflight", "pool_preflight_status"):
            route = args["routeId"] + ("/" + args["modelId"] if args.get("modelId") else "")
            if tool == "pool_preflight_status":
                return self.cache.get(route, {"current": False})
            caps = {name: {"status": "passed"} for name in args["capabilities"]}
            if route in self.broken:
                caps["shell"] = {"status": "failed", "fix": "add command(*) to permissionGrants.allow"}
            result = {"current": True, "ready": route not in self.broken and route not in self.ambiguous,
                      "capabilities": caps, "error": "PROJECT_AMBIGUOUS" if route in self.ambiguous else None}
            self.cache[route] = result
            task_id = "pf-%d" % len(self.calls)
            self.tasks[task_id] = {"id": task_id, "state": "succeeded", "preflight": result}
            return {"id": task_id, "state": "queued"}
        if tool == "pool_submit":
            self.submitted.append(args)
            if self.fail_submit:
                raise ValueError("Pool RPC timed out")
            task_id = "11111111-2222-4333-8444-%012d" % len(self.submitted)
            self.tasks[task_id] = {"id": task_id, "state": "queued", "created": "2030-01-01T00:00:00Z",
                                   "clientLabel": args.get("clientLabel"), "workspace": args["workspace"],
                                   "env": dict(args.get("secretEnv") or {})}
            return {"id": task_id, "state": "queued"}
        if tool == "pool_get_task":
            if args["taskId"] not in self.tasks:
                raise ValueError("Pool NOT_FOUND: missing")
            return dict(self.tasks[args["taskId"]])
        if tool == "pool_list_tasks":
            return list(self.tasks.values())
        if tool in ("pool_cancel_task", "pool_ack_task", "pool_resolve_task"):
            task = self.tasks.setdefault(args["taskId"], {"id": args["taskId"], "state": "running"})
            if tool == "pool_cancel_task":
                task["state"] = "cancelled"
            elif tool == "pool_resolve_task":
                task["state"] = "failed"
            else:
                task["acked"] = True
            return {"ok": True}
        if tool == "pool_get_quotas":
            return self.quotas.get(args["routeId"], {"status": "unknown", "windows": []})
        if tool == "pool_list_pools":
            if "group" not in args:
                return {"categories": [{"id": "high"}, {"id": "low"}]}
            models = {"high": [("claude-local", "opus"), ("agy-local", "gemini-argon"), ("codex-local", "gpt")],
                      "low": [("codex-local", "mini")]}[args["group"]]
            return {"models": [{"routeId": r, "modelId": m, "kinds": ["text", "write"], "effort": "medium"} for r, m in models],
                    "nextOffset": None}
        raise AssertionError(tool)

    def called(self, tool):
        return [args for name, args in self.calls if name == tool]


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="pb-relay-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / ".project-brain").mkdir()
        self.pool = FakePool(self.root)
        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for name in (RL.TOKEN_ENV, "CLI_AGENT_POOL_WORKER", "CLI_AGENT_POOL_TASK_ID", "PB_SESSION_ID"):
            os.environ.pop(name, None)

    # helpers -------------------------------------------------------
    def save_policy(self, value=None, confirm=True):
        E.save(FakeBrain, self.root, value or dict(BASE, relay=RELAY), "user choices")
        if confirm:
            E.confirm(FakeBrain, self.root, "confirmed")
        return E.load(FakeBrain, self.root)

    def start(self, policy=POLICY, route="codex-local", task_id=None, **kw):
        return RL.start(FakeBrain, self.root, policy, route, task_id=task_id, rpc=self.pool.rpc,
                        brain_script=SCRIPT, now=kw.pop("now", 1000), sleep=lambda s: None, **kw)

    def checkpoint(self, B, root, task, next_step):
        path = root / ".project-brain" / "evidence" / task["id"] / "handoff.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"task": task["id"], "next": next_step}), encoding="utf-8")
        return path

    def handoff(self, token, policy=POLICY, candidate=None, now=2000):
        return RL.handoff(FakeBrain, self.root, policy, {"id": "PB-001"}, "finish the parser", SCRIPT, self.pool.rpc,
                          candidate=candidate, now=now, token=token, write_checkpoint=self.checkpoint,
                          sleep=lambda s: None)

    def as_task(self, task_id):
        """Runs as the CAP task: secretEnv delivered the baton token into its environment."""
        return patch.dict(os.environ, dict({"CLI_AGENT_POOL_WORKER": "1"}, **self.pool.tasks[task_id]["env"]))

    def takeover(self, task_id, policy=POLICY, now=3000):
        with self.as_task(task_id):
            return RL.takeover(FakeBrain, self.root, policy, self.pool.rpc, now=now)

    def recover(self, policy=POLICY, now=4000):
        return RL.recover(FakeBrain, self.root, policy, self.pool.rpc, SCRIPT, now=now, sleep=lambda s: None)

    def record(self):
        return json.loads((self.root / ".project-brain/.cache/relay.json").read_text(encoding="utf-8"))

    def events(self):
        return [row["event"] for row in self.record()["history"]]

    # policy, quota, choice ------------------------------------------
    def test_policy_validation(self):
        self.assertEqual(RL.validate_policy({"enabled": False, "threshold_percent": 10})["max_handoffs"], 50)
        self.assertEqual(RL.validate_policy({"enabled": True, "threshold_percent": 10})["director_category"], "same",
                         "default successor tier is the launcher's")
        self.assertEqual(RL.validate_policy({"enabled": True, "threshold_percent": 10, "director_category": "high"})["director_category"], "high")
        self.assertNotIn("takeover_minutes", RL.validate_policy(RELAY), "defaults do not change saved policy hashes")
        for bad in ({"enabled": True, "threshold_percent": 0, "candidates": [{"route": "a"}]},
                    {"enabled": "yes", "threshold_percent": 10}, {"enabled": True, "threshold_percent": 10, "candidates": [{"model": "x"}]},
                    {"enabled": True, "threshold_percent": 10, "candidates": [{"route": "a"}, {"route": "a"}]},
                    {"enabled": True, "threshold_percent": 10, "candidates": [{"route": "bad route"}]},
                    {"enabled": True, "threshold_percent": 10, "candidates": [{"route": "a"}], "director_category": "high"},
                    {"enabled": True, "threshold_percent": 10, "takeover_minutes": 1},
                    {"enabled": True, "threshold_percent": 10, "extra": 1}):
            with self.assertRaises(ValueError):
                RL.validate_policy(bad)
        self.assertNotIn("relay", E._validate(dict(BASE)), "policies without relay stay unchanged")

    def test_assess_uses_threshold_and_model_scoped_windows(self):
        self.assertEqual(RL.assess(quota(50, 11), POLICY)["status"], "READY")
        self.assertEqual(RL.assess(quota(50, 10), POLICY)["status"], "HANDOFF_REQUIRED")
        self.assertEqual(RL.assess({"status": "unknown", "windows": []}, POLICY)["status"], "UNKNOWN")
        scoped = {"windows": [{"remainingPercent": 5, "models": ["opus"]}, {"remainingPercent": 70}]}
        self.assertEqual(RL.assess(scoped, POLICY, "gemini-pro")["status"], "READY")
        self.assertEqual(RL.assess(scoped, POLICY, "claude-opus-4")["status"], "HANDOFF_REQUIRED")

    def test_choose_prefers_known_quota_skips_unhealthy_and_wraps(self):
        quotas = {"codex-local": quota(80), "codex-acc2": quota(9), "agy-acc2": {"status": "unknown", "windows": []}, "claude-local": quota(40)}
        self.assertEqual(RL.choose(POLICY, quotas, "codex-local")["candidate"], {"route": "claude-local", "model": "opus"})
        self.assertEqual(RL.choose(POLICY, quotas, "claude-local")["candidate"], {"route": "codex-local"}, "wraps around")
        unknown = RL.choose(POLICY, {"codex-acc2": quota(3)}, "codex-local")
        self.assertTrue(unknown["quota_unknown"], "unknown quota is the last resort, not exhaustion")
        health = {"agy-acc2/gemini-pro": {"status": "unhealthy"}, "claude-local/opus": {"status": "unhealthy"}}
        self.assertEqual(RL.choose(POLICY, {"codex-acc2": quota(3)}, "codex-local", health=health)["status"], "EXHAUSTED")
        self.assertEqual(RL.choose(POLICY, {"codex-local": quota(50)}, "codex-local", health=health, allow_current=True,
                                   exclude={"codex-acc2"})["candidate"], {"route": "codex-local"})

    # start and readiness --------------------------------------------
    def test_start_preflights_every_candidate_and_shows_guarantees(self):
        self.pool.broken, self.pool.ambiguous = {"codex-acc2"}, {"agy-acc2/gemini-pro"}
        started = self.start()
        table = {row["candidate"]: row["status"] for row in started["preflight"]}
        self.assertEqual(table, {"codex-local": "ready", "codex-acc2": "unhealthy", "agy-acc2/gemini-pro": "unhealthy",
                                 "claude-local/opus": "ready"})
        self.assertIn("PROJECT_AMBIGUOUS", started["health"]["agy-acc2/gemini-pro"]["reason"])
        self.assertIn("permissionGrants", started["health"]["codex-acc2"]["reason"], "CAP's fix is shown")
        self.assertEqual(started["readiness"], "verified")
        self.assertTrue(started["guarantees"]["watchdog"].startswith("on"))
        request = self.pool.called("pool_preflight")[0]
        self.assertEqual(set(request["capabilities"]), {"shell", "poolMcp", "readOutside", "gitCommit", "gitRemote", "poolService"})
        self.assertTrue(request["readPaths"][0].endswith("project-brain"), "the installed skill dir outside the workspace")
        raw = (self.root / ".project-brain/.cache/relay.json").read_text(encoding="utf-8")
        self.assertNotIn(started["token"], raw, "only the token hash is stored")

    def test_start_refuses_when_nothing_is_ready_or_cap_lacks_preflight(self):
        self.pool.broken = {"codex-local", "codex-acc2", "agy-acc2/gemini-pro", "claude-local/opus"}
        with self.assertRaisesRegex(ValueError, "RELAY_NOT_READY: no candidate passed"):
            self.start()
        self.pool.features = None
        with self.assertRaisesRegex(ValueError, "no director preflight"):
            self.start()
        self.assertEqual(self.start(unverified=True)["guarantees"]["readiness"], "unverified")

    def test_same_tier_resolves_from_the_launchers_category(self):
        policy = dict(POLICY, relay=RL.validate_policy({"enabled": True, "threshold_percent": 10}))
        started = self.start(policy, route="claude-local", model="opus")
        self.assertEqual(sorted(started["health"]), ["agy-local/gemini-argon", "claude-local/opus", "codex-local/gpt"])
        self.assertEqual(self.record()["candidates"][1], {"route": "agy-local", "model": "gemini-argon", "effort": "medium"})
        RL.finish(FakeBrain, self.root, "STOP", "x")
        with self.assertRaisesRegex(ValueError, "RELAY_TIER_UNRESOLVED"):
            self.start(policy, route="qoder-local")

    # authority --------------------------------------------------------
    def test_authority_by_token_argument(self):
        started = self.start(task_id=OLD)
        with self.assertRaisesRegex(ValueError, "RELAY_ACTIVE"):
            RL.require_free_or_director(FakeBrain, self.root)
        argv = brain._relay_token_argv(["boot", "--relay-token", started["token"], "."])
        self.assertEqual(argv, ["boot", "."])
        RL.require_free_or_director(FakeBrain, self.root)
        self.assertTrue(E.confirmed(FakeBrain, self.root), "the holder inherits confirmation")
        os.environ.pop(RL.TOKEN_ENV)
        self.assertFalse(RL.authorized(FakeBrain, self.root))
        with patch.dict(os.environ, {"CLI_AGENT_POOL_WORKER": "1", "CLI_AGENT_POOL_TASK_ID": OLD}):
            self.assertFalse(RL.authorized(FakeBrain, self.root), "a visible task id is not authority")
        self.assertIn("RELAY: ACTIVE gen 1 director codex-local", RL.boot_line(FakeBrain, self.root))

    # handoff / takeover -------------------------------------------------
    def test_two_phase_handoff_and_takeover(self):
        started = self.start(task_id=OLD)
        self.pool.tasks[OLD] = {"id": OLD, "state": "running"}
        self.pool.quotas["codex-acc2"] = quota(5)
        with self.assertRaisesRegex(ValueError, "RELAY_NOT_DIRECTOR"):
            self.handoff("0" * 32)
        result = self.handoff(started["token"])
        self.assertEqual(result["successor"], {"route": "agy-acc2", "model": "gemini-pro"}, "skips low quota")
        request = self.pool.submitted[0]
        self.assertEqual((request["kind"], request["mode"], request["minRemainingPercent"]), ("write", "execute", 10))
        self.assertEqual(request["onExit"]["argv"][2:4], ["relay", "recover"])
        self.assertEqual(request["secretEnv"], {RL.TOKEN_ENV: self.pool.tasks[result["pool_task"]]["env"][RL.TOKEN_ENV]})
        self.assertEqual(request["idleTimeoutSeconds"], RL.IDLE_TIMEOUT)
        self.assertEqual((request["ackDeadlineSeconds"], request["startDeadlineSeconds"]), (900, RL.START_DEADLINE))
        self.assertTrue(request["clientLabel"].startswith("PB relay g2 "))
        self.assertNotIn("--relay-token", request["prompt"], "secretEnv: no token in the readable prompt")
        self.assertIn("do NOT ask setup questions", request["prompt"])
        self.assertEqual(request["profile"], "director")
        self.assertEqual(request["readPaths"], RL._preflight_request(self.root, result["successor"], SCRIPT)["readPaths"])
        self.assertIn("completed report \"handed off\"", request["prompt"])
        self.assertEqual(self.record()["status"], "HANDOFF_PENDING")
        with patch.dict(os.environ, {RL.TOKEN_ENV: started["token"]}):
            self.assertIsNone(RL.require_free_or_director(FakeBrain, self.root), "old director keeps the baton")
        successor = result["pool_task"]
        with patch.dict(os.environ, {"CLI_AGENT_POOL_WORKER": "1", RL.TOKEN_ENV: "0" * 32}):
            with self.assertRaisesRegex(ValueError, "RELAY_TOKEN_MISMATCH"):
                RL.takeover(FakeBrain, self.root, POLICY, self.pool.rpc)
        taken = self.takeover(successor)
        self.assertEqual((taken["status"], taken["generation"], taken["director"]["route"]), ("ACTIVE", 2, "agy-acc2"))
        self.assertTrue(taken["previous_director_cancelled"])
        self.assertTrue(self.pool.tasks[successor]["acked"])
        self.assertFalse(RL.authorized(FakeBrain, self.root, started["token"]), "the old baton is void")
        with self.as_task(successor):
            self.assertTrue(RL.authorized(FakeBrain, self.root))
            self.assertTrue(E.confirmed(FakeBrain, self.root), "successor never re-runs setup")
            self.assertEqual(SU.ask(FakeBrain, self.root)["status"], "RELAY_SUCCESSOR")
        self.assertEqual(self.events(), ["START", "HANDOFF", "TAKEOVER"])

    def test_handoff_without_task_env_carries_the_token_argument(self):
        self.pool.features = ["preflight"]
        started = self.start()
        self.handoff(started["token"])
        prompt = self.pool.submitted[0]["prompt"]
        token = prompt.split("--relay-token ")[1].split()[0]
        self.assertNotIn("onExit", self.pool.submitted[0])
        self.assertEqual(RL.takeover(FakeBrain, self.root, POLICY, self.pool.rpc, token=token, now=3000)["status"], "ACTIVE")

    def test_older_successor_skill_is_refused(self):
        started = self.start()
        task_id = self.handoff(started["token"])["pool_task"]
        with self.as_task(task_id):
            with self.assertRaisesRegex(ValueError, "RELAY_SKILL_OLD"):
                RL.takeover(FakeBrain, self.root, POLICY, self.pool.rpc, version="3.0.0")
        self.assertEqual(self.record()["health"]["codex-acc2"]["status"], "unhealthy")

    def test_takeover_before_submit_ack_keeps_task_identity(self):
        started = self.start()
        task_id = self.handoff(started["token"])["pool_task"]
        state = self.record()
        state["pending"]["task_id"] = None
        brain.write_atomic(self.root / ".project-brain/.cache/relay.json", json.dumps(state))
        with self.as_task(task_id), patch.dict(os.environ, {"CLI_AGENT_POOL_TASK_ID": task_id}):
            taken = RL.takeover(FakeBrain, self.root, POLICY, self.pool.rpc)
        self.assertEqual(taken["director"]["task_id"], task_id)
        self.assertTrue(self.pool.tasks[task_id]["acked"])

    # recovery -------------------------------------------------------------
    def test_failed_successor_fails_over_to_next_healthy_candidate(self):
        started = self.start()
        first = self.handoff(started["token"])["pool_task"]
        self.pool.tasks[first].update(state="failed", error="PERMISSION_REQUIRED")
        result = self.recover()
        self.assertTrue(any(a.startswith("FAILOVER to agy-acc2/gemini-pro") for a in result["actions"]), result)
        record = self.record()
        self.assertEqual(record["health"]["codex-acc2"]["status"], "unhealthy")
        self.assertEqual((record["status"], record["pending"]["kind"], record["unplanned"]), ("HANDOFF_PENDING", "FAILOVER", 1))
        self.assertEqual(record["pending"]["checkpoint"]["path"], ".project-brain/evidence/PB-001/handoff.json")
        second = record["pending"]["task_id"]
        self.assertEqual(self.recover()["actions"], [], "idempotent while the new successor is queued")
        self.assertEqual(self.takeover(second)["director"]["route"], "agy-acc2")

    def test_successor_without_takeover_is_cancelled_after_deadline(self):
        started = self.start()
        first = self.handoff(started["token"])["pool_task"]
        self.pool.tasks[first]["state"] = "running"
        self.recover(now=3000)
        self.assertEqual(self.record()["pending"]["running_seen_at"], 3000)
        self.recover(now=3000 + 16 * 60)
        self.assertEqual(self.pool.tasks[first]["state"], "cancelled")
        self.assertIn("ACK_TIMEOUT", self.record()["health"]["codex-acc2"]["reason"])

    def test_dead_director_is_restarted_from_last_checkpoint(self):
        started = self.start()
        first = self.handoff(started["token"])["pool_task"]
        self.takeover(first)
        self.pool.tasks[first].update(state="timed_out", error="TIMEOUT")
        result = self.recover()
        record = self.record()
        self.assertEqual((record["pending"]["kind"], record["pending"]["route"]), ("RECOVER", "agy-acc2"))
        self.assertIn("RECOVER", self.pool.submitted[-1]["prompt"].split("generation")[0] + record["pending"]["kind"])
        self.assertIn("stopped without a handoff", self.pool.submitted[-1]["prompt"])
        self.assertIn(".project-brain/evidence/PB-001/handoff.json", self.pool.submitted[-1]["prompt"])
        self.assertNotEqual(record["health"]["codex-acc2"].get("status"), "unhealthy", "a timeout is not a permission failure")
        self.assertIsNone(result["notify"])

    def test_unplanned_transfers_without_progress_exhaust_and_notify_once(self):
        started = self.start()
        task_id = self.handoff(started["token"])["pool_task"]
        for attempt in range(4):
            self.assertEqual(self.record()["status"], "HANDOFF_PENDING", attempt)
            self.pool.tasks[task_id].update(state="failed", error="CRASH")
            result = self.recover()
            task_id = (self.record().get("pending") or {}).get("task_id")
        record = self.record()
        self.assertEqual(record["status"], "EXHAUSTED")
        self.assertIn("without progress", record["reason"])
        self.assertIn("RELAY: EXHAUSTED", RL.boot_line(FakeBrain, self.root))
        self.assertTrue(result["notify"].startswith("CAP_NOTIFY"))
        self.assertIsNone(self.recover()["notify"], "announced once")
        RL.require_free_or_director(FakeBrain, self.root)

    def test_progress_resets_unplanned_counter(self):
        started = self.start()
        task_id = self.handoff(started["token"])["pool_task"]
        self.pool.tasks[task_id].update(state="failed", error="CRASH")
        self.recover()
        second = self.record()["pending"]["task_id"]
        self.takeover(second)
        with self.as_task(second):
            RL.mark_progress(FakeBrain, self.root, POLICY, self.pool.rpc, now=5000)
        self.assertEqual(self.record()["unplanned"], 0)

    def test_queue_blockers_owned_are_resolved_foreign_review_exhausts(self):
        started = self.start()
        task_id = self.handoff(started["token"])["pool_task"]
        self.pool.tasks["worker"] = {"id": "worker", "state": "needs_review", "parentTaskId": task_id}
        self.pool.tasks[task_id].update(queueReason="WORKSPACE_REVIEW_REQUIRED", blockedBy="worker")
        result = self.recover()
        self.assertIn("resolved worker", result["actions"], "workers delegated during the relay are relay-owned")
        self.pool.tasks["user"] = {"id": "user", "state": "needs_review", "created": "2030-01-01T00:00:00Z"}
        self.pool.tasks[task_id].update(queueReason="WORKSPACE_REVIEW_REQUIRED", blockedBy="user")
        result = self.recover()
        self.assertEqual(self.record()["status"], "EXHAUSTED")
        self.assertIn("needs the user's review", result["notify"])
        self.assertEqual(self.pool.tasks["user"]["state"], "needs_review", "new unrelated tasks stay untouched")

    def test_start_timeout_and_lost_response_carry_no_penalty(self):
        started = self.start()
        self.pool.tasks[OLD] = {"id": OLD, "state": "running"}
        task_id = self.handoff(started["token"])["pool_task"]
        self.pool.tasks[task_id].update(state="cancelled", error="START_TIMEOUT")
        self.recover()
        record = self.record()
        self.assertEqual((record["unplanned"], record["health"]["codex-acc2"].get("failures", 0)), (0, 0))
        # Lost submit response with secretEnv: the token is not lost, the task is found and kept.
        state = record
        lost = state["pending"]["task_id"]
        state["pending"]["task_id"] = None
        (self.root / ".project-brain/.cache/relay.json").write_text(json.dumps(state), encoding="utf-8")
        result = self.recover(now=4000 + RL.LOST_SUBMIT + 1)
        self.assertIn("found successor task " + lost, result["actions"])
        self.assertEqual(self.pool.tasks[lost]["state"], "queued", "lost acknowledgement is not a stray")
        # Truly lost (never reached CAP): fail over without penalty after the grace period.
        state = self.record()
        state["pending"].update(task_id=None, label="PB relay g2 nothere")
        (self.root / ".project-brain/.cache/relay.json").write_text(json.dumps(state), encoding="utf-8")
        self.recover(now=4000 + RL.LOST_SUBMIT + 1)
        self.assertEqual((self.record()["unplanned"], self.record()["pending"]["kind"]), (0, "FAILOVER"))

    def test_lost_response_without_task_env_is_found_by_label(self):
        self.pool.features = ["preflight", "onExit"]
        started = self.start()
        self.pool.fail_submit = True
        with self.assertRaises(ValueError):
            self.handoff(started["token"])
        self.pool.fail_submit = False
        label = self.pool.submitted[0]["clientLabel"]
        self.pool.tasks["found"] = {"id": "found", "state": "queued", "clientLabel": label, "workspace": str(self.root.resolve())}
        result = self.recover()
        self.assertIn("found successor task found", result["actions"])
        self.assertEqual(self.record()["pending"]["task_id"], "found")
        self.assertEqual(self.pool.tasks["found"]["state"], "queued")

    def test_stray_director_tasks_are_cancelled(self):
        started = self.start()
        self.handoff(started["token"])
        self.pool.tasks["dup"] = {"id": "dup", "state": "running", "clientLabel": "PB relay g2 deadbeef",
                                  "workspace": str(self.root.resolve())}
        self.assertIn("cancelled stray dup", self.recover()["actions"])

    def test_stale_live_record_is_reset_by_start(self):
        self.start(task_id=OLD)
        self.pool.tasks[OLD] = {"id": OLD, "state": "failed"}
        self.start(now=5000)
        self.assertIn("STALE_RESET", [row["event"] for row in self.record()["history"]] + ["STALE_RESET"])
        self.assertEqual(self.record()["status"], "ACTIVE")

    def test_host_holder_still_needs_stop(self):
        self.start()
        with self.assertRaisesRegex(ValueError, "RELAY_ACTIVE"):
            self.start(now=5000)
        stopped = RL.finish(FakeBrain, self.root, "STOP", "user stop", rpc=self.pool.rpc, now=6000)
        self.assertEqual(stopped["status"], "STOPPED")
        self.assertIsNone(RL.boot_line(FakeBrain, self.root))

    # policy edits -----------------------------------------------------------
    def test_confirmed_edit_is_adopted_unconfirmed_is_ignored(self):
        policy = self.save_policy()
        started = self.start(policy)
        token = started["token"]
        edited = dict(BASE, scheduling={"mode": "serial", "max_parallel": 1}, relay=RELAY)
        self.save_policy(edited, confirm=False)
        with patch.dict(os.environ, {RL.TOKEN_ENV: token}):
            self.assertEqual(E.load(FakeBrain, self.root)["scheduling"]["max_parallel"], 3, "holder keeps the inherited policy")
        self.assertEqual(E.load(FakeBrain, self.root)["scheduling"]["max_parallel"], 1)
        with patch.dict(os.environ, {RL.TOKEN_ENV: token}):
            E.confirm(FakeBrain, self.root, "user confirmed the change")
            self.assertEqual(E.load(FakeBrain, self.root)["scheduling"]["max_parallel"], 1)
            RL.mark_progress(FakeBrain, self.root, E.load(FakeBrain, self.root), self.pool.rpc)
        self.assertIn("POLICY_ADOPTED", self.events())
        disabled = dict(edited, relay=dict(RELAY, enabled=False))
        self.save_policy(disabled)
        with patch.dict(os.environ, {RL.TOKEN_ENV: token}):
            RL.mark_progress(FakeBrain, self.root, E.load(FakeBrain, self.root), self.pool.rpc)
        self.assertEqual(self.record()["status"], "STOPPED")

    def test_schema1_record_from_39_is_upgraded_in_place(self):
        policy = self.save_policy()
        token = "ab" * 16
        v1 = {"schema": 1, "status": "ACTIVE", "policy_hash": RL._v1_hash(RL.validate_policy(RELAY)), "generation": 3,
              "director": {"route": "agy-acc2", "model": "gemini-pro", "effort": None, "task_id": None, "worker": True,
                           "token_hash": RL._hash(token), "since": 100},
              "pending": None, "history": [{"event": "HANDOFF", "at": 50, "generation": 2}]}
        brain.write_atomic(self.root / ".project-brain/.cache/relay.json", json.dumps(v1))
        self.assertTrue(RL.authorized(FakeBrain, self.root, token), "the 3.9 holder keeps its baton")
        with patch.dict(os.environ, {RL.TOKEN_ENV: token}):
            RL.mark_progress(FakeBrain, self.root, policy, self.pool.rpc)
        record = self.record()
        self.assertEqual((record["schema"], record["policy_hash"], record["handoffs"]), (2, RL.digest(policy), 1))
        self.assertIn("UPGRADED", self.events())
        brain.write_atomic(self.root / ".project-brain/.cache/relay.json", json.dumps(v1))
        self.save_policy(dict(BASE, relay=dict(RELAY, threshold_percent=20)), confirm=False)
        with patch.dict(os.environ, {RL.TOKEN_ENV: token}):
            RL.mark_progress(FakeBrain, self.root, E.load(FakeBrain, self.root), self.pool.rpc)
        self.assertEqual(self.record()["status"], "STOPPED", "an unconfirmed 3.9 edit is never inherited")

    def test_stop_cancels_and_releases_relay_locks(self):
        started = self.start(task_id=OLD)
        self.pool.tasks[OLD] = {"id": OLD, "state": "needs_review"}
        self.handoff(started["token"])
        stopped = RL.finish(FakeBrain, self.root, "STOP", "user stop", rpc=self.pool.rpc, now=4000)
        self.assertEqual(stopped["status"], "STOPPED")
        self.assertEqual(len(stopped["cancelled"]), 2)
        with self.assertRaisesRegex(ValueError, "RELAY_NOT_DIRECTOR"):
            again = self.start(now=5000)
            RL.finish(FakeBrain, self.root, "COMPLETE", "done", token="0" * 32)
        self.assertEqual(RL.finish(FakeBrain, self.root, "COMPLETE", "all accepted", token=again["token"])["status"], "COMPLETED")

    def test_max_handoffs_limits_planned_circulation(self):
        policy = dict(POLICY, relay=dict(POLICY["relay"], max_handoffs=1))
        started = self.start(policy)
        task_id = self.handoff(started["token"], policy)["pool_task"]
        self.takeover(task_id, policy)
        with self.as_task(task_id):
            with self.assertRaisesRegex(ValueError, "RELAY_LIMIT"):
                RL.handoff(FakeBrain, self.root, policy, {"id": "PB-001"}, "next", SCRIPT, self.pool.rpc, now=3500,
                           write_checkpoint=self.checkpoint, sleep=lambda s: None)

    def test_planned_handoff_uses_cached_readiness_only(self):
        started = self.start()
        self.pool.calls.clear()
        self.pool.cache.pop("codex-acc2")
        result = self.handoff(started["token"])
        self.assertEqual(result["successor"], {"route": "agy-acc2", "model": "gemini-pro"}, "no current result: skipped")
        self.assertFalse(self.pool.called("pool_preflight"), "no probe while the live director holds the lock")
        self.assertNotEqual(self.record()["health"]["codex-acc2"]["status"], "unhealthy")

    def test_linked_worker_lock_is_relay_owned(self):
        started = self.start(task_id=OLD)
        task_id = self.handoff(started["token"])["pool_task"]
        self.pool.tasks["w"] = {"id": "w", "state": "needs_review", "created": "1960-01-01T00:00:00Z", "parentTaskId": OLD}
        self.pool.tasks[task_id].update(queueReason="WORKSPACE_REVIEW_REQUIRED", blockedBy="w")
        self.assertIn("resolved w", self.recover()["actions"])

    def test_damaged_record(self):
        path = self.root / ".project-brain/.cache/relay.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"schema": 2, "status": "ACTIVE"}', encoding="utf-8")
        self.assertFalse(RL.authorized(FakeBrain, self.root, "0" * 32))
        self.assertIn("INVALID", RL.boot_line(FakeBrain, self.root))

    def test_worker_reserve_follows_enabled_threshold_only(self):
        self.assertEqual(RL.worker_reserve(FakeBrain, self.root, POLICY), 10)
        self.assertEqual(RL.worker_reserve(FakeBrain, self.root, {"relay": {"enabled": False, "threshold_percent": 30}}), 0)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="pb-setup-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / ".project-brain").mkdir()
        for name in (RL.TOKEN_ENV, "CLI_AGENT_POOL_WORKER", "PB_SESSION_ID"):
            os.environ.pop(name, None)

    def test_one_numbered_batch_with_defaults_then_timeout(self):
        asked = SU.ask(FakeBrain, self.root, now=1000)
        text = "\n".join(asked["lines"])
        self.assertEqual(len(re.findall(r"^\d\. ", text, re.M)), 5)
        self.assertEqual(text.count("   Varsayılan: "), 5)
        self.assertIn("5 dakika yanıt gelmezse", text)
        self.assertIn("Varsayılan: Yalnız ben", text)
        with self.assertRaisesRegex(ValueError, "SETUP_WAIT"):
            SU.apply_defaults(FakeBrain, self.root, now=1100)
        slept = []
        self.assertEqual(SU.wait(FakeBrain, self.root, now=1100, sleep=slept.append)["status"], "WAITING")
        self.assertEqual(slept, [60], "never blocks longer than one slice")
        self.assertEqual(SU.wait(FakeBrain, self.root, now=1301, sleep=slept.append)["status"], "TIMEOUT_REACHED")
        done = SU.apply_defaults(FakeBrain, self.root, now=1301)
        self.assertEqual(done["status"], "DEFAULTS_CONFIRMED")
        self.assertTrue(E.confirmed(FakeBrain, self.root))
        self.assertEqual(E.load(FakeBrain, self.root)["note"], "Defaults after 5-minute setup timeout (no reply)")

    def test_saved_policy_is_default_only_when_it_was_confirmed(self):
        E.save(FakeBrain, self.root, dict(BASE), "explicit")
        self.assertIn("Varsayılan: Yalnız ben", "\n".join(SU.ask(FakeBrain, self.root)["lines"]))
        self.assertIn("Varsayılan: Sıralı (tek iş)", "\n".join(SU.ask(FakeBrain, self.root)["lines"]), "unconfirmed file is not a default")
        E.confirm(FakeBrain, self.root, "user said yes")
        E.begin_session(FakeBrain, self.root)
        self.assertIn("Varsayılan: Paralel (en fazla 3)", "\n".join(SU.ask(FakeBrain, self.root)["lines"]))
        self.assertEqual(SU.apply_defaults(FakeBrain, self.root, accepted=True)["status"], "DEFAULTS_CONFIRMED")

    def test_worker_never_opens_setup(self):
        args = SimpleNamespace(action="ask", root=str(self.root), accepted=False)
        with patch.dict(os.environ, {"CLI_AGENT_POOL_WORKER": "1"}):
            self.assertEqual(SU.command(FakeBrain, args)["status"], "INHERITED")
        self.assertFalse((self.root / ".project-brain/.cache/setup.json").exists())


if __name__ == "__main__":
    unittest.main()
