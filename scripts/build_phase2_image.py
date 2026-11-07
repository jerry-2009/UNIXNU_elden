#!/usr/bin/env python3
"""Pack a phase-2.3 Android boot image.

Two layouts are supported:

* ramdisk (default): kernel = gzip(shim + FD), the FAT volume travels in the
  Android ramdisk field;
* --embed-payload: kernel = gzip(shim + FD + payload), the ramdisk field is
  empty.  BootShim learns the payload size at build time, advertises it in its
  ARM64 header and passes base/size to the firmware, which publishes the FAT
  image through a HOB.  This matches the SM8750 ports whose ABL replaces or
  ignores the ramdisk field.

--header-version 4 re-labels the v3 header as the Android v4 layout (header
size 1584, empty boot signature).
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
CLANG = "/opt/local/libexec/llvm-20/bin/clang"

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
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--header-version", type=int, choices=(3, 4), default=3)
    parser.add_argument("--embed-payload", action="store_true")
    parser.add_argument("--entry-fdt-mailbox", action="store_true")
    parser.add_argument("--work", type=Path, default=OUT,
                        help="directory for the generated shim and kernel gzip")
    parser.add_argument("--clang", default=CLANG)
    args = parser.parse_args()
    if args.entry_fdt_mailbox and not args.embed_payload:
        parser.error("--entry-fdt-mailbox requires --embed-payload")

    default_ramdisk, default_output = KINDS[args.kind]
    if args.embed_payload:
        default_output = default_output.with_name(
            f"elden-phase2-embed-{args.kind}.img"
        )
    elif args.header_version == 4 and args.output is None:
        default_output = default_output.with_name(
            default_output.stem + "-v4" + default_output.suffix
        )
    output = (args.output or default_output).resolve()
    fd = args.fd.resolve()
    if not fd.is_file():
        raise SystemExit(f"missing firmware FD: {fd}")
    if fd.stat().st_size != 0x400000:
        raise SystemExit("BootShim requires an exactly 4 MiB firmware FD")
    output.parent.mkdir(parents=True, exist_ok=True)
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)

    if args.embed_payload:
        payload = (args.payload or default_ramdisk).resolve()
        if not payload.is_file():
            raise SystemExit(f"missing payload: {payload}")
        if args.entry_fdt_mailbox:
            with payload.open('rb') as source:
                source.seek(0x1c0)
                record = source.read(24)
            if record != b'ELDFDT01' + struct.pack('<IIQ', 1, 0, 0):
                raise SystemExit('RAM FAT must reserve the empty ELDFDT01 mailbox before shim construction')
        shim = work / f"shim-{args.kind}-embed.bin"
        command = [
            sys.executable,
            str(ROOT / "scripts" / "build_boot_shim.py"),
            "--payload-bytes", str(payload.stat().st_size),
            "--output", str(shim),
            "--clang", args.clang,
        ]
        if args.entry_fdt_mailbox:
            command.append("--entry-fdt-mailbox")
        print("+ " + " ".join(command))
        subprocess.run(command, check=True)
        kernel_bytes = shim.read_bytes() + fd.read_bytes() + payload.read_bytes()
        kernel = work / f"kernel-{args.kind}-embed.gzip"
        kernel.write_bytes(gzip.compress(kernel_bytes, 9, mtime=0))
        ramdisk = None
    else:
        if not args.shim.is_file():
            raise SystemExit(f"missing BootShim: {args.shim}")
        shim = args.shim.resolve()
        ramdisk = (args.ramdisk or default_ramdisk).resolve()
        if not ramdisk.is_file():
            raise SystemExit(f"missing ramdisk: {ramdisk}")
        kernel = work / (
            f"kernel-{args.kind}-v4.gzip" if args.header_version == 4
            else f"kernel-{args.kind}.gzip"
        )
        kernel.write_bytes(gzip.compress(shim.read_bytes() + fd.read_bytes(), 9, mtime=0))

    command = [
        sys.executable,
        str(MBOOTIMG),
        "--kernel", str(kernel),
        "-o", str(output),
        "--pagesize", "4096",
        "--header_version", "3",
        "--cmdline", "",
        "--base", "0x0",
        "--os_version", "13.0.0",
        "--os_patch_level", "2023-04-01",
    ]
    if ramdisk is not None:
        command.extend(["--ramdisk", str(ramdisk)])
    print("+ " + " ".join(command))
    subprocess.run(command, check=True)
    if args.header_version == 4 or args.embed_payload:
        relabel_v4(output)

    print(f"image:   {output} ({output.stat().st_size} bytes)")
    print(f"sha256:  {sha256(output)}")
    print(f"kernel:  {kernel} ({kernel.stat().st_size} bytes)")
    if args.embed_payload:
        print(f"payload: {payload} ({payload.stat().st_size} bytes, embedded)")


if __name__ == "__main__":
    main()
