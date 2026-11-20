"""Verify callback-derived WAKE MSI values and original error behavior."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('cc', 'qmi-source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / 'drivers/EldenWifi/peach'))
    from HostWakeCapabilityPatch import patch
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'qmi.c').write_bytes(patch(args.qmi_source.read_bytes()))
    code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
#define ATH12K_HW_PEACH_HW20 17
struct ath12k_base;
struct ath12k_hif_ops {int (*get_user_msi_vector)(struct ath12k_base *,char *,int *,u32 *,u32 *);};
struct ath12k_base {unsigned hw_rev;struct {struct ath12k_hif_ops *ops;}hif;};
struct qmi_wlanfw_host_cap_req_msg_v01 {unsigned char wake_msi_valid;u32 wake_msi;u32 untouched[12];};
static unsigned calls;static int error,vectors=1;static u32 data=13,base=13;
static int get(struct ath12k_base *ab,char *name,int *v,u32 *d,u32 *b){assert(ab&&strcmp(name,"WAKE")==0);calls++;*v=vectors;*d=data;*b=base;return error;}
static void ath12k_warn(struct ath12k_base *ab,const char *format,...){(void)ab;(void)format;}
@HELPER@
int main(){unsigned cases=0;struct ath12k_hif_ops ops={get};struct ath12k_base ab={17,{&ops}};
 struct qmi_wlanfw_host_cap_req_msg_v01 req={0},old;
 assert(!elden_wifi_host_wake_capability(&ab,&req)&&req.wake_msi==13&&req.wake_msi_valid&&calls==1);cases++;
 assert(!elden_wifi_host_wake_capability(&ab,&req)&&calls==2);cases++;
 for(unsigned hw=0;hw<20;hw++){ab.hw_rev=hw;memset(&req,0x6a,sizeof req);old=req;unsigned seen=calls;
  if(hw==17){req.wake_msi_valid=0;assert(!elden_wifi_host_wake_capability(&ab,&req));}else{assert(!elden_wifi_host_wake_capability(&ab,&req)&&!memcmp(&req,&old,sizeof req)&&calls==seen);}cases++;}
 ab.hw_rev=17;
 for(unsigned fault=0;fault<8;fault++){memset(&req,0,sizeof req);old=req;ops.get_user_msi_vector=get;vectors=1;data=13;base=13;error=0;
  if(fault==0)error=-5;else if(fault==1)vectors=0;else if(fault==2)vectors=2;else if(fault==3)base=12;
  else if(fault==4)data=32;else if(fault==5)data=12;else if(fault==6)ops.get_user_msi_vector=0;else{req.wake_msi_valid=1;req.wake_msi=14;old=req;}
  assert(elden_wifi_host_wake_capability(&ab,&req)<0&&!memcmp(&req,&old,sizeof req));cases++;}
 printf("PASS %u actual host-WAKE capability cases; derived vector, non-Peach unchanged, callback/shape errors preserved\n",cases);
}
'''.replace('@HELPER@', (ROOT / 'drivers/EldenWifi/HostWakeCapability.inc').read_text())
    source = out / 'test.c'
    source.write_text(code)
    cmd = [str(args.cc), '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', str(source), '-o', str(out / 'test')]
    if sys.platform == 'darwin':
        cmd[1:1] = ['-isysroot', subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()]
    for name, command in [('compile', cmd), ('run', [str(out / 'test')])]:
        result = subprocess.run(command, capture_output=True)
        (out / (name + '.log')).write_bytes(result.stdout + result.stderr)
        result.check_returncode()
    own = ['tools/test_wifi_host_wake_capability.py', 'drivers/EldenWifi/HostWakeCapability.inc', 'drivers/EldenWifi/peach/HostWakeCapabilityPatch.py']
    proof = dict(passed=True, actual_helper=True, asan_ubsan=True, callback_modeled=True, hardware_tested=False, summary=(out / 'run.log').read_text().strip(), source_inputs={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in own})
    (out / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
