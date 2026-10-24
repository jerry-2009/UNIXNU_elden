#!/usr/bin/env python3
"""Statically validate the elden phase-1 UEFI integration."""

from __future__ import annotations

import re
from pathlib import Path

from make_payload import DEFAULT_OUTPUT, verify_payload


ROOT = Path(__file__).resolve().parents[1]
MU = ROOT / "third_party" / "mu_wide_platforms"
UNIXNU = ROOT / "third_party" / "UniXNU"
DEVICE = MU / "Platforms" / "PakalaPkg" / "Device" / "lenovo-y700g4"


def require_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"missing required file: {path}")


def require_text(path: Path, values: list[str]) -> None:
    text = path.read_text()
    for value in values:
        if value not in text:
            raise SystemExit(f"{path}: missing {value!r}")


def main() -> None:
    required = [
        MU / "BootShim" / "BootShim.S",
        MU / "Platforms" / "EldenPhase1Pkg" / "EldenRamDiskDxe.c",
        MU / "Platforms" / "EldenPhase1Pkg" / "EldenRamDiskDxe.inf",
        DEFAULT_OUTPUT,
        UNIXNU / "package" / "UniXNUPkg" / "Application" / "UniXNU" / "UniXNU.inf",
        UNIXNU / "package" / "UniXNUPkg" / "Driver" / "UniXNUDxe" / "UniXNUDxe.inf",
        UNIXNU / "drivers" / "DarwinBoot" / "DarwinBootPkg" / "Driver" / "DarwinBoot.inf",
    ]
    for path in required:
        require_file(path)

    require_text(
        DEVICE / "DXE.dsc.inc",
        [
            "EldenPhase1Pkg/EldenRamDiskDxe.inf",
            "UniXNUPkg/Application/UniXNU/UniXNU.inf",
            "UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf",
            "DarwinBootPkg/Driver/DarwinBoot.inf",
        ],
    )
    require_text(
        DEVICE / "DXE.inc",
        [
            "6A6B6F43-2AE5-4A7E-9C4E-7C9A9136D2B0",
            "EldenPhase1Pkg/Payload/payload.img",
            "UniXNUPkg/Application/UniXNU/UniXNU.inf",
            "DarwinBootPkg/Driver/DarwinBoot.inf",
        ],
    )
    require_text(DEVICE / "APRIORI.inc", ["EldenPhase1Pkg/EldenRamDiskDxe.inf"])

    driver = (MU / "Platforms" / "EldenPhase1Pkg" / "EldenRamDiskDxe.c").read_text()
    guid_source = re.search(
        r"gEldenPayloadFvFileGuid\s*=\s*\{([^}]+)\}", driver, re.MULTILINE
    )
    if not guid_source:
        raise SystemExit("cannot find embedded payload GUID")
    if "6a6b6f43" not in guid_source.group(1).lower():
        raise SystemExit("payload GUID in driver and FDF differ")

    verify_payload(DEFAULT_OUTPUT)
    print("phase1 layout: OK")
    print("  embedded FAT: EFI/UniXNU/unixnu.toml")
    print("  firmware modules: UniXNU, UniXNUDxe, DarwinBoot, EldenRamDiskDxe")
    print("  storage dependency for menu: none")


if __name__ == "__main__":
    main()

