"""Execute command-scoped OEM wake helpers and original send wrapper."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('cc','pci-source','wmi-source','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
    from UmacCommandLeasePatch import patch
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    for name,path in [('pci.c',a.pci_source),('wmi.c',a.wmi_source)]:(out/name).write_bytes(patch(name,path.read_bytes()))
    s=(out/'wmi.c').read_text();at=s.index('int ath12k_wmi_cmd_send(');wrapper=s[at:s.index('\n}\n',at)+3]
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
struct ath12k_base {unsigned hw_rev;void *mem;size_t mem_len;struct ath12k_pci *pci;unsigned dev_flags;};
static struct ath12k_base *elden_umac_owner;static struct mhi_device *elden_umac_device;
static unsigned get_calls,put_calls,writes,delays,ready_at,status_reads,send_calls,inspect_calls;static int failure,send_result;static u32 request,status=2;
static struct ath12k_pci *ath12k_pci_priv(struct ath12k_base *ab){return ab->pci;}
static int mhi_device_get_sync(struct mhi_device *d){get_calls++;if(failure)return failure;d->refs++;return 0;}
static void mhi_device_put(struct mhi_device *d){assert(d->refs>1);d->refs--;put_calls++;}
static u32 ath12k_pci_read32(struct ath12k_base *ab,u32 off){assert(ab);if(off==0x3004)return request;assert(off==0x1e04040);return writes&&status_reads++>=ready_at?status:0;}
static void ath12k_pci_write32(struct ath12k_base *ab,u32 off,u32 v){assert(ab&&off==0x3004&&v<=1);request=v;writes++;}
static void udelay(unsigned n){assert(n==5000);delays++;}
static void ath12k_warn(struct ath12k_base *,const char *,...){}
@HELPER@
struct sk_buff {unsigned n;};struct ath12k_wmi_base {struct ath12k_base *ab;unsigned tx_credits_wq;};struct ath12k_wmi_pdev {struct ath12k_wmi_base *wmi_ab;};
#define ATH12K_FLAG_CRASH_FLUSH 0
#define WMI_SEND_TIMEOUT_HZ 3
#define might_sleep() ((void)0)
#define test_bit(n,p) ((*(p)&(1u<<(n)))!=0)
#define wait_event_timeout_once(queue,condition,timeout) do { unsigned rounds=0;(void)(queue);while(!(condition)&&++rounds<(timeout)){} }while(0)
static int ath12k_wmi_cmd_send_nowait(struct ath12k_wmi_pdev *w,struct sk_buff *,u32){assert(elden_umac_device->refs==2&&w->wmi_ab->ab==elden_umac_owner);send_calls++;return send_result;}
static void elden_ce3_inspect(struct ath12k_base *,u32){inspect_calls++;}
@WRAPPER@
static void clear(){get_calls=put_calls=writes=delays=status_reads=send_calls=inspect_calls=0;request=0;ready_at=0;failure=0;status=2;send_result=0;}
int main(){
 unsigned cases=0;struct mhi_device d={1};struct mhi_controller m={&d};struct ath12k_pci pci={&m};struct ath12k_base ab={17,(void *)1,0x100000,&pci,0};elden_umac_owner=&ab;elden_umac_device=&d;
 struct ath12k_wmi_base base={&ab,0};struct ath12k_wmi_pdev w={&base};struct sk_buff skb={0};
 for(unsigned i=0;i<11;i++){clear();ready_at=i;assert(!ath12k_wmi_cmd_send(&w,&skb,0x4003)&&d.refs==1&&get_calls==1&&put_calls==1&&send_calls==1&&writes==1&&delays==i);cases++;}
 clear();failure=-EIO;assert(ath12k_wmi_cmd_send(&w,&skb,0x4003)==-EIO&&d.refs==1&&!send_calls&&!writes&&!put_calls);cases++;
 for(unsigned i=0;i<4;i++){if(i==2)continue;clear();status=i;assert(ath12k_wmi_cmd_send(&w,&skb,0x4003)==-ETIMEDOUT&&d.refs==1&&!send_calls&&put_calls==1&&writes==2&&delays==10);cases++;}
 clear();send_result=-EAGAIN;assert(ath12k_wmi_cmd_send(&w,&skb,0x3001)==-EAGAIN&&d.refs==1&&send_calls==3&&put_calls==1&&inspect_calls==1);cases++;
 clear();send_result=-EIO;assert(ath12k_wmi_cmd_send(&w,&skb,0x5001)==-EIO&&d.refs==1&&send_calls==1&&put_calls==1&&!inspect_calls);cases++;
 clear();send_result=-EAGAIN;ab.dev_flags=1;assert(ath12k_wmi_cmd_send(&w,&skb,0x4003)==-ESHUTDOWN&&d.refs==1&&put_calls==1&&!inspect_calls);ab.dev_flags=0;cases++;
 for(unsigned i=0;i<64;i++){clear();assert(!ath12k_wmi_cmd_send(&w,&skb,0x4003)&&d.refs==1&&put_calls==1);cases++;}
 printf("PASS %u actual command-lease/wrapper cases; extra ref spans original send, real error propagation, no ring writes\n",cases);
}
'''.replace('@HELPER@',(ROOT/'drivers/EldenWifi/UmacCommandLease.inc').read_text()).replace('@WRAPPER@',wrapper)
    src=out/'test.cpp';src.write_text(code);cmd=[str(a.cc),'-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(src),'-o',str(out/'test')]
    if sys.platform=='darwin':cmd[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for name,command in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(command,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    own=['tools/test_wifi_umac_command_lease.py','tools/build_wifi_umac_access.py','drivers/EldenWifi/UmacCommandLease.inc','drivers/EldenWifi/peach/UmacCommandLeasePatch.py']
    proof=dict(passed=True,actual_helper_wrapper=True,asan_ubsan=True,mmio_mhi_modeled=True,hardware_tested=False,summary=(out/'run.log').read_text().strip(),source_inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in own})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
