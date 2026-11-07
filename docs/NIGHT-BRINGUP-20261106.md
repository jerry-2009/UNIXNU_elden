# Host bring-up changes, 2026-11-06

The board now has an opt-in source console patch (`elden-gop-console=1`) after
the OS patch series. It uses UEFI boot_args.Video, marks its physical address,
selects text mode and routes kprintf to the console. It avoids Apple's fixed
panic-log handoff. A completed Mac kernel build produced SHA256
1a4d7d81cec5305aa28a7dff46392e04cda3ea8267df9d9ba109ecbad41360fa.
The separate diagnostic copy adds the existing AMFI latch workaround and an
entry band, producing 7a0822e1281f114c0fac5b87db742b1d0d2f04fc7319fe55fa6c5ddf2bf33abf.
The accepted FD is unchanged. No device boot is claimed.

The mockfs archive builder prefers patched source headers over stale cached
EXPORT_HDRS. The non-PPL pmap_cs header only requires the private TrustCache
monitor API when its monitor is selected. Actual kernel/archives/prelink have
completed; these build repairs do not implement an Apple power manager.

Root-check is a separate configuration. The archive keeps READ_ONLY=1,
builds the IOBlockStorageDevice interface and selects LUN0/4 explicitly.
It validates inherited SMMUv2 identity DMA before using PA, leaving SMMU
registers unchanged on the admitted path. Unknown configurations fail closed.
The complete root-check kernel now compiles/prelinks with genuine original
storage bindings: 52,023,296 bytes, SHA256
07d4df1d49e0dd64acab02e84a74d452c7034acd92e5a44b0ce37d67f53e4b15.
Its final static/live ABI and actual class-registration gate pass in a bounded
raw-entry QEMU run before UFS MMIO; see STORAGE-ABI-20261106.md. The saved
build/restore result is 0/0. It is not a verified hardware root device.
The portable identity test covers the captured matching bank and
synthetic nonmatching slots plus adverse field/address mutations.

The root parser expects manifest/windows for distinct OS and SystemOS images.
An empty ARMADA_BACKUP is only an I/O test window. No root image, GPT change or
hardware encryption operation was performed in this work.

The Windows host prepares a separate TWRP/Linux EFI prototype using the stock
EFI-stub kernel, vendor platform ramdisk and kernel-less TWRP ramdisk, with
LoadFile2 initrd. It preserves XNU menu selection. Its larger 160 MiB FAT and
hardware Linux/USB/decryption path remain unverified. Independent-partition
updates still require a UEFI UFS reader and explicit cross-volume loading.
Existing KShimC/dual-boot work is retained for later integration.

Host evidence and local signed artifacts live in the owner's Patch/Y700-Elden
work area and Mac out/ directories. They are not published. The signed boot
admission checks require exactly 1738713600@0; no stock index was raised.
