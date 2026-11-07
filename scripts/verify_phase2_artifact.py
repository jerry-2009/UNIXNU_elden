#!/usr/bin/env python3
"""Verify a phase-2.3 boot image, its FAT payload, and the firmware FV.

Two layouts are supported: the FAT volume travels in the Android ramdisk
field, or --embed-payload appends it after the firmware inside the kernel
field.  The firmware must publish the volume through the phase-2.3 payload
driver and must not carry the phase-1 embedded volume.
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
}
FORBIDDEN_FV_FILES = {
    "EldenRamDiskDxe": uuid.UUID("03AD2B0E-0E8E-46D9-A976-C424B7F2D7F6"),
    "elden-phase1-payload": uuid.UUID("6A6B6F43-2AE5-4A7E-9C4E-7C9A9136D2B0"),
    "UFSDxe": uuid.UUID("0D35CD8E-97EA-4F9A-96AF-0F0D89F76567"),
}
RAMDISK_DRIVER = ("UniXNURamDiskDxe", uuid.UUID("75CA63AD-FBAE-4A06-92A0-F937C671251D"))
PAYLOAD_DRIVER = ("EldenPayloadDxe", uuid.UUID("8C2F0D5E-41B7-4E63-9A2D-5F6B8C1E3A70"))
KERNEL_MACHO_BYTES = 54050816
KERNEL_MACHO_SHA256 = "65a3e799e1eb7f631a3b146dfc890ef5a8147c8fc613ee383a1665b398fb1ef9"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_embedded_shim(shim: bytes, payload_bytes: int) -> None:
    """Check both advertised size and the size actually handed to PrePi in x3.

    Editing only the ARM64 header leaves the old compiled x3 constant intact.
    Accept the two encodings clang emits for `ldr x3, =constant`; reject an
    unfamiliar stub instead of guessing that its handoff is safe.
    """
    if len(shim) < 64 or shim[56:60] != b"ARM\x64":
        raise SystemExit("BootShim ARM64 header is missing")
    if struct.unpack_from("<Q", shim, 16)[0] != FD_SIZE + payload_bytes:
        raise SystemExit("BootShim header size does not cover FD + payload")
    # add x2, x1, #0x400, lsl #12: payload base follows the 4 MiB FD.
    candidates = [offset for offset in range(64, len(shim) - 8, 4)
                  if struct.unpack_from("<I", shim, offset)[0] == 0x91500022]
    if len(candidates) != 1:
        raise SystemExit("BootShim embedded payload-base instruction is missing/ambiguous")
    offset = candidates[0] + 4
    instruction = struct.unpack_from("<I", shim, offset)[0]
    if instruction & 0xFF00001F == 0x58000003:  # ldr x3, literal
        delta = (instruction >> 5) & 0x7FFFF
        if delta & 0x40000:
            delta -= 0x80000
        literal = offset + delta * 4
        if literal < 0 or literal + 8 > len(shim):
            raise SystemExit("BootShim x3 literal is outside the shim")
        actual = struct.unpack_from("<Q", shim, literal)[0]
    elif instruction & 0xFF80001F == 0xD2800003:  # movz x3, imm16, lsl hw
        actual = ((instruction >> 5) & 0xFFFF) << (((instruction >> 21) & 3) * 16)
    else:
        raise SystemExit("unrecognised BootShim x3 handoff; audit the new assembly")
    branch = offset + 4
    if struct.unpack_from("<I", shim, branch)[0] == 0xF900E840:  # str x0, [x2, #0x1d0]
        branch += 4
    if struct.unpack_from("<I", shim, branch)[0] != 0xD61F00A0:  # br x5
        raise SystemExit("BootShim does not branch to firmware after loading x3")
    if actual != payload_bytes:
        raise SystemExit(f"BootShim passes x3={actual:#x}, payload is {payload_bytes:#x}")


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


def verify_fd(fd: bytes, embedded: bool) -> bytes:
    if len(fd) != FD_SIZE:
        raise SystemExit(f"unexpected firmware volume size: {len(fd):#x}")
    fvmain = decompress_fvmain(fd)
    required = dict(REQUIRED_FV_FILES)
    forbidden = dict(FORBIDDEN_FV_FILES)
    required[PAYLOAD_DRIVER[0]] = PAYLOAD_DRIVER[1]
    forbidden[RAMDISK_DRIVER[0]] = RAMDISK_DRIVER[1]
    for name, guid in required.items():
        if fvmain.find(guid.bytes_le) < 0:
            raise SystemExit(f"firmware volume is missing {name} ({guid})")
    for name, guid in forbidden.items():
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


FAT_MAX_FAT12_CLUSTER = 0xFF5
FAT_MAX_FAT16_CLUSTER = 0xFFF5


def verify_fat_type(volume: bytes) -> tuple[str, str]:
    """Reject volumes EnhancedFatDxe would not mount.

    FatPkg/EnhancedFatDxe/Init.c decides the FAT type from MaxCluster, not from
    the BPB size fields.  A FAT32 BPB below FAT_MAX_FAT16_CLUSTER clusters is
    returned as EFI_VOLUME_CORRUPTED, so an 8 MiB FAT32 volume silently never
    becomes a SimpleFileSystem and UniXNU falls back to the built-in menu.
    """
    if len(volume) < 512 or volume[510:512] != b"\x55\xAA":
        raise SystemExit("FAT volume has no boot signature")
    sector_size, = struct.unpack_from("<H", volume, 11)
    sectors_per_cluster = volume[13]
    reserved, = struct.unpack_from("<H", volume, 14)
    fats = volume[16]
    root_entries, = struct.unpack_from("<H", volume, 17)
    total16, = struct.unpack_from("<H", volume, 19)
    fat_sectors16, = struct.unpack_from("<H", volume, 22)
    total32, = struct.unpack_from("<I", volume, 32)
    fat_sectors32, = struct.unpack_from("<I", volume, 36)
    ext_flags, = struct.unpack_from("<H", volume, 40)
    fs_version, = struct.unpack_from("<H", volume, 42)
    total_sectors = total16 or total32
    fat_sectors = fat_sectors16 or fat_sectors32
    if not sector_size or not sectors_per_cluster or not reserved or not fats:
        raise SystemExit("FAT boot sector (BPB) is incomplete")
    if not total_sectors or not fat_sectors:
        raise SystemExit("FAT boot sector (BPB) has no geometry")
    if (sector_size not in (512, 1024, 2048, 4096)
            or sectors_per_cluster & (sectors_per_cluster - 1)):
        raise SystemExit("FAT sector/cluster geometry is invalid")
    if total_sectors * sector_size > len(volume):
        raise SystemExit("FAT BPB extends past the published payload")
    label = volume[43:54].decode("ascii", "replace").strip() if fat_sectors16 else ""
    if fat_sectors16:
        if root_entries == 0:
            raise SystemExit("FAT12/16 BPB has no root directory entries")
        fat_name = "FAT12/16"
    else:
        if fs_version != 0 or (ext_flags & 0x80):
            raise SystemExit("FAT32 BPB has a version or mirroring flag FatDxe rejects")
        fat_name = "FAT32"
        label = volume[71:82].decode("ascii", "replace").strip()
    root_sectors = (root_entries * 32 + sector_size - 1) // sector_size
    first_data_sector = reserved + fats * fat_sectors + root_sectors
    cluster_alignment = sectors_per_cluster.bit_length() - 1
    max_cluster = (total_sectors - first_data_sector) >> cluster_alignment
    if fat_sectors16:
        if not FAT_MAX_FAT12_CLUSTER <= max_cluster < FAT_MAX_FAT16_CLUSTER:
            raise SystemExit(
                f"FAT16 volume has {max_cluster} clusters; EnhancedFatDxe wants "
                f"{FAT_MAX_FAT12_CLUSTER}..{FAT_MAX_FAT16_CLUSTER - 1}"
            )
    elif max_cluster < FAT_MAX_FAT16_CLUSTER:
        raise SystemExit(
            f"FAT32 volume has only {max_cluster} clusters; EnhancedFatDxe "
            f"returns EFI_VOLUME_CORRUPTED below {FAT_MAX_FAT16_CLUSTER}"
        )
    return fat_name, label


def verify_ramdisk(
    ramdisk: bytes,
    kind: str,
    expect_kernel_bytes: int = KERNEL_MACHO_BYTES,
    expect_kernel_sha256: str = KERNEL_MACHO_SHA256,
    xnu_title: str = "ELDEN 2.3 INITRD 56M",
    expect_timeout: int = -1,
    expect_default: str = "reset",
) -> str:
    fat_name, volume_label = verify_fat_type(ramdisk)
    expected_label = "ELDENPROBE" if kind == "probe" else "ELDENRAM"
    if volume_label != expected_label:
        raise SystemExit(f"ramdisk volume label is {volume_label!r}, want {expected_label}")
    with tempfile.TemporaryDirectory(prefix="elden-2.3-") as directory:
        image = Path(directory) / "ramdisk.img"
        image.write_bytes(ramdisk)
        mtools("mdir", "-i", str(image), "-/", "::")
        config = Path(directory) / "unixnu.toml"
        mtools(
            "mcopy", "-o", "-i", str(image),
            "::/EFI/UniXNU/unixnu.toml", str(config),
        )
        text = config.read_text()
        import tomllib
        parsed = tomllib.loads(text)
        boot = parsed.get('boot', {})
        if type(boot.get('timeout')) is not int or boot['timeout'] != expect_timeout:
            raise SystemExit(f'unixnu.toml timeout differs from explicitly expected {expect_timeout}')
        if boot.get('default') != expect_default:
            raise SystemExit(f'unixnu.toml default differs from explicitly expected {expect_default}')
        if sum(entry.get('id') == expect_default for entry in parsed.get('entry', [])) != 1:
            raise SystemExit('default menu entry is missing or ambiguous')
        scale = [line for line in text.splitlines() if line.strip().startswith("scale")]
        if not scale:
            raise SystemExit("unixnu.toml does not pin the menu scale ([ui] scale)")
        value = int(scale[0].split("=", 1)[1].strip())
        if not 1 <= value <= 6:
            raise SystemExit(f"unixnu.toml menu scale {value} is outside 1..6")
        if kind == "probe":
            if "ELDEN 2.3 PROBE" not in text:
                raise SystemExit("probe title is missing from unixnu.toml")
            if 'type = "xnu"' in text:
                raise SystemExit("probe configuration unexpectedly has an XNU entry")
        else:
            if xnu_title not in text:
                raise SystemExit(f"final title {xnu_title!r} is missing from unixnu.toml")
            kernel = Path(directory) / "kernel.macho"
            mtools(
                "mcopy", "-o", "-i", str(image),
                "::/EFI/UniXNU/Payloads/kernel.macho", str(kernel),
            )
            data = kernel.read_bytes()
            if len(data) != expect_kernel_bytes or sha256(data) != expect_kernel_sha256:
                raise SystemExit(
                    f"kernel.macho is {len(data)} bytes sha256={sha256(data)}, "
                    f"expected {expect_kernel_bytes} bytes sha256={expect_kernel_sha256}")
            adt = Path(directory) / "adt.bin"
            mtools(
                "mcopy", "-o", "-i", str(image),
                "::/EFI/UniXNU/Payloads/kernel.macho.adt", str(adt),
            )
            if adt.stat().st_size == 0:
                raise SystemExit("kernel.macho.adt is empty")
    return fat_name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("probe", "boot"), required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--fd", type=Path, default=OUT / "SILICIUM_UEFI.fd")
    parser.add_argument("--shim", type=Path, default=MU / "BootShim" / "BootShim.bin")
    parser.add_argument("--report", type=Path, default=OUT / "verify.json")
    parser.add_argument("--embed-payload", action="store_true")
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--expect-kernel-bytes", type=int, default=KERNEL_MACHO_BYTES)
    parser.add_argument("--expect-kernel-sha256", default=KERNEL_MACHO_SHA256)
    parser.add_argument(
        "--xnu-title",
        default="ELDEN 2.3 INITRD 56M",
        help="xnu entry title the payload configuration must carry",
    )
    parser.add_argument('--expect-timeout', type=int, default=-1,
                        help='exact expected menu countdown; default keeps the original manual gate')
    parser.add_argument('--expect-default', default='reset', help='exact expected default entry ID')
    args = parser.parse_args()
    if args.expect_timeout != -1 and not 1 <= args.expect_timeout <= 3600:
        raise SystemExit('expected timeout must be -1 or 1..3600 seconds')

    image = args.image.read_bytes()
    fd = args.fd.read_bytes()
    shim = args.shim.read_bytes()

    if image[:8] != b"ANDROID!":
        raise SystemExit("boot image magic is missing")
    kernel_size, ramdisk_size = struct.unpack_from("<II", image, 8)
    header_size, = struct.unpack_from("<I", image, 20)
    header_version, = struct.unpack_from("<I", image, 40)
    expected_header = 1580 if header_version == 3 else 1584
    if header_version not in (3, 4) or header_size != expected_header:
        raise SystemExit(f"unexpected boot header v{header_version}, size {header_size}")
    if header_version == 4:
        signature_size, = struct.unpack_from("<I", image, 1580)
        if signature_size != 0:
            raise SystemExit(f"unexpected v4 boot signature size: {signature_size}")
    kernel = image[PAGE_SIZE : PAGE_SIZE + kernel_size]
    unpacked = gzip.decompress(kernel)
    if unpacked[: len(shim)] != shim:
        raise SystemExit("BootShim bytes differ from the built shim")

    if args.embed_payload:
        if ramdisk_size != 0:
            raise SystemExit(f"embedded payload image still has a ramdisk ({ramdisk_size} bytes)")
        if args.payload is None:
            raise SystemExit("--embed-payload requires --payload")
        payload = args.payload.read_bytes()
        verify_embedded_shim(shim, len(payload))
        if unpacked[len(shim) :] != fd + payload:
            raise SystemExit("kernel payload is not shim + FD + embedded FAT image")
        ramdisk = payload
    else:
        if ramdisk_size == 0:
            raise SystemExit("boot image has no ramdisk")
        if unpacked[len(shim) :] != fd:
            raise SystemExit("firmware volume bytes differ from the build output")
        ramdisk_start = PAGE_SIZE + ((kernel_size + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE
        ramdisk = image[ramdisk_start : ramdisk_start + ramdisk_size]
        if len(ramdisk) != ramdisk_size:
            raise SystemExit("boot image is truncated inside the ramdisk")

    fvmain = verify_fd(fd, args.embed_payload)
    fat_name = verify_ramdisk(
        ramdisk, args.kind, args.expect_kernel_bytes, args.expect_kernel_sha256,
        args.xnu_title,
        args.expect_timeout, args.expect_default,
    )

    entry = {
        "image": str(args.image.resolve().relative_to(ROOT)),
        "image_bytes": len(image),
        "image_sha256": sha256(image),
        "ramdisk_bytes": ramdisk_size,
        "ramdisk_sha256": sha256(ramdisk),
        "embedded_payload": args.embed_payload,
        "kernel_gzip_bytes": kernel_size,
        "fvmain_bytes": len(fvmain),
        "fd_sha256": sha256(fd),
        "shim_bytes": len(shim),
        "kind": args.kind,
        "fat_type": fat_name,
        "kernel_macho_bytes": args.expect_kernel_bytes,
        "kernel_macho_sha256": args.expect_kernel_sha256,
        "header_version": header_version,
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
    print(f"  boot header: v{header_version}, ramdisk {ramdisk_size} bytes")
    print(f"  kernel gzip: {kernel_size} bytes")
    if args.embed_payload:
        print(f"  unpacked: shim {len(shim)} + FD {len(fd)} + payload {len(ramdisk)}")
    else:
        print(f"  unpacked: shim {len(shim)} + FD {len(fd)}")
    print(f"  ramdisk label: {'ELDENPROBE' if args.kind == 'probe' else 'ELDENRAM'}")
    print(f"  FAT type for EnhancedFatDxe: {fat_name}")
    print(f"  decompressed FVMAIN: {len(fvmain)} bytes")
    print("  required FV files: " + ", ".join([*REQUIRED_FV_FILES, PAYLOAD_DRIVER[0]]))
    print("  forbidden FV files absent: " + ", ".join([*FORBIDDEN_FV_FILES, RAMDISK_DRIVER[0]]))
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()
