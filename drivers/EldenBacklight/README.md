# Elden backlight

The original21H461 AppleARMBacklight-compatible service drives this board's
AW99706 through the qualified GENI I2C path. The current build/runtime evidence
is in [backlight-service](../../profiles/backlight-service/README.md).

`BootSource.py` adds only the short `ebl` fallback to the hash-bound original
driver, allowing `ebl=6` to fit the crowded boot-argument buffer. The original
chip, brightness and stop code is preserved. Mode6 uses the established settled
health qualification before publishing the service; it does not ignore an
arbitrary fault or force-enable an unqualified chip.

System request2048, hardware readback and restoration to1597 have passed on the
current charging/Bluetooth baseline. Manual slider behavior, display sleep and
net charging still require their own acceptance.
