# Peach non-MLO VDEV creation

The OEM UMAC trial moved CE3 from HP16/TP8 to HP64/TP64. Its first failure is
VDEV SET_PARAM`0x5008` while creating a scan VDEV, followed by ENCAP/RXDECAP/NSS
failures. This is the next wire-contract audit, not an inference from pdev numbers.

The loaded TB322FC module`33869cd650843656e216b092809b9cd7327865abb1b6b9dfcd55399abd600d76`
contains`vdev_create_mlo_params_size` at`0x54c674`: non-MLO returns4 bytes.
`vdev_create_add_mlo_params` at`0x54c6d8` writes`0x00120000` and advances4:
ARRAY_STRUCT tag18 with length0. Public SM8750 vendor source
`d50b305f7da9e14715a25120a4ac7b1a4b8b97c3` implements the same behavior in
`wmi/src/wmi_unified_11be_tlv.c`, and`fw-api/fw/wmi_tlv_defs.h` declares that
array after TX/RX stream parameters. Even the non-MLO build's fallback emits it.
The original module/disassembly remain private outside Git.

The currently compiled Linux7.0.14 creator allocates/appends the array only
when`is_ml_vdev` is true. `VdevMloArrayPatch.py` adds the missing4 bytes only
for ordinary Peach HW2.0 VDEVs. Other hardware and actual MLO packets remain
byte-identical. No pdev/vdev identifiers, stream counts, command IDs, power,
credit accounting, timeout or CE descriptor changes are made.

20 actual old/new creator scenarios and both exact vendor helper bodies pass
ASan/UBSan. They reproduce the old two-TLV packet versus the required third
empty array, check exact OEM bytes, allocation/send failure ownership, and
the unchanged MLO/other-device stream. Kernel/MHI/firmware behavior is not
modeled as a successful hardware transaction. The initial host1 fixture
omitted Linux`BIT`; host2 supplied it, and the failed test is retained.

One WMI object is rebuilt over the qualified OEM UMAC runtime; the other124
runtime objects remain. WMI632 inherited warnings persist. Native worker is
the exact preceding UMAC worker. Full native/prelink,30 Apple execution regions,
entry delta7124,24 component mutation checks and signed boot qualification pass.
Image`c37cd59d83ce1ff53666094992cd9e42771dd1dca5d1df29ee91f4cbcb6e62b9`,
session`7fde4cc64a53f234`, floor1738713600/footer0/parent3; hardware pending.

```text
python tools/test_wifi_vdev_mlo_array.py --cc CLANG --wmi-source STRIDE_WMI --vendor-repository SM8750 --output NEW_HOST
python tools/build_wifi_vdev_mlo_array.py --runtime-build BASE --stride-build STRIDE --umac-build UMAC --llvm LLVM --output NEW_RUNTIME
```

Compose with the retained`--umac-hold` worker through
`tools/build_wifi_net17_kernel.py`, then the ordinary entry/package audit.
The first UMAC hardware run reached a bounded physical reset without proving
graceful runtime/MSI/DMA shutdown. Do not promote either trial to a daily baseline
until the actual VDEV/scan and complete stop/restoration are qualified.

[Evidence](../../../docs/evidence/wifi-vdev-array-20261120.json).
Mac`lab/wifi-vdev-array-20261120/{host2,runtime1,kernel1,entry1,package1}`;
workbench`edl_work/wifi-vdev-array-20261120`.
