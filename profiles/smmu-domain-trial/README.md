# v159 early SMMU trial — allocator refusal, not DMA acceptance

The complete candidate boots and returns safely, but **does not establish a
Wi-Fi SMMU domain**. Hardware completed601 read-only selection reads, choosing
bank7/slot8/ASID1 with CB0 SCTLR0x0a9f00e0. The allocator then returned-71 at
native stage3, before fault IRQ registration, registry reservation or SMMU
programming. Its exact physical-segment/PAR rejection is not yet localized.

The missing domain correctly prevents subsequent PCIe power-up. Root images,
PID1 and all-eight-core admission still pass. Touch DMA attaches, transfers,
detaches and releases memory successfully against the unchanged baseline; this
is not a physical-finger test or hardware proof of the registered Wi-Fi route.
Sync reset, physical fastboot, full stock SHA, Android/root/green, original
charging/radio/scanning settings and sleep restoration all pass.

## Implemented source

`EarlySource.py` injects a noinline invocation after UFS's own SMMU setup and
before host queue start. The exported guard requires the actual early watchdog,
a bounded90-second window and no panic/RPC withdrawal. Native code additionally
requires a low observed/latched WLAN GPIO and active GIC before proceeding.
The later PCIe worker checks SMMU readiness; WCN stopping withdraws that readiness.

The native owner connects the real selector/allocator, exact stock IRQ map,
registered fault handlers, upstream context programmer and full table walker.
Only the selected bank/stream and whitelisted registers can be written. Fault
handlers mask their own registered interrupt, preserve SMMU fault registers,
publish one fault snapshot and refuse further setup. Spurious IRQs are bounded.
All mappings/references remain until reset once hardware can access them.

The stock IRQ list is not linear. `Irqs.h` is generated from the hash-bound
stock FDT, with global INTID97 and83 implemented context entries. Raw source
facts and unused DT entries are in `Irqs.json`. No other device's IRQ numbering
is substituted.

The CPU derivative also adopts upstream `acba4ee`'s owned-SGI mask and self-probe
filter. Existing Darwin assembly corrections remain. Normal8-core IPI/timer
admission passed here; a deliberate SGI self-probe was not run.

## ATOS correction

The actual baseline ID0=0x4c017e84 has **ATOSNS bit26 set: hardware translation
queries are not supported**. Fixed TB322FC Linux checks that bit and falls back
to the page-table walker. `audit_smmu_atos.py` binds this conclusion to source.
The final domain code likewise uses the independent complete physical graph
audit and context readback. Native writes to unsupported ATS registers refuse.
Translation mode2 explicitly means software walk; it never claims a hardware
translation count or completed DMA. A future controlled MHI transfer still
must verify real device DMA end-to-end.

The first unflashed native attempt assumed ATOS support and is superseded. The
first kernel compile also caught recovery definitions below the UFS caller;
the noinline invocation bridge fixes that ordering. Failed artifacts remain.

## Build and validation

The domain programmer has25 host scenarios/4020100 checks, including the actual
TB322FC no-ATOS path with zero ATS writes. Fault/status functions have17 checks.
ASan/UBSan pass; physical MMIO/GIC are modeled. Native binding contains11
components with the real allocator/table code; its remaining early guard is
resolved by the UFS object in the full kernel.

Five existing native objects are replaced and16 component objects added. Core
filelist, other archive members, initializer targets, all30 original Apple
executable ranges and the7124-byte entry/return relation are preserved. Eleven
direct init/stop/selection/domain/PCIe calls and their prelink bytes are audited.
The1019-byte menu preserves8-second countdown, fallbacks and recovery/power guards.
No new firmware, partition layout or rollback floor is introduced.

Build with the explicit `--smmu-domain` WCN variant, `--smmu-build` PCIe variant,
and `build_pcie_root_kernel.py --endpoint-build ... --smmu-build ... --route-build ...`.
The latter still consumes the source-built v156 parent and declared components.
Pack/audit via `--wcn-report`/`--bt-runtime` as in the previous profile; this is
not a newly rerun combined empty-directory clean build. Do not flash raw kernels.

- Raw kernel: `50424764d8f19f211e1ee033e09a9cf422e8fe65c1484163c726b2c4800b94bc`.
- Signed image: `cc29e9e305e95db69ef0a88a2f8f405d0cac8db4a346a3de25b2e03c933eca76`.
- Session: `fa0f855a25106996`; floor1738713600/footer0/parent3.
- Capture148056 bytes, reported drop maximum0, no reconnect/discontinuity.
  Required lines are present; no post-disconnect counter is available.
- Raw capture SHA: `9ebed94e71d2e7287e710c6e5b1e0ccc271b6755412fb9b5efc97a738ebf65ef`.
- [Assessment](../../docs/evidence/smmu-domain-v159-20261116.json).

Workbench run: `edl_work/live-smmu-v159-20261116`; final build:
`edl_work/smmu-kernel-v159-20261116/build2`; package:
`edl_work/smmu-boot-v159-20261116/package1`. Core/fault/native tests use
`edl_work/smmu-domain-20261116/{host2,fault2,native2}`; final bridge objects are
`smmu-kernel-v159-20261116/{wcn3,pcie3}` on Windows and
`lab/smmu-domain-20261116/{wcn3,pcie3}` on Mac.

Next expose the allocator's exact stage, returned physical-segment lengths,
addresses and PAR attributes. Do not guess which condition failed or weaken a
gate from this generic-71 result. Fault IRQ/context/DMA/MSI/MHI and networking
remain unaccepted. All trial jobs ended with stock Android restored.
