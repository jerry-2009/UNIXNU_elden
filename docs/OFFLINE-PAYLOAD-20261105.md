# Offline payload delivery checks (2026-11-05)

This host-only change fixes the ramdisk argument placement in
`scripts/build_phase2_image.py` and validates both the ARM64 advertised size
and BootShim's actual x3 payload-size instruction. A header-only enlargement
of an 8 MiB shim is now rejected. The FAT verifier also rejects a BPB whose
volume extends past the published bytes. Gzip has a fixed mtime for repeatable
assembly from identical inputs.

`scripts/build_offline_ufs_packet.py` consumes an existing accepted 4 MiB FD,
FAT payload and independently compiled kernel. It copies the payload, adds
the marker menu, extracts kernel/ADT, compares the kernel hash, runs the
DarwinBoot preflight, rebuilds the shim from the payload's real length and
runs the phase-2 verifier. It does not contact a device or rebuild firmware.

Host input: device HEAD 33b55083a0b61630f71478230f648606163115eb plus the local
packaging changes; CLI 73a793d20f7dd9d36f3dc05f63ecf6c30dd45c7c. The prior
kernel is reused; no new kernel compilation or hardware qualification is claimed.

The accepted FD SHA256 is
`e50e1d6e2be51367225d76d4e97b90d51ba7812193d99fd4d4d7dd9fdc2ee534`.
The candidate contains that exact FD, a 128-byte freshly compiled shim and
58,720,256 payload bytes. Kernel: 51,986,432 bytes; 15 Mach-O segments;
span 0x4136000; entry 0xfffffff0073ed488. ADT: 13,624 bytes, 256 MiB handoff
window, no optional RAMDisk/TrustCache/GpuAddon placeholders. Preflight and
FAT16/FD/config/kernel verification passed on macOS.

The marker menu has four entries and a 600-second fallback if input is absent.
The UFS entry requests probe 2. Its expected diagnostic endpoint is a deliberate
`NATIVE_UFS inspect` panic. Probe 7/8 are SMMU/CB diagnostics; they do not discover
GPT or publish storage. The SM8750 guard rejects probe 3 in this build.

An independent Windows check executes the real old/new shim bytes in Unicorn,
both relocated and already at the FD destination. The original passes x3=8 MiB,
the candidate passes x3=56 MiB, and both preserve x0 and the FD copy. A shim
with only its header changed to 60 MiB is refused by the new verifier.

Firmware inventory: the accepted FD has EldenPayloadDxe and lacks
UniXNURamDiskDxe, so fixing Android ramdisk packaging alone cannot make that
FD consume an initrd. Android v3/v4 ramdisk_size at offset 0x0c is the standard
layout, not a private format. The bad newer FD adds AdvancedLogDxe and changes
many existing modules. That comparison does not identify the reset cause.

The existing phase-1-only `make_payload.py --verify-only` default references a
missing local phase-1 payload. This candidate instead passes the applicable
`verify_phase2_artifact.py` with explicit actual kernel size/hash and title.
No phase-1 rebuild, root mount, new FD runtime fix or device boot is claimed.
The separate experiment directory contains build-log.json, verify.json and
inputs-and-products.json. Device acceptance remains owner operated.
