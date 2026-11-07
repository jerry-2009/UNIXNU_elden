# Current-boot FDT handoff for recovery

The accepted embedded-payload PrePi path passes the payload base/size into
DXE and does not preserve the ABL FDT argument through the separate entry
FDT HOB. The entry-HOB GUID is absent from the accepted FD and its expanded
FV. Recovery therefore cannot assume the presence of an EFI FDT table.
The supplied historical FDT dump also had CRLF expansion; its repaired
copy is diagnostic evidence, not a substitute for this boot's FDT.

The optional `--entry-fdt-mailbox` BootShim mode records x0 in a reserved
slot of the RAM FAT boot sector. It does not dereference x0 or write disk.
The default build stays byte-identical to the previous accepted shim.
Both builds remain 128 bytes and keep the 4 MiB FD and payload handoff.

| Offset | Bytes | Meaning |
|---|---:|---|
| 0x1c0 | 8 | ASCII ELDFDT01 |
| 0x1c8 | 4 | Little-endian version 1 |
| 0x1cc | 4 | Reserved zero |
| 0x1d0 | 8 | Little-endian current ABL FDT pointer; zero in the signed file |

The slot is outside the FAT BPB and before the boot-sector signature. The
builder refuses the feature unless the exact empty record was reserved.
The additional instruction is `str x0, [x2, #0x1d0]`; the unreachable dead
branch is omitted in this mode so the shim size remains unchanged.
Six actual ARM64 instruction runs cover copied/in-place FD paths and three
pointer values, including unmapped ones. Only the pointer slot changes;
x0/x1/x2/x3, the copied FD and surrounding payload bytes match expectations.

The recovery application reads this record only from its own source
volume. It checks the pointer against RAM-like EFI memory-map descriptors,
caps the FDT at 2 MiB, validates its header, structure tokens, strings and
reservation list, then copies it to ACPI reclaim memory and publishes the
FDT table. Failure return restores the previous table and frees the copy.
With no mailbox it can use an already installed valid firmware FDT.

The EFI test producer supplies a real QEMU-generated FDT and the same real
files, using a test-only BlockIo view of the volatile mailbox. It exercises
out-of-map pointers, oversized headers, an intentional child failure and
a fresh successful retry with the complete vendor/TWRP initrd. This is a
software contract test, not a TWRP hardware or decryption qualification.

The four EFI contract cases now pass with application SHA256 2800abf8…:
an out-of-map pointer and an oversized FDT are refused; a valid current
FDT is copied and published, then restored after both an intentional child
error and a successful retry. Both real initrd reads return 145,697,592
bytes with CRC32 4407361e. BootShim remains 128 bytes, SHA256 20791726….

The new signed combined experiment is cae0750e… in
Patch/Y700-Elden/edl_work/combined-rescue-fdt-20261106. It supersedes the
40fc9e6c… combined experiment's assumption that a firmware FDT table exists.
The plain XNU first-validation packet 345e5052… remains unchanged. Exact
stock index 1738713600@0, complete recovery contents and accepted FD bytes
are independently checked. Hardware Linux/TWRP, USB and FBE remain untested.
