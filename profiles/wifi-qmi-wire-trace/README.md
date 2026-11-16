# v170 QMI shutdown transaction evidence

v169 isolated the wait to `ath12k_qmi_firmware_stop`. This candidate retains the
same shutdown and timeout policy and records MODE_OFF transaction initialization,
send return and wait return; MHI IPCR queue attempts and UL/DL completions; parsed
QMI header identifiers and matching transaction completion. It never logs message
payloads, keys, EAPOL, SSIDs or packet bytes. Tracing latches only when MODE_OFF
begins and remains until reset; each direction/header category logs at most8
records. Counters are diagnostic aggregates while that window is active, not a
claim that every IPCR callback belongs to the one transaction.

The existing bounded native quiesce sampler additionally reads five logical IRQ
masks from the fixed64-slot dispatcher table. It changes no IRQ state. Shared IRQs
can appear in both enabled and disabled masks. Native hardware reads are limited
to the retained root's MSI status/enable/mask and MHI status registers, with read
return codes and native IRQ counters. Snapshots are not coherent transactions and
do not consume pending bits. The9s WCN and5s owned cleanup limits remain unchanged.

`QmiWireTracePatch.py` verifies that removing its insertions restores original
statements. Four units (ath12k_qmi, nw_qrtr_mhi, qmi_interface and lx_rt) rebuild;
116 original units and five previously reviewed init/lifecycle/stop objects stay.
The new metadata array and fixed-table reader have unique strong symbols; the
full binding must resolve them. `build_wifi_qmi_trace.py` takes the original
runtime, lifecycle, init and stop outputs explicitly. Use its runtime result with
the existing native/root/boot builders; the profile is selected from that result.

Final Mac: `lab/wifi-qmi-v170-20261116/{source2,runtime1,native2,kernel1}`;
workbench mirrors them in `edl_work/wifi-qmi-v170-20261116`. Native1 caught a helper
referenced before its declaration; Native2 uses the existing bounded Region read
method at exact constant offsets. The failed attempt is retained.

Kernel `5ef8942835e980ba14a56ee371d63b073d2add93be0bfdd118feeb51a2f4fa11`;186 source pins, Apple30,
entry7124 and23 existing critical calls pass. C warning counts are recorded in
[evidence](../../docs/evidence/wifi-qmi-v170-20261116.json), not globally waived.
No hardware result or new networking acceptance is claimed at this component stage.

Signed candidate `0b2608e540e9814f00515e3f30bdda0b514a978faf823f8c9794b065fab4cb11`, session `dda874c589629554`.
All186 source inputs match Git index; entry/asset/FAT/AVB checks pass
(1738713600/0/3). Hardware queues MODE_OFF (send0/txn38/52B) but observes no UL completion,
DL callback or QMI RX. Software and native IRQs remain enabled; hardware pending0,
count80/error0 and MHI201. No native drain completion. Typed fallback and full
stock Android/root/green/settings restore pass. Capture266413B/SHA69d5d52f,
maximum reported drop0/no reconnect; no final post-disconnect counter.

Observation correction: qmi_txn_init returns its nonnegative allocated ID38.
The trace ternary incorrectly renders snapshot txn0 when ret>0; send/wait lines
identify38. This does not fabricate the absent UL/DL callbacks. Correct before
reuse; do not rewrite the tested v170 pins.

Next [platform shutdown integration](../../docs/WIFI-PLATFORM-SHUTDOWN.md) uses
the actual upstream shutdown callback with independent native drain checks.
