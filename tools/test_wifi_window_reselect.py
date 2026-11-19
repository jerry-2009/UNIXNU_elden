"""Run exact old/new selector with hardware-window reset and original lock."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('cc','pci-source','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
    from WindowReselectPatch import patch,function
    data=a.pci_source.read_bytes();fixed=patch(data)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);(out/'pci.c').write_bytes(fixed)
    bodies=function(data.decode()).replace('ath12k_pci_select_window(','select_old(',1)+'\n'+function(fixed.decode()).replace('ath12k_pci_select_window(','select_new(',1)
    code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
#define ATH12K_HW_PEACH_HW20 17
#define WINDOW_VALUE_MASK 0x01f80000U
#define WINDOW_STATIC_MASK 0x00ffffc0U
#define WINDOW_ENABLE_BIT 0x40000000U
struct ath12k_base {unsigned hw_rev;unsigned char *mem;};
struct ath12k_pci {struct ath12k_base *ab;u32 register_window,window_reg_addr;int window_lock;};
static unsigned writes,reads;
#define lockdep_assert_held(p) assert(*(p)==1)
static u32 u32_get_bits(u32 x,u32 mask){return (x&mask)>>19;}
static void iowrite32(u32 val,void *p){*(u32 *)p=val;writes++;}
static u32 ioread32(void *p){reads++;return *(u32 *)p;}
@BODIES@
int main(void){
 unsigned cases=0;u32 hw;
 struct ath12k_base ab={17,(unsigned char *)&hw-0x3278};
 struct ath12k_pci pci={&ab,0x37,0x3278,1};
 hw=WINDOW_ENABLE_BIT;select_old(&pci,0x1b86400);assert(!writes&&hw==WINDOW_ENABLE_BIT);cases++;
 select_new(&pci,0x1b86400);assert(writes==1&&reads==1&&hw==(WINDOW_ENABLE_BIT|0x37));cases++;
 for(unsigned chip=0;chip<2;chip++)for(unsigned cached=0;cached<64;cached++)for(unsigned wanted=0;wanted<64;wanted++){
  ab.hw_rev=chip?17:3;pci.register_window=cached;hw=WINDOW_ENABLE_BIT;writes=reads=0;
  select_new(&pci,wanted<<19);unsigned expected=chip||wanted!=cached;
  assert(writes==expected&&reads==expected);if(expected)assert(hw==(WINDOW_ENABLE_BIT|wanted));cases++;
 }
 ab.hw_rev=3;pci.register_window=0x123400;hw=0;writes=reads=0;select_new(&pci,0x1b86400);
 assert(hw==(WINDOW_ENABLE_BIT|0x123437));cases++;
 printf("PASS %u actual window selector cases; old stale-cache failure reproduced; exact lock/value/readback retained\n",cases);
}
'''.replace('@BODIES@',bodies)
    src=out/'test.c';src.write_text(code)
    cmd=[str(a.cc),'-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(src),'-o',str(out/'test')]
    if sys.platform=='darwin':cmd[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for n,c in [('compile',cmd),('run',[str(out/'test')])]:
        x=subprocess.run(c,capture_output=True);(out/(n+'.log')).write_bytes(x.stdout+x.stderr);x.check_returncode()
    proof=dict(passed=True,actual_selector_functions=True,stale_cache_failure_reproduced=True,mmio_modeled=True,hardware_tested=False,summary=(out/'run.log').read_text().strip(),
        pci_parent_sha256=hashlib.sha256(data).hexdigest(),pci_fixed_sha256=hashlib.sha256(fixed).hexdigest(),
        source_inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['tools/test_wifi_window_reselect.py','drivers/EldenWifi/peach/WindowReselectPatch.py']})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
