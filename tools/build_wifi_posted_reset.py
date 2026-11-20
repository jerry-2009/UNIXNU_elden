"""Compile the TB322FC posted-reset fix on the retained OEM-init runtime."""
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
from PostedResetPatch import patch, UPSTREAM


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbols(path, defined):
    return {n for n, v in global_symbols(path).items() if bool(v[0] & 0x0e) == defined}


def main():
    if sys.flags.optimize:
        raise ValueError("Assertions required")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime-build", "parent-build", "llvm", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    base, parent, out = args.runtime_build.resolve(), args.parent_build.resolve(), args.output.resolve()
    prior = json.loads((parent / "result.json").read_text())
    if not prior.get("host_wake_capability_trial") or not prior.get("pci_state_trace_trial") or sha(parent / "WifiRuntimeMsiBinding.o") != prior["binding_sha256"]:
        raise ValueError("Qualified host-capability / PCI state parent required")
    cmd = list(prior["pci_state_command"])
    original, = [Path(v) for v in cmd if v.endswith("/pci.c")]
    old, = [Path(v) for v in prior["link"] if v.endswith("/ath12k_pci.o")]
    if sha(original) != prior["pci_state_source_sha256"] or sha(old) != prior["pci_state_object_sha256"]:
        raise ValueError("Consumed PCI source/object changed")
    out.mkdir(parents=True, exist_ok=False)
    source, raw, obj, dep = out / "pci.c", out / "ath12k_pci.raw.o", out / "ath12k_pci.o", out / "pci.d"
    source.write_bytes(patch(original.read_bytes()))
    cmd[cmd.index(str(original))] = str(source)
    cmd[cmd.index("-o") + 1] = str(raw)
    cmd[cmd.index("-MF") + 1] = str(dep)
    result = subprocess.run(cmd, cwd=out, capture_output=True)
    (out / "compile.log").write_bytes(result.stdout + result.stderr)
    result.check_returncode()
    dependencies = shlex.split(dep.read_text().replace("\\\n", " ").split(":", 1)[1])
    inherited = prior["pci_state_consumed_inputs"]
    if set(dependencies) - {str(source)} != set(inherited) - {str(original)}:
        raise ValueError("Posted-reset dependency set changed")
    for value in dependencies:
        if value != str(source) and sha(Path(value)) != inherited[value]:
            raise ValueError("Posted-reset header changed: " + value)
    subprocess.run([str(args.llvm / "llvm-objcopy"), "--redefine-syms=" + str(base / "objects/rename.txt"), str(raw), str(obj)], check=True)
    rename = dict(line.split() for line in (base / "objects/rename.txt").read_text().splitlines())
    if global_symbols(obj) != {rename.get(n, n): v for n, v in global_symbols(raw).items()} or sections(obj) != sections(raw):
        raise ValueError("Posted-reset rename changed code/data")
    if symbols(obj, True) != symbols(old, True) or symbols(obj, False) != symbols(old, False):
        raise ValueError("Posted-reset PCI interface changed")
    assembly = subprocess.check_output([str(args.llvm / "llvm-objdump"), "-dr", obj], text=True)
    (out / "pci.asm").write_text(assembly)
    if any(n.endswith("/__mod_init_func") for n in sections(obj)) or re.search(r"^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)", assembly, re.M):
        raise ValueError("Posted-reset initializer/SIMD introduced")
    link = list(prior["link"])
    objects = [Path(v) for i, v in enumerate(link) if v.endswith(".o") and link[i - 1] != "-o"]
    if len(objects) != 125 or objects.count(old) != 1:
        raise ValueError("Wrong retained posted-reset runtime")
    retained = {str(p): sha(p) for p in objects if p != old}
    target = out / "WifiRuntimeMsiBinding.o"
    link[link.index("-o") + 1] = str(target)
    link = [str(obj) if v == str(old) else v for v in link]
    result_link = subprocess.run(link, capture_output=True)
    (out / "link.log").write_bytes(result_link.stdout + result_link.stderr)
    result_link.check_returncode()
    if symbols(target, True) != symbols(parent / "WifiRuntimeMsiBinding.o", True) or symbols(target, False) != symbols(parent / "WifiRuntimeMsiBinding.o", False):
        raise ValueError("Combined posted-reset interface changed")
    for name, digest in retained.items():
        if sha(Path(name)) != digest:
            raise ValueError("Retained runtime object changed")
    own = ["tools/build_wifi_posted_reset.py", "tools/test_wifi_posted_reset.py", "drivers/EldenWifi/peach/PostedResetPatch.py"]
    proof = dict(prior)
    proof.update(posted_reset_trial=True, posted_reset_reversible=True,
                 posted_reset_upstream_commit=UPSTREAM, posted_reset_readbacks=2,
                 posted_reset_delay_ms=10, posted_reset_writes_unchanged=True,
                 posted_reset_ring_credit_firmware_unchanged=True,
                 posted_reset_parent_source_sha256=sha(original),
                 posted_reset_parent_object_sha256=sha(old),
                 posted_reset_source_sha256=sha(source), posted_reset_object_sha256=sha(obj),
                 parent_posted_reset_binding_sha256=prior["binding_sha256"],
                 pci_state_source_sha256=sha(source), pci_state_object_sha256=sha(obj),
                 pci_state_command=cmd, pci_state_consumed_inputs={v: sha(Path(v)) for v in dependencies},
                 pci_state_warning_count=result.stderr.count(b"warning:"),
                 binding_sha256=sha(target), link=link, retained_objects=retained,
                 source_inputs={**prior["source_inputs"], **{n: sha(ROOT / n) for n in own}}, hardware_tested=False)
    (out / "result.json").write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps({k: proof[k] for k in ("compiled", "posted_reset_trial", "binding_sha256", "pci_state_warning_count", "hardware_tested")}))


if __name__ == "__main__":
    main()
