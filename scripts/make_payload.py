#!/usr/bin/env python3
"""Build and verify the small FAT16 RAM payload used by elden phase 1.

The image contains only ``EFI/UniXNU/unixnu.toml`` and a marker file.  It is
embedded in the firmware volume and published by EldenRamDiskDxe, so neither
UFS nor a writable Android partition participates in the phase-1 boot.
"""

from __future__ import annotations

import argparse
import math
import shutil
import struct
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "package" / "unixnu.toml"
DEFAULT_OUTPUT = (
    ROOT
    / "third_party"
    / "mu_wide_platforms"
    / "Platforms"
    / "EldenPhase1Pkg"
    / "Payload"
    / "payload.img"
)

BYTES_PER_SECTOR = 512
SECTORS_PER_CLUSTER = 1
RESERVED_SECTORS = 1
NUMBER_OF_FATS = 2
ROOT_ENTRY_COUNT = 512
ROOT_DIR_SECTORS = ROOT_ENTRY_COUNT * 32 // BYTES_PER_SECTOR
VOLUME_LABEL = b"ELDENRAM"
CONFIG_IMAGE_PATH = "EFI/UniXNU/unixnu.toml"


class Fat16Builder:
    def __init__(self, total_sectors: int) -> None:
        self.total_sectors = total_sectors
        self.fat_sectors = self._choose_fat_size()
        data_sectors = (
            total_sectors
            - RESERVED_SECTORS
            - NUMBER_OF_FATS * self.fat_sectors
            - ROOT_DIR_SECTORS
        )
        self.cluster_count = data_sectors // SECTORS_PER_CLUSTER
        if not 4085 <= self.cluster_count <= 65524:
            raise ValueError("image geometry does not produce a FAT16 volume")

        self.image = bytearray(total_sectors * BYTES_PER_SECTOR)
        self.fat = [0] * (self.fat_sectors * BYTES_PER_SECTOR // 2)
        self.fat[0] = 0xFFF8
        self.fat[1] = 0xFFFF
        self.next_cluster = 2
        self.root_dir_offset = (RESERVED_SECTORS + NUMBER_OF_FATS * self.fat_sectors) * BYTES_PER_SECTOR
        self.data_offset = self.root_dir_offset + ROOT_DIR_SECTORS * BYTES_PER_SECTOR
        self._write_boot_sector()

    def _choose_fat_size(self) -> int:
        for fat_sectors in range(1, self.total_sectors // 8):
            data_sectors = (
                self.total_sectors
                - RESERVED_SECTORS
                - NUMBER_OF_FATS * fat_sectors
                - ROOT_DIR_SECTORS
            )
            clusters = data_sectors // SECTORS_PER_CLUSTER
            capacity = fat_sectors * BYTES_PER_SECTOR // 2
            if 4085 <= clusters <= 65524 and clusters <= capacity:
                return fat_sectors
        raise ValueError("cannot select a FAT16 geometry")

    def _write_boot_sector(self) -> None:
        boot = bytearray(BYTES_PER_SECTOR)
        boot[0:3] = b"\xEB\x3C\x90"
        boot[3:11] = b"MSWIN4.1"
        struct.pack_into("<H", boot, 11, BYTES_PER_SECTOR)
        boot[13] = SECTORS_PER_CLUSTER
        struct.pack_into("<H", boot, 14, RESERVED_SECTORS)
        boot[16] = NUMBER_OF_FATS
        struct.pack_into("<H", boot, 17, ROOT_ENTRY_COUNT)
        if self.total_sectors < 65536:
            struct.pack_into("<H", boot, 19, self.total_sectors)
        else:
            struct.pack_into("<I", boot, 32, self.total_sectors)
        boot[21] = 0xF8
        struct.pack_into("<H", boot, 22, self.fat_sectors)
        struct.pack_into("<H", boot, 24, 32)
        struct.pack_into("<H", boot, 26, 64)
        struct.pack_into("<I", boot, 28, 0)
        boot[36] = 0x80
        boot[38] = 0x29
        struct.pack_into("<I", boot, 39, 0x454C444E)
        boot[43:54] = VOLUME_LABEL.ljust(11, b" ")
        boot[54:62] = b"FAT16   "
        boot[510:512] = b"\x55\xAA"
        self.image[:BYTES_PER_SECTOR] = boot

    def _allocate(self, data: bytes) -> int:
        cluster_count = max(1, math.ceil(len(data) / (BYTES_PER_SECTOR * SECTORS_PER_CLUSTER)))
        first = self.next_cluster
        if first + cluster_count - 1 > self.cluster_count + 1:
            raise ValueError("payload image is too small")
        for index in range(cluster_count):
            cluster = first + index
            self.fat[cluster] = cluster + 1 if index + 1 < cluster_count else 0xFFFF
        offset = self.data_offset + (first - 2) * BYTES_PER_SECTOR * SECTORS_PER_CLUSTER
        self.image[offset : offset + len(data)] = data
        self.next_cluster += cluster_count
        return first

    @staticmethod
    def _short_name(name: str) -> bytes:
        if name == ".":
            return b"." + b" " * 10
        if name == "..":
            return b".." + b" " * 9
        if "." in name:
            stem, suffix = name.rsplit(".", 1)
        else:
            stem, suffix = name, ""
        stem = stem.upper()
        suffix = suffix.upper()
        if len(stem) > 8 or len(suffix) > 3:
            raise ValueError(f"{name!r} is not an 8.3 FAT name")
        return stem.encode("ascii").ljust(8, b" ") + suffix.encode("ascii").ljust(3, b" ")

    def _direntry(self, name: str, attr: int, first_cluster: int, size: int) -> bytes:
        entry = bytearray(32)
        entry[0:11] = self._short_name(name)
        entry[11] = attr
        # Fixed timestamp: 2026-10-25 00:00:00, for reproducible images.
        struct.pack_into("<H", entry, 14, 0)
        struct.pack_into("<H", entry, 16, (46 << 9) | (10 << 5) | 25)
        struct.pack_into("<H", entry, 18, 0)
        struct.pack_into("<H", entry, 20, 0)
        struct.pack_into("<H", entry, 22, (46 << 9) | (10 << 5) | 25)
        struct.pack_into("<H", entry, 26, first_cluster)
        struct.pack_into("<I", entry, 28, size)
        return bytes(entry)

    def _write_directory(self, parent_cluster: int, entries: list[bytes]) -> int:
        data = bytearray()
        data += self._direntry(".", 0x10, parent_cluster, 0)
        data += self._direntry("..", 0x10, 0 if parent_cluster == 0 else 0, 0)
        for entry in entries:
            data += entry
        return self._allocate(bytes(data))

    def add_file(self, parent_cluster: int, name: str, data: bytes) -> int:
        cluster = self._allocate(data)
        directory = self._read_cluster(parent_cluster)
        free = self._first_free_entry(directory)
        directory[free : free + 32] = self._direntry(name, 0x20, cluster, len(data))
        self._write_cluster(parent_cluster, directory)
        return cluster

    def add_directory(self, parent_cluster: int, name: str) -> int:
        cluster = self.next_cluster
        directory = bytearray()
        directory += self._direntry(".", 0x10, cluster, 0)
        directory += self._direntry("..", 0x10, parent_cluster, 0)
        self._allocate(bytes(directory))
        parent = self._read_cluster(parent_cluster)
        free = self._first_free_entry(parent)
        parent[free : free + 32] = self._direntry(name, 0x10, cluster, 0)
        self._write_cluster(parent_cluster, parent)
        return cluster

    def _read_cluster(self, cluster: int) -> bytearray:
        if cluster == 0:
            start = self.root_dir_offset
            return bytearray(self.image[start : start + ROOT_DIR_SECTORS * BYTES_PER_SECTOR])
        offset = self.data_offset + (cluster - 2) * BYTES_PER_SECTOR
        return bytearray(self.image[offset : offset + BYTES_PER_SECTOR])

    def _write_cluster(self, cluster: int, data: bytes) -> None:
        if cluster == 0:
            start = self.root_dir_offset
            length = ROOT_DIR_SECTORS * BYTES_PER_SECTOR
        else:
            start = self.data_offset + (cluster - 2) * BYTES_PER_SECTOR
            length = BYTES_PER_SECTOR
        self.image[start : start + length] = data[:length].ljust(length, b"\x00")

    def _first_free_entry(self, directory: bytearray) -> int:
        for offset in range(0, len(directory), 32):
            if directory[offset] in (0x00, 0xE5):
                return offset
        raise ValueError("directory is full")

    def finish(self) -> bytes:
        fat_bytes = struct.pack(f"<{len(self.fat)}H", *self.fat)
        for index in range(NUMBER_OF_FATS):
            offset = (RESERVED_SECTORS + index * self.fat_sectors) * BYTES_PER_SECTOR
            self.image[offset : offset + len(fat_bytes)] = fat_bytes
        return bytes(self.image)


def build_payload(config_path: Path, output: Path, size_mib: int) -> None:
    if size_mib < 2:
        raise ValueError("payload image must be at least 2 MiB")
    total_sectors = size_mib * 1024 * 1024 // BYTES_PER_SECTOR
    builder = Fat16Builder(total_sectors)
    builder.add_file(0, "PAYLOAD.TXT", b"ELDEN PHASE1 RAM PAYLOAD\n")
    efi = builder.add_directory(0, "EFI")
    builder.add_directory(efi, "UNIXNU")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(builder.finish())
    add_long_name_file(output, config_path, CONFIG_IMAGE_PATH)


def verify_payload(path: Path) -> None:
    image = path.read_bytes()
    if image[510:512] != b"\x55\xAA":
        raise ValueError("missing FAT boot signature")
    if image[54:62] != b"FAT16   ":
        raise ValueError("not a FAT16 image")
    for required in (b"EFI        ", b"UNIXNU     ", b"PAYLOAD TXT"):
        if required not in image:
            raise ValueError(f"missing directory entry {required!r}")
    actual = read_image_file(path, CONFIG_IMAGE_PATH)
    expected = DEFAULT_CONFIG.read_bytes()
    if actual != expected:
        raise ValueError("EFI/UniXNU/unixnu.toml content does not match the source")


def mtools_tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise SystemExit(f"missing required mtools command: {name}")
    return executable


def add_long_name_file(image: Path, source: Path, image_path: str) -> None:
    subprocess.run(
        [
            mtools_tool("mcopy"),
            "-i",
            str(image),
            "-o",
            str(source),
            f"::{image_path}",
        ],
        check=True,
    )


def read_image_file(image: Path, image_path: str) -> bytes:
    result = subprocess.run(
        [mtools_tool("mtype"), "-i", str(image), f"::{image_path}"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--size-mib", type=int, default=4)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        verify_payload(args.output)
        print(f"verified: {args.output}")
        return
    build_payload(args.config, args.output, args.size_mib)
    verify_payload(args.output)
    print(f"payload: {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

