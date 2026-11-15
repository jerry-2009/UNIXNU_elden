# Owned Wi-Fi DMA arena — component ready, native integration pending

The [native adapter](../EldenSmmu/DMA-NATIVE.md) now compiles with real kernel
locks and the qualified SMMU memory provider. Its callbacks are not yet called
by the PCIe/MHI worker; no new device DMA or full-kernel acceptance is implied.

`DmaArena.c` adapts the split/coalesce allocator and size-based bus alignment
from Sheng's `package/WifiProbe.cpp` at
`e8937177309d88c93b305a57bad147fd5fac8a86`. Its complete BSD-2-Clause-Patent
notice is retained in [LICENSE.sheng](LICENSE.sheng). No Sheng register,
physical RAM reservation, firmware or IRQ number is copied.

The intended backing is the [v163 owned NC mapping](../../profiles/smmu-prefault-memory/README.md).
Initialization receives that mapping, a power-of-two IOVA window, separate
metadata and an owner/epoch. It does not establish or verify the SMMU itself.
The first 4 KiB remains the MSI sink. Small allocations use 64-byte rounding;
page-size allocations are rounded to pages and aligned to the next power of
two, preserving the upstream MHI image/firmware-region requirement. Requests
are bounded before rounding. Allocation zeros the NC bytes before returning.

Changes relative to the upstream helper:

- `dma_map` validates the complete requested range within a live allocation.
  The upstream mapper only tests the starting address within the whole arena.
- Free accepts only the allocation start; nonzero length and bus metadata
  must match. Zero metadata remains supported for the real QRTR/MHI callback.
- Owner/epoch mismatch refuses access. Stop prevents new allocation/mapping;
  range validation for ordering existing DMA and exact free remain available
  while draining. A stopped arena cannot be reinitialized.
- Metadata and CPU ranges cannot overlap. Exhausted metadata refuses allocation
  without changing the partition. Adjacent free ranges are coalesced as upstream.

Every call is serialized by the caller. The native adapter must supply that
serialization, current SMMU/power admission and a real NC ordering barrier.
This core does not supply a lock, IRQ handler, cache operation, mapping-unmap
counter or hardware drain. In particular, `live == 0` does **not** prove MHI
has stopped; the backing and metadata must remain alive until independently
qualified shutdown/reset. Raw pointers cannot identify a stale use after the
same address has already been reallocated; runtime completion ownership still
has to be correct.

## Validation and build

The actual C core was compared with the three extracted, fixed upstream
functions under ASan/UBSan: 4,000 allocation/free steps preserve addresses,
partition sizes and usage. It additionally checks zeroing, large image
alignment, exhaustion, full-span validation, reserved sink, overflow, invalid
metadata, epochs and stopping. Kernel services/hardware are not involved.
Final host evidence contains 1,554,917 checks, primarily partition invariants.

The native ARM64/iOS17 object compiles with zero warnings, no FP/SIMD or
initializers. Its six exports and remaining `_bzero`/`_memmove` imports were
checked against the v163 native kernel. Initial native1 was rejected because
the checker expected `_memset`; Apple Clang emitted `_bzero`. The final
checker verifies the actual zeroing symbol against the kernel. That failed
attempt is retained. Before host2, stop semantics were corrected to allow
range validation of existing buffers during drain, while still rejecting new
maps/allocations.

```text
python tools/test_wifi_dma_arena.py --sheng-repository <fixed-sheng-clone> --output <new-host-output>
python tools/build_wifi_dma_arena.py --llvm <llvm-bin> --reference-kernel <qualified-native.macho> --output <new-native-output>
```

Object: `b9b5a93bbfa252d5d536527ef9c8f7d52c1349cd9f93ab3250fd9afb6e7c7791`.
[Evidence](../../docs/evidence/wifi-dma-arena-20261116.json).
Final Mac: `lab/wifi-dma-arena-20261116/{source2,host2,native2}`; workbench
copies: `edl_work/wifi-dma-arena-20261116` and `lab/records/wifi-dma-arena-20261116`.
This is not a new kernel, signed image or hardware/DMA acceptance.

## Next integration

1. Expose the qualified SMMU memory view only to the real PCIe/WLAN owner;
   connect the arena and `lx_platform` callbacks from the fixed Ath12k ABI.
2. Bind the MSI receiver and IRQ using TB322FC stock/Linux evidence. Sheng's
   SPI 141 is a method reference, not an Elden board constant.
3. Check config/MMIO errors and readbacks. The fixed `nw_pci.c` MSI helper
   currently ignores config callback errors; `pci_set_master` is a no-op, so
   board-side enable/withdrawal must be explicit and qualified.
4. Add actual MHI/completion/IRQ drain within the recovery deadline. Retain
   memory and power to reset on uncertainty. Only then enable bus mastering,
   bind the real QMI consumer and start the firmware/runtime.

v163 remains the latest hardware candidate. No tablet operation or new
charging command occurred during this component work.
