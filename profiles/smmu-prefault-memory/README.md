# v163: owned SMMU mapping established on Y700

The native allocator now supplies a verified 128 MiB normal-NC mapping, and
the early owner programs bank 7 / stream slot 8 / ASID 1 before touch starts.
All 32,768 leaves and 66 table pages pass the independent physical graph walk;
context readback and both fault IRQ registrations pass. Touch DMA continues
to transfer and releases normally. The PCIe endpoint remains MEM-only
(`command=2`): **Wi-Fi device DMA, MSI, MHI and networking have not run**.

## Why the earlier attempts stopped

| Candidate | Observed refusal | Applied correction |
| --- | --- | --- |
| [v160](../smmu-memory-detail/README.md) | First segment is 64 MiB for a 130 MiB allocation | v161 accepts descriptor segmentation but retains every 4 KiB PA/PAR continuity check |
| [v161](../smmu-segmented-memory/README.md) | Requested NC alias still has WB attribute `ff` | v162 adds `kIOMapUnique` to avoid the same-task static mapping shortcut |
| [v162](../smmu-unique-memory/README.md) | New alias has PAR `80d`, absent CPU translation | v163 adds `kIOMapPrefault` for the already prepared/wired mapping |

These changes follow the actual XNU `IOGeneralMemoryDescriptor` mapping and
segment implementation. `SegmentSource.py`, `UniqueSource.py`, then
`PrefaultSource.py` derive the explicit variants from the diagnostic base.
No page/attribute, allocation-overlap or release-ownership check is removed.
No fixed RAM address is substituted for an owned allocation.

## Hardware evidence and limits

This run allocated data at `0x8eb800000` and tables at `0x8f3a00000`; these
are observed addresses, not reusable constants. Final data-page PAR was
`44000008f37ffb00`, matching PA and NC attribute `44` for read/write checks.
Context CBAR/CBA2R was `1f300/1`, TCR/TCR2 `80802020/38071`, SCTLR `67`,
TTBR0/1 `10008f3a00000/1000000000000`, MAIR `ff44/0`.

FSR `400` contains FORMAT bits 10:9; fault mask `c00001fe` is zero. Upstream
readback rules allow TCR2's read-only TBI bits and cleared SCTLR ASIDPNE.
The ID0 ATOSNS bit means hardware ATOS is unsupported: mode 2 and zero hardware
translations are intentional. The table walk is not a device DMA test.
Global/context IRQs 97/136 registered with flags `a003`, router 0; fault
injection was not performed. Registered Wi-Fi route and touch coexisted.

Gen3 x2 and Peach major 2 remained valid. IRQ masking, PERST-low quiescence,
typed sync reset, physical fastboot and complete stock SHA restoration passed.
Android/root/green/boot completion, original charging/radio/background-scan
settings and requested sleep were restored. Retaining resources until reset
does not prove a future MHI engine has drained.

## Reproduce

All driver changes and tools live in this repository. The source-built base
comes from [CLEAN-BUILD](../../docs/CLEAN-BUILD.md); the declared parent is its
`--ufs-idle-trial` output, not a downloaded v99 binary. Use the component
builders described in [v159](../smmu-domain-trial/README.md) and the PCIe
component documents, with these explicit selections:

```text
python tools/test_wifi_dma_memory.py --prefault --output <new-host-output>
python tools/build_wifi_dma_memory.py --prefault --clean-build <base> --reference-kernel <parent-native> --llvm <llvm-bin> --output <new-memory-output>
python tools/build_smmu_domain.py --clean-build <base> --memory-build <new-memory-output> --selection-build <selection> --route-build <route> --reference-kernel <reference-native> --llvm <llvm-bin> --output <new-domain-output>
```

The SMMU binding's early guard is resolved in the final kernel. Build the WCN
provider with `--smmu-domain`, the PCIe native worker with `--smmu-build`, and
pass both to `build_pcie_root_kernel.py` with all declared root/power/WCN/
endpoint/route dependencies and
`--prefault-memory --unique-memory --segmented-memory --memory-detail`.
Then qualify the kernel using `audit_pcie_kernel_hooks.py --endpoint --smmu`.
Entry conversion, boot packaging and audit use the resulting `--wcn-report`
and `--bt-runtime`. The native contract is included here. Do not flash a raw
kernel. This round rebuilt components and the complete kernel and package;
it did not repeat an entire empty-directory base build.

Host ASan/UBSan: 17 allocator/lifetime cases, 447,346 checks and 14 table
cases. The predecessor reproduces the missing prefault failure. Kernel
services/cache/PAR are modeled in those tests. Five existing native objects
and 16 components are integrated; core, other archive members, initializers,
30 Apple executable regions and the 7,124-byte entry relation are preserved.
The 1,019-byte menu keeps countdown, fallback and return guards.

Captured acceptance can be rerun with
`tools/assess_pcie_root_capture.py --smmu --run <run> --audit <boot-audit> --output <new-report>`.
`tools/test_pcie_root_capture.py` with the same flags plus a new output
directory rejects 40 rehashed mutations, including wrong cache/TTBR/fault,
missing IRQ or route, broken touch transfers and incomplete restoration.

- Raw kernel: `f823af26a3a64e796707856901a3f2e189b136af8a85208a49cf45cdc885b150`.
- Signed image: `59d0510575f6570603373ecdf49289e797c32191e1f56a3d2ab34e3d436f2bec`.
- Session: `c583623b4517c495`; rollback/footer/parent: `1738713600/0/3`.
- Capture: 145,603 bytes, `3902d9205ebd0a56f87cdf19a6289b7c60919bc7460e54cc17094de4acf4974a`.
  Maximum reported drops 0; no reconnect/discontinuity, no post-disconnect counter.
- [Consolidated evidence](../../docs/evidence/smmu-prefault-v163-20261116.json).

Workbench: `edl_work/smmu-prefault-v163-20261116/{memory1,native2,kernel2}`,
`edl_work/smmu-boot-v163-20261116/package1` and
`edl_work/live-smmu-v163-20261116`. Mac has matching directories under `lab/`;
final build sources are `smmu-prefault-v163-20261116/source2`.
Initial native1/kernel1 outputs precede the context log and are not the flashed
artifact. Historical failed runs and their hashes remain unchanged.

Next connect the owned DMA arena and runtime callbacks, MSI ownership and
real stopping/draining, then MHI/Peach/QMI and actual scan/association/traffic.
Do not repeat selection or mapping-only trials. Charging and the whole
peripheral Goal remain incomplete; the device is restored to stock Android.
