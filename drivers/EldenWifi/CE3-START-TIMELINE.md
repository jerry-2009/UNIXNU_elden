# CE3 register lifetime during startup

The first DMA inspector hardware run validated both pending28-byte buffers:
descriptor bus addresses match, native arena/CPU PAR44 and backing PAs agree,
fixed HTC/WMI/TLV headers match the actual command. It did not establish device
reads or hardware SMMU translation. At the same first timeout the HIF reads
returned CE3 base/size/ID/MSI/HP/TP0 and MISC`0x80` (idle, disabled), while
software HP16 and remote DMA TP8 remain. The stage at which this configuration
became zero is not proved.

`Ce3TimelinePatch.py` leaves original operations intact and reads the same
CE3 registers at existing boundaries: CE init, common DP init, HIF start,
service ready, cookie configuration, unified ready, mode-request return,
HTT version-request return and first PMF PDEV send. Each record includes
the accessible remap-control witness; at most12 records/7 reads each.
No reinitialization, inferred mode-response success, response-trace candidate,
credit/timeout change or firmware modification is introduced.

This distinguishes initial programming failure, later configuration loss,
and a stable register read-path discrepancy. Reads retain normal HIF
window/wake semantics and are observations, not an atomic hardware snapshot.
Mode-request return is enqueue success, not proof the firmware applied it.
Original first-failure descriptor/DMA inspection remains for comparison.

14 actual helper host cases pass ASan/UBSan with MMIO modeled.37 component
mutation cases and complete native/prelink/entry/package checks pass;30 original
Apple executable regions and entry delta7124 remain. Core C157/WMI632 inherited
warnings are preserved. Only two runtime C units are recompiled;123 parent
runtime objects and the exact native inspector worker remain.

```text
python tools/test_wifi_ce3_timeline.py --cc CLANG --core-source PLAIN_CORE --wmi-source INSPECT_WMI --output NEW_HOST
python tools/build_wifi_ce3_timeline.py --runtime-build BASE --parent-build INSPECT_RUNTIME --llvm LLVM --output NEW_RUNTIME
```

Use the qualified inspector worker, then the complete network17 kernel and
entry/package audit. [Evidence](../../docs/evidence/wifi-ce3-timeline-20261120.json).
No scan, association, DHCP or traffic acceptance is implied. Full physical
fence/stock restoration remains mandatory for the bounded live trial.
