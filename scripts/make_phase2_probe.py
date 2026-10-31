#!/usr/bin/env python3
"""Build the small phase-2.3 initrd probe FAT image.

The probe proves, without loading XNU, that the bootloader initrd reaches
UniXNU as a readable FAT volume: its only boot entries are actions, so no
kernel is involved.  The image is copied to out/phase2.3/probe.img.

The volume is FAT16, built by the same writer that produces the phase-1
payload.  mtools' ``mformat -F`` produces FAT32 here, and EnhancedFatDxe
rejects a FAT32 volume that holds fewer than 0xFFF5 clusters
(``FatOpenDevice`` returns EFI_VOLUME_CORRUPTED), which an 8 MiB image always
does: that is why the 2026-11-01 device run showed the built-in configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
from pathlib import Path

from make_payload import build_config_image


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "phase2.3"
VOLUME = b"ELDENPROBE"
VOLUME_ID = 0x53484E47
SIZE_MIB = 8

PROBE_CONFIG = """version = 1
[boot]
timeout = -1
default = "reset"
[kits]
autoload = false
[ui]
scale = 4
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

    for tool in ("mcopy", "mdir"):
        if shutil.which(tool) is None:
            raise SystemExit(f"missing mtools tool: {tool}")

    with tempfile.TemporaryDirectory(prefix="elden-probe-") as directory:
        config = Path(directory) / "unixnu.toml"
        config.write_text(PROBE_CONFIG, encoding="utf-8")
        build_config_image(
            config,
            args.output,
            args.size_mib,
            label=VOLUME,
            media_id=VOLUME_ID,
        )

    print(f"probe:   {args.output} ({args.output.stat().st_size} bytes)")
    print(f"sha256:  {sha256(args.output)}")


if __name__ == "__main__":
    main()
