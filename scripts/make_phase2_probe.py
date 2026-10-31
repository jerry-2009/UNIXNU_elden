#!/usr/bin/env python3
"""Build the small phase-2.3 initrd probe FAT image.

The probe proves, without loading XNU, that the bootloader initrd reaches
UniXNU as a readable FAT volume: its only boot entries are actions, so no
kernel is involved.  The image is copied to out/phase2.3/probe.img.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "phase2.3"
VOLUME = "ELDENPROBE"
SIZE_MIB = 8

PROBE_CONFIG = """version = 1
[boot]
timeout = -1
default = "reset"
[kits]
autoload = false
[[entry]]
id = "probe"
title = "ELDEN 2.3 PROBE - initrd FAT"
type = "action"
action = "reset"
[[entry]]
id = "reset"
title = "Restart"
type = "action"
action = "reset"
[[entry]]
id = "shutdown"
title = "Power off"
type = "action"
action = "shutdown"
"""


def run(command: list[str]) -> None:
    print("+ " + " ".join(command))
    subprocess.run(command, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size-mib", type=int, default=SIZE_MIB)
    parser.add_argument("--output", type=Path, default=OUT / "probe.img")
    args = parser.parse_args()

    for tool in ("mformat", "mmd", "mcopy", "mdir"):
        if shutil.which(tool) is None:
            raise SystemExit(f"missing mtools tool: {tool}")

    with tempfile.TemporaryDirectory(prefix="elden-probe-") as directory:
        stage = Path(directory)
        config = stage / "unixnu.toml"
        config.write_text(PROBE_CONFIG, encoding="utf-8")
        image = stage / "probe.img"
        run([
            "mformat",
            "-C",
            "-F",
            "-T", str(args.size_mib * 2048),
            "-v", VOLUME,
            "-N", "53484e47",
            "-i", str(image),
            "::",
        ])
        run(["mmd", "-i", str(image), "::/EFI"])
        run(["mmd", "-i", str(image), "::/EFI/UniXNU"])
        run([
            "mcopy",
            "-o",
            "-m",
            "-i", str(image),
            str(config),
            "::/EFI/UniXNU/unixnu.toml",
        ])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image, args.output)

    print(f"probe:   {args.output} ({args.output.stat().st_size} bytes)")
    print(f"sha256:  {sha256(args.output)}")


if __name__ == "__main__":
    main()
