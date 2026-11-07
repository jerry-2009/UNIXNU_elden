# Read-only UEFI storage work

This separate component is GPL-3.0-only, matching the reused kShimC core.
COPYING and provenance.json preserve the license and exact source hashes.
The original exported kShimC working tree is not modified, and no Git commit
is invented for an exported directory without .git.

The session layer admits only LUN4 and the unique CRC-checked ARMADA_BACKUP
GPT window. It exposes read operations, checks the DMA mapping before claim
and every submission, rejects write commands at the actual doorbell, and
checks all restored firmware register values after release. It never changes
GCC, HCE/reset or SMMU state. An uncertain release quarantines the session.

The UEFI backend now performs current-FDT platform admission, checks CPU
identity mappings and GCC clocks, allocates a below-4GiB DMA arena, checks
the inherited SID 0x60 SMMU route before each submission, and maintains caches.
It does not install an exception handler: readable mappings and clocks alone
cannot prove that hardware will never raise a bus fault. Tablet qualification
is still required. Both success and failure paths must call HardwareClose.

Build with `scripts/build-ufs-stage2.py` on the configured Mac. The script
first checks every imported file against provenance.json, generates only
standard-header/include adaptations under Generated/, and records both source
and compiled hashes. It does not rebuild or replace the accepted FD.

`EldenUfsProbe.efi` accepts only `inspect`; `EldenStage2.efi` accepts only
`current` or `previous`. Neither belongs in APRIORI. Stage2 checks two commit
records inside ARMADA_BACKUP, copies a complete SHA256-checked FAT image to
RAM, closes and verifies the UFS session, then publishes a read-only RAM
BlockIo volume and starts its `EFI/BOOT/BOOTAA64.EFI`. It restores the current
ABL FDT for the child. Failures before executing external code clean up and
return. After arbitrary external code returns it cold-restarts to the fixed
bootstrap because that code may have left drivers/events active.

Two equal commit generations are rejected. `current` prefers the highest
valid header and may use the other complete payload if its SHA is corrupt;
I/O failures end the session. `previous` explicitly selects the older header.
There is no automatic retry after executing arbitrary stage2 code. The
fixed signed menu and its embedded rescue entry remain the recovery path.

See `docs/UFS-STAGE2-20261106.md` for layout and evidence. The host transaction
tool operates on local regular files only. A separate owner-operated ADB
transport has root/su model tests, but has never been run against a device.
A complete external UniXNU bundle and separately signed bootstrap experiment
now exist; exact menu/reset and QEMU-ADT kernel-path tests pass. Session and
AAVMF tests are not hardware transport qualification.
