"""Execute OEM preferred-mode mapping and both original/fixed init wrappers."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('cc','core-source','wmi-source','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
    from OemInitModePatch import patch
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    for name,path in [('core.c',a.core_source),('wmi.c',a.wmi_source)]:(out/name).write_bytes(patch(name,path.read_bytes()))
    helper=(ROOT/'drivers/EldenWifi/OemInitMode.inc').read_text()
    s=a.wmi_source.read_text();at=s.index('int ath12k_wmi_cmd_init(');original=s[at:s.index('\n}\n',at)+3].replace('ath12k_wmi_cmd_init(', 'init_original(',1)
    s=(out/'wmi.c').read_text();at=s.index('int ath12k_wmi_cmd_init(');fixed=s[at:s.index('\n}\n',at)+3].replace('ath12k_wmi_cmd_init(', 'init_fixed(',1)
    code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;typedef uint8_t u8;
#define WMI_HOST_MAX_PDEV 3
#define MAX_RADIOS 3
#define ATH12K_HW_PEACH_HW20 17
#define WMI_HOST_HW_MODE_SINGLE 0
#define WMI_HOST_HW_MODE_MAX 6
#define WMI_HOST_WLAN_2GHZ_CAP 1
#define WMI_HOST_WLAN_5GHZ_CAP 2
#define WMI_HOST_WLAN_2GHZ_5GHZ_CAP 3
#define WMI_TLV_SERVICE_REG_CC_EXT_EVENT_SUPPORT 0
struct ath12k_fw_pdev {u32 pdev_id,phy_id,supported_bands;};
struct ath12k_wmi_hal_reg_capabilities_ext_arg {u32 phy_id,low_2ghz_chan,high_2ghz_chan,low_5ghz_chan,high_5ghz_chan;};
struct ath12k_wmi_pdev_band_arg {u32 pdev_id,start_freq,end_freq;};
struct res_cfg {unsigned is_reg_cc_ext_event_supported,rx_decap_mode,peer_metadata_ver;};
struct ath12k_wmi_init_cmd_arg {struct res_cfg res_cfg;u8 num_mem_chunks;void *mem_chunks;u32 hw_mode_id,num_band_to_mac;struct ath12k_wmi_pdev_band_arg band_to_mac[3];};
struct ath12k_wmi_base {u32 preferred_hw_mode;unsigned svc_map[1];u8 num_mem_chunks;void *mem_chunks;struct {unsigned x;} wmi[1];};
struct ath12k_hw_params {bool single_pdev_only;void (*wmi_init)(void *,struct res_cfg *);};
struct ath12k_dp {unsigned peer_metadata_ver;};
struct ath12k_base {unsigned hw_rev;struct ath12k_hw_params *hw_params;struct ath12k_wmi_base wmi_ab;u32 fw_pdev_count;struct ath12k_fw_pdev fw_pdev[3];struct ath12k_wmi_hal_reg_capabilities_ext_arg hal_reg_cap[3];unsigned num_radios;struct {unsigned wmi_conf_rx_decap_mode;} wow;struct ath12k_dp dp;};
static unsigned sends;static struct ath12k_wmi_init_cmd_arg sent;
static int test_bit(unsigned n,unsigned *p){return (p[0]&(1u<<n))!=0;}
static struct ath12k_dp *ath12k_ab_to_dp(struct ath12k_base *ab){return &ab->dp;}
static void ath12k_fill_band_to_mac_param(struct ath12k_base *ab,struct ath12k_wmi_pdev_band_arg *p){p[0]=(struct ath12k_wmi_pdev_band_arg){0,2300,7125};assert(ab->num_radios==1);}
static int ath12k_init_cmd_send(void *,struct ath12k_wmi_init_cmd_arg *a){sent=*a;sends++;return 0;}
static void ath12k_warn(struct ath12k_base *,const char *,...){}
static void wmi_init(void *,struct res_cfg *r){r->peer_metadata_ver=1;r->rx_decap_mode=2;}
@HELPER@
@ORIGINAL@
@FIXED@
static struct ath12k_base good(struct ath12k_hw_params *p){
 struct ath12k_base ab={};ab.hw_rev=17;ab.hw_params=p;ab.wmi_ab.preferred_hw_mode=5;ab.num_radios=1;ab.fw_pdev_count=2;
 ab.fw_pdev[0]=(struct ath12k_fw_pdev){1,0,1};ab.fw_pdev[1]=(struct ath12k_fw_pdev){2,1,2};
 ab.hal_reg_cap[0]=(struct ath12k_wmi_hal_reg_capabilities_ext_arg){0,2300,2500,0,0};ab.hal_reg_cap[1]=(struct ath12k_wmi_hal_reg_capabilities_ext_arg){1,0,0,4900,7125};return ab;
}
int main(){
 unsigned cases=0;struct ath12k_hw_params params={true,wmi_init};struct ath12k_base ab=good(&params);
 assert(!init_original(&ab)&&sent.hw_mode_id==6&&sent.num_band_to_mac==1&&sent.band_to_mac[0].pdev_id==0);cases++;
 assert(!init_fixed(&ab)&&sent.hw_mode_id==5&&sent.num_band_to_mac==2&&sent.band_to_mac[0].pdev_id==1&&sent.band_to_mac[1].pdev_id==2&&sent.band_to_mac[0].start_freq==2300&&sent.band_to_mac[1].start_freq==4900&&ab.num_radios==1);cases++;
 for(unsigned hw=0;hw<20;hw++){ab=good(&params);ab.hw_rev=hw;assert(!init_fixed(&ab));assert(sent.hw_mode_id==(hw==17?5:6));cases++;}
 for(unsigned fault=0;fault<10;fault++){
  ab=good(&params);if(fault==0)ab.fw_pdev_count=0;else if(fault==1)ab.fw_pdev_count=4;else if(fault==2)ab.wmi_ab.preferred_hw_mode=6;
  else if(fault==3)ab.fw_pdev[1].pdev_id=1;else if(fault==4)ab.fw_pdev[1].phy_id=0;else if(fault==5)ab.fw_pdev[1].phy_id=3;
  else if(fault==6)ab.fw_pdev[0].supported_bands=0;else if(fault==7)ab.hal_reg_cap[1].phy_id=0;else if(fault==8)ab.hal_reg_cap[1].low_5ghz_chan=0;else ab.hal_reg_cap[1].high_5ghz_chan=4000;
  unsigned before=sends;assert(init_fixed(&ab)==-EINVAL&&sends==before);cases++;
 }
 ab=good(&params);ab.wmi_ab.preferred_hw_mode=0;assert(!init_fixed(&ab)&&sent.hw_mode_id==6);cases++;
 params.single_pdev_only=false;ab=good(&params);assert(!init_fixed(&ab)&&sent.hw_mode_id==5&&sent.num_band_to_mac==1);params.single_pdev_only=true;cases++;
 printf("PASS %u actual init/mapping cases; logical alias0 retained, preferred5 and physical bands1/2 derived from capabilities\n",cases);
}
'''.replace('@HELPER@',helper).replace('@ORIGINAL@',original).replace('@FIXED@',fixed)
    src=out/'test.cpp';src.write_text(code);cmd=[str(a.cc),'-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(src),'-o',str(out/'test')]
    if sys.platform=='darwin':cmd[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for name,command in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(command,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    own=['tools/test_wifi_oem_init.py','tools/build_wifi_oem_init.py','drivers/EldenWifi/OemInitMode.inc','drivers/EldenWifi/peach/OemInitModePatch.py']
    proof=dict(passed=True,actual_helper_init_wrapper=True,asan_ubsan=True,mmio_firmware_modeled=True,hardware_tested=False,summary=(out/'run.log').read_text().strip(),source_inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in own})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
