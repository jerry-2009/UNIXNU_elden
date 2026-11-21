"""Run the actual one-access OEM recipe with reference/error fixtures."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('cc','pci-source','wmi-source','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
    from UmacAccessPatch import patch
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    for name,path in [('pci.c',a.pci_source),('wmi.c',a.wmi_source)]:(out/name).write_bytes(patch(name,path.read_bytes()))
    code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdarg.h>
#include <errno.h>
typedef uint32_t u32;
#define ATH12K_HW_PEACH_HW20 17
#define ELDEN_UMAC_WAKE_OFFSET 0x3004U
#define ELDEN_UMAC_SCRATCH_OFFSET 0x1e04040U
#define ELDEN_UMAC_AWAKE 2U
#define ELDEN_UMAC_CHECKS 11U
#define ELDEN_UMAC_DELAY_US 5000U
struct mhi_device {unsigned refs;};
struct mhi_controller {struct mhi_device *mhi_dev;};
struct ath12k_pci {struct mhi_controller *mhi_ctrl;};
struct ath12k_base {unsigned hw_rev;void *mem;size_t mem_len;struct ath12k_pci *pci;};
static struct ath12k_base *elden_umac_owner;static struct mhi_device *elden_umac_device;
static unsigned get_calls,put_calls,writes,delays,selected=1,ready_at,status_reads;static int failure;static u32 request,status=2;
static int elden_wifi_umac_hold_requested(){return selected;}
static struct ath12k_pci *ath12k_pci_priv(struct ath12k_base *ab){return ab->pci;}
static int mhi_device_get_sync(struct mhi_device *d){get_calls++;if(failure)return failure;d->refs++;return 0;}
static void mhi_device_put(struct mhi_device *d){assert(d->refs>1);d->refs--;put_calls++;}
static u32 ath12k_pci_read32(struct ath12k_base *ab,u32 off){assert(ab);if(off==0x3004)return request;assert(off==0x1e04040);return writes&&status_reads++>=ready_at?status:0;}
static void ath12k_pci_write32(struct ath12k_base *ab,u32 off,u32 v){assert(ab&&off==0x3004&&v<=1);request=v;writes++;}
static void udelay(unsigned n){assert(n==5000);delays++;}
static void ath12k_warn(struct ath12k_base *,const char *,...){}
@HELPER@
static void clear(){elden_umac_access_seen=0;get_calls=put_calls=writes=delays=status_reads=0;request=0;ready_at=0;failure=0;status=2;}
int main(){
 unsigned cases=0;struct mhi_device d={1};struct mhi_controller m={&d};struct ath12k_pci pci={&m};struct ath12k_base ab={17,(void *)1,0x100000,&pci};elden_umac_owner=&ab;elden_umac_device=&d;
 clear();assert(!elden_wifi_umac_access_first(NULL)&&!writes);cases++;
 clear();selected=0;assert(!elden_wifi_umac_access_first(&ab)&&!writes);selected=1;cases++;
 clear();elden_umac_device=NULL;assert(elden_wifi_umac_access_first(&ab)==-ENODEV&&!writes);elden_umac_device=&d;cases++;
 for(unsigned i=0;i<11;i++){clear();ready_at=i;assert(!elden_wifi_umac_access_first(&ab)&&d.refs==1&&get_calls==1&&put_calls==1&&writes==1&&delays==i);assert(!elden_wifi_umac_access_first(&ab)&&writes==1);cases++;}
 clear();failure=-EIO;assert(elden_wifi_umac_access_first(&ab)==-EIO&&d.refs==1&&!writes&&!put_calls);cases++;
 for(unsigned i=0;i<4;i++){if(i==2)continue;clear();status=i;assert(elden_wifi_umac_access_first(&ab)==-ETIMEDOUT&&d.refs==1&&get_calls==1&&put_calls==1&&writes==2&&delays==10&&request==0);cases++;}
 clear();status=0xffffffff;assert(elden_wifi_umac_access_first(&ab)==-EIO&&d.refs==1&&writes==2&&!delays);cases++;
 clear();request=1;status=1;assert(elden_wifi_umac_access_first(&ab)==-ETIMEDOUT&&d.refs==1&&request==1);cases++;
 printf("PASS %u actual first-access cases; MHI/MMIO modeled, balanced extra ref, real errors and zero ring writes\n",cases);
}
'''.replace('@HELPER@',(ROOT/'drivers/EldenWifi/UmacAccess.inc').read_text())
    src=out/'test.cpp';src.write_text(code);cmd=[str(a.cc),'-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(src),'-o',str(out/'test')]
    if sys.platform=='darwin':cmd[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for name,command in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(command,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    own=['tools/test_wifi_umac_access.py','tools/build_wifi_umac_access.py','drivers/EldenWifi/UmacAccess.inc','drivers/EldenWifi/peach/UmacAccessPatch.py']
    proof=dict(passed=True,actual_helper=True,asan_ubsan=True,mmio_mhi_modeled=True,hardware_tested=False,summary=(out/'run.log').read_text().strip(),source_inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in own})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
