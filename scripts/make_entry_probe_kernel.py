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

Once the MMU is on the frame buffer is no longer mapped, so a later checkpoint
cannot draw.  ``--reset-at`` and ``--reset-va`` therefore overwrite the target
instruction in place: the stub assembles to a fixed 48 bytes inside
``__TEXT_EXEC``, so it stays executable after the kernel switches page tables.
The stub waits on ``CNTPCT_EL0`` and then issues the PSCI ``SYSTEM_RESET``
call (``0x84000009`` over ``smc``, the conduit the ADT advertises).  A device
that reboots after the band proves the kernel reached that instruction; a
device that stays frozen proves it did not.  ``--reset-entry`` puts the same
wait and reset in the entry probe itself, which validates the reset mechanism
at a point the band already proves is reached.  ``--ret-at`` writes ``ret``
over a named handoff (for example the iBoot video-console read in
``PE_create_console``) to test whether the kernel can continue without it.

``--poke`` replaces one 32-bit word at an arbitrary virtual address or symbol,
including data.  It carries the console experiment: skip the iBoot panic-log
read that faults, force ``initialize_screen`` to map the physical frame buffer,
and set the ``startup_debug`` tunable so the kernel prints its startup entries.
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

STUB_HEADER = """\
  .arch armv8-a
  .text
  .p2align 3
  .global elden_probe
elden_probe:
"""

# Draws a blue band across the middle of the frame buffer.  x0 is the boot_args
# physical pointer, Video[0..5] start at offset 0x28.
BAND_BODY = """\
  cbz x0, 9f
  ldr x9, [x0, #0x28]        // Video[0]: frame buffer base
  cbz x9, 9f
  ldr x10, [x0, #0x30]       // Video[1]: display type flag
  cbz x10, 9f
  ldr x10, [x0, #0x38]       // Video[2]: bytes per row
  ldr x11, [x0, #0x40]       // Video[3]: pixels per row
  ldr x12, [x0, #0x48]       // Video[4]: rows
  cbz x10, 9f
  cbz x11, 9f
  cbz x12, 9f
  lsr x12, x12, #1           // y = rows / 2
  sub x12, x12, #32
  movz w16, #0xFF
  movk w16, #0xFF00, lsl #16 // BGRA blue, 32 bpp
  mov x14, #64               // 64 solid rows: a band visible on a dense panel
1:
  madd x15, x12, x10, x9
  mov x17, x11
2:
  str w16, [x15], #4
  subs x17, x17, #1
  b.ne 2b
  add x12, x12, #1
  subs x14, x14, #1
  b.ne 1b
  dsb sy
9:
"""

# Waits {delay} seconds on the generic counter, then resets through PSCI.  The
# ADT describes PSCI as ``arm,psci-1.0`` with method ``smc``; XNU's own PSCI
# call sites in this image also use ``smc #0``.
RESET_BODY = """\
  mrs x1, cntfrq_el0
  mov x2, #{delay}
  mul x1, x1, x2
  mrs x3, cntpct_el0
  add x1, x1, x3
5:
  mrs x4, cntpct_el0
  cmp x4, x1
  b.lo 5b
  mov x0, #0x09
  movk x0, #0x8400, lsl #16  // PSCI SYSTEM_RESET
  smc #0
  b .
"""

JUMP_BACK = "  .word 0x14000000           // patched with the original entry target\n"


def probe_source(band: bool, reset: bool, delay: int) -> str:
    body = BAND_BODY if band else ""
    if reset:
        body += RESET_BODY.format(delay=delay)
    else:
        body += JUMP_BACK
    return STUB_HEADER + body



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


def assemble(clang: Path, source_text: str) -> bytes:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "probe.s"
        obj = Path(directory) / "probe.o"
        source.write_text(source_text)
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
    if not text:
        raise ValueError("probe stub is empty")
    return text


def mtools(*arguments: str) -> None:
    subprocess.run(["mcopy", *arguments], check=True)


def extract_payload(image: Path, directory: Path) -> tuple[bytes, bytes]:
    kernel = directory / "kernel.macho"
    adt = directory / (kernel.name + ".adt")
    mtools("-o", "-m", "-i", str(image), f"::{KERNEL_IMAGE_PATH}", str(kernel))
    mtools("-o", "-m", "-i", str(image), f"::{ADT_IMAGE_PATH}", str(adt))
    return kernel.read_bytes(), adt.read_bytes()


