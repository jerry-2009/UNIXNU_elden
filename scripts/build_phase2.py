#!/usr/bin/env python3
"""Build the elden phase-2 RAM-boot image.

The payload is carried as the Android boot-image ramdisk.  UniXNURamDiskDxe
publishes it from the FDT initrd handoff, so the verified phase-1 4 MiB
firmware image remains unchanged.  This script never invokes fastboot.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MU = ROOT / "third_party" / "mu_wide_platforms"
OUT = ROOT / "out"
BUILD_LOG = OUT / "phase2-build.log"
EXPECTED_KERNEL_SHA256 = "6912319adf0b623eb04987f2dbd29c4b5c9f97ca18b469571bd67c7815c86c07"


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


def find_dtc(explicit: Path | None) -> Path:
    if explicit:
        candidate = explicit.expanduser().resolve()
    else:
        installed = shutil.which("dtc")
        candidate = Path(installed) if installed else ROOT / ".cache" / "dtc-src" / "dtc"
    if not candidate.is_file():
        raise SystemExit("dtc not found; pass --dtc or install dtc")
    return candidate


def build_payload(
    unixnu: Path,
    kernel: Path,
    unique_chip_id: str,
    dtc: Path,
) -> tuple[Path, Path]:
    sys.path.insert(0, str(unixnu / "scripts"))
    from unixnu import payload as unixnu_payload
    from unixnu.cli import parser as cli_parser
    from unixnu.config import Context

    args = cli_parser().parse_args(
        [
            "payload",
            "-D",
            str(ROOT),
            "--kernel",
            str(kernel),
            "--unique-chip-id",
            unique_chip_id,
        ]
    )
    context = Context(args)
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join([str(dtc.parent), original_path])
    try:
        image = unixnu_payload.build(context, kernel=kernel)
    finally:
        os.environ["PATH"] = original_path
    report = unixnu_payload.paths(context)[2]
    return image, report


def write_report(paths: list[Path], test_seed: bool) -> Path:
    report = {
        "schema": "unixnu-elden-phase2-build/v1",
        "device": {"codename": "elden", "model_id": "TB322FC", "soc": "SM8750P"},
        "payload_transport": "android-boot-v3-ramdisk",
        "platform_seed_source": "host-test-only" if test_seed else "caller-supplied-device-seed",
        "device_ready": False,
        "test_policy": {
            "boot_operator": "device_owner",
            "ram_boot_only": True,
            "require_two_consecutive_boots": True,
            "hardware_tested": False,
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
    path = OUT / "phase2-build.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return path


def prepare_unixnu_package(unixnu: Path) -> Path:
    """Copy the current package and repair its undeclared EmbeddedPkg dependency."""
    root = OUT / "phase2-unixnu"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(unixnu / "package", root / "package")
    info = root / "package" / "UniXNUPkg" / "Library" / "UniXNULib" / "UniXNULib.inf"
    contents = info.read_text()
    if "EmbeddedPkg/EmbeddedPkg.dec" not in contents:
        contents = contents.replace(
            "  MdePkg/MdePkg.dec\n",
            "  MdePkg/MdePkg.dec\n  EmbeddedPkg/EmbeddedPkg.dec\n",
            1,
        )
        info.write_text(contents)
    overlay = ROOT / "patches" / "overlays" / "UniXNU" / "package" / "UniXNUPkg"
    shutil.copy2(
        overlay / "Library" / "UniXNULib" / "Inject.c",
        root / "package" / "UniXNUPkg" / "Library" / "UniXNULib" / "Inject.c",
    )
    ramdisk = (
        root
        / "package"
        / "UniXNUPkg"
        / "Driver"
        / "UniXNURamDiskDxe"
        / "UniXNURamDiskDxe.c"
    )
    ramdisk_info = ramdisk.with_suffix(".inf")
    info_text = ramdisk_info.read_text()
    if "EmbeddedPkg/EmbeddedPkg.dec" not in info_text:
        ramdisk_info.write_text(
            info_text.replace(
                "  MdePkg/MdePkg.dec\n",
                "  MdePkg/MdePkg.dec\n  EmbeddedPkg/EmbeddedPkg.dec\n",
                1,
            )
        )
    source = ramdisk.read_text()
    replacements = {
        "#include <Library/FdtLib.h>": "#include <libfdt.h>",
        "FdtPathOffset (": "fdt_path_offset (",
        "FdtGetProp (": "fdt_getprop (",
        "FdtCheckHeader (": "fdt_check_header (",
        "FdtTotalSize (": "fdt_totalsize (",
        "Fdt32ToCpu (": "fdt32_to_cpu (",
        "Fdt64ToCpu (": "fdt64_to_cpu (",
    }
    for old, new in replacements.items():
        source = source.replace(old, new)
    ramdisk.write_text(source)
    drivers = root / "drivers"
    drivers.mkdir()
    os.symlink(unixnu / "drivers" / "DarwinBoot", drivers / "DarwinBoot", target_is_directory=True)
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True, help="prelinked kernel.macho")
    parser.add_argument("--unique-chip-id", required=True, help="per-device hexadecimal platform seed")
    parser.add_argument(
        "--unixnu",
        type=Path,
        default=Path(os.environ.get("UNIXNU_DIR", ROOT.parent / "UniXNU")),
        help="current UniXNU checkout containing UniXNURamDiskDxe",
    )
    parser.add_argument("--crypto-path", type=Path, help="directory containing Driver/Bin/CryptoDriver.inc.dsc")
    parser.add_argument(
        "--test-seed",
        action="store_true",
        help="mark the supplied platform seed as a host test value, not a device identity",
    )
    parser.add_argument("--toolchain", type=Path, default=Path("/opt/local/libexec/llvm-20/bin"))
    parser.add_argument("--dtc", type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()

    kernel = args.kernel.expanduser().resolve()
    if not kernel.is_file():
        raise SystemExit(f"kernel not found: {kernel}")
    actual_kernel_hash = sha256(kernel)
    if actual_kernel_hash != EXPECTED_KERNEL_SHA256:
        raise SystemExit(
            f"unexpected prelinked kernel sha256: {actual_kernel_hash}; "
            f"expected {EXPECTED_KERNEL_SHA256}"
        )
    try:
        seed = int(args.unique_chip_id, 16)
    except ValueError as error:
        raise SystemExit("--unique-chip-id must be hexadecimal") from error
    if not 0 < seed < 1 << 64:
        raise SystemExit("--unique-chip-id must be a nonzero u64")
    if not args.prepare_only and args.crypto_path is None:
        parser.error("full build requires --crypto-path; see docs/PHASE1.md")

    unixnu = args.unixnu.expanduser().resolve()
    if not (unixnu / "package" / "UniXNUPkg" / "Driver" / "UniXNURamDiskDxe" / "UniXNURamDiskDxe.inf").is_file():
        raise SystemExit(f"{unixnu} has no shared UniXNURamDiskDxe")

    OUT.mkdir(parents=True, exist_ok=True)
    BUILD_LOG.write_text("", encoding="utf-8")
    run([sys.executable, str(ROOT / "scripts" / "bootstrap_third_party.py")])
    run([sys.executable, str(ROOT / "scripts" / "build_boot_shim.py"), "--clang", str(args.toolchain / "clang")])

    dtc = find_dtc(args.dtc)
    dtb = OUT / "elden-phase2.dtb"
    run(
        [
            str(dtc),
            "-I",
            "dts",
            "-O",
            "dtb",
            "-i",
            str(ROOT / "soc" / "sm8750" / "dts"),
            "-o",
            str(dtb),
            str(ROOT / "dts" / "elden.dts"),
        ]
    )

    payload_source, payload_report_source = build_payload(
        unixnu, kernel, args.unique_chip_id, dtc
    )
    payload = OUT / "elden-phase2-payload.img"
    payload_report = OUT / "elden-phase2-payload.json"
    shutil.copy2(payload_source, payload)
    shutil.copy2(payload_report_source, payload_report)

    copied = [dtb, payload, payload_report]
    if not args.prepare_only:
        phase2_unixnu = prepare_unixnu_package(unixnu)
        run(
            [
                sys.executable,
                str(ROOT / "scripts" / "build_direct_edk2.py"),
                "--target",
                "DEBUG",
                "--toolchain",
                str(args.toolchain),
                "--crypto-path",
                str(args.crypto_path),
                "--jobs",
                str(args.jobs),
                "--unixnu",
                str(phase2_unixnu),
                "--define",
                "ELDEN_USE_RAMDISK=TRUE",
            ]
        )
        fd_source = MU / "Build" / "PakalaPkg" / "DEBUG_CLANGPDB" / "FV" / "SM8750_EFI.fd"
        fd = OUT / "SILICIUM_UEFI-phase2.fd"
        shim = MU / "BootShim" / "BootShim.bin"
        image = OUT / "elden-phase2.img"
        shutil.copy2(fd_source, fd)

        with tempfile.TemporaryDirectory(prefix="elden-phase2-") as temporary:
            temp = Path(temporary)
            kernel_section = temp / "Image.gz-dtb"
            kernel_section.write_bytes(gzip.compress(shim.read_bytes() + fd_source.read_bytes(), compresslevel=9, mtime=0) + dtb.read_bytes())
            run(
                [
                    sys.executable,
                    str(MU / "Platforms" / "PakalaPkg" / "PythonLibs" / "mkbootimg.py"),
                    "--kernel",
                    str(kernel_section),
                    "--ramdisk",
                    str(payload),
                    "-o",
                    str(image),
                    "--pagesize",
                    "4096",
                    "--header_version",
                    "3",
                    "--cmdline",
                    "",
                    "--base",
                    "0x0",
                    "--os_version",
                    "13.0.0",
                    "--os_patch_level",
                    "2023-04-01",
                ]
            )
        run(
            [
                sys.executable,
                str(ROOT / "scripts" / "verify_phase2_artifact.py"),
                "--image",
                str(image),
                "--fd",
                str(fd),
                "--bootshim",
                str(shim),
                "--payload",
                str(payload),
                "--dtb",
                str(dtb),
                "--kernel",
                str(kernel),
            ]
        )
        copied += [fd, image]

    report = write_report(copied, args.test_seed)
    print(f"report: {report}")
    for path in copied:
        print(f"sha256 {sha256(path)}  {path}")


if __name__ == "__main__":
    main()
