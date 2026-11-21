"""Exercise the real fixed-response parser and bounded CE3 config reader."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from ModeResponsePatch import patch
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--parent-runtime',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    original=(args.parent_runtime/'wmi.c').read_bytes();derived=patch(original);(out/'wmi.c').write_bytes(derived)
    try:patch(original+b'\n')
    except ValueError:pass
    else:raise AssertionError('Unpinned response source accepted')
    (out/'wifi7').mkdir();(out/'hif.h').write_text('')
    (out/'wifi7/hal.h').write_text('')
    code=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
using u32=uint32_t;using u64=uint64_t;
#define EcfWmiRequest 1
#define HAL_SRNG_RING_ID_MAX 128
#define HAL_SRNG_REG_GRP_R0 0
#define HAL_SRNG_DIR_SRC 0
#define HAL_ADDR_MSB_REG_SHIFT 32
#define HAL_TCL1_RING_BASE_MSB_RING_BASE_ADDR_MSB 255
#define HAL_TCL1_RING_BASE_MSB_RING_SIZE 0x00ffff00
#define HAL_REO1_RING_ID_ENTRY_SIZE 255
#define HAL_TCL1_RING_MISC_SRNG_ENABLE 64
#define WMI_PDEV_SET_HW_MODE_RESP_EVENTID 0x4010
#define WMI_TAG_PDEV_SET_HW_MODE_RESPONSE_EVENT 0x321
#define EMR_HOST_TEST 1
static unsigned bad_offset;
#define HAL_TCL1_RING_BASE_MSB_OFFSET(hal) ((void)(hal),4)
#define HAL_TCL1_RING_ID_OFFSET(hal) ((void)(hal),8)
#define HAL_TCL1_RING_MISC_OFFSET(hal) ((void)(hal),bad_offset?0x104u:16u)
#define HAL_TCL1_RING_TP_ADDR_LSB_OFFSET(hal) ((void)(hal),28)
#define HAL_TCL1_RING_TP_ADDR_MSB_OFFSET(hal) ((void)(hal),32)
static u32 u32_encode_bits(u32 v,u32 mask){unsigned shift=0;while(!(mask&(1u<<shift)))shift++;return (v<<shift)&mask;}
struct wmi_cmd_hdr {u32 id;};struct sk_buff {unsigned char *data;u32 len;};
struct hw {u32 ce_count;};struct ce_ring {u32 hal_ring_id;};
struct hal_srng {bool initialized;u32 ring_dir,hwreg_base[2],entry_size,num_entries;u64 ring_base_paddr;
 struct {struct {u32 *hp_addr,*tp_addr;} src_ring;} u;};
struct ath12k_hal {hal_srng srng_list[128];struct {u64 paddr;void *vaddr;} rdp;};
struct ath12k_base {void *mem;hw *hw_params;struct {struct {ce_ring *src_ring;} ce_pipe[4];} ce;ath12k_hal hal;};
static unsigned reads,notes,par_reads;static u32 offsets[6];static u64 captured[5];
static u32 ath12k_hif_read32(ath12k_base *,u32 off){assert(reads<6);offsets[reads++]=off;return 0;}
static u64 emr_host_par(uintptr_t){par_reads++;return 0x40400000;}
static void elden_wifi_ce3_flow_note(ath12k_base *,unsigned,u64 a,u64 b,u64 c,u64 d,u64 e){notes++;captured[0]=a;captured[1]=b;captured[2]=c;captured[3]=d;captured[4]=e;}
#include "ModeResponseTrace.inc"
static void word(unsigned char *p,u32 v){for(unsigned i=0;i<4;i++)p[i]=(v>>(8*i))&255;}
int main(){
 unsigned cases=0;unsigned char raw[25]={};unsigned char *payload=raw+1;EldenWifiModeResponse r;
 word(payload,(0x321u<<16)|16);word(payload+4,0);word(payload+12,1);word(payload+16,0);
 for(unsigned status=0;status<7;status++){word(payload+8,status);assert(!emr_parse(payload,20,0x321,&r));assert(r.status==status&&r.configured_mode==1);cases++;}
 for(unsigned len=0;len<20;len++){assert(emr_parse(payload,len,0x321,&r)==-71&&r.reason==1);cases++;}
 word(payload+8,1);word(payload+12,UINT32_MAX);assert(!emr_parse(payload,20,0x321,&r));cases++;
 word(payload+8,0);assert(emr_parse(payload,20,0x321,&r)==-71);word(payload+12,1);cases++;
 assert(emr_parse(payload,20,0x322,&r)==-71&&r.reason==2);cases++;
 assert(emr_parse(nullptr,20,0x321,&r)==-71&&emr_parse(payload,20,0x321,nullptr)==-22);cases++;
 ath12k_base ab={};hw params={4};ce_ring cr={67};alignas(4) unsigned char memory[4096]={};u32 rdp[128]={};
 ab.mem=memory;ab.hw_params=&params;ab.ce.ce_pipe[3].src_ring=&cr;ab.hal.rdp={0x10004000,rdp};
 auto &ring=ab.hal.srng_list[67];ring.initialized=true;ring.hwreg_base[0]=0x1b86000;ring.entry_size=4;ring.num_entries=32;ring.ring_base_paddr=0x10008000;
 ring.u.src_ring={reinterpret_cast<u32*>(memory+0x984),&rdp[67]};
 reads=notes=par_reads=0;emr_ring(&ab);assert(reads==6&&notes==4&&par_reads==1);
 u32 expected[]={0x1b86000,0x1b86004,0x1b86010,0x1b86008,0x1b8601c,0x1b86020};assert(!memcmp(offsets,expected,sizeof(expected)));cases++;
 for(unsigned bad=0;bad<5;bad++){
  reads=notes=par_reads=0;ring.initialized=true;ring.hwreg_base[0]=0x1b86000;bad_offset=0;ab.hal.rdp.vaddr=rdp;params.ce_count=4;
  if(bad==0)ring.initialized=false;if(bad==1)bad_offset=1;if(bad==2)ab.hal.rdp.vaddr=nullptr;if(bad==3)ring.hwreg_base[0]++;if(bad==4)params.ce_count=3;
  emr_ring(&ab);assert(!reads&&!notes&&!par_reads);cases++;
 }
 unsigned char packet[24]={};word(packet,0x4010);memcpy(packet+4,payload,20);sk_buff skb={packet,24};notes=0;
 emr_event(&ab,&skb,0x4001);assert(!notes);emr_event(&ab,&skb,0x4010);assert(notes==1&&captured[2]==EmrResponse&&captured[0]==0&&captured[1]==1);cases++;
 printf("PASS %u actual response/config parser cases; six documented reads, bounded geometry and unaligned LE input\n",cases);
}
'''
    (out/'test.cpp').write_text(code)
    command=['clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(out),'-I'+str(ROOT/'drivers/EldenWifi'),str(out/'test.cpp'),'-o',str(out/'test')]
    for name,command in [('compile',command),('run',[str(out/'test')])]:
        run=subprocess.run(command,capture_output=True);(out/(name+'.log')).write_bytes(run.stdout+run.stderr);run.check_returncode()
    receipt=dict(passed=True,actual_response_and_config_helpers=True,hardware_mmio_par_and_linux_protocol_modeled=True,
        source_reversible=True,source_sha256=hashlib.sha256(derived).hexdigest(),fixed_bytes=20,reads=6,
        sanitizers=['ASan','UBSan'],summary=(out/'run.log').read_text().strip(),hardware_tested=False)
    (out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt['summary'])
if __name__=='__main__':main()
