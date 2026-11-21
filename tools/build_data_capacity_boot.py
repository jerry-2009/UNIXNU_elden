"""Package and independently audit the explicit2GiB software-KeyStore profile.

Inputs may be outputs of build_clean.py or separately qualified component
stages. No archived recipe, developer path, tablet or device writer is used.
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
        raise ValueError("Assertions must remain enabled")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("kernel-build", "clean-build", "seed-build", "stock-boot",
                 "parent-vbmeta", "avbtool", "signing-key", "llvm", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--data-ui-replay", action="store_true", help="Explicit bounded software UI trial")
    args = parser.parse_args()
    kernel = args.kernel_build.resolve(strict=True)
    clean = args.clean_build.resolve(strict=True)
    seed = args.seed_build.resolve(strict=True)
    result = json.loads((kernel / "result.json").read_text())
    if result["profile"] != "data-capacity-2g-key" or result.get("actual_keystore_adapter_rebuilt") is not True:
        raise ValueError("The actual2GiB KeyStore adapter is required")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    originals = json.loads((ROOT / "profiles/v91/image-build/plan.json").read_text())["prelink"]["original_executable_sha256"]
    plan = {"candidate_sha256": result["kernel_sha256"], "original_executable_sha256": originals}
    (output / "entry-plan.json").write_text(json.dumps(plan, indent=2) + "\n")

    def run(name, *arguments):
        command = [sys.executable, "-B", str(ROOT / "tools" / name), *map(str, arguments)]
        with (output / (name + ".log")).open("xb") as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)

    run("prepare_v91_entry.py", "--kernel", kernel / "kernel.macho", "--plan", output / "entry-plan.json",
        "--clang", args.llvm / "clang", "--output", output / "entry")
    variant = ["--wcn-report", kernel / "result.json", "--bt-runtime", kernel / "runtime",
               "--expanded-data", "--keep-packed-data"]
    if args.data_ui_replay:
        variant.append("--data-ui-replay")
    run("build_v91_boot.py", "--portable-fat", "--kernel", output / "entry/kernel.macho",
        "--entry-report", output / "entry/result.json", "--fd", clean / "firmware/UEFI.fd",
        "--loader", clean / "loader/EldenPayloadLoader.efi", "--data", seed / "data.packed",
        "--data-report", seed / "result.json", "--library", clean / "icon/EldenIconCpuMode.dylib",
        "--agent", clean / "agent/iconservicesagent", "--stock-boot", args.stock_boot,
        "--avbtool", args.avbtool, "--key", args.signing_key, "--clang", args.llvm / "clang",
        *variant, "--output", output / "boot")
    run("audit_v91_boot.py", "--image", output / "boot/boot-signed.img",
        "--entry-kernel", output / "entry/kernel.macho", "--entry-report", output / "entry/result.json",
        "--stock-boot", args.stock_boot, "--parent-vbmeta", args.parent_vbmeta,
        "--data-report", seed / "result.json", *variant, "--output", output / "boot/audit.json")
    audit = json.loads((output / "boot/audit.json").read_text())
    image_hash = hashlib.sha256((output / "boot/boot-signed.img").read_bytes()).hexdigest()
    if not audit["accepted_static"] or audit["image_sha256"] != image_hash:
        raise ValueError("Boot audit failed")
    qualification = audit["bluetooth_runtime"]
    if bool(qualification.get("data_ui_replay")) != args.data_ui_replay:
        raise ValueError("UI trial mode differs from requested audit")
    if qualification.get("keystore_capacity_updated") is not True or qualification.get("keep_packed_data") is not True:
        raise ValueError("Missing actual KeyStore or packed Data qualification")
    if (audit["rollback_index"], audit["footer_location"], audit["parent_boot_chain_location"]) != (1738713600, 0, 3):
        raise ValueError("Boot floor changed")
    receipt = {"profile": result["profile"], "image_sha256": image_hash, "session": audit["session"],
               "kernel_sha256": result["kernel_sha256"], "data_packed_sha256": qualification["data_packed_sha256"],
               "expected_data_bytes": qualification["expected_data_bytes"], "accepted_static": True,
               "keystore_capacity_updated": True, "keep_packed_data": True, "tablet_accessed": False,
               "data_ui_replay": args.data_ui_replay,
               "hardware_tested": False}
    (output / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
