# CPU-only BAR and Peach identity transaction

`Endpoint.c` continues a successful cold root with BAR sizing, assignment,
outbound memory routing and a real chip-version read. The component passed
295 host scenarios/45259 checks with ASan/UBSan and compiles as ARM64/iOS17
object `91695536406cb5d9e90e286c4f2d7f71eb721c4fd639eb08b264c759015ab921`.
It has one export, no imports/FP/SIMD/initializers and zero warnings.
**Native BAR mapping, worker integration, complete kernel and hardware testing
of this component remain pending.** v157 root-only remains the hardware baseline.

## Sources and board differences

The flow follows Sheng `endpointProbe` at commit
`24aab96163799cb1db083d94539a5eefc07e0475`. Board and Peach fields use ArmadaOS's
TB322FC Linux `6f97250ead155fc3b980856323e99a4623dae73d`, not TB321FU/SM8650.
`audit_pcie_endpoint_sources.py` checks the exact Git objects, DesignWare iATU
layout, chip address masks and the optional original FDT against its full SHA.

The stock FDT memory aperture is `[0x40300000, 0x44000000)` (61MiB), whereas
the fixed Linux DTS extends it to `0x64000000`. The code uses the stock range,
which is their intersection. Public facts are in `endpoint-facts.json`; the
private original FDT is not required to build. The 2MiB BAR0 and32KiB BAR2
expectations come from stock resource caches and must still be discovered
through actual config reads before this transaction accepts them.

Peach's remap register is `0x3278`, versus Sheng/WCN7850's `0x310c`.
Version register `0x01b00000` uses window bits24:19, BAR offset0x80000 plus
bits18:0, with enable bit30. The dynamic selection preserves static fields
and is restored/read back afterwards. Version bits11:8 must equal2.

## Contract and order

Zero-initialize the endpoint once. The caller must serialize the entire
transaction, all config/BAR users, and stopping against the same root/epoch.
The existing root admission callback remains authoritative on every access.
There is no success stub for native mapping or root power.

1. Recheck the live root/epoch, actual endpoint ID, type0 header, disabled
   I/O/MEM/bus-master and ROM decode, and unused outbound iATU region1.
2. Probe each BAR with memory decoding off. Read/probe/restore both halves of
   a64-bit BAR; reject I/O, unsupported type, malformed masks, unexpected
   resources and sizes. Restore original values with readbacks.
3. Assign aligned, nonoverlapping addresses inside the stock aperture. With
   the expected sizes BAR0 is0x40400000 and BAR2 is0x40600000. This deliberately
   does not claim to reuse Android's cached BAR2 assignment at0x40300000.
4. Configure outbound region1 and root memory base/limit, verify all fields,
   and bound enable confirmation to1000µs/100 iterations. Region0 remains CFG0.
5. Map exactly BAR0 through the native callback. Recheck identity and assigned
   BARs after mapping, catching a reset that clears BARs before enabling decode.
6. Set endpoint **MEM only**. Command writes preserve unrelated command flags,
   write zero PCI W1C status bits, and cannot set I/O or bus master. Read the
   chip version via the Peach window, restore that window and recheck identity,
   command and BAR assignments before publishing `Identified`.

No DMA buffer, SMMU context, MSI target, MHI command or firmware is touched.
CPU reads of endpoint registers do not require granting endpoint DMA rights.
Partial/uncertain failure becomes Held; mappings and power remain until reset.
No failed object may restart. A failed read does not publish an identity.
`Identified` is not QMI readiness by itself: the native caller still must pass
the actual PCI ID and chip-major to the existing confirmed-epoch power API.

## Reproduce and integrate next

```text
python tools/audit_pcie_endpoint_sources.py --linux-repository <tb322fc-clone> --sheng-repository <sheng-clone> --output <new-audit>
python tools/test_pcie_endpoint.py --wsl-distro Ubuntu --output <new-host-results>
python tools/build_pcie_endpoint.py --llvm <llvm-bin> --output <new-native-results>
```

The native build uses macOS/Xcode; omit `--wsl-distro` for a native POSIX host
test. Outputs are retained, not overwritten or deleted. This is a standalone
component build and not a signed boot recipe.

Tests run the actual transaction with modeled MMIO/map/time providers. They
inject every fallible callback, cover32/64-bit BAR forms, failed readbacks,
busy region, stale epoch, lost assignments, malformed masks, stalled clocks,
wrong/allFF versions, command W1C handling and remap restoration. They do not
prove physical register access or native scheduling/quiescence.

Next connect native BAR mapping and read/write callbacks to the root worker,
keep the cold no-DMA stop contract, extend terminal status and wire real epoch
confirmation. Rebuild/review the full candidate before one root+BAR+identity
trial. DMA/MSI/MHI need their separate ownership and drain implementation.

[Evidence](../../docs/evidence/pcie-endpoint-20261116.json). Workbench records:
`lab/records/pcie-endpoint-20261116/{host3,source-audit2}` and
`edl_work/pcie-endpoint-20261116/native1`. Mac component build:
`lab/pcie-endpoint-20261116/native1`. Earlier test outputs are preserved.
