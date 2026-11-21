"""Exercise the actual bounded observer and reversible PCI insertion."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('cc','pci-source','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
    from PciStateTracePatch import patch
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'pci.c').write_bytes(patch(a.pci_source.read_bytes()))
    helper=(ROOT/'drivers/EldenWifi/PciStateTrace.inc').read_text()
    code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
#define ATH12K_HW_PEACH_HW20 17
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
struct mhi_device {u32 dev_wake;};
struct mhi_controller {void *regs;size_t reg_len;void *wake_db;u32 pm_state,dev_state,ee;int dev_wake;struct mhi_device *mhi_dev;};
struct ath12k_pci {struct mhi_controller *mhi_ctrl;};
struct ath12k_base {u32 hw_rev;char *mem;size_t mem_len;struct ath12k_pci *pci;};
static void (*lx_mmio_trace)(volatile void *,u32);
static struct ath12k_base *elden_umac_owner;
static struct mhi_device *elden_umac_device;
static unsigned writes,reads,logs,other_calls;static char last[320];
static struct ath12k_pci *ath12k_pci_priv(struct ath12k_base *ab){return ab->pci;}
static int atomic_read(int *p){return __atomic_load_n(p,__ATOMIC_ACQUIRE);}
static u32 ioread32(const volatile void *p){reads++;return *(const volatile u32 *)p;}
static void write32(volatile void *p,u32 v){if(lx_mmio_trace)lx_mmio_trace(p,v);*(volatile u32 *)p=v;writes++;}
static void ath12k_warn(struct ath12k_base *ab,const char *format,...){(void)ab;va_list a;va_start(a,format);int n=vsnprintf(last,sizeof last,format,a);va_end(a);assert(n>0&&(unsigned)n<sizeof last);logs++;}
static void other(volatile void *p,u32 v){(void)p;(void)v;other_calls++;}
@HELPER@
int main(void){
 unsigned cases=0;char *mem=calloc(1,0x90000);assert(mem);struct mhi_device dev={1};
 struct mhi_controller m={mem,0x90000,mem+0x1ff8,1,2,2,1,&dev};struct ath12k_pci pci={&m};
 struct ath12k_base ab={17,mem,0x90000,&pci};elden_umac_owner=&ab;elden_umac_device=&dev;
 *(u32 *)(mem+0x3278)=0x40000037;*(u32 *)(mem+0x38)=0x200;*(u32 *)(mem+0x48)=0x201;
 elden_pci_state_install(NULL);assert(!lx_mmio_trace);cases++;
 ab.hw_rev=1;elden_pci_state_install(&ab);assert(!lx_mmio_trace);ab.hw_rev=17;cases++;
 elden_umac_device=NULL;elden_pci_state_install(&ab);assert(!lx_mmio_trace);elden_umac_device=&dev;cases++;
 lx_mmio_trace=other;elden_pci_state_install(&ab);assert(lx_mmio_trace==other&&!elden_pci_state.owner);cases++;
 write32(mem+0x3004,1);assert(other_calls==1&&*(u32 *)(mem+0x3004)==1);cases++;
 lx_mmio_trace=NULL;elden_pci_state_install(&ab);assert(lx_mmio_trace==elden_pci_state_mmio&&elden_pci_state.installed);cases++;
 elden_pci_state_install(&ab);assert(lx_mmio_trace==elden_pci_state_mmio);cases++;
 for(unsigned i=0;i<36;i++)write32(mem+0x3004,i&1);assert(elden_pci_state.count==36&&elden_pci_state.overflow==4&&writes==37);cases++;
 write32(mem+0x100,123);assert(elden_pci_state.count==36&&*(u32 *)(mem+0x100)==123);cases++;
 write32(mem+0x86000,42);assert(elden_pci_state.count==37);cases++;
 *(u32 *)(mem+0x3278)=0x40000000;write32(mem+0x86000,43);assert(elden_pci_state.count==37);cases++;
 *(u32 *)(mem+0x3278)=0x40000037;write32(mem+0x3008,1);assert(elden_pci_state.count==38);cases++;
 unsigned before=reads;elden_pci_state_read(&ab,0x100,0);assert(reads==before);cases++;
 for(unsigned i=0;i<17;i++)elden_pci_state_read(&ab,0x3004,1);assert(elden_pci_state.states==16&&reads==before+32);cases++;
 elden_pci_state.states=0;elden_pci_state_read(&ab,0x3004,0);assert(elden_pci_state.dumped);cases++;
 elden_pci_state_remove(&ab);assert(!lx_mmio_trace&&!elden_pci_state.owner);cases++;
 memset(&elden_pci_state,0,sizeof elden_pci_state);elden_pci_state_install(&ab);lx_mmio_trace=other;
 elden_pci_state_remove(&ab);assert(lx_mmio_trace==other&&elden_pci_state.owner==&ab);cases++;
 lx_mmio_trace=NULL;free(mem);printf("PASS %u actual observer cases; original writes preserved, bounded RAM and modeled MHI/MMIO\n",cases);
}
'''.replace('@HELPER@',helper)
    source=out/'test.c';source.write_text(code)
    cmd=[str(a.cc),'-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(source),'-o',str(out/'test')]
    if sys.platform=='darwin':cmd[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for name,command in [('compile',cmd),('run',[str(out/'test')])]:
        result=subprocess.run(command,capture_output=True);(out/(name+'.log')).write_bytes(result.stdout+result.stderr);result.check_returncode()
    own=['tools/test_wifi_pci_state_trace.py','drivers/EldenWifi/peach/PciStateTracePatch.py','drivers/EldenWifi/PciStateTrace.inc']
    report=dict(passed=True,actual_helper=True,insertion_reversible=True,original_mmio_writes_preserved=True,
        hook_restore_ownership_checked=True,mmio_mhi_modeled=True,hardware_tested=False,summary=(out/'run.log').read_text().strip(),
        source_inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in own})
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
