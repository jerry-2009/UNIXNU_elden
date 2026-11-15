# Native PCIe control transport — compiled, MHI execution pending

The explicit `TransportNativeSource.py` variant now calls the real DMA bind,
endpoint config and MSI providers from the existing PCIe worker, after BAR /
Peach / WLAN epoch confirmation. It uses the worker's held config and DBI
maps, native `armcpu_spi_attach` / `armcpu_spi_mask`, and IRQ-safe thread wake.
The old root/endpoint variants stay unchanged. `ewt=1` additionally requires
the existing endpoint and early-SMMU intents; no standalone boot package was
created, and these callbacks have not been executed on the tablet yet.

## Config access and lifetime

`Config.c` discovers bounded, noncyclic MSI and PCIe capability lists on the
actual `17cb:110e` endpoint with MEM-only command2. Reads support the existing
Ath12k convention for PCIe-relative offsets. Writes are restricted to MSI
control/target/data/mask and Device/Link Control. MSI targets must match the
owned sink. Capability identity/width/MMC fields are preserved. The upper
Device/Link Status halves are written as zero instead of accidentally clearing
W1C bits during a lower-half update.

Bus master cannot be changed by the generic config callback. Its dedicated
API checks a separate readiness callback, marks a possible enable *before*
writing, and verifies command readback while preserving PCI Status. The native
readiness callback currently returns `-95`: **the real MHI execution/drain
provider is not implemented yet**, so enabling bus mastering would be premature.
An attempted master operation never qualifies as drained merely because the
command bit was subsequently cleared.

Normal operations require current root/recovery/power admission. Cleanup uses
the same retained native owner/maps after WLAN admission is withdrawn; it
permits MSI disable and the dedicated master-disable operation. It cannot set
new target addresses. The worker must already be terminal before the current
parent quiesce callback enters cleanup. MSI shutdown and entered-handler
completion precede PERST assertion. Snapshot queries use a try-lock gate;
cleanup acquires the same gate within its deadline, avoiding concurrent reads
of mutable config/receiver state. Mappings and IRQ cookies remain until reset.

This is still the no-device-DMA control variant. The inherited reset-only
comments/stop ordering in the parent source are historical; the final MHI
variant must replace that contract and delay SMMU fault-IRQ withdrawal until
its real drain is complete. It must not reclassify this control-only result
as a successful MHI stop.

## Verification

74 host scenarios / 315 checks run the actual native transport callbacks and
the actual config/MSI cores with modeled physical services and DMA provider.
They cover every injected setup failure, wrong owner/IRQ route/capability list,
W1C preservation, invalid MSI target, generic bus-master refusal, cleanup after
power-epoch withdrawal, missing drain proof and busy status/stop gates.
The initial fixture's static definitions conflicted with the real DMA header's
C linkage; that fixture-only compile failure was corrected and retained.

Config and the native worker compile ARM64/iOS17 with zero warnings, FP/SIMD
or initializers. Eleven supplied objects/bindings (including the real DMA/SMMU,
WCN, root, endpoint, config and MSI providers) link together. Their 72 remaining
imports all exist in the v163 native reference kernel. This relocatable link
is not a complete XNU kernel, flashable image or hardware acceptance.

- Config object: `0e822d7b5072f5ae3a7e47466baca5feb383703772dde1b41a0cf998e5ff29c4`.
- Native worker: `8dd0e9e98d0ef5500498503443ef0262f6a82880fc8eb29eafb71a94095fb816`.
- Binding: `6ae33c50e59745ad51909c80b68f45d3d603f9e43750d57c42978610ee04166f`.

```text
python tools/test_pcie_transport.py --output <new-host-output>
python tools/build_pcie_config.py --llvm <llvm-bin> --output <new-config-output>
```

Use `build_pcie_native.py` with its declared root/power/WLAN/WCN/endpoint/DMA
SMMU inputs plus `--config-build`, `--msi-build` and `--reference-kernel`.
The explicit transport requires the 12-component DMA-capable SMMU binding.
The normal full-kernel recipe has not yet been extended/qualified for this
transport, so do not feed it this object as the old mapping-only candidate.

## Original firmware evidence

A read-only capture of this TB322FC's `cnss2.ko` matched the device's own SHA:
`fd8e10b29cf48d372e2c48dafc5e610e43801043f6e8fda21b6085c05df5bec4`.
Its `cnss_pci_load_m3` selector explicitly includes PCI110e in mask64480 and
selects `phy_ucode20.elf` for major2. The generic `m3.bin` literal belongs to
a different branch. Relocations lead from that selector through the prefix
and firmware-request helpers. The major field's writer and original diagnostic
format identify it as the reported device major version.

`tools/analysis/audit_oem_wifi_m3.py --module <stock-cnss2.ko> --output <new-json>`
verifies the exact module, instructions and relocations. This supports mapping
the Linux API's M3 request to the original `image/peach/phy_ucode20.elf` asset
already listed in `package/EldenWifiFirmwareInputs.h`; it is not a new firmware
download result. No proprietary module/firmware binary is added to Git.

## Next

Complete the bounded original-firmware cache, bind the real Linux QMI consumer,
and run the frozen MHI/Peach stack through these callbacks. Add cancellation,
actual MHI reset/stop evidence, PCI master disable and IRQ drain before allowing
master enable. Then qualify a complete combined kernel/package and run one
bounded hardware MHI test with the existing stock-recovery supervisor.
No additional mapping-only or receiver-only hardware trial is needed.

[Evidence](../../docs/evidence/wifi-transport-20261116.json). Mac:
`lab/wifi-transport-20261116/{source2,host2,config1,native1}`; workbench has
matching `edl_work/wifi-transport-20261116` and `lab/records/wifi-transport-20261116`.
v163/stock remain the latest hardware/restoration evidence. Only read-only
Android module inspection occurred; no charging settings, boot or partition
writes. Charging and the whole peripheral Goal remain incomplete.