def append_segment(data: bytes, parsed: dict, stub: bytes, name: bytes) -> tuple[bytes, dict]:
    if len(data) < 32:
        raise ValueError("kernel is too short")
    ncmds, sizeofcmds = struct.unpack_from("<II", data, 16)
    commands_end = 32 + sizeofcmds
    if any(data[commands_end:commands_end + LC_SEGMENT_64_SIZE]):
        raise ValueError("no zero room after the load commands for a new segment")
    stub_va = (parsed["end"] + SEGMENT_ALIGNMENT - 1) & ~(SEGMENT_ALIGNMENT - 1)
    stub_offset = (len(data) + SEGMENT_ALIGNMENT - 1) & ~(SEGMENT_ALIGNMENT - 1)
    stub_size = len(stub)
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
    if len(name) > 16:
        raise ValueError("segment name is longer than 16 bytes")
    output[commands_end + 8:commands_end + 8 + len(name)] = name
    struct.pack_into("<Q", output, commands_end + 24, stub_va)
    struct.pack_into("<Q", output, commands_end + 32, (stub_size + SEGMENT_ALIGNMENT - 1) & ~(SEGMENT_ALIGNMENT - 1))
    struct.pack_into("<Q", output, commands_end + 40, stub_offset)
    struct.pack_into("<Q", output, commands_end + 48, stub_size)
    struct.pack_into("<I", output, commands_end + 56, 7)
    struct.pack_into("<I", output, commands_end + 60, 5)  # r-x
    facts = {
        "segment": name.rstrip(b"\0").decode(),
        "stub_va": stub_va,
        "stub_file_offset": stub_offset,
        "stub_bytes": stub_size,
    }
    return bytes(output), facts


def add_entry_probe(data: bytes, parsed: dict, stub: bytes) -> tuple[bytes, dict]:
    entry_va = parsed["entry"]
    entry_offset = parsed["entry_file_offset"]
    entry_word = struct.unpack_from("<I", data, entry_offset)[0]
    original_target = branch_target(entry_word, entry_va)
    output, facts = append_segment(data, parsed, stub, b"__ELDEN_PROBE\0")
    last_word = facts["stub_va"] + facts["stub_bytes"] - 4
    output_bytearray = bytearray(output)
    output_bytearray[facts["stub_file_offset"] + facts["stub_bytes"] - 4:
                     facts["stub_file_offset"] + facts["stub_bytes"]] = encode_b(last_word, original_target)
    output_bytearray[entry_offset:entry_offset + 4] = encode_b(entry_va, facts["stub_va"])
    facts.update({
        "entry_va": entry_va,
        "entry_word": entry_word,
        "entry_target": original_target,
        "entry_jump": f"{entry_va:#x} -> {facts['stub_va']:#x}, back to {original_target:#x}",
    })
    return bytes(output_bytearray), facts


def symbols(data: bytes) -> dict[str, int]:
    ncmds = struct.unpack_from("<I", data, 16)[0]
    offset = 32
    table: dict[str, int] = {}
    for _ in range(ncmds):
        command, size = struct.unpack_from("<II", data, offset)
        if command == 0x2:  # LC_SYMTAB
            symoff, nsyms, stroff, _ = struct.unpack_from("<IIII", data, offset + 8)
            for index in range(nsyms):
                base = symoff + index * 16
                strx, ntype = struct.unpack_from("<IB", data, base)
                value = struct.unpack_from("<Q", data, base + 8)[0]
                if ntype & 0x0E == 0:  # undefined
                    continue
                termination = data.index(b"\0", stroff + strx)
                table[data[stroff + strx:termination].decode()] = value
            break
        offset += size
    return table


def segments(data: bytes) -> list[dict]:
    """Every ``LC_SEGMENT_64`` with a file offset, in load-command order."""
    ncmds = struct.unpack_from("<I", data, 16)[0]
    offset = 32
    table = []
    for _ in range(ncmds):
        command, size = struct.unpack_from("<II", data, offset)
        if command == LC_SEGMENT_64:
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, offset + 24)
            table.append({
                "name": data[offset + 8:offset + 24].rstrip(b"\0").decode(),
                "address": vmaddr,
                "size": vmsize,
                "file_offset": fileoff,
                "file_size": filesize,
                "protection": struct.unpack_from("<I", data, offset + 60)[0],
            })
        offset += size
    return table


def locate(data: bytes, va: int, size: int = 4, executable: bool = False) -> tuple[dict, int]:
    """Return the segment holding ``va`` and its file offset."""
    for segment in segments(data):
        if segment["address"] <= va and va + size <= segment["address"] + segment["file_size"]:
            if executable and not segment["protection"] & 4:
                continue
            return segment, segment["file_offset"] + (va - segment["address"])
    raise ValueError(f"{va:#x} is not inside an executable segment" if executable
                     else f"{va:#x} is not inside a file-backed segment")


