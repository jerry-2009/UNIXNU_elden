"""Test exact observer helpers and reversible production HAL/WMI insertion."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drivers/EldenWifi/peach"))
from SrngTracePatch import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-build", type=Path, required=True)
    parser.add_argument("--credit-build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = json.loads((args.runtime_build / "objects/build-report.json").read_text())["objects"]
    hal, = [r for r in rows if Path(r["path"]).name == "ath12k_hal.o"]
    inputs = {"hal.c": Path(hal["source"]), "wmi.c": args.credit_build / "wmi.c"}
    for name, path in inputs.items():
        data = path.read_bytes()
        result = patch(name, data)
        (output / name).write_bytes(result)
        try:
            patch(name, data + b"\n")
        except ValueError:
            pass
        else:
            raise AssertionError("Unpinned observer source accepted")
    (output / "wifi7").mkdir()
    (output / "wifi7/hal.h").write_text("#define HAL_OFFSET_FROM_HP_TO_TP 4\n#define HAL_SHADOW_REG(i) (0x1000u+4u*(i))\n")
    code = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <cstring>
using u32=uint32_t;using u64=uint64_t;
#define HAL_SRNG_RING_ID_MAX 32
#define HAL_SHADOW_NUM_REGS_MAX 40
#define HAL_SRNG_REG_GRP_R2 1
#define HAL_SRNG_DIR_SRC 0
#define HAL_SRNG_FLAGS_LMAC_RING 1
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
struct hal_srng {u32 ring_id,ring_dir,flags,ring_size;bool initialized;u32 hwreg_base[2];
 struct {struct {u32 hp;u32 *hp_addr,*tp_addr;} src_ring;} u;};
struct ring {u32 hal_ring_id;};struct pipe {ring *src_ring;};
struct hw {u32 ce_count;bool supports_shadow_regs;};
struct ath12k_base {void *mem;hw *hw_params;struct {pipe ce_pipe[4];} ce;
 struct {hal_srng srng_list[32];int num_shadow_reg_configured;u32 shadow_reg_addr[40];} hal;};
static u32 reads,offsets[2],lines,longest;static char last[1024];
static u32 ath12k_hif_read32(ath12k_base *,u32 off){assert(reads<2);offsets[reads++]=off;return off==0x2000?16:8;}
static void ath12k_warn(ath12k_base *,const char *format,...){va_list a;va_start(a,format);int n=vsnprintf(last,sizeof(last),format,a);va_end(a);assert(n>0&&n<320);lines++;if((u32)n>longest)longest=n;}
#include "SrngTrace.inc"
static unsigned scenarios;
static void init(ath12k_base &ab,hw &params,ring &r,char *mem,u32 &tp){
 memset(&ab,0,sizeof(ab));memset(esn_records,0,sizeof(esn_records));esn_captured=0;reads=lines=0;
 ab.mem=mem;params={4,true};ab.hw_params=&params;r.hal_ring_id=3;ab.ce.ce_pipe[3].src_ring=&r;
 auto &s=ab.hal.srng_list[3];s.ring_id=3;s.ring_dir=HAL_SRNG_DIR_SRC;s.ring_size=64;s.initialized=true;
 s.hwreg_base[1]=0x2000;s.u.src_ring.hp=16;s.u.src_ring.hp_addr=(u32*)(mem+HAL_SHADOW_REG(2));s.u.src_ring.tp_addr=&tp;
 ab.hal.num_shadow_reg_configured=3;ab.hal.shadow_reg_addr[2]=0x2000;
}
int main(){
 ath12k_base ab;hw params;ring r;alignas(4) char mem[0x4000];u32 tp=8;
 init(ab,params,r,mem,tp);auto &s=ab.hal.srng_list[3];
 for(unsigned i=0;i<4;i++){esn_enter(&ab,&s);esn_exit(&s);}for(unsigned i=0;i<7;i++)esn_timer(&s);
 assert(esn_records[3].enter==4&&esn_records[3].exit==4&&esn_records[3].timer==7);
 assert(esn_records[3].hp==16&&esn_records[3].offset==HAL_SHADOW_REG(2));
 elden_wifi_srng_first_wmi(&ab);assert(reads==2&&offsets[0]==0x2000&&offsets[1]==0x2004&&lines==2);
 assert(strstr(last,"sw=16 last=16 enter=4 exit=4 timer=7")&&strstr(last,"hw=10/8 dma-tp=8"));
 elden_wifi_srng_first_wmi(&ab);assert(reads==2&&lines==2);scenarios++;
 for(unsigned fail=0;fail<12;fail++){
  init(ab,params,r,mem,tp);
  if(fail==0)ab.mem=nullptr;if(fail==1)ab.hw_params=nullptr;if(fail==2)params.ce_count=3;
  if(fail==3)ab.ce.ce_pipe[3].src_ring=nullptr;if(fail==4)r.hal_ring_id=32;
  if(fail==5)s.initialized=false;if(fail==6)s.flags=HAL_SRNG_FLAGS_LMAC_RING;
  if(fail==7)ab.hal.num_shadow_reg_configured=41;if(fail==8)s.u.src_ring.tp_addr=nullptr;
  if(fail==9)s.hwreg_base[1]=0x2001;
  if(fail==10)r.hal_ring_id=UINT32_MAX;if(fail==11)ab.hal.num_shadow_reg_configured=-1;
  elden_wifi_srng_first_wmi(&ab);assert(!reads&&lines==1);scenarios++;
 }
 init(ab,params,r,mem,tp);elden_wifi_srng_first_wmi(nullptr);assert(!reads&&!lines);scenarios++;
 s.ring_id=32;esn_enter(&ab,&s);esn_exit(&s);esn_timer(&s);assert(!esn_records[3].enter);scenarios++;
 init(ab,params,r,mem,tp);esn_records[3]={UINT64_MAX,UINT64_MAX,UINT64_MAX,UINT64_MAX,UINT64_MAX};
 elden_wifi_srng_first_wmi(&ab);assert(reads==2&&lines==2);scenarios++;
 printf("PASS %u actual observer scenarios; two real HP/TP accesses, no shadow read, one-shot and bounds; max line=%u\n",scenarios,longest);
}
'''
    (output / "test.cpp").write_text(code)
    command = ["clang++", "-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
               "-Wno-misleading-indentation", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
               "-I" + str(ROOT / "drivers/EldenWifi"), "-I" + str(output), str(output / "test.cpp"), "-o", str(output / "test")]
    for name, command in [("compile", command), ("run", [str(output / "test")])]:
        process = subprocess.run(command, capture_output=True)
        (output / (name + ".log")).write_bytes(process.stdout + process.stderr)
        process.check_returncode()
    result = {"passed": True, "actual_observer_helpers": True, "reversible_sources": 2,
              "hardware_mmio_and_driver_protocol_modeled": True, "sanitizers": ["ASan", "UBSan"],
              "observer_sha256": hashlib.sha256((ROOT / "drivers/EldenWifi/SrngTrace.inc").read_bytes()).hexdigest(),
              "summary": (output / "run.log").read_text().strip(), "hardware_tested": False}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["summary"])


if __name__ == "__main__":
    main()
