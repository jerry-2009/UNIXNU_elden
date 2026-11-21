"""Execute actual old/new cap callbacks with short/full TLVs and allocation faults."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from MacPhyStridePatch import callback,patch


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wmi-source',type=Path,required=True);parser.add_argument('--wmi-header',type=Path,required=True)
    parser.add_argument('--cc',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    old=args.wmi_source.read_bytes();new=patch(old);(out/'wmi.c').write_bytes(new)
    header=args.wmi_header.read_text()
    def structure(name):
        start=header.index('struct '+name+' {');return header[start:header.index('} __packed;',start)+len('} __packed;')]
    layout=structure('ath12k_wmi_ppe_threshold_params')+'\n'+structure('ath12k_wmi_mac_phy_caps_params')
    code=r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint16_t u16;typedef uint32_t u32;typedef uint32_t __le32;
#define __packed __attribute__((packed))
#define WMI_MAX_NUM_SS 8
#define WMI_MAX_HECAP_PHY_SIZE 3
#define WMI_TAG_MAC_PHY_CAPABILITIES 1
#define GFP_ATOMIC 0
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
@LAYOUT@
struct ath12k_base{};
struct ath12k_wmi_svc_rdy_ext_parse {u32 n_mac_phy_caps,tot_phy_id;struct ath12k_wmi_mac_phy_caps_params *mac_phy_caps;};
static size_t requested,backing=65536;static unsigned allocations;static int alloc_fail;
static unsigned char *buffer;
static void *kzalloc(size_t bytes,int ignored){
 (void)ignored;allocations++;requested=bytes;if(alloc_fail)return NULL;
 buffer=calloc(1,backing);assert(buffer&&bytes<=backing);return buffer;
}
@OLD@
@NEW@
int main(){
 unsigned cases=0;const size_t stride=sizeof(struct ath12k_wmi_mac_phy_caps_params);
 for(unsigned count=1;count<=8;count++)for(unsigned short_tlv=0;short_tlv<4;short_tlv++){
   const u16 length=short_tlv==0?20:short_tlv==1?(u16)(stride-4):short_tlv==2?(u16)stride:(u16)(stride+12);
   unsigned char payload[512];memset(payload,0x42,sizeof payload);
   for(unsigned fixed=0;fixed<2;fixed++){
     struct ath12k_wmi_svc_rdy_ext_parse state={0,count,NULL};allocations=0;requested=0;
     for(unsigned index=0;index<count;index++){
       int result=fixed?new_callback(NULL,1,length,payload,&state):old_callback(NULL,1,length,payload,&state);
       assert(result==0&&state.n_mac_phy_caps==index+1&&allocations==1);
     }
     const size_t copied=length<stride?length:stride,last_end=(count-1)*stride+copied;
     assert(requested==count*(fixed?stride:copied));
     if(fixed)assert(last_end<=requested);else if(count>1&&copied<stride)assert(last_end>requested);
     for(unsigned index=0;index<count;index++){
       for(size_t byte=0;byte<copied;byte++)assert(buffer[index*stride+byte]==0x42);
       if(fixed)for(size_t byte=copied;byte<stride;byte++)assert(!buffer[index*stride+byte]);
     }
     free(buffer);buffer=NULL;cases++;
   }
 }
 for(unsigned fail=0;fail<3;fail++)for(unsigned fixed=0;fixed<2;fixed++){
   struct ath12k_wmi_svc_rdy_ext_parse state={fail==1?2u:0u,2,NULL};allocations=0;alloc_fail=fail==2;
   int expected=fail==0?-EPROTO:fail==1?-ENOBUFS:-ENOMEM;
   int result=fixed?new_callback(NULL,fail==0?2:1,20,NULL,&state):old_callback(NULL,fail==0?2:1,20,NULL,&state);
   assert(result==expected&&state.n_mac_phy_caps==(fail==1?2u:0u));cases++;
 }
 alloc_fail=0;printf("PASS %u actual old/new MAC-PHY callbacks; full stride %zu; short TLV allocation overrun reproduced without out-of-allocation writes\n",cases,stride);
}
'''
    code=code.replace('@LAYOUT@',layout).replace('@OLD@',callback(old.decode()).replace('ath12k_wmi_mac_phy_caps_parse(','old_callback(',1))
    code=code.replace('@NEW@',callback(new.decode()).replace('ath12k_wmi_mac_phy_caps_parse(','new_callback(',1))
    source=out/'test.c';source.write_text(code)
    cmd=[str(args.cc),'-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
        '-fsanitize=address,undefined','-fno-sanitize-recover=all',str(source),'-o',str(out/'test')]
    if sys.platform=='darwin':cmd[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for name,command in [('compile',cmd),('run',[str(out/'test')])]:
        result=subprocess.run(command,capture_output=True);(out/(name+'.log')).write_bytes(result.stdout+result.stderr);result.check_returncode()
    proof=dict(passed=True,actual_production_callback_executed=True,original_short_tlv_stride_defect_reproduced=True,
        hardware_proven=False,sanitizers=['ASan','UBSan'],summary=(out/'run.log').read_text().strip(),
        wmi_source_sha256=hashlib.sha256(old).hexdigest(),wmi_header_sha256=hashlib.sha256(args.wmi_header.read_bytes()).hexdigest(),
        generated_source_sha256=hashlib.sha256(new).hexdigest(),upstream='4c6eb712a91fa079be6f9f1419c96e0ad2227081',
        board_revision='26f8f87f0a556e7984366c64cebc16d49e15d22f',
        source_inputs={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
          ['tools/test_wifi_mac_phy_stride.py','drivers/EldenWifi/peach/MacPhyStridePatch.py']})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))


if __name__=='__main__':main()
