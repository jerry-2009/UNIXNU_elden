# Compressed XNU and independent recovery entry

The complete source-console/UFS kernel, stock EFI Linux kernel and complete
vendor/TWRP ramdisks fit together in 50,660,494 compressed bytes (48.3 MiB).
The vendor and TWRP CPIO contents are retained. Their concatenated raw initrd
is 145,697,592 bytes including its rebuilt, checked bootconfig trailer.
EDK's LzmaCompress and an independent decoder reproduce all input hashes.
No TWRP functions or libraries were removed to achieve this size.

`drivers/EldenPayloadLoader` provides a bounded EFI application intended to
keep the RAM FAT at the already accepted 56 MiB size. It reads compressed
assets from the filesystem that loaded the application. XNU is exposed to
the installed DarwinBoot protocol through a read-only memory filesystem,
including its Apple-format `.adt` sidecar. The accepted loader rejects a
non-null Request.DeviceTree, so that field remains null. The original request
carries the kernel path and boot arguments. Linux is loaded through its stock EFI stub, with the complete
raw initrd published through the standard Linux LoadFile2 media path.

The two menu argument prefixes are `xnu ` and `linux `, followed by that
kernel's actual arguments. The Linux entry must not declare a separate
UniXNU `initrd` because the application publishes the decoded initrd itself.
Linux requires a valid firmware FDT; its hardware description, EFI handoff,
USB, display and wrapped-key decryption remain device acceptance items.

The application also has an `audit` mode for offline firmware testing: it
decodes the same three complete assets and emits lengths and CRC32 values.
The 22,528-byte application (SHA256 364b0d79…) has now executed all three
complete decodes in AAVMF. Their lengths/CRC32 are 52,035,688/1d45f1c1,
36,731,392/5bdcc5f2 and 145,697,592/4407361e. With a test DarwinBoot build
using BaseDebugLibNull, the normal EFI path passes EBS and reaches the
same XNU's console and actual storage-class registration gate. That run
does not patch guest code or PC and stops before UFS MMIO.

The exact accepted DarwinBoot PE depends on the Y700 platform graphics
debug sink. In AAVMF it faults at RVA 0x3484 in that sink, before EBS.
The neutral-debug test build is explicitly a different binary, 8dee9a1a…;
its result must not be reported as a boot of the complete Y700 firmware.

The combined experimental signed packet is 40fc9e6c… in the owner's Patch
workspace. Its AVB, FAT, decompressed inputs, bootconfig and entry band
checks pass, with the accepted FD and the same 56 MiB payload size.
TWRP boot, USB, touch and wrapped-key decryption remain hardware-unverified.
The primary signed read-only XNU packet remains 345e5052… for first device
validation. No device was accessed or written during these tests.

This improves the self-contained recovery prototype. Independent-partition
updates still require a qualified UEFI UFS reader and explicit selection of
the updated stage-two loader; they are not completed by compression alone.
The existing KShimC dual-boot work remains a separate preserved entry route.

An independent EFI initrd consumer and launcher are added for the recovery
software contract test. They replace only the Linux kernel inside a separate
QEMU fixture and keep the complete original vendor/TWRP initrd. They check
LoadFile2 discovery, size query, short-buffer protection, boot arguments,
full initrd CRC, failure cleanup and a fresh successful retry. These test
applications are not included in tablet images and do not prove TWRP boot.

The current combined experiment is now cae0750e…, with a 24,576-byte loader
(2800abf8…) and the live ABL FDT mailbox described in ENTRY-FDT-HANDOFF-20261106.md.
It supersedes the earlier 40fc9e6c… experiment's assumption of an installed
firmware FDT table. The new loader passes the four mailbox rejection/copy/
cleanup/retry cases using the full original initrd. Its XNU branch also
passes the AAVMF/neutral-debug DarwinBoot EBS-to-registration test with no
guest code or PC modification. Actual Linux/TWRP and device UFS remain
unverified; the plain 345e5052… XNU packet remains the first-validation choice.
