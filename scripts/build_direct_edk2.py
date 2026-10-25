#!/usr/bin/env python3
"""Build phase-1 firmware directly with the MacPorts LLVM/LLD toolchain."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MU = ROOT / "third_party" / "mu_wide_platforms"
UNIXNU = ROOT / "third_party" / "UniXNU"
BASE = MU / "MU_BASECORE"
BASE_TOOLS = BASE / "BaseTools"
CONF = MU / "Build" / "Conf"
TOOLCHAIN = Path("/opt/local/libexec/llvm-20/bin")
TARGET_DEVICE = "lenovo-y700g4"
FDT_NAME = TARGET_DEVICE.split("-", 1)[1] + ".dtb"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("DEBUG", "RELEASE"), default="DEBUG")
    parser.add_argument("--jobs", default=str(os.cpu_count() or 4))
    parser.add_argument("--toolchain", type=Path, default=TOOLCHAIN)
    parser.add_argument("--crypto-path", type=Path, help="directory containing Driver/Bin/CryptoDriver.inc.dsc")
    parser.add_argument("--unixnu", type=Path, default=UNIXNU)
    parser.add_argument(
        "--define",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="additional EDK II define (repeatable)",
    )
    args = parser.parse_args()

    toolchain = args.toolchain.expanduser().resolve()
    unixnu = args.unixnu.expanduser().resolve()
    for executable in ("clang", "lld-link", "llvm-lib", "llvm-rc"):
        if not os.access(toolchain / executable, os.X_OK):
            raise SystemExit(f"missing executable: {toolchain / executable}")
    if args.crypto_path is None:
        raise SystemExit(
            "pass --crypto-path DIR containing "
            "Driver/Bin/CryptoDriver.inc.dsc; see docs/PHASE1.md"
        )
    crypto = args.crypto_path.expanduser().resolve()
    if not (crypto / "Driver" / "Bin" / "CryptoDriver.inc.dsc").is_file():
        raise SystemExit(f"CryptoDriver.inc.dsc not found under {crypto / 'Driver' / 'Bin'}")
    # EDK II's GenFds turns an absolute path outside WORKSPACE into a malformed
    # workspace-relative path by stripping its leading slash.  Keep the CLI
    # path absolute, but pass a relative path through the EDK II defines.
    crypto_define = os.path.relpath(crypto, MU)

    for executable in ("GenFw", "GenFv", "GenFfs"):
        if not (BASE_TOOLS / "Source" / "C" / "bin" / executable).is_file():
            raise SystemExit(f"BaseTools is missing {executable}; run make first")

    CONF.mkdir(parents=True, exist_ok=True)
    for name in ("target", "tools_def", "build_rule"):
        source = BASE_TOOLS / "Conf" / f"{name}.template"
        destination = CONF / f"{name}.txt"
        if not destination.is_file() or source.read_bytes() != destination.read_bytes():
            shutil.copy2(source, destination)

    packages = [
        MU,
        MU / "Platforms",
        unixnu / "package",
        unixnu / "drivers" / "DarwinBoot",
        BASE,
        MU / "Common" / "MU",
        MU / "Common" / "MU_TIANO",
        MU / "Common" / "MU_TIANO" / "EmbeddedPkg",
        MU / "Common" / "MU_OEM_SAMPLE",
        MU / "Silicon" / "Arm" / "MU_TIANO",
        MU / "Features" / "DFCI",
        MU / "Features" / "CONFIG",
        MU / "Binaries",
        MU / "Silicon" / "QC" / "Sm8750",
        MU / "Platforms" / "CranePkg",
        MU / "Platforms" / "SurfaceDuoACPI",
    ]
    env = dict(os.environ)
    env["WORKSPACE"] = str(MU)
    env["PACKAGES_PATH"] = os.pathsep.join(str(path) for path in packages)
    env["EDK_TOOLS_PATH"] = str(BASE_TOOLS)
    env["CONF_PATH"] = str(CONF)
    env["PYTHON_COMMAND"] = sys.executable
    env["CLANG_BIN"] = str(toolchain) + os.sep
    env["PATH"] = os.pathsep.join(
        [
            str(toolchain),
            str(BASE_TOOLS / "BinWrappers" / "PosixLike"),
            str(BASE_TOOLS / "Source" / "C" / "bin"),
            env.get("PATH", ""),
        ]
    )

    command = [
        str(BASE_TOOLS / "BinWrappers" / "PosixLike" / "build"),
        "-p",
        "PakalaPkg/PakalaNoSb.dsc",
        "-a",
        "AARCH64",
        "-b",
        args.target,
        "-t",
        "CLANGPDB",
        "-n",
        args.jobs,
        "-D",
        f"TARGET_DEVICE={TARGET_DEVICE}",
        "-D",
        f"FDT={FDT_NAME}",
        "-D",
        f"SHARED_CRYPTO_PATH={crypto_define}",
    ]
    for value in args.define:
        command += ["-D", value]
    print("+", " ".join(command))
    subprocess.run(command, cwd=MU, env=env, check=True)


if __name__ == "__main__":
    main()

