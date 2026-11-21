"""Exercise the actual old/new reset body with delayed PCI posted writes."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cc", "pci-source", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "drivers/EldenWifi/peach"))
    from PostedResetPatch import patch, reset_body
    original = args.pci_source.read_bytes()
    fixed = patch(original)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "pci.c").write_bytes(fixed)
    code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdbool.h>
typedef uint32_t u32;
#define PCIE_SOC_GLOBAL_RESET 0x3008u
#define PCIE_SOC_GLOBAL_RESET_V 1u
struct ath12k_base {int unused;};
static u32 reg, queued, initial;
static bool pending, posted, down;
static unsigned reads, writes, waits, warnings, restores, at_write, pulse;
static char events[16];static unsigned used;
static void arrive(void){
 if(!pending)return;
 if((queued&1)&&!(reg&1))at_write=waits*10;
 if(!(queued&1)&&(reg&1))pulse=waits*10-at_write;
 reg=queued;pending=false;
}
static u32 ath12k_pci_read32(struct ath12k_base *ab,u32 off){
 assert(ab&&off==0x3008);events[used++]='R';reads++;arrive();return down?UINT32_MAX:reg;
}
static void ath12k_pci_write32(struct ath12k_base *ab,u32 off,u32 val){
 assert(ab&&off==0x3008);assert((val&~1u)==(initial&~1u));
 events[used++]='W';writes++;queued=val;pending=true;if(!posted)arrive();
}
static void mdelay(u32 ms){assert(ms==10);events[used++]='D';waits++;}
static void ath12k_warn(struct ath12k_base *ab,const char *format){assert(ab&&format);warnings++;}
static void ath12k_pci_restore_window(struct ath12k_base *ab){assert(ab);events[used++]='S';restores++;}
@OLD@
@NEW@
static void begin(u32 value,bool delayed,bool inaccessible){
 reg=initial=value;queued=0;pending=false;posted=delayed;down=inaccessible;
 reads=writes=waits=warnings=restores=at_write=pulse=used=0;
}
int main(void){
 unsigned cases=0;struct ath12k_base ab={0};
 for(unsigned i=0;i<16;i++){
  u32 value=(0xa5a54000u|(i<<4));
  begin(value,true,false);old_reset(&ab);
  assert(writes==2&&waits==2&&restores==1&&reads==2&&warnings==0&&pulse==0);cases++;
  begin(value,true,false);new_reset(&ab);
  assert(writes==2&&waits==2&&restores==1&&reads==4&&warnings==0&&pulse==10);
  assert(reg==value&&!pending&&used==9);
  const char expected[]="RWRDWRDRS";for(unsigned n=0;n<9;n++)assert(events[n]==expected[n]);cases++;
  begin(value,false,false);new_reset(&ab);
  assert(writes==2&&waits==2&&pulse==10&&reg==value&&warnings==0);cases++;
 }
 begin(UINT32_MAX,true,true);new_reset(&ab);
 assert(warnings==1&&restores==1&&writes==2&&waits==2);cases++;
 printf("PASS %u actual old/new posted-reset scenarios; queue latency/PCI I/O modeled, not hardware proof\n",cases);
}
'''.replace("@OLD@", reset_body(original.decode()).replace("ath12k_pci_soc_global_reset", "old_reset", 1)).replace("@NEW@", reset_body(fixed.decode()).replace("ath12k_pci_soc_global_reset", "new_reset", 1))
    source = out / "test.c"
    source.write_text(code)
    command = [str(args.cc), "-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-fno-sanitize-recover=all", str(source), "-o", str(out / "test")]
    if sys.platform == "darwin":
        command[1:1] = ["-isysroot", subprocess.check_output(["xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True).strip()]
    for name, cmd in [("compile", command), ("run", [str(out / "test")])]:
        result = subprocess.run(cmd, capture_output=True)
        (out / (name + ".log")).write_bytes(result.stdout + result.stderr)
        result.check_returncode()
    own = ["tools/test_wifi_posted_reset.py", "drivers/EldenWifi/peach/PostedResetPatch.py"]
    proof = dict(passed=True, actual_reset_body=True, asan_ubsan=True, pci_io_modeled=True,
                 hardware_tested=False, summary=(out / "run.log").read_text().strip(),
                 source_inputs={n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in own})
    (out / "result.json").write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
