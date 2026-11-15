# Native brightness service (v142)

The current charging/Bluetooth menu omitted `elden-backlight`, leaving the
already built native brightness service off. The old v47 run had proved its
system request, chip readback and stop/restore path. This variant re-enables
that same driver on the current v140 charging baseline.

The original9418f7f7 BacklightRuntime body remains unchanged except for a boot
argument fallback: `ebl` is read only when `elden-backlight` is absent. The long
name therefore still wins, including an explicit0/invalid mode. `ebl=6` fits the
primary menu at1021 bytes; all other arguments and fallback entries are identical
to the parent. No security/recovery option is removed or shortened.

Only `BacklightRuntime.late.o` rebuilds. The original removal of automatic class
initialization/globalization, original AppleARMBacklight ABI, chip identity,
settled health qualification, signed brightness bounds, async/fade handling,
resource ownership and original-level restoration remain. Other archive members,
all core objects and the charging policy are unchanged. Original30 Apple code
regions, entry, full assets and AVB1738713600/footer0/parent3 pass.

One current hardware run passed: service published at1597, the system requested
2048 and the chip readback was2048. Stop restored1597, released the controller
without quarantine and confirmed restoration before synchronized fastboot return.
Full-SHA stock restore, Android/root/green/boot and unchanged charging settings
passed; sleep was requested. Capture1144721B/drop0. See [hardware.json](hardware.json).
This is an actual system-generated request, not a manual slider test. Screen
sleep, low-brightness net charging and dual-port charging are not established.

Add `--backlight-service` to the complete
[current charging build recipe](../charge-window-handoff/README.md#build).
It includes window handoff/verification and then builds this one-object variant.
Do not combine it with the independent SPMI translation diagnostic. Direct staged
builds use `build_charge_verification.py --backlight-service` over the qualified
window parent. Individual source stages/full packaging ran; the newest combined
empty-directory command was not repeated.

The initial native-code check accidentally included later functions when counting
argument-parser calls. It was corrected to use the actual function boundary;
the compiler output was unchanged and the failed packaging attempt is retained.
