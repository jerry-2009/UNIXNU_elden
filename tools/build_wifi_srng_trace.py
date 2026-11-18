"""Rebuild only common HAL/WMI over the exact v179 credit-observer runtime."""
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
from SrngTracePatch import patch


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbols(path, defined):
    return {name for name, value in global_symbols(path).items() if bool(value[0] & 0x0e) == defined}


def main():
    if sys.flags.optimize:
        raise ValueError("Assertions required")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime-build", "credit-build", "llvm", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    base, parent, output = args.runtime_build.resolve(), args.credit_build.resolve(), args.output.resolve()
    prior = json.loads((parent / "result.json").read_text())
    assert prior["credit_trace"] and prior["units"] == 125 and prior["rebuilt_units"] == 4
    assert sha(parent / "WifiRuntimeMsiBinding.o") == prior["binding_sha256"]
    rows = json.loads((base / "objects/build-report.json").read_text())["objects"]
    rename = dict(line.split() for line in (base / "objects/rename.txt").read_text().splitlines())
    output.mkdir(parents=True, exist_ok=False)
    link = list(prior["link"])
    old_objects = link[link.index("-o") + 2:]
    assert len(old_objects) == 125
    inherited = {name: sha(Path(name)) for name in old_objects}
    replacements, records, consumed = {}, {}, {}
    for objname, name in (("ath12k_hal.o", "hal.c"), ("ath12k_wmi.o", "wmi.c")):
        row, = [r for r in rows if Path(r["path"]).name == objname]
        old, = [Path(p) for p in old_objects if Path(p).name == objname]
        identity = json.loads((base / "objects/raw" / objname.replace(".o", ".inputs.json")).read_text())
        original = parent / name if name == "wmi.c" else Path(row["source"])
        command = list(prior["objects"][objname]["command"] if name == "wmi.c" else identity["command"])
        if name == "wmi.c":
            assert sha(original) == prior["objects"][objname]["source_sha256"]
        else:
            assert sha(original) == row["source_sha256"]
        source = output / name
        source.write_bytes(patch(name, original.read_bytes()))
        raw, obj, dep = output / objname.replace(".o", ".raw.o"), output / objname, output / objname.replace(".o", ".d")
        assert command[command.index("-target") + 1] == "arm64-apple-ios17.0" and "-mgeneral-regs-only" in command
        assert command.count(str(original)) == 1
        command[command.index(str(original))] = str(source)
        command[command.index("-o") + 1] = str(raw)
        command[command.index("-MF") + 1] = str(dep)
        command += ["-I", str(ROOT / "drivers/EldenWifi")]
        run = subprocess.run(command, cwd=output, capture_output=True)
        (output / (objname + ".log")).write_bytes(run.stdout + run.stderr)
        run.check_returncode()
        dependencies = shlex.split(dep.read_text().replace("\\\n", " ").split(":", 1)[1])
        for path in dependencies:
            file = Path(path)
            actual = sha(file)
            if path in identity["dependencies"] and path != str(original):
                assert actual == identity["dependencies"][path], path
            elif path in prior["consumed_inputs"]:
                assert actual == prior["consumed_inputs"][path], path
            elif path != str(source):
                assert file.is_relative_to(ROOT / "drivers/EldenWifi") or file.is_relative_to(base / "component"), path
            consumed[path] = actual
        subprocess.run([str(args.llvm / "llvm-objcopy"), "--redefine-syms=" + str(base / "objects/rename.txt"), str(raw), str(obj)], check=True)
        assert global_symbols(obj) == {rename.get(n, n): v for n, v in global_symbols(raw).items()}
        assert sections(raw) == sections(obj) and not any(n.endswith("/__mod_init_func") for n in sections(obj))
        assert symbols(obj, True) == symbols(old, True) | ({"_elden_wifi_srng_first_wmi"} if name == "hal.c" else set())
        assembly = subprocess.check_output([str(args.llvm / "llvm-objdump"), "-dr", obj], text=True)
        (output / (objname + ".asm")).write_text(assembly)
        assert not re.search(r"^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)", assembly, re.M)
        records[objname] = {"object_sha256": sha(obj), "source_sha256": sha(source), "command": command,
                            "warnings": run.stderr.count(b"warning:"), "added_imports": sorted(symbols(obj, False) - symbols(old, False))}
        replacements[str(old)] = str(obj)
    target = output / "WifiRuntimeMsiBinding.o"
    link[link.index("-o") + 1] = str(target)
    link = [replacements.get(p, p) for p in link]
    run = subprocess.run(link, capture_output=True)
    (output / "link.log").write_bytes(run.stdout + run.stderr)
    run.check_returncode()
    assert symbols(target, True) == symbols(parent / "WifiRuntimeMsiBinding.o", True) | {"_elden_wifi_srng_first_wmi"}
    assert symbols(target, False) == symbols(parent / "WifiRuntimeMsiBinding.o", False)
    for name, digest in inherited.items():
        assert sha(Path(name)) == digest, name
    for name, digest in consumed.items():
        assert sha(Path(name)) == digest, name
    own = ["tools/build_wifi_srng_trace.py", "tools/test_wifi_srng_trace.py", "drivers/EldenWifi/SrngTrace.h",
           "drivers/EldenWifi/SrngTrace.inc", "drivers/EldenWifi/peach/SrngTracePatch.py"]
    sources = dict(prior["source_inputs"], **{name: sha(ROOT / name) for name in own})
    for name, digest in sources.items():
        assert sha(ROOT / name) == digest, name
    result = {"compiled": True, "units": 125, "rebuilt_units": 5, "retained_units": 120,
              "compiled_this_step": 2, "credit_trace": True, "srng_trace": True, "append_only_observer": True,
              "base_binding_sha256": prior["base_binding_sha256"], "parent_binding_sha256": prior["binding_sha256"],
              "binding_sha256": sha(target), "source_inputs": sources, "objects": records,
              "inherited_objects": inherited, "consumed_inputs": consumed, "link": link,
              "scalar": True, "producer_credit_timeout_changes": False, "full_kernel_linked": False,
              "hardware_tested": False}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"compiled": True, "binding_sha256": result["binding_sha256"],
                      "warnings": {name: r["warnings"] for name, r in records.items()}}, indent=2))


if __name__ == "__main__":
    main()
