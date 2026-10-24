#!/usr/bin/env python3
"""Prepare pinned third-party checkouts for the elden firmware build."""

from __future__ import annotations

import argparse
import filecmp
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THIRD_PARTY = ROOT / "third_party"
OVERLAYS = ROOT / "patches" / "overlays"
DRIVERS = ROOT / "drivers"


@dataclass(frozen=True)
class Dependency:
    path: str
    url: str
    commit: str
    purpose: str


DEPENDENCIES = {
    "UniXNU": Dependency(
        "UniXNU",
        "https://github.com/UniXNU/UniXNU.git",
        "c62bf12595f9a86c1b7282cf12d5af40b441fdac",
        "boot manager, DarwinBoot, and common drivers",
    ),
    "UniXNU-piano": Dependency(
        "UniXNU-piano",
        "https://github.com/code002-2/UniXNU-piano.git",
        "98b3f94a067aff93a9296de7b80fdddc03dae380",
        "same-SoC menu and payload reference",
    ),
    "mu_wide_platforms": Dependency(
        "mu_wide_platforms",
        "https://github.com/sunflower2333/mu_wide_platforms.git",
        "3e1d052064beb6e59cda3cfba87d50e6cc088174",
        "UEFI baseline with lenovo-y700g4",
    ),
    "elden-linux": Dependency(
        "elden-linux",
        "https://github.com/xiaquwan1001/lenovo-legion-y700-gen4-tb322fc-elden-linux.git",
        "2ea1a67cad14032e3c9c5d1c61e4ee92ad30742b",
        "device constants and Linux bring-up evidence",
    ),
    "UniXNU-sheng": Dependency(
        "UniXNU-sheng",
        "https://github.com/UniXNU/UniXNU-sheng.git",
        "251b291adf941b9953fe3ae66a808b9b626e164d",
        "driver integration reference",
    ),
    "Project-SunUEFI": Dependency(
        "Project-SunUEFI",
        "https://github.com/slwyts/Project-SunUEFI.git",
        "2d4752a1455f6448ec0d300aece28ec6eb148b20",
        "SM8750 firmware integration reference",
    ),
}

BUILD_DEPENDENCIES = ("UniXNU", "mu_wide_platforms")


def git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def ensure_dependency(name: str) -> None:
    dependency = DEPENDENCIES[name]
    destination = THIRD_PARTY / dependency.path

    if destination.exists() and not (destination / ".git").exists():
        raise SystemExit(
            f"{destination} exists but is not a Git checkout; "
            "move it aside and retry"
        )

    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        print(f"clone {name}: {dependency.url}")
        subprocess.run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                dependency.url,
                str(destination),
            ],
            check=True,
        )
        git(destination, "fetch", "--depth", "1", "origin", dependency.commit)
        git(destination, "checkout", "--detach", "FETCH_HEAD")
        return

    head = git(destination, "rev-parse", "HEAD")
    if head == dependency.commit:
        print(f"ok    {name}: {dependency.commit}")
        return

    print(
        f"warn  {name}: HEAD is {head}, expected {dependency.commit}; "
        "leaving the existing checkout untouched"
    )


def overlay_files(name: str) -> list[tuple[Path, Path]]:
    source_root = OVERLAYS / name
    target_root = THIRD_PARTY / DEPENDENCIES[name].path
    files: list[tuple[Path, Path]] = []
    if source_root.is_dir():
        for source in sorted(source_root.rglob("*")):
            if source.is_file():
                relative = source.relative_to(source_root)
                files.append((source, target_root / relative))

    if name == "mu_wide_platforms":
        driver_root = DRIVERS / "EldenRamDiskDxe"
        driver_target = target_root / "Platforms" / "EldenPhase1Pkg"
        for source in sorted(driver_root.iterdir()):
            if source.is_file():
                files.append((source, driver_target / source.name))
    return files


def apply_overlays(check_only: bool) -> bool:
    failures = False
    for name in DEPENDENCIES:
        files = overlay_files(name)
        if not files:
            continue
        if not (THIRD_PARTY / DEPENDENCIES[name].path).is_dir():
            if check_only:
                print(f"missing {name}: required for its overlay")
                failures = True
            else:
                print(f"skip  {name}: checkout is absent")
            continue

        for source, destination in files:
            if check_only:
                if not destination.is_file() or not filecmp.cmp(
                    source, destination, shallow=False
                ):
                    print(f"diff  {destination.relative_to(ROOT)}")
                    failures = True
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

        if not check_only:
            print(f"apply {name}: {len(files)} file(s)")
    return not failures


def initialize_submodules() -> None:
    unixnu = THIRD_PARTY / "UniXNU"
    if unixnu.is_dir():
        git(
            unixnu,
            "submodule",
            "update",
            "--init",
            "--depth",
            "1",
            "drivers/DarwinBoot",
        )

    mu = THIRD_PARTY / "mu_wide_platforms"
    if mu.is_dir():
        print("initialize mu_wide_platforms submodules; this can download several GB")
        git(mu, "submodule", "update", "--init", "--recursive")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all-references",
        action="store_true",
        help="also clone the four research/reference repositories",
    )
    parser.add_argument(
        "--clean-build-deps",
        action="store_true",
        help="clone only UniXNU and mu_wide_platforms when they are absent",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="check that applied overlay files match this repository",
    )
    parser.add_argument(
        "--init-submodules",
        action="store_true",
        help="initialize submodules needed by a full EDK II build",
    )
    args = parser.parse_args()

    if args.verify_only:
        if not apply_overlays(check_only=True):
            raise SystemExit("third-party overlays are missing or out of date")
        print("overlays: verified")
        return

    if args.all_references:
        selected = tuple(DEPENDENCIES)
    else:
        selected = BUILD_DEPENDENCIES

    for name in selected:
        ensure_dependency(name)
    apply_overlays(check_only=False)
    if args.init_submodules:
        initialize_submodules()

    if not apply_overlays(check_only=True):
        raise SystemExit("third-party overlays are missing or out of date")
    print("overlays: verified")


if __name__ == "__main__":
    main()
