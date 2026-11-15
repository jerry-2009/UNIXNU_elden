# PD handoff followed by bounded power measurement (v144)

This joins the already tested native PD startup/pause/restore controller to the
current v140 charging and v143 brightness backend. It keeps SDP-only ICL mode2
and the500mA limit; no DC FIFO/register write path is enabled.

The menu selects `epd=2` (fallback for the long PD option), the existing thermal
pulse mode3 and the existing600-second SMP hold. Other recovery settings remain.
Two numeric-one battery options use their equivalent bare form; the final command
line is1023 bytes. No security option or fallback entry is removed.

`PdStartupSource.py` changes only the option alias and publishes an observation of
the original controller/telemetry. It does not change its GPIO, current-setting,
retry or qualification algorithm. A single64-bit atomic binds state, transport
epoch and timestamp; the getter rejects stopped/down/changed epochs and expires
pending/ready data after3 seconds. Mode2 must have really completed, restored and
still show qualified9V, fresh data and matching500mA applied/readback before Ready.

`PdPowerSource.py` waits at most240 seconds before beginning the existing bounded
brightness experiment. Failed/disabled status refuses the experiment; loss of
Ready during a hold aborts it and follows original-level restoration. The wait,
hold, getter and predicate passed34 host ASan/UBSan scenarios. These tests do not
replace real PD or fault-path acceptance.

Two objects rebuild, in their respective PMIC and backlight archives. The only
new export is the read-only `elden_pd_power_observation`; all other exports/core
objects/unchanged archive members and30 original Apple code regions are checked.
The late backlight class-initialization handling and entry/AVB contract remain.

## Hardware result

The original GPIO pulse completed high/low successfully (101011µs, held0). The
9V contract and repeated ICL0 readbacks were followed by500mA restoration and
phase6/error0/restored1. Only then did the brightness test begin. No observation
loss occurred during the successful test; state3 afterwards was stop withdrawal,
with the controller still phase6/error0.

After excluding the original six transition cycles, each phase had9 complete
samples. Positive current here means flowing into the battery:

| Backlight code | Median battery current | Interpretation |
| ---: | ---: | --- |
| 1597 | 0mA | Near-zero sampled current, not indefinite endurance proof |
| 798 | +190mA | All9 aggregate/dual-gauge samples and native publisher agreed on net charging |
| 1597 restored | 0mA | Original brightness restored |

“Half” means1597→798 raw backlight codes, not50% of the iPadOS slider. This was a
45-second dim window at99/100% SOC, with both data and PD connectors present.
It does not prove input27W, peak fast charge, long-term maintenance, all cables,
full protection cycles or the normal GUI-service operating point. The contract
advertised9V/3A; the software ICL limit stayed500mA.

Capture1281918B/drop26, no reconnection/discontinuity. Synchronized return, clean
PD/backlight stop, full-SHA stock restoration and Android/root/green/boot passed;
charge settings matched and sleep was requested. [hardware.json](hardware.json)
retains losses and limits. The normal GUI candidate remains v142; this is a
separate diagnostic, not an automatically promoted daily-use image.

## Reproduce

Add `--pd-power-trial` to the full
[charging option chain](../charge-window-handoff/README.md#build). It includes
the required backlight/charging stages. Direct native builds use
`build_charge_verification.py --pd-power-trial` over the qualified v143 power
parent. Individual stages and full packaging ran; the newest combined command
was not repeated in an empty directory. Frozen inputs are not changed by fetching
reference repositories.

Use `tools/analysis/assess_pd_power.py RUN --output NEW.json` for current build
metadata; the legacy assessor requires an obsolete packet.json and hardcodes a
different charger's current. No fake packet is generated. Battery phase analysis
continues to use the existing complete-sample/six-cycle exclusion rules.
