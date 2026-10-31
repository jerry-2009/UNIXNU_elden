#!/usr/bin/env python3
"""Build a kernel whose entry point runs a visible probe before the real code.

Stage 2.4 ends when DarwinBoot prints ``inputs validated`` and paints its green
bar, but that only proves the loader ran.  To tell "the kernel entry executed"
from "the loader handed off and nothing happened", this tool adds a tiny
executable segment at the end of the kernel image, rewrites the entry
instruction to branch there, and has the probe draw a blue band across the
middle of the frame buffer before branching to the original target.

Why an appended segment: the kernel entry is inside ``__TEXT_EXEC``, which is
fully file-backed with no spare bytes, and DarwinBoot maps segment
``Address`` to ``window + Address - Kernel.Base``.  A segment placed at the old
``Kernel.End`` (16 KiB aligned, args are placed after the new end) is copied
into the window exactly like the real segments, and the probe runs before the
kernel disables the MMU, so it needs no page-table entry of its own.

The probe only reads ``boot_args->Video`` (``BootArgs.h``: ``Video[6]`` at
offset 0x28, filled by ``BootVideo.h``) and draws with the MMU and caches off,
then executes the original first instruction's branch target.  Registers
x0-x7 stay untouched so the kernel sees the same entry state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from darwinboot_preflight import adt_walk, parse_kernel, sha256  # noqa: E402

PAYLOAD_IMAGE = Path("out/phase2.3/payload.img")
KERNEL_IMAGE_PATH = "EFI/UniXNU/Payloads/kernel.macho"
ADT_IMAGE_PATH = "EFI/UniXNU/Payloads/kernel.macho.adt"
SOURCE_KERNEL_BYTES = 54050816
SOURCE_KERNEL_SHA256 = "65a3e799e1eb7f631a3b146dfc890ef5a8147c8fc613ee383a1665b398fb1ef9"
SEGMENT_ALIGNMENT = 0x4000
LC_SEGMENT_64 = 0x19
LC_SEGMENT_64_SIZE = 72
BLUE_ABGR = 0xFF0000FF

PROBE_SOURCE = """\
// DarwinBoot entry probe: draw a blue band across the middle of the frame
// buffer, then run the kernel's original entry instruction.  x0 is the
// boot_args physical pointer; Video[0..5] start at offset 0x28.
  .arch armv8-a
  .text
  .p2align 3
  .global elden_probe_entry
