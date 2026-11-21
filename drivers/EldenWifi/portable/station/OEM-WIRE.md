# Y700 station command format

The latest full station capture proves TCL consumed all three descriptors
(HP=TP=24 words), but WBM2SW0 remained empty. It does not prove RF TX/ACK.
Hardware mode returned status0/configured1; the HIF wake reference is held.
See [actual capture](../../../../docs/evidence/wifi-station-tx-hardware-20261121.json).

The loaded TB322FC module is `qca_cld3_peach_v2.ko`, SHA256
`33869cd650843656e216b092809b9cd7327865abb1b6b9dfcd55399abd600d76`.
Its actual disassembly confirms portable donor2438556c has older station
command tails. Vendor source d50b305f explains the same field order:

| Command | Fixed donor | Loaded OEM | Derived change |
| --- | --- | --- | --- |
| VDEV_START | 112-byte fixed body; NOA array | 128-byte body; MLO12 structure and partner array | Append zero fields and disabled non-MLO structure/tag0x3d6 |
| VDEV_UP | 32-byte body | 36-byte body | Append flags0 |
| PEER_ASSOC | 244-byte body; four empty struct arrays | 248-byte body; MLO68 structure; final TID-to-link array | Append assoc_flags0, disabled structure/tag0x3d0 and empty final array |

The sizes come from module functions `send_vdev_start_cmd_tlv`@0x1360e4,
`send_vdev_up_cmd_tlv`@0x136d18, `send_peer_assoc_cmd_tlv`@0x138bb0,
`vdev_start_add_mlo_params`@0x54c7d4, `peer_assoc_add_mlo_params`@0x54cb10
and `peer_assoc_add_tid_to_link_map`@0x54d194. Vendor WMA explicitly leaves
non-MLO flags disabled when no MLD context exists. This is an unconditional
OEM envelope with disabled fields, not an invented MLO connection. The
header comments allow empty MLO arrays, while this loaded host helper always
emits its disabled structure; the concrete binary is authoritative here.

Other checks prevent speculative fixes: actual OEM implicit-RBM helper is
only `ret`; TCL0→WBM0 uses RBM5 in its table and descriptors. The eight-word
TCL/WBM sizes match. OEM disables vdev-ID checking for its single-device
bank; the successful donor/Linux enables it. That difference alone is not
proof of the failure, so this candidate keeps the existing bank0x4a04,
metadata, peer search/hash, pdev0, rings and DMA owner unchanged.

`StationWireSource.py` derives only these command envelopes from a SHA-bound
donor codec using a single exact Clang VFS file overlay. Original Git blobs,
previous builds, key/authorization rules, frame payload, board power and
timeouts remain unchanged. Bounded metadata observations report the genuine
peer-association confirmation and EAPOL message numbers; never keys or frames.

```text
python tools/build_wifi_station_wire.py --parent-build QUALIFIED_TX_RUNTIME --llvm LLVM_BIN --output NEW_RUNTIME
python tools/build_wifi_station_kernel.py --parent-build TESTED_SCAN_KERNEL --runtime-build NEW_RUNTIME --native-build STATION_WORKER --core-build STATION_CORE --assets STATION_ASSETS --clean-build CLEAN --original-kernelcache ORIGINAL_21H461 --output NEW_KERNEL
python tools/test_wifi_station_qualification.py --report NEW_KERNEL/result.json --output QUALIFICATION.json
```

`TestStationWire.cpp` checks the actual derived bytes against independently
specified OEM lengths, all legacy/HT rate counts and every truncated buffer.
ASan/UBSan and the scalar ARM64/full native/prelink checks pass. Those are
codec/model/build evidence, not a Wi-Fi hardware success. The next single
full trial checks association confirmation, genuine TX/WBM/ACK, EAPOL2→3→4,
both key completions, controlled port and BSD traffic, plus physical return
and complete stock restoration. WPA2/DHCP/traffic remain unaccepted until
their actual evidence appears. Foundation clean build and this incremental
Wi-Fi chain still have separate reproducibility scope.

Workbench source/disassembly evidence:
`lab/records/wifi-station-tx-20261121/oem-audit`.
Final prepared build: `wifi-station-wire-20261121/runtime2` and `kernel1`.
The initial compile rejected an explicit integer narrowing in the new
metadata observer; it was fixed before any signing or device write.
