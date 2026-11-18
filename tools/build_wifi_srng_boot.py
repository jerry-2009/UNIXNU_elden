"""Prepare entry, package and independently audit a qualified CE3 observation boot.

Only declared component/original inputs are used. This does not access a tablet.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.flags.optimize:
        raise ValueError("Assertions required")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("kernel-build", "clean-build", "stock-boot", "parent-vbmeta", "avbtool", "signing-key", "llvm", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    kernel, clean, output = args.kernel_build.resolve(), args.clean_build.resolve(), args.output.resolve()
    result = json.loads((kernel / "result.json").read_text())
    if result["profile"] not in ("wifi-srng-trace","wifi-pci-window-trace","wifi-ce3-flow-trace") or result["runtime_snapshot"].get("srng_trace") is not True:
        raise ValueError("Complete qualified SRNG kernel required")
    output.mkdir(parents=True, exist_ok=False)
    originals = json.loads((ROOT / "profiles/v91/image-build/plan.json").read_text())["prelink"]["original_executable_sha256"]
    (output / "entry-plan.json").write_text(json.dumps({"candidate_sha256": result["kernel_sha256"], "original_executable_sha256": originals}, indent=2) + "\n")

    def run(name, *arguments):
        command = [sys.executable, "-B", str(ROOT / "tools" / name), *map(str, arguments)]
        (output / (name + ".command.json")).write_text(json.dumps(command, indent=2) + "\n")
        with (output / (name + ".log")).open("xb") as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)

    run("prepare_v91_entry.py", "--kernel", kernel / "kernel.macho", "--plan", output / "entry-plan.json",
        "--clang", args.llvm / "clang", "--output", output / "entry")
    variant = ["--wcn-report", kernel / "result.json", "--bt-runtime", kernel / "runtime"]
    run("build_v91_boot.py", "--portable-fat", "--kernel", output / "entry/kernel.macho",
        "--entry-report", output / "entry/result.json", "--fd", clean / "firmware/UEFI.fd",
        "--loader", clean / "loader/EldenPayloadLoader.efi", "--data", clean / "data/data.packed",
        "--data-report", clean / "data/result.json", "--library", clean / "icon/EldenIconCpuMode.dylib",
        "--agent", clean / "agent/iconservicesagent", "--stock-boot", args.stock_boot,
        "--avbtool", args.avbtool, "--key", args.signing_key, "--clang", args.llvm / "clang",
        *variant, "--output", output / "boot")
    run("audit_v91_boot.py", "--image", output / "boot/boot-signed.img", "--entry-kernel", output / "entry/kernel.macho",
        "--entry-report", output / "entry/result.json", "--stock-boot", args.stock_boot,
        "--parent-vbmeta", args.parent_vbmeta, "--data-report", clean / "data/result.json",
        *variant, "--output", output / "boot/audit.json")
    audit = json.loads((output / "boot/audit.json").read_text())
    image_hash = hashlib.sha256((output / "boot/boot-signed.img").read_bytes()).hexdigest()
    if not audit["accepted_static"] or audit["image_sha256"] != image_hash or audit["bluetooth_runtime"]["profile"] != result["profile"]:
        raise ValueError("SRNG image audit failed")
    if (audit["rollback_index"], audit["footer_location"], audit["parent_boot_chain_location"]) != (1738713600, 0, 3):
        raise ValueError("Boot floor changed")
    receipt = {"profile": result["profile"], "image_sha256": image_hash, "session": audit["session"],
               "kernel_sha256": result["kernel_sha256"], "accepted_static": True, "hardware_tested": False,
               "packaging_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
