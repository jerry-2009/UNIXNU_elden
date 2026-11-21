"""Compile parsed-init and existing-wake evidence over the qualified PCI state runtime."""
import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

from replay_xnu_objects import global_symbols, sections

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drivers/EldenWifi/peach"))
from StartupContractPatch import patch


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbols(path, defined):
    return {name for name, value in global_symbols(path).items() if bool(value[0] & 0x0e) == defined}


def main():
    if sys.flags.optimize:
        raise ValueError("Assertions required")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime-build", "parent-build", "llvm", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    base, parent, out = args.runtime_build.resolve(), args.parent_build.resolve(), args.output.resolve()
    prior = json.loads((parent / "result.json").read_text())
    if not prior.get("pci_state_trace_trial") or prior.get("umac_access_trial") or prior.get("umac_command_lease_trial") or prior.get("oem_init_mode_trial") or sha(parent / "WifiRuntimeMsiBinding.o") != prior["binding_sha256"]:
        raise ValueError("Exact passive original-shadow parent required")
    out.mkdir(parents=True, exist_ok=False)
    changes, units = {}, {}
    for name in ("pci.c", "core.c"):
        row = prior if name == "pci.c" else prior["timeline_units"]["ath12k_core.o"]
        cmd = list(row["pci_state_command"] if name == "pci.c" else row["command"])
        originals = [Path(v) for v in cmd if v.endswith("/" + name)]
        if len(originals) != 1:
            raise ValueError("Exact consumed source required: " + name)
        original = originals[0]
        old = parent / "ath12k_pci.o" if name == "pci.c" else Path(row["command"][row["command"].index("-o") + 1])
        if name == "core.c":
            old = old.with_name("ath12k_core.o")
        expected_source = row["pci_state_source_sha256"] if name == "pci.c" else row["source_sha256"]
        expected_object = row["pci_state_object_sha256"] if name == "pci.c" else row["object_sha256"]
        if sha(original) != expected_source or sha(old) != expected_object:
            raise ValueError("Consumed parent source/object changed: " + name)
        source, raw, obj, dep = out / name, out / (name[:-2] + ".raw.o"), out / ("ath12k_" + name[:-2] + ".o"), out / (name[:-2] + ".d")
        source.write_bytes(patch(name, original.read_bytes()))
        cmd[cmd.index(str(original))] = str(source)
        cmd[cmd.index("-o") + 1] = str(raw)
        cmd[cmd.index("-MF") + 1] = str(dep)
        cmd += ["-iquote", str(original.parent)]
        result = subprocess.run(cmd, cwd=out, capture_output=True)
        (out / (name + ".log")).write_bytes(result.stdout + result.stderr)
        result.check_returncode()
        dependencies = shlex.split(dep.read_text().replace("\\\n", " ").split(":", 1)[1])
        inherited = row["pci_state_consumed_inputs"] if name == "pci.c" else row["consumed_inputs"]
        if set(dependencies) - {str(source)} != set(inherited) - {str(original)}:
            raise ValueError("Startup evidence dependency set changed: " + name)
        for value in dependencies:
            if value != str(source) and sha(Path(value)) != inherited[value]:
                raise ValueError("Consumed header changed: " + value)
        subprocess.run([str(args.llvm / "llvm-objcopy"), "--redefine-syms=" + str(base / "objects/rename.txt"), str(raw), str(obj)], check=True)
        rename = dict(line.split() for line in (base / "objects/rename.txt").read_text().splitlines())
        if global_symbols(obj) != {rename.get(n, n): v for n, v in global_symbols(raw).items()} or sections(obj) != sections(raw):
            raise ValueError("Startup evidence rename changed code/data")
        if symbols(obj, True) != symbols(old, True) or symbols(obj, False) != symbols(old, False):
            raise ValueError("Startup evidence interface changed")
        assembly = subprocess.check_output([str(args.llvm / "llvm-objdump"), "-dr", obj], text=True)
        (out / (name + ".asm")).write_text(assembly)
        if any(n.endswith("/__mod_init_func") for n in sections(obj)) or re.search(r"^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)", assembly, re.M):
            raise ValueError("Unexpected startup evidence initializer/SIMD")
        changes[str(old)] = str(obj)
        units[name] = dict(source_sha256=sha(source), object_sha256=sha(obj), warnings=result.stderr.count(b"warning:"), command=cmd, consumed_inputs={v: sha(Path(v)) for v in dependencies})
    link = list(prior["link"])
    objects = [Path(v) for i, v in enumerate(link) if v.endswith(".o") and link[i - 1] != "-o"]
    if len(objects) != 125 or not set(changes) <= set(map(str, objects)):
        raise ValueError("Wrong retained startup evidence runtime")
    retained = {str(p): sha(p) for p in objects if str(p) not in changes}
    target = out / "WifiRuntimeMsiBinding.o"
    link[link.index("-o") + 1] = str(target)
    link = [changes.get(v, v) for v in link]
    result = subprocess.run(link, capture_output=True)
    (out / "link.log").write_bytes(result.stdout + result.stderr)
    result.check_returncode()
    if symbols(target, True) != symbols(parent / "WifiRuntimeMsiBinding.o", True) or symbols(target, False) != symbols(parent / "WifiRuntimeMsiBinding.o", False):
        raise ValueError("Combined startup evidence interface changed")
    for name, digest in retained.items():
        if sha(Path(name)) != digest:
            raise ValueError("Retained runtime object changed")
    own = ["tools/build_wifi_startup_contract.py", "tools/test_wifi_startup_contract.py", "drivers/EldenWifi/peach/StartupContractPatch.py"]
    proof = dict(prior)
    proof.update(startup_contract_trial=True, startup_contract_reversible=True,
                 startup_contract_no_new_device_writes=True, startup_contract_par_cpu_only=True,
                 startup_contract_par_reads_max=3, startup_contract_fw_status_parsed=True,
                 startup_contract_wake_db_owner_checked=True, startup_contract_payload_logging=False,
                 startup_contract_units=units, parent_startup_binding_sha256=prior["binding_sha256"],
                 binding_sha256=sha(target), link=link, retained_objects=retained,
                 source_inputs={**prior["source_inputs"], **{n: sha(ROOT / n) for n in own}}, hardware_tested=False)
    (out / "result.json").write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps({k: proof[k] for k in ("compiled", "startup_contract_trial", "binding_sha256", "hardware_tested")}))


if __name__ == "__main__":
    main()
