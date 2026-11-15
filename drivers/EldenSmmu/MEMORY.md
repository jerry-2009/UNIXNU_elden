# Owned Wi-Fi DMA memory and domain selection

The real IOKit allocator, upstream page-table code and read-only bank/ASID
selector compile for ARM64/iOS17. Host fault tests run the actual methods with
physical mappings/cache/IOKit services modeled. [v159](../../profiles/smmu-domain-trial/README.md)
then ran the selector successfully on Y700 and entered the allocator, which
refused with-71 before SMMU writes. The full build/boot and return are verified;
allocation and the SMMU domain are not accepted. Investigate exact segment/PAR
values next. ID0.ATOSNS forbids hardware translation queries here; use audited
tables and eventual real DMA evidence.

## Memory and tables

`DmaMemory.cpp` requests130MiB of physically contiguous, mapper-bypassed kernel
memory, retaining an aligned128MiB data range, plus a separate66-page table
pool. Both descriptors are prepared and held. Every4KiB page is checked through
`getPhysicalSegment` and CPU read/write address translation. Initial mappings
must be normal WB and the complete physical allocations must not overlap.

After zeroing and clean/invalidation, data gets a normal-NC write-combined CPU
mapping. Its pages must match the owned PA range and PAR attribute0x44. The
original cached data mapping is no longer accessed. Tables remain cached and
are cleaned before publication and independently walked through their actual
mapping. No fixed physical memory or device-memory mapping of RAM is used.

`DmaTables.c` maps a32-bit IOVA range starting0x10000000 onto128MiB using32768
native4KiB leaves and66 table pages. Output width is decoded from supplied IDs;
the known0x5111 caps give36 bits. Leaves are RW, normal-NC, inner-shareable and
non-executable. IDs and ASID passed to these helpers are not ownership proof.

`claimForContext` records owner/epoch before hardware can walk tables. Afterwards,
destruction requires a same-owner/epoch callback proving DMA stopped and the
context/translations withdrawn. Failed IOKit `complete` is uncertain: remaining
references stay held, further cleanup does not repeat the call, and the object
cannot be used as a successful allocation. Platform reset is the fallback.

## Upstream and selection

`upstream/` contains ArmSmmu4K builder/context/program/audit/table-memory code at
`83969cd874503e65997ff7639f7dcf3d0a92cd17`. Only identifier, filename and guard
prefixes change to `EldenWifiSmmu4K`, isolating it from the separate GPU work.
Algorithms and original MIT LICENSE are unchanged. `prepare_wifi_smmu.py`
reproduces every file from Git blobs; original/derived hashes are recorded in
`upstream/source.json`. A clean re-export was compared byte-for-byte.
The hash-bound manifest uses explicit CRLF on both hosts and a local Git
attribute preserves those bytes; C sources retain their original line endings.

`Select.c` checks the TB322FC baseline required by touch: global IDs/control/
fault state, all132 SMR/S2CR entries and83 CBAR/CBA2R pairs. It reads implemented
context SCTLR/FSR registers, preserves CB0 bypass, and selects a disabled,
fault-free bank from7 onward. Enabled known AArch64 contexts contribute both
TTBR ASIDs; unknown active formats refuse. Slot7 stays reserved for touch; the
baseline's first Wi-Fi slot is8. Slots128..131 are included.

The selector has no write callback. The native caller must keep a real exclusive
early lease through subsequent programming. Selection is not that lease, a
fault handler, or a route reservation. Native read failures must retain the
reported stage/register/error and prevent programming.

## Verification

- 14 table cases include a complete128MiB build/walk, bad widths, overlap,
  overflow, corrupted descriptors and one-shot build state.
- 13 allocator/lifetime cases and232501 checks cover creation/claim/destruction,
  failed allocation/prepare/map, bad physical extents/cache attributes, overlap,
  denied release proofs and uncertain cleanup. Production methods ran with
  explicit host models for kernel services and ARM cache/PAR effects.
- 1815 selector cases/1645092 checks cover every fallible admission/read,
  occupied ASIDs, faulted banks, foreign slots, CB0 translation and unknown
  formats. MMIO is modeled. All host tests pass ASan/UBSan.
- Seven allocator/table objects have9 remaining imports, all found in the
  actual v158 native kernel. They and the selector compile without warnings,
  FP/SIMD or initialization routines. Previously qualified IOKit vtable offsets
  and emitted PAR/cache instructions are checked; this is not new hardware proof.

Allocator object: `9ecb8671b33639781c0105d29a2493ae44f9d81d455fa6a86e6ab18524c3137c`.
Allocator/table binding: `6bed391205de7edbba579e9f324fa4291e4679c1286d946dfacd9ac25ec31b6a`.
Selector: `9d7254246ef20ad5ae907f45983a553988200736e4b80d2b719f935d0674a5c6`.

## Reproduce and continue

On macOS with Xcode and declared LLVM tools:

```text
python tools/test_wifi_dma_memory.py --output <new-host-output>
python tools/build_wifi_dma_memory.py --clean-build <source-built-unified> --reference-kernel <v158-native.macho> --llvm <llvm-bin> --output <new-native-output>
python tools/audit_wifi_dma_native.py --build <native-output> --output <new-codegen.json>
python tools/build_smmu_selection.py --llvm <llvm-bin> --output <new-selection-output>
```

`test_smmu_selection.py --wsl-distro Ubuntu --output <new-output>` runs the selector
model. The allocator host test needs Clang; the first WSL attempt found no Clang
and stopped before compilation. The successful run used the Mac; both records
remain. No compiler was installed as a workaround.

Next wire the real early provider before UFS/Data publication: exclusive phase
and endpoint-quiescence checks, register maps, selection/allocation, context and
global fault IRQ ownership, real context programming, hardware translation
verification, then immutable route publication. Only then bind the late PCIe/
MHI caller. Real DMA draining, MSI, MHI/firmware and networking still remain.

[Evidence](../../docs/evidence/wifi-dma-memory-20261116.json). Workbench outputs:
`edl_work/wifi-dma-memory-20261116/{host1,native1,selection1}` and
`lab/records/wifi-dma-memory-20261116` (select-host1 and codegen). Mac outputs
are in the corresponding `lab/wifi-dma-memory-20261116` directories. All stage
jobs have ended; existing candidates and GPU worktree remain unchanged.
