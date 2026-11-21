"""Exercise actual bounded restoration against startup/service failures."""
import unittest
import subprocess
from android_radio_restore import restore_radio_settings, RadioRestoreTimeout


class Android:
    def __init__(self):
        self.flags = dict(bluetooth_on="0", wifi_on="0", ble_scan_always_enabled="0", wifi_scan_always_enabled="0")
        self.time = 0
        self.calls = []
        self.startup_reads = 0
        self.wifi_failures = 0
        self.ignore_commands = False

    def now(self):
        return self.time

    def sleep(self, seconds):
        self.time += seconds

    def adb(self, *arguments, timeout):
        assert 0 < timeout <= 5
        self.calls.append(arguments)
        if arguments[1:3] == ("settings", "get"):
            if self.startup_reads:
                self.startup_reads -= 1
                raise RuntimeError("settings service starting")
            return self.flags[arguments[4]]
        if arguments[1:3] == ("svc", "wifi") and self.wifi_failures:
            self.wifi_failures -= 1
            raise RuntimeError("wifi service starting")
        if not self.ignore_commands:
            if arguments[1:3] == ("settings", "put"):
                self.flags[arguments[4]] = arguments[5]
            elif arguments[1:3] == ("settings", "delete"):
                self.flags[arguments[4]] = "null"
            elif arguments[1:3] == ("cmd", "bluetooth_manager"):
                self.flags["bluetooth_on"] = "1" if arguments[3] == "enable" else "0"
            elif arguments[1:3] == ("svc", "wifi"):
                self.flags["wifi_on"] = "1" if arguments[3] == "enable" else "0"
            else:
                raise AssertionError(arguments)
        return ""

    def restore(self, radios=("1", "1"), scans=("null", "1"), seconds=10):
        return restore_radio_settings(self.adb, radios, scans, seconds=seconds, clock=self.now, sleep=self.sleep)


class Restoration(unittest.TestCase):
    def test_startup_failures_retained_then_actual_equality(self):
        android = Android()
        android.startup_reads = 2
        android.wifi_failures = 2
        receipt = android.restore()
        self.assertTrue(receipt["complete"])
        self.assertEqual(receipt["actual_radios"], ["1", "1"])
        self.assertEqual(receipt["actual_scans"], ["null", "1"])
        self.assertEqual(len(receipt["errors"]), 4)

    def test_already_restored_performs_no_writes(self):
        android = Android()
        receipt = android.restore(("0", "0"), ("0", "0"))
        self.assertTrue(receipt["complete"])
        self.assertEqual(len(android.calls), 4)

    def test_command_success_without_state_change_is_refused(self):
        android = Android()
        android.ignore_commands = True
        with self.assertRaises(RadioRestoreTimeout) as caught:
            android.restore(seconds=3)
        self.assertFalse(caught.exception.receipt["complete"])
        self.assertEqual(android.time, 3)

    def test_persistent_startup_failure_is_bounded(self):
        android = Android()
        android.startup_reads = 99
        with self.assertRaises(RadioRestoreTimeout) as caught:
            android.restore(seconds=4)
        self.assertEqual(len(caught.exception.receipt["errors"]), 4)
        self.assertEqual(android.time, 4)

    def test_subprocess_timeout_consumes_only_remaining_budget(self):
        android = Android()

        def timed(*arguments, timeout):
            android.time += timeout
            raise subprocess.TimeoutExpired(arguments, timeout)

        with self.assertRaises(RadioRestoreTimeout) as caught:
            restore_radio_settings(timed, ("1", "1"), ("0", "0"), seconds=3.5,
                                   clock=android.now, sleep=android.sleep)
        self.assertEqual(android.time, 3.5)
        self.assertEqual(len(caught.exception.receipt["errors"]), 1)

    def test_invalid_saved_values_issue_no_commands(self):
        for radios, scans in ((("1",), ("0", "0")), (("1", "2"), ("0", "0")),
                              (("1", "0"), ("null", "2"))):
            android = Android()
            with self.assertRaises(ValueError):
                android.restore(radios, scans)
            self.assertEqual(android.calls, [])


if __name__ == "__main__":
    unittest.main()
