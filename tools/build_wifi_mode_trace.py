"""Add bounded mode/capability/event metadata by rebuilding only v189 WMI."""
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
from ModeTracePatch import patch


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbols(path, defined):
    return {name for name, value in global_symbols(path).items() if bool(value[0] & 0x0e) == defined}


def main():
    if sys.flags.optimize:
        raise ValueError("Assertions required")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime-build", "parent-runtime", "llvm", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument('--response-trace',action='store_true')
    args = parser.parse_args()
    parent, output = args.parent_runtime.resolve(), args.output.resolve()
    prior = json.loads((parent / "result.json").read_text())
    assert prior["ce3_flow_trace"] and prior["pci_window_trace"]
    assert (prior["rebuilt_units"], prior["retained_units"]) == (7, 118)
    assert prior["producer_credit_timeout_changes"] is False
    assert bool(prior.get('mode_trace'))==args.response_trace and not prior.get('response_trace')
    assert sha(parent / "WifiRuntimeMsiBinding.o") == prior["binding_sha256"]
    link = list(prior["link"])
    objects = link[link.index("-o") + 2:]
    assert len(objects) == 125
    inherited = {name: sha(Path(name)) for name in objects}
    old, = [Path(name) for name in objects if Path(name).name == "ath12k_wmi.o"]
    original = parent / "wmi.c"
    assert sha(original) == prior["objects"]["ath12k_wmi.o"]["source_sha256"]
    output.mkdir(parents=True, exist_ok=False)
    source, raw, obj, dep = output / "wmi.c", output / "ath12k_wmi.raw.o", output / "ath12k_wmi.o", output / "ath12k_wmi.d"
    selected=patch
    if args.response_trace:
        from ModeResponsePatch import patch as selected
    source.write_bytes(selected(original.read_bytes()))
    command = list(prior["objects"]["ath12k_wmi.o"]["command"])
    assert command[command.index("-target") + 1] == "arm64-apple-ios17.0" and "-mgeneral-regs-only" in command
    assert command.count(str(original)) == 1
    command[command.index(str(original))] = str(source)
    command[command.index("-o") + 1] = str(raw)
    command[command.index("-MF") + 1] = str(dep)
    command += ["-I", str(ROOT / "drivers/EldenWifi")]
    process = subprocess.run(command, cwd=output, capture_output=True)
    (output / "compile.log").write_bytes(process.stdout + process.stderr)
    process.check_returncode()
    consumed = {}
    base=args.runtime_build.resolve()
    hal_dependencies={}
    for identity_path in (base/'objects/raw').glob('*.inputs.json'):
        for name,digest in json.loads(identity_path.read_text())['dependencies'].items():
            if name in hal_dependencies:assert hal_dependencies[name]==digest,name
            hal_dependencies[name]=digest
    for path in shlex.split(dep.read_text().replace("\\\n", " ").split(":", 1)[1]):
        file = Path(path)
        if path in prior["consumed_inputs"] and path != str(original):
            assert sha(file) == prior["consumed_inputs"][path], path
        elif path in hal_dependencies:
            assert sha(file)==hal_dependencies[path],path
        elif path != str(source):
            assert file.is_relative_to(ROOT / "drivers/EldenWifi") or path in prior["consumed_inputs"], path
        consumed[path] = sha(file)
    rename_file = base / "objects/rename.txt"
    rename = dict(line.split() for line in rename_file.read_text().splitlines())
    subprocess.run([str(args.llvm / "llvm-objcopy"), "--redefine-syms=" + str(rename_file), str(raw), str(obj)], check=True)
    assert global_symbols(obj) == {rename.get(name, name): value for name, value in global_symbols(raw).items()}
    assert sections(raw) == sections(obj) and not any(name.endswith("/__mod_init_func") for name in sections(obj))
    assert symbols(obj, True) == symbols(old, True)
    if args.response_trace:
        assert symbols(obj,False)<=symbols(parent/'WifiRuntimeMsiBinding.o',True)|symbols(parent/'WifiRuntimeMsiBinding.o',False)
    else:
        assert symbols(obj,False)==symbols(old,False)
    assembly = subprocess.check_output([str(args.llvm / "llvm-objdump"), "-dr", obj], text=True)
    (output / "wmi.asm").write_text(assembly)
    assert not re.search(r"^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)", assembly, re.M)
    target = output / "WifiRuntimeMsiBinding.o"
    link[link.index("-o") + 1] = str(target)
    link = [str(obj) if value == str(old) else value for value in link]
    process = subprocess.run(link, capture_output=True)
    (output / "link.log").write_bytes(process.stdout + process.stderr)
    process.check_returncode()
    assert symbols(target, True) == symbols(parent / "WifiRuntimeMsiBinding.o", True)
    assert symbols(target, False) == symbols(parent / "WifiRuntimeMsiBinding.o", False)
    for path, digest in inherited.items():
        assert sha(Path(path)) == digest, path
    own = ["tools/build_wifi_mode_trace.py", "tools/test_wifi_mode_trace.py",
           "tools/analysis/decode_wifi_mode_trace.py", "drivers/EldenWifi/ModeTraceMeta.h",
           "drivers/EldenWifi/peach/ModeTracePatch.py"]
    if args.response_trace:
        own+=['drivers/EldenWifi/ModeResponse.h','drivers/EldenWifi/ModeResponseTrace.inc',
              'drivers/EldenWifi/peach/ModeResponsePatch.py','tools/test_wifi_mode_response.py',
              'tools/analysis/decode_wifi_response_trace.py']
    inputs = dict(prior["source_inputs"], **{name: sha(ROOT / name) for name in own})
    for name, digest in inputs.items():
        assert sha(ROOT / name) == digest, name
    records = dict(prior["objects"])
    records["ath12k_wmi.o"] = dict(object_sha256=sha(obj), source_sha256=sha(source), command=command,
                                   warnings=(output / "compile.log").read_bytes().count(b"warning:"), added_imports=[])
    result = dict(prior, mode_trace=True, reversible_mode_insertions=True, mode_note_limits=[8, 4, 16],
                  compiled_this_step=1, parent_binding_sha256=prior["binding_sha256"], binding_sha256=sha(target),
                  source_inputs=inputs, consumed_inputs=consumed, objects=records, inherited_objects=inherited,
                  link=link, full_kernel_linked=False, hardware_tested=False)
    result.update(response_trace=args.response_trace,reversible_response_insertions=args.response_trace,
                  fixed_response_bytes=20 if args.response_trace else 0,ce3_config_read_count=6 if args.response_trace else 0)
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(compiled=True, binding_sha256=sha(target), warnings=records["ath12k_wmi.o"]["warnings"])))


if __name__ == "__main__":
    main()
