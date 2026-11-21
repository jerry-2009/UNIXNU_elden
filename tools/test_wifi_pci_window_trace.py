"""Exercise original/patched PCI read functions and diagnostic metadata on the host."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from PciWindowTracePatch import patch

def function(text,name):
    match=re.search(r'(?m)^(?:static inline |static )?u32 '+re.escape(name)+r'\(',text)
    if not match and name=='ath12k_pci_is_offset_within_mhi_region':match=re.search(r'(?m)^static inline bool '+re.escape(name)+r'\(',text)
    if not match:raise ValueError('Missing function definition: '+name)
    start=match.start();brace=text.index('{',start);depth=0
    for end in range(brace,len(text)):
        depth+=(text[end]=='{')-(text[end]=='}')
        if depth==0:return text[start:end+1]
    raise ValueError('Unclosed function')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--credit-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    original=(a.credit_build/'pci.c').read_bytes();changed=patch(original);(out/'pci.c').write_bytes(changed)
    try:patch(original+b'\n')
    except ValueError:pass
    else:raise AssertionError('Unpinned PCI input accepted')
    old=function(original.decode(),'ath12k_pci_read32').replace('ath12k_pci_read32','old_read')
    new=function(changed.decode(),'ath12k_pci_read32')
    code=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <initializer_list>
using u32=uint32_t;
#define WINDOW_START 0x80000u
#define WINDOW_RANGE_MASK 0x7ffffu
#define PCI_MHIREGLEN_REG 0x1e00000u
#define PCI_MHI_REGION_END 0x1e08000u
#define ACCESS_ALWAYS_OFF 0xfe0u
#define ATH12K_PCI_FLAG_INIT_DONE 0
struct ath12k_base;
struct region {u32 ce_reg_base,umac_base;};
struct ops {int (*wakeup)(ath12k_base *);void (*release)(ath12k_base *);};
struct ath12k_pci {ath12k_base *ab;unsigned flags;u32 register_window,window_reg_addr;region *reg_base;ops *pci_ops;int window_lock;};
struct ath12k_base {unsigned char *mem;bool static_window_map;ath12k_pci *pci;};
static unsigned reads,locks,unlocks,wakes,releases,selections,logs,longest;static int wake_rc;
static u32 addresses[8],last_request,last_effective;static char last[1024];static unsigned char memory[0x200000];
static ath12k_pci *ath12k_pci_priv(ath12k_base *a){return a->pci;}
static bool test_bit(unsigned, unsigned *v){return *v!=0;}
static void spin_lock_bh(int *){locks++;}static void spin_unlock_bh(int *){unlocks++;}
static u32 ioread32(unsigned char *p){u32 off=(u32)(p-memory);assert(off<sizeof(memory)&&reads<8);addresses[reads++]=off;return off==0x310c?0x40001dc0:off^0xa5a5;}
static int wake(ath12k_base *){wakes++;return wake_rc;}static void release(ath12k_base *){releases++;}
static void ath12k_pci_select_window(ath12k_pci *p,u32 off){selections++;p->register_window=off>>19;}
static void ath12k_warn(ath12k_base *,const char *fmt,...){va_list a;va_start(a,fmt);int n=vsnprintf(last,sizeof(last),fmt,a);va_end(a);assert(n>0&&n<320);logs++;if((unsigned)n>longest)longest=n;}
static u32 ath12k_hif_read32(ath12k_base *,u32);
'''
    helper=function(original.decode(),'ath12k_pci_get_window_start').replace('static u32','static u32',1)
    mhi=function(original.decode(),'ath12k_pci_is_offset_within_mhi_region')
    tail=r'''
static u32 ath12k_hif_read32(ath12k_base *a,u32 off){return ath12k_pci_read32(a,off);}
static void reset(){reads=locks=unlocks=wakes=releases=selections=logs=0;epw_busy=0;}
int main(){region r={0x1b80000,0x1c00000};ops o={wake,release};ath12k_pci p={};ath12k_base a={memory,true,&p};p.ab=&a;p.flags=1;p.reg_base=&r;p.pci_ops=&o;p.window_reg_addr=0x310c;
 unsigned scenarios=0;u32 requests[]={0x38,0x984,0x1b86400,0x1b86404,0x1c01234,0x123456,PCI_MHIREGLEN_REG+0x38};
 for(bool is_static:{false,true})for(int rc:{0,-5})for(u32 request:requests){
  a.static_window_map=is_static;wake_rc=rc;reset();u32 expected=old_read(&a,request),off=addresses[0];unsigned old_reads=reads,old_locks=locks,old_wakes=wakes,old_release=releases,old_selections=selections;
  reset();u32 plain=ath12k_pci_read32(&a,request);assert(plain==expected&&reads==old_reads&&locks==old_locks&&wakes==old_wakes&&releases==old_release&&selections==old_selections&&!logs);
  reset();u32 traced=elden_wifi_pci_diag_read(&a,request);assert(traced==expected&&reads==old_reads+1&&addresses[0]==off&&addresses[reads-1]==0x310c&&locks==old_locks&&wakes==old_wakes&&releases==old_release&&selections==old_selections&&logs==1&&!epw_busy);
  char token[80];snprintf(token,sizeof(token),"off=%x",off);assert(strstr(last,token));snprintf(token,sizeof(token),"wake=%d",rc&&request>=ACCESS_ALWAYS_OFF?rc:0);assert(strstr(last,token));scenarios++;
 }
 a.static_window_map=true;wake_rc=0;reset();elden_wifi_pci_diag_read(&a,0x1b86400);assert(addresses[0]==0x106400);scenarios++;
 p.window_reg_addr=0x80000;reset();elden_wifi_pci_diag_read(&a,0x1b86400);assert(reads==1&&logs==1&&strstr(last,"read=0"));scenarios++;
 printf("PASS %u actual original/patched PCI read scenarios, offsets/wake/window/counters; max line=%u\n",scenarios,longest);
}
'''
    (out/'test.cpp').write_text(code+helper+'\n'+mhi+'\n'+old+'\n#include "PciWindowTrace.inc"\n'+new+'\n'+tail)
    cmd=['clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-variable','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'drivers/EldenWifi'),str(out/'test.cpp'),'-o',str(out/'test')]
    for name,cmd in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(cmd,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    r={'passed':True,'actual_read_functions':True,'old_return_and_access_order_preserved':True,'reversible_source':True,'hardware_and_window_configuration_modeled':True,'observer_sha256':hashlib.sha256((ROOT/'drivers/EldenWifi/PciWindowTrace.inc').read_bytes()).hexdigest(),'summary':(out/'run.log').read_text().strip(),'hardware_tested':False};(out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(r['summary'])
if __name__=='__main__':main()
