# Bounded backlight power comparison (v143)

This opt-in diagnostic reuses the existing mode5 backend dim/restore trial.
It does not publish the normal mode6 GUI brightness service during measurement.
Normal use remains the [v142 service](../backlight-service/README.md).

Only the trial schedule changes:30 seconds settling, then45 seconds each at
original1597, half798 and restored1597. The original300..900-second admission,
health checks, stop checks, lowering-only write and unconditional restore remain.
The rest of the driver is byte-identical to the service derivation. The actual
trial function passed10 ASan/UBSan normal/cancellation/failure cases. One late
backlight object rebuilds; PMIC/core/other members, Apple30 and entry/AVB remain.
The only menu change from v142 is `ebl=6` to `ebl=5`; normal recovery is not extended.

One hardware run completed all phases and original-level restoration. Analysis
retained the existing rule excluding the first six poll cycles after each
transition;10/9/10 samples remained. Positive values below would mean battery
charging; all three measured medians were negative:

| Phase | Level | Median battery current |
| --- | ---: | ---: |
| Baseline | 1597 | −480.5mA |
| Dim | 798 | −212.0mA |
| Restored | 1597 | −368.5mA |

The dim phase still discharged. Startup/workload drift is visible between the
two original-level phases, so these are not an exact isolated LED power estimate.
The short-port PD contract selected5V/3A; a contract does not prove input watts.
No current limit was raised and no PD bootstrap/pulse or DC write was enabled.
This is not a full charge-cycle or GUI-slider acceptance.

The host requested synchronized fastboot return only after `power-finished=0`,
confirmed original brightness and controller release. Full-SHA stock restoration,
Android/root/green/boot completion and unchanged charge settings passed; sleep
was requested. Capture1228466B/drop0. See [hardware.json](hardware.json).

Add `--backlight-power-trial` to the full charging recipe; it selects the backlight
build stage and this diagnostic instead of the GUI brightness service. Direct
builds use `build_charge_verification.py --backlight-service --backlight-power-trial`
over the qualified window parent. Individual stages/full packaging ran; the
newest combined empty-directory command was not repeated.

The initial30-second draft was not packaged/flashed because it left too few
post-transition samples. A subsequent command typo in the original kernelcache
path stopped prelink; that output is retained. Final native/package output is
`backlight-power-v143-3` in the Mac isolated build area.
