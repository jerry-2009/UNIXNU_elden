#!/usr/bin/env python3
"""Build BootShim without llvm-objcopy.

Apple clang can emit an AArch64 ELF relocatable, but Command Line Tools does
not install llvm-objcopy.  BootShim is a single allocation section, so a small
ELF64 section extractor is sufficient and keeps the build reproducible.
"""

from __future__ import annotations

import argparse
import struct
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MU = ROOT / "third_party" / "mu_wide_platforms"
SOURCE = ROOT / "patches/overlays/mu_wide_platforms/BootShim/BootShim.S"
OUTPUT = MU / "BootShim" / "BootShim.bin"
UEFI_BASE = 0xFF300000
UEFI_SIZE = 0x00400000


def extract_alloc_sections(elf: bytes) -> bytes:
    if elf[:4] != b"\x7fELF" or elf[4] != 2 or elf[5] != 1:
        raise ValueError("expected a little-endian ELF64 object")
    shoff = struct.unpack_from("<Q", elf, 40)[0]
    shentsize = struct.unpack_from("<H", elf, 58)[0]
    shnum = struct.unpack_from("<H", elf, 60)[0]
    shstrndx = struct.unpack_from("<H", elf, 62)[0]
    if shoff == 0 or shentsize < 64 or shnum == 0:
        raise ValueError("ELF section table is missing")
    headers = [
        struct.unpack_from("<IIQQQQIIQQ", elf, shoff + index * shentsize)
        for index in range(shnum)
    ]
    shstr_header = headers[shstrndx]
    shstr = elf[shstr_header[4] : shstr_header[4] + shstr_header[5]]

    sections = []
    for header in headers:
        name_offset, section_type, flags, address, offset, size, *_ = header
        if section_type == 8 or size == 0 or not (flags & 0x2):
            continue
        end = shstr.find(b"\x00", name_offset)
        name = shstr[name_offset:end].decode("ascii")
        sections.append((address, offset, size, name, elf[offset : offset + size]))
    if not sections:
        raise ValueError("ELF has no allocated sections")

    base = min(section[0] for section in sections)
    end = max(section[0] + section[2] for section in sections)
    output = bytearray(end - base)
    for address, _, size, name, data in sections:
        start = address - base
        output[start : start + size] = data
    return bytes(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--clang", default="clang")
    parser.add_argument("--entry-fdt-mailbox", action="store_true",
                        help="record ABL x0 at RAM FAT byte 0x1d0; requires reserved ELDFDT01 slot")
    parser.add_argument(
        "--payload-bytes", type=int, default=0,
        help="embedded FAT payload appended after the firmware volume",
    )
    args = parser.parse_args()
    if args.payload_bytes < 0:
        parser.error("--payload-bytes must not be negative")
    if args.entry_fdt_mailbox and args.payload_bytes < 512:
        parser.error("--entry-fdt-mailbox needs an embedded FAT payload")

    with tempfile.TemporaryDirectory(prefix="elden-shim-") as temp:
        obj = Path(temp) / "BootShim.elf"
        subprocess.run(
            [
                args.clang,
                "--target=aarch64-none-elf",
                "-c",
                str(SOURCE),
                "-o",
                str(obj),
                f"-DUEFI_BASE=0x{UEFI_BASE:08X}",
                f"-DUEFI_SIZE=0x{UEFI_SIZE:08X}",
            ] + (
                [f"-DEMBEDDED_PAYLOAD_SIZE={args.payload_bytes}"]
                if args.payload_bytes else []
            ) + (["-DENTRY_FDT_MAILBOX_OFFSET=0x1d0"] if args.entry_fdt_mailbox else []),
            check=True,
        )
        image = extract_alloc_sections(obj.read_bytes())

    if image[0x38:0x3C] != b"ARM\x64":
        raise ValueError("BootShim image header magic is missing")
    if args.entry_fdt_mailbox and len(image) != 128:
        raise ValueError("FDT mailbox shim must retain the accepted 128-byte layout")
    if struct.unpack_from("<Q", image, 0x08)[0] != UEFI_BASE:
        raise ValueError("BootShim firmware base does not match the SM8750 config")
    expected_size = UEFI_SIZE + args.payload_bytes
    if struct.unpack_from("<Q", image, 0x10)[0] != expected_size:
        raise ValueError("BootShim image size does not match the SM8750 config")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(image)
    print(f"bootshim: {args.output} ({len(image)} bytes)")


if __name__ == "__main__":
    main()

