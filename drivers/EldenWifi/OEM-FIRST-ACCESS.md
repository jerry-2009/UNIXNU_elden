# Recheck UMAC at the first command access

The passive hardware record shows UMAC request/state0 and CE3 configuration0
before first PMF, while MHICTRL0x200/MHISTATUS0x201 and software M0/EE2 remain.
Both wake-reference counts are1 and the selected callback path records no
reset/wake/CE configuration write. Other host writers were not observed, and
the cause is still unproved. No graceful stop was recorded; full typed physical
fastboot and stock Android/root/green/settings restoration passed.
[Exact hardware record](../../docs/evidence/wifi-pci-state-hardware-20261120.json).

The loaded OEM module and public `d50b305f` HIF source use MHI get_sync followed
by UMAC request1/status2 at actual accesses. The current trial held that request
only at startup. `UmacAccess.inc` performs one bounded recheck before the first
PMF command, retaining the original platform hold and adding one balanced real
MHI reference. Only the known0x3004 request is written; the exact0x1e04040
status must become2 within50ms. A failure returns its real error and restores
a known prior0/1 request. No CE ring programming or new packet is performed.

This contrast tests whether the target is merely asleep and its CE registers
recover after the original handshake. If the ring remains zero or the handshake
fails, it provides no justification to reinstall a live ring. It is a first-access
experiment, not a full runtime reference-counting or power-management port.

20 actual helper cases pass ASan/UBSan; MMIO and MHI are modeled.63 composition
mutations, two scalar C objects/full kernel,30 Apple execution regions, entry7124
and signature checks pass. PCI120/WMI632 inherited warnings remain. The initial
test wrongly included ready2 among timeout states; that fixture failure is kept.
The actual opcode/schema, firmware, CE, credits, WMI deadlines and shutdown
contract are retained, as are the matched battery-only worker and actual WCN
archive. Hardware trial is pending.

```text
python tools/test_wifi_umac_access.py --cc CLANGXX --pci-source STATE_PCI --wmi-source TIMELINE_WMI --output HOST
python tools/build_wifi_umac_access.py --runtime-build BASE --parent-build STATE_RUNTIME --timeline-build TIMELINE --llvm LLVM --output RUNTIME
```

Then rebuild the exact net17 kernel with the qualified battery pair, prepare
entry, package and audit. [Candidate evidence](../../docs/evidence/wifi-umac-access-20261120.json).
