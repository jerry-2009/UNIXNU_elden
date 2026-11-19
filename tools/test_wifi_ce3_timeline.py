"""Execute exact timeline helper and verify every insertion is reversible."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('cc','core-source','wmi-source','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
    from Ce3TimelinePatch import patch
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    for name,path in [('core.c',a.core_source),('wmi.c',a.wmi_source)]:(out/name).write_bytes(patch(name,path.read_bytes()))
    helper=(ROOT/'drivers/EldenWifi/Ce3Timeline.inc').read_text().replace('#include "Ce3Timeline.h"','')
    code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdarg.h>
typedef uint32_t u32;
#define ATH12K_HW_PEACH_HW20 17
#define HAL_SRNG_RING_ID_MAX 128
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
struct ath12k_ce_ring {unsigned hal_ring_id;};
struct hal_srng {unsigned initialized,entry_size,ring_size;u32 hwreg_base[2];struct {struct {u32 hp,*tp_addr;} src_ring;} u;};
struct params {unsigned ce_count;};
struct ath12k_base {unsigned hw_rev;void *mem;struct params *hw_params;struct {struct {struct ath12k_ce_ring *src_ring;} ce_pipe[4];} ce;struct {struct hal_srng srng_list[128];} hal;};
static unsigned reads,logs;static u32 misc=0x42;
static u32 ath12k_hif_read32(struct ath12k_base *ab,u32 off){(void)ab;reads++;return off==0x1b86010?misc:off;}
static void ath12k_warn(struct ath12k_base *ab,const char *fmt,...){(void)ab;char b[320];va_list ap;va_start(ap,fmt);int n=vsnprintf(b,sizeof b,fmt,ap);va_end(ap);assert(n>0&&(unsigned)n<sizeof b);logs++;}
@HELPER@
int main(void){
 unsigned cases=0;struct ath12k_ce_ring ring={67};struct params p={9};u32 tail=8;
 struct ath12k_base ab={0};ab.hw_rev=17;ab.mem=(void *)1;ab.hw_params=&p;ab.ce.ce_pipe[3].src_ring=&ring;
 struct hal_srng *s=&ab.hal.srng_list[67];s->initialized=1;s->entry_size=4;s->ring_size=128;s->hwreg_base[0]=0x1b86000;s->hwreg_base[1]=0x1b86400;s->u.src_ring.tp_addr=&tail;
 elden_ce3_timeline(NULL,1,0);assert(!reads);cases++;
 for(unsigned i=1;i<=12;i++){misc=i<6?0x42:0x80;elden_ce3_timeline(&ab,i,0);assert(reads==i*7&&logs==i);cases++;}
 elden_ce3_timeline(&ab,9,0);assert(reads==84&&logs==12);cases++;
 printf("PASS %u actual timeline cases; bounded12 events/7reads, register state modeled\n",cases);
}
'''.replace('@HELPER@',helper)
    src=out/'test.c';src.write_text(code)
    cmd=[str(a.cc),'-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(src),'-o',str(out/'test')]
    if sys.platform=='darwin':cmd[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for n,c in [('compile',cmd),('run',[str(out/'test')])]:
        x=subprocess.run(c,capture_output=True);(out/(n+'.log')).write_bytes(x.stdout+x.stderr);x.check_returncode()
    proof=dict(passed=True,actual_helper=True,insertion_reversible=True,mmio_modeled=True,hardware_tested=False,summary=(out/'run.log').read_text().strip(),
        source_inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['tools/test_wifi_ce3_timeline.py','drivers/EldenWifi/peach/Ce3TimelinePatch.py','drivers/EldenWifi/Ce3Timeline.inc','drivers/EldenWifi/Ce3Timeline.h']})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