def symbol_address(data: bytes, name: str) -> tuple[str, int]:
    table = symbols(data)
    key = name if name.startswith("_") else "_" + name
    if key not in table and name in table:
        key = name
    if key not in table:
        raise ValueError(f"symbol {name} is not in the kernel symbol table")
    return key, table[key]


def patch_symbol(data: bytes, name: str, stub_va: int) -> tuple[bytes, dict]:
    key, va = symbol_address(data, name)
    segment, offset = locate(data, va, 4, executable=True)
    word = struct.unpack_from("<I", data, offset)[0]
    output = bytearray(data)
    output[offset:offset + 4] = encode_b(va, stub_va)
    return bytes(output), {
        "patched_symbol": key,
        "patched_va": va,
        "patched_file_offset": offset,
        "patched_word": word,
        "patched_target": f"{va:#x} -> {stub_va:#x}",
    }


def patch_address_in_place(data: bytes, va: int, stub: bytes) -> tuple[bytes, dict]:
    """Write the reset stub at an arbitrary executable VA."""
    if va & 3:
        raise ValueError(f"{va:#x} is not 4-byte aligned")
    segment, offset = locate(data, va, len(stub), executable=True)
    word = struct.unpack_from("<I", data, offset)[0]
    output = bytearray(data)
    output[offset:offset + len(stub)] = stub
    return bytes(output), {
        "patched_va": va,
        "patched_file_offset": offset,
        "patched_word": word,
        "patched_bytes": len(stub),
        "patched_target": f"{va:#x} (in place)",
    }


def patch_word_at(data: bytes, va: int, word: int, executable: bool = True) -> tuple[bytes, dict]:
    """Replace one instruction (or, with ``executable=False``, data) word at a VA."""
    if va & 3:
        raise ValueError(f"{va:#x} is not 4-byte aligned")
    segment, offset = locate(data, va, 4, executable=executable)
    output = bytearray(data)
    old = struct.unpack_from("<I", output, offset)[0]
    struct.pack_into("<I", output, offset, word)
    return bytes(output), {
        "va": va,
        "word": old,
        "new": word,
        "segment": segment["name"],
        "file_offset": offset,
    }


def patch_symbol_in_place(data: bytes, name: str, stub: bytes) -> tuple[bytes, dict]:
    """Write the reset stub over a symbol's first bytes.

    The kernel image is copied to the window before DarwinBoot exits boot
    services, so the stub lives in __TEXT_EXEC and keeps execute permission
    when arm_vm_init replaces the bootstrap page tables with the kernel pmap.
    A stub appended after Kernel.End does not.
    """
    key, va = symbol_address(data, name)
    segment, offset = locate(data, va, len(stub), executable=True)
    if offset + len(stub) > segment["file_offset"] + segment["file_size"]:
        raise ValueError(f"symbol {name} at {va:#x} is too close to its segment end")
    word = struct.unpack_from("<I", data, offset)[0]
    output = bytearray(data)
    output[offset:offset + len(stub)] = stub
    return bytes(output), {
        "patched_symbol": key,
        "patched_va": va,
        "patched_file_offset": offset,
        "patched_word": word,
        "patched_bytes": len(stub),
        "patched_target": f"{va:#x} (in place)",
    }


