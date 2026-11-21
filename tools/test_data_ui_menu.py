"""Check actual2GiB UI menu semantics, byte budget and unchanged recovery gates."""
import copy
import tomllib
import unittest
from battery_boot import arguments
from data_capacity_boot import enable_ui_replay, menu


class DataUiMenu(unittest.TestCase):
    def setUp(self):
        self.q = dict(profile="data-capacity-2g-key", expanded_data=True,
                      expected_data_bytes=2147483648, keystore_capacity_updated=True,
                      keep_packed_data=True)

    def test_default_keeps_diagnostics_and_disables_replay(self):
        config = tomllib.loads(menu(self.q))
        args = arguments(config["entry"][0]["args"])
        self.assertEqual(args["armcpu-self-ipi"], "1")
        self.assertEqual(args["ecp"], "2")
        self.assertNotIn("elden-ui-replay", args)

    def test_ui_opt_in_changes_only_two_diagnostics_and_replay(self):
        old = tomllib.loads(menu(self.q))
        new = tomllib.loads(menu(enable_ui_replay(self.q)))
        expected = arguments(old["entry"][0]["args"])
        expected.pop("elden-power-votes")
        expected.pop("ecp")
        expected["elden-ui-replay"] = "1"
        self.assertEqual(arguments(new["entry"][0]["args"]), expected)
        restored = copy.deepcopy(new)
        restored["entry"][0]["args"] = old["entry"][0]["args"]
        self.assertEqual(restored, old)
        self.assertLessEqual(len(new["entry"][0]["args"].replace("@SESSION@", "0" * 16).encode()), 1023)
        for name, value in {"cpus": "8", "sheng-smp": "1", "armcpu-self-ipi": "1", "smp-hold": "600",
                            "vdog": "3", "elden-panic-delay": "180", "elden-thermal": "3",
                            "elden-touch": "7", "elden-charge-control": "1", "elden-pmic-notify": "1",
                            "elden-usb-icl": "2", "epd": "2"}.items():
            self.assertEqual(expected[name], value)

    def test_wrong_or_unqualified_profiles_are_rejected(self):
        for changes in ({"profile": "data-capacity-2g"}, {"expanded_data": False},
                        {"expected_data_bytes": 536870912}, {"keystore_capacity_updated": False}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                enable_ui_replay(dict(self.q, **changes))


if __name__ == "__main__":
    unittest.main()
