"""Check actual service-profile runtime boundaries; no assets or device I/O."""
import unittest
import hashlib
import json
from wifi_service_boot import qualify_runtime_snapshot
from build_wifi_service_kernel import relocated_baseline_plan


class RuntimeBoundary(unittest.TestCase):
    def snapshot(self, profile):
        srng = profile == "wifi-srng-trace"
        credit = profile != "wifi-wmi-snapshot"
        return dict(append_only_observer=True, base_binding_sha256="a" * 64,
                    credit_trace=credit, srng_trace=srng,
                    rebuilt_units=5 if srng else 4 if credit else 1,
                    retained_units=120 if srng else 121 if credit else 124,
                    compiled_this_step=2 if srng else 3 if credit else 1,
                    reversible_counter_insertions=True, inherited_irq_observer=True,
                    reversible_srng_insertions=True, producer_credit_timeout_changes=False)

    def test_all_three_profiles_keep_their_own_boundary(self):
        for profile in ("wifi-wmi-snapshot", "wifi-credit-trace", "wifi-srng-trace"):
            snap = self.snapshot(profile)
            qualify_runtime_snapshot(snap, dict(credit_trace=snap["credit_trace"], srng_trace=snap["srng_trace"]), "a" * 64, profile)

    def test_srng_rejects_unqualified_or_mixed_inputs(self):
        for change in ({"rebuilt_units": 4}, {"retained_units": 121}, {"compiled_this_step": 3},
                       {"base_binding_sha256": "b" * 64}, {"credit_trace": False}, {"srng_trace": False},
                       {"reversible_counter_insertions": False}, {"reversible_srng_insertions": False},
                       {"inherited_irq_observer": False}, {"producer_credit_timeout_changes": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                qualify_runtime_snapshot(dict(self.snapshot("wifi-srng-trace"), **change),
                                         dict(credit_trace=True, srng_trace=True), "a" * 64, "wifi-srng-trace")

    def test_native_variant_must_match(self):
        with self.assertRaises(ValueError):
            qualify_runtime_snapshot(self.snapshot("wifi-srng-trace"), dict(credit_trace=True, srng_trace=False), "a" * 64, "wifi-srng-trace")

    def test_provider_relocation_preserves_all_other_plan_bytes(self):
        digest="feb9fefa74ee07e39b7f5694c5921329d0017163a6391bdd82bf64a2ae9208c0"
        old=dict(kind="repository",path="drivers/EldenBluetooth/WcnPower.c",sha256=digest,bytes=10257)
        new=dict(old,kind="snapshot",path="frozen/WcnPower-feb9fefa74ee.c")
        raw=json.dumps(dict(providers={digest:old},unchanged=[1,2,3]),separators=(',',':')).encode()
        current=raw.replace(json.dumps(old,separators=(',',':')).encode(),json.dumps(new,separators=(',',':')).encode())
        expected=hashlib.sha256(raw).hexdigest()
        self.assertEqual(relocated_baseline_plan(current,expected),digest)
        with self.assertRaises(ValueError):relocated_baseline_plan(current.replace(b'[1,2,3]',b'[1,2,4]'),expected)


if __name__ == "__main__":
    unittest.main()
