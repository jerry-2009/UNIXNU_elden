"""Run the actual HAL pointer selector against source/destination ring cases."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('cc','hal-source','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
    from Ce3DirectPointerPatch import patch,callback
    raw=a.hal_source.read_bytes();fixed=patch(raw)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);(out/'hal.c').write_bytes(fixed)
    bodies=callback(raw.decode()).replace('ath12k_wifi7_hal_set_umac_srng_ptr_addr(', 'select_old(',1)+'\n'+callback(fixed.decode()).replace('ath12k_wifi7_hal_set_umac_srng_ptr_addr(', 'select_new(',1)
    code=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
typedef uint32_t u32;
#define ATH12K_HW_PEACH_HW20 17
#define HAL_SRNG_RING_ID_CE0_SRC 64
#define HAL_SRNG_REG_GRP_R2 1
#define HAL_SRNG_DIR_SRC 0
#define HAL_REO1_RING_TP 4
#define HAL_REO1_RING_HP 0
#define ATH12K_DBG_HAL 0
#define ath12k_dbg(...) ((void)0)
#define ath12k_warn(...) ((void)0)
struct hal_srng {unsigned ring_id,ring_dir;u32 hwreg_base[2];union {struct {u32 *hp_addr;} src_ring;struct {u32 *tp_addr;} dst_ring;} u;};
struct params {bool supports_shadow_regs;};
struct ath12k_base {unsigned hw_rev;void *mem;struct params *hw_params;};
@BODIES@
int main(void){
 unsigned cases=0;struct params hw={true};struct ath12k_base ab={17,(void *)(uintptr_t)0x10000000,&hw};
 for(unsigned chip=0;chip<2;chip++)for(unsigned shadow=0;shadow<2;shadow++)for(unsigned src=0;src<2;src++)for(unsigned ring=64;ring<73;ring++)for(unsigned valid=0;valid<2;valid++){
  ab.hw_rev=chip?17:3;hw.supports_shadow_regs=shadow;
  struct hal_srng s={.ring_id=ring,.ring_dir=src?0:1,.hwreg_base={0,valid?0x1b86400:0x1b86404}};
  s.u.src_ring.hp_addr=(u32 *)(uintptr_t)0x10000984;struct hal_srng old=s,new=s;
  select_old(&ab,&old);select_new(&ab,&new);
  bool selected=chip&&src&&ring==67&&valid;
  if(selected)assert((uintptr_t)new.u.src_ring.hp_addr==0x11b86400);
  else assert(!memcmp(&old,&new,sizeof(old)));
  assert(!memcmp(&s.hwreg_base,&new.hwreg_base,sizeof(s.hwreg_base)));
  cases++;
 }
 printf("PASS %u actual HAL pointer scenarios; only exact Peach CE3 source selects original direct branch\n",cases);
}
'''.replace('@BODIES@',bodies)
    src=out/'test.c';src.write_text(code)
    cmd=[str(a.cc),'-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(src),'-o',str(out/'test')]
    if sys.platform=='darwin':cmd[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for n,c in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(c,capture_output=True);(out/(n+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    proof=dict(passed=True,actual_hal_pointer_functions=True,mmio_not_executed=True,hardware_tested=False,
        summary=(out/'run.log').read_text().strip(),sanitizers=['ASan','UBSan'],hal_source_sha256=hashlib.sha256(raw).hexdigest(),hal_fixed_sha256=hashlib.sha256(fixed).hexdigest(),
        source_inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['tools/test_wifi_ce3_direct.py','drivers/EldenWifi/peach/Ce3DirectPointerPatch.py']})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
