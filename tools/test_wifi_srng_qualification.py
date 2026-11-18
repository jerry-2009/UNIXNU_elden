"""Check actual service-profile runtime boundaries; no assets or device I/O."""
import unittest
import hashlib
import json
from wifi_service_boot import qualify_runtime_snapshot
from build_wifi_service_kernel import relocated_baseline_plan, runtime_observer_exports


class RuntimeBoundary(unittest.TestCase):
    def snapshot(self, profile):
        window=profile=="wifi-pci-window-trace"
        srng = profile in ("wifi-srng-trace","wifi-pci-window-trace")
        credit = profile != "wifi-wmi-snapshot"
        return dict(append_only_observer=True, base_binding_sha256="a" * 64,
                    credit_trace=credit, srng_trace=srng,
                    pci_window_trace=window,
                    rebuilt_units=6 if window else 5 if srng else 4 if credit else 1,
                    retained_units=119 if window else 120 if srng else 121 if credit else 124,
                    compiled_this_step=3 if window else 2 if srng else 3 if credit else 1,
                    reversible_counter_insertions=True, inherited_irq_observer=True,
                    reversible_srng_insertions=True, producer_credit_timeout_changes=False)

    def test_all_three_profiles_keep_their_own_boundary(self):
        for profile in ("wifi-wmi-snapshot", "wifi-credit-trace", "wifi-srng-trace","wifi-pci-window-trace"):
            snap = self.snapshot(profile)
            qualify_runtime_snapshot(snap, dict(credit_trace=snap["credit_trace"], srng_trace=snap["srng_trace"],pci_window_trace=snap['pci_window_trace']), "a" * 64, profile)

    def test_pci_window_mode_rejects_wrong_units_and_native(self):
        snapshot=self.snapshot('wifi-pci-window-trace')
        for changes in ({'rebuilt_units':5},{'retained_units':120},{'compiled_this_step':2},{'pci_window_trace':False}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                qualify_runtime_snapshot(dict(snapshot,**changes),dict(credit_trace=True,srng_trace=True,pci_window_trace=True),'a'*64,'wifi-pci-window-trace')

    def test_ce3_flow_boundary_and_native_match(self):
        snapshot=dict(self.snapshot('wifi-pci-window-trace'),rebuilt_units=7,
                      retained_units=118,compiled_this_step=2,ce3_flow_trace=True,
                      reversible_flow_insertions=True,flow_record_limit=64)
        native=dict(credit_trace=True,srng_trace=True,pci_window_trace=True,ce3_flow_trace=True)
        qualify_runtime_snapshot(snapshot,native,'a'*64,'wifi-ce3-flow-trace')
        for changes in ({'rebuilt_units':6},{'retained_units':119},{'compiled_this_step':3},
                        {'ce3_flow_trace':False},{'ce3_flow_trace':'true'},
                        {'reversible_flow_insertions':False},{'flow_record_limit':65},
                        {'flow_record_limit':64.0},{'pci_window_trace':False},
                        {'producer_credit_timeout_changes':True}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                qualify_runtime_snapshot(dict(snapshot,**changes),native,'a'*64,'wifi-ce3-flow-trace')
        for native_flag in (False,'true'):
            with self.assertRaises(ValueError):
                qualify_runtime_snapshot(snapshot,dict(native,ce3_flow_trace=native_flag),'a'*64,'wifi-ce3-flow-trace')
        with self.assertRaises(ValueError):
            qualify_runtime_snapshot(snapshot,native,'a'*64,'wifi-pci-window-trace')

    def test_link_exports_add_exactly_the_two_flow_functions(self):
        parent=self.snapshot('wifi-pci-window-trace')
        current=dict(parent,ce3_flow_trace=True)
        self.assertEqual(runtime_observer_exports(current)-runtime_observer_exports(parent),
                         {'_elden_wifi_ce3_flow_note','_elden_wifi_ce3_flow_dump'})
        self.assertEqual(runtime_observer_exports(parent)-runtime_observer_exports(current),set())
        with self.assertRaises(ValueError):
            runtime_observer_exports(dict(current,pci_window_trace=False))

    def test_mode_metadata_has_one_rebuilt_unit_and_exact_variant(self):
        snapshot=dict(self.snapshot('wifi-pci-window-trace'),rebuilt_units=7,
                      retained_units=118,compiled_this_step=1,ce3_flow_trace=True,
                      reversible_flow_insertions=True,flow_record_limit=64,
                      mode_trace=True,reversible_mode_insertions=True,mode_note_limits=[8,4,16])
        native=dict(credit_trace=True,srng_trace=True,pci_window_trace=True,ce3_flow_trace=True,mode_trace=True)
        qualify_runtime_snapshot(snapshot,native,'a'*64,'wifi-ce3-flow-trace')
        for change in ({'compiled_this_step':2},{'mode_trace':'true'},
                       {'reversible_mode_insertions':False},{'mode_note_limits':[8,4,17]},
                       {'mode_note_limits':[8.0,4,16]}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                qualify_runtime_snapshot(dict(snapshot,**change),native,'a'*64,'wifi-ce3-flow-trace')
        with self.assertRaises(ValueError):
            qualify_runtime_snapshot(snapshot,dict(native,mode_trace=False),'a'*64,'wifi-ce3-flow-trace')

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
