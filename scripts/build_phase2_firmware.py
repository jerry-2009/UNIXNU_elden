#!/usr/bin/env python3
"""Build the phase-2.3 firmware: initrd RAM-disk channel, no embedded payload.

The phase-1 firmware (out/, 4 MiB FD with the embedded ELDENRAM volume) is not
touched.  The build defines ELDEN_PHASE2, which:

  * drops EldenRamDiskDxe and the embedded payload image from the FDF,
  * adds UniXNURamDiskDxe to the DXE FV,
  * compiles the PrePi FDT handoff into SEC.

The output FD is copied to out/phase2.3/ together with a small manifest.  This
script never invokes fastboot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from build_direct_edk2 import TOOLCHAIN


ROOT = Path(__file__).resolve().parents[1]
MU = ROOT / "third_party" / "mu_wide_platforms"
OUT = ROOT / "out" / "phase2.3"


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+ " + " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("DEBUG", "RELEASE"), default="DEBUG")
    parser.add_argument("--toolchain", type=Path, default=TOOLCHAIN)
    parser.add_argument(
        "--crypto-path",
        type=Path,
        required=True,
        help="directory containing Driver/Bin/CryptoDriver.inc.dsc",
    )
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument(
        "--keep-build-tree",
        action="store_true",
        help="do not delete the previous EDK II output directory",
    )
    args = parser.parse_args()

    build_dir = MU / "Build" / "PakalaPkg" / f"{args.target}_CLANGPDB"
    if build_dir.exists() and not args.keep_build_tree:
        print(f"remove stale build tree: {build_dir}")
        shutil.rmtree(build_dir)

    run([
        sys.executable,
        str(ROOT / "scripts" / "build_boot_shim.py"),
        "--clang",
        str(args.toolchain.expanduser().resolve() / "clang"),
    ])
    run([
        sys.executable,
        str(ROOT / "scripts" / "build_direct_edk2.py"),
        "--target", args.target,
        "--toolchain", str(args.toolchain),
        "--crypto-path", str(args.crypto_path),
        "--jobs", str(args.jobs),
        "--define", "ELDEN_PHASE2=1",
    ])

    fd = build_dir / "FV" / "SM8750_EFI.fd"
    if not fd.is_file():
        raise SystemExit(f"build finished without expected artifact: {fd}")
    if fd.stat().st_size != 0x400000:
        raise SystemExit(f"{fd} is {fd.stat().st_size} bytes, expected 0x400000")

    OUT.mkdir(parents=True, exist_ok=True)
    destination = OUT / "SILICIUM_UEFI.fd"
    destination.write_bytes(fd.read_bytes())
    report = {
        "schema": "unixnu-elden-phase2.3-firmware/v1",
        "defines": {"ELDEN_PHASE2": "1", "ELDEN_INITRD_HANDOFF": "1"},
        "artifacts": {
            str(destination.relative_to(ROOT)): {
                "bytes": destination.stat().st_size,
                "sha256": sha256(destination),
            }
        },
    }
    report_path = OUT / "firmware.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"firmware: {destination} ({sha256(destination)})")
    print(f"report:   {report_path}")


if __name__ == "__main__":
    main()