def parse_poke(text: str) -> tuple[str | None, int | None, int, int]:
    """Parse ``ADDRESS=WORD``, ``SYMBOL=WORD`` or ``SYMBOL+OFFSET=WORD``."""
    target, _, value = text.partition("=")
    if not target or not value:
        raise SystemExit(f"--poke expects ADDRESS=WORD or SYMBOL[+OFFSET]=WORD, got {text!r}")
    try:
        word = int(value, 0)
    except ValueError:
        raise SystemExit(f"--poke value {value!r} is not a number") from None
    if not 0 <= word <= 0xFFFFFFFF:
        raise SystemExit(f"--poke value {value!r} does not fit in 32 bits")
    try:
        return None, int(target, 0), 0, word
    except ValueError:
        pass
    symbol, separator, offset = target.partition("+")
    if separator:
        try:
            return symbol, None, int(offset, 0), word
        except ValueError:
            raise SystemExit(f"--poke offset {offset!r} is not a number") from None
    return target, None, 0, word


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
    parser.add_argument("--reset-entry", action="store_true",
                        help="entry stub draws the band, waits, then resets; validates the reset path")
    parser.add_argument("--reset-at", metavar="SYMBOL",
                        help="wait and reset when control reaches SYMBOL instead of jumping back")
    parser.add_argument("--reset-va", metavar="ADDRESS",
                        help="wait and reset when control reaches the given executable address")
    parser.add_argument("--ret-at", action="append", metavar="ADDRESS", default=[],
                        help="replace the instruction at ADDRESS with ret (may be repeated)")
    parser.add_argument("--poke", action="append", metavar="TARGET=WORD", default=[],
                        help="replace one 32-bit word at ADDRESS or SYMBOL (may be repeated)")
    parser.add_argument("--reset-delay", type=int, default=2, metavar="SECONDS",
                        help="seconds to wait before the PSCI reset (default 2)")
    args = parser.parse_args()
    if args.reset_entry and (args.reset_at or args.reset_va):
        raise SystemExit("--reset-entry and --reset-at/--reset-va are exclusive")
    if args.reset_at and args.reset_va:
        raise SystemExit("--reset-at and --reset-va are exclusive")
    for address in args.ret_at:
        if int(address, 0) & 3:
            raise SystemExit("--ret-at address must be 4-byte aligned")
    if args.reset_delay <= 0:
        raise SystemExit("--reset-delay must be positive")
    pokes = [(text, *parse_poke(text)) for text in args.poke]

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

    entry_resets = args.reset_entry
    entry_stub = assemble(args.clang, probe_source(band=True, reset=entry_resets, delay=args.reset_delay))
    probed, facts = add_entry_probe(kernel_bytes, parsed, entry_stub)
    facts["entry_mode"] = "band+reset" if entry_resets else "band+jump"
    facts["delay_seconds"] = args.reset_delay

    if args.reset_at or args.reset_va:
        reset_stub = assemble(args.clang, probe_source(band=False, reset=True, delay=args.reset_delay))
        if args.reset_va:
            probed, patch_facts = patch_address_in_place(probed, int(args.reset_va, 0), reset_stub)
        else:
            probed, patch_facts = patch_symbol_in_place(probed, args.reset_at, reset_stub)
        facts["reset"] = patch_facts
    for address in args.ret_at:
        probed, ret_facts = patch_word_at(probed, int(address, 0), 0xD65F03C0)
        facts.setdefault("ret", []).append(ret_facts)
    for text, symbol, address, offset, word in pokes:
        key = None
        if symbol is not None:
            key, address = symbol_address(probed, symbol)
            address += offset
        probed, poke_facts = patch_word_at(probed, address, word, executable=False)
        poke_facts["request"] = text
        if key is not None:
            poke_facts["symbol"] = key
            poke_facts["symbol_offset"] = offset
        facts.setdefault("poke", []).append(poke_facts)

    check = parse_kernel(probed)
    if check["entry"] != facts["entry_va"]:
        raise SystemExit("patched kernel does not re-parse with the expected layout")
    if check["end"] < facts["stub_va"]:
        raise SystemExit("patched kernel lost the entry probe segment")

    kernel_out = directory / "kernel.macho"
    adt_out = directory / (kernel_out.name + ".adt")
    kernel_out.write_bytes(probed)
    adt_out.write_bytes(adt_bytes)
    manifest = {
        "schema": "unixnu-elden-entry-probe/v2",
        "baseline_kernel": {"bytes": len(kernel_bytes), "sha256": sha256(kernel_bytes)},
        "baseline_adt": {"bytes": len(adt_bytes), "sha256": sha256(adt_bytes)},
        "output_kernel": {"bytes": len(probed), "sha256": sha256(probed)},
        "output_adt": {"bytes": len(adt_bytes), "sha256": sha256(adt_bytes)},
        "source": {"payload_image": str(args.payload_image), "kernel_path": KERNEL_IMAGE_PATH,
                   "adt_path": ADT_IMAGE_PATH},
        "layout": facts,
        "band": "blue BGRA 0xFF0000FF, full width, 64 rows centred on height/2",
        "reset": facts.get("reset"),
    }
    (directory / "probe.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"probe kernel: {kernel_out} {len(probed)} bytes sha256={sha256(probed)}")
    print(f"probe adt:    {adt_out} {len(adt_bytes)} bytes sha256={sha256(adt_bytes)}")
    print("entry %#x -> b %#x (stub), mode %s" % (
        facts["entry_va"], facts["stub_va"], facts["entry_mode"]))
    if "reset" in facts:
        print("reset %#x (%s): %d bytes in place, delay %ss" % (
            facts["reset"]["patched_va"], facts["reset"].get("patched_symbol", "address"),
            facts["reset"]["patched_bytes"], args.reset_delay))
    for item in facts.get("poke", []):
        print("poke  %#x (%s): %#010x -> %#010x" % (
            item["va"], item.get("symbol", item["segment"]), item["word"], item["new"]))


if __name__ == "__main__":
    main()
