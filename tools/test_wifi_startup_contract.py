"""Exercise the retained observer plus parsed firmware status and wake scope."""
import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drivers/EldenWifi/peach"))
from StartupContractPatch import INIT_REPORT, patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cc", "pci-source", "core-source", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    for name, source in (("pci.c", args.pci_source), ("core.c", args.core_source)):
        (out / name).write_bytes(patch(name, source.read_bytes()))
        try:
            patch(name, source.read_bytes() + b" ")
        except ValueError:
            pass
        else:
            raise AssertionError("Changed parent accepted")
    # Reuse the actual original observer scenarios without copying its fixture.
    tree = ast.parse((ROOT / "tools/test_wifi_pci_state_trace.py").read_text())
    # The fixture is one literal followed by .replace(), so read that literal.
    literals = [node.value.func.value.value for node in ast.walk(tree)
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "code" for t in node.targets)
                and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                and isinstance(node.value.func.value, ast.Constant)]
    if len(literals) != 1:
        raise ValueError("Original observer fixture changed")
    code = literals[0]
    derived = (out / "pci.c").read_text()
    start = derived.index("struct elden_pci_write_note")
    end = derived.index("\nint ath12k_pci_hif_suspend(", start)
    code = code.replace("@HELPER@", derived[start:end] + "\n" + INIT_REPORT)
    code = code.replace("typedef uint32_t u32;", "typedef uint32_t u32;typedef uint64_t u64;\n#define ELDEN_STARTUP_HOST_TEST 1\nstatic unsigned par_reads;static u64 elden_wifi_host_par(unsigned long a){par_reads++;return a;}")
    code = code.replace("u32 pm_state,dev_state,ee;", "u32 pm_state,dev_state,ee;bool wake_set;")
    code = code.replace("struct ath12k_base {u32 hw_rev;", "struct ath12k_base {u32 hw_rev;bool wmi_ready;u32 wlan_init_status,num_radios,fw_pdev_count;struct {u32 preferred_hw_mode;} wmi_ab;")
    marker = " lx_mmio_trace=NULL;free(mem);"
    extra = r'''
 memset(&elden_pci_state,0,sizeof elden_pci_state);lx_mmio_trace=NULL;par_reads=0;
 elden_pci_state_install(&ab);m.wake_db=mem+0x6f8;
 unsigned prior=elden_pci_state.count;
 write32(mem+0x6f8,1);write32(mem+0x6fc,0);
 assert(elden_pci_state.count==prior+2);cases++;
 m.mhi_dev=NULL;write32(mem+0x6f8,0);assert(elden_pci_state.count==prior+2);m.mhi_dev=&dev;cases++;
 write32(mem+0x700,1);assert(elden_pci_state.count==prior+2);cases++;
 m.wake_db=mem+0x90000-4;write32(mem+0x90000-4,1);assert(elden_pci_state.count==prior+2);cases++;
 m.wake_db=mem+0x6f8;m.wake_set=true;elden_pci_state_read(&ab,0x3004,1);
 assert(strstr(last,"wake-set=1")&&strstr(last,"db-off=6f8"));cases++;
 elden_pci_state_read(&ab,0x3004,0);assert(par_reads==3);cases++;
 elden_pci_state_read(&ab,0x3004,0);assert(par_reads==3);cases++;
 ab.wmi_ready=true;ab.num_radios=1;ab.fw_pdev_count=2;ab.wmi_ab.preferred_hw_mode=5;
 u32 statuses[]={0,1,0x12340005,0xffffffffU};
 for(unsigned i=0;i<4;i++){
   ab.wlan_init_status=statuses[i];unsigned seen=logs;
   elden_wifi_init_contract(&ab,0);assert(logs==seen+1);
   char expected[40];snprintf(expected,sizeof expected,"status=%x",statuses[i]);assert(strstr(last,expected));
   assert(ab.wlan_init_status==statuses[i]);cases++;
 }
 elden_wifi_init_contract(&ab,-110);assert(strstr(last,"wait=-110"));cases++;
 ab.hw_rev=1;unsigned seen=logs;elden_wifi_init_contract(&ab,0);assert(logs==seen);cases++;
'''
    if code.count(marker) != 1:
        raise ValueError("Original observer fixture terminal changed")
    code = code.replace(marker, extra + marker)
    code = code.replace("m={mem,0x90000,mem+0x1ff8,1,2,2,1,&dev}",
                        "m={.regs=mem,.reg_len=0x90000,.wake_db=mem+0x1ff8,.pm_state=1,.dev_state=2,.ee=2,.dev_wake=1,.mhi_dev=&dev}")
    code = code.replace("ab={17,mem,0x90000,&pci}",
                        "ab={.hw_rev=17,.mem=mem,.mem_len=0x90000,.pci=&pci}")
    src = out / "test.c"
    src.write_text(code)
    command = [str(args.cc), "-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
               "-fsanitize=address,undefined", "-fno-sanitize-recover=all", str(src), "-o", str(out / "test")]
    if sys.platform == "darwin":
        command[1:1] = ["-isysroot", subprocess.check_output(["xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True).strip()]
    for name, cmd in (("compile", command), ("run", [str(out / "test")])):
        result = subprocess.run(cmd, capture_output=True)
        (out / (name + ".log")).write_bytes(result.stdout + result.stderr)
        result.check_returncode()
    own = ["tools/test_wifi_startup_contract.py", "tools/test_wifi_pci_state_trace.py",
           "drivers/EldenWifi/peach/StartupContractPatch.py"]
    proof = dict(passed=True, actual_helpers=True, original_observer_scenarios_retained=True,
                 asan_ubsan=True, mhi_mmio_par_modeled=True, no_new_device_writes=True,
                 hardware_tested=False, summary=(out / "run.log").read_text().strip(),
                 source_inputs={n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in own})
    (out / "result.json").write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
