#!/usr/bin/env python3
"""Verify the elden phase-2 boot image, RAM-disk payload and firmware modules."""

from __future__ import annotations

import argparse
import hashlib
import lzma
import shutil
import struct
import subprocess
import uuid
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE_SIZE = 4096
FD_SIZE = 0x00400000
FVMAIN_FILE_GUID = uuid.UUID("9E21FD93-9C72-4C15-8C4B-E77F1DB2D792")
LZMA_GUIDED_SECTION_GUID = uuid.UUID("EE4E5898-3914-4259-9D6E-DC7BD79403CF")
REQUIRED_FV_FILES = {
    "UniXNURamDiskDxe": uuid.UUID("75CA63AD-FBAE-4A06-92A0-F937C671251D"),
    "UniXNU": uuid.UUID("9B665204-A133-47A2-9396-9E2B370A4E25"),
    "UniXNUDxe": uuid.UUID("29B950CF-586D-49EA-9D71-F88645CCDAF6"),
    "DarwinBoot": uuid.UUID("1B64AF87-8415-4B57-9B16-680D70913B9F"),
}
FORBIDDEN_FV_FILES = {
    "EldenRamDiskDxe": uuid.UUID("03AD2B0E-0E8E-46D9-A976-C424B7F2D7F6"),
    "elden-phase1-payload": uuid.UUID("6A6B6F43-2AE5-4A7E-9C4E-7C9A9136D2B0"),
    "UFSDxe": uuid.UUID("0D35CD8E-97EA-4F9A-96AF-0F0D89F76567"),
}


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def verify_fv(fd: bytes) -> bytes:
    fvmain_offset = fd.find(FVMAIN_FILE_GUID.bytes_le)
    if fvmain_offset < 0:
        raise SystemExit("FVMAIN file GUID is missing from the firmware device")
    section_offset = fvmain_offset + 24
    section_size = struct.unpack_from("<I", fd, section_offset)[0] & 0xFFFFFF
    if fd[section_offset + 3] != 0x02:
        raise SystemExit("FVMAIN does not start with a GUID-defined section")
    compression_offset = fd.find(
        LZMA_GUIDED_SECTION_GUID.bytes_le,
        section_offset,
        section_offset + section_size,
    )
    if compression_offset < 0:
        raise SystemExit("FVMAIN LZMA guided section is missing")
    data_offset = struct.unpack_from("<H", fd, compression_offset + 16)[0]
    compressed_start = section_offset + data_offset
    compressed_end = section_offset + section_size
    if not section_offset < compressed_start < compressed_end <= len(fd):
        raise SystemExit("FVMAIN compressed section has invalid bounds")
    unpacked = lzma.decompress(fd[compressed_start:compressed_end])
    # GenFds prepends an eight-byte FV-image section header. Its short or
    # extended form depends on the final FV size; the FV header is authoritative.
    if len(unpacked) < 64:
        raise SystemExit("decompressed FVMAIN section is truncated")
    fvmain = unpacked[8:]
    if len(fvmain) < 56 or fvmain[40:44] != b"_FVH":
        raise SystemExit("decompressed FVMAIN volume header is invalid")
    if struct.unpack_from("<Q", fvmain, 32)[0] != len(fvmain):
        raise SystemExit("decompressed FVMAIN volume length is inconsistent")
    for name, guid in REQUIRED_FV_FILES.items():
        if fvmain.find(guid.bytes_le) < 0:
            raise SystemExit(f"firmware volume is missing {name} ({guid})")
    for name, guid in FORBIDDEN_FV_FILES.items():
        if fvmain.find(guid.bytes_le) >= 0:
            raise SystemExit(f"firmware volume unexpectedly contains {name} ({guid})")
    return fvmain


def fat_file(payload: Path, path: str) -> bytes:
    mcopy = shutil.which("mcopy")
    if not mcopy:
        raise SystemExit("mcopy not found; install mtools")
    return subprocess.check_output([mcopy, "-i", str(payload), f"::{path}", "-"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--fd", type=Path, required=True)
    parser.add_argument("--bootshim", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--dtb", type=Path, required=True)
    parser.add_argument("--kernel", type=Path, required=True)
    args = parser.parse_args()

    image = args.image.read_bytes()
    fd = args.fd.read_bytes()
    shim = args.bootshim.read_bytes()
    payload = args.payload.read_bytes()
    dtb = args.dtb.read_bytes()
    kernel_file = args.kernel.read_bytes()
    if image[:8] != b"ANDROID!":
        raise SystemExit("boot image magic is missing")
    kernel_size, ramdisk_size = struct.unpack_from("<II", image, 8)
    header_size = struct.unpack_from("<I", image, 20)[0]
    header_version = struct.unpack_from("<I", image, 40)[0]
    if header_version != 3 or header_size != 1580:
        raise SystemExit(f"unexpected boot header v{header_version}, size {header_size}")
    if len(fd) != FD_SIZE:
        raise SystemExit(f"unexpected firmware volume size: {len(fd):#x}")

    kernel_section = image[PAGE_SIZE : PAGE_SIZE + kernel_size]
    unpacker = zlib.decompressobj(16 + zlib.MAX_WBITS)
    combined = unpacker.decompress(kernel_section)
    if not unpacker.eof or unpacker.unused_data != dtb:
        raise SystemExit("gzip firmware and appended device tree do not round-trip")
    if combined[: len(shim)] != shim or combined[len(shim) :] != fd:
        raise SystemExit("BootShim or firmware volume bytes differ from the build output")

    ramdisk_start = PAGE_SIZE * (1 + -(-kernel_size // PAGE_SIZE))
    if image[ramdisk_start : ramdisk_start + ramdisk_size] != payload:
        raise SystemExit("boot image ramdisk differs from the generated FAT payload")
    fvmain = verify_fv(fd)

    config = fat_file(args.payload, "/EFI/UniXNU/unixnu.toml")
    if b'type = "xnu"' not in config or b'path = "Payloads/kernel.macho"' not in config:
        raise SystemExit("payload configuration has no XNU entry")
    payload_kernel = fat_file(args.payload, "/EFI/UniXNU/Payloads/kernel.macho")
    payload_adt = fat_file(args.payload, "/EFI/UniXNU/Payloads/kernel.macho.adt")
    if payload_kernel != kernel_file:
        raise SystemExit("payload kernel differs from the verified prelinked input")
    if len(payload_adt) < 1024:
        raise SystemExit("payload ADT sidecar is missing or truncated")

    print(f"phase2 artifact: OK ({len(image)} bytes)")
    print("  platform seed: caller-supplied; run build_phase2.py --test-seed for host-only images")
    print(f"  boot header: v{header_version}, ramdisk {ramdisk_size} bytes")
    print(f"  kernel section: {kernel_size} bytes")
    print(f"  payload kernel: {sha256(payload_kernel)}")
    print(f"  payload ADT: {len(payload_adt)} bytes, {sha256(payload_adt)}")
    print(f"  firmware volume: {len(fd)} bytes")
    print(f"  decompressed FVMAIN: {len(fvmain)} bytes")
    print("  required FV files: " + ", ".join(REQUIRED_FV_FILES))
    print("  forbidden embedded/phase-1 files absent: " + ", ".join(FORBIDDEN_FV_FILES))


if __name__ == "__main__":
    main()
