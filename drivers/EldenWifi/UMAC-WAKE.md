# Peach OEM UMAC wake trial

The current first failure is CE3 consumption after the two initial WMI commands.
The preceding real MHI reference trial reached M0 but left CE3 at HP16/TP8 and
BSS0. Holding MHI alone did not resolve it.

The loaded TB322FC Android module provides a distinct contract:

- `/vendor_dlkm/lib/modules/qca_cld3_peach_v2.ko`, SHA256
  `33869cd650843656e216b092809b9cd7327865abb1b6b9dfcd55399abd600d76`.
- `hif_force_wake_request` at ELF text offset `0x452738`, size1300: real
  `pld_force_wake_request_sync`, then write1 at BAR offset`0x3004`; read
  device address`0x01e04040` and require2, with bounded5ms checks.
- `hif_force_wake_release` releases the UMAC request before its MHI reference.

This agrees with the public SM8750 vendor source at
`d50b305f7da9e14715a25120a4ac7b1a4b8b97c3`:
`qca-wifi-host-cmn/hif/src/pcie/{if_pci.c,if_pci.h}`. The
`sun_gki_peach-v2_defconfig` enables both`FEATURE_FORCE_WAKE` and
`DEVICE_FORCE_WAKE_ENABLE`. The ELF contains the actual handshake; config
selection alone is not the evidence. The private original module stays outside
Git. No firmware or device identity is changed.

`UmacWake.inc` implements one explicitly selected, platform-lifetime contrast.
After the original PCI initialization flag, it obtains a real MHI reference,
asserts only this UMAC request, and checks the documented status at most11 times
with ten5ms delays. The existing accessor supplies normal dynamic PCI windowing.
Only2 succeeds;0/1/3 time out and`0xffffffff` returns an error. A failed handshake
clears its request and balances the reference. Successful ownership lasts
through CE cleanup and is released on PCI stop/power-down. This scope differs
from OEM's per-access reference counting and is a trial, not a default port or
proof that UMAC collapse caused the historical failure.

The plain125-object runtime retains its upstream MAC/PHY stride repair and
124 other objects. CE operations, credits, WMI payloads, firmware, IRQ policy,
timeouts and physical recovery stay unchanged. Only the matched runtime and
native`--umac-hold` worker expose this option; the existing owned`ewt=1` intent
and all1023 boot argument bytes remain. The old MHI-only trial is mutually
exclusive and its normal generated source is byte-identical.

37 actual helper scenarios pass ASan/UBSan with MHI/MMIO/clock modeled;
17 component mutation cases check the pair, addresses, status,50ms bound and
preserved menu/return. Scalar iOS17 PCI/native compilation, full native/prelink,
30 Apple executable regions and entry delta7124 pass. PCI120 inherited warnings
and one native shadow warning remain. The first native-interface checker
omitted the real`lx_delay_us` dependency; the failed runtime1 is preserved and
runtime2 checks it explicitly.

```text
python tools/test_wifi_umac_wake.py --cc CLANG --pci-source PLAIN_PCI_C --output NEW_HOST
python tools/build_wifi_umac_wake.py --runtime-build BASE --stride-build STRIDE --llvm LLVM --output NEW_RUNTIME
python tools/build_wifi_net17_native.py --umac-hold --parent-native SERVICE_NATIVE --net-build NET17 --reference-kernel NATIVE --clean-build CLEAN --llvm LLVM --output NEW_WORKER
python tools/build_wifi_net17_kernel.py --parent-build SERVICE_KERNEL --worker-build NEW_WORKER --net-build NET17 --mac-phy-runtime NEW_RUNTIME --clean-build CLEAN --original-kernelcache APPLE --output NEW_KERNEL
```

[Candidate evidence](../../docs/evidence/wifi-umac-wake-20261120.json).
Mac`lab/wifi-umac-wake-20261120/{host1,runtime2,worker1,kernel1,entry1,package1}`;
workbench mirrors under`edl_work/wifi-umac-wake-20261120`.
The signed candidate is`21b9231b3ca96156b9bf7b787f64481d932717048c1ebd745f658453692db930`,
session`b86eb5d73f05fd7b`, floor1738713600/footer0/parent3.
Hardware remains pending: require the real handshake and CE3 progression,
then scan/BSS, association, DHCP and bidirectional traffic before Wi-Fi acceptance.

## First hardware result

The genuine handshake returned0/held1/before2/after2. CE3 progressed to
sw16/write16/HP64/DMA-TP64, then the first timeout was VDEV20488 during
scan-interface setup. No BSS/association/DHCP/traffic acceptance exists. The
WCN9s stop bound expired; no put, network-drain, runtime-stop or physical
DMA/MSI/PERST fence was observed. Resources remained held to typed physical
reset. Physical fastboot and complete stock Android/root/green/original
settings restoration passed. Do not call this a graceful stop or attribute
causation from one contrast.

[Hardware evidence](../../docs/evidence/wifi-umac-wake-hardware-20261120.json).
