"""Exercise the actual optional lease helper with modeled MHI references."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    helper=ROOT/'drivers/EldenWifi/MhiLease.inc'
    code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stddef.h>
#include <errno.h>
struct mhi_device{unsigned refs;};struct mhi_controller{struct mhi_device *mhi_dev;};
struct ath12k_pci{struct mhi_controller *mhi_ctrl;};
struct ath12k_base{unsigned hw_rev;struct ath12k_pci *pci;};
#define ATH12K_HW_PEACH_HW20 17
static struct ath12k_pci *ath12k_pci_priv(struct ath12k_base *ab){return ab->pci;}
static unsigned requested=1,get_calls,put_calls;static int failure;
int elden_wifi_mhi_hold_requested(void){return requested;}
static int mhi_device_get_sync(struct mhi_device *d){get_calls++;if(failure)return failure;d->refs++;return 0;}
static void mhi_device_put(struct mhi_device *d){assert(d->refs);d->refs--;put_calls++;}
#define ath12k_warn(...) ((void)0)
@HELPER@
int main(){
 unsigned cases=0;struct mhi_device d={0},d2={0};struct mhi_controller ctrl={&d},ctrl2={&d2};
 struct ath12k_pci pci={&ctrl},pci2={&ctrl2};struct ath12k_base ab={17,&pci},other={17,&pci2};
 requested=0;assert(!elden_mhi_lease_get(NULL)&&!get_calls);cases++;
 requested=1;assert(elden_mhi_lease_get(NULL)==-ENODEV);cases++;
 ab.hw_rev=3;assert(elden_mhi_lease_get(&ab)==-ENODEV&&!get_calls);ab.hw_rev=17;cases++;
 pci.mhi_ctrl=NULL;assert(elden_mhi_lease_get(&ab)==-ENODEV);pci.mhi_ctrl=&ctrl;cases++;
 ctrl.mhi_dev=NULL;assert(elden_mhi_lease_get(&ab)==-ENODEV);ctrl.mhi_dev=&d;cases++;
 for(unsigned i=0;i<3;i++){failure=-(5+(int)i);assert(elden_mhi_lease_get(&ab)==failure&&!d.refs&&!elden_mhi_lease);elden_mhi_lease_put(&ab);assert(!put_calls);cases++;}
 failure=0;assert(!elden_mhi_lease_get(&ab)&&d.refs==1&&elden_mhi_lease==&d);cases++;
 unsigned before=get_calls;assert(!elden_mhi_lease_get(&ab)&&get_calls==before&&d.refs==1);cases++;
 assert(elden_mhi_lease_get(&other)==-EBUSY&&!d2.refs);cases++;
 elden_mhi_lease_put(&other);assert(!put_calls&&d.refs==1);cases++;
 elden_mhi_lease_put(&ab);assert(put_calls==1&&!d.refs&&!elden_mhi_lease);cases++;
 elden_mhi_lease_put(&ab);assert(put_calls==1);cases++;
 for(unsigned i=0;i<20;i++){assert(!elden_mhi_lease_get(&ab));elden_mhi_lease_put(&ab);assert(!d.refs);cases++;}
 printf("PASS %u actual MHI lease cases; refused gets own no put; exact release and stable scope\n",cases);
}
'''.replace('@HELPER@',helper.read_text())
    source=out/'test.c';source.write_text(code)
    command=[str(args.cc),'-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-fno-sanitize-recover=all',str(source),'-o',str(out/'test')]
    if sys.platform=='darwin':command[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for name,cmd in [('compile',command),('run',[str(out/'test')])]:
        result=subprocess.run(cmd,capture_output=True);(out/(name+'.log')).write_bytes(result.stdout+result.stderr);result.check_returncode()
    proof=dict(passed=True,actual_helper_executed=True,mhi_reference_model=True,
        summary=(out/'run.log').read_text().strip(),sanitizers=['ASan','UBSan'],hardware_tested=False,
        source_inputs={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ['tools/test_wifi_mhi_lease.py','drivers/EldenWifi/MhiLease.inc','drivers/EldenWifi/peach/MhiLeasePatch.py']})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
