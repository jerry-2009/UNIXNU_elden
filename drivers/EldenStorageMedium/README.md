# Nonrotating UFS and RAM media

This is the small medium-property delta from ShengUfs
`2f6c7b0d48a37ffd54943cf13d6709bf66564045` and RamBlock
`8732b3e436a65132ffaa82e8ad3e402aab669e60`, adapted to the exact Elden sources.
The transport/queue, root extent, hash authentication, write gate, RAM seed and
memory ownership code remain unchanged.

The helper publishes `Device Characteristics` → `Medium Type` → `Solid State`
before registerService. It clones an existing dictionary, including one inherited
through the service plane, so unrelated vendor properties are preserved. Retained
objects are released correctly; wrong types, allocation/set failure and failed
readback return false and log the missing hint without preventing root boot.
It does not claim RAM is nonvolatile storage or enable seed recycling/swap.

The existing frozen storage header has the same three strings. Public
IOStorageFamily312,315 and337.100.1 have byte-identical DKIOCISSOLIDSTATE handlers.
More importantly, the actual reconstructed21H461 XNU sources were checked against
their source-provider hashes: ioctl0x4004644f initializes the disk's SSD state and
sets MNTK_SSD when the mount query succeeds. Default lower-tier periods are
40/85/200ms for rotating and5/15/25ms for SSD; this is source behavior, not a
measured speedup. Existing spec_open logs allow end-to-end checking without
adding a new probe thread or ioctl caller.

The v149 device run published one512MiB RAM device and two UFS windows, all with
readback solid=1. Existing kernel messages recorded isssd=1 twice for each BSD
unit0/2/4, replacing the corresponding v146 baseline's zeros. Mount flags were
not separately inspected. Root mounting, sync return and complete stock Android
restoration passed. See [profile](../../profiles/storage-medium/README.md).

`tools/test_storage_medium.py` runs the actual helper through10 ownership/failure
cases under ASan/UBSan. `tools/analysis/audit_storage_medium.py` binds public-family
and actual-XNU source evidence; the runtime reader is
`tools/analysis/assess_storage_medium.py`. The source transform is MediumSource.py;
no old source/provider hash is silently changed.

Next: use the audited UFS completion-wait/queue/DMA design, after checking the
earliest modified stage has a qualified watchdog/return path. This property fix
does not implement interrupts, concurrent slots, direct DMA or an auth-page cache.