elden_probe_entry:
  cbz x0, 9f
  ldr x9, [x0, #0x28]        // Video[0]: frame buffer base
  cbz x9, 9f
  ldr x10, [x0, #0x30]       // Video[2]: bytes per row
  ldr x11, [x0, #0x38]       // Video[3]: pixels per row
  ldr x12, [x0, #0x40]       // Video[4]: rows
  cbz x10, 9f
  cbz x11, 9f
  cbz x12, 9f
  lsr x12, x12, #1           // y = rows / 2
  sub x12, x12, #12
  movz w16, #0xFF
  movk w16, #0xFF00, lsl #16 // BGRA blue, 32 bpp
  mov x14, #4                // four rows, four pixels apart
1:
  madd x15, x12, x10, x9
  mov x17, x11
2:
  str w16, [x15], #4
  subs x17, x17, #1
  b.ne 2b
  add x12, x12, #4
  subs x14, x14, #1
  b.ne 1b
  dsb sy
9:
  .word 0x14000000           // patched with the original entry target
"""


def encode_b(origin: int, target: int) -> bytes:
    delta = target - origin
    if delta & 3:
        raise ValueError(f"branch from {origin:#x} to {target:#x} is not 4-byte aligned")
    immediate = delta >> 2
    if not -(1 << 25) <= immediate < (1 << 25):
        raise ValueError(f"branch from {origin:#x} to {target:#x} is out of range")
    return struct.pack("<I", 0x14000000 | (immediate & 0x3FFFFFF))


def branch_target(word: int, origin: int) -> int:
    if word >> 26 != 0b000101:
        raise ValueError(f"instruction {word:#010x} at {origin:#x} is not an unconditional B")
    immediate = word & 0x3FFFFFF
    if immediate & (1 << 25):
        immediate -= 1 << 26
    return origin + immediate * 4


def assemble_stub(clang: Path) -> bytes:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "probe.s"
        obj = Path(directory) / "probe.o"
        source.write_text(PROBE_SOURCE)
        subprocess.run([str(clang), "--target=aarch64-none-elf", "-c", str(source), "-o", str(obj)],
                       check=True)
        blob = obj.read_bytes()
    return elf_stub_text(blob)


def elf_stub_text(blob: bytes) -> bytes:
    if blob[:4] != b"\x7fELF" or blob[4] != 2 or blob[5] != 1:
        raise ValueError("probe object is not a little-endian ELF64 file")
    if struct.unpack_from("<H", blob, 0x12)[0] != 0xB7:
        raise ValueError("probe object is not an AArch64 ELF file")
    section_offset = struct.unpack_from("<Q", blob, 0x28)[0]
    entry_size, count = struct.unpack_from("<HH", blob, 0x3A)
    names_index = struct.unpack_from("<H", blob, 0x3E)[0]
    sections = []
    for index in range(count):
        base = section_offset + index * entry_size
        name, kind = struct.unpack_from("<II", blob, base)
        offset = struct.unpack_from("<Q", blob, base + 0x18)[0]
        size = struct.unpack_from("<Q", blob, base + 0x20)[0]
        sections.append((name, kind, offset, size))
    if names_index >= count:
        raise ValueError("probe object has no section-name table")
    names_offset = sections[names_index][2]
    text = None
    for name, kind, offset, size in sections:
        termination = blob.index(b"\0", names_offset + name)
        section_name = blob[names_offset + name:termination]
        if kind in (4, 9):
            raise ValueError("probe object has relocations; labels must resolve in-section")
        if section_name == b".text":
            text = blob[offset:offset + size]
    if not text:
        raise ValueError("probe object has no .text section")
    if text[-4:] != b"\x00\x00\x00\x14":
        raise ValueError("probe stub does not end with the branch placeholder")
    return text


def mtools(*arguments: str) -> None:
    subprocess.run(["mcopy", *arguments], check=True)


def extract_payload(image: Path, directory: Path) -> tuple[bytes, bytes]:
    kernel = directory / "kernel.macho"
    adt = directory / (kernel.name + ".adt")
    mtools("-o", "-m", "-i", str(image), f"::{KERNEL_IMAGE_PATH}", str(kernel))
    mtools("-o", "-m", "-i", str(image), f"::{ADT_IMAGE_PATH}", str(adt))
    return kernel.read_bytes(), adt.read_bytes()


def add_segment(data: bytes, parsed: dict, stub: bytes) -> tuple[bytes, dict]:
    if len(data) < 32:
        raise ValueError("kernel is too short")
    ncmds, sizeofcmds = struct.unpack_from("<II", data, 16)
    commands_end = 32 + sizeofcmds
    if any(data[commands_end:commands_end + LC_SEGMENT_64_SIZE]):
        raise ValueError("no zero room after the load commands for a new segment")
    entry_va = parsed["entry"]
    entry_offset = parsed["entry_file_offset"]
    entry_word = struct.unpack_from("<I", data, entry_offset)[0]
    original_target = branch_target(entry_word, entry_va)

    stub_va = (parsed["end"] + SEGMENT_ALIGNMENT - 1) & ~(SEGMENT_ALIGNMENT - 1)
    stub_offset = (len(data) + SEGMENT_ALIGNMENT - 1) & ~(SEGMENT_ALIGNMENT - 1)
    stub_size = len(stub)
    last_word = stub_va + stub_size - 4
    stub = stub[:-4] + encode_b(last_word, original_target)

    if stub_va < parsed["end"]:
        raise ValueError("probe segment would overlap the kernel image")
    if stub_va - parsed["base"] > 0x100000000 - 0x200000:
        raise ValueError("probe segment pushes the image past the window")

    output = bytearray(data)
    output += b"\0" * (stub_offset - len(output))
    output += stub
    struct.pack_into("<I", output, 16, ncmds + 1)
    struct.pack_into("<I", output, 20, sizeofcmds + LC_SEGMENT_64_SIZE)
    struct.pack_into("<I", output, commands_end, LC_SEGMENT_64)
    struct.pack_into("<I", output, commands_end + 4, LC_SEGMENT_64_SIZE)
    name = b"__ELDEN_PROBE\0"
    output[commands_end + 8:commands_end + 8 + len(name)] = name
    struct.pack_into("<Q", output, commands_end + 24, stub_va)
    struct.pack_into("<Q", output, commands_end + 32, (stub_size + SEGMENT_ALIGNMENT - 1) & ~(SEGMENT_ALIGNMENT - 1))
    struct.pack_into("<Q", output, commands_end + 40, stub_offset)
    struct.pack_into("<Q", output, commands_end + 48, stub_size)
    struct.pack_into("<I", output, commands_end + 56, 7)
    struct.pack_into("<I", output, commands_end + 60, 5)  # r-x
    output[entry_offset:entry_offset + 4] = encode_b(entry_va, stub_va)
    facts = {
        "entry_va": entry_va,
        "entry_word": entry_word,
        "entry_target": original_target,
        "stub_va": stub_va,
        "stub_file_offset": stub_offset,
        "stub_bytes": stub_size,
    }
    return bytes(output), facts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-image", type=Path, default=PAYLOAD_IMAGE,
                        help="payload image whose kernel and ADT are the stage 2.3 baseline")
    parser.add_argument("--kernel", type=Path, help="use this kernel instead of extracting one")
    parser.add_argument("--adt", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("out/phase2.4"))
    parser.add_argument("--clang", type=Path, default=Path(shutil.which("clang") or "clang"))
    parser.add_argument("--expect-kernel-bytes", type=int, default=SOURCE_KERNEL_BYTES)
    parser.add_argument("--expect-kernel-sha256", default=SOURCE_KERNEL_SHA256)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    directory = args.output_dir / "probe"
    directory.mkdir(exist_ok=True)
    if args.kernel:
        if args.adt is None or not args.adt.is_file():
            raise SystemExit("--kernel needs --adt")
        kernel_bytes = args.kernel.read_bytes()
        adt_bytes = args.adt.read_bytes()
    else:
        if args.adt is not None:
            raise SystemExit("--adt without --kernel is not used")
        with tempfile.TemporaryDirectory() as scratch:
            kernel_bytes, adt_bytes = extract_payload(args.payload_image, Path(scratch))
    if len(kernel_bytes) != args.expect_kernel_bytes or sha256(kernel_bytes) != args.expect_kernel_sha256:
        raise SystemExit("baseline kernel does not match the pinned stage 2.3 bytes")
    parsed = parse_kernel(kernel_bytes)
    tree = adt_walk(adt_bytes)
    if tree["ramdisk"] is not None or tree["trustcache"] is not None or tree["gpuaddon"] is not None:
        raise SystemExit("baseline ADT carries placeholders; the probe keeps the plain payload")
    if tree["window"] != 0x10000000:
        raise SystemExit(f"baseline ADT window is {tree['window']:#x}, expected 0x10000000")

    stub = assemble_stub(args.clang)
    probed, facts = add_segment(kernel_bytes, parsed, stub)
    check = parse_kernel(probed)
    if check["entry"] != facts["entry_va"] or check["end"] != facts["stub_va"] + ((facts["stub_bytes"] + 0x3FFF) & ~0x3FFF):
        raise SystemExit("patched kernel does not re-parse with the expected layout")

    kernel_out = directory / "kernel.macho"
    adt_out = directory / (kernel_out.name + ".adt")
    kernel_out.write_bytes(probed)
    adt_out.write_bytes(adt_bytes)
    manifest = {
        "schema": "unixnu-elden-entry-probe/v1",
        "baseline_kernel": {"bytes": len(kernel_bytes), "sha256": sha256(kernel_bytes)},
        "baseline_adt": {"bytes": len(adt_bytes), "sha256": sha256(adt_bytes)},
        "output_kernel": {"bytes": len(probed), "sha256": sha256(probed)},
        "output_adt": {"bytes": len(adt_bytes), "sha256": sha256(adt_bytes)},
        "source": {"payload_image": str(args.payload_image), "kernel_path": KERNEL_IMAGE_PATH,
                   "adt_path": ADT_IMAGE_PATH},
        "layout": facts,
        "band": "blue BGRA 0xFF0000FF, full width, four rows at height/2-12",
    }
    (directory / "probe.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"probe kernel: {kernel_out} {len(probed)} bytes sha256={sha256(probed)}")
    print(f"probe adt:    {adt_out} {len(adt_bytes)} bytes sha256={sha256(adt_bytes)}")
    print("entry %#x -> b %#x (stub), stub ends with b %#x" % (
        facts["entry_va"], facts["stub_va"], facts["entry_target"]))


if __name__ == "__main__":
    main()
