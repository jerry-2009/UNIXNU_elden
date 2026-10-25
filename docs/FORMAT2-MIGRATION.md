# Format 2 migration record

Migration target: <https://unixnu.com/zh/porting/migration>

Date: 2026-10-25

## Result

`board.toml` now declares device schema 2 and selects:

- ARM64, SM8750 and `ipados-17.7.11-21H461` profiles;
- `ArmDTPlatform`, `ArmCpu`, `SoftwareAES`, `XnuPrelink` and `DarwinBoot`;
- ordered ARM64, SoC, OS and device configuration fragments;
- ordered ARM64, SoC, OS and device XNU patch series;
- `dts/elden.dts` with `soc/sm8750/dts` as the include path.

The output layout is
`out/elden/ipados-17.7.11-21H461/elden/`, with the resolved tree under that
directory.

## Host validation

The format 2 configuration resolved against UniXNU `main` at
`16e592abee8a550dec8154ed1f38b5ebc4f16213` on 2026-10-25:

- `defconfig` wrote the resolved `.config`;
- `status --json` reported the local SM8750 source, five selected components,
  and 56 ordered XNU patches;
- `tree` assembled the format 2 output tree;
- `porting-record.py check` validated all 13 structured areas;
- `dtc` 1.8.1 compiled `dts/elden.dts` and the resulting DTB round-tripped with
  the expected CPU, PSCI, GICv3, timer and DRAM nodes.

These are host checks only. They do not change the phase 1 device result and do
not qualify an XNU boot.

## Preserved phase 1 work

The migration does not change the verified phase 1 recipes:

- `drivers/EldenRamDiskDxe/`
- `patches/overlays/`
- `scripts/build_phase1.py` and the other phase 1 build scripts
- `package/unixnu.toml`
- `out/` artifacts and their recorded hashes

The `UniXNU` build dependency remains pinned to the commit that produced the
accepted phase 1 image. A separate current UniXNU checkout is used for format 2
configuration validation.

## Source ownership

No public `UniXNU-sm8750-common` repository exists at migration time. The
committed `soc/sm8750` directory therefore provides the required shared profile
shape:

- CPU MPIDR topology, PSCI conduit and architectural timer frequency;
- GICv3 distributor/redistributor ranges and stride;
- empty shared XNU patch series;
- SoC-specific configuration fragment.

It contains no UFS, display, GPU or touch implementation. `feeds.toml` marks
that source as local. Before publication, move the profile into the shared
repository, pin its reviewed commit and update `unixnu.lock`.

## Remaining hardware inputs

The first board DTS deliberately exports only the resources required by
`ArmDTPlatform` and `ArmCpu`:

- one contiguous 2 GiB DRAM window at `0x80000000`;
- eight declared MPIDR values from `0x0` through `0x10100`, with secondary
  startup still opt-in;
- GIC distributor `0x16000000 + 0x10000`;
- GIC redistributors `0x16080000 + 0x200000`, stride `0x40000`;
- timebase `19,200,000 Hz`;
- PSCI SMC conduit.

Still required before a complete format 2 release:

- a full live memory map and reserved-memory ownership;
- the reviewed SM8750 shared SoC repository and commit;
- kernelcache/ABI inputs and the unique per-device seed;
- UFS controller, PHY, clocks, power domains and SMMU ownership;
- DPU/DSI/panel/backlight description;
- Novatek SPI touch description;
- the phase 2 payload size and boot image format.
