"""Restore saved Android radio/scan flags through a serial-bound ADB caller.

The caller must already have verified stock boot, Android identity/root/green.
Command success is insufficient: actual saved flag equality closes restoration.
"""
import subprocess
import time

RADIOS = ("bluetooth_on", "wifi_on")
SCANS = ("ble_scan_always_enabled", "wifi_scan_always_enabled")


class RadioRestoreTimeout(RuntimeError):
    def __init__(self, receipt):
        super().__init__("Saved Android radio/scan flags did not return before deadline")
        self.receipt = receipt


def restore_radio_settings(adb, original_radios, original_scans, *, seconds=40,
                           clock=time.monotonic, sleep=time.sleep):
    radios, scans = tuple(original_radios), tuple(original_scans)
    if len(radios) != 2 or any(value not in ("0", "1") for value in radios):
        raise ValueError("Two saved radio flags required")
    if len(scans) != 2 or any(value not in ("0", "1", "null") for value in scans):
        raise ValueError("Two saved scan flags required")
    if not isinstance(seconds, (int, float)) or not 0 < seconds <= 60:
        raise ValueError("Bounded restoration window required")
    deadline = clock() + seconds
    receipt = dict(complete=False, attempts=0, errors=[], actual_radios=None, actual_scans=None)

    def command(*arguments):
        remaining = deadline - clock()
        if remaining <= 0:
            raise RadioRestoreTimeout(receipt)
        # The serial-bound caller must forward this timeout to subprocess.run.
        return adb(*arguments, timeout=min(5, remaining))

    while clock() < deadline:
        receipt["attempts"] += 1
        try:
            actual_radios = tuple(command("shell", "settings", "get", "global", key).strip() for key in RADIOS)
            actual_scans = tuple(command("shell", "settings", "get", "global", key).strip() for key in SCANS)
            receipt.update(actual_radios=list(actual_radios), actual_scans=list(actual_scans))
            if actual_radios == radios and actual_scans == scans:
                receipt["complete"] = True
                return receipt
            for key, expected, actual in zip(SCANS, scans, actual_scans):
                if actual == expected or clock() >= deadline:
                    continue
                if expected == "null":
                    command("shell", "settings", "delete", "global", key)
                else:
                    command("shell", "settings", "put", "global", key, expected)
            if clock() < deadline and actual_radios[0] != radios[0]:
                command("shell", "cmd", "bluetooth_manager", "enable" if radios[0] == "1" else "disable")
            if clock() < deadline and actual_radios[1] != radios[1]:
                command("shell", "svc", "wifi", "enable" if radios[1] == "1" else "disable")
        except (RuntimeError, TimeoutError, subprocess.TimeoutExpired) as error:
            # Preserve startup failures even when a later observation succeeds.
            if len(receipt["errors"]) < 16:
                receipt["errors"].append(dict(attempt=receipt["attempts"], type=type(error).__name__, message=str(error)[:400]))
        remaining = deadline - clock()
        if remaining > 0:
            sleep(min(1, remaining))
    raise RadioRestoreTimeout(receipt)
