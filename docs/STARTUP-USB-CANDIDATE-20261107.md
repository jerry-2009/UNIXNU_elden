# Elden root/startup and USB CDC candidate

This is an offline-built device test candidate, not a device-qualified iPadOS release.
The owner disconnected the tablet before this build; no device writes were performed in this offline phase.

## Root and initial Data

The two original 21H461 raw OS/SystemOS images are pinned by size, SHA256 and the APFS volume UUIDs
observed with native read-only tools. The pins reside in the AVB-authenticated kernel. The driver hashes
each entire image before publishing any window, builds a 4KiB hash table, protects that table read-only,
then checks every block read. Mutable or unknown media do not gain root authorization.

The owner startup bridge verifies live IOMedia UUID, BSD device identity, read-only state and ancestry
to a sealed pinned provider. It supplies the existing SystemOS/owner-image-set hooks without pretending
that Virtio was initialized or that an unverified UUID is sufficient. The build guard retains the original
requirements for other modes; the elden extension requires the actual UFS/crypto build and bridge exports.

SystemOS uses the existing native read-only union mount. A new 512MiB APFS RAM Data seed comes only from
the unchanged OS's initial private/var tree plus empty runtime/persona directories. It contains no personal
keys or account records. Its DBRDISK1 encoding expands to the checked raw SHA under the actual C decoder.
It is volatile, and device ownership/provisioning remains unqualified. UFS stays read-only.

The original two-module TrustCache and four version-matched runtime text fixups are included.
The current build does not provide persistent iPadOS Data, GPU/display acceleration, touch or complete power management.
The mdev Data path skips the optional GPU-addon installation that requires the separate native RAM-block provider.

## USB adapter

Generic DWC3/CDC comes from the unchanged MIT QcomXnuUsbDebug core based on m1n1 v1.4.17.
References and hashes stay under the owner's research/qcom-usb-core-20261107 directory.
Its private translated-DMA native adapter was not copied or weakened; this is an independent elden adapter.

Hardware constants live in soc/sm8750/include/EldenUsbResources.h. The adapter requires inherited powered
clocks, device role, supported DWC3 ID, 64-byte cache lines, contiguous addressable DMA and a freshly checked
unique SID0x40 identity route. It does not change GCC, GPIO, PHY calibration or SMMU tables. It configures only
the admitted DWC3 device and documented Qualcomm session/VBUS overrides. Unknown state is refused.
Cold initialization and the actual post-EBS USB/SMMU state have not been established on the tablet.

The 128KiB console ring is nonblocking; contention/full cases count drops. A CPU-bound worker serializes
all DWC3 access. Panic has a bounded TX-only drain on that CPU; it does not execute commands or allocate.
DMA memory is retained after failures, including an unproved stop. Console duplication remains fixed.

The experimental USB identity is1209:7004, serial ELDEN-XNU. Commands are limited to ping/status.
Reboot/fastboot requests return an explicit unqualified error. No raw memory, shell or flash operation is exposed.

## Observations and tests

Native host tests cover the actual pinned-image algorithm with both complete owned images and corruption,
bounds, read/protection failures; the USB core covers descriptors, control transfers, high DMA addresses,
RX/TX bounds, cache ordering, reset and timeout cases. Console ring and session/milestone rejection cases pass.
Actual C firmware decoding reconstructs the512MiB Data SHA and rejects malformed extents. No QEMU was run.

Kernel compilation, original storage ABI binding, prelinking and payload checks pass. These results do not
establish USB enumeration, real mount/exec, or driver stability. Device evidence belongs in a later record.
The new session-bound status exposes actual SystemOS/Data results, successful init exec, and a PID1 EL0 BSD
syscall marker. Repeated live status and logs are required for the requested milestone; a filename alone is not proof.
