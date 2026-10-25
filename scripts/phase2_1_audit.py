#!/usr/bin/env python3
"""Audit the elden Phase 2.1 firmware memory, ADT and CPU handoff.

The script compiles the minimal XNU hardware tree, generates an ADT with the
current shared UniXNU generator, decodes that ADT independently, and checks the
selected handoff window against a firmware FDT.

By default it audits ``dts/elden-firmware-memory.dts``. Pass ``--linux-dir`` to
rebuild the full candidate FDT from the pinned elden Linux source, or
``--firmware-dtb`` to audit a live tree captured from the device.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tomllib
import zlib
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UNIXNU = ROOT / ".cache" / "phase2-plan" / "UniXNU"
DEFAULT_OUTPUT = ROOT / ".cache" / "phase2.1"
HARDWARE_DTS = ROOT / "dts" / "elden.dts"
SANITIZED_FIRMWARE_DTS = ROOT / "dts" / "elden-firmware-memory.dts"
BOARD = ROOT / "board.toml"
SOC = ROOT / "soc" / "sm8750" / "soc.toml"
LINUX_BOARD_DTS = Path("arch/arm64/boot/dts/qcom/sm8750-lenovo-elden.dts")
EXPECTED_MPIDRS = (0x0, 0x100, 0x200, 0x300, 0x400, 0x500, 0x10000, 0x10100)
UEFI_FD = (0xFF300000, 0x00400000)
UEFI_GOP = (0xFC800000, 0x02B00000)
RAMDISK_ALIGNMENT = 4096
MU_MEMORY_MAP = (
    ROOT
    / "third_party"
    / "mu_wide_platforms"
    / "Platforms"
    / "PakalaPkg"
    / "Device"
    / "lenovo-y700g4"
    / "Library"
    / "PlatformMemoryMapLib"
    / "PlatformMemoryMapLib.c"
)


@dataclass(frozen=True)
class Range:
    name: str
    start: int
    size: int

    @property
    def end(self) -> int:
        return self.start + self.size

    def overlaps(self, other: "Range") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass
class AdtNode:
    name: str
    properties: dict[str, bytes]
    children: list["AdtNode"]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run(command: list[str | os.PathLike[str]], *, input_text: str | None = None) -> bytes:
    rendered = [str(part) for part in command]
    print("+ " + " ".join(rendered), file=sys.stderr)
    result = subprocess.run(
        rendered,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=input_text is not None,
    )
    if result.returncode != 0:
        if result.stdout:
            sys.stderr.write(
                result.stdout.decode(errors="replace")
                if isinstance(result.stdout, bytes)
                else result.stdout
            )
        if result.stderr:
            sys.stderr.write(
                result.stderr.decode(errors="replace")
                if isinstance(result.stderr, bytes)
                else result.stderr
            )
        raise SystemExit(f"command failed ({result.returncode}): {' '.join(rendered)}")
    return result.stdout.encode() if isinstance(result.stdout, str) else result.stdout


def executable(name: str, fallbacks: tuple[Path, ...] = ()) -> Path:
    value = os.environ.get(name.upper())
    if value:
        path = Path(value).expanduser()
        if path.is_file():
            return path
        raise SystemExit(f"{name.upper()} does not name a file: {path}")
    found = shutil.which(name)
    if found:
        return Path(found)
    for path in fallbacks:
        if path.is_file():
            return path
    raise SystemExit(f"missing required tool: {name}")


DTC = executable("dtc", (ROOT / ".cache" / "dtc-src" / "dtc",))


def compile_dts(source: Path, output: Path, include_dirs: list[Path]) -> bytes:
    output.parent.mkdir(parents=True, exist_ok=True)
    command: list[str | Path] = [DTC, "-I", "dts", "-O", "dtb"]
    for directory in include_dirs:
        command += ["-i", directory]
    command += ["-Wno-unique_unit_address", "-Wno-unit_address_vs_reg"]
    command += ["-o", output, source]
    run(command)
    return output.read_bytes()


def compile_pinned_linux_fdt(linux_dir: Path, output: Path) -> tuple[bytes, str]:
    source = linux_dir / LINUX_BOARD_DTS
    if not source.is_file():
        raise SystemExit(
            f"missing {source}; fetch the pinned elden Linux source with "
            "sparse paths arch/arm64/boot/dts/qcom, include/dt-bindings and include/uapi"
        )
    revision = run(["git", "-C", linux_dir, "rev-parse", "HEAD"]).decode().strip()
    configured = tomllib.loads(SOC.read_text())["soc"]["source_revision"]
    if revision != configured:
        raise SystemExit(
            f"Linux source revision {revision} differs from soc.toml {configured}"
        )
    dirty = run(
        [
            "git",
            "-C",
            linux_dir,
            "status",
            "--porcelain",
            "--",
            "arch/arm64/boot/dts/qcom",
            "include/dt-bindings",
        ]
    ).decode()
    if dirty:
        raise SystemExit(f"pinned Linux DTS inputs are modified:\n{dirty}")

    compiler = executable(
        "clang",
        (
            ROOT / ".cache" / "phase1" / "bin" / "clang",
            Path("/opt/local/libexec/llvm-20/bin/clang"),
        ),
    )
    command = [
        compiler,
        "-E",
        "-nostdinc",
        "-undef",
        "-D__DTS__",
        "-x",
        "assembler-with-cpp",
        "-I",
        linux_dir / "arch/arm64/boot/dts/qcom",
        "-I",
        linux_dir / "include",
        "-I",
        linux_dir / "include/uapi",
        "-I",
        linux_dir / "arch/arm64/boot/dts",
        source,
    ]
    preprocessed = run(command).decode()
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        DTC,
        "-I",
        "dts",
        "-O",
        "dtb",
        "-Wno-unique_unit_address",
        "-Wno-unit_address_vs_reg",
        "-o",
        output,
        "-",
    ]
    run(command, input_text=preprocessed)
    return output.read_bytes(), revision


def parse_adt(data: bytes) -> AdtNode:
    def parse_node(offset: int) -> tuple[AdtNode, int]:
        if offset + 8 > len(data):
            raise ValueError("truncated ADT node header")
        property_count, child_count = struct.unpack_from("<II", data, offset)
        offset += 8
        properties: dict[str, bytes] = {}
        for _ in range(property_count):
            if offset + 36 > len(data):
                raise ValueError("truncated ADT property header")
            raw_name = data[offset : offset + 32]
            name = raw_name.split(b"\0", 1)[0].decode("ascii")
            length = struct.unpack_from("<I", data, offset + 32)[0]
            offset += 36
            if offset + length > len(data):
                raise ValueError("truncated ADT property value")
            value = data[offset : offset + length]
            offset = (offset + length + 3) & ~3
            if name in properties:
                raise ValueError(f"duplicate ADT property: {name}")
            properties[name] = value
        children = []
        for _ in range(child_count):
            child, offset = parse_node(offset)
            children.append(child)
        return AdtNode(properties.get("name", b"").rstrip(b"\0").decode(), properties, children), offset

    root, consumed = parse_node(0)
    if consumed != len(data):
        raise ValueError(f"ADT has {len(data) - consumed} trailing bytes")
    return root


def adt_child(node: AdtNode, name: str) -> AdtNode:
    matches = [child for child in node.children if child.name == name]
    if len(matches) != 1:
        raise ValueError(f"ADT requires one /{name} child, found {len(matches)}")
    return matches[0]


def adt_u32(node: AdtNode, name: str) -> int:
    value = node.properties.get(name)
    if value is None or len(value) != 4:
        raise ValueError(f"{node.name}:{name} is not a u32")
    return struct.unpack("<I", value)[0]


def adt_u64(node: AdtNode, name: str) -> int:
    value = node.properties.get(name)
    if value is None or len(value) != 8:
        raise ValueError(f"{node.name}:{name} is not a u64")
    return struct.unpack("<Q", value)[0]


def adt_strings(node: AdtNode, name: str) -> list[str]:
    value = node.properties.get(name)
    if value is None or not value.endswith(b"\0"):
        raise ValueError(f"{node.name}:{name} is not a terminated string list")
    return [item.decode() for item in value.rstrip(b"\0").split(b"\0")]


def fdt_ranges(node, devicetree) -> list[Range]:
    result = []
    for child in node.children:
        if "reg" not in child.properties:
            continue
        for index, (start, size) in enumerate(devicetree.registers(child)):
            if size:
                result.append(Range(f"{child.name}[{index}]", start, size))
    return result


def fdt_u32(node, name: str) -> int:
    return node.scalar(name)


def fdt_string(node, name: str) -> str | None:
    values = node.strings(name)
    return values[0] if values else None


def fdt_optional_integer(node, name: str) -> int | None:
    cells = node.cells(name)
    return devicetree_number(cells) if cells else None


def devicetree_number(cells: list[int]) -> int:
    value = 0
    for cell in cells:
        value = (value << 32) | cell
    return value


def covered(candidate: Range, ranges: list[Range]) -> bool:
    return any(
        item.start <= candidate.start and candidate.end <= item.end for item in ranges
    )


def overlap_names(candidate: Range, ranges: list[Range]) -> list[str]:
    return [item.name for item in ranges if candidate.overlaps(item)]


def audit_fdt(fdt: bytes) -> dict:
    root = devicetree.read_fdt(fdt)
    compatible = root.strings("compatible")
    markers = []
    for entry in root.walk():
        markers.extend(
            key for key in entry.properties if "elden" in key.lower()
        )
        for key in (
            "compatible",
            "model",
            "label",
            "qcom,mdss-dsi-panel-name",
            "qcom,mdss-dsi-panel-type",
        ):
            if key not in entry.properties:
                continue
            try:
                values = entry.strings(key)
            except ValueError:
                continue
            markers.extend(value for value in values if "elden" in value.lower())
        if "elden" in entry.name.lower() and entry.name not in markers:
            markers.append(entry.name)
    if "lenovo,elden" in compatible:
        identity = "lenovo,elden"
    elif (
        any(item in compatible for item in ("qcom,sun", "qcom,sunp"))
        and markers
    ):
        identity = "generic-qcom-sun-with-elden-markers"
    else:
        raise ValueError(f"FDT does not identify elden: {compatible}, markers={markers}")
    memory_nodes = [
        entry for entry in root.children if entry.strings("device_type") == ["memory"]
    ]
    if len(memory_nodes) != 1:
        raise ValueError(f"firmware FDT has {len(memory_nodes)} memory nodes")
    memory_node = memory_nodes[0]
    memory_ranges = [
        Range(f"memory[{index}]", start, size)
        for index, (start, size) in enumerate(devicetree.registers(memory_node))
        if size
    ]
    reserved_node = next(
        (entry for entry in root.children if entry.name == "reserved-memory"), None
    )
    if reserved_node is None:
        raise ValueError("firmware FDT has no /reserved-memory")
    reserved_ranges = fdt_ranges(reserved_node, devicetree)
    chosen = next((entry for entry in root.children if entry.name == "chosen"), None)
    if chosen is None:
        raise ValueError("firmware FDT has no /chosen")
    framebuffer = next(
        (
            entry
            for entry in chosen.children
            if entry.strings("compatible") == ["simple-framebuffer"]
        ),
        None,
    )
    expected_pixel = {
        "width": 1904,
        "height": 3040,
        "stride": 1904 * 4,
        "format": "a8r8g8b8",
    }
    if framebuffer is None:
        framebuffer_range = Range("GOP framebuffer (phase 1 static)", *UEFI_GOP)
        pixel = expected_pixel | {"source": "phase-1-gop-static"}
    else:
        framebuffer_ranges = devicetree.registers(framebuffer)
        if len(framebuffer_ranges) != 1:
            raise ValueError("framebuffer must have one register range")
        framebuffer_range = Range("GOP framebuffer", *framebuffer_ranges[0])
        pixel = {
            "width": fdt_u32(framebuffer, "width"),
            "height": fdt_u32(framebuffer, "height"),
            "stride": fdt_u32(framebuffer, "stride"),
            "format": fdt_string(framebuffer, "format"),
            "source": "firmware-fdt",
        }
        if pixel != (expected_pixel | {"source": "firmware-fdt"}):
            raise ValueError(f"unexpected elden framebuffer: {pixel}")

    initrd_start = fdt_optional_integer(chosen, "linux,initrd-start")
    initrd_end = fdt_optional_integer(chosen, "linux,initrd-end")
    if (initrd_start is None) != (initrd_end is None):
        raise ValueError("firmware FDT has only one initrd endpoint")
    initrd = None
    if initrd_start is not None and initrd_end is not None:
        if not 0 < initrd_start < initrd_end:
            raise ValueError(f"invalid initrd range {initrd_start:#x}-{initrd_end:#x}")
        if initrd_start % RAMDISK_ALIGNMENT:
            raise ValueError("initrd start is not aligned to 4096 bytes")
        initrd = Range("initrd", initrd_start, initrd_end - initrd_start)

    return {
        "compatible": compatible,
        "identity": identity,
        "elden_markers": markers,
        "memory": [range_record(item) for item in memory_ranges],
        "reserved_memory": [range_record(item) for item in reserved_ranges],
        "framebuffer": range_record(framebuffer_range) | pixel,
        "initrd": range_record(initrd) if initrd else None,
        "_memory_ranges": memory_ranges,
        "_reserved_ranges": reserved_ranges,
        "_framebuffer_range": framebuffer_range,
        "_initrd_range": initrd,
    }


def parse_uefi_memory_map() -> list[dict]:
    if not MU_MEMORY_MAP.is_file():
        raise SystemExit(
            f"missing {MU_MEMORY_MAP}; bootstrap or retain the pinned "
            "mu_wide_platforms checkout"
        )
    entries = []
    for line in MU_MEMORY_MAP.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith('{ "') and not stripped.startswith('{"'):
            continue
        fields = [field.strip() for field in stripped.strip("{},").split(",")]
        if len(fields) < 7:
            continue
        try:
            address = int(fields[1], 0)
            size = int(fields[2], 0)
        except ValueError:
            continue
        entries.append(
            {
                "name": fields[0].strip('"'),
                "start": address,
                "size": size,
                "memory_type": fields[6],
            }
        )
    return entries


def range_record(item: Range) -> dict:
    return {
        "name": item.name,
        "start": f"{item.start:#x}",
        "size": f"{item.size:#x}",
        "end": f"{item.end:#x}",
    }


def parse_adt_and_check(
    adt: bytes,
    hardware_fdt: bytes,
    board: dict,
) -> tuple[dict, Range]:
    root = parse_adt(adt)
    if root.name != "device-tree":
        raise ValueError(f"unexpected ADT root {root.name!r}")
    chosen = adt_child(root, "chosen")
    cpus = adt_child(root, "cpus")
    psci = adt_child(root, "psci")
    arm_io = adt_child(root, "arm-io")
    defaults = adt_child(root, "defaults")
    adt_child(root, "options")
    product = adt_child(root, "product")
    memory_map = adt_child(chosen, "memory-map")
    adt_child(chosen, "manifest-properties")

    random_seed = chosen.properties.get("random-seed", b"")
    if len(random_seed) != 64 or not any(random_seed):
        raise ValueError("ADT random-seed is not 64 bytes")
    if adt_u32(chosen, "nvram-bank-size") != 8192:
        raise ValueError("unexpected CHRP NVRAM bank size")
    nvram = chosen.properties.get("nvram-proxy-data", b"")
    if len(nvram) != 8192:
        raise ValueError("unexpected CHRP NVRAM image size")
    if nvram[4:9] != b"nvram" or nvram[36:40] != b"comm":
        raise ValueError("unexpected CHRP NVRAM headers")
    if struct.unpack_from("<I", nvram, 16)[0] != zlib.adler32(nvram[20:]):
        raise ValueError("CHRP NVRAM checksum is invalid")
    candidate = Range("XNU handoff", adt_u64(chosen, "dram-base"), adt_u64(chosen, "dram-size"))
    if candidate.size != int(str(board["payload"]["dram_size"]), 0):
        raise ValueError("ADT DRAM size differs from board.toml")
    if adt_u64(chosen, "darwinboot-memory-size") != int(
        str(board["payload"]["adt"]["owned_memory_size"]), 0
    ):
        raise ValueError("ADT DarwinBoot window differs from board.toml")
    if adt_u32(defaults, "sleep-disabled") != 1:
        raise ValueError("ADT /defaults sleep-disabled is not 1")
    if adt_u32(chosen, "chip-id") != int(board["payload"]["adt"]["chip_id"], 16):
        raise ValueError("ADT chip-id differs from board.toml")
    if adt_u64(chosen, "unique-chip-id") != 1:
        raise ValueError("host audit did not use its declared non-device test seed")
    memory_map_properties = set(memory_map.properties) - {"name"}
    if memory_map_properties:
        raise ValueError(
            "ADT has optional memory-map placeholders without matching payload inputs"
        )

    cpu_nodes = cpus.children
    if len(cpu_nodes) != len(EXPECTED_MPIDRS):
        raise ValueError(f"ADT exports {len(cpu_nodes)} CPUs, expected 8")
    mpidrs = tuple(adt_u32(cpu, "reg") for cpu in cpu_nodes)
    if mpidrs != EXPECTED_MPIDRS:
        raise ValueError(f"unexpected ADT MPIDRs: {mpidrs}")
    states = [cpu.properties.get("state", b"").rstrip(b"\0").decode() for cpu in cpu_nodes]
    if states != ["running", *(["waiting"] * 7)]:
        raise ValueError(f"unexpected ADT CPU states: {states}")
    if any(adt_u32(cpu, "timebase-frequency") != 19_200_000 for cpu in cpu_nodes):
        raise ValueError("ADT CPU timebase differs from 19.2 MHz")
    if psci.properties.get("method", b"").rstrip(b"\0") != b"smc":
        raise ValueError("ADT PSCI method is not SMC")

    ranges = arm_io.properties.get("ranges", b"")
    if len(ranges) != 24:
        raise ValueError("ADT /arm-io ranges is not one 24-byte tuple")
    _, arm_base, arm_size = struct.unpack("<QQQ", ranges)
    intc = adt_child(arm_io, "intc")
    intc_reg = intc.properties.get("reg", b"")
    if len(intc_reg) != 32:
        raise ValueError("ADT /arm-io/intc reg is not two address/size pairs")
    intc_values = struct.unpack("<QQQQ", intc_reg)
    physical_intc = (arm_base + intc_values[0], arm_base + intc_values[2])
    if physical_intc != (0x16000000, 0x16080000):
        raise ValueError(f"unexpected physical GIC bases: {physical_intc}")
    if intc.properties.get("redistributor-stride") != struct.pack("<Q", 0x40000):
        raise ValueError("unexpected ADT redistributor stride")
    if adt_child(root, "product").properties.get(
        "product-name"
    ) != b"iPad Pro (12.9-inch) (2nd generation)\0":
        raise ValueError("ADT product identity differs from the selected OS profile")

    # Ensure the source input really has the same one-range handoff contract.
    hardware_root = devicetree.read_fdt(hardware_fdt)
    hardware_memory = [
        entry
        for entry in hardware_root.children
        if entry.strings("device_type") == ["memory"]
    ]
    if (
        len(hardware_memory) != 1
        or len(devicetree.registers(hardware_memory[0])) != 1
    ):
        raise ValueError("hardware DTS does not have one contiguous XNU range")
    hardware_range = Range(
        "hardware handoff", *devicetree.registers(hardware_memory[0])[0]
    )
    if (candidate.start, candidate.size) != (hardware_range.start, hardware_range.size):
        raise ValueError("ADT DRAM range differs from the hardware handoff node")

    summary = {
        "bytes": len(adt),
        "sha256": sha256_bytes(adt),
        "root_compatible": adt_strings(root, "compatible"),
        "xnu_handoff": range_record(candidate),
        "darwinboot_window": f"{adt_u64(chosen, 'darwinboot-memory-size'):#x}",
        "random_seed_bytes": len(random_seed),
        "nvram": {
            "bank_size": adt_u32(chosen, "nvram-bank-size"),
            "bank_count": adt_u32(chosen, "nvram-bank-count"),
            "current_bank": adt_u32(chosen, "nvram-current-bank"),
        },
        "defaults": {"sleep-disabled": adt_u32(defaults, "sleep-disabled")},
        "memory_map_placeholders": sorted(memory_map_properties),
        "cpu_mpidrs": [f"{value:#x}" for value in mpidrs],
        "cpu_states": states,
        "timebase_hz": adt_u32(cpu_nodes[0], "timebase-frequency"),
        "psci_method": psci.properties["method"].rstrip(b"\0").decode(),
        "arm_io": {"base": f"{arm_base:#x}", "size": f"{arm_size:#x}"},
        "gic": {
            "distributor": f"{physical_intc[0]:#x}",
            "redistributor": f"{physical_intc[1]:#x}",
            "stride": "0x40000",
        },
        "product_name": product.properties["product-name"].rstrip(b"\0").decode(),
        "options_present": True,
    }
    return summary, hardware_range


def main() -> None:
    global UNIXNU_DIR, devicetree

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unixnu-dir", type=Path, default=DEFAULT_UNIXNU)
    parser.add_argument("--linux-dir", type=Path)
    parser.add_argument("--firmware-dtb", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if sum(value is not None for value in (args.linux_dir, args.firmware_dtb)) > 1:
        parser.error("choose at most one of --linux-dir and --firmware-dtb")
    if not (args.unixnu_dir / "scripts" / "unixnu" / "devicetree.py").is_file():
        parser.error(f"not a UniXNU source tree: {args.unixnu_dir}")
    args.unixnu_dir = args.unixnu_dir.resolve()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    UNIXNU_DIR = args.unixnu_dir
    sys.path.insert(0, str(UNIXNU_DIR / "scripts"))
    from unixnu import devicetree
    from unixnu.profiles import merge

    board = tomllib.loads(BOARD.read_text())
    kernel_args = list(board["payload"]["kernel_args"])
    if "armcpu-diagnostics=1" not in kernel_args:
        raise SystemExit("boot CPU verification requires armcpu-diagnostics=1")
    if "armcpu-spi-ipi=1" in kernel_args:
        raise SystemExit(
            "armcpu-spi-ipi=1 requires separate elden SGI/SPI evidence before use"
        )
    if "sheng-smp=1" in kernel_args:
        raise SystemExit("the minimum Phase 2.1 milestone must not enable SMP")
    os_profile = (
        UNIXNU_DIR
        / "profiles"
        / "os"
        / board["board"]["os_profile"]
        / "profile.toml"
    )
    config = merge(tomllib.loads(os_profile.read_text()), board)

    hardware_fdt = compile_dts(
        HARDWARE_DTS,
        args.output_dir / "hardware.dtb",
        [ROOT / "soc" / "sm8750" / "dts"],
    )
    if args.firmware_dtb:
        firmware_fdt = args.firmware_dtb.expanduser().resolve().read_bytes()
        firmware_source = {
            "kind": "provided-fdt",
            "path": str(args.firmware_dtb.expanduser().resolve()),
            "sha256": sha256_bytes(firmware_fdt),
        }
    elif args.linux_dir:
        firmware_fdt, revision = compile_pinned_linux_fdt(
            args.linux_dir.expanduser().resolve(), args.output_dir / "firmware-linux.dtb"
        )
        firmware_source = {
            "kind": "pinned-linux-source",
            "path": str(LINUX_BOARD_DTS),
            "revision": revision,
            "sha256": sha256_bytes(firmware_fdt),
        }
    else:
        firmware_fdt = compile_dts(
            SANITIZED_FIRMWARE_DTS, args.output_dir / "firmware-sanitized.dtb", []
        )
        firmware_source = {
            "kind": "sanitised-source",
            "path": str(SANITIZED_FIRMWARE_DTS.relative_to(ROOT)),
            "sha256": sha256_bytes(firmware_fdt),
        }

    firmware = audit_fdt(firmware_fdt)
    adt = devicetree.generate(
        args.output_dir / "hardware.dtb",
        config,
        unique_chip_id="1",
        data=False,
        trust=False,
        addon=False,
    )
    adt_path = args.output_dir / "kernel.macho.adt"
    adt_path.write_bytes(adt)
    adt_summary, hardware_range = parse_adt_and_check(adt, hardware_fdt, board)

    memory_ranges = firmware.pop("_memory_ranges")
    reserved_ranges = firmware.pop("_reserved_ranges")
    framebuffer_range = firmware.pop("_framebuffer_range")
    initrd = firmware.pop("_initrd_range")
    if not covered(hardware_range, memory_ranges):
        raise SystemExit(
            f"XNU handoff {hardware_range.start:#x}+{hardware_range.size:#x} "
            "is not covered by firmware RAM"
        )
    conflicts = overlap_names(hardware_range, reserved_ranges)
    if conflicts:
        raise SystemExit(f"XNU handoff overlaps firmware reservations: {conflicts}")
    if hardware_range.overlaps(framebuffer_range):
        raise SystemExit("XNU handoff overlaps the GOP framebuffer")
    fd = Range("UEFI FD", *UEFI_FD)
    if hardware_range.overlaps(fd):
        raise SystemExit("XNU handoff overlaps the UEFI FD")
    if initrd and initrd.overlaps(hardware_range):
        raise SystemExit("XNU handoff overlaps the initrd")
    if initrd and overlap_names(initrd, reserved_ranges):
        raise SystemExit("initrd overlaps firmware reservations")

    uefi_memory = parse_uefi_memory_map()
    uefi_ranges = [
        Range(entry["name"], entry["start"], entry["size"])
        for entry in uefi_memory
        if entry["size"]
    ]
    uefi_conflicts = [item for item in uefi_ranges if hardware_range.overlaps(item)]
    uefi_types = {
        entry["name"]: entry["memory_type"]
        for entry in uefi_memory
        if entry["size"]
    }
    if not uefi_conflicts or any(
        uefi_types.get(item.name) != "Conv" for item in uefi_conflicts
    ):
        raise SystemExit(
            "XNU handoff must be inside UEFI conventional memory; "
            f"conflicts: {[item.name for item in uefi_conflicts]}"
        )

    old_candidate = Range("rejected low 2 GiB candidate", 0x80000000, 0x80000000)
    old_conflicts = overlap_names(old_candidate, reserved_ranges)
    if not old_conflicts:
        raise SystemExit("audit expected the old low 2 GiB range to hit reservations")
    previous_kernel_carveout = Range("previous A8000000 handoff", 0xA8000000, 0x10000000)
    previous_live_conflicts = []
    if initrd and previous_kernel_carveout.overlaps(initrd):
        previous_live_conflicts.append("live initrd")
    previous_live_conflicts += overlap_names(previous_kernel_carveout, reserved_ranges)

    report = {
        "schema": "unixnu-elden-phase2.1-audit/v1",
        "device": {
            "name": board["board"]["name"],
            "model_id": board["board"]["model_id"],
            "soc": board["board"]["soc"],
        },
        "sources": {
            "unixnu_revision": run(
                ["git", "-C", UNIXNU_DIR, "rev-parse", "HEAD"]
            ).decode().strip(),
            "firmware_fdt": firmware_source,
            "hardware_dts": str(HARDWARE_DTS.relative_to(ROOT)),
            "hardware_dts_sha256": sha256_file(HARDWARE_DTS),
            "hardware_dtb_sha256": sha256_bytes(hardware_fdt),
            "board_sha256": sha256_file(BOARD),
        },
        "firmware_memory": firmware,
        "xnu_handoff": range_record(hardware_range),
        "xnu_handoff_uefi_overlap": [
            range_record(item) | {"memory_type": uefi_types[item.name]}
            for item in uefi_conflicts
        ],
        "uefi_fd": range_record(fd),
        "boot_args": kernel_args,
        "uefi_memory_regions": [
            {
                "name": entry["name"],
                "start": f"{entry['start']:#x}",
                "size": f"{entry['size']:#x}",
                "memory_type": entry["memory_type"],
            }
            for entry in uefi_memory
        ],
        "runtime_only_intervals": [
            "BootShim source stream and decompression workspace: ABL implementation",
            "DarwinBoot kernel/ADT/boot_args placement: recorded at loader handoff",
        ],
        "rejected_old_candidate": {
            "range": range_record(old_candidate),
            "reservation_conflicts": sorted(old_conflicts),
        },
        "rejected_previous_handoff": {
            "range": range_record(previous_kernel_carveout),
            "conflicts": sorted(previous_live_conflicts),
        },
        "adt": adt_summary,
        "checks": {
            "host_passed": True,
            "firmware_fdt_was_provided_by_device": args.firmware_dtb is not None,
            "xnu_range_covered_by_firmware_ram": True,
            "xnu_range_avoids_firmware_reservations": True,
            "framebuffer_matches_known_elden_configuration": True,
            "sleep_disabled_in_final_adt": True,
            "optional_memory_map_matches_inputs": True,
            "boot_cpu_first_and_only_running_cpu": True,
            "boot_cpu_diagnostics_enabled": True,
            "unproven_spi_ipi_disabled": True,
            "secondary_cpu_startup_disabled": True,
        },
    }
    report_path = args.output_dir / "audit.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        f"phase 2.1 audit: OK\n"
        f"  firmware FDT: {firmware_source['kind']} {firmware_source['sha256']}\n"
        f"  XNU window: {hardware_range.start:#x}+{hardware_range.size:#x}\n"
        f"  ADT: {len(adt)} bytes {adt_summary['sha256']}\n"
        f"  report: {report_path}"
    )


if __name__ == "__main__":
    main()
