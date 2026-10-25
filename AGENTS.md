# Device agent guide

This repository owns the Lenovo Legion Y700 Gen 4 (`elden`, TB322FC)
board description, peripheral wiring, component selection, firmware inputs
and packaging. It uses UniXNU device schema version 2.

## Read first

Read this file, `README.md`, `porting.toml` and `board.toml` before changing
the port. Then read the applicable UniXNU documentation:

| Task | Required reading |
| --- | --- |
| Every port | [Porting](https://unixnu.com/zh/porting/), [device repository](https://unixnu.com/zh/porting/device-repository), [component catalog](https://unixnu.com/zh/reference/components) |
| Migration | [Migrate an existing repository](https://unixnu.com/zh/porting/migration) |
| Hardware | [Device tree](https://unixnu.com/zh/porting/device-tree), [device-tree matching](https://unixnu.com/zh/drivers/device-tree-matching) |
| Kernel | [Source and patches](https://unixnu.com/zh/xnu/source-and-patches), selected OS profile |
| Images | [Prelink](https://unixnu.com/zh/concepts/prelink), [payload](https://unixnu.com/zh/concepts/payload), [UEFI](https://unixnu.com/zh/porting/uefi-firmware) |
| Verification | [Building](https://unixnu.com/zh/building), [bring-up](https://unixnu.com/zh/porting/bring-up) |

## Work rules

- Keep verified phase 1 firmware and RAM-boot behavior working.
- Put board wiring and device policy in `dts/elden.dts` and `board.toml`.
- Put shared SM8750 resources in the selected SoC source. `soc/sm8750` is a
  temporary local profile until `UniXNU-sm8750-common` is published.
- Select reusable implementations by canonical component ID from UniXNU
  `components.toml`; do not rename runtime identifiers.
- Replace `local = ...` in `feeds.toml` with a reviewed commit before release.
- Update the relevant `porting.toml` area with every code change.
- Never commit device identifiers, trust caches, seeds, backups or signing keys.
- Do not add automation that flashes, erases, formats, changes slots or edits
  the GPT. Device tests remain owner-operated `fastboot boot` RAM boots.

## Validation

Run from a current UniXNU checkout:

```sh
./unixnu defconfig elden_defconfig -D ../UniXNU-elden
./unixnu status --json -D ../UniXNU-elden
./unixnu tree -D ../UniXNU-elden
python3 scripts/porting-record.py check --device ../UniXNU-elden
```

Compile the hardware DTS and run the existing phase 1 artifact checks:

```sh
dtc -I dts -O dtb -i soc/sm8750/dts -o /tmp/elden.dtb dts/elden.dts
python3 scripts/make_payload.py --verify-only
python3 scripts/verify_artifact.py --fd out/SILICIUM_UEFI.fd --image out/elden-phase1.img
```

Record host and device evidence separately. A menu boot does not prove XNU,
storage, display or touch support.
