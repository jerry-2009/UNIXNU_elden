"""Exercise actual old/new Host Capability requests and preserved QMI errors."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('cc','qmi-source','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'));from EagerMemoryPatch import patch,body
    old=a.qmi_source.read_bytes();new=patch(old);out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);(out/'qmi.c').write_bytes(new)
    code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;typedef uint64_t u64;
#define ATH12K_HW_PEACH_HW20 17
#define BIT(n) (1u<<(n))
#define HOST_CSTATE_BIT 4u
#define SLEEP_CLOCK_SELECT_INTERNAL_BIT 2u
#define PLATFORM_CAP_PCIE_GLOBAL_RESET 8u
#define CNSS_AUX_UC_SUPPORT_V01 2u
#define ATH12K_QMI_WLANFW_TIMEOUT_MS 10000
#define QMI_WLANFW_HOST_CAP_REQ_V01 0x34
#define QMI_WLANFW_HOST_CAP_REQ_MSG_V01_MAX_LEN 900
#define QMI_RESULT_SUCCESS_V01 0
struct qmi_handle{int unused;};struct qmi_txn{int unused;};
struct qmi_wlanfw_host_cap_req_msg_v01{
 unsigned char num_clients_valid;u32 num_clients;unsigned char mem_cfg_mode_valid;u32 mem_cfg_mode;
 unsigned char bdf_support_valid,bdf_support,m3_support_valid,m3_support,m3_cache_support_valid,m3_cache_support;
 unsigned char cal_done_valid,cal_done,feature_list_valid;u64 feature_list;
 unsigned char nm_modem_valid,nm_modem,nw_on_demand_mem_valid,nw_on_demand_mem;
 unsigned char wake_msi_valid;u32 wake_msi;
};
struct qmi_wlanfw_host_cap_resp_msg_v01{struct{int result,error;}resp;};
struct params{struct{void *m3_loader;bool download_tme_lite,download_aux_ucode;}fw;u64 qmi_cnss_feature_bitmap;bool internal_sleep_clock;};
struct ath12k_base{unsigned hw_rev;struct{u32 target_mem_mode;unsigned char cal_done;struct qmi_handle handle;}qmi;struct params *hw_params;};
static int loader;static void *ath12k_m3_fw_loader_driver=&loader;
static int qmi_wlanfw_host_cap_resp_msg_v01_ei,qmi_wlanfw_host_cap_req_msg_v01_ei;
static unsigned sends,cancels;static int wake_error,mlo_error,init_error,send_error,wait_error,reply_error;
static struct qmi_wlanfw_host_cap_req_msg_v01 captured;
static int elden_wifi_host_wake_capability(struct ath12k_base *ab,struct qmi_wlanfw_host_cap_req_msg_v01 *r){if(wake_error)return wake_error;if(ab->hw_rev==17){r->wake_msi_valid=1;r->wake_msi=13;}return 0;}
static int ath12k_host_cap_parse_mlo(struct ath12k_base *ab,struct qmi_wlanfw_host_cap_req_msg_v01 *r){(void)ab;(void)r;return mlo_error;}
static int qmi_txn_init(struct qmi_handle *h,struct qmi_txn *t,void *e,struct qmi_wlanfw_host_cap_resp_msg_v01 *r){assert(h&&t&&e&&r);r->resp.result=reply_error;r->resp.error=7;return init_error;}
static int qmi_send_request(struct qmi_handle *h,void *a,struct qmi_txn *t,int id,int max,void *e,struct qmi_wlanfw_host_cap_req_msg_v01 *r){assert(h&&!a&&t&&id==0x34&&max==900&&e);sends++;captured=*r;return send_error;}
static int qmi_txn_wait(struct qmi_txn *t,int ms){assert(t&&ms==10000);return wait_error;}
static int msecs_to_jiffies(int ms){return ms;}
static void qmi_txn_cancel(struct qmi_txn *t){assert(t);cancels++;}
static void ath12k_warn(struct ath12k_base *ab,const char *format,...){assert(ab&&format);}
@OLD@
@NEW@
static void reset(){sends=cancels=0;wake_error=mlo_error=init_error=send_error=wait_error=reply_error=0;memset(&captured,0,sizeof captured);}
int main(void){
 unsigned cases=0;struct params p={0};p.fw.m3_loader=ath12k_m3_fw_loader_driver;p.fw.download_tme_lite=true;p.qmi_cnss_feature_bitmap=0x12345678;
 struct ath12k_base ab={17,{1,1,{0}},&p};struct qmi_wlanfw_host_cap_req_msg_v01 expected;
 for(unsigned hw=0;hw<20;hw++)for(unsigned flags=0;flags<4;flags++){
  ab.hw_rev=hw;p.internal_sleep_clock=flags&1;p.fw.download_aux_ucode=flags&2;
  reset();assert(!old_host_cap(&ab)&&sends==1);expected=captured;
  reset();assert(!new_host_cap(&ab)&&sends==1);
  if(hw==17){expected.nw_on_demand_mem_valid=0;expected.nw_on_demand_mem=0;}
  assert(!memcmp(&expected,&captured,sizeof captured));cases++;
 }
 ab.hw_rev=17;
 for(unsigned failure=0;failure<6;failure++){
  reset();if(failure==0)wake_error=-5;else if(failure==1)mlo_error=-22;else if(failure==2)init_error=-12;else if(failure==3)send_error=-5;else if(failure==4)wait_error=-110;else reply_error=1;
  int rc=new_host_cap(&ab);assert(rc<0);
  assert(sends==(failure>=3));assert(cancels==(failure==3));cases++;
 }
 printf("PASS %u actual old/new Host Capability cases; request fields and QMI errors preserved, transport modeled\n",cases);
}
'''.replace('@OLD@',body(old.decode()).replace('ath12k_qmi_host_cap_send','old_host_cap',1)).replace('@NEW@',body(new.decode()).replace('ath12k_qmi_host_cap_send','new_host_cap',1))
    # The native QMI declarations use array pointers for element tables.
    code=code.replace('qmi_wlanfw_host_cap_resp_msg_v01_ei, &resp','&qmi_wlanfw_host_cap_resp_msg_v01_ei, &resp').replace('qmi_wlanfw_host_cap_req_msg_v01_ei, &req','&qmi_wlanfw_host_cap_req_msg_v01_ei, &req')
    source=out/'test.c';source.write_text(code);cmd=[str(a.cc),'-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(source),'-o',str(out/'test')]
    if sys.platform=='darwin':cmd[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for name,command in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(command,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    own=['tools/test_wifi_eager_memory.py','drivers/EldenWifi/peach/EagerMemoryPatch.py']
    proof=dict(passed=True,actual_hostcap_body=True,asan_ubsan=True,qmi_transport_modeled=True,hardware_tested=False,summary=(out/'run.log').read_text().strip(),source_inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in own})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
