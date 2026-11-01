"""Offline director quota-recovery state/authority regressions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import brain
import runtime_quota_recovery as Q


class FakeBrain:
    BRAIN_DIR = ".project-brain"
    write_atomic = staticmethod(brain.write_atomic)
    checkout_lock = staticmethod(brain.checkout_lock)


def snapshot(used=80, reset=2000, secondary=None, account="stable-account-id"):
    value = {"accountId": account, "ordinaryUsageAllowed": True,
             "rateLimits": {"limitId": "provider-director",
                            "primary": {"usedPercent": used, "resetsAt": reset,
                                        "windowDurationMins": 300}}}
    if secondary is not None:
        value["rateLimits"]["secondary"] = {
            "usedPercent": secondary[0], "resetsAt": secondary[1], "windowDurationMins": 10080}
    return value


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="pb-quota-recovery-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.policy = {"quota_recovery": {"enabled": True, "threshold_percent": 20},
                       "execution": {"mode": "solo"}}
        self.checkpoint = ".project-brain/evidence/PB-001/handoff.json"
        self.file = self.root / self.checkpoint
        self.file.parent.mkdir(parents=True)
        self.file.write_text(json.dumps({"task": "PB-001", "progress": "checkpointed",
                                         "handoff": "continue verification"}), encoding="utf-8")

    def prepare(self, observation=None, rearm=False):
        return Q.prepare(FakeBrain, self.root, observation or snapshot(), self.policy,
                         self.checkpoint, now=1000, allow_rearm=rearm)

    def armed(self, observation=None, rearm=False):
        prepared = self.prepare(observation, rearm=rearm)
        Q.arm(FakeBrain, self.root, prepared["nonce"], "host-automation-1")
        return prepared["nonce"]

    def resume(self, nonce, observation=None, now=2000, policy=None):
        return Q.check_resume(FakeBrain, self.root, observation or snapshot(used=10, reset=3000),
                              policy or self.policy, nonce, now=now)

    def test_assess_threshold_and_all_blocking_resets(self):
        self.assertEqual(Q.assess(snapshot(79), self.policy, 1000)["status"], "READY")
        for used in (80, 100):
            result = Q.assess(snapshot(used), self.policy, 1000)
            self.assertEqual(result["status"], "CHECKPOINT_REQUIRED")
            self.assertEqual(result["next_reset_at"], 2000)
        result = Q.assess(snapshot(80, 2000, (99, 9000)), self.policy, 1000)
        self.assertEqual(result["next_reset_at"], 9000)
        self.assertEqual(set(result["limiting_windows"]), {"primary", "secondary"})
        result = Q.assess(snapshot(80, 2000, (1, 9000)), self.policy, 1000)
        self.assertEqual(result["next_reset_at"], 2000)
        disabled = copy.deepcopy(self.policy)
        disabled["quota_recovery"]["enabled"] = False
        self.assertEqual(Q.assess(None, disabled, 1000), {"status": "DISABLED"})
        self.assertEqual(Q.assess(None, {"quota_recovery": {"enabled": False}}, 1000),
                         {"status": "DISABLED"})

    def test_unknown_observations_never_imply_capacity(self):
        invalid = [None, {}, snapshot(account=""), snapshot(reset=1000), snapshot(reset=None),
                   snapshot(used=float("nan")), snapshot(used=float("inf")), snapshot(used=True),
                   snapshot(used=-1), snapshot(used=101), snapshot(used=10 ** 1000)]
        for key in ("accountId", "ordinaryUsageAllowed", "rateLimits"):
            value = snapshot()
            del value[key]
            invalid.append(value)
        for key in ("limitId", "primary"):
            value = snapshot()
            del value["rateLimits"][key]
            invalid.append(value)
        for field in ("usedPercent", "resetsAt", "windowDurationMins"):
            value = snapshot()
            del value["rateLimits"]["primary"][field]
            invalid.append(value)
        value = snapshot(used=10)
        value["ordinaryUsageAllowed"] = False
        invalid.append(value)
        value = snapshot()
        value["rateLimits"]["secondary"] = {"usedPercent": 5, "resetsAt": "unknown"}
        invalid.append(value)
        for value in invalid:
            with self.subTest(value=value):
                self.assertEqual(Q.assess(value, self.policy, 1000)["status"], "UNKNOWN")
        for value in (0, 51, True, float("nan"), float("inf"), "20"):
            policy = {"quota_recovery": {"enabled": True, "threshold_percent": value}}
            self.assertEqual(Q.assess(snapshot(), policy, 1000)["status"], "UNKNOWN")
            with self.assertRaises(ValueError):
                Q.prepare(FakeBrain, self.root, snapshot(), policy, self.checkpoint, 1000)

    def test_prepare_idempotence_and_lost_ack_requires_readback(self):
        first = self.prepare()
        self.assertEqual(first["host_action"], "CREATE_AUTOMATION")
        second = self.prepare()
        self.assertEqual(second["nonce"], first["nonce"])
        self.assertEqual(second["host_action"], "READBACK_AUTOMATION")
        self.assertEqual(self.resume(first["nonce"])["status"], "BLOCKED")
        Q.arm(FakeBrain, self.root, first["nonce"], "host-automation-1")
        self.assertEqual(self.prepare()["host_action"], "ALREADY_ARMED")
        Q.arm(FakeBrain, self.root, first["nonce"], "host-automation-1")
        for nonce, host_id in (("wrong", "host-automation-1"), (first["nonce"], "different"),
                               (first["nonce"], ""), (first["nonce"], "x" * 257)):
            with self.assertRaises(ValueError):
                Q.arm(FakeBrain, self.root, nonce, host_id)
        with self.assertRaises(ValueError):
            self.prepare(snapshot(reset=2500))
        raw = (self.root / ".project-brain/.cache/quota-recovery.json").read_text(encoding="utf-8")
        self.assertNotIn("stable-account-id", raw)
        self.assertNotIn("provider-director", raw)
        self.assertNotIn("account_hash", json.dumps(Q.status(FakeBrain, self.root)))
        self.assertLess(len(json.dumps(first)), 2048)

    def test_prepare_requires_existing_guarded_public_checkpoint(self):
        for path in (".project-brain/evidence/PB-002/handoff.json", "../handoff.json",
                     str(self.file), ".project-brain/.cache/handoff.json",
                     ".project-brain/evidence/PB-001/../PB-001/handoff.json",
                     ".project-brain/evidence/secrets/handoff.json"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                Q.prepare(FakeBrain, self.root, snapshot(), self.policy, path, 1000)
        self.file.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.prepare()
        self.file.write_text("x" * (Q.MAX_CHECKPOINT + 1), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.prepare()

    def test_linked_checkpoint_refused(self):
        target = self.root / "actual.json"
        target.write_text('{"handoff":"continue"}', encoding="utf-8")
        self.file.unlink()
        try:
            self.file.symlink_to(target)
        except OSError:
            self.skipTest("symlink creation unavailable on this host")
        with self.assertRaises(ValueError):
            self.prepare()

    def test_checkpoint_change_or_loss_revokes(self):
        nonce = self.armed()
        self.file.write_text('{"handoff":"changed"}', encoding="utf-8")
        self.assertEqual(self.resume(nonce)["status"], "CANCELLED")
        self.assertEqual(self.resume(nonce)["status"], "CANCELLED")
        nonce = self.armed(rearm=True)
        self.file.unlink()
        self.assertEqual(self.resume(nonce)["status"], "CANCELLED")

    def test_account_change_revokes_before_due_and_never_rearms(self):
        nonce = self.armed()
        other = snapshot(used=5, reset=3000, account="different-account")
        result = self.resume(nonce, other, now=1500)
        self.assertEqual(result["status"], "CANCELLED")
        self.assertEqual(result["automation_id"], "host-automation-1")
        self.assertEqual(self.resume(nonce)["status"], "CANCELLED")
        self.assertNotIn("different-account", json.dumps(result))
        low_other = snapshot(used=95, account="different-account")
        with self.assertRaises(ValueError):
            self.prepare(low_other)
        self.assertEqual(Q.status(FakeBrain, self.root)["status"], "CANCELLED")
        explicit = self.prepare(low_other, rearm=True)
        self.assertNotEqual(explicit["nonce"], nonce)
        self.assertEqual(explicit["host_action"], "CREATE_AUTOMATION")

    def test_early_wake_and_quota_not_renewed(self):
        nonce = self.armed(snapshot(80, 2000, (99, 2500)))
        self.assertEqual(self.resume(nonce, snapshot(1, 3000, (1, 3500)), 2400)["status"], "WAIT")
        self.assertEqual(self.resume(nonce, snapshot(99, 3000, (1, 3500)), 2500)["status"], "WAIT")
        self.assertEqual(self.resume(nonce, snapshot(1, 3000), 2500)["status"], "WAIT")
        # Old exhausted observations cannot become usable merely because time passed.
        self.assertEqual(self.resume(nonce, snapshot(1, 2000, (1, 2500)), 2500)["status"], "WAIT")
        self.assertEqual(self.resume(nonce, snapshot(1, 3000, (1, 3500)), 2500)["status"], "RESUMED")

    def test_policy_change_or_disable_revokes(self):
        for change in ("disable", "threshold", "execution"):
            nonce = self.armed(rearm=True)
            policy = copy.deepcopy(self.policy)
            if change == "disable":
                policy["quota_recovery"]["enabled"] = False
            elif change == "threshold":
                policy["quota_recovery"]["threshold_percent"] = 10
            else:
                policy["execution"]["mode"] = "native"
            self.assertEqual(self.resume(nonce, now=1500, policy=policy)["status"], "CANCELLED")

    def test_cancel_blocks_late_callback_and_stale_nonce(self):
        nonce = self.armed()
        result = Q.cancel(FakeBrain, self.root)
        self.assertEqual(result["status"], "CANCELLED")
        self.assertEqual(result["host_action"], "DELETE_AUTOMATION")
        self.assertEqual(self.resume(nonce)["status"], "CANCELLED")
        with self.assertRaises(ValueError):
            Q.arm(FakeBrain, self.root, nonce, "host-automation-1")
        with self.assertRaises(ValueError):
            self.prepare()
        new = self.prepare(rearm=True)
        self.assertNotEqual(new["nonce"], nonce)
        self.assertEqual(self.resume(nonce)["status"], "BLOCKED")
        self.assertEqual(Q.status(FakeBrain, self.root)["status"], "PREPARED")

    def test_callback_authorizes_only_once_and_policy_canonicalization(self):
        nonce = self.armed()
        equivalent = {"execution": {"mode": "solo"}, "quota_recovery": {
            "threshold_percent": 20, "enabled": True}}
        result = self.resume(nonce, policy=equivalent)
        self.assertEqual(result["status"], "RESUMED")
        self.assertEqual(result["checkpoint"], self.checkpoint)
        self.assertEqual(len(result["checkpoint_sha256"]), 64)
        self.assertEqual(self.resume(nonce)["status"], "CONSUMED")

    def test_readonly_status_and_cancel_missing_create_nothing(self):
        empty = self.root / "empty"
        empty.mkdir()
        self.assertEqual(Q.status(FakeBrain, empty), {"status": "NONE"})
        self.assertEqual(Q.cancel(FakeBrain, empty), {"status": "NONE"})
        self.assertEqual(list(empty.iterdir()), [])

    def test_malformed_private_state_never_grants_authority(self):
        nonce = self.armed()
        path = self.root / ".project-brain/.cache/quota-recovery.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for field, value in (("automation_id", None), ("schema", 2), ("nonce", 1),
                             ("observed_reset_at", 1), ("policy_hash", "wrong")):
            state = dict(original)
            state[field] = value
            path.write_text(json.dumps(state), encoding="utf-8")
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.resume(nonce)

    def test_unknown_account_waits_without_authorizing_and_limit_change_revokes(self):
        nonce = self.armed()
        unknown = snapshot(used=1, reset=3000)
        del unknown["accountId"]
        self.assertEqual(self.resume(nonce, unknown)["status"], "BLOCKED")
        changed = snapshot(used=1, reset=3000)
        changed["rateLimits"]["limitId"] = "other-limit"
        self.assertEqual(self.resume(nonce, changed)["status"], "CANCELLED")


if __name__ == "__main__":
    unittest.main()
