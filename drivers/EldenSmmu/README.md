# Immutable boot SMMU route coexistence

The existing touch route validates the complete captured SMMU baseline: all132
SMR/S2CR entries and all83 CBAR/CBA2R pairs. Creating a Wi-Fi translation in a
previously unused slot/bank therefore makes that exact touch code refuse with
`-16`, even when touch's own route is unchanged. The host test reproduces this
with the actual original `DmaRoute.c` before testing the derived version.

`BootRoute.c` is a small boot-lifetime registry. `TouchSource.py` derives the
touch checker so it accepts exactly the four register words of one registered
Wi-Fi route. Everything else retains the original strict baseline, including
CB0 SCTLR capture, all132 slots, foreign UFS routes and global fault detection.
The frozen touch sources and existing candidates are unchanged.

This is **bookkeeping and consumer integration**, not a native SMMU provider.
It does not reserve a real bank/ASID, install fault handlers, allocate/pin RAM,
write hardware, build tables or prove translation/DMA. Those steps must precede
publication by the future early native provider. No new kernel/boot or device
trial was produced for this component.

## Required ordering

1. During early UFS initialization, before Data/PID1 can start touch, the native
   provider checks real SMMU IDs, existing routes and ownership, chooses an
   unused bank/ASID/slot, owns and publishes its data/table pages, installs fault
   handling and keeps the endpoint physically quiesced.
2. Immediately before the first configuration write, reserve the registry.
   It only admits exact SID0x1401, slot8..131, bank7..82, S2CR=bank and the selected
   ArmSmmu4K native stage1 image's CBAR0x1f300/CBA2R1. These bounds do not themselves
   prove a slot/bank is unused. Boot slots0..6, touch slot7 and banks0..6 cannot
   be registered or overridden.
3. After real programming, context/table/translation checks and register reads,
   commit those observed values. Copying the plan into the commit call is not
   native verification. Any partial/uncertain failure must poison the registry
   and retain resources until reset; there is no retry or replacement.
4. Touch seals the registry before its first snapshot. Empty/ready becomes
   permanently sealed. An in-progress/poisoned producer refuses. A late producer
   cannot add a route after touch has started.
5. The mapping and registration remain immutable through normal operation and
   stopping, until platform reset. Later MHI work must drain real DMA before
   reset; registry membership is not a completion fence or power lease.

Reserve/commit/poison calls belong to the single serialized early provider.
Concurrent consumers only call seal/expected/state. Acquire/release publication
keeps the immutable register record consistent. This avoids admitting arbitrary
foreign changes or making a touch frame race an in-progress SMMU update.

## Source findings for the next native stage

Sources are checked by `audit_smmu_boot_route_sources.py`:

- ArmadaOS TB322FC Linux `6f97250ead155fc3b980856323e99a4623dae73d` sets both PCI
  streaming/coherent DMA masks to36 bits. Sheng's older32-bit comments must not
  be presented as this chip's actual limit. A32-bit IOVA aperture remains a
  possible compatible design, subject to real mapping proof.
- The retained Y700 ID2=0x5111 decodes36-bit input/output/upper sizes. Re-read
  actual IDs when creating a native domain; do not copy a48-bit output setting.
- ArmSmmu4K `83969cd874503e65997ff7639f7dcf3d0a92cd17` encodes CBAR0x1f300 for its
  translating context. The inherited bypass bank's0x1f000 is preserved. The
  different bypass attributes are intentional, not interchangeable constants.
- The fixed Qualcomm SMMU source documents firmware substitution/ignoring of
  BYPASS/FAULT writes. Do not replay the opaque unused readout0x0300006e or assume
  a generic FAULT write took effect. Match the actual platform and read back.
- The retained stock FDT lists113 IRQ entries at apps-smmu0x15000000. This is
  not113 implemented banks; the ID1 count governs. Global SPI65 and the first
  context entries97..105 are recorded, not activated here.
- Sheng's current Wi-Fi method owns a RAM arena behind an SMMU mapping. Its
  legacy storage integration warns about late stream-register access. The
  Elden provider should run before storage/Data publication, not add SMMU
  configuration to the late v158 worker after touch has sealed.

The candidate must integrate the registry **and** derived `DmaRoute.o` together,
with exactly one registry provider. Add the real early producer only after its
ownership, fault handling and translation prerequisites are implemented.

## Verification and reproduction

122 modeled boot/route scenarios and11494 checks pass ASan/UBSan: original
rejection, unchanged baseline, registered coexistence and detach, every foreign
register mismatch, CB0/UFS protection, invalid identities, poison, late install,
and100 reserve/seal races. MMIO is modeled. The initial test compilation caught
misleading indentation; the failed output is retained and the final test passes.

ARM64/iOS17 `BootRoute.o`98fa93ae and derived `DmaRoute.o`58380437 compile without
warnings, FP/SIMD or initialization routines. The relocatable bindingf86a4733
resolves both consumer calls and has no external imports. No complete kernel or
physical SMMU/IRQ/DMA acceptance follows from this component build.

```text
python tools/test_smmu_boot_route.py --wsl-distro Ubuntu --output <new-host-output>
python tools/build_smmu_boot_route.py --llvm <llvm-bin> --output <new-native-output>
python tools/audit_smmu_boot_route_sources.py --linux-repository <tb322fc> --smmu-repository <ArmSmmu4K> --sheng-repository <sheng> --output <new-source-audit>
```

The native compiler is macOS/Xcode. Source audit optionally accepts `--stock-fdt`
and verifies its full hash; that private input is not published or required for
compilation. [Evidence](../../docs/evidence/smmu-boot-route-20261116.json).
Workbench records: `lab/records/smmu-boot-route-20261116/{host2,source-audit1}`;
native output: `edl_work/smmu-boot-route-20261116/native1`.
Mac: `lab/smmu-boot-route-20261116/native1`.
