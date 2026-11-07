# LUN0/ipados read-only preparation

## Device result, 2026-11-07

The owner photograph of the new source kernel confirms the intended probe10
report: partition ipados, first 0xcd4f700, last 0xed4f7fa, selected LUN last
0xed4f7ff, 4096-byte blocks, SHNGROOT magic and manifest status0/windows2.
Inherited SID60 slot0/CB0 qualification passes without SMMU writes. Panic text
is doubled on screen; values above remove that duplication. This qualifies the
new source load form and root manifest read, not APFS mounting or userland.

The complete 9381609472-byte root image was written and checked by full SHA256,
including another full read after reboot. Android setup, the matching KernelSU
manager and root authorization survived that reboot, confirmed by properties
and the owner entering the desktop. Older account/Wi-Fi restoration remains a
separate task with the original encrypted backups preserved.

Android currently reports MemTotal15517668KiB and fragmented physical RAM,
including an approximately13GiB high region at0x8c0000000..0xbffffefff. The new
menu includes the existing EFI read-only memory report to determine actual
allocatable ranges; do not advertise a flat16GiB from the low base.

The owner has created a dedicated 128GiB partition at LUN0 LBA
215283456..248838138 (4096-byte blocks). Android userdata retains its original
start and ends immediately before it. Partition write/readback evidence is in
the owner's Y700 work repository; no backup, device identity or signing key is
committed here.

The existing root-check kernel was verified on the device against
LUN4/ARMADA_BACKUP, including GPT CRCs, a block read and inherited SID60/CB0
identity qualification. That does not establish root mounting or userland.

`elden-ufs_ipados_defconfig` changes the compiled root name to `ipados`.
Select `native-ufs-lun=0` explicitly in its menu. Preserve the corrected ADT
arm-io origin 0x01000000, range size 0x16000000, corresponding relative child
registers and `AAPL,phandle=1` on the existing interrupt controller.

`sheng-ufs-elden-mmio-load.patch` makes the read helper emit fixed-address LDR
even when inlined. Device experiments isolated external aborts to post-index
LDR forms in the SMMU scan/CB0 diagnostics; equivalent non-writeback accesses
passed. The patch preserves full hardware stream-count and uniqueness checks
and does not alter SMMU registers. This source implementation still needs
compilation and device verification; earlier binary experiments are the
evidence for the selected instruction form.

Keep root I/O read-only. The first test is probe10: expected manifest status0
and two OS/SystemOS windows after the reviewed SHNGROOT image is installed.
Actual APFS root, launchd and SpringBoard additionally require sufficient
qualified RAM, matching trust input, Data configuration and userland fixups.
The existing 256MiB diagnostic memory budget is not a complete-system config.

Android boots after repartitioning, but the owner observed initial setup and
missing prior settings. Old encrypted data and metadata backups are retained
for later recovery investigation. This is not a successful data-preservation
claim. Stock rollback indices remain mandatory and unchanged.
