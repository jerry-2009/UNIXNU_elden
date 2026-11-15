# PD initialization with normal GUI brightness (v145)

This packaging selection reuses the exact v144 kernel, entry transform and
runtime assets. Its only FAT member change is `unixnu.toml`: `ebl=5` becomes
`ebl=6` plus the derived session ID. No native kernel recompilation or frozen
report rewrite is needed. The PD mode2/thermal3, SDP-only500mA budget and existing
600-second observation/recovery settings remain.

`--pd-gui` is required by both the packer and independent auditor. It transforms
only a fully qualified `pd-power-trial` descriptor into GUI intent; the original
native report/profile remains unchanged. The normal brightness service runs;
the timed backend dim/restore experiment does not run.

One real run passed PD handoff, a system brightness request/readback2048 and
restoration to1597. After PD Ready, one explicit virtual-HID Home press/release
reached the SpringBoard desktop. Four CRC-verified desktop frames were captured
and visually checked. No Settings tap was attempted: UI-replay diagnostics stay
disabled. This is software input, not physical-touch or manual-slider acceptance.
White placeholder widgets/black background remain; this is not perfect rendering.

At the system-requested level2048, the last10 qualified published battery samples
before restoration had median−177.5mA (discharge). The prior+190mA result at raw
level798 must not be generalized to this default brightness or peak power.
PD initialization and brightness control coexist, but everyday net charging,
long-term stability and full protection cycles remain unaccepted.

Synchronized return, clean PD/backlight stop, full-SHA stock restore and Android
root/green/boot completion passed; settings matched and sleep was requested.
Capture losses remain in [hardware.json](hardware.json). The exact reused inputs
and changed FAT member are recorded in [reuse-proof.json](reuse-proof.json).

For a clean build, add `--pd-gui` to the full charging option chain. It builds the
required PD kernel stages and passes GUI intent to packaging/audit. Staged use
adds `--pd-gui` to `build_v91_boot.py` and `audit_v91_boot.py` with the unchanged
v144 report/runtime/entry inputs. The packaging/audit ran; the combined newest
empty-directory build was not repeated.

The existing watcher now offers `--desktop-only --entry-gesture home
--wait-pd-ready` for this configuration. It uses the same checked frame matcher
and structured control channel, never attempts an unavailable Settings replay,
and requests return if no desktop is observed within90 seconds after entry.
