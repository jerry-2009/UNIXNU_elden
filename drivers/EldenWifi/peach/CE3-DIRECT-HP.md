# CE3 shadow versus direct producer notification

The UMAC trial progressed to16 CE3 descriptors once, then the following VDEV
trial returned to the same HP16/TP8 first-PDEV failure. A successful UMAC
handshake therefore does not establish a stable solution. The candidate below
tests the unresolved producer-notification path with one narrow contrast.

The exact SM8750 OEM HAL exposes`hal_srng_setup(ignore_shadow)` and uses
`SRNG_SRC_ADDR(srng,HP)` directly in that mode. The existing Linux function
`ath12k_wifi7_hal_set_umac_srng_ptr_addr` uses the same direct path on hardware
without shadow registers. The board/vendor sources agree on CE base`0x1b80000`,
engine stride`0x2000`, R2 HP offset`0x400`: CE3 HP`0x01b86400`. The original
QMI config maps shadow index34/offset`0x984` to this address; hardware showed
software notification16 but DMA tail8. Neither that observation nor CSR0/0
alone proves whether the shadow notification arrived.

`Ce3DirectPointerPatch.py` selects the original direct-HP assignment only
for Peach HW2.0/source ring67/exact R2 address`0x01b86400`. The existing HAL
access-end writes then use the unchanged PCI dynamic window/accessors.
No extra head/tail write, speculative barrier, fake completion, credit or
timeout is introduced. CE2 and all other source/destination pointers retain
their exact behavior; the firmware's shadow configuration remains unchanged.
This is an explicit candidate, not a default or a proven fix.

144 actual old/new pointer-selector cases pass ASan/UBSan. These execute the
production selector while treating register memory as symbolic addresses,
not hardware. One`w7_hal.o` rebuild retains the other124 runtime objects,
the UMAC option, and the source-tested VDEV array fix. All imports/exports,
rename/code/data, scalar iOS17 and no initializer checks pass. HAL71 warnings
are recorded. The first build resolved quoted`hw.h` outside the original
wifi7 directory and was rejected by the dependency audit; runtime2 preserves
the original quoted namespace with`-iquote`, and its dependency set matches.

Complete native/prelink,30 Apple executable regions, entry delta7124,
30 component mutation tests and signed boot audit pass. Candidate
`771f524042a0c58406d22ac077bbb7fb0e4b64f0dcb8461c1cc3718594351639`,
session`4e3c23ffa069941e`, floor1738713600/footer0/parent3; hardware pending.

```text
python tools/test_wifi_ce3_direct.py --cc CLANG --hal-source WIFI7_HAL_C --output NEW_HOST
python tools/build_wifi_ce3_direct.py --runtime-build BASE --parent-build VDEV_RUNTIME --llvm LLVM --output NEW_RUNTIME
```

Use the existing UMAC native worker with the new runtime through
`build_wifi_net17_kernel.py` and its full entry/package qualification.
Acceptance needs actual CE3 completion and scanning/BSS, followed by real
physical fence and complete stock restoration. Association/DHCP/traffic remain
unaccepted. Do not retry the previous interrupted response-trace candidate.

[Evidence](../../../docs/evidence/wifi-ce3-direct-20261120.json).
Mac`lab/wifi-ce3-direct-20261120/{host1,runtime2,kernel1,entry1,package1}`;
workbench`edl_work/wifi-ce3-direct-20261120`.
