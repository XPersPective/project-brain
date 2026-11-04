"""Offline Baton Relay Policy (BRP) regressions: no Pool, provider or account access."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import brain
import runtime_executor_policy as E
import runtime_relay as RL


class FakeBrain:
    BRAIN_DIR = ".project-brain"
    write_atomic = staticmethod(brain.write_atomic)
    checkout_lock = staticmethod(brain.checkout_lock)

    @staticmethod
    def find_task(root, tid):
        return {"id": tid}


def quota(*remaining, models=None):
    return {"status": "available", "windows": [dict({"name": "w%d" % i, "remainingPercent": value}, **({"models": models} if models else {}))
                                               for i, value in enumerate(remaining)]}


POLICY = {"relay": {"enabled": True, "threshold_percent": 10,
                    "candidates": [{"route": "codex-local"}, {"route": "codex-acc2"},
                                   {"route": "agy-acc2", "model": "gemini-pro"}, {"route": "claude-local", "model": "opus"}]}}


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="pb-relay-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.submitted, self.cancelled, self.states = [], [], {}

    def checkpoint(self, B, root, task, next_step):
        path = root / ".project-brain" / "evidence" / task["id"] / "handoff.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"task": task["id"], "next": next_step}), encoding="utf-8")
        return path

    def submit(self, request):
        self.submitted.append(request)
        return {"id": "11111111-2222-4333-8444-%012d" % len(self.submitted)}

    def handoff(self, token, candidate, now=2000, submit=None):
        return RL.handoff(FakeBrain, self.root, POLICY, {"id": "PB-001"}, "finish the parser", candidate,
                          "/pb/brain.py", submit or self.submit, now=now, token=token, write_checkpoint=self.checkpoint)

    def takeover(self, token, policy=POLICY):
        return RL.takeover(FakeBrain, self.root, policy, cancel=self.cancelled.append,
                           task_state=lambda task_id: self.states.get(task_id, "succeeded"), token=token, now=3000)

    def test_policy_validation_is_strict_and_optional_in_executor_policy(self):
        self.assertEqual(RL.validate_policy({"enabled": False, "threshold_percent": 10})["max_handoffs"], 50)
        for bad in ({"enabled": True, "threshold_percent": 10}, {"enabled": True, "threshold_percent": 0, "candidates": [{"route": "a"}]},
                    {"enabled": "yes", "threshold_percent": 10}, {"enabled": True, "threshold_percent": 10, "candidates": [{"model": "x"}]},
                    {"enabled": True, "threshold_percent": 10, "candidates": [{"route": "a"}, {"route": "a"}]},
                    {"enabled": True, "threshold_percent": 10, "candidates": [{"route": "bad route"}]},
                    {"enabled": True, "threshold_percent": 10, "extra": 1, "candidates": [{"route": "a"}]}):
            with self.assertRaises(ValueError):
                RL.validate_policy(bad)
        base = {"schema": 1, "execution": {"source": "solo"}, "scheduling": {"mode": "serial", "max_parallel": 1},
                "quota_recovery": {"enabled": False, "threshold_percent": 10}}
        self.assertNotIn("relay", E._validate(dict(base)), "policies without relay stay unchanged")
        self.assertEqual(E._validate(dict(base, relay=POLICY["relay"]))["relay"]["candidates"][2],
                         {"route": "agy-acc2", "model": "gemini-pro"})

    def test_assess_uses_threshold_and_model_scoped_windows(self):
        self.assertEqual(RL.assess(quota(50, 11), POLICY)["status"], "READY")
        self.assertEqual(RL.assess(quota(50, 10), POLICY)["status"], "HANDOFF_REQUIRED")
        self.assertEqual(RL.assess({"status": "unknown", "windows": []}, POLICY)["status"], "UNKNOWN")
        self.assertEqual(RL.assess({"status": "auth_required", "windows": [{"remainingPercent": 90}]}, POLICY)["status"], "UNKNOWN")
        scoped = {"windows": [{"remainingPercent": 5, "models": ["opus"]}, {"remainingPercent": 70}]}
        self.assertEqual(RL.assess(scoped, POLICY, "gemini-pro")["status"], "READY")
        self.assertEqual(RL.assess(scoped, POLICY, "claude-opus-4")["status"], "HANDOFF_REQUIRED")
        with self.assertRaises(ValueError):
            RL.assess(quota(50), {"relay": {"enabled": False, "threshold_percent": 10}})

    def test_next_circulates_after_current_and_skips_exhausted_or_unknown(self):
        quotas = {"codex-local": quota(80), "codex-acc2": quota(9), "agy-acc2": {"status": "unknown", "windows": []}, "claude-local": quota(40)}
        chosen = RL.choose(POLICY, quotas, "codex-local")
        self.assertEqual(chosen["candidate"], {"route": "claude-local", "model": "opus"})
        self.assertEqual([row["route"] for row in chosen["skipped"]] if "skipped" in chosen else [], [])
        self.assertEqual(RL.choose(POLICY, quotas, "claude-local")["candidate"], {"route": "codex-local"}, "wraps around")
        exhausted = RL.choose(POLICY, {"codex-acc2": quota(3)}, "codex-local")
        self.assertEqual(exhausted["status"], "EXHAUSTED")
        self.assertEqual(len(exhausted["skipped"]), 3)

    def test_single_director_gate_and_boot_visibility(self):
        started = RL.start(FakeBrain, self.root, POLICY, "codex-local", now=1000)
        self.assertEqual(started["status"], "ACTIVE")
        self.assertRegex(started["token"], r"^[0-9a-f]{32}$")
        raw = (self.root / ".project-brain/.cache/relay.json").read_text(encoding="utf-8")
        self.assertNotIn(started["token"], raw, "only the token hash is stored")
        with self.assertRaisesRegex(ValueError, "RELAY_ACTIVE"):
            RL.start(FakeBrain, self.root, POLICY, "codex-acc2", now=1001)
        with patch.dict(os.environ, {RL.TOKEN_ENV: ""}):
            with self.assertRaisesRegex(ValueError, "RELAY_ACTIVE"):
                RL.require_free_or_director(FakeBrain, self.root)
        with patch.dict(os.environ, {RL.TOKEN_ENV: started["token"]}):
            RL.require_free_or_director(FakeBrain, self.root)
            self.assertTrue(RL.authorized(FakeBrain, self.root))
        self.assertIn("RELAY: ACTIVE gen 1 director codex-local", RL.boot_line(FakeBrain, self.root))
        self.assertIn("1970-01-01T00:16:40Z", RL.boot_line(FakeBrain, self.root))

    def test_handoff_takeover_cancels_live_predecessor_and_records_timestamps(self):
        started = RL.start(FakeBrain, self.root, POLICY, "codex-local", task_id="aaaaaaaa-2222-4333-8444-000000000000", now=1000)
        with self.assertRaisesRegex(ValueError, "RELAY_NOT_DIRECTOR"):
            self.handoff("0" * 32, {"route": "codex-acc2"})
        with self.assertRaisesRegex(ValueError, "listed relay candidate"):
            self.handoff(started["token"], {"route": "other-route"})
        result = self.handoff(started["token"], {"route": "agy-acc2", "model": "gemini-pro"})
        self.assertEqual(result["status"], "HANDED_OFF")
        request = self.submitted[0]
        self.assertEqual((request["routeId"], request["modelId"], request["kind"], request["mode"]), ("agy-acc2", "gemini-pro", "write", "execute"))
        self.assertEqual(request["minRemainingPercent"], 10, "the Pool refuses a successor below the threshold")
        self.assertEqual(request["clientLabel"], "Project Brain relay director gen 2")
        self.assertRegex(request["idempotencyKey"], r"^[a-zA-Z0-9_.:-]{8,128}$")
        successor = request["prompt"].split(RL.TOKEN_ENV + "=")[1].split()[0]
        self.assertIn("relay takeover", request["prompt"])
        self.assertIn(".project-brain/evidence/PB-001/handoff.json", request["prompt"])
        with self.assertRaisesRegex(ValueError, "HANDOFF_PENDING"):
            self.handoff(started["token"], {"route": "agy-acc2", "model": "gemini-pro"})
        with self.assertRaisesRegex(ValueError, "RELAY_TOKEN_MISMATCH"):
            self.takeover(started["token"])
        self.states["aaaaaaaa-2222-4333-8444-000000000000"] = "running"
        taken = self.takeover(successor)
        self.assertEqual((taken["status"], taken["generation"], taken["director"]["route"]), ("ACTIVE", 2, "agy-acc2"))
        self.assertTrue(taken["previous_director_cancelled"])
        self.assertEqual(self.cancelled, ["aaaaaaaa-2222-4333-8444-000000000000"], "previous CLI stopped, not its login")
        self.assertFalse(RL.authorized(FakeBrain, self.root, started["token"]), "the old baton is void")
        self.assertTrue(RL.authorized(FakeBrain, self.root, successor))
        events = [row["event"] for row in json.loads((self.root / ".project-brain/.cache/relay.json").read_text())["history"]]
        self.assertEqual(events, ["START", "HANDOFF", "TAKEOVER"])
        self.assertEqual(RL.status(FakeBrain, self.root)["last_event"]["at"], "1970-01-01T00:50:00Z")

    def test_lost_submit_retry_voids_the_earlier_successor(self):
        started = RL.start(FakeBrain, self.root, POLICY, "codex-local", now=1000)
        def failing(request):
            self.submitted.append(request)
            raise ValueError("Pool RPC timed out")
        with self.assertRaises(ValueError):
            self.handoff(started["token"], {"route": "codex-acc2"}, submit=failing)
        lost = self.submitted[0]["prompt"].split(RL.TOKEN_ENV + "=")[1].split()[0]
        self.handoff(started["token"], {"route": "codex-acc2"})
        retried = self.submitted[1]
        self.assertNotEqual(retried["idempotencyKey"], self.submitted[0]["idempotencyKey"])
        with self.assertRaisesRegex(ValueError, "RELAY_TOKEN_MISMATCH"):
            self.takeover(lost)
        self.assertEqual(self.takeover(retried["prompt"].split(RL.TOKEN_ENV + "=")[1].split()[0])["status"], "ACTIVE")

    def test_policy_change_or_checkpoint_edit_blocks_takeover(self):
        started = RL.start(FakeBrain, self.root, POLICY, "codex-local", now=1000)
        self.handoff(started["token"], {"route": "codex-acc2"})
        token = self.submitted[0]["prompt"].split(RL.TOKEN_ENV + "=")[1].split()[0]
        changed = {"relay": dict(POLICY["relay"], threshold_percent=20)}
        with self.assertRaisesRegex(ValueError, "RELAY_POLICY_CHANGED"):
            self.takeover(token, policy=changed)
        (self.root / ".project-brain/evidence/PB-001/handoff.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "RELAY_CHECKPOINT_CHANGED"):
            self.takeover(token)

    def test_stop_cancels_live_tasks_and_complete_needs_the_baton(self):
        started = RL.start(FakeBrain, self.root, POLICY, "codex-local", task_id="aaaaaaaa-2222-4333-8444-000000000000", now=1000)
        self.handoff(started["token"], {"route": "codex-acc2"})
        with self.assertRaisesRegex(ValueError, "RELAY_NOT_DIRECTOR"):
            RL.finish(FakeBrain, self.root, "COMPLETE", "done", token="0" * 32)
        stopped = RL.finish(FakeBrain, self.root, "STOP", "user stop", cancel=self.cancelled.append, now=4000)
        self.assertEqual(stopped["status"], "STOPPED")
        self.assertEqual(len(stopped["cancelled"]), 2)
        self.assertIsNone(RL.boot_line(FakeBrain, self.root))
        RL.require_free_or_director(FakeBrain, self.root)
        again = RL.start(FakeBrain, self.root, POLICY, "codex-acc2", now=5000)
        self.assertEqual(RL.finish(FakeBrain, self.root, "COMPLETE", "all accepted", token=again["token"])["status"], "COMPLETED")

    def test_max_handoffs_limits_circulation(self):
        policy = {"relay": dict(POLICY["relay"], max_handoffs=1)}
        started = RL.start(FakeBrain, self.root, policy, "codex-local", now=1000)
        RL.handoff(FakeBrain, self.root, policy, {"id": "PB-001"}, "next", {"route": "codex-acc2"}, "/pb/brain.py",
                   self.submit, now=2000, token=started["token"], write_checkpoint=self.checkpoint)
        token = self.submitted[0]["prompt"].split(RL.TOKEN_ENV + "=")[1].split()[0]
        self.takeover(token, policy=policy)
        with self.assertRaisesRegex(ValueError, "RELAY_LIMIT"):
            RL.handoff(FakeBrain, self.root, policy, {"id": "PB-001"}, "next", {"route": "codex-local"}, "/pb/brain.py",
                       self.submit, now=3500, token=token, write_checkpoint=self.checkpoint)

    def test_worker_reserve_follows_enabled_threshold_only(self):
        self.assertEqual(RL.worker_reserve(FakeBrain, self.root, POLICY), 10)
        self.assertEqual(RL.worker_reserve(FakeBrain, self.root, {"relay": {"enabled": False, "threshold_percent": 30}}), 0)
        self.assertEqual(RL.worker_reserve(FakeBrain, self.root, None), 0)

    def test_damaged_record_withholds_authority(self):
        path = self.root / ".project-brain/.cache/relay.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"schema": 1, "status": "ACTIVE"}', encoding="utf-8")
        self.assertFalse(RL.authorized(FakeBrain, self.root, "0" * 32))
        self.assertIn("INVALID", RL.boot_line(FakeBrain, self.root))
        with self.assertRaises(ValueError):
            RL.require_free_or_director(FakeBrain, self.root)


if __name__ == "__main__":
    unittest.main()
