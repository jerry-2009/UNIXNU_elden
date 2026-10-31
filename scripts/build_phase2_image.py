#!/usr/bin/env python3
"""Pack a phase-2.3 Android boot image (shim + FD as kernel, FAT ramdisk).

The packaging matches the phase-1 board format (base 0, pagesize 4096,
Android 13.0.0/2023-04-01) and adds the ramdisk field that carries the initrd
FAT volume. --header-version 4 re-labels the v3 header as the Android v4
layout (header size 1584, empty boot signature) for bootloaders that only
accept v4.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import struct
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MU = ROOT / "third_party" / "mu_wide_platforms"
SHIM = MU / "BootShim" / "BootShim.bin"
MBOOTIMG = MU / "Platforms" / "PakalaPkg" / "PythonLibs" / "mkbootimg.py"
OUT = ROOT / "out" / "phase2.3"

KINDS = {
    "probe": (OUT / "probe.img", OUT / "elden-phase2-probe.img"),
    "boot": (OUT / "payload.img", OUT / "elden-phase2-boot.img"),
}


def relabel_v4(path: Path) -> None:
    """Turn the v3 header into a v4 header with an empty boot signature."""
    data = bytearray(path.read_bytes())
    if data[:8] != b"ANDROID!":
        raise SystemExit("mkbootimg did not produce an Android boot image")
    struct.pack_into("<I", data, 20, 1584)
    struct.pack_into("<I", data, 40, 4)
    struct.pack_into("<I", data, 1580, 0)
    path.write_bytes(data)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=tuple(KINDS), required=True)
    parser.add_argument("--fd", type=Path, default=OUT / "SILICIUM_UEFI.fd")
    parser.add_argument("--shim", type=Path, default=SHIM)
    parser.add_argument("--ramdisk", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--header-version", type=int, choices=(3, 4), default=3)
    args = parser.parse_args()

    default_ramdisk, default_output = KINDS[args.kind]
    if args.header_version == 4 and args.output is None:
        default_output = default_output.with_name(
            default_output.stem + "-v4" + default_output.suffix
        )
    ramdisk = (args.ramdisk or default_ramdisk).resolve()
    output = (args.output or default_output).resolve()
    fd = args.fd.resolve()
    shim = args.shim.resolve()

    for path, label in ((fd, "firmware FD"), (shim, "BootShim"), (ramdisk, "ramdisk")):
        if not path.is_file():
            raise SystemExit(f"missing {label}: {path}")

    kernel = OUT / (
        f"kernel-{args.kind}-v4.gzip" if args.header_version == 4
        else f"kernel-{args.kind}.gzip"
    )
    kernel.write_bytes(gzip.compress(shim.read_bytes() + fd.read_bytes(), 9))

    command = [
        sys.executable,
        str(MBOOTIMG),
        "--kernel", str(kernel),
        "--ramdisk", str(ramdisk),
        "-o", str(output),
        "--pagesize", "4096",
        "--header_version", "3",
        "--cmdline", "",
        "--base", "0x0",
        "--os_version", "13.0.0",
        "--os_patch_level", "2023-04-01",
    ]
    print("+ " + " ".join(command))
    subprocess.run(command, check=True)
    if args.header_version == 4:
        relabel_v4(output)

    print(f"image:   {output} ({output.stat().st_size} bytes)")
    print(f"sha256:  {sha256(output)}")
    print(f"kernel:  {kernel} ({kernel.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
