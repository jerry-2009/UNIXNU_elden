# v140: automatic charge windows after explicit bypass

One real high-SOC trial passed: bypass →80% →bypass →40–60% →stock,
applied generations1..5. Both exits from bypass sent SET28=1 and received real
ACKs, while firmware kept charging off at100% (`firmware-held=1`). Stock restored
window95100 and enabled1. Session-bound sync/reset returned to physical fastboot;
full-SHA stock restore and Android/root/green/boot completion passed. Android
charging_enable1/protection095100/EU095100 matched before/after; sleep was requested.
See [hardware.json](hardware.json) for raw capture identity and losses. This does
not prove low-SOC automatic resumption or a complete physical protection cycle.

The previous policy could leave the OEM manual charge inhibit latched when the
user selected an automatic window above its upper threshold. It saw charging
already disabled and reported the window applied without clearing the manual
flag. A later SOC decrease therefore could not resume charging. Conversely, if
firmware had not yet applied a new window, the host could send SET28=0 itself
and turn a temporary threshold hold into the same persistent manual inhibit.

`WindowSource.py` derives this variant from the v139 verified policy. After the
normal window write/readback and two later complete polls, leaving our previously
applied explicit bypass always sends SET28=1, waits for its real ACK and later
fresh readback. Firmware may still hold charging off; that is reported separately.
Automatic window transitions otherwise leave charging permission to OEM firmware.
Only explicit bypass sends SET28=0. Original EU precedence, hysteresis and other
firmware protections are not replaced by a host approximation.

The distinction is established by the fixed stock ADSP: vendor property28 calls
`mm8013_set_info` selector16, which stores `(value == 0)` in the manual inhibit
flag. The automatic controller checks that flag before the bypass/EU/normal
windows. The dormant selector24 bypass-window setter is not a newly qualified
host command. `tools/analysis/audit_charge_window_contract.py` checks27 instruction
and table anchors; its output is in [the firmware evidence](../../docs/evidence/charge-window-contract.json).

Host validation executes the actual v139 and v140 C policies with a bounded
firmware-contract model: old7 scenarios reproduce the defects, fixed11 cover
high-SOC mode changes, subsequent low/high/low SOC, unrelated firmware holds,
refused/missing release ACK and unchanged EU priority. The existing146 mode
checks also pass under ASan/UBSan. These are not actual DSP execution or physical
charge-cycle tests. Original v139 freshness/quarantine/30-second timeout handling
and the same ChargePolicy structure/API remain.

## Build

Add `--charge-window-handoff` to the existing `build_clean.py --bt-address17`
recipe, keeping that recipe's other prerequisite options and declared inputs.
It includes v139 verification. Direct staged builds use
`build_charge_verification.py --window-handoff` with the same explicit inputs.
All source is in this repository; no retained v139 objects are required.

Complete option chain (paths are supplied by the caller):

```sh
.venv/bin/python -B tools/build_clean.py \
  --variant bluetooth --inputs /path/to/inputs.json \
  --output out/clean-charge-window --target boot --jobs 4 \
  --bt-exit-stack --software-keystore --bluetool-launch \
  --bt-transport-trace --bluetool-lifecycle --bt-registry \
  --bt-helper-trace --bt-process-lifetime --bt-address17 \
  --charge-window-handoff
```

The component stages, complete link and final packaging have run; this newest
combined command has not been repeated in an empty directory. It preserves the
explicit original/toolchain inputs described in CLEAN-BUILD.md.

The native build replaces two PMIC archive members, preserves all core objects,
hashes the30 original Apple executable regions and checks the existing entry
assembly/return contract. The variant has its own loaded-content contract and
exact derived-source validation. It keeps59 native Bluetooth rules and the existing
runtime/ADT/trust/boot arguments. The initial packaging attempt rejected the new
profile before writing an image; the explicit qualifier and menu/ADT/trust routing
were then added. The failure is retained; final packaging is `boot2`.

This fixes host handoff to automatic policy. Dual-port arbitration, physical net
charge, full protection cycles and persistent settings still require completion.
See [charging status](../../docs/CHARGING-STATUS.md) for device evidence.
