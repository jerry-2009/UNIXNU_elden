#!/usr/bin/env python3
"""Prepare and build the elden phase-1 RAM-boot image.

The script never invokes fastboot.  The owner performs the RAM boot manually,
records the SHA-256 twice, and follows docs/PHASE1.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from build_direct_edk2 import TOOLCHAIN


ROOT = Path(__file__).resolve().parents[1]
MU = ROOT / "third_party" / "mu_wide_platforms"
UNIXNU = ROOT / "third_party" / "UniXNU"
OUT = ROOT / "out"
BUILD_LOG = OUT / "phase1-build.log"


def run(command: list[str], *, cwd: Path | None = None) -> None:
    command_line = "+ " + " ".join(command)
    print(command_line)
    with BUILD_LOG.open("a", encoding="utf-8") as log:
        log.write(command_line + "\n")
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log.write(line)
        return_code = process.wait()
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, command)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_report(paths: list[Path]) -> Path:
    report = {
        "schema": "unixnu-elden-phase1-build/v1",
        "device": {"codename": "elden", "model_id": "TB322FC", "soc": "SM8750P"},
        "test_policy": {
            "boot_operator": "device_owner",
            "ram_boot_only": True,
            "require_two_consecutive_boots": True,
        },
        "artifacts": {
            str(path.relative_to(ROOT)): {
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in paths
            if path.is_file()
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / "build.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--skip-submodules", action="store_true")
    parser.add_argument("--target", choices=("DEBUG", "RELEASE"), default="DEBUG")
    parser.add_argument("--toolchain", type=Path, default=TOOLCHAIN)
    parser.add_argument("--crypto-path", type=Path, help="directory containing Driver/Bin/CryptoDriver.inc.dsc")
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()

    if not args.prepare_only and args.crypto_path is None:
        parser.error("full build requires --crypto-path; see docs/PHASE1.md")

    OUT.mkdir(parents=True, exist_ok=True)
    BUILD_LOG.write_text("", encoding="utf-8")

    if not args.skip_submodules:
        run(
            ["git", "submodule", "update", "--init", "--depth", "1", "drivers/DarwinBoot"],
            cwd=UNIXNU,
        )

    run([sys.executable, str(ROOT / "scripts" / "make_payload.py")])
    run([
        sys.executable,
        str(ROOT / "scripts" / "build_boot_shim.py"),
        "--clang",
        str(args.toolchain.expanduser().resolve() / "clang"),
    ])
    run([sys.executable, str(ROOT / "scripts" / "verify_layout.py")])

    fd = MU / "Build" / "PakalaPkg" / f"{args.target}_CLANGPDB" / "FV" / "SM8750_EFI.fd"
    image = MU / "Build" / "PakalaPkg" / "lenovo-y700g4.img"
    if not args.prepare_only:
        run(
            [
                sys.executable,
                str(ROOT / "scripts" / "build_direct_edk2.py"),
                "--target", args.target,
                "--toolchain", str(args.toolchain),
                "--crypto-path", str(args.crypto_path),
                "--jobs", str(args.jobs),
                "--define", "ELDEN_USE_RAMDISK=FALSE",
            ]
        )
        # Preserve the board's Android v3 packaging after the direct EDK II build.
        sys.path.insert(0, str(MU / "Platforms" / "PakalaPkg" / "PythonLibs"))
        from PostBuild import makeAndroidImage

        makeAndroidImage(
            str(fd.parent.parent), str(image.parent), str(MU), "lenovo-y700g4", ""
        )
        run(
            [
                sys.executable,
                str(ROOT / "scripts" / "verify_artifact.py"),
                "--fd",
                str(fd),
                "--image",
                str(image),
            ]
        )

    OUT.mkdir(parents=True, exist_ok=True)
    copied = []
    products = [] if args.prepare_only else [
        (fd, "SILICIUM_UEFI.fd"),
        (image, "elden-phase1.img"),
    ]
    for source, name in products:
        if source.is_file():
            destination = OUT / name
            destination.write_bytes(source.read_bytes())
            copied.append(destination)
        elif not args.prepare_only:
            raise SystemExit(f"build finished without expected artifact: {source}")

    copied.append(MU / "Platforms" / "EldenPhase1Pkg" / "Payload" / "payload.img")
    report = write_report(copied)
    print(f"report: {report}")
    if copied:
        for path in copied:
            print(f"sha256 {sha256(path)}  {path}")


if __name__ == "__main__":
    main()

