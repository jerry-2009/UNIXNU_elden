#!/usr/bin/env python3
"""Verify a phase-2.3 boot image, its ramdisk volume, and the firmware FV.

Checks the Android v3 header, the gzip(shim + FD) kernel, the ramdisk FAT
payload, and the phase-2.3 firmware contents (initrd RAM-disk driver present,
phase-1 embedded volume absent).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import lzma
import struct
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MU = ROOT / "third_party" / "mu_wide_platforms"
OUT = ROOT / "out" / "phase2.3"
PAGE_SIZE = 4096
FD_SIZE = 0x00400000
FVMAIN_FILE_GUID = uuid.UUID("9E21FD93-9C72-4C15-8C4B-E77F1DB2D792")
LZMA_GUIDED_SECTION_GUID = uuid.UUID("EE4E5898-3914-4259-9D6E-DC7BD79403CF")
REQUIRED_FV_FILES = {
    "UniXNU": uuid.UUID("9B665204-A133-47A2-9396-9E2B370A4E25"),
    "UniXNUDxe": uuid.UUID("29B950CF-586D-49EA-9D71-F88645CCDAF6"),
    "DarwinBoot": uuid.UUID("1B64AF87-8415-4B57-9B16-680D70913B9F"),
    "UniXNURamDiskDxe": uuid.UUID("75CA63AD-FBAE-4A06-92A0-F937C671251D"),
}
FORBIDDEN_FV_FILES = {
    "EldenRamDiskDxe": uuid.UUID("03AD2B0E-0E8E-46D9-A976-C424B7F2D7F6"),
    "elden-phase1-payload": uuid.UUID("6A6B6F43-2AE5-4A7E-9C4E-7C9A9136D2B0"),
    "UFSDxe": uuid.UUID("0D35CD8E-97EA-4F9A-96AF-0F0D89F76567"),
}
KERNEL_MACHO_BYTES = 54050816
KERNEL_MACHO_SHA256 = "65a3e799e1eb7f631a3b146dfc890ef5a8147c8fc613ee383a1665b398fb1ef9"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decompress_fvmain(fd: bytes) -> bytes:
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

    # The decompressed stream is a section stream.  GenFds emits the FV as an
    # EFI_SECTION_FIRMWARE_VOLUME_IMAGE section (0x17); phase 2 can have a
    # leading 4-byte RAW section, so walk the stream instead of assuming a
    # fixed prefix.
    offset = 0
    fvmain = None
    while offset + 4 <= len(unpacked):
        size = unpacked[offset] | (unpacked[offset + 1] << 8) | (unpacked[offset + 2] << 16)
        section_type = unpacked[offset + 3]
        header_size = 4
        if size == 0xFFFFFF:
            if offset + 8 > len(unpacked):
                break
            size = struct.unpack_from("<I", unpacked, offset + 4)[0]
            header_size = 8
        if size < header_size or offset + size > len(unpacked):
            break
        if section_type == 0x17:
            fvmain = unpacked[offset + header_size : offset + size]
            break
        offset = (offset + size + 3) & ~3
    if fvmain is None:
        raise SystemExit("decompressed FVMAIN section stream has no FV image")
    if len(fvmain) < 56 or fvmain[40:44] != b"_FVH":
        raise SystemExit("decompressed FVMAIN volume header is invalid")
    if struct.unpack_from("<Q", fvmain, 32)[0] != len(fvmain):
        raise SystemExit("decompressed FVMAIN volume length is inconsistent")
    return fvmain


def verify_fd(fd: bytes) -> bytes:
    if len(fd) != FD_SIZE:
        raise SystemExit(f"unexpected firmware volume size: {len(fd):#x}")
    fvmain = decompress_fvmain(fd)
    for name, guid in REQUIRED_FV_FILES.items():
        if fvmain.find(guid.bytes_le) < 0:
            raise SystemExit(f"firmware volume is missing {name} ({guid})")
    for name, guid in FORBIDDEN_FV_FILES.items():
        if fvmain.find(guid.bytes_le) >= 0:
            raise SystemExit(f"firmware volume unexpectedly contains {name} ({guid})")
    return fvmain


def mtools(*arguments: str) -> str:
    result = subprocess.run(
        list(arguments),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.stdout


def verify_ramdisk(ramdisk: bytes, kind: str) -> None:
    with tempfile.TemporaryDirectory(prefix="elden-2.3-") as directory:
        image = Path(directory) / "ramdisk.img"
        image.write_bytes(ramdisk)
        listing = mtools("mdir", "-i", str(image), "-/", "::")
        expected_label = "ELDENPROBE" if kind == "probe" else "ELDENRAM"
        if expected_label not in listing:
            raise SystemExit(f"ramdisk volume label is not {expected_label}")
        config = Path(directory) / "unixnu.toml"
        mtools(
            "mcopy", "-o", "-i", str(image),
            "::/EFI/UniXNU/unixnu.toml", str(config),
        )
        text = config.read_text()
        if "timeout = -1" not in text:
            raise SystemExit("unixnu.toml does not wait for input (timeout = -1)")
        if 'default = "reset"' not in text:
            raise SystemExit('unixnu.toml default is not reset')
        if kind == "probe":
            if "ELDEN 2.3 PROBE" not in text:
                raise SystemExit("probe title is missing from unixnu.toml")
            if 'type = "xnu"' in text:
                raise SystemExit("probe configuration unexpectedly has an XNU entry")
        else:
            if "ELDEN 2.3 INITRD 56M" not in text:
                raise SystemExit("final title is missing from unixnu.toml")
            kernel = Path(directory) / "kernel.macho"
            mtools(
                "mcopy", "-o", "-i", str(image),
                "::/EFI/UniXNU/Payloads/kernel.macho", str(kernel),
            )
            data = kernel.read_bytes()
            if len(data) != KERNEL_MACHO_BYTES or sha256(data) != KERNEL_MACHO_SHA256:
                raise SystemExit("kernel.macho differs from the phase-2.2 prelinked kernel")
            adt = Path(directory) / "adt.bin"
            mtools(
                "mcopy", "-o", "-i", str(image),
                "::/EFI/UniXNU/Payloads/kernel.macho.adt", str(adt),
            )
            if adt.stat().st_size == 0:
                raise SystemExit("kernel.macho.adt is empty")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("probe", "boot"), required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--fd", type=Path, default=OUT / "SILICIUM_UEFI.fd")
    parser.add_argument("--shim", type=Path, default=MU / "BootShim" / "BootShim.bin")
    parser.add_argument("--report", type=Path, default=OUT / "verify.json")
    args = parser.parse_args()

    image = args.image.read_bytes()
    fd = args.fd.read_bytes()
    shim = args.shim.read_bytes()

    if image[:8] != b"ANDROID!":
        raise SystemExit("boot image magic is missing")
    kernel_size, ramdisk_size = struct.unpack_from("<II", image, 8)
    header_size, = struct.unpack_from("<I", image, 20)
    header_version, = struct.unpack_from("<I", image, 40)
    if header_version != 3 or header_size != 1580:
        raise SystemExit(f"unexpected boot header v{header_version}, size {header_size}")
    if ramdisk_size == 0:
        raise SystemExit("boot image has no ramdisk")

    kernel = image[PAGE_SIZE : PAGE_SIZE + kernel_size]
    unpacked = gzip.decompress(kernel)
    if unpacked[: len(shim)] != shim:
        raise SystemExit("BootShim bytes differ from the built shim")
    if unpacked[len(shim) :] != fd:
        raise SystemExit("firmware volume bytes differ from the build output")

    ramdisk_start = PAGE_SIZE + ((kernel_size + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE
    ramdisk = image[ramdisk_start : ramdisk_start + ramdisk_size]
    if len(ramdisk) != ramdisk_size:
        raise SystemExit("boot image is truncated inside the ramdisk")

    fvmain = verify_fd(fd)
    verify_ramdisk(ramdisk, args.kind)

    entry = {
        "image": str(args.image.resolve().relative_to(ROOT)),
        "image_bytes": len(image),
        "image_sha256": sha256(image),
        "ramdisk_bytes": ramdisk_size,
        "ramdisk_sha256": sha256(ramdisk),
        "kernel_gzip_bytes": kernel_size,
        "fvmain_bytes": len(fvmain),
        "fd_sha256": sha256(fd),
        "shim_bytes": len(shim),
        "kind": args.kind,
    }
    report = {"schema": "unixnu-elden-phase2.3-verify/v1", "artifacts": []}
    if args.report.is_file():
        try:
            report = json.loads(args.report.read_text())
        except json.JSONDecodeError:
            pass
    report["artifacts"] = [
        item for item in report.get("artifacts", [])
        if item.get("image") != entry["image"]
    ] + [entry]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(f"artifact: OK ({len(image)} bytes)")
    print(f"  boot header: v3, ramdisk {ramdisk_size} bytes")
    print(f"  kernel gzip: {kernel_size} bytes -> shim {len(shim)} + FD {len(fd)}")
    print(f"  ramdisk label: {'ELDENPROBE' if args.kind == 'probe' else 'ELDENRAM'}")
    print(f"  decompressed FVMAIN: {len(fvmain)} bytes")
    print("  required FV files: " + ", ".join(REQUIRED_FV_FILES))
    print("  forbidden FV files absent: " + ", ".join(FORBIDDEN_FV_FILES))
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()
