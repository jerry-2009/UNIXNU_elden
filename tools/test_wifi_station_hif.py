"""Exercise the actual HIF helper's owner/failed-get/release behavior on host."""
import argparse,subprocess,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/portable/station'))
from PortableHifPatch import PCI,RELEASE
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <stdbool.h>
#include <string.h>
#define ATH12K_HW_PEACH_HW20 17
#define ATH12K_PCI_FLAG_INIT_DONE 0
#define MHI_EE_AMSS 2
struct mhi_device{int refs;};
struct mhi{void *regs;unsigned ee;struct mhi_device *mhi_dev;};
struct ath12k_pci{struct mhi *mhi_ctrl;unsigned long flags;};
struct ath12k_base{unsigned hw_rev;void *mem;unsigned mem_len;struct ath12k_pci pci;};
static unsigned bound,get,put;static int bind_error,get_error;
static int elden_wifi_station_requested(void){return 1;}
static struct ath12k_pci *ath12k_pci_priv(struct ath12k_base *ab){return &ab->pci;}
static int test_bit(int bit,unsigned long *p){return !!(*p&(1ul<<bit));}
static void set_bit(int bit,unsigned long *p){*p|=1ul<<bit;}
static int elden_umac_wake_get(struct ath12k_base *ab){assert(ab);bound++;return bind_error;}
static int mhi_device_get_sync(struct mhi_device *dev){assert(dev);get++;if(!get_error)dev->refs++;return get_error;}
static void mhi_device_put(struct mhi_device *dev){assert(dev&&dev->refs>0);put++;dev->refs--;}
static void ath12k_warn(struct ath12k_base *ab,const char *text,...){assert(ab&&text);}
@PCI@
static void release(struct ath12k_base *ab){@RELEASE@}
static void reset(){elden_portable_hif_owner=NULL;elden_portable_hif_wake=NULL;bound=get=put=0;bind_error=get_error=0;}
int main(){
 unsigned count=0;struct mhi_device dev={0};struct mhi m={&dev,2,&dev};struct ath12k_base ab={17,&dev,0x100000,{&m,0}},other=ab;
 reset();assert(elden_wifi_portable_hif_prepare(NULL)==-ENODEV);count++;
 reset();ab.hw_rev=1;assert(elden_wifi_portable_hif_prepare(&ab)==-ENODEV&&!get);ab.hw_rev=17;count++;
 reset();m.ee=0;assert(elden_wifi_portable_hif_prepare(&ab)==-EBUSY&&!get);m.ee=2;count++;
 reset();ab.pci.flags=1;assert(elden_wifi_portable_hif_prepare(&ab)==-EBUSY&&!get);ab.pci.flags=0;count++;
 reset();bind_error=-19;assert(elden_wifi_portable_hif_prepare(&ab)==-19&&get==0&&put==0);release(&ab);assert(put==0);ab.pci.flags=0;count++;
 reset();get_error=-110;assert(elden_wifi_portable_hif_prepare(&ab)==-110&&get==1&&put==0);release(&ab);assert(put==0);ab.pci.flags=0;count++;
 reset();assert(elden_wifi_portable_hif_prepare(&ab)==0&&dev.refs==1&&ab.pci.flags==1&&bound==1);count++;
 assert(elden_wifi_portable_hif_prepare(&ab)==-EBUSY&&get==1);count++;
 release(&other);assert(put==0&&dev.refs==1);count++;
 release(&ab);assert(put==1&&dev.refs==0);count++;
 release(&ab);assert(put==1);count++;
 printf("actual HIF helper: %u scenarios passed; MHI and PCI memory are modeled\n",count);return 0;
}
'''
    code=code.replace('@PCI@',PCI.replace('extern int elden_wifi_station_requested(void);','')).replace('@RELEASE@',RELEASE)
    sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
    file=out/'hif.c';file.write_text(code);binary=out/'hif';cmd=[str(a.cc),'-isysroot',sdk,'-std=c11','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(file),'-o',str(binary)]
    r=subprocess.run(cmd,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run([str(binary)],capture_output=True);(out/'run.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    print(r.stdout.decode().strip());(out/'result.json').write_text(json.dumps(dict(passed=True,scenarios=11,actual_helper=True,asan_ubsan=True,hardware_modeled=True))+'\n')
if __name__=='__main__':main()
