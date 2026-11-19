"""Exercise original/derived charge policies across transport interruption.

Uses real production policy functions and the prior audited OEM-contract peer.
The peer does not execute firmware or establish hardware charge acceptance.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drivers/EldenPmicGlink"))
from LinkSource import header, policy, client
from WindowSource import policy as original_policy


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if sys.flags.optimize:
        raise ValueError("Assertions required")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / "drivers/EldenPmicGlink"
    fixture = (source / "TestChargeWindow.c").read_bytes()
    marker = b"\nint main(void)"
    if fixture.count(marker) != 1:
        raise ValueError("OEM fixture entry differs")
    firmware_peer = fixture[:fixture.index(marker)]
    records = []
    for name, generated, generated_header, flags in (
        ("original", original_policy(), (source / "ChargePolicy.h").read_bytes(), ["-DORIGINAL"]),
        ("fixed", policy(), header(), []),
    ):
        folder = output / name
        folder.mkdir()
        (folder / "ChargePolicy.c").write_bytes(generated)
        (folder / "ChargePolicy.h").write_bytes(generated_header)
        (folder / "ChargeLinkFirmware.inc").write_bytes(firmware_peer)
        (folder / "TestChargeLink.c").write_bytes((source / "TestChargeLink.c").read_bytes())
        executable = folder / "test"
        command = [args.cc, "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                   "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                   "-I", str(folder), *flags, str(folder / "ChargePolicy.c"),
                   str(folder / "TestChargeLink.c"), "-o", str(executable)]
        for phase, invocation in (("compile", command), ("run", [str(executable)])):
            process = subprocess.run(invocation, capture_output=True)
            (folder / (phase + ".log")).write_bytes(process.stdout + process.stderr)
            process.check_returncode()
        records.append(dict(case=name, policy_sha256=sha(generated), header_sha256=sha(generated_header),
                            summary=(folder / "run.log").read_text(encoding="utf-8").strip()))

    # Existing scenarios use the fixed header by compiling a copied test in the
    # same directory. A quoted include must not resolve to the frozen header.
    fixed = output / "fixed"
    regressions = []
    for name in ("TestChargeWindow.c", "TestChargePolicy.c"):
        (fixed / name).write_bytes((source / name).read_bytes())
        executable = fixed / Path(name).stem
        command = [args.cc, "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                   "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                   "-I", str(fixed), str(fixed / "ChargePolicy.c"), str(fixed / name),
                   "-o", str(executable)]
        for phase, invocation in (("compile", command), ("run", [str(executable)])):
            process = subprocess.run(invocation, capture_output=True)
            (fixed / (Path(name).stem + "-" + phase + ".log")).write_bytes(process.stdout + process.stderr)
            process.check_returncode()
        regressions.append(dict(test=name, summary=(fixed / (Path(name).stem + "-run.log")).read_text(encoding="utf-8").strip()))

    (output / "PmicClient.cpp").write_bytes(client())
    inputs = {name: sha((ROOT / name).read_bytes()) for name in (
        "drivers/EldenPmicGlink/LinkSource.py", "drivers/EldenPmicGlink/WindowSource.py",
        "drivers/EldenPmicGlink/VerificationSource.py", "drivers/EldenPmicGlink/ChargePolicy.c",
        "drivers/EldenPmicGlink/ChargePolicy.h", "drivers/EldenPmicGlink/ChargeVerification.h",
        "profiles/v91/sources/power/PmicClient.cpp", "drivers/EldenPmicGlink/TestChargeLink.c",
        "drivers/EldenPmicGlink/TestChargeWindow.c", "drivers/EldenPmicGlink/TestChargePolicy.c",
        "tools/test_charge_link.py")}
    result = dict(passed=True, actual_production_policies_executed=True,
                  original_partial_inhibit_reproduced=True, firmware_behavior_modeled=True,
                  sanitizers=["ASan", "UBSan"], results=records, regressions=regressions,
                  client_source_sha256=sha(client()), generated_header_sha256=sha(header()),
                  source_inputs=inputs, firmware_peer_sha256=sha(firmware_peer),
                  native_consumer_recompile_required=True, hardware_tested=False)
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "results": records, "regressions": regressions}))


if __name__ == "__main__":
    main()
