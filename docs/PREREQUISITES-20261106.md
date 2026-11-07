# Offline prerequisites, 2026-11-06

The current work adds bounded Android boot-property inheritance to the
compressed recovery loader. It reads `/chosen/bootargs` and, when present,
the original initrd's bootconfig trailer through the EFI memory map. It
rejects malformed ranges, sizes, checksums, conflicting recognized fields
and inconsistent slot/suffix values. Eight platform properties are eligible;
explicit final arguments and existing recovery bootconfig win. Recovery mode
and force_normal_boot remain unchanged. Missing sources are reported, not
replaced with guessed slot values.

The original vendor/TWRP CPIO bytes are preserved. Only a new in-memory
bootconfig trailer is constructed when inheritance adds fields. No partition
is read or written by this operation. `memory` reports at most eight large
conventional EFI extents and waits for a key or30seconds. This is a snapshot,
not an allocation, memory-map edit or larger XNU-memory qualification.

Current EldenPayloadLoader.efi is31744bytes, SHA256
`ae8e5938b22766b921f43f68e2ea63db028fb57ec1f3791edaf7db10f5825299`.
The existing signed first XNU candidate345e5052… is retained.

New host artifacts in the working project's `edl_work/prerequisites-20261106`:

| Artifact | SHA256 | Scope |
|---|---|---|
| combined/boot-signed.img | 9ebc7b6a021257ea9bcd44736d6338d96c69a83c99296ae099b4a57a4ddb883a |96MiB direct XNU/recovery/external update experiment,12entries |
| kshim48/boot-signed.img | 6af63b3e172890fbb3f8a1e6bb394fd260e6792b0fd42c55db4be5a9ab1d8f02 |96MiB frozen dual11 runtime and stock Android with48MiB recovery FAT; external XNU |
| external/stage2.fat | d26daaaf0f90da2d70a51b7c0bbc3fa48ea5d6739657c5fce16331de40803dd2 |56MiB external application/kernel/recovery bundle |

Both signed boot artifacts independently pass RSA/data digest, original
properties, partition size and exact boot1738713600@0 checks. The old FD is
unchanged. KShimC uses the exact known dual11 runtime; rebuilding its old
control is byte-identical. Its original Android image is reconstructable
byte-for-byte. The larger FreeExec entry has an explicit64MiB copy bound.
This does not establish a new successful KShimC hardware handoff.

AAVMF tests cover parent metadata bounds/CRC, `_b` inheritance over stale `_a`,
explicit recovery preservation, two complete145697280-byte CPIO prefix reads,
error cleanup/retry and memory-report return. The unchanged FDT-mailbox
contract also passes with absent metadata. The final EFI loader reaches the
same XNU storage registration return1 through neutral-debug DarwinBoot, and
stops before UFS MMIO. Neither test boots the real recovery Linux kernel on
the tablet. The external bundle's actual menu and cold-return path pass.

Original OS/SystemOS files were acquired from the profile's official Apple
IPSW using range reads. Their fixed SHA256 and ZIP CRC match; BuildManifest
binds roles and21H461/j120ap. OS's UDIF APFS region is decoded with its Apple
blkx CRC, where IGNORE extents are excluded from CRC and materialized as
verified zero holes. SystemOS is already raw. Mac readonly APFS inspection
inside this repository confirms both volume identities and17.7.11/21H461.
Four profile fixup source-byte locations match; no fixups are applied.
The original two-module trust bundle is61356bytes and matches7416ca4f….

The prepared9,381,609,472-byte SHNGROOT image passes independent window
readback and the actual NativeUfs RootLayout parser with file callbacks.
Its OS volume UUID is04769D26-2CA0-4825-B443-E2E5F88300F2, not the container
or GPT UUID. It is **not flash-ready**: the LUN0/ipados partition is only a
plan, Data/memory policy and a formal root-target kernel remain separate.
Current diagnostic kernels still target LUN4/ARMADA_BACKUP.

The full strategy and operator handoff are maintained in the working project
`research/STRATEGY-Y700-XNU-20261106.md` and
`research/PREREQUISITES-DELIVERY-20261106.md`. No tablet access, GPT modification,
formatting or firmware-floor change was performed.
