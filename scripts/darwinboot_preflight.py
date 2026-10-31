#!/usr/bin/env python3
"""Replay DarwinBoot's input checks against a real kernel and ADT on the host.

The loader in ``third_party/UniXNU/drivers/DarwinBoot`` parses the payload
before it touches the firmware exit path.  A rejected input prints a short
``DARWINBOOT: ...`` line on the device and returns to the menu, so the same
checks can be replayed here from the exact bytes that will be embedded in the
boot image:

* ``ParseKernel`` accepts the Mach-O header, its load commands, the segment
  layout, the ``LC_UNIXTHREAD`` entry point and the 256 MiB window bound;
* ``AdtNode`` accepts the flattened ADT, finds the optional ramdisk,
  trust-cache and GPU-addon placeholders and reads ``darwinboot-memory-size``;
* the optional ``.trustcache``/``.gpuaddon`` sidecars match those placeholders
  the same way ``Boot`` requires them to.

``DarwinBoot.c`` rejects a request whose kernels the loader would refuse; this
script only reports those refusals, it does not change the payload.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path


WINDOW_SIZE = 0x10000000
WINDOW_MAX = 0x200000000
BLOCK_SIZE = 0x200000
MAX_SEGMENTS = 64
MAX_UINT64 = (1 << 64) - 1


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def parse_kernel(data: bytes) -> dict:
    """Mirror ``ParseKernel`` from DarwinBoot.c."""
    size = len(data)
    if size < 32:
        raise ValueError("kernel is shorter than a Mach-O header")
    if (_u32(data, 0) != 0xFEEDFACF or _u32(data, 4) != 0x100000C
            or _u32(data, 8) != 0 or _u32(data, 12) != 2):
        raise ValueError("kernel is not a thin 64-bit ARM64 MH_EXECUTE Mach-O")
    if _u32(data, 20) > size - 32:
        raise ValueError("sizeofcmds runs past the end of the kernel")
    count = _u32(data, 16)
    end = 32 + _u32(data, 20)
    offset = 32
    segments: list[dict] = []
    entry = None
    for _ in range(count):
        if end - offset < 8:
            raise ValueError("load command header runs past sizeofcmds")
        command = _u32(data, offset)
        length = _u32(data, offset + 4)
        if length < 8 or length & 7 or length > end - offset:
            raise ValueError(f"load command at {offset:#x} has a bad length")
        if command == 0x19:
            if length < 72 or _u32(data, offset + 64) > (length - 72) // 80:
                raise ValueError(f"LC_SEGMENT_64 at {offset:#x} is malformed")
            if len(segments) == MAX_SEGMENTS:
                raise ValueError(f"kernel has more than {MAX_SEGMENTS} segments")
            if _u64(data, offset + 32) != 0:
                segment = {
                    "address": _u64(data, offset + 24),
                    "size": _u64(data, offset + 32),
                    "file_offset": _u64(data, offset + 40),
                    "file_size": _u64(data, offset + 48),
                    "protection": _u32(data, offset + 60),
                }
                if (segment["size"] > WINDOW_SIZE
                        or segment["address"] > MAX_UINT64 - segment["size"]
                        or segment["file_size"] > segment["size"]
                        or segment["file_offset"] > size
                        or segment["file_size"] > size - segment["file_offset"]):
                    raise ValueError(f"segment at {offset:#x} is outside the file or window")
                segments.append(segment)
        elif command == 5:
            if entry is not None or length != 288 or _u32(data, offset + 8) != 6 or _u32(data, offset + 12) != 68:
                raise ValueError(f"LC_UNIXTHREAD at {offset:#x} is malformed")
            entry = _u64(data, offset + 272)
        offset += length
    if offset != end:
        raise ValueError("load commands do not fill sizeofcmds")
    if entry is None or not segments:
        raise ValueError("kernel has no LC_UNIXTHREAD entry or no loaded segment")
    base = min(segment["address"] for segment in segments)
    kernel_end = max(segment["address"] + segment["size"] for segment in segments)
    executable = any(
        segment["address"] <= entry < segment["address"] + segment["file_size"]
        and segment["protection"] & 4
        for segment in segments
    )
    if not executable:
        raise ValueError("entry point is not inside an executable file-backed segment")
    for index, segment in enumerate(segments):
        for other in segments[:index]:
            if (segment["address"] < other["address"] + other["size"]
                    and other["address"] < segment["address"] + segment["size"]):
                raise ValueError("kernel segments overlap")
    if entry & 3:
        raise ValueError("entry point is not 4-byte aligned")
    if base & 0xFFF:
        raise ValueError("kernel base is not 4 KiB aligned")
    if base > MAX_UINT64 - WINDOW_SIZE:
        raise ValueError("kernel base leaves no 256 MiB window")
    if kernel_end - base > WINDOW_SIZE - BLOCK_SIZE:
        raise ValueError("kernel span exceeds the window minus the allocation block")
    return {
        "segments": len(segments),
        "base": base,
        "end": kernel_end,
        "entry": entry,
        "span": kernel_end - base,
        "entry_file_offset": next(
            segment["file_offset"] + entry - segment["address"]
            for segment in segments
            if segment["address"] <= entry < segment["address"] + segment["file_size"]
        ),
    }


def window_size_valid(size: int) -> bool:
    return WINDOW_SIZE <= size <= WINDOW_MAX and not size & (BLOCK_SIZE - 1)


def adt_walk(data: bytes) -> dict:
    """Mirror ``AdtNode`` from DarwinBoot.c."""
    size = len(data)
    result = {
        "ramdisk": None,
        "trustcache": None,
        "gpuaddon": None,
        "window": 0,
        "keep_packed": False,
    }

    def walk(offset: int, depth: int, parent_path: int) -> int:
        if depth > 64 or size - offset < 8:
            raise ValueError("ADT node header is truncated")
        properties = _u32(data, offset)
        children = _u32(data, offset + 4)
        offset += 8
        if properties > (size - offset) // 36:
            raise ValueError(f"ADT node at depth {depth} claims too many properties")
        name = None
        candidate = trust_candidate = addon_candidate = memory_candidate = None
        for _ in range(properties):
            if size - offset < 36:
                raise ValueError("ADT property header is truncated")
            if data[offset:offset + 32].find(0) < 0:
                raise ValueError("ADT property name is not NUL padded")
            length = _u32(data, offset + 32)
            offset += 36
            if length > size - offset:
                raise ValueError("ADT property value runs past the tree")
            key = data[offset - 36:offset - 4].split(b"\0", 1)[0]
            value_offset = offset
            if key == b"name":
                if name is not None:
                    raise ValueError("ADT node has two name properties")
                name = data[value_offset:value_offset + length]
            if key in (b"RAMDisk", b"PackedRAMDisk"):
                if key == b"PackedRAMDisk":
                    if result["keep_packed"]:
                        raise ValueError("ADT has two packed ramdisk markers")
                    result["keep_packed"] = True
                if candidate is not None or length != 16:
                    raise ValueError("ADT RAMDisk placeholder is duplicated or not 16 bytes")
                candidate = value_offset
            if key == b"TrustCache":
                if trust_candidate is not None or length != 16:
                    raise ValueError("ADT TrustCache placeholder is duplicated or not 16 bytes")
                trust_candidate = value_offset
            if key == b"GpuAddon":
                if addon_candidate is not None or length != 16:
                    raise ValueError("ADT GpuAddon placeholder is duplicated or not 16 bytes")
                addon_candidate = value_offset
            if key == b"darwinboot-memory-size":
                if memory_candidate is not None or length != 8:
                    raise ValueError("ADT darwinboot-memory-size is duplicated or not 8 bytes")
                memory_candidate = value_offset
            offset += length
            if ((offset + 3) & ~3) > size:
                raise ValueError("ADT property padding runs past the tree")
            offset = (offset + 3) & ~3
        path = 3
        if depth == 0:
            path = 0
        if depth == 1 and parent_path == 0 and name == b"chosen\0":
            path = 1
        if depth == 2 and parent_path == 1 and name == b"memory-map\0":
            path = 2
        if path == 2 and candidate is not None:
            if result["ramdisk"] is not None:
                raise ValueError("ADT has more than one RAMDisk placeholder")
            result["ramdisk"] = candidate
        if path == 2 and trust_candidate is not None:
            if result["trustcache"] is not None:
                raise ValueError("ADT has more than one TrustCache placeholder")
            result["trustcache"] = trust_candidate
        if path == 2 and addon_candidate is not None:
            if result["gpuaddon"] is not None:
                raise ValueError("ADT has more than one GpuAddon placeholder")
            result["gpuaddon"] = addon_candidate
        if memory_candidate is not None:
            if path != 1 or result["window"] != 0:
                raise ValueError("ADT darwinboot-memory-size is not a single /chosen property")
            result["window"] = _u64(data, memory_candidate)
            if not window_size_valid(result["window"]):
                raise ValueError(f"ADT window {result['window']:#x} is not a valid allocation size")
        if children > (size - offset) // 8:
            raise ValueError(f"ADT node at depth {depth} claims too many children")
        for _ in range(children):
            offset = walk(offset, depth + 1, path)
        return offset

    if walk(0, 0, 3) != size:
        raise ValueError("ADT walk did not consume the whole tree")
    return result


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--adt", type=Path, required=True)
    parser.add_argument("--expect-kernel-bytes", type=int)
    parser.add_argument("--expect-kernel-sha256")
    args = parser.parse_args()

    kernel = args.kernel.read_bytes()
    adt = args.adt.read_bytes()
    if args.expect_kernel_bytes is not None and len(kernel) != args.expect_kernel_bytes:
        raise SystemExit(f"kernel is {len(kernel)} bytes, want {args.expect_kernel_bytes}")
    if args.expect_kernel_sha256 and sha256(kernel) != args.expect_kernel_sha256:
        raise SystemExit("kernel SHA-256 differs from the expected value")
    parsed = parse_kernel(kernel)
    tree = adt_walk(adt)
    here = args.kernel.parent
    sidecars = {
        "trustcache": Path(str(args.kernel) + ".trustcache"),
        "gpuaddon": Path(str(args.kernel) + ".gpuaddon"),
    }
    present = {name: path.is_file() for name, path in sidecars.items()}
    for name, present_here in present.items():
        placeholder = tree[name]
        if present_here and placeholder is None:
            raise SystemExit(f"{name} sidecar is present but the ADT has no matching placeholder")
        if not present_here and placeholder is not None:
            raise SystemExit(f"ADT has a {name} placeholder but the sidecar is missing")
    print(
        f"kernel: OK segments={parsed['segments']} base={parsed['base']:#x} "
        f"end={parsed['end']:#x} entry={parsed['entry']:#x} span={parsed['span']:#x} "
        f"entry-file-offset={parsed['entry_file_offset']:#x}"
    )
    print(
        "adt: OK "
        f"tree={len(adt)} bytes window={tree['window']:#x} "
        f"ramdisk={'present' if tree['ramdisk'] is not None else 'absent'} "
        f"trustcache={'present' if tree['trustcache'] is not None else 'absent'} "
        f"gpuaddon={'present' if tree['gpuaddon'] is not None else 'absent'}"
    )
    if present["trustcache"] or present["gpuaddon"]:
        print("sidecars: " + ", ".join(name for name, here in present.items() if here))
    print("darwinboot preflight: OK")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        raise SystemExit(f"darwinboot preflight: REFUSED: {error}") from error
