# Peach window selection without a local cache

The hardware CE3 startup timeline shows base10001bc0/size8000/ID4/MISCc2,
actual HP/TP8/8 and window40000037 through stage8 (HTT request return).
Before the first PDEV, the register reads become ffffffff while the actual
always-accessible remap control reads40000000. The local driver still expects
window37. The cause of the hardware window change is unproved. The earlier
zero CE3 configuration is therefore not proof of an actual ring reset.

The exact SM8750 OEM source at`d50b305f7da9e14715a25120a4ac7b1a4b8b97c3`
defines`PCIE_REG_WINDOW_LOCAL_NO_CACHE1` in
`qcacld-3.0/configs/default_config.h`. Both OEM HIF and HAL selectors write
and confirm the required window every time under their original lock.
The consumed Linux selector instead skips selection when its local cache
already equals the desired value.

`WindowReselectPatch.py` ports only that established policy for Peach HW2.0.
The existing lock, encoded window value, static bits, iowrite32 and ioread32
stay intact. Other hardware retains its original cached policy. This fixes
the demonstrated software stale-cache defect; hardware Wi-Fi efficacy is
pending. No ring reinitialization, extra barriers, credit/timeouts, pdev or
firmware changes. Retain the original shadow path, UMAC/VDEV repairs and
passive timeline for the decisive hardware trial.

8195 actual old/new selector cases reproduce window0/cache37 with the old
function, then verify exact writes/readbacks, all64 cached/desired values,
non-Peach behavior and static-bit preservation under ASan/UBSan. MMIO is
modeled. One PCI unit/124 runtime objects retained, PCI120 warnings;
unchanged native inspector worker, complete kernel/prelink,30 Apple regions,
entry7124 and41 qualification mutations pass. Signed candidate
`17c7d76afda9e77c3d3937366ee7083b52a0a795566f4250efa3b44ea1362a7e`,
session`f25726514a16d4aa`, floor1738713600/footer0/parent3; hardware pending.

```text
python tools/test_wifi_window_reselect.py --cc CLANG --pci-source UMAC_PCI --output NEW_HOST
python tools/build_wifi_window_reselect.py --runtime-build BASE --parent-build TIMELINE_RUNTIME --umac-build UMAC_RUNTIME --llvm LLVM --output NEW_RUNTIME
```

[Evidence](../../../docs/evidence/wifi-window-reselect-20261120.json).
Mac`lab/wifi-window-reselect-20261120/{host1,runtime1,kernel1,entry1,package1}`;
workbench`edl_work/wifi-window-reselect-20261120`.
Accept only actual CE3 progression/scan and complete physical stop/restoration;
no association, DHCP or traffic claim yet.

## Hardware result

Attempt1 was rejected at PD admission before any Wi-Fi runtime execution.
Same-image fresh attempt2 reached the runtime: window37 is retained at stage9,
but actual CE3 base/size/ID/MSI remain0, MISC80 and the early PDEV failure
persists. This repairs stale selection without solving the whole Wi-Fi fault.
Full physical fence, UMAC release, typed fastboot and stock restoration passed.
[Hardware evidence](../../../docs/evidence/wifi-window-reselect-hardware-20261120.json).
