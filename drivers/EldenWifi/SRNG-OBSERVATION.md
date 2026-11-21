# CE3 first-failure notification observation

v179 proves WMI endpoint2 uses uplink CE3/downlink CE2, with four send API
successes and later credit shortage. The existing ring dump reports software
HP16/coherent TP8. It does not tell whether the last producer notification
reached the actual hardware HP. The exact TB322FC6f97250e source uses shadow
registers for Peach and supplies the real R2 HP/TP layout.

`SrngTracePatch.py` derives two exact production inputs: unchanged common HAL
and v179's already-instrumented WMI. Removing its insertions restores each
original byte. Existing send, wait, credit, register-write and timeout statements
remain unchanged. Both source hashes are required; modified inputs are refused.

The HAL records entry/return counts and the last software HP/offset around the
existing non-LMAC producer write, plus shadow timer callback count. WMI requests
one snapshot on its first `-EAGAIN`, before its existing timeout warning and the
later forced-RDDM path. The snapshot resolves the **actual CE3 source ring**,
checks initialization/direction/index/pointers/geometry, finds its shadow table
entry and reads the documented real R2 HP and TP through the existing PCI HIF.

No shadow register is read. That register can be write-only; its last notification
value is observed in software. No producer/consumer register, credit value,
timeout or clock policy is written by the observer. HIF reads retain their
existing window-selection/wakeup behavior. Read words are raw observations;
returned0xffffffff or mismatched values must not be called successful delivery.
Atomic counters are individually observed, not a coherent multiword snapshot.

The two bounded lines distinguish software notification/count/offset, expected
shadow target, actual hardware HP/TP and coherent DMA TP. If the actual HP did
not advance to the notified value, audit mapping/notification; if it did advance,
continue the device consumption/completion investigation. Neither case by itself
proves the root cause or authorizes fabricated credits/extended timeouts.

## Build and validation

```sh
python3 tools/test_wifi_srng_trace.py --runtime-build BASE --credit-build V179 --output NEW-HOST
python3 tools/build_wifi_srng_trace.py --runtime-build BASE --credit-build V179 --llvm LLVM --output NEW-RUNTIME
```

`BASE` is the qualified125-object Peach runtime and `V179` its credit-observer
output. Only HAL/WMI are recompiled, preserving the preceding LX IRQ/HTC/PCI
changes:5 changed/120 retained units. Scalar ARM64/iOS17, full symbol renaming,
unchanged combined imports, one new real observer export, no initializers and
all inherited object/dependency fingerprints are checked.

16 actual helper scenarios with ASan/UBSan cover first-only sampling, correct two
real accesses, no shadow read, invalid/unavailable contexts, bounds, signed count
rejection, counter calls and formatting (longest168B below320B). MMIO and driver
protocol are modeled; these are not hardware results. Final Mac host3/runtime3
passes; existing HAL70/WMI632 warnings remain recorded. Prior warning-bearing
builds remain archived. [Evidence](../../docs/evidence/wifi-srng-component-20261118.json).

This component is not a complete kernel/boot candidate. Next compose it with the
current service core/native and qualification profile, audit the entire boot,
then take one first-failure diagnostic window with the preserved physical
DMA/MSI/PERST stop and complete stock/root/settings restoration.
