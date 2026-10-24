#!/usr/bin/env python3
"""Verify the final Android boot image and its BootShim/UEFI payload."""

from __future__ import annotations

import argparse
import gzip
import lzma
import struct
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MU = ROOT / "third_party" / "mu_wide_platforms"
DEFAULT_IMAGE = MU / "Build" / "PakalaPkg" / "lenovo-y700g4.img"
DEFAULT_FD = MU / "Build" / "PakalaPkg" / "DEBUG_CLANGPDB" / "FV" / "SM8750_EFI.fd"
DEFAULT_SHIM = MU / "BootShim" / "BootShim.bin"
DEFAULT_PAYLOAD = MU / "Platforms" / "EldenPhase1Pkg" / "Payload" / "payload.img"
PAGE_SIZE = 4096
FD_SIZE = 0x00400000
FVMAIN_FILE_GUID = uuid.UUID("9E21FD93-9C72-4C15-8C4B-E77F1DB2D792")
LZMA_GUIDED_SECTION_GUID = uuid.UUID("EE4E5898-3914-4259-9D6E-DC7BD79403CF")
REQUIRED_FV_FILES = {
    "EldenRamDiskDxe": uuid.UUID("03AD2B0E-0E8E-46D9-A976-C424B7F2D7F6"),
    "UniXNU": uuid.UUID("9B665204-A133-47A2-9396-9E2B370A4E25"),
    "UniXNUDxe": uuid.UUID("29B950CF-586D-49EA-9D71-F88645CCDAF6"),
    "DarwinBoot": uuid.UUID("1B64AF87-8415-4B57-9B16-680D70913B9F"),
    "elden-phase1-payload": uuid.UUID("6A6B6F43-2AE5-4A7E-9C4E-7C9A9136D2B0"),
}
FORBIDDEN_FV_FILES = {
    "UFSDxe": uuid.UUID("0D35CD8E-97EA-4F9A-96AF-0F0D89F76567"),
}


def verify_firmware_volume(fd: bytes, payload: bytes) -> bytes:
    fvmain_offset = fd.find(FVMAIN_FILE_GUID.bytes_le)
    if fvmain_offset < 0:
        raise SystemExit("FVMAIN file GUID is missing from the firmware device")

    # The FFS file header is 24 bytes; the following GUID-defined section
    # contains the LZMA-compressed copy of FVMAIN.
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
    if len(unpacked) < 8 or unpacked[:3] != b"\xFF\xFF\xFF" or unpacked[3] != 0x17:
        raise SystemExit("decompressed FVMAIN section header is invalid")
    if struct.unpack_from("<I", unpacked, 4)[0] != len(unpacked):
        raise SystemExit("decompressed FVMAIN section size is inconsistent")
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
    if payload not in fvmain:
        raise SystemExit("embedded FAT payload differs from the generated payload")
    return fvmain


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--fd", type=Path, default=DEFAULT_FD)
    parser.add_argument("--bootshim", type=Path, default=DEFAULT_SHIM)
    parser.add_argument("--payload", type=Path, default=DEFAULT_PAYLOAD)
    args = parser.parse_args()

    image = args.image.read_bytes()
    fd = args.fd.read_bytes()
    shim = args.bootshim.read_bytes()
    payload = args.payload.read_bytes()
    if image[:8] != b"ANDROID!":
        raise SystemExit("boot image magic is missing")
    kernel_size, ramdisk_size = struct.unpack_from("<II", image, 8)
    header_size, = struct.unpack_from("<I", image, 20)
    header_version, = struct.unpack_from("<I", image, 40)
    if header_version != 3 or header_size != 1580:
        raise SystemExit(
            f"unexpected boot header v{header_version}, size {header_size}"
        )
    if ramdisk_size != 0:
        raise SystemExit("phase-1 image unexpectedly contains a ramdisk")
    if len(fd) != FD_SIZE:
        raise SystemExit(f"unexpected firmware volume size: {len(fd):#x}")

    kernel = image[PAGE_SIZE : PAGE_SIZE + kernel_size]
    unpacked = gzip.decompress(kernel)
    expected_size = len(shim) + len(fd)
    if len(unpacked) != expected_size:
        raise SystemExit(
            f"shim+FV size {len(unpacked):#x}, expected {expected_size:#x}"
        )
    if unpacked[: len(shim)] != shim:
        raise SystemExit("BootShim bytes differ from the built shim")
    if unpacked[len(shim) :] != fd:
        raise SystemExit("firmware volume bytes differ from the build output")

    fvmain = verify_firmware_volume(fd, payload)
    print(f"artifact: OK ({args.image.stat().st_size} bytes)")
    print(f"  boot header: v{header_version}, no ramdisk")
    print(f"  compressed payload: {kernel_size} bytes")
    print(f"  BootShim: {len(shim)} bytes")
    print(f"  firmware volume: {len(fd)} bytes")
    print(f"  decompressed FVMAIN: {len(fvmain)} bytes")
    print("  required FV files: " + ", ".join(REQUIRED_FV_FILES))
    print("  forbidden FV files absent: " + ", ".join(FORBIDDEN_FV_FILES))


if __name__ == "__main__":
    main()

