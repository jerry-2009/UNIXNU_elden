"""Exercise actual OEM access helper with success, nesting and failure gates."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('cc', 'pci-source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / 'drivers/EldenWifi/peach'))
    from UmacRegisterPatch import patch
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'pci.c').write_bytes(patch(args.pci_source.read_bytes()))
    code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
typedef int spinlock_t;
#define ATH12K_HW_PEACH_HW20 17
#define WINDOW_START 0x80000u
#define WINDOW_RANGE_MASK 0x7ffffu
#define ACCESS_ALWAYS_OFF 0xfe0u
#define ATH12K_PCI_FLAG_INIT_DONE 0
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
struct mhi_device {int refs;};
struct mhi_controller {struct mhi_device *mhi_dev;};
struct ath12k_pci {struct mhi_controller *mhi_ctrl;unsigned long flags;};
struct ath12k_base {u32 hw_rev;char *mem;size_t mem_len;struct ath12k_pci *pci;};
static bool optin=true;static int get_error;static u32 scratch=2,wake;
static unsigned gets,puts,reads,writes,delays,logs;
static int elden_wifi_umac_hold_requested(void){return optin;}
static struct ath12k_pci *ath12k_pci_priv(struct ath12k_base *ab){return ab->pci;}
static int test_bit(unsigned bit,unsigned long *p){return (*p>>bit)&1;}
static void spin_lock_init(spinlock_t *p){*p=0;}
static void spin_lock_bh(spinlock_t *p){assert(!*p);*p=1;}
static void spin_unlock_bh(spinlock_t *p){assert(*p);*p=0;}
static int mhi_device_get_sync(struct mhi_device *p){assert(p&&!elden_umac_test_lock);gets++;if(get_error)return get_error;p->refs++;return 0;}
static void mhi_device_put(struct mhi_device *p){assert(p&&!elden_umac_test_lock&&p->refs>0);p->refs--;puts++;}
static u32 elden_pci_read32_raw(struct ath12k_base *ab,u32 off){assert(ab&&off==0x1e04040);reads++;return scratch;}
static void elden_pci_write32_raw(struct ath12k_base *ab,u32 off,u32 val){assert(ab&&off==0x3004&&val<=1);wake=val;writes++;}
static void udelay(unsigned us){assert(us==5000);delays++;}
static void ath12k_warn(struct ath12k_base *ab,const char *f,...){assert(ab&&f);logs++;}
@HELPER@
static void reset(struct ath12k_base *ab,struct mhi_device *dev){
 elden_umac_owner=NULL;elden_umac_device=NULL;elden_umac_access_enabled=false;
 elden_umac_access_refs=elden_umac_access_notes=0;elden_umac_access_fault=0;
 get_error=0;scratch=2;wake=0;gets=puts=reads=writes=delays=logs=0;dev->refs=0;
 optin=true;assert(!elden_umac_wake_get(ab));
}
int main(void){
 unsigned cases=0;struct mhi_device dev={0};struct mhi_controller m={&dev};
 struct ath12k_pci pci={&m,1};char mem;struct ath12k_base ab={17,&mem,0x90000,&pci};bool taken;
 reset(&ab,&dev);assert(!gets&&!puts&&!writes&&!dev.refs&&elden_umac_owner==&ab);cases++;
 for(unsigned n=0;n<16;n++){
  assert(!elden_umac_register_begin(&ab,0x1b86000,&taken)&&taken&&wake==1&&dev.refs==1);
  elden_umac_register_end(&ab,taken);assert(!wake&&!dev.refs&&gets==puts&&writes==2*(n+1));cases++;
 }
 unsigned before=reads;
 assert(!elden_umac_register_begin(&ab,0x1b86000,&taken)&&taken);
 bool second;assert(!elden_umac_register_begin(&ab,0x1b86010,&second)&&second);
 assert(dev.refs==2&&reads==before+1&&elden_umac_access_refs==2);cases++;
 elden_umac_register_end(&ab,taken);assert(wake==1&&dev.refs==1);cases++;
 elden_umac_register_end(&ab,second);assert(!wake&&!dev.refs);cases++;
 before=gets;assert(!elden_umac_register_begin(&ab,0xfdf,&taken)&&!taken&&gets==before);cases++;
 pci.flags=0;assert(!elden_umac_register_begin(&ab,0x1b86000,&taken)&&!taken&&gets==before);pci.flags=1;cases++;
 ab.hw_rev=2;assert(!elden_umac_register_begin(&ab,0x1b86000,&taken)&&!taken&&gets==before);ab.hw_rev=17;cases++;
 reset(&ab,&dev);get_error=-5;assert(elden_umac_register_begin(&ab,0x1b86000,&taken)==-5&&!taken&&!writes&&!puts&&!dev.refs);cases++;
 for(unsigned fault=0;fault<2;fault++){
  reset(&ab,&dev);scratch=fault?UINT32_MAX:0;
  assert(elden_umac_register_begin(&ab,0x1b86000,&taken)==(fault?-EIO:-ETIMEDOUT)&&!taken&&!dev.refs&&gets==puts&&!wake);
  assert(reads==(fault?1:11)&&delays==(fault?0:10));cases++;
  before=gets;assert(elden_umac_register_begin(&ab,0x1b86000,&taken)<0&&!taken&&gets==before);cases++;
  assert(elden_umac_owner==&ab&&elden_umac_device==&dev);elden_umac_wake_put(&ab);assert(!elden_umac_owner&&!dev.refs);cases++;
 }
 reset(&ab,&dev);assert(!elden_umac_register_begin(&ab,0x1b86000,&taken));
 elden_umac_wake_put(&ab);assert(elden_umac_owner==&ab&&dev.refs==1);cases++;
 elden_umac_register_end(&ab,taken);elden_umac_wake_put(&ab);assert(!elden_umac_owner&&!dev.refs&&!wake);cases++;
 reset(&ab,&dev);m.mhi_dev=NULL;assert(elden_umac_register_begin(&ab,0x1b86000,&taken)==-ENODEV&&!taken&&!gets);m.mhi_dev=&dev;cases++;
 reset(&ab,&dev);optin=false;elden_umac_wake_put(&ab);assert(!elden_umac_wake_get(&ab)&&!elden_umac_owner);cases++;
 printf("PASS %u actual UMAC register-access scenarios; MHI/MMIO and executor modeled, not hardware proof\n",cases);
}
'''
    # Forward the test lock assertion without redeclaring the production lock.
    code = code.replace('gets', 'get_count').replace('puts', 'put_count')
    code = code.replace('static int mhi_device_get_sync', 'static spinlock_t elden_umac_access_lock;\n#define elden_umac_test_lock elden_umac_access_lock\nstatic int mhi_device_get_sync')
    helper = (ROOT / 'drivers/EldenWifi/UmacRegisterAccess.inc').read_text()
    helper = helper.replace('static spinlock_t elden_umac_access_lock;\n', '')
    code = code.replace('@HELPER@', helper)
    source = out / 'test.c'
    source.write_text(code)
    cmd = [str(args.cc), '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', str(source), '-o', str(out / 'test')]
    if sys.platform == 'darwin':
        cmd[1:1] = ['-isysroot', subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'], text=True).strip()]
    for name,command in [('compile',cmd),('run',[str(out/'test')])]:
        result = subprocess.run(command,capture_output=True)
        (out/(name+'.log')).write_bytes(result.stdout+result.stderr)
        result.check_returncode()
    own=['tools/test_wifi_umac_register_access.py','drivers/EldenWifi/UmacRegisterAccess.inc','drivers/EldenWifi/peach/UmacRegisterPatch.py']
    proof=dict(passed=True,actual_helper=True,asan_ubsan=True,mhi_mmio_executor_modeled=True,
               hardware_tested=False,summary=(out/'run.log').read_text().strip(),
               source_inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in own})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
