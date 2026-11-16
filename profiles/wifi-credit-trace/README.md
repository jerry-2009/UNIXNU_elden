# v179 HTC credit and CE completion observations

Three production units receive reversible counter insertions: the exact prepared
`htc.c`, common `pci.c` and common `wmi.c`. Removing the inserted observers yields
the original bytes. No packet content, credentials, registers, timeout or credit
value is changed. Only counts and the fixed HTC header words are retained.

The first WMI failure snapshot copies the counters and emits bounded lines
(worst host fixture202B, below the existing320B formatter). Transmit attempts
include EAGAIN retries; `ok` means the existing CE submission returned0, not
firmware execution. RX counts follow valid endpoint selection; trailer/report
counters preserve their original processing boundaries.

Build `build_wifi_credit_trace.py --runtime-build <base> --irq-build <v178-runtime>
--llvm <llvm> --output <runtime>`, then use that runtime in the v178 native/full
kernel recipe. Three units are rebuilt now; the prior IRQ-observer unit is
retained, yielding4 changed/121 retained units relative to the original platform
runtime. The core, helper, cache and trust inputs remain unchanged.
`test_wifi_credit_trace.py` checks exact input/reversible insertion, actual
counter bounds and formatting with ASan/UBSan. It does not execute the complete
driver protocol on the host. Final Mac source1/host2/runtime1/native1/kernel1;
host1 exposed the actual prepared `wait_event_timeout_once` anchor and was
retained. Warnings: HTC126, common PCI120, common WMI632, native1.

Hardware: WMI command16387 was call5 after4 send API successes. Endpoint2 is
WMI service0x100, flow enabled, credit size2176, uplink CE3/downlink CE2.
It started with2 credits and received2 more across2 reports;4 sends were accepted
and2591 retry checks found no credit. This is not a complete absence of credit
reports. CE callbacks entered and returned, including CE2 nine times.

The actual WMI source ring is CE3: producer HP16 versus hardware TP8 at the
first-failure ring report. CE4 is the flow-disabled HTT endpoint and its drained
ring must not be mistaken for WMI completion. Next inspect CE3 head-pointer/
shadow/notification handling using the exact Armada TB322FC source. Timers and
CE completion work already use the bottom-half completion queue; do not add a
duplicate queue flag as an unproven fix. No scan/network acceptance yet.

Native MSI status/pending/error stayed0 with the receiver armed. Later diagnostics
request forced RDDM, so later failures are not independent evidence. Physical
fence and full stock/Android/root/green/settings restoration passed.
[Evidence](../../docs/evidence/wifi-credit-trace-v179-20261116.json).
