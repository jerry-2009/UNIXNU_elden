# MSI receiver and endpoint configuration — offline components ready

The [native control transport](TRANSPORT.md) now connects the DMA/MSI/config
providers to the PCIe worker and compiles as a combined native binding. MHI
execution/drain and complete-kernel/hardware validation remain pending.

The local DesignWare receiver core is implemented in `Msi.c`. The endpoint
configuration fix is in `EldenWifi/peach/PciMsiPatch.py` / `PciMsi.inc`.
Both are compiled; neither has been connected to a native Wi-Fi worker or
tested with a device-generated MSI. v163 remains the latest hardware image.

## Receiver ownership and stopping

The register layout and INTID173 come from the exact TB322FC Linux commit
`6f97250ead155fc3b980856323e99a4623dae73d`, independently of Sheng. Only
group0 (32 vectors, DBI `820/824/828/82c/830`) is touched. Stock and this Linux
normally route the endpoint through ITS device1401; choosing local iMSI is
an explicit alternate route that still needs hardware validation. See the
[source audit](../EldenSmmu/DMA-NATIVE.md#msi-route-and-next-step).

Preparation requires the actual root/power/DMA owner and real quiescence.
It refuses an unmasked active foreign receiver, masks/disables group0,
acknowledges only observed old status, sets the owned sink, and verifies the
registers and exclusive GIC registration. Arming enables the receiver only
after those checks. There are no endpoint capability, bus-master or ITS writes
in this core. Native callbacks must retain DBI mapping and clocks through stop.

The handler performs one status read and an ordered W1C of only those bits,
then accumulates pending vectors and wakes the worker. It never invokes MHI
or allocates memory in IRQ context. A later MSI remains latched for the next
interrupt. Read/write failures or 128 empty interrupts latch an error and mask
the owned GIC line. The native poller must inspect `irq_error` atomically as
well as consuming `elden_pcie_msi_pending()`; state `Armed` alone is not health.

Stopping first asks the caller to prove MHI/DMA quiescence. A premature request
leaves interrupts available to deliver the last completion. Only afterwards
does it withdraw IRQ access, mask GIC and receiver, disable the receiver and
wait for entered handlers within the deadline. Sequentially consistent access
and in-flight accounting close the late-entry race. Failures retain state and
maps until reset; a repeated failed stop does not repeat register writes.
The callback is not allowed to equate an empty DMA arena with hardware drain.

45 actual-core scenarios / 132 checks pass ASan/UBSan, including all setup
callback failures, foreign ownership, stuck readback, bad IRQ flags, W1C arrival
races, premature stop, IRQ failure/storm and an outstanding-handler timeout.
MMIO/GIC/quiescence are host models. The ARM64/iOS17 object has no warnings,
FP/SIMD, imports or initializers:
`7b31f720f8f2d365d127bf8a28c6b95dd50e1df3d988388ef729d8dfb4fdf2de`.

## Endpoint MSI error handling

The actual frozen Ath12k5f7f5a8 `pci_alloc_irq_vectors` / `pci_free_irq_vectors`
functions reproduced three problems: a refused PCI target write still returns
success; asking for three vectors enables four but publishes three; and free
clears software state without disabling endpoint MSI.

The repair validates the real capability and available vector count, chooses
a supported power of two, handles 32/64-bit targets and per-vector masks,
preserves the upper half of the 16-bit data register, and checks every config
operation and readback before publishing descriptors. Free confirms the whole
disabled control word before clearing software ownership. Failure retains the
descriptor state and logs the real error. Best-effort disable on an allocation
error is not a restoration or DMA-drain claim; the board still has to verify
shutdown/reset. `pci_set_master` remains a no-op and requires explicit native
enable/withdrawal in the later transport integration.

29 actual-entrypoint fault scenarios / 50 checks pass ASan/UBSan, with original
false success reproduced separately. The corrected `nw_pci.o` was rebuilt with
the complete existing kernel-target headers, then linked with all 124 unchanged
runtime objects. Their hashes and all old consumed inputs were rechecked;
the new unit's dependency set differs only by its source path. Symbol renaming
preserves code/data/bindings, and the 125-object union has the same imports.
The real `pwrseq_qcom_wcn_set_ol_cpr` dependency remains external.

- PCI object: `52291af3fa3b52873b1f684ca30413d887d0cd13a6cedb51d825d1aaf7cd4fd2`.
- Runtime binding: `dfdba1646a260843683658ffe7590341c0a93bc1b7c677a2d8f7e68accba32fb`.
- This unit has 24 inherited warnings versus the old 26; the two repaired
  entrypoints have zero warnings. Other runtime warning review remains open.
- Initial runtime1 had additional bounded signed-conversion warnings. Explicit
  checked types removed them; the earlier output remains available.

`build_wifi_runtime.py` now applies this repair automatically on a new full
build, retaining the original source. `audit_wifi_runtime.py` checks the exact
derivative when its record is present. That complete preparation recipe was
updated but not rerun from empty in this round; the targeted compile/link above
is the executed validation.

## Reproduce and continue

```text
python tools/test_pcie_msi.py --output <new-receiver-host>
python tools/build_pcie_msi.py --llvm <llvm-bin> --output <new-receiver-native>
python tools/test_pci_msi_config.py --component-repository <fixed-Ath12kWifi-clone> --output <new-pci-host>
python tools/build_wifi_pci_msi.py --runtime-build <verified-MHI-fixed-runtime> --llvm <llvm-bin> --output <new-runtime-binding>
```

Next connect native DBI/GIC/wake callbacks and actual config access from the
confirmed PCIe worker, bind the DMA provider, and implement real MHI/IRQ drain.
The old `dma-started=0` stop path must change before bus mastering is enabled.
Then build one combined MHI candidate; do not flash another mapping-only probe.
No tablet access or charging setting change occurred in this component round.

[Evidence](../../docs/evidence/pcie-msi-20261116.json). Workbench:
`edl_work/pcie-msi-20261116/{host1,native1,pci-host3,runtime2}` and
`lab/records/pcie-msi-20261116`. Mac has matching `lab/pcie-msi-20261116` outputs;
final source snapshot is `source3`. Charging and the full Goal remain incomplete.
